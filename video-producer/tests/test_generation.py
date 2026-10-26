import asyncio
import itertools

import pytest

from backend import estimate, generation, presets, takes, tracker
from backend.estimate import Order
from backend.generation import Blocked, TakeError
from hooks import generation_hooks
from src.plugin_api import HookContext

SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 6, "firstFromPrevious": False}]
GPU = "video-producer.gpu_minutes"


@pytest.fixture
def seeds(monkeypatch):
    counter = itertools.count(1001)
    monkeypatch.setattr(generation, "new_seed", lambda: next(counter))


def _start(core, project, owner="user-1", **fields):
    order = Order(**{"shots": ["s1", "s2"], "quality": "draft", "variants": 2, "preset_id": presets.WAN, **fields})
    user = core.users[owner]
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    return asyncio.run(generation.start(user, project, evaluation))


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _done_take(core, make_project, preset_id=presets.WAN, **project_parts):
    project = make_project(**({"clips": SHOTS[:1]} | project_parts))
    (take,) = _start(core, project, shots=["s1"], variants=1, preset_id=preset_id)
    core.complete(take["generation_id"])
    _tick()
    return project, takes.get_take(take["id"])


def test_one_take_per_shot_and_variant_each_with_its_own_seed_and_generation(core, make_project, seeds):
    core.use_wan()
    project = make_project(clips=SHOTS)

    created = _start(core, project)

    assert [(take["shot_id"], take["variant"], take["seed"]) for take in created] == [
        ("s1", "A", 1001),
        ("s1", "B", 1002),
        ("s2", "A", 1003),
        ("s2", "B", 1004),
    ]
    assert all(take["status"] == "queued" and take["quality"] == "draft" and take["kind"] == "render" for take in created)
    assert all(take["user_id"] == "user-1" and take["profile"] == "FL2VA" for take in created)
    assert [take["generation_id"] for take in created] == ["gen-1", "gen-2", None, None]
    for take, (user_id, request) in zip(created, core.submitted):
        assert user_id == "user-1"
        assert request["idempotency_key"] == f"vp:{take['id']}"
        assert request["form_data"]["seed"] == take["seed"]
        assert request["form_data"]["video_director"]["settings"]["seed"] == take["seed"]
        assert request["mode"] == "video" and request.get("form_data", {}).get("quantity", 1) == 1
        assert take["request"] == request


def test_queued_takes_wait_for_a_free_slot_then_the_tracker_submits_them(core, make_project, store):
    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    project = make_project(clips=SHOTS)

    created = _start(core, project, variants=1)

    assert [take["generation_id"] for take in created] == ["gen-1", None]
    assert takes.in_flight("user-1") == 1
    assert _tick() is True
    assert len(core.submitted) == 1

    core.complete("gen-1")
    _tick()

    assert takes.get_take(created[0]["id"])["status"] == "done"
    assert takes.get_take(created[1]["id"])["generation_id"] == "gen-2"
    assert [request["idempotency_key"] for _, request in core.submitted] == [f"vp:{take['id']}" for take in created]


def test_native_takes_reserve_their_minutes_under_their_own_reference(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS)

    created = _start(core, project, variants=1)

    assert core.recorded == [
        ("user-1", GPU, round(4 * 10 / 60, 3), f"video-producer:{created[0]['id']}"),
        ("user-1", GPU, 1.0, f"video-producer:{created[1]['id']}"),
    ]
    assert [take["units_reserved"] for take in created] == [round(4 * 10 / 60, 3), 1.0]
    assert takes.list_jobs(created[0]["id"])[0]["limit_ref_id"] == f"video-producer:{created[0]['id']}"


