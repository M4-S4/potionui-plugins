import asyncio
import copy
import json
import subprocess

import pytest

from backend import chainvideo, encoder, estimate, generation, presets, sequence, takes, tracker
from backend.estimate import Order
from backend.frame_grab import FrameError

from .test_chain_frame import FFMPEG, TAKE_FILE, _frame_luma, library, video

FACE = {"id": "face", "kind": "image", "name": "face", "origin": {"kind": "library", "itemId": "lib-face"}}
REFERENCE = {"id": "r-face", "assetId": "face", "space": "identite", "scope": {"type": "global"}}
SHOTS = [{"id": "s1", "start": 0, "dur": 4, "label": "One"}, {"id": "s2", "start": 4, "dur": 3, "label": "Two"}]
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
STAND_IN = "chainvideo:s1"


class Ends:
    def __init__(self, monkeypatch):
        self.calls = []
        self.error = None
        monkeypatch.setattr(chainvideo, "end_video", self.cut)

    async def cut(self, owner, project, previous, after, frames, size, sound=False):
        self.calls.append((owner.id, previous, after["id"] if after else None, frames, tuple(size), sound))
        if self.error is not None:
            raise self.error
        value = f"uploads/end-{previous}-{len(self.calls)}.mp4"
        source = {"shotId": previous, "takeId": after["id"] if after else None, "assetId": f"gen-{after['id']}" if after else PLACED["id"], "at": 4.0}
        return {"value": value, "filename": value.rsplit("/", 1)[-1], "source": source, "frames": frames, "seconds": round(frames / 24, 6)}


@pytest.fixture
def ends(monkeypatch):
    return Ends(monkeypatch)


@pytest.fixture
def slots(store):
    store[("max_parallel_jobs", None)] = "4"


def _parts(clips=SHOTS, mode="Ref2VA", assets=(), references=(REFERENCE,)):
    return {"clips": [dict(clip) for clip in clips], "assets": [FACE, *assets], "references": list(references), "direction": {"mode": mode}}


def _project(core, make_project, chain_by="video", **options):
    core.use_h3()
    core.add_media({"kind": "library", "item_id": "lib-face"}, "uploads/face.png", "image")
    project = make_project(**_parts(**options))
    if chain_by is not None:
        project["doc"]["chainBy"] = chain_by
    return project


def _order(shots, **fields):
    return Order(**{"shots": list(shots), "quality": "draft", "variants": 1, "preset_id": presets.MINIMAX_H3, **fields})


def _evaluate(core, project, shots, **fields):
    user = core.users["user-1"]
    return asyncio.run(estimate.evaluate(user, user, project["doc"], _order(shots, **fields), project["id"]))


def _start(core, project, shots, **fields):
    user = core.users["user-1"]
    return asyncio.run(generation.start(user, project, _evaluate(core, project, shots, **fields)))


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _plan(evaluation, shot_id):
    return next(plan for plan in evaluation.plans.shots if plan.shot_id == shot_id)


def _codes(evaluation, shot_id="s2"):
    return [item["code"] for item in evaluation.payload["warnings"] if (item.get("data") or {}).get("shot_id") == shot_id and item["code"].startswith("chain_video")]


def _sections(prompt):
    return dict(block.partition(": ")[::2] for block in prompt.split("\n\n"))


def test_a_chained_ref2va_shot_after_one_of_the_same_order_sends_the_end_of_its_take_as_a_continuation_video(core, make_project, slots):
    project = _project(core, make_project)

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")
    sections = _sections(plan.prompt_text)

    assert evaluation.payload["blocks"] == []
    assert plan.request["form_data"]["references"] == [STAND_IN, "uploads/face.png"]
    assert plan.chain == "s1"
    assert plan.chain_video.trace() == {"previous": "s1", "frames": 56, "seconds": round(56 / 24, 6), "size": [832, 480], "sound": False}
    assert evaluation.payload["shots"][1]["chain_video"] == plan.chain_video.trace()
    assert evaluation.payload["shots"][1]["chain"] == "s1"
    assert _plan(evaluation, "s1").chain_video is None
    assert "<Video 1> is the footage that [Shot 1] continues." in sections["subject_definitions"]
    assert sections["summary"].startswith("[video continuation] + [reference generation] A 3-second shot that continues <Video 1>")
    assert "<Video 1> (continued by [Shot 1]): fully_preserved" in sections["retention_analysis"]
    assert sections["detailed_description"] == "[Shot 1] The shot continues from the last frame of <Video 1>. <Subject 1> appears in the shot."
    assert plan.rows is not None and plan.track_scale > 1.0
    assert set(evaluation.waits) == {"s2"}


