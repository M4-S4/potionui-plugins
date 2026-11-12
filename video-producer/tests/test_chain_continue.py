import asyncio
import json
from pathlib import Path

import pytest
import yaml

from backend import bible, chainvideo, director, estimate, generation, presets, sequence, takes, tracker
from backend.estimate import Order
from backend.projects import DocError, validate_doc

PRESET = Path(__file__).resolve().parents[1] / "presets" / "MiniMax-H3-12GB"
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
OWN = {"id": "own", "kind": "image", "src": "/api/media/uploads/own.png", "origin": {"kind": "library", "itemId": "it-own"}}
STAND_IN = "chainvideo:s1"
TWELVE = presets.MINIMAX_H3_12GB


class Ends:
    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr(chainvideo, "end_video", self.cut)

    async def cut(self, owner, project, previous, after, frames, size, sound=False):
        self.calls.append((previous, after["id"] if after else None, frames, tuple(size), sound))
        value = f"uploads/end-{previous}.mp4"
        source = {"shotId": previous, "takeId": after["id"] if after else None, "assetId": "gen-x", "at": 4.0}
        return {"value": value, "filename": "end.mp4", "source": source, "frames": frames, "seconds": round(frames / 24, 6)}


@pytest.fixture
def ends(monkeypatch):
    return Ends(monkeypatch)


@pytest.fixture
def slots(store):
    store[("max_parallel_jobs", None)] = "4"


def _project(core, make_project, chain_by="video", clips=SHOTS, assets=(), frames=(), **extra):
    core.use_h3_continue()
    core.add_media({"kind": "library", "item_id": "it-1"}, "uploads/harbour.png")
    core.add_media({"kind": "library", "item_id": "it-own"}, "uploads/own.png")
    project = make_project(clips=[dict(clip) for clip in clips], assets=list(assets), frames=list(frames), direction={"mode": "FL2VA"}, **extra)
    if chain_by is not None:
        project["doc"]["chainBy"] = chain_by
    return project


def _order(shots, preset_id=TWELVE):
    return Order(shots=list(shots), quality="draft", variants=1, preset_id=preset_id)


def _evaluate(core, project, shots, preset_id=TWELVE):
    user = core.users["user-1"]
    return asyncio.run(estimate.evaluate(user, user, project["doc"], _order(shots, preset_id), project["id"]))


def _plan(evaluation, shot_id="s2"):
    return next(plan for plan in evaluation.plans.shots if plan.shot_id == shot_id)


def _codes(evaluation, shot_id="s2"):
    return [item["code"] for item in evaluation.payload["warnings"] if (item.get("data") or {}).get("shot_id") == shot_id and item["code"].startswith("chain_continue")]


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def test_a_shot_chained_by_continuation_sends_the_end_of_the_previous_take_as_its_source_video_without_a_document(core, make_project, slots):
    project = _project(core, make_project)

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation)
    form = plan.request["form_data"]

    assert evaluation.payload["blocks"] == []
    assert (plan.request["mode"], plan.preset_mode, plan.director_mode) == ("extend", "extend", "extend")
    assert "video_director" not in form
    assert (form["source_video"], form["frames"], form["resolution"], form["quantity"]) == (STAND_IN, 72, plan.resolution, 1)
    assert form["model"] == "model:id-fl2va-sha" and form["audio_vae"].startswith("model:")
    assert plan.chain == "s1"
    assert plan.chain_video.trace() == {"previous": "s1", "frames": 56, "seconds": round(56 / 24, 6), "size": [int(side) for side in plan.resolution.split("x")], "sound": True}
    assert plan.work_scale == pytest.approx((72 + 17) / 72)
    assert plan.request["prompts"][0]["positive"] == plan.prompt_text
    assert _plan(evaluation, "s1").request["mode"] == "video"
    assert set(evaluation.waits) == {"s2"}
    assert _codes(evaluation) == []


def test_by_default_a_shot_still_chains_by_the_last_image(core, make_project, slots):
    project = _project(core, make_project, chain_by=None)

    plan = _plan(_evaluate(core, project, ["s1", "s2"]))
    shot = {**project["doc"]["clips"][1], "chainBy": "video"}
    project["doc"]["clips"][1] = shot
    continued = _plan(_evaluate(core, project, ["s1", "s2"]))

    assert (plan.request["mode"], plan.director_mode, plan.chain_video) == ("video", "i2v", None)
    assert continued.request["mode"] == "extend"


def test_the_take_of_a_shot_chained_by_continuation_waits_then_receives_the_end_of_the_previous_take_with_its_sound(core, make_project, ends, slots):
    project = _project(core, make_project)
    user = core.users["user-1"]
    s1, s2 = asyncio.run(generation.start(user, project, _evaluate(core, project, ["s1", "s2"])))

    assert s2["chain_wait"] is True and s2["chain"]["video"]["sound"] is True
    assert s2["request"]["form_data"]["source_video"] == STAND_IN
    core.complete(s1["generation_id"])
    _tick()

    (_, request) = core.submitted[1]
    assert ends.calls == [("s1", s1["id"], 56, tuple(s2["chain"]["video"]["size"]), True)]
    assert request["mode"] == "extend" and request["form_data"]["source_video"] == "uploads/end-s1.mp4"
    assert "chainvideo:" not in json.dumps(request)