def test_cloud_takes_reserve_nothing(core, make_project):
    core.use_openrouter()
    project = make_project(clips=SHOTS)

    created = _start(core, project, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert core.recorded == []
    assert all(take["units_reserved"] == 0 and take["model_id"] == "cm-veo" for take in created)
    assert created[0]["mode"] == "txt2video"


def test_a_blocked_evaluation_creates_no_take(core, make_project):
    project = make_project(clips=SHOTS)

    with pytest.raises(Blocked) as caught:
        _start(core, project)

    assert [block["code"] for block in caught.value.blocks] == ["no_preset"]
    assert takes.list_takes(project["id"]) == []


@pytest.mark.parametrize(
    "refusal, code",
    [
        (PermissionError("Preset not available"), "preset_not_available"),
        (ValueError("resolution: Invalid resolution"), "invalid_request"),
        (RuntimeError("No backend"), "no_backend"),
    ],
)
def test_a_take_the_core_refuses_fails_and_is_refunded(core, make_project, refusal, code):
    core.use_wan()
    core.refusal = refusal
    project = make_project(clips=SHOTS[:1])

    (take,) = _start(core, project, shots=["s1"], variants=1)

    assert (take["status"], take["error_code"], take["generation_id"]) == ("failed", code, None)
    assert core.refunded == [f"video-producer:{take['id']}"]
    assert core.notified[-1]["notification_type"] == "video-producer.take_failed"


def test_a_running_generation_reports_its_progress_step_start_and_backend(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.states["gen-1"] = {
        "status": "running", "progress": 0.425, "current_step": "Sampling", "backend_id": "b-local",
        "started_at": "2026-10-17T10:00:00+00:00",
    }

    _tick()

    current = takes.get_take(take["id"])
    assert (current["status"], current["progress"], current["step"], current["backend_id"], current["started_at"]) == (
        "running",
        42.5,
        "Sampling",
        "b-local",
        "2026-10-17T10:00:00+00:00",
    )


def test_a_finished_take_gets_its_video_calibration_quota_adjustment_and_notification(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.complete("gen-1", duration_ms=90000, width=832, height=480, seconds=4.06, fps=16.0)

    _tick()

    done = takes.public(takes.get_take(take["id"]))
    assert done["status"] == "done" and done["progress"] == 100.0
    assert done["url"] == "/api/media/generations/gen-1/1.mp4"
    assert done["thumb_url"] == "/api/media/generations/gen-1/1.mp4?size=medium"
    assert (done["file_id"], done["width"], done["height"], done["duration_s"], done["fps"]) == ("file-gen-1", 832, 480, 4.06, 16.0)
    assert done["backend_id"] == "b-local" and done["finished_at"]
    assert takes.calibration(presets.WAN, "b-local", "832x480") == [(4.0, 90000)]
    ref = f"video-producer:{take['id']}"
    assert core.recorded[-1] == ("user-1", GPU, round(1.5 - 0.667, 3), f"{ref}:adjust")
    assert core.notified == [
        {
            "user_id": "user-1",
            "notification_type": "video-producer.take_done",
            "title": "Take ready",
            "message": f"{project['name']}: the draft take A is ready.",
            "level": "success",
            "metadata": {"project_id": project["id"], "take_id": take["id"], "shot_id": "s1"},
        }
    ]
    assert takes.list_jobs(take["id"])[0]["finished_at"]


def test_a_take_shorter_than_reserved_refunds_and_records_its_real_minutes(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.complete("gen-1", duration_ms=12000)

    _tick()

    ref = f"video-producer:{take['id']}"
    assert core.refunded == [ref]
    assert core.recorded[-1] == ("user-1", GPU, 0.2, f"{ref}:actual")


def test_a_done_take_without_thumbnail_has_no_thumbnail_url(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.complete("gen-1", thumbnail=False)

    _tick()

    assert takes.public(takes.get_take(take["id"]))["thumb_url"] is None


def test_a_generation_without_video_fails_its_take(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.complete("gen-1")
    core.files["gen-1"] = core.files["gen-1"][:1]

    _tick()

    assert takes.get_take(take["id"])["error_code"] == "no_output"


def test_a_failed_generation_fails_its_take_with_the_core_code_and_user_message(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1")

    _tick()

    failed = takes.get_take(take["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "cuda_oom", "The GPU ran out of memory.")
    assert core.refunded == [f"video-producer:{take['id']}"]
    assert core.notified[-1]["notification_type"] == "video-producer.take_failed"
    assert core.notified[-1]["message"].endswith("failed. The GPU ran out of memory.")


def test_a_generation_the_core_lost_fails_its_take(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    del core.states["gen-1"]

    _tick()

    assert takes.get_take(take["id"])["error_code"] == "generation_not_found"


def test_a_take_whose_owner_is_gone_fails(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    del core.users["user-1"]

    _tick()

    assert takes.get_take(take["id"])["error_code"] == "user_not_found"


def test_a_take_whose_owner_cannot_be_read_waits_for_the_next_round(core, make_project, monkeypatch, store):
    from backend import core_bridge

    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    project = make_project(clips=SHOTS)
    first, waiting = _start(core, project, variants=1)
    core.complete("gen-1")

    def unreadable(user_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(core_bridge, "get_user", unreadable)
    assert _tick() is True
    assert takes.get_take(first["id"])["status"] == "queued" and takes.get_take(waiting["id"])["generation_id"] is None

    monkeypatch.setattr(core_bridge, "get_user", core.get_user)
    _tick()
    assert takes.get_take(first["id"])["status"] == "done" and takes.get_take(waiting["id"])["generation_id"] == "gen-2"


def test_the_hooks_and_the_tracker_settle_a_take_once(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.complete("gen-1")
    context = HookContext(
        hook_name="generation.after_complete",
        plugin_id="system",
        data={"generation_id": "gen-1", "status": "completed", "duration": 61.0, "preset_id": presets.WAN, "user_id": "user-1"},
    )

    assert generation_hooks.on_after_complete(context) is context
    generation_hooks.on_after_complete(context)
    _tick()

    assert takes.get_take(take["id"])["status"] == "done"
    assert len(takes.calibration(presets.WAN, "b-local", "832x480")) == 1
    assert len(core.notified) == 1
    assert len([record for record in core.recorded if record[3].endswith(":adjust")]) == 1


def test_the_failed_hook_settles_a_take_before_after_complete_and_the_tracker(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1", code="other", message="from the state")
    failed = HookContext(
        hook_name="generation.failed",
        plugin_id="system",
        data={"generation_id": "gen-1", "error_code": "missing_model_file", "message": "A model file is missing."},
    )
    completed = HookContext(hook_name="generation.after_complete", plugin_id="system", data={"generation_id": "gen-1", "status": "failed"})

    generation_hooks.on_failed(failed)
    generation_hooks.on_after_complete(completed)
    _tick()

    current = takes.get_take(take["id"])
    assert (current["error_code"], current["error_message"]) == ("missing_model_file", "A model file is missing.")
    assert core.refunded == [f"video-producer:{take['id']}"]
    assert len(core.notified) == 1


def test_after_complete_alone_reads_the_failure_from_the_state(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1")

    generation_hooks.on_after_complete(
        HookContext(hook_name="generation.after_complete", plugin_id="system", data={"generation_id": "gen-1", "status": "failed"})
    )

    assert takes.get_take(take["id"])["error_code"] == "cuda_oom"


def test_after_complete_cancelled_cancels_and_refunds(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)

    generation_hooks.on_after_complete(
        HookContext(hook_name="generation.after_complete", plugin_id="system", data={"generation_id": "gen-1", "status": "cancelled"})
    )

    assert takes.get_take(take["id"])["status"] == "cancelled"
    assert core.refunded == [f"video-producer:{take['id']}"]


@pytest.mark.parametrize("data", [{}, {"generation_id": "unknown", "status": "completed"}, None])
def test_the_generation_hooks_ignore_generations_of_no_take(core, data):
    context = HookContext(hook_name="generation.after_complete", plugin_id="system", data=data)

    assert generation_hooks.on_after_complete(context) is context
    assert generation_hooks.on_failed(context) is context
    assert core.notified == []


def test_the_generation_hooks_swallow_errors(core, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(generation, "settle_from_hook", broken)
    context = HookContext(hook_name="generation.failed", plugin_id="system", data={"generation_id": "gen-1"})

    assert generation_hooks.on_failed(context) is context
    assert generation_hooks.on_after_complete(context) is context
    assert "Could not settle the take of generation gen-1" in caplog.text


def test_cancelling_a_submitted_take_cancels_its_generation_and_refunds(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)

    cancelled = asyncio.run(generation.cancel(core.users["user-1"], take))

    assert cancelled["status"] == "cancelled" and cancelled["finished_at"]
    assert core.cancelled == [("user-1", "gen-1")]
    assert core.refunded == [f"video-producer:{take['id']}"]
    _tick()
    assert core.refunded == [f"video-producer:{take['id']}"]


def test_cancelling_a_take_still_waiting_needs_no_core_call(core, make_project, store):
    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    project = make_project(clips=SHOTS)
    waiting = _start(core, project, variants=1)[1]

    cancelled = asyncio.run(generation.cancel(core.users["user-1"], waiting))

    assert cancelled["status"] == "cancelled"
    assert core.cancelled == []
    core.complete("gen-1")
    _tick()
    assert len(core.submitted) == 1


def test_cancelling_a_finished_take_changes_nothing(core, make_project):
    core.use_wan()
    _, done = _done_take(core, make_project)

    assert asyncio.run(generation.cancel(core.users["user-1"], done))["status"] == "done"
    assert core.cancelled == []


def test_a_take_cancelled_while_it_was_submitted_cancels_the_new_generation(core, make_project, monkeypatch):
    from backend import core_bridge

    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    original = core.submit_generation

    async def submit(user, request):
        result = await original(user, request)
        generation.cancel_local(takes.list_takes(project["id"])[0])
        return result

    monkeypatch.setattr(core_bridge, "submit_generation", submit)
    (take,) = _start(core, project, shots=["s1"], variants=1)

    assert take["status"] == "cancelled" and take["generation_id"] is None
    assert core.cancelled == [("user-1", "gen-1")]


def test_a_final_by_upscale_runs_seedvr2_on_the_source_video(core, make_project, seeds):
    core.use_wan()
    core.use_seedvr2()
    project, source = _done_take(core, make_project)
    core.add_media(
        {"kind": "history", "generation_id": "gen-1", "file_id": "file-gen-1"},
        "generations/2026-10-17/gen-1/1.mp4",
        "VIDEO",
        origin={"generation_id": "gen-1", "file_index": 1},
    )

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "fhd1080"))

    assert (final["quality"], final["kind"], final["parent_take_id"], final["preset_id"], final["mode"]) == (
        "final",
        "upscale",
        source["id"],
        presets.SEEDVR2,
        "video_upscale",
    )
    assert (final["seed"], final["variant"], final["resolution"], final["shot_id"]) == (source["seed"], "A", "1872x1080", "s1")
    assert final["generation_id"] == "gen-2"
    request = core.submitted[-1][1]
    assert request["form_data"]["input_video"] == "generations/2026-10-17/gen-1/1.mp4"
    assert request["form_data"]["input_video__origin"] == {"generation_id": "gen-1", "file_index": 1}
    assert (request["form_data"]["resolution_target"], request["form_data"]["seed"]) == ("fhd1080", -1)
    assert request["idempotency_key"] == f"vp:{final['id']}"
    assert core.recorded[-1][3] == f"video-producer:{final['id']}"


def test_a_final_by_upscale_of_an_h3_take_runs_the_h3_upscale_mode(core, make_project):
    core.use_h3()
    project, source = _done_take(core, make_project, preset_id=presets.MINIMAX_H3, direction={"mode": "Hybrid AV"})
    core.add_media({"kind": "history", "generation_id": "gen-1", "file_id": "file-gen-1"}, "generations/x/1.mp4", "VIDEO")

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "qhd1440"))

    request = core.submitted[-1][1]
    assert (final["preset_id"], final["mode"], final["profile"]) == (presets.MINIMAX_H3, "upscale", "Hybrid AV")
    assert request["form_data"]["target_size"] == "2k"
    assert "input_video__origin" not in request["form_data"]


def test_a_final_by_render_reuses_the_seed_at_the_largest_size(core, make_project):
    core.use_wan()
    project, source = _done_take(core, make_project)

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "render", "uhd2160"))

    request = core.submitted[-1][1]
    assert (final["kind"], final["quality"], final["resolution"], final["seed"]) == ("render", "final", "1280x720", source["seed"])
    assert request["form_data"]["seed"] == source["seed"] and request["form_data"]["resolution"] == "1280x720"


def test_a_final_needs_a_finished_take(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)

    with pytest.raises(TakeError) as caught:
        asyncio.run(generation.final(core.users["user-1"], project, take, "render", "fhd1080"))

    assert (caught.value.status_code, caught.value.code) == (409, "take_not_done")


def test_a_final_is_blocked_by_the_quota_missing_models_or_a_missing_upscaler(core, make_project):
    core.use_wan()
    project, source = _done_take(core, make_project)

    with pytest.raises(Blocked) as caught:
        asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "fhd1080"))
    assert [block["code"] for block in caught.value.blocks] == ["no_preset"]

    core.quota = {"limit": 10, "used": 10, "remaining": 0.0, "exempt": False, "resets_at": None}
    with pytest.raises(Blocked) as caught:
        asyncio.run(generation.final(core.users["user-1"], project, source, "render", "fhd1080"))
    assert [block["code"] for block in caught.value.blocks] == ["quota_exceeded"]

    core.quota = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}
    core.missing.add("vae-sha")
    with pytest.raises(Blocked) as caught:
        asyncio.run(generation.final(core.users["user-1"], project, source, "render", "fhd1080"))
    assert caught.value.blocks[0]["data"] == {"fields": ["vae"]}
    assert len(takes.list_takes(project["id"])) == 1


def test_a_retry_is_a_new_take_with_the_same_shot_seed_quality_and_preset(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1")
    _tick()
    failed = takes.get_take(take["id"])

    retried = asyncio.run(generation.retry(core.users["user-1"], project, failed))

    assert retried["id"] != failed["id"]
    assert (retried["shot_id"], retried["seed"], retried["quality"], retried["preset_id"], retried["kind"]) == (
        "s1",
        failed["seed"],
        "draft",
        presets.WAN,
        "render",
    )
    assert retried["generation_id"] == "gen-2" and core.submitted[-1][1]["form_data"]["seed"] == failed["seed"]
    assert takes.get_take(failed["id"])["status"] == "failed"


def test_a_retry_reserves_the_minutes_measured_on_the_backend_that_rendered_its_source(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.states["gen-1"] = {"id": "gen-1", "status": "running", "progress": 0.2, "backend_id": "b-studio"}
    _tick()
    core.fail("gen-1", backend_id="b-studio")
    _tick()
    for duration_ms in (60000, 60000, 60000):
        takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, duration_ms)
    takes.add_calibration(presets.WAN, "b-studio", "832x480", 4.0, 24000)
    failed = takes.get_take(take["id"])

    retried = asyncio.run(generation.retry(core.users["user-1"], project, failed))

    assert failed["backend_id"] == "b-studio"
    assert retried["units_reserved"] == round(4 * 6 / 60, 3)


def test_a_retry_of_a_take_no_backend_rendered_reserves_the_default_minutes(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1", backend_id=None)
    _tick()
    takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, 24000)
    failed = takes.get_take(take["id"])

    retried = asyncio.run(generation.retry(core.users["user-1"], project, failed))

    assert failed["backend_id"] is None
    assert retried["units_reserved"] == round(4 * 10 / 60, 3)


def test_a_final_reserves_the_minutes_measured_on_the_backend_of_its_source(core, make_project):
    core.use_wan()
    project, source = _done_take(core, make_project)
    takes.add_calibration(presets.WAN, "b-studio", "1280x720", 4.0, 400000)
    takes.add_calibration(presets.WAN, "b-local", "1280x720", 4.0, 120000)

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "render", "fhd1080"))

    assert source["backend_id"] == "b-local"
    assert final["units_reserved"] == round(4 * 30 / 60, 3)


def test_only_a_failed_or_cancelled_take_can_be_retried(core, make_project):
    core.use_wan()
    project, done = _done_take(core, make_project)

    with pytest.raises(TakeError) as caught:
        asyncio.run(generation.retry(core.users["user-1"], project, done))

    assert caught.value.code == "take_not_retryable"


def test_a_failed_upscale_is_retried_from_its_parent_with_the_same_target(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, source = _done_take(core, make_project)
    core.add_media({"kind": "history", "generation_id": "gen-1", "file_id": "file-gen-1"}, "generations/x/1.mp4", "VIDEO")
    upscale = asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "qhd1440"))
    core.fail(upscale["generation_id"])
    _tick()

    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(upscale["id"])))

    assert (retried["kind"], retried["parent_take_id"], retried["quality"]) == ("upscale", source["id"], "final")
    assert core.submitted[-1][1]["form_data"]["resolution_target"] == "qhd1440"


def test_deleting_an_in_flight_take_cancels_it_first(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)

    assert asyncio.run(generation.delete(core.users["user-1"], take)) is True

    assert takes.get_take(take["id"]) is None and takes.list_jobs(take["id"]) == []
    assert core.cancelled == [("user-1", "gen-1")]
    assert core.refunded == [f"video-producer:{take['id']}"]


def test_variant_letters_go_past_z():
    assert [generation.variant_letter(index) for index in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]


def test_seeds_are_drawn_below_two_to_the_thirty_one():
    assert all(0 <= generation.new_seed() < 2**31 for _ in range(50))


@pytest.mark.parametrize(
    "quota",
    [
        {"limit": 10, "used": None, "remaining": None, "exempt": True, "resets_at": None},
        {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None},
    ],
)
def test_an_unlimited_or_exempt_owner_reserves_nothing_for_a_final_or_a_retry(core, make_project, quota):
    core.use_wan()
    core.quota = quota
    project, source = _done_take(core, make_project)

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "render", "fhd1080"))
    core.fail(final["generation_id"])
    _tick()
    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(final["id"])))

    assert (final["units_reserved"], retried["units_reserved"]) == (0, 0)
    assert core.recorded == [] and core.refunded == []


