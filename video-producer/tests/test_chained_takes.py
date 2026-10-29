import asyncio
import json
from pathlib import Path

import pytest

from backend import chain, chaining, core_bridge, estimate, generation, presets, projects, takes, tracker
from backend.chain import ChainError
from backend.estimate import Order
from backend.tables import create_tables

from .test_chain_frame import FFMPEG, FPS, TAKE_FILE, _frame_luma, _luma, library, video
from .test_director import _wan_tier

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 6}, {"id": "s3", "start": 10, "dur": 4}]
STAND_IN = "chain:s1"
PLACED = {
    "id": "gen-t0",
    "kind": "video",
    "src": "/api/media/generations/g-0/1.mp4",
    "origin": {"kind": "history", "generationId": "g-0", "fileId": "f-0"},
    "srcDur": 6.0,
    "generated": True,
    "quality": "draft",
    "resultId": "t0",
}
STILL = {"id": "img", "kind": "image", "src": "/api/media/uploads/harbour.png", "origin": {"kind": "library", "itemId": "it-1"}}


class Frames:
    def __init__(self, monkeypatch, store):
        self.store = store
        self.calls = []
        self.error = None
        monkeypatch.setattr(chain, "cut_frame", self.cut)

    async def cut(self, owner, project_id, clip, asset):
        self.calls.append((owner.id, clip["id"], clip.get("srcIn"), clip.get("dur"), asset["id"]))
        if self.error is not None:
            raise self.error
        end = chain.end_of(clip)
        value = f"uploads/{asset['id']}-frame-{chain.num(end)}s.png"
        self.store.items[value] = f"item-{len(self.calls)}"
        return {"value": value, "filename": value.rsplit("/", 1)[-1], "source": {"shotId": clip["id"], "takeId": asset.get("resultId"), "assetId": asset["id"], "at": end}}


@pytest.fixture
def frames(monkeypatch, media_store):
    return Frames(monkeypatch, media_store)


@pytest.fixture
def slots(store):
    store[("max_parallel_jobs", None)] = "4"


def _order(shots, variants=1, **fields):
    return Order(**{"shots": list(shots), "quality": "draft", "variants": variants, "preset_id": presets.WAN, **fields})


def _evaluate(core, project, shots, **fields):
    user = core.users["user-1"]
    return asyncio.run(estimate.evaluate(user, user, project["doc"], _order(shots, **fields), project["id"]))


def _start(core, project, shots, **fields):
    user = core.users["user-1"]
    return asyncio.run(generation.start(user, project, _evaluate(core, project, shots, **fields)))


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _paths(request):
    return [entry["media"]["path"] for entry in request["form_data"]["video_director"]["media"]]


def _waits(make_doc, shots, **parts):
    return chaining.waits("", make_doc(**parts), shots)


def test_without_ffmpeg_the_shots_that_start_from_the_previous_one_are_blocked_before_any_take_is_made(core, make_project, slots, monkeypatch):
    core.use_wan()
    project = make_project(clips=SHOTS)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    evaluation = _evaluate(core, project, ["s1", "s2", "s3"])

    assert [(block["code"], block["data"]) for block in evaluation.payload["blocks"]] == [
        ("chain_ffmpeg_missing", {"shot_ids": ["s2", "s3"]}),
    ]
    assert evaluation.payload["blocks"][0]["message"] == "ffmpeg is not available on this server: the last image of the previous shot cannot be taken for the shots that start from it."
    with pytest.raises(generation.Blocked):
        asyncio.run(generation.start(core.users["user-1"], project, evaluation))
    assert takes.list_takes(project["id"]) == []


def test_with_ffmpeg_or_without_a_chain_nothing_blocks(core, make_project, slots, monkeypatch):
    core.use_wan()
    project = make_project(clips=SHOTS)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    assert _evaluate(core, project, ["s1"]).payload["blocks"] == []
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    assert _evaluate(core, project, ["s1", "s2"]).payload["blocks"] == []


