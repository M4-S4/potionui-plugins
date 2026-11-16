import asyncio

import pytest

from backend import director, estimate, presets
from backend.estimate import Order

from .test_frame_crop import PROMPTS, SHOT, SHOTS, _frame, pictures

LARGE = "frame_cropped_large"


def _plans(core, doc, preset_id, **options):
    return director.build_plans(core.users["user-1"], doc, ["s1"], preset_id, "draft", **options)


def _doc(make_doc, assets, frames, clips=(SHOT,), **parts):
    return make_doc(clips=list(clips), prompts=PROMPTS, frames=frames, assets=assets, **parts)


def _crops(plans):
    return [warning for warning in plans.warnings if warning["code"].startswith("frame_cropped")]


def test_a_start_image_a_crop_cuts_by_more_than_the_film_shows_without_a_word_is_a_warning_with_the_share_it_loses(core, make_doc, pictures):
    core.use_h3_12gb()
    doc = _doc(make_doc, [pictures.add("four-three", (1024, 768))], [_frame("f1", "four-three", "first")])

    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == [
        {
            "code": "frame_cropped",
            "message": "The start image of the shot is 1024x768, not 16:9: it is cropped at its centre (23 % of the picture).",
            "data": {"shot_id": "s1", "roles": ["first"], "size": "1024x768", "aspect": "16:9", "loss": 23, "chained": False},
        }
    ]