def test_the_variant_letters_continue_after_the_takes_of_the_shot_at_that_quality(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS)

    first = _start(core, project, shots=["s1"], variants=2)
    second = _start(core, project, shots=["s1", "s2"], variants=2)
    final = _start(core, project, shots=["s1"], variants=1, quality="final")

    assert [take["variant"] for take in first] == ["A", "B"]
    assert [(take["shot_id"], take["variant"]) for take in second] == [("s1", "C"), ("s1", "D"), ("s2", "A"), ("s2", "B")]
    assert [take["variant"] for take in final] == ["A"]


def test_a_freed_letter_is_used_again_and_a_retry_keeps_its_source_letter(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    first, second = _start(core, project, shots=["s1"], variants=2)
    takes.delete_take(first["id"])
    core.fail(second["generation_id"])
    _tick()

    (again,) = _start(core, project, shots=["s1"], variants=1)
    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(second["id"])))

    assert again["variant"] == "A"
    assert retried["variant"] == "B"


def test_two_pumps_of_different_users_do_not_wait_for_each_other(core, make_project, store):
    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    mine = make_project(clips=SHOTS[:1])
    theirs = make_project(user_id="user-2", clips=SHOTS[:1])
    _start(core, mine, shots=["s1"], variants=2)
    _start(core, theirs, owner="user-2", shots=["s1"], variants=2)

    assert (takes.in_flight("user-1"), takes.in_flight("user-2")) == (1, 1)