def test_a_project_saved_before_the_chain_setting_keeps_its_chained_ref2va_shot_starting_from_its_references_as_before(core, make_project, slots):
    project = _project(core, make_project, chain_by=None)
    unchained = _project(core, make_project, chain_by=None, clips=[SHOTS[0], {**SHOTS[1], "firstFromPrevious": False}])

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")
    s1, s2 = _start(core, project, ["s1", "s2"])

    assert "chainBy" not in project["doc"]
    assert plan.request == _plan(_evaluate(core, unchained, ["s1", "s2"]), "s2").request
    assert plan.request["form_data"]["references"] == ["uploads/face.png"]
    assert (plan.chain, plan.chain_video) == (None, None)
    assert "[video continuation]" not in plan.prompt_text
    assert _codes(evaluation) == [] and evaluation.waits == {}
    assert s2["chain"] is None and s2["chain_wait"] is False and s2["generation_id"] is not None


def test_the_final_render_of_a_chained_ref2va_shot_of_a_project_saved_before_the_chain_setting_is_the_one_it_was(core, make_project, slots, monkeypatch):
    monkeypatch.setattr(sequence, "CEILING", 10**6)
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    project = _project(core, make_project, chain_by=None, clips=[first, {**SHOTS[1], "stage": "draft"}], assets=[PLACED])
    unchained = _project(core, make_project, chain_by=None, clips=[first, {**SHOTS[1], "stage": "draft", "firstFromPrevious": False}], assets=[PLACED])
    user = core.users["user-1"]

    def final(project):
        source = takes.create_take(
            {"project_id": project["id"], "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-2", "file_id": "f-2", "preset_id": presets.MINIMAX_H3, "seed": 7, "variant": "A", "profile": "Ref2VA"}
        )
        plan, _, _ = asyncio.run(generation.final_plan(user, project, source, generation.RENDER, "final"))
        return plan, generation.create_final(user, project, source, generation.RENDER, plan, presets.MINIMAX_H3, 0.0)

    plan, take = final(project)

    assert plan.request == final(unchained)[0].request
    assert plan.request["form_data"]["references"] == ["uploads/face.png"]
    assert (plan.chain, plan.chain_video, take["chain"]) == (None, None, None)

def test_a_ref2va_shot_chained_by_the_last_frame_in_a_project_that_continues_starts_from_its_references(core, make_project, slots):
    project = _project(core, make_project, clips=[SHOTS[0], {**SHOTS[1], "chainBy": "frame"}])

    evaluation = _evaluate(core, project, ["s1", "s2"])

    assert _plan(evaluation, "s2").chain_video is None and evaluation.waits == {}
    assert _plan(evaluation, "s2").request["form_data"]["references"] == ["uploads/face.png"]


def test_the_take_of_a_chained_ref2va_shot_waits_then_receives_the_cut_end_of_the_previous_take(core, make_project, ends, slots):
    project = _project(core, make_project)
    s1, s2 = _start(core, project, ["s1", "s2"])

    assert s2["generation_id"] is None and s2["chain_wait"] is True
    assert s2["chain"]["after"] == s1["id"] and s2["chain"]["state"] == "waiting"
    assert s2["chain"]["video"] == {"previous": "s1", "frames": 56, "seconds": round(56 / 24, 6), "size": [832, 480], "sound": False}
    assert s2["request"]["form_data"]["references"] == [STAND_IN, "uploads/face.png"]
    _tick()
    assert ends.calls == []
    core.complete(s1["generation_id"])
    _tick()

    taken = takes.get_take(s2["id"])
    assert ends.calls == [("user-1", "s1", s1["id"], 56, (832, 480), False)]
    assert taken["chain"]["state"] == "taken" and taken["chain"]["frame"] is None
    assert taken["chain"]["video"]["value"] == "uploads/end-s1-1.mp4"
    assert taken["chain"]["source"]["takeId"] == s1["id"]
    (_, request) = core.submitted[1]
    assert request["form_data"]["references"] == ["uploads/end-s1-1.mp4", "uploads/face.png"]
    assert "chainvideo:" not in json.dumps(request)