def test_a_crop_past_the_share_the_film_crops_before_bars_is_the_strong_warning_that_asks_for_a_start_image_in_the_frame(core, make_doc, pictures):
    core.use_h3_12gb()
    doc = _doc(make_doc, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == [
        {
            "code": LARGE,
            "message": "The start image of the shot is 1024x1024, not 16:9: it is cropped at its centre and loses 42 % of the picture. Make a start image in the frame of the film instead.",
            "data": {"shot_id": "s1", "roles": ["first"], "size": "1024x1024", "aspect": "16:9", "loss": 42, "chained": False},
        }
    ]


@pytest.mark.parametrize("size", [(1280, 720), (1344, 768), (832, 480)])
def test_a_crop_the_film_would_make_without_a_word_says_nothing(core, make_doc, pictures, size):
    core.use_h3_12gb()
    doc = _doc(make_doc, [pictures.add("wide", size)], [_frame("f1", "wide", "first")])

    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == []


def test_each_image_of_a_first_and_last_image_shot_gets_its_own_warning(core, make_doc, pictures):
    core.use_h3_12gb()
    assets = [pictures.add("four-three", (1024, 768)), pictures.add("portrait", (768, 1152))]
    doc = _doc(make_doc, assets, [_frame("f1", "four-three", "first"), _frame("f2", "portrait", "last", 4)])

    found = _crops(_plans(core, doc, presets.MINIMAX_H3_12GB))

    assert [(item["code"], item["data"]["roles"], item["data"]["loss"]) for item in found] == [("frame_cropped", ["first"], 23), (LARGE, ["last"], 62)]
    assert found[1]["message"].startswith("The end image of the shot is 768x1152, not 16:9")


def test_the_size_the_file_declares_wins_over_the_size_the_project_recorded(core, make_doc, pictures):
    core.use_h3_12gb()
    asset = {**pictures.add("turned", (768, 1024)), "width": 1024, "height": 768}
    doc = _doc(make_doc, [asset], [_frame("f1", "turned", "first")])

    (warning,) = _crops(_plans(core, doc, presets.MINIMAX_H3_12GB))

    assert warning["data"]["size"] == "768x1024"


def test_without_a_file_here_the_size_the_project_recorded_is_used_and_without_either_nothing_is_said(core, make_doc, pictures):
    core.use_h3_12gb()
    core.add_media({"kind": "library", "item_id": "lib-far"}, "uploads/far.png", "image")
    far = {"id": "far", "kind": "image", "name": "far.png", "origin": {"kind": "library", "itemId": "lib-far"}, "width": 1024, "height": 1024}
    doc = _doc(make_doc, [far], [_frame("f1", "far", "first")])

    assert [item["data"]["size"] for item in _crops(_plans(core, doc, presets.MINIMAX_H3_12GB))] == ["1024x1024"]
    doc["assets"][0].update(width=None, height=None)
    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == []


def test_a_wan_shot_of_a_vertical_film_says_how_much_of_a_landscape_image_it_loses(core, make_doc, pictures):
    core.use_wan()
    doc = _doc(make_doc, [pictures.add("landscape", (1280, 720))], [_frame("f1", "landscape", "first")], aspect="9:16")

    (warning,) = _crops(_plans(core, doc, presets.WAN))

    assert (warning["code"], warning["data"]["aspect"], warning["data"]["loss"]) == (LARGE, "9:16", 68)


def test_a_cloud_shot_measures_its_image_against_the_aspect_ratio_it_sends(core, make_doc, pictures):
    core.use_openrouter()
    doc = _doc(make_doc, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    (warning,) = _crops(_plans(core, doc, presets.OPENROUTER_VIDEO, model_id="cm-veo"))

    assert (warning["code"], warning["data"]["aspect"], warning["data"]["loss"]) == (LARGE, "16:9", 44)


def test_a_shot_that_starts_from_the_last_image_of_an_imported_video_in_another_ratio_says_so(core, make_doc, pictures):
    core.use_wan()
    phone = {"id": "phone", "kind": "video", "name": "phone.mp4", "origin": {"kind": "library", "itemId": "lib-phone"}, "width": 1080, "height": 1920, "srcDur": 6.0}
    clips = [{**SHOTS[0], "assetId": "phone"}, SHOTS[1]]
    doc = make_doc(clips=clips, prompts=PROMPTS, assets=[phone])

    plans = director.build_plans(core.users["user-1"], doc, ["s2"], presets.WAN, "draft", chained={"s2": director.Chain("s1")})

    (warning,) = _crops(plans)
    assert warning["code"] == LARGE and warning["data"] == {"shot_id": "s2", "roles": ["first"], "size": "1080x1920", "aspect": "16:9", "loss": 68, "chained": True}
    assert warning["message"].startswith("The last image of the previous shot is 1080x1920, not 16:9")


def test_the_estimate_carries_the_warning_before_generate(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = make_project(doc=_doc(make_doc, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")]))
    user = core.users["user-1"]

    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.MINIMAX_H3_12GB)))

    assert [warning["code"] for warning in evaluation.payload["warnings"] if warning["code"].startswith("frame_")] == [LARGE]
    assert evaluation.payload["blocks"] == []


def test_a_large_crop_of_an_end_image_asks_for_an_end_image(core, make_doc, pictures):
    core.use_h3_12gb()
    assets = [pictures.add("exact", (832, 480)), pictures.add("square", (1024, 1024))]
    doc = _doc(make_doc, assets, [_frame("f1", "exact", "first"), _frame("f2", "square", "last", 4)])

    (warning,) = _crops(_plans(core, doc, presets.MINIMAX_H3_12GB))

    assert warning["data"]["roles"] == ["last"] and warning["message"].endswith("Make an end image in the frame of the film instead.")


def test_a_file_here_that_cannot_be_read_is_sent_as_it_is_and_gets_no_crop_warning(core, make_doc, pictures):
    core.use_h3_12gb()
    asset = pictures.add("drawing", (1024, 1024))
    pictures.files[(("item_id", "lib-drawing"), ("kind", "library"))].write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"/>', encoding="utf-8")
    doc = _doc(make_doc, [asset], [_frame("f1", "drawing", "first")])

    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == []


def test_a_picture_too_small_to_crop_within_the_tolerance_gets_no_crop_warning(core, make_doc, pictures):
    core.use_h3_12gb()
    doc = _doc(make_doc, [pictures.add("tiny", (31, 31))], [_frame("f1", "tiny", "first")])

    assert _crops(_plans(core, doc, presets.MINIMAX_H3_12GB)) == []


def test_a_picture_past_the_pixel_ceiling_is_said_to_be_sent_as_it_is_before_generate(core, make_doc, pictures, monkeypatch):
    from backend import framefit

    core.use_h3_12gb()
    monkeypatch.setattr(framefit, "MAX_PIXELS", 1_000_000)
    doc = _doc(make_doc, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    plans = _plans(core, doc, presets.MINIMAX_H3_12GB)

    assert _crops(plans) == []
    assert [warning for warning in plans.warnings if warning["code"] == "frame_not_cropped"] == [
        {
            "code": "frame_not_cropped",
            "message": "The start image of the shot is sent as it is, not cropped to the frame of the take: it has more than 64 million pixels.",
            "data": {"shot_id": "s1", "cause": "too_many_pixels", "roles": ["first"], "chained": False},
        }
    ]