GENERIC = "Something went wrong while generating."
RAW = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB. GPU 0 has a total capacity of 11.99 GiB of which 0 bytes is free."
DETAIL = RAW + "\n\nTraceback (most recent call last):\n  File \"/app/src/pipes/text_encoder.py\", line 88, in encode\n    out = model(x)\nRuntimeError: CUDA out of memory."


def _unclassified(core, generation_id, detail=DETAIL):
    core.fail(
        generation_id,
        code="unclassified",
        message=GENERIC + "\n- Try again\n- If it keeps happening, send the error ID to your administrator",
        error_message=GENERIC,
        error_detail=detail,
    )


def test_an_unclassified_failure_of_an_admin_keeps_the_raw_error_without_its_traceback(core, make_project):
    core.use_wan()
    project = make_project(user_id="admin-1", clips=SHOTS[:1])
    (take,) = _start(core, project, owner="admin-1", shots=["s1"], variants=1)
    _unclassified(core, "gen-1")

    generation_hooks.on_failed(
        HookContext(
            hook_name="generation.failed",
            plugin_id="system",
            data={"generation_id": "gen-1", "error_code": "unclassified", "message": GENERIC},
        )
    )

    failed = takes.get_take(take["id"])
    assert (failed["error_code"], failed["error_message"]) == ("unclassified", RAW)
    assert "Traceback" not in core.notified[-1]["message"] and RAW in core.notified[-1]["message"]


