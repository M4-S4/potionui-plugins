import asyncio

from backend import estimate, generation, presets, reception
from backend.estimate import Order

from .conftest import cloud_model
from .test_frame_crop import _frame, _paths, _project, pictures
from .test_sheet import _doc, _media, _plans


def _estimate(core, project, preset_id, quality="draft", **fields):
    user = core.users["user-1"]
    order = Order(shots=["s1"], quality=quality, variants=1, preset_id=preset_id, **fields)
    return asyncio.run(estimate.evaluate(user, user, project["doc"], order))


def _frames(evaluation):
    return [shot["frame"] for shot in evaluation.payload["shots"]]


def test_the_estimate_gives_each_shot_the_ratio_of_the_take_its_images_are_cropped_to(core, make_doc, make_project, pictures):
    core.use_wan()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], aspect="2.39:1")

    evaluation = _estimate(core, project, presets.WAN)
    asyncio.run(generation.start(core.users["user-1"], project, evaluation))

    assert _frames(evaluation) == [[26, 15]]
    assert evaluation.payload["shots"][0]["resolution"] == "832x480"
    assert _paths(core.submitted[0][1]) == [("first", "uploads/stored-1-square-crop-1024x590.png")]


def test_the_ratio_of_a_final_take_is_the_one_of_its_final_size(core, make_doc, make_project, pictures):
    core.use_wan()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], aspect="2.39:1")

    evaluation = _estimate(core, project, presets.WAN, quality="final")

    assert evaluation.payload["shots"][0]["resolution"] == "1280x720"
    assert _frames(evaluation) == [[16, 9]]


def test_a_minimax_h3_draft_of_a_scope_film_has_the_ratio_of_its_draft_size(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], aspect="2.39:1")

    evaluation = _estimate(core, project, presets.MINIMAX_H3_12GB)

    assert evaluation.payload["shots"][0]["resolution"] == "960x416"
    assert _frames(evaluation) == [[30, 13]]


def test_a_cloud_shot_has_the_ratio_of_the_aspect_ratio_it_sends(core, make_doc, make_project, pictures):
    core.use_openrouter()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], aspect="2.39:1")

    evaluation = _estimate(core, project, presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert _frames(evaluation) == [[16, 9]]


def test_a_shot_with_its_own_engine_has_the_ratio_of_the_take_of_that_engine(core, make_doc, make_project, pictures):
    core.use_wan()
    core.use_h3_12gb()
    clips = [{"id": "s1", "start": 0, "dur": 4, "engine": {"preset": presets.MINIMAX_H3_12GB}}, {"id": "s2", "start": 4, "dur": 4, "firstFromPrevious": False}]
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], clips=clips, aspect="2.39:1")
    user = core.users["user-1"]
    order = Order(shots=["s1", "s2"], quality="draft", variants=1, preset_id=presets.WAN)

    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))

    assert [(shot["shot_id"], shot["resolution"], shot["frame"]) for shot in evaluation.payload["shots"]] == [("s1", "960x416", [30, 13]), ("s2", "832x480", [26, 15])]


def test_a_take_with_neither_a_size_nor_an_aspect_ratio_has_no_frame(core, make_doc, make_project, pictures):
    model = cloud_model()
    model["params"] = [param for param in model["params"] if param["name"] != "aspect_ratio"]
    core.use_openrouter(model)
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], aspect="2.39:1")

    evaluation = _estimate(core, project, presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert evaluation.payload["shots"][0]["resolution"] == "720p"
    assert _frames(evaluation) == [None]


def test_a_ref2va_shot_of_ltx_2_5_has_the_ratio_of_its_reference_sheet_take(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc)
    doc["aspect"] = "4:3"

    (plan,) = _plans(core, doc).shots

    assert reception.sheet_size(4 / 3) == (672, 512)
    assert (plan.preset_mode, plan.resolution, plan.summary()["frame"]) == ("video", "672x512", [21, 16])
