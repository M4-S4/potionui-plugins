import asyncio
import threading

import pytest

from backend import core_bridge, generation, presets, takes, tracker
from hooks import generation_hooks
from src.plugin_api import HookContext, get_current_active_user

BASE = "/api/plugins/video-producer"
GPU = "video-producer.gpu_minutes"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 6, "firstFromPrevious": False}]
ORDER = {"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.WAN}
FRAME_ASSET = {"id": "b", "kind": "image", "name": "b", "origin": {"kind": "history", "generationId": "g-b", "fileId": "2"}}


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _ref(take):
    return f"video-producer:{take['id']}"


def _generate(client, project_id, status=202, **order):
    response = client.post(f"{BASE}/projects/{project_id}/generate", json={**ORDER, **order})
    assert response.status_code == status, response.text
    return response.json()["data"]["takes"] if status == 202 else response.json()["detail"]


def _estimate(client, project_id, **order):
    response = client.post(f"{BASE}/projects/{project_id}/estimate", json={**ORDER, **order})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _finish(core, take, **fields):
    core.complete(take["generation_id"], **fields)
    _tick()
    return takes.get_take(take["id"])


def _after_complete(generation_id, status="completed", **data):
    return HookContext(
        hook_name="generation.after_complete",
        plugin_id="system",
        data={"generation_id": generation_id, "status": status, "duration": 61.0, **data},
    )


def _failed(generation_id, error_code="missing_model_file", message="A model file is missing."):
    return HookContext(
        hook_name="generation.failed",
        plugin_id="system",
        data={"generation_id": generation_id, "error_code": error_code, "message": message},
    )


def _upscale_source(core, take):
    core.add_media(
        {"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"},
        f"generations/2026-10-17/{take['generation_id']}/1.mp4",
        "VIDEO",
    )


@pytest.fixture
def project(core, make_project):
    core.use_wan()
    return make_project(clips=SHOTS)


@pytest.mark.parametrize(
    "failure, code",
    [
        (RuntimeError("no backend"), "no_backend"),
        (PermissionError("denied"), "preset_not_available"),
        (ValueError("resolution: invalid"), "invalid_request"),
        (core_bridge.IdempotencyKeyConflict("vp:x"), "duplicate_submission"),
        (KeyError("boom"), "submit_failed"),
        (OSError("disk full"), "submit_failed"),
        (asyncio.TimeoutError(), "submit_failed"),
    ],
)
def test_a_submit_that_raises_after_the_reservation_refunds_it_and_fails_the_take_with_a_code(client, core, project, failure, code):
    core.refusal = failure

    (take,) = _generate(client, project["id"])

    assert (take["status"], take["error_code"], take["generation_id"]) == ("failed", code, None)
    assert take["error_message"] and take["finished_at"]
    assert core.recorded == [("user-1", GPU, round(4 * 10 / 60, 3), _ref(take))]
    assert core.refunded == [_ref(take)]
    assert [note["notification_type"] for note in core.notified] == ["video-producer.take_failed"]
    assert takes.in_flight("user-1") == 0 and takes.list_jobs(take["id"]) == []
    _tick()
    assert core.refunded == [_ref(take)] and len(core.notified) == 1


def test_a_refused_submit_does_not_take_the_slot_of_the_takes_behind_it(client, core, project, store, monkeypatch):
    store[("max_parallel_jobs", None)] = "1"
    original = core.submit_generation
    calls = []

    async def first_refused(user, request):
        calls.append(request["idempotency_key"])
        if len(calls) == 1:
            raise RuntimeError("No backend")
        return await original(user, request)

    monkeypatch.setattr(core_bridge, "submit_generation", first_refused)

    refused, accepted = _generate(client, project["id"], variants=2)

    assert (refused["status"], refused["error_code"]) == ("failed", "no_backend")
    assert (accepted["status"], accepted["generation_id"]) == ("queued", "gen-1")
    assert takes.in_flight("user-1") == 1


def test_a_reservation_the_core_could_not_record_refuses_the_request_and_stores_no_take(client, core, project, monkeypatch):
    monkeypatch.setattr(core_bridge, "record_limit_event", lambda *args: False)

    detail = _generate(client, project["id"], status=409)

    assert [block["code"] for block in detail["data"]["blocks"]] == ["quota_unrecorded"]
    assert takes.list_takes(project["id"]) == []
    assert core.refunded == [] and core.submitted == []


@pytest.mark.parametrize(
    "sequence",
    [
        ("hook", "tracker"),
        ("tracker", "hook"),
        ("hook", "hook", "tracker", "tracker"),
        ("tracker", "hook", "tracker", "hook"),
    ],
)
def test_after_complete_and_the_tracker_in_any_order_finish_a_take_once(core, project, client, sequence):
    (take,) = _generate(client, project["id"])
    core.complete(take["generation_id"], duration_ms=90000)

    for step in sequence:
        if step == "hook":
            generation_hooks.on_after_complete(_after_complete(take["generation_id"], duration=95.0))
        else:
            _tick()

    done = takes.get_take(take["id"])
    assert (done["status"], done["progress"]) == ("done", 100.0)
    assert takes.calibration(presets.WAN, "b-local", "832x480") == [(4.0, 90000)]
    assert len(core.notified) == 1 and core.notified[0]["notification_type"] == "video-producer.take_done"
    assert [record[3] for record in core.recorded if record[3].endswith(":adjust")] == [f"{_ref(take)}:adjust"]
    assert core.refunded == []
    jobs = takes.list_jobs(take["id"])
    assert len(jobs) == 1 and jobs[0]["finished_at"]


def test_the_hook_duration_stands_in_when_the_state_has_none_and_is_counted_once(core, project, client):
    (take,) = _generate(client, project["id"])
    core.complete(take["generation_id"])
    del core.states[take["generation_id"]]["duration_ms"]

    generation_hooks.on_after_complete(_after_complete(take["generation_id"], duration=75.0))
    _tick()

    assert takes.calibration(presets.WAN, "b-local", "832x480") == [(4.0, 75000)]
    assert len(core.notified) == 1


def test_racing_hooks_and_tracker_rounds_finish_a_take_exactly_once(core, project, client):
    (take,) = _generate(client, project["id"])
    core.complete(take["generation_id"], duration_ms=90000)
    barrier = threading.Barrier(6)
    errors = []

    def hook():
        barrier.wait()
        try:
            generation_hooks.on_after_complete(_after_complete(take["generation_id"]))
        except Exception as exc:
            errors.append(exc)

    def round_():
        barrier.wait()
        try:
            _tick()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=target) for target in (hook, round_, hook, round_, hook, round_)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert takes.get_take(take["id"])["status"] == "done"
    assert len(takes.calibration(presets.WAN, "b-local", "832x480")) == 1
    assert len(core.notified) == 1
    assert len([record for record in core.recorded if record[3].endswith(":adjust")]) == 1