def test_a_chained_ref2va_shot_after_a_placed_take_continues_the_end_of_its_cut(core, make_project, ends, slots):
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0", "srcIn": 1.0}
    project = _project(core, make_project, clips=[first, SHOTS[1]], assets=[PLACED])

    (s2,) = _start(core, project, ["s2"])
    _tick()

    assert s2["chain"]["after"] is None
    assert ends.calls == [("user-1", "s1", None, 56, (832, 480), False)]
    assert takes.get_take(s2["id"])["generation_id"] is not None


def test_a_chained_ref2va_shot_with_a_first_frame_still_continues_the_previous_take(core, make_project, slots):
    project = _project(core, make_project, assets=[STILL])
    project["doc"]["frames"] = [{"id": "f2", "shotId": "s2", "time": 4, "assetId": "img", "role": "first", "strength": 100}]

    evaluation = _evaluate(core, project, ["s1", "s2"])

    assert _plan(evaluation, "s2").chain == "s1"


def test_a_take_of_the_previous_shot_that_failed_fails_the_waiting_ref2va_take(core, make_project, ends, slots):
    project = _project(core, make_project)
    s1, s2 = _start(core, project, ["s1", "s2"])

    core.fail(s1["generation_id"])
    _tick()

    failed = takes.get_take(s2["id"])
    assert (failed["status"], failed["error_code"]) == ("failed", "previous_take_failed")
    assert ends.calls == []