def test_a_first_frame_the_page_took_from_the_previous_shot_does_not_stop_the_continuation(core, make_project, slots):
    chained = {**STILL, "id": "chain-x", "frameOf": {"shotId": "s1", "takeId": "t0", "assetId": "gen-t0", "at": 4}}
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    frame = {"id": "f2", "shotId": "s2", "time": 4, "assetId": "chain-x", "role": "first", "strength": 100}
    project = _project(core, make_project, clips=[first, SHOTS[1]], assets=[PLACED, chained], frames=[frame])

    plan = _plan(_evaluate(core, project, ["s2"]))

    assert plan.request["mode"] == "extend" and plan.chain == "s1"


def test_a_shot_with_a_first_frame_of_its_own_does_not_chain(core, make_project, slots):
    frame = {"id": "f2", "shotId": "s2", "time": 4, "assetId": "own", "role": "first", "strength": 100}
    project = _project(core, make_project, assets=[OWN], frames=[frame])

    evaluation = _evaluate(core, project, ["s1", "s2"])

    assert _plan(evaluation).request["mode"] == "video" and _plan(evaluation).chain is None
    assert "s2" not in evaluation.waits
    project["doc"]["frames"] = []
    assert _plan(_evaluate(core, project, ["s1", "s2"])).request["mode"] == "extend"


@pytest.mark.parametrize("case", ["last", "keep"])
def test_a_shot_with_a_last_frame_keeps_the_chain_by_the_last_image_and_says_why(core, make_project, slots, case):
    clips = [SHOTS[0], {**SHOTS[1], "keepFraming": True} if case == "keep" else SHOTS[1]]
    frames = [{"id": "l2", "shotId": "s2", "time": 6.9, "assetId": "own", "role": "last", "strength": 100}] if case == "last" else []
    project = _project(core, make_project, clips=clips, assets=[OWN], frames=frames)

    evaluation = _evaluate(core, project, ["s1", "s2"])
    plan = _plan(evaluation)

    assert (plan.request["mode"], plan.director_mode, plan.chain) == ("video", "flf", "s1")
    assert _codes(evaluation) == ["chain_continue_last_frame"]


@pytest.mark.parametrize(
    ("case", "code", "mode"),
    [
        ("engine", "chain_continue_unsupported", "i2v"),
        ("still", "chain_continue_still", "i2v"),
        ("short", "chain_continue_short", "i2v"),
        ("long", "chain_continue_too_long", "i2v"),
    ],
)
def test_a_shot_that_cannot_be_continued_starts_from_the_last_image_and_says_why(core, make_project, slots, case, code, mode):
    clips = [dict(clip) for clip in SHOTS]
    if case == "still":
        clips[0].update(assetId=STILL["id"], stage="source")
    if case == "short":
        clips[0]["dur"] = 2.0
    if case == "long":
        clips[1]["dur"] = 14.0
    project = _project(core, make_project, clips=clips, assets=[STILL])
    shots = ["s2"] if case == "still" else ["s1", "s2"]

    evaluation = _evaluate(core, project, shots, presets.MINIMAX_H3 if case == "engine" else TWELVE)
    plan = _plan(evaluation)

    assert (plan.request["mode"], plan.director_mode, plan.chain_video) == ("video", mode, None)
    assert plan.chain == "s1"
    assert _codes(evaluation) == [code]


def test_a_shot_whose_sound_is_mixed_onto_its_take_keeps_the_chain_by_the_last_image(core, make_project, slots):
    core.add_media({"kind": "library", "item_id": "it-rain"}, "uploads/rain.wav", "audio")
    rain = {"id": "rain", "kind": "audio", "src": "/api/media/uploads/rain.wav", "origin": {"kind": "library", "itemId": "it-rain"}}
    references = [{"id": "r-rain", "assetId": "rain", "space": "son", "scope": {"type": "shot", "shotId": "s2"}}]
    project = _project(core, make_project, assets=[rain], references=references)

    evaluation = _evaluate(core, project, ["s1", "s2"])

    assert _plan(evaluation).request["mode"] == "video"
    assert _codes(evaluation) == ["chain_continue_sound"]


def test_a_shot_can_keep_the_last_image_in_a_project_that_continues(core, make_project, slots):
    project = _project(core, make_project, clips=[SHOTS[0], {**SHOTS[1], "chainBy": "frame"}])

    plan = _plan(_evaluate(core, project, ["s1", "s2"]))

    assert (plan.request["mode"], plan.director_mode) == ("video", "i2v")