@pytest.mark.parametrize("order", ["failed first", "after_complete first", "tracker first"])
def test_failed_and_after_complete_failed_end_a_take_once_with_the_first_reason(core, project, client, order):
    (take,) = _generate(client, project["id"])
    core.fail(take["generation_id"], code="cuda_oom", message="The GPU ran out of memory.")
    failed = _failed(take["generation_id"])
    completed = _after_complete(take["generation_id"], status="failed")

    if order == "failed first":
        generation_hooks.on_failed(failed)
        generation_hooks.on_after_complete(completed)
        _tick()
        expected = ("missing_model_file", "A model file is missing.")
    elif order == "after_complete first":
        generation_hooks.on_after_complete(completed)
        generation_hooks.on_failed(failed)
        _tick()
        expected = ("cuda_oom", "The GPU ran out of memory.")
    else:
        _tick()
        generation_hooks.on_failed(failed)
        generation_hooks.on_after_complete(completed)
        expected = ("cuda_oom", "The GPU ran out of memory.")

    current = takes.get_take(take["id"])
    assert (current["status"], current["error_code"], current["error_message"]) == ("failed", *expected)
    assert core.refunded == [_ref(take)]
    assert [note["notification_type"] for note in core.notified] == ["video-producer.take_failed"]
    assert takes.calibration(presets.WAN, "b-local", "832x480") == []


def test_a_hook_for_a_take_already_deleted_or_finished_changes_nothing(core, project, client):
    first, second = _generate(client, project["id"], variants=2)
    client.delete(f"{BASE}/projects/{project['id']}/takes/{first['id']}")
    core.complete(first["generation_id"])
    core.complete(second["generation_id"])
    _tick()
    notified = len(core.notified)
    recorded = len(core.recorded)

    generation_hooks.on_after_complete(_after_complete(first["generation_id"]))
    generation_hooks.on_failed(_failed(second["generation_id"]))
    generation_hooks.on_after_complete(_after_complete(second["generation_id"], status="cancelled"))

    assert takes.get_take(first["id"]) is None
    assert takes.get_take(second["id"])["status"] == "done"
    assert (len(core.notified), len(core.recorded)) == (notified, recorded)