def test_a_shot_after_one_of_the_same_order_waits_for_its_take_of_the_same_letter(core, make_project, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])

    s1a, s1b, s2a, s2b = _start(core, project, ["s1", "s2"], variants=2)

    assert [take["generation_id"] is not None for take in (s1a, s1b, s2a, s2b)] == [True, True, False, False]
    assert (s1a["chain"], s1b["chain"]) == (None, None)
    assert (s2a["chain"]["after"], s2b["chain"]["after"]) == (s1a["id"], s1b["id"])
    assert all(take["chain"]["state"] == "waiting" and take["chain"]["previous"] == "s1" and take["chain_wait"] for take in (s2a, s2b))
    assert s2a["chain"]["batch"] == s2b["chain"]["batch"]
    assert s2a["director_mode"] == "i2v" and _paths(s2a["request"]) == [STAND_IN]
    assert takes.waiting("user-1") == []
    assert takes.public(s2a)["chain"] == s2a["chain"]


def test_a_shot_with_more_takes_than_the_previous_one_waits_for_its_first_take_with_the_others(core, make_project, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])

    s1a, s2a, s2b = _start(core, project, ["s1", "s2"], shot_variants={"s2": 2})

    assert (s2a["variant"], s2b["variant"]) == ("A", "B")
    assert s2a["chain"]["after"] == s2b["chain"]["after"] == s1a["id"]


def test_the_takes_are_created_in_the_order_of_the_edit_whatever_the_order_of_the_request(core, make_project, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])

    created = _start(core, project, ["s2", "s1"])

    assert [take["shot_id"] for take in created] == ["s1", "s2"]
    assert created[1]["chain"]["after"] == created[0]["id"]


def test_the_tracker_gives_the_waiting_take_the_end_of_the_previous_take_then_hands_it_over(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])

    _tick()

    assert len(core.submitted) == 1 and frames.calls == []
    core.complete(s1["generation_id"])
    _tick()

    taken = takes.get_take(s2["id"])
    assert frames.calls == [("user-1", "s1", 0, 4.0, f"gen-{s1['id']}")]
    assert taken["generation_id"] == "gen-2" and taken["chain_wait"] is False
    assert taken["chain"]["state"] == "taken"
    assert taken["chain"]["source"] == {"shotId": "s1", "takeId": s1["id"], "assetId": f"gen-{s1['id']}", "at": 4.0}
    assert taken["chain"]["frame"]["url"] == f"/api/media/uploads/gen-{s1['id']}-frame-4s.png"
    assert taken["chain"]["frame"]["origin"] == {"kind": "library", "itemId": "item-1"}
    (_, request) = core.submitted[1]
    assert _paths(request) == [f"uploads/gen-{s1['id']}-frame-4s.png"]
    assert "chain:" not in json.dumps(request)
    assert taken["request"] == request


def test_the_end_of_a_previous_take_is_the_duration_of_its_shot_from_the_start_of_the_take(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 3, "srcIn": 1.5}, SHOTS[1]])
    s1, _ = _start(core, project, ["s1", "s2"])

    core.complete(s1["generation_id"])
    _tick()

    assert frames.calls == [("user-1", "s1", 0, 3.0, f"gen-{s1['id']}")]


@pytest.mark.parametrize(
    ("end", "code"),
    [("failed", "previous_take_failed"), ("cancelled", "previous_take_cancelled"), ("deleted", "previous_take_gone")],
)
def test_a_waiting_take_fails_when_the_previous_take_does_not_finish_and_gives_back_its_minutes(core, make_project, frames, slots, end, code):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])

    if end == "failed":
        core.fail(s1["generation_id"])
    elif end == "cancelled":
        asyncio.run(generation.cancel(core.users["user-1"], s1))
    else:
        takes.delete_take(s1["id"])
    _tick()

    failed = takes.get_take(s2["id"])
    assert (failed["status"], failed["error_code"], failed["generation_id"]) == ("failed", code, None)
    assert f"video-producer:{s2['id']}" in core.refunded
    assert core.notified[-1]["notification_type"] == "video-producer.take_failed"
    assert frames.calls == [] and len(core.submitted) == 1