def test_an_end_that_cannot_be_cut_fails_the_waiting_ref2va_take_with_its_reason(core, make_project, ends, slots):
    project = _project(core, make_project)
    s1, s2 = _start(core, project, ["s1", "s2"])
    ends.error = FrameError("chain_video_failed", "ffmpeg stopped.", 502)

    core.complete(s1["generation_id"])
    _tick()

    failed = takes.get_take(s2["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "chain_video_failed", "ffmpeg stopped.")
    assert len(core.submitted) == 1


def test_a_continuation_track_the_user_placed_wins_over_the_end_of_the_previous_take(core, make_project, slots):
    core.add_media({"kind": "library", "item_id": "lib-walk"}, "uploads/walk.mp4", "video")
    walk = {"id": "walk", "kind": "video", "origin": {"kind": "library", "itemId": "lib-walk"}}
    project = _project(core, make_project, assets=[walk])
    project["doc"]["vrefTracks"] = [{"id": "t1", "slot": 1, "role": "continuation", "name": "Track 1"}]
    project["doc"]["vrefItems"] = [{"id": "i1", "track": "t1", "assetId": "walk", "start": 0, "dur": 4, "srcIn": 0}]

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")

    assert plan.chain is None and plan.chain_video is None
    assert plan.request["form_data"]["references"] == ["vtrack:t1", "uploads/face.png"]
    assert _codes(evaluation) == ["chain_video_own"]
    assert "s2" not in evaluation.waits


@pytest.mark.parametrize(
    ("case", "code"),
    [("nothing", "chain_video_none"), ("still", "chain_video_still"), ("short", "chain_video_short")],
)
def test_a_chained_ref2va_shot_that_cannot_continue_starts_from_its_references_and_says_why(core, make_project, slots, case, code):
    core.add_media({"kind": "library", "item_id": "it-1"}, "uploads/harbour.png")
    clips = [dict(clip) for clip in SHOTS]
    if case == "still":
        clips[0].update(assetId=STILL["id"], stage="source")
    if case == "short":
        clips[0]["dur"] = 2.0
    project = _project(core, make_project, clips=clips, assets=[STILL])
    shots = ["s1", "s2"] if case == "short" else ["s2"]

    evaluation = _evaluate(core, project, shots)
    plan = _plan(evaluation, "s2")

    assert plan.chain is None and plan.chain_video is None
    assert plan.request["form_data"]["references"] == ["uploads/face.png"]
    assert _codes(evaluation) == [code]
    assert "[video continuation]" not in plan.prompt_text


def test_a_ref2va_shot_whose_chain_is_off_sends_nothing_of_the_previous_take_and_says_nothing(core, make_project, slots):
    clips = [SHOTS[0], {**SHOTS[1], "firstFromPrevious": False}]
    project = _project(core, make_project, clips=clips)

    evaluation = _evaluate(core, project, ["s1", "s2"])

    assert _plan(evaluation, "s2").chain_video is None
    assert _codes(evaluation) == []
    assert evaluation.waits == {}
    assert _plan(evaluation, "s2").prompt_text.count("<Video") == 0
    assert _plan(evaluation, "s2").request["form_data"]["references"] == ["uploads/face.png"]
    assert _plan(evaluation, "s1").chain_video is None


def test_the_end_of_the_previous_take_is_not_added_past_three_videos(core, make_project, slots):
    videos, references = [], [REFERENCE]
    for name in ("v1", "v2", "v3"):
        core.add_media({"kind": "library", "item_id": f"lib-{name}"}, f"uploads/{name}.mp4", "video")
        videos.append({"id": name, "kind": "video", "origin": {"kind": "library", "itemId": f"lib-{name}"}})
        references.append({"id": f"r-{name}", "assetId": name, "space": "mouvement", "scope": {"type": "shot", "shotId": "s2"}})
    project = _project(core, make_project, assets=videos, references=references)

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")

    assert plan.chain is None and plan.chain_video is None
    assert STAND_IN not in plan.request["form_data"]["references"]
    assert _codes(evaluation) == ["chain_video_trimmed"]


def test_the_end_of_the_previous_take_is_left_out_when_it_alone_takes_the_shot_past_what_12_gb_holds(core, make_project, slots, monkeypatch):
    project = _project(core, make_project)
    monkeypatch.setattr(sequence, "CEILING", 1000)

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")

    assert plan.chain is None and plan.chain_video is None
    assert plan.request["form_data"]["references"] == ["uploads/face.png"]
    assert _codes(evaluation) == ["chain_video_rows"]
    assert "[video continuation]" not in plan.prompt_text
    assert "vref_rows_high" not in [item["code"] for item in evaluation.payload["warnings"]]


def test_fl2va_still_chains_by_the_last_image(core, make_project, slots):
    project = _project(core, make_project, chain_by=None, mode="FL2VA")

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation, "s2")

    assert plan.chain == "s1" and plan.chain_video is None and plan.director_mode == "i2v"
    assert _codes(evaluation) == []


def test_the_prompt_route_shows_the_continuation_a_shot_after_a_placed_take_will_send(core, make_project, client):
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    project = _project(core, make_project, clips=[first, SHOTS[1]], assets=[PLACED])

    response = client.post(f"/api/plugins/video-producer/projects/{project['id']}/prompts", json={"shots": ["s2"], "preset_id": presets.MINIMAX_H3, "doc": project["doc"]})
    (entry,) = response.json()["data"]["prompts"]

    assert "[video continuation]" in entry["prompt"]
    assert "chain_video_none" not in [item["code"] for item in entry["warnings"]]


def test_the_cut_command_keeps_the_sound_only_when_asked(tmp_path):
    silent = chainvideo.cut_command("ffmpeg", "in.mp4", 1.5, 56, (832, 480), tmp_path / "out.mp4")
    sound = chainvideo.cut_command("ffmpeg", "in.mp4", 0.0, 56, (832, 480), tmp_path / "out.mp4", sound=True)

    assert silent[silent.index("-ss") + 1] == "1.5" and "-an" in silent and "0:a:0?" not in silent
    assert "-ss" not in sound and "-an" not in sound and sound[sound.index("-map", sound.index("0:v:0")) + 1] == "0:a:0?"
    assert silent[silent.index("-frames:v") + 1] == "56" and silent[silent.index("-t") + 1] == chainvideo.num(56 / 24)


def _frames(path):
    command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames,width,height", "-of", "json", str(path)]
    return json.loads(subprocess.run(command, capture_output=True, check=True, text=True).stdout)["streams"][0]


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_the_end_of_a_take_is_cut_to_the_frames_and_size_asked_and_ends_on_the_frame_its_shot_ends_on(core, make_project, library, video, monkeypatch):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 2.5, "srcIn": 0.0}, {"id": "s2", "start": 2.5, "dur": 3}])
    take = takes.create_take(
        {"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-1", "file_id": "f-1", "file_path": TAKE_FILE}
    )
    library.files[("history", TAKE_FILE)] = video
    kept = {}
    original = library.save_user_media

    async def save(user, path):
        kept["probe"] = _frames(path)
        kept["last"] = _frame_luma(path, int(kept["probe"]["nb_read_frames"]) - 1)
        return await original(user, path)

    monkeypatch.setattr(chainvideo.core_bridge, "save_user_media", save)

    cut = asyncio.run(chainvideo.end_video(core.users["user-1"], project, "s1", take, 24, (64, 36)))

    assert cut["source"] == {"shotId": "s1", "takeId": take["id"], "assetId": f"gen-{take['id']}", "at": 2.5}
    assert (int(kept["probe"]["nb_read_frames"]), kept["probe"]["width"], kept["probe"]["height"]) == (24, 64, 36)
    assert abs(kept["last"] - _frame_luma(video, 24)) < 3


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_a_take_shorter_than_the_continuation_cannot_be_cut(core, make_project, library, video):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 1.0, "srcIn": 0.0}, {"id": "s2", "start": 1.0, "dur": 3}])
    take = takes.create_take(
        {"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-1", "file_id": "f-1", "file_path": TAKE_FILE}
    )
    library.files[("history", TAKE_FILE)] = video

    with pytest.raises(FrameError) as raised:
        asyncio.run(chainvideo.end_video(core.users["user-1"], project, "s1", take, 56, (64, 36)))

    assert raised.value.code == "chain_video_short"
    assert library.saved == []