def test_a_generation_state_that_cannot_be_read_leaves_the_take_and_its_reservation_alone(core, project, client, monkeypatch):
    (take,) = _generate(client, project["id"])

    def unreadable(user, generation_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(core_bridge, "generation_state", unreadable)

    assert _tick() is True
    assert takes.get_take(take["id"])["status"] == "queued"
    assert core.refunded == [] and core.notified == []


def test_three_takes_with_one_slot_submit_one_and_queue_two_without_generation(client, core, project, store):
    store[("max_parallel_jobs", None)] = "1"

    first, second, third = _generate(client, project["id"], variants=3)

    assert [(take["variant"], take["status"], take["generation_id"]) for take in (first, second, third)] == [
        ("A", "queued", "gen-1"),
        ("B", "queued", None),
        ("C", "queued", None),
    ]
    assert len(core.submitted) == 1 and takes.in_flight("user-1") == 1
    queue = client.get(f"{BASE}/projects/{project['id']}/queue").json()["data"]
    assert [take["variant"] for take in queue["takes"]] == ["A", "B", "C"]
    assert queue["slots"] == {"in_flight": 1, "max": 1}
    assert [record[3] for record in core.recorded] == [_ref(take) for take in (first, second, third)]
    assert _tick() is True
    assert len(core.submitted) == 1

    core.complete("gen-1")
    _tick()

    assert [takes.get_take(take["id"])["status"] for take in (first, second, third)] == ["done", "queued", "queued"]
    assert [takes.get_take(take["id"])["generation_id"] for take in (second, third)] == ["gen-2", None]
    assert client.get(f"{BASE}/projects/{project['id']}/queue").json()["data"]["slots"] == {"in_flight": 1, "max": 1}

    core.fail("gen-2")
    _tick()

    assert takes.get_take(second["id"])["status"] == "failed"
    assert takes.get_take(third["id"])["generation_id"] == "gen-3"
    assert [request["idempotency_key"] for _, request in core.submitted] == [f"vp:{take['id']}" for take in (first, second, third)]


def test_a_slot_freed_by_a_cancel_goes_to_the_next_queued_take(client, core, project, store):
    store[("max_parallel_jobs", None)] = "1"
    first, second, third = _generate(client, project["id"], variants=3)

    client.post(f"{BASE}/takes/{first['id']}/cancel")
    _tick()

    assert takes.get_take(first["id"])["status"] == "cancelled"
    assert takes.get_take(second["id"])["generation_id"] == "gen-2"
    assert takes.get_take(third["id"])["generation_id"] is None
    assert core.cancelled == [("user-1", "gen-1")]


def test_the_parallel_limit_of_each_user_is_its_own(app, client, core, make_project, store):
    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    mine = make_project(clips=SHOTS)
    theirs = make_project(user_id="user-2", clips=SHOTS)

    _generate(client, mine["id"], variants=2)
    _as(app, core.users["user-2"])
    other, _ = _generate(client, theirs["id"], variants=2)

    assert [user_id for user_id, _ in core.submitted] == ["user-1", "user-2"]
    assert other["generation_id"] == "gen-2"
    assert takes.in_flight("user-1") == 1 and takes.in_flight("user-2") == 1


def test_two_pumps_running_at_once_never_exceed_max_parallel_jobs(client, core, project, store, monkeypatch):
    store[("max_parallel_jobs", None)] = "1"
    first, second, third = _generate(client, project["id"], variants=3)
    client.post(f"{BASE}/takes/{first['id']}/cancel")
    original = core.submit_generation

    async def slow(user, request):
        await asyncio.sleep(0)
        return await original(user, request)

    monkeypatch.setattr(core_bridge, "submit_generation", slow)

    async def both():
        user = core.users["user-1"]
        return await asyncio.gather(generation.pump(user), generation.pump(user))

    asyncio.run(both())

    assert takes.in_flight("user-1") == 1
    assert len(core.submitted) == 2
    assert sum(1 for take in (second, third) if takes.get_take(take["id"])["generation_id"]) == 1


def test_cancelling_a_queued_take_never_submitted_calls_nothing_in_the_core_and_refunds(client, core, project, store):
    store[("max_parallel_jobs", None)] = "1"
    _, waiting = _generate(client, project["id"], variants=2)
    assert waiting["generation_id"] is None

    response = client.post(f"{BASE}/takes/{waiting['id']}/cancel")

    assert response.status_code == 200
    cancelled = response.json()["data"]["take"]
    assert (cancelled["status"], cancelled["generation_id"], cancelled["finished_at"] is not None) == ("cancelled", None, True)
    assert core.cancelled == []
    assert core.refunded == [_ref(waiting)]
    assert client.post(f"{BASE}/takes/{waiting['id']}/cancel").json()["data"]["take"]["status"] == "cancelled"
    assert core.refunded == [_ref(waiting)]
    core.complete("gen-1")
    _tick()
    assert len(core.submitted) == 1 and takes.get_take(waiting["id"])["generation_id"] is None


def test_cancelling_twice_or_after_the_end_refunds_once(client, core, project):
    done, running = _generate(client, project["id"], variants=2)
    core.complete(done["generation_id"])
    _tick()

    client.post(f"{BASE}/takes/{done['id']}/cancel")
    client.post(f"{BASE}/takes/{running['id']}/cancel")
    client.post(f"{BASE}/takes/{running['id']}/cancel")

    assert takes.get_take(done["id"])["status"] == "done"
    assert core.cancelled == [("user-1", running["generation_id"])]
    assert core.refunded == [_ref(running)]


def test_a_core_that_cannot_cancel_still_ends_the_take_and_refunds_it(client, core, project, monkeypatch):
    (take,) = _generate(client, project["id"])

    async def refuses(user, generation_id):
        raise RuntimeError("backend unreachable")

    monkeypatch.setattr(core_bridge, "cancel_generation", refuses)

    response = client.post(f"{BASE}/takes/{take['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["data"]["take"]["status"] == "cancelled"
    assert core.refunded == [_ref(take)]


@pytest.mark.parametrize("state", ["queued", "running", "failed", "cancelled"])
def test_a_final_of_a_take_that_is_not_done_answers_409_and_starts_nothing(client, core, project, state):
    (take,) = _generate(client, project["id"])
    if state == "running":
        core.states[take["generation_id"]] = {"status": "running", "progress": 0.3, "backend_id": "b-local"}
        _tick()
    elif state == "failed":
        core.fail(take["generation_id"])
        _tick()
    elif state == "cancelled":
        client.post(f"{BASE}/takes/{take['id']}/cancel")
    submitted = len(core.submitted)
    recorded = len(core.recorded)

    for method in ("render", "upscale"):
        response = client.post(
            f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": method, "target": "fhd1080"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "take_not_done"

    assert len(takes.list_takes(project["id"])) == 1
    assert (len(core.submitted), len(core.recorded)) == (submitted, recorded)


def test_a_final_by_upscale_is_blocked_until_seedvr2_is_assigned_and_its_source_exists(client, core, project):
    (take,) = _generate(client, project["id"])
    done = _finish(core, take)
    recorded = len(core.recorded)
    path = f"{BASE}/projects/{project['id']}/takes/{done['id']}/final"
    body = {"method": "upscale", "target": "fhd1080"}

    absent = client.post(path, json=body)
    assert absent.status_code == 409
    assert absent.json()["detail"]["error"] == "blocked"
    assert [block["code"] for block in absent.json()["detail"]["data"]["blocks"]] == ["no_preset"]

    core.use_seedvr2()
    unreachable = client.post(path, json=body)
    assert unreachable.status_code == 409
    assert [block["code"] for block in unreachable.json()["detail"]["data"]["blocks"]] == ["source_unavailable"]

    assert len(takes.list_takes(project["id"])) == 1 and len(core.submitted) == 1 and len(core.recorded) == recorded

    _upscale_source(core, done)
    allowed = client.post(path, json=body)
    assert allowed.status_code == 202
    assert allowed.json()["data"]["take"]["preset_id"] == presets.SEEDVR2


def test_a_final_by_render_does_not_need_the_upscaler(client, core, project):
    (take,) = _generate(client, project["id"])
    done = _finish(core, take)

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{done['id']}/final", json={"method": "render", "target": "fhd1080"})

    assert response.status_code == 202
    final = response.json()["data"]["take"]
    assert (final["kind"], final["quality"], final["parent_take_id"], final["seed"]) == ("render", "final", done["id"], done["seed"])


def test_a_final_the_quota_cannot_pay_is_blocked_and_reserves_nothing(client, core, project):
    (take,) = _generate(client, project["id"])
    done = _finish(core, take)
    core.quota = {"limit": 5, "used": 5, "remaining": 0.0, "exempt": False, "resets_at": None}
    recorded = len(core.recorded)

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{done['id']}/final", json={"method": "render", "target": "fhd1080"})

    assert response.status_code == 409
    assert [block["code"] for block in response.json()["detail"]["data"]["blocks"]] == ["quota_exceeded"]
    assert len(takes.list_takes(project["id"])) == 1 and len(core.recorded) == recorded


def test_a_retry_reuses_the_seed_through_failures_and_cancellations(client, core, project):
    (first,) = _generate(client, project["id"])
    core.fail(first["generation_id"])
    _tick()
    second = client.post(f"{BASE}/takes/{first['id']}/retry").json()["data"]["take"]
    client.post(f"{BASE}/takes/{second['id']}/cancel")
    third = client.post(f"{BASE}/takes/{second['id']}/retry").json()["data"]["take"]

    assert len({first["seed"], second["seed"], third["seed"]}) == 1
    assert len({first["id"], second["id"], third["id"]}) == 3
    keys = [request["idempotency_key"] for _, request in core.submitted]
    assert keys == [f"vp:{first['id']}", f"vp:{second['id']}", f"vp:{third['id']}"]
    assert all(request["form_data"]["seed"] == first["seed"] for _, request in core.submitted)
    assert [take["status"] for take in takes.list_takes(project["id"])] == ["failed", "cancelled", "queued"]
    assert core.refunded == [_ref(first), _ref(second)]


def test_a_retry_of_a_take_cancelled_before_its_submission_goes_out_with_the_same_seed(client, core, project, store):
    store[("max_parallel_jobs", None)] = "1"
    _, waiting = _generate(client, project["id"], variants=2)
    client.post(f"{BASE}/takes/{waiting['id']}/cancel")
    core.complete("gen-1")
    _tick()

    retried = client.post(f"{BASE}/takes/{waiting['id']}/retry").json()["data"]["take"]

    assert retried["seed"] == waiting["seed"] and retried["generation_id"] == "gen-2"
    assert core.submitted[-1][1]["form_data"]["seed"] == waiting["seed"]


def test_a_retry_the_quota_cannot_pay_answers_409_and_creates_no_take(client, core, project):
    (take,) = _generate(client, project["id"])
    core.fail(take["generation_id"])
    _tick()
    core.quota = {"limit": 5, "used": 5, "remaining": 0.0, "exempt": False, "resets_at": None}

    response = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert response.status_code == 409
    assert [block["code"] for block in response.json()["detail"]["data"]["blocks"]] == ["quota_exceeded"]
    assert len(takes.list_takes(project["id"])) == 1


def _own_takes(client, core, project, store):
    store[("max_parallel_jobs", None)] = "3"
    done, failed, active = _generate(client, project["id"], variants=3)
    core.complete(done["generation_id"])
    core.fail(failed["generation_id"])
    _tick()
    return done, failed, active


ACTIONS = {
    "list": lambda client, project, done, failed, active: client.get(f"{BASE}/projects/{project['id']}/takes"),
    "queue": lambda client, project, done, failed, active: client.get(f"{BASE}/projects/{project['id']}/queue"),
    "choose": lambda client, project, done, failed, active: client.post(
        f"{BASE}/projects/{project['id']}/takes/{done['id']}/choose", json={"chosen": True}
    ),
    "flag": lambda client, project, done, failed, active: client.post(
        f"{BASE}/projects/{project['id']}/takes/{done['id']}/flag", json={"flag": "keep"}
    ),
    "final": lambda client, project, done, failed, active: client.post(
        f"{BASE}/projects/{project['id']}/takes/{done['id']}/final", json={"method": "render", "target": "fhd1080"}
    ),
    "cancel": lambda client, project, done, failed, active: client.post(f"{BASE}/takes/{active['id']}/cancel"),
    "retry": lambda client, project, done, failed, active: client.post(f"{BASE}/takes/{failed['id']}/retry"),
    "delete": lambda client, project, done, failed, active: client.delete(f"{BASE}/projects/{project['id']}/takes/{done['id']}"),
    "estimate": lambda client, project, done, failed, active: client.post(f"{BASE}/projects/{project['id']}/estimate", json=ORDER),
    "generate": lambda client, project, done, failed, active: client.post(f"{BASE}/projects/{project['id']}/generate", json=ORDER),
}


@pytest.mark.parametrize("action", list(ACTIONS))
def test_another_users_takes_answer_404_and_stay_untouched(app, client, core, project, store, action):
    done, failed, active = _own_takes(client, core, project, store)
    before = [dict(take) for take in takes.list_takes(project["id"])]
    submitted, cancelled, recorded = len(core.submitted), len(core.cancelled), len(core.recorded)
    _as(app, core.users["user-2"])

    response = ACTIONS[action](client, project, done, failed, active)

    assert response.status_code == 404
    assert response.json()["detail"]["error"] in ("project_not_found", "take_not_found")
    assert takes.list_takes(project["id"]) == before
    assert (len(core.submitted), len(core.cancelled), len(core.recorded)) == (submitted, cancelled, recorded)


@pytest.mark.parametrize("action", list(ACTIONS))
def test_an_admin_reaches_the_takes_of_a_user_and_the_core_sees_the_owner(app, client, core, project, store, action):
    done, failed, active = _own_takes(client, core, project, store)
    _as(app, core.users["admin-1"])

    response = ACTIONS[action](client, project, done, failed, active)

    assert response.status_code in (200, 202)
    assert {user_id for user_id, _ in core.submitted} == {"user-1"}
    assert {user_id for user_id, _ in core.cancelled} <= {"user-1"}
    assert {record[0] for record in core.recorded} == {"user-1"}
    assert {user_id for user_id, _ in core.previewed} <= {"user-1"}


def test_an_unknown_take_or_project_is_not_found_whoever_asks(app, client, core, project):
    for caller in ("user-1", "admin-1"):
        _as(app, core.users[caller])
        assert client.post(f"{BASE}/takes/nope/cancel").status_code == 404
        assert client.post(f"{BASE}/takes/nope/retry").status_code == 404
        assert client.get(f"{BASE}/projects/nope/takes").status_code == 404
        assert client.get(f"{BASE}/projects/{project['id']}/takes/nope").status_code in (404, 405)
        assert client.delete(f"{BASE}/projects/{project['id']}/takes/nope").status_code == 404
        assert client.post(f"{BASE}/projects/{project['id']}/takes/nope/flag", json={"flag": "keep"}).status_code == 404


@pytest.mark.parametrize("quota", [
    {"limit": 10, "used": None, "remaining": None, "exempt": True, "resets_at": None},
    {"limit": 1, "used": None, "remaining": None, "exempt": True, "resets_at": None},
])
def test_an_exempt_user_is_never_blocked_and_reserves_no_minutes(app, client, core, project, quota):
    core.quota = quota
    _as(app, core.users["admin-1"])

    estimated = _estimate(client, project["id"], variants=16)
    (take, *_) = _generate(client, project["id"], variants=16)

    assert estimated["quota"]["exempt"] is True and estimated["quota"]["blocks"] is False
    assert estimated["blocks"] == []
    assert core.recorded == []
    assert take["units_reserved"] == 0


def test_an_exempt_take_that_finishes_or_fails_neither_adjusts_nor_refunds(client, core, project):
    core.quota = {"limit": 10, "used": None, "remaining": None, "exempt": True, "resets_at": None}
    done, failed = _generate(client, project["id"], variants=2)
    core.complete(done["generation_id"], duration_ms=600000)
    core.fail(failed["generation_id"])

    _tick()

    assert takes.get_take(done["id"])["status"] == "done" and takes.get_take(failed["id"])["status"] == "failed"
    assert core.recorded == [] and core.refunded == []


def test_a_user_without_a_limit_is_not_blocked_and_reserves_no_minutes(client, core, project):
    core.quota = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}
    estimated = _estimate(client, project["id"], variants=16)

    assert estimated["quota"]["limit"] is None and estimated["quota"]["blocks"] is False
    assert estimated["quota"]["applies"] is True
    created = _generate(client, project["id"], variants=16)
    assert len(created) == 16
    assert core.recorded == [] and all(take["units_reserved"] == 0 for take in created)


def test_a_cloud_preset_reserves_no_minutes_and_ignores_an_exhausted_quota(client, core, make_project):
    core.use_openrouter()
    project = make_project(clips=SHOTS)
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}
    order = {"preset_id": presets.OPENROUTER_VIDEO, "model_id": "cm-veo", "shots": ["s1", "s2"]}

    estimated = _estimate(client, project["id"], **order)
    done, failed = _generate(client, project["id"], **order)

    assert estimated["quota"]["applies"] is False and estimated["quota"]["needed_minutes"] == 0
    assert estimated["quota"]["blocks"] is False and estimated["blocks"] == []
    assert estimated["vram"]["estimate_gb"] is None and core.previewed == []
    assert core.recorded == []
    assert (done["units_reserved"], failed["units_reserved"]) == (0, 0)
    core.complete(done["generation_id"], duration_ms=600000)
    core.fail(failed["generation_id"])
    _tick()
    assert core.recorded == [] and core.refunded == []
    client.post(f"{BASE}/takes/{done['id']}/cancel")
    assert core.refunded == []


def test_a_cancelled_cloud_take_refunds_nothing(client, core, make_project):
    core.use_openrouter()
    project = make_project(clips=SHOTS)

    (take,) = _generate(client, project["id"], preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")
    client.post(f"{BASE}/takes/{take['id']}/cancel")

    assert takes.get_take(take["id"])["status"] == "cancelled"
    assert core.recorded == [] and core.refunded == []


@pytest.mark.parametrize(
    "failure", [RuntimeError("no backend"), TimeoutError("slow"), KeyError("device"), ValueError("bad request"), OSError("pipe")]
)
def test_an_estimate_whose_memory_preview_raises_reports_unknown_and_never_blocks(client, core, project, failure):
    core.memory = failure

    estimated = _estimate(client, project["id"])

    assert estimated["vram"] == {
        "estimate_gb": None,
        "free_gb": None,
        "total_gb": None,
        "budget_gb": None,
        "streams": False,
        "unknown": True,
        "backend_id": None,
    }
    assert [warning["code"] for warning in estimated["warnings"] if warning["code"] == "vram_unknown"] == ["vram_unknown"]
    assert estimated["blocks"] == []
    assert len(core.previewed) == 1


def test_a_generation_goes_ahead_when_the_memory_preview_fails(client, core, project):
    core.memory = RuntimeError("no backend")

    (take,) = _generate(client, project["id"])

    assert take["status"] == "queued" and take["generation_id"] == "gen-1"


@pytest.mark.parametrize("memory", [{}, {"estimate": None}, {"estimate": {}, "device": None}, {"estimate": {"checkpoint_estimate_gb": "big"}}])
def test_a_memory_preview_without_a_usable_estimate_is_unknown_with_a_warning(client, core, project, memory):
    core.memory = memory

    estimated = _estimate(client, project["id"])

    assert estimated["vram"]["unknown"] is True and estimated["vram"]["estimate_gb"] is None
    assert "vram_unknown" in [warning["code"] for warning in estimated["warnings"]]
    assert estimated["blocks"] == []


def test_a_model_larger_than_the_free_memory_warns_and_still_starts(client, core, project):
    core.memory = {**core.memory, "estimate": {"checkpoint_estimate_gb": 40.0}, "device": {"free_gb": 12.0, "total_gb": 24.0}}

    estimated = _estimate(client, project["id"])
    (take,) = _generate(client, project["id"])

    assert (estimated["vram"]["streams"], estimated["vram"]["unknown"]) == (True, False)
    assert "vram_stream" in [warning["code"] for warning in estimated["warnings"]] and estimated["blocks"] == []
    assert take["status"] == "queued"


def _last_frame_project(core, make_project, **parts):
    core.add_media({"kind": "history", "generation_id": "g-b", "file_id": "2"}, "generations/2026-10-17/g-b/2.png", "IMAGE")
    frames = [{"id": "f2", "shotId": "s1", "time": 3.9, "assetId": "b", "role": "last"}]
    return make_project(clips=SHOTS, frames=frames, assets=[FRAME_ASSET], **parts)


def test_a_fl2va_document_with_a_last_frame_alone_runs_text_to_video_and_says_so(client, core, make_project):
    core.use_wan()
    project = _last_frame_project(core, make_project)

    estimated = _estimate(client, project["id"])
    (take,) = _generate(client, project["id"])

    assert estimated["shots"][0]["director_mode"] == "t2v"
    assert [(warning["code"], warning["data"]) for warning in estimated["warnings"] if warning["code"] == "fl2va_no_frame"] == [
        ("fl2va_no_frame", {"shot_id": "s1"})
    ]
    assert estimated["blocks"] == []
    assert take["director_mode"] == "t2v" and take["status"] == "queued"
    document = takes.get_take(take["id"])["request"]["form_data"]["video_director"]
    assert (document["mode"], document["media"]) == ("t2v", [])
    assert "t2v_high_noise_model" in takes.get_take(take["id"])["request"]["form_data"]


def test_a_first_and_last_frame_make_no_warning_but_a_last_alone_on_one_shot_does_not_hide_the_others(client, core, make_project):
    core.use_wan()
    project = _last_frame_project(core, make_project)

    estimated = _estimate(client, project["id"], shots=["s1", "s2"])

    assert [(shot["shot_id"], shot["director_mode"]) for shot in estimated["shots"]] == [("s1", "t2v"), ("s2", "t2v")]
    assert sorted(warning["data"]["shot_id"] for warning in estimated["warnings"] if warning["code"] == "fl2va_no_frame") == ["s1", "s2"]


def test_a_shot_longer_than_max_duration_is_clamped_with_a_warning_and_the_take_keeps_the_clamp(client, core, make_project):
    core.use_wan()
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 75}, {"id": "s2", "start": 75, "dur": 6}])

    estimated = _estimate(client, project["id"], shots=["s1", "s2"])
    first, second = _generate(client, project["id"], shots=["s1", "s2"])

    assert [(shot["shot_id"], shot["seconds"]) for shot in estimated["shots"]] == [("s1", 60.0), ("s2", 6.0)]
    clamped = [warning for warning in estimated["warnings"] if warning["code"] == "duration_clamped"]
    assert [warning["data"] for warning in clamped] == [{"shot_id": "s1", "max": 60}]
    assert (first["duration_s"], second["duration_s"]) == (60.0, 6.0)
    request = takes.get_take(first["id"])["request"]
    assert request["form_data"]["video_director"]["settings"]["duration"] == 60.0
    assert estimated["quota"]["needed_minutes"] == round((60 + 6) * 10 / 60, 2)