def test_the_final_render_of_a_shot_chained_by_continuation_continues_the_placed_take_of_the_previous_shot(core, make_project, slots):
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    project = _project(core, make_project, clips=[first, {**SHOTS[1], "stage": "draft"}], assets=[PLACED])
    source = takes.create_take(
        {"project_id": project["id"], "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-2", "file_id": "f-2", "preset_id": TWELVE, "seed": 7, "variant": "A", "profile": "FL2VA"}
    )
    user = core.users["user-1"]

    plan, _, _ = asyncio.run(generation.final_plan(user, project, source, generation.RENDER, "final"))
    take = generation.create_final(user, project, source, generation.RENDER, plan, TWELVE, 0.0)

    assert (plan.request["mode"], plan.chain, plan.quality) == ("extend", "s1", "final")
    assert take["chain"]["state"] == "waiting" and take["chain"]["after"] is None and take["chain"]["video"]["sound"] is True


def test_the_final_render_of_a_ref2va_shot_continues_the_placed_take_of_the_previous_shot(core, make_project, slots, monkeypatch):
    monkeypatch.setattr(sequence, "CEILING", 10**6)
    core.use_h3()
    core.add_media({"kind": "library", "item_id": "lib-face"}, "uploads/face.png", "image")
    face = {"id": "face", "kind": "image", "name": "face", "origin": {"kind": "library", "itemId": "lib-face"}}
    first = {**SHOTS[0], "assetId": PLACED["id"], "stage": "draft", "take": "t0"}
    project = make_project(
        clips=[first, {**SHOTS[1], "stage": "draft"}],
        assets=[PLACED, face],
        references=[{"id": "r-face", "assetId": "face", "space": "identite", "scope": {"type": "global"}}],
        direction={"mode": "Ref2VA"},
    )
    project["doc"]["chainBy"] = "video"
    source = takes.create_take(
        {"project_id": project["id"], "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-2", "file_id": "f-2", "preset_id": presets.MINIMAX_H3, "seed": 7, "variant": "A", "profile": "Ref2VA"}
    )
    user = core.users["user-1"]

    plan, _, _ = asyncio.run(generation.final_plan(user, project, source, generation.RENDER, "final"))
    take = generation.create_final(user, project, source, generation.RENDER, plan, presets.MINIMAX_H3, 0.0)

    assert plan.chain == "s1" and STAND_IN in plan.request["form_data"]["references"]
    assert take["chain"]["state"] == "waiting" and take["chain"]["video"]["sound"] is False


def test_the_starter_project_chains_by_the_last_image_and_keeps_the_words_of_its_cards():
    doc = json.loads((Path(__file__).resolve().parent / "fixtures" / "starter_lumi.json").read_text(encoding="utf-8"))

    assert "chainBy" not in doc and "cardWords" not in doc
    assert all("chainBy" not in clip and "cardWords" not in clip for clip in doc["clips"])
    assert [director.chain_by(doc, clip) for clip in doc["clips"]] == [director.FRAME_CHAIN] * len(doc["clips"])
    assert [bible.card_words(doc, clip) for clip in doc["clips"]] == [bible.CARD_WORDS] * len(doc["clips"])

@pytest.mark.parametrize("where", ["project", "shot"])
def test_a_document_may_chain_by_the_last_image_or_by_continuation_and_nothing_else(make_doc, where):
    doc = make_doc(clips=SHOTS)
    holder = doc if where == "project" else doc["clips"][1]
    for value in ("frame", "video"):
        holder["chainBy"] = value
        validate_doc(doc)
    holder["chainBy"] = "audio"

    with pytest.raises(DocError):
        validate_doc(doc)


def test_the_continue_mode_of_the_12_gb_preset_returns_the_new_footage_alone_from_the_fl2va_files():
    pipeline = yaml.safe_load((PRESET / "modes" / "extend" / "pipeline.yml").read_text(encoding="utf-8"))["pipeline"]
    manifest = yaml.safe_load((PRESET / "preset.yml").read_text(encoding="utf-8"))
    generation_tab = (PRESET / "modes" / "extend" / "tabs" / "generation.yml").read_text(encoding="utf-8")
    generator = next(step for step in pipeline if step["name"] == "generator/video_minimax_h3")
    gallery = next(step for step in pipeline if step["name"] == "gallery")
    fields = {field["name"]: field for field in yaml.safe_load(generation_tab)["fields"][1]["children"] if "name" in field}

    assert manifest["modes"][-1] == "extend" and "extend" not in manifest["vars"]["video_director"]["preset_modes"]
    assert generator["configuration"]["source_video_role"] == "continue" and generator["configuration"]["source_overlap_latents"] == 5
    assert generator["configuration"]["decode"] is True and "document" not in generator["configuration"]
    assert ["source_video", "source", "video"] in generator["input"]
    assert gallery["input"][0] == ["video", "generator", "video"]
    assert not any(step["name"] == "video_concat" for step in pipeline)
    assert fields["frames"]["configuration"]["max"] == director.MAX_CONTINUE_FRAMES
    assert "models_fl2va.yml" in generation_tab