def test_a_last_image_that_cannot_be_taken_fails_the_waiting_take_with_its_reason(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])
    frames.error = ChainError("extract_failed", "Taking the frame took longer than 60 s.", 502)

    core.complete(s1["generation_id"])
    _tick()

    failed = takes.get_take(s2["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "chain_frame_failed", "Taking the frame took longer than 60 s.")
    assert len(core.submitted) == 1


def test_cancelling_a_waiting_take_needs_no_core_call_and_the_queue_never_hands_it_over(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])

    cancelled = asyncio.run(generation.cancel(core.users["user-1"], s2))
    core.complete(s1["generation_id"])
    _tick()

    assert cancelled["status"] == "cancelled" and core.cancelled == []
    assert takes.get_take(s2["id"])["status"] == "cancelled"
    assert frames.calls == [] and len(core.submitted) == 1


def test_a_new_tracker_after_a_restart_picks_up_the_waiting_takes_from_the_table(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])

    create_tables()
    core.complete(s1["generation_id"])
    _tick()

    assert takes.get_take(s2["id"])["generation_id"] == "gen-2"


def test_each_shot_of_a_sequence_waits_for_the_one_before_it(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS)
    s1, s2, s3 = _start(core, project, ["s1", "s2", "s3"])

    assert (s2["chain"]["after"], s3["chain"]["after"]) == (s1["id"], s2["id"])
    core.complete(s1["generation_id"])
    _tick()
    assert takes.get_take(s3["id"])["chain_wait"] is True
    core.complete(takes.get_take(s2["id"])["generation_id"])
    _tick()

    assert [call[1] for call in frames.calls] == ["s1", "s2"]
    assert takes.get_take(s3["id"])["generation_id"] == "gen-3"