def test_the_clamp_of_the_h3_preset_is_its_own_maximum(client, core, make_project):
    core.use_h3()
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 40}], direction={"mode": "Hybrid AV"})

    estimated = _estimate(client, project["id"], preset_id=presets.MINIMAX_H3)

    assert estimated["shots"][0]["seconds"] == 15.0
    assert [warning["data"] for warning in estimated["warnings"] if warning["code"] == "duration_clamped"] == [
        {"shot_id": "s1", "max": 15}
    ]


def test_a_shot_lengthened_past_its_take_is_generated_again_at_its_new_duration(client, core, make_project):
    core.use_h3()
    released = {"id": "s1", "start": 0, "dur": 8, "assetId": None, "take": None, "srcIn": 0, "stage": "todo"}
    assets = [{"id": "gen-t1", "kind": "video", "name": "Take", "generated": True, "srcDur": 4.375}]
    project = make_project(clips=[released], assets=assets, direction={"mode": "Hybrid AV"})

    estimated = _estimate(client, project["id"], preset_id=presets.MINIMAX_H3)

    assert estimated["shots"][0]["seconds"] == 8.0
    assert not [warning for warning in estimated["warnings"] if warning["code"] == "duration_clamped"]

    core.use_wan()
    wan = make_project(clips=[released], assets=assets)
    (take,) = _generate(client, wan["id"], shots=["s1"])
    assert take["duration_s"] == 8.0
    assert takes.get_take(take["id"])["request"]["form_data"]["video_director"]["settings"]["duration"] == 8.0