def _streams(path):
    command = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(path)]
    return {stream["codec_type"]: float(stream.get("duration") or 0) for stream in json.loads(subprocess.run(command, capture_output=True, check=True, text=True).stdout)["streams"]}


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_the_end_of_a_take_cut_with_its_sound_keeps_the_sound_of_those_frames(core, make_project, library, tmp_path, monkeypatch):
    source = tmp_path / "source" / "sound.mp4"
    source.parent.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x36:r=24:d=4", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", str(source)],
        check=True,
    )
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 4.0, "srcIn": 0.0}, {"id": "s2", "start": 4.0, "dur": 3}])
    take = takes.create_take(
        {"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-1", "file_id": "f-1", "file_path": TAKE_FILE}
    )
    library.files[("history", TAKE_FILE)] = source
    kept = {}
    original = library.save_user_media

    async def save(user, path):
        kept["streams"] = _streams(path)
        kept["frames"] = int(_frames(path)["nb_read_frames"])
        return await original(user, path)

    monkeypatch.setattr(chainvideo.core_bridge, "save_user_media", save)

    asyncio.run(chainvideo.end_video(core.users["user-1"], project, "s1", take, 56, (64, 36), sound=True))

    assert kept["frames"] == 56
    assert set(kept["streams"]) == {"video", "audio"}
    assert abs(kept["streams"]["audio"] - 56 / 24) < 0.1