def test_a_shot_after_a_placed_video_waits_for_the_tracker_to_take_the_end_of_its_cut(core, make_project, frames, slots):
    core.use_wan()
    first = {"id": "s1", "start": 0, "dur": 3, "srcIn": 1.0, "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    project = make_project(clips=[first, SHOTS[1]], assets=[PLACED])

    (s2,) = _start(core, project, ["s2"])
    _tick()

    assert s2["chain"]["after"] is None and s2["chain"]["state"] == "waiting"
    assert frames.calls == [("user-1", "s1", 1.0, 3, "gen-t0")]
    assert takes.get_take(s2["id"])["chain"]["source"]["at"] == 4.0
    assert takes.get_take(s2["id"])["generation_id"] == "gen-1"


def test_a_shot_after_a_still_starts_from_the_still_at_once(core, make_project, frames, slots):
    core.use_wan()
    core.add_media({"kind": "library", "item_id": "it-1"}, "uploads/harbour.png")
    first = {"id": "s1", "start": 0, "dur": 4, "assetId": STILL["id"], "stage": "source"}
    project = make_project(clips=[first, SHOTS[1]], assets=[STILL])

    (s2,) = _start(core, project, ["s2"])

    assert s2["generation_id"] == "gen-1" and s2["chain_wait"] is False
    assert s2["chain"]["state"] == "taken"
    assert s2["chain"]["source"] == {"shotId": "s1", "takeId": None, "assetId": "img", "at": None}
    assert _paths(s2["request"]) == ["uploads/harbour.png"]
    assert frames.calls == []


def test_a_shot_after_a_shot_still_being_generated_waits_for_its_take_of_the_same_letter(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1a, s1b = _start(core, project, ["s1"], variants=2)

    (s2,) = _start(core, project, ["s2"])

    assert s2["chain"]["after"] == s1a["id"]
    core.complete(s1a["generation_id"])
    _tick()
    assert takes.get_take(s2["id"])["chain"]["source"]["takeId"] == s1a["id"]


def test_orders_added_while_takes_run_queue_behind_them_with_the_next_letter_and_chain_on_the_takes_still_queued(core, make_project, frames, store):
    store[("max_parallel_jobs", None)] = "1"
    core.use_wan()
    project = make_project(clips=SHOTS)
    (s1a,) = _start(core, project, ["s1"])

    (s1b,) = _start(core, project, ["s1"])
    (s2,) = _start(core, project, ["s2"])
    (s3,) = _start(core, project, ["s3"])

    assert (s1a["variant"], s1b["variant"], s2["variant"], s3["variant"]) == ("A", "B", "A", "A")
    assert s1a["generation_id"] is not None and (s1b["generation_id"], s2["generation_id"], s3["generation_id"]) == (None, None, None)
    assert [take["id"] for take in takes.waiting("user-1")] == [s1b["id"]]
    assert (s2["chain"]["after"], s3["chain"]["after"]) == (s1a["id"], s2["id"])
    assert s2["chain"]["batch"] != s3["chain"]["batch"]
    core.complete(s1a["generation_id"])
    _tick()

    assert takes.get_take(s1b["id"])["generation_id"] is not None
    assert takes.get_take(s2["id"])["chain"]["state"] == "taken" and takes.get_take(s2["id"])["generation_id"] is None
    assert takes.get_take(s3["id"])["chain_wait"] is True
    assert len(core.submitted) == 2


def test_a_shot_keeps_an_image_of_its_own_and_a_last_image_already_taken_from_a_previous_shot_left_out_of_the_order(make_doc):
    own = {"id": "own", "kind": "image", "src": "/x.png", "origin": {"kind": "library", "itemId": "it-2"}}
    taken = {**own, "id": "taken", "frameOf": {"shotId": "s1", "takeId": "t0", "assetId": "gen-t0", "at": 4.0}}

    def first(asset):
        return {"frames": [{"id": "f", "shotId": "s2", "time": 4, "assetId": asset["id"], "role": "first"}], "assets": [asset]}

    assert _waits(make_doc, ["s2"], clips=SHOTS[:2], **first(own)) == {}
    assert _waits(make_doc, ["s1", "s2"], clips=SHOTS[:2], **first(own)) == {}
    assert _waits(make_doc, ["s2"], clips=SHOTS[:2], **first(taken)) == {}
    assert _waits(make_doc, ["s1", "s2"], clips=SHOTS[:2], **first(taken))["s2"].source == chaining.BATCH


def test_the_option_of_a_shot_wins_over_the_option_of_the_project(make_doc):
    off = {**SHOTS[1], "firstFromPrevious": False}
    on = {**SHOTS[1], "firstFromPrevious": True}
    project_off = make_doc(clips=[SHOTS[0], on])
    project_off["firstFromPrevious"] = False
    plain_off = make_doc(clips=SHOTS[:2])
    plain_off["firstFromPrevious"] = False

    assert list(_waits(make_doc, ["s1", "s2"], clips=SHOTS[:2])) == ["s2"]
    assert _waits(make_doc, ["s1", "s2"], clips=[SHOTS[0], off]) == {}
    assert list(chaining.waits("", project_off, ["s1", "s2"])) == ["s2"]
    assert chaining.waits("", plain_off, ["s1", "s2"]) == {}
    assert _waits(make_doc, ["s1"], clips=SHOTS[:2]) == {}


def test_an_engine_that_starts_from_text_only_does_not_wait(core, make_project, frames, slots):
    preset_id = _wan_tier(core, preset_id=presets.WAN22_14B_LIGHTNING_12GB)
    project = make_project(clips=SHOTS[:2])

    evaluation = _evaluate(core, project, ["s1", "s2"], preset_id=preset_id)
    s1, s2 = _start(core, project, ["s1", "s2"], preset_id=preset_id)

    assert evaluation.waits == {}
    assert [shot["chain"] for shot in evaluation.payload["shots"]] == [None, None]
    assert all(warning["code"] != "text_only_preset" for warning in evaluation.payload["warnings"])
    assert s2["chain"] is None and s2["director_mode"] == "t2v" and s2["generation_id"] == "gen-2"


def test_the_estimate_plans_the_waiting_shot_from_an_image(core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])

    payload = _evaluate(core, project, ["s1", "s2"]).payload

    assert [(shot["shot_id"], shot["director_mode"], shot["chain"]) for shot in payload["shots"]] == [("s1", "t2v", None), ("s2", "i2v", "s1")]
    assert [warning["data"]["shot_id"] for warning in payload["warnings"] if warning["code"] == "fl2va_no_frame"] == ["s1"]


def test_the_queue_gives_no_place_to_a_waiting_take(client, core, make_project, store):
    core.use_wan()
    store[("max_parallel_jobs", None)] = "1"
    project = make_project(clips=[*SHOTS[:2], {**SHOTS[2], "firstFromPrevious": False}])
    s1, s2, s3 = _start(core, project, ["s1", "s2", "s3"])

    data = client.get(f"{BASE}/projects/{project['id']}/queue").json()["data"]

    assert [(take["id"], take["queue_position"]) for take in data["takes"]] == [(s1["id"], None), (s2["id"], None), (s3["id"], 1)]
    assert [take["id"] for take in takes.waiting("user-1")] == [s3["id"]]
    assert takes.prioritize(takes.get_take(s2["id"]))["priority"] == 0


def test_a_retry_of_a_take_whose_previous_take_failed_waits_for_the_new_take_of_the_previous_shot(core, make_project, frames, slots):
    core.use_wan()
    project = make_project(clips=SHOTS[:2])
    s1, s2 = _start(core, project, ["s1", "s2"])
    core.fail(s1["generation_id"])
    _tick()
    owner = core.users["user-1"]
    current = projects.get_project(project["id"])

    again = asyncio.run(generation.retry(owner, current, takes.get_take(s1["id"])))
    retried = asyncio.run(generation.retry(owner, current, takes.get_take(s2["id"])))

    assert retried["chain"]["after"] == again["id"] and retried["chain_wait"] is True
    assert _paths(retried["request"]) == [STAND_IN]


def test_the_shot_option_is_an_optional_boolean_and_both_migrations_drop_any_other_value(make_doc):
    cases = json.loads((Path(__file__).parent / "fixtures" / "chain_flag_migration.json").read_text(encoding="utf-8"))
    for case in cases:
        doc = make_doc(clips=[SHOTS[0], {**SHOTS[1], "firstFromPrevious": case["value"]}])
        migrated = projects.migrate(doc)["clips"][1]
        assert migrated.get("firstFromPrevious", None) == case["expected"]
        assert ("firstFromPrevious" in migrated) == (case["expected"] is not None)
        projects.validate_doc(projects.migrate(doc))
    with pytest.raises(projects.DocError):
        projects.validate_doc(make_doc(clips=[{**SHOTS[0], "firstFromPrevious": "yes"}]))


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_the_end_of_a_take_not_placed_yet_is_cut_from_its_file_at_the_duration_of_its_shot(core, make_project, library, video):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 2.0, "srcIn": 0.7}, SHOTS[1]])
    take = takes.create_take(
        {"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-1", "file_id": "f-1", "file_path": TAKE_FILE}
    )
    library.files[("history", TAKE_FILE)] = video

    frame = asyncio.run(chain.take_end_frame(core.users["user-1"], project, "s1", take))

    assert frame["source"] == {"shotId": "s1", "takeId": take["id"], "assetId": f"gen-{take['id']}", "at": 2.0}
    assert abs(_luma(library.saved[0][2]) - _frame_luma(video, int(2.0 * FPS) - 1)) < 1.5