def _no_shots(core):
    return {"shots": []}, "no_shots"


def _unknown_shot(core):
    return {"shots": ["nope"]}, "no_shots"


def _no_preset(core):
    return {"preset_id": "01NOSUCHPRESET0000000000"}, "no_preset"


def _missing_models(core):
    core.missing.add("vae-sha")
    return {}, "missing_models"


def _exhausted_quota(core):
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}
    return {}, "quota_exceeded"


def _cloud_without_model(core):
    core.use_openrouter()
    return {"preset_id": presets.OPENROUTER_VIDEO, "model_id": None}, "no_model"


def _cloud_with_unknown_model(core):
    core.use_openrouter()
    return {"preset_id": presets.OPENROUTER_VIDEO, "model_id": "cm-gone"}, "no_model"


@pytest.mark.parametrize(
    "prepare",
    [_no_shots, _unknown_shot, _no_preset, _missing_models, _exhausted_quota, _cloud_without_model, _cloud_with_unknown_model],
)
def test_a_generate_the_estimate_blocks_answers_409_blocked_and_creates_no_take(client, core, project, prepare):
    order, code = prepare(core)

    estimated = _estimate(client, project["id"], **order)
    detail = _generate(client, project["id"], status=409, **order)

    assert [block["code"] for block in estimated["blocks"]] == [code]
    assert detail["error"] == "blocked" and detail["success"] is False
    assert [block["code"] for block in detail["data"]["blocks"]] == [code]
    assert takes.list_takes(project["id"]) == []
    assert core.submitted == [] and core.recorded == [] and core.refunded == [] and core.scheduled == []