def test_the_tracker_gives_an_admin_the_same_raw_reason_cut_to_three_hundred_characters(core, make_project):
    core.use_wan()
    project = make_project(user_id="admin-1", clips=SHOTS[:1])
    (take,) = _start(core, project, owner="admin-1", shots=["s1"], variants=1)
    long_error = "ValueError: " + "x" * 400
    _unclassified(core, "gen-1", detail=long_error + "\n\nTraceback (most recent call last):\n  boom")

    _tick()

    failed = takes.get_take(take["id"])
    assert (failed["error_code"], failed["error_message"]) == ("unclassified", long_error[:300])


USER_REASON = GENERIC + "\n- Try again\n- If it keeps happening, send the error ID to your administrator\nError ID: gen-1"


def test_an_unclassified_failure_of_a_user_keeps_the_fullest_core_message_and_its_error_id(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    _unclassified(core, "gen-1")

    generation_hooks.on_failed(
        HookContext(
            hook_name="generation.failed",
            plugin_id="system",
            data={"generation_id": "gen-1", "error_code": "unclassified", "message": GENERIC},
        )
    )

    failed = takes.get_take(take["id"])
    assert (failed["error_code"], failed["error_message"]) == ("unclassified", USER_REASON)
    assert "CUDA" not in core.notified[-1]["message"] and core.notified[-1]["message"].endswith(USER_REASON)


def test_the_tracker_gives_a_user_the_same_reason_without_the_raw_error(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    _unclassified(core, "gen-1")

    _tick()

    assert takes.get_take(take["id"])["error_message"] == USER_REASON


def test_an_unclassified_failure_of_an_admin_without_raw_error_keeps_the_fullest_core_message(core, make_project):
    core.use_wan()
    project = make_project(user_id="admin-1", clips=SHOTS[:1])
    (take,) = _start(core, project, owner="admin-1", shots=["s1"], variants=1)
    _unclassified(core, "gen-1", detail=None)

    _tick()

    assert takes.get_take(take["id"])["error_message"] == USER_REASON.rsplit("\nError ID", 1)[0]


def test_a_classified_failure_keeps_the_hook_message_first(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:1])
    (take,) = _start(core, project, shots=["s1"], variants=1)
    core.fail("gen-1", code="cuda_oom", message="Ran out of GPU memory (VRAM) during generation.\n- Lower the resolution", error_detail=DETAIL)

    generation_hooks.on_failed(
        HookContext(
            hook_name="generation.failed",
            plugin_id="system",
            data={"generation_id": "gen-1", "error_code": "cuda_oom", "message": "Ran out of GPU memory (VRAM) during generation."},
        )
    )

    failed = takes.get_take(take["id"])
    assert (failed["error_code"], failed["error_message"]) == ("cuda_oom", "Ran out of GPU memory (VRAM) during generation.")