TWELVE = presets.MINIMAX_H3_12GB
QUAY = {"id": "quay", "kind": "image", "name": "quay", "origin": {"kind": "library", "itemId": "lib-quay"}, "width": 1344, "height": 768}
BOOTS = {"id": "boots", "kind": "image", "name": "boots", "origin": {"kind": "library", "itemId": "lib-boots"}, "width": 1024, "height": 1024}


def _twelve(core, make_project, monkeypatch, size, pictures):
    monkeypatch.setattr(sequence, "CEILING", 10**6)
    core.use_h3_12gb()
    sized = [{**FACE, "width": 1024, "height": 1024}, QUAY, *pictures]
    for asset in sized:
        core.add_media({"kind": "library", "item_id": asset["origin"]["itemId"]}, f"uploads/{asset['id']}.png", "image")
    references = [{"id": f"r-{asset['id']}", "assetId": asset["id"], "space": "identite", "scope": {"type": "global"}} for asset in sized]
    project = make_project(clips=[dict(clip) for clip in SHOTS], assets=sized, references=references, direction={"mode": "Ref2VA"})
    project["doc"]["chainBy"] = "video"
    project["doc"].setdefault("engine", {})["sizes"] = {TWELVE: {"draft": size}}
    return project


def _encoder_codes(evaluation):
    return [item for item in evaluation.payload["warnings"] if item["code"] == "chain_video_encoder"]


def test_on_the_12_gb_preset_a_ref2va_shot_at_832_by_480_with_two_pictures_still_receives_the_end_of_the_previous_take(core, make_project, slots, monkeypatch):
    project = _twelve(core, make_project, monkeypatch, "832x480", [])

    evaluation = _evaluate(core, project, ["s1", "s2"], preset_id=TWELVE)
    plan = _plan(evaluation, "s2")

    assert plan.chain_video is not None and plan.chain_video.size == (832, 480)
    assert STAND_IN in plan.request["form_data"]["references"]
    assert _encoder_codes(evaluation) == []
    assert encoder.vision_tokens([(1024, 1024), (1344, 768)], [(56, (832, 480))], encoder.max_pixels(1, (832, 480))) == 1895


def test_on_the_12_gb_preset_a_ref2va_shot_at_960_by_544_with_two_pictures_keeps_the_last_image_and_says_why(core, make_project, slots, monkeypatch):
    project = _twelve(core, make_project, monkeypatch, "960x544", [])
    unchained = copy.deepcopy(project)
    unchained["doc"]["chainBy"] = "frame"

    evaluation = _evaluate(core, project, ["s1", "s2"], preset_id=TWELVE)
    plan = _plan(evaluation, "s2")
    (warning,) = _encoder_codes(evaluation)

    assert plan.chain_video is None and plan.chain is None
    assert STAND_IN not in json.dumps(plan.request)
    assert plan.request == _plan(_evaluate(core, unchained, ["s1", "s2"], preset_id=TWELVE), "s2").request
    assert warning["data"] == {"shot_id": "s2", "previous": "s1", "tokens": 2507, "limit": encoder.LIMIT_12GB}
    assert evaluation.waits == {}


def test_on_the_12_gb_preset_a_third_picture_at_832_by_480_takes_the_shot_past_what_the_encoder_reads(core, make_project, slots, monkeypatch):
    project = _twelve(core, make_project, monkeypatch, "832x480", [BOOTS])

    evaluation = _evaluate(core, project, ["s1", "s2"], preset_id=TWELVE)
    (warning,) = _encoder_codes(evaluation)

    assert _plan(evaluation, "s2").chain_video is None
    assert warning["data"]["tokens"] == 1895 + 361
    assert len(_plan(evaluation, "s2").request["form_data"]["references"]) == 3


def test_a_picture_of_unknown_size_counts_as_large_as_the_encoder_reads_one():
    limit = encoder.max_pixels(1, (832, 480))

    assert encoder.image_tokens(None, limit) == 390
    assert encoder.image_tokens((1024, 1024), limit) == 361
    assert encoder.image_tokens((1024, 1024), encoder.max_pixels(None, (832, 480))) == 1024
    assert encoder.max_pixels(0, (832, 480)) == encoder.MAX_PIXELS