def test_a_profile_the_preset_does_not_know_blocks_the_generation(client, core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS, direction={"mode": "Ref2VA"})

    estimated = _estimate(client, project["id"])
    detail = _generate(client, project["id"], status=409)

    assert [block["code"] for block in estimated["blocks"]] == ["profile_unsupported"]
    assert detail["error"] == "blocked" and takes.list_takes(project["id"]) == [] and core.submitted == []


def test_the_estimate_and_the_generate_blocks_agree_when_several_things_block_at_once(client, core, project):
    core.missing.add("vae-sha")
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}

    estimated = _estimate(client, project["id"])
    detail = _generate(client, project["id"], status=409)

    assert [block["code"] for block in detail["data"]["blocks"]] == [block["code"] for block in estimated["blocks"]]
    assert takes.list_takes(project["id"]) == []


def test_shots_listed_twice_or_unknown_make_one_take_per_known_shot(client, core, project):
    created = _generate(client, project["id"], shots=["s1", "nope", "s1", "s2"], variants=2)

    assert [(take["shot_id"], take["variant"]) for take in created] == [("s1", "A"), ("s1", "B"), ("s2", "A"), ("s2", "B")]
    assert len({take["seed"] for take in created}) == 4


@pytest.mark.parametrize(
    "fields",
    [
        {"variants": 17},
        {"variants": True},
        {"variants": 1.5},
        {"variants": "2"},
        {"quality": "ultra"},
        {"shots": "s1"},
        {"shots": [1]},
        {"preset_id": ""},
        {"model_id": 3},
        {"label": "x" * 201},
    ],
)
def test_a_malformed_order_answers_422_and_creates_nothing(client, core, project, fields):
    for route in ("estimate", "generate"):
        response = client.post(f"{BASE}/projects/{project['id']}/{route}", json={**ORDER, **fields})
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "invalid_request"

    assert takes.list_takes(project["id"]) == [] and core.submitted == [] and core.recorded == []


def test_a_deleted_take_is_not_brought_back_by_the_tracker_or_the_hooks(client, core, project):
    (take,) = _generate(client, project["id"])
    client.delete(f"{BASE}/projects/{project['id']}/takes/{take['id']}")
    core.complete(take["generation_id"])

    generation_hooks.on_after_complete(_after_complete(take["generation_id"]))
    _tick()

    assert takes.list_takes(project["id"]) == []
    assert core.notified == [] and takes.calibration(presets.WAN, "b-local", "832x480") == []


def test_the_variant_letters_of_a_shot_stay_unique_across_generations(client, core, project):
    first = _generate(client, project["id"], variants=2)
    second = _generate(client, project["id"], variants=2)

    assert len({take["variant"] for take in first + second}) == 4
