import json
from pathlib import Path

import pytest

from backend import keepframing, presets
from backend.projects import DocError, validate_doc

from .test_director import SHOT, _frame, _images, _plans, _wan_tier

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PAGE_TABLE = PLUGIN_ROOT / "frontend" / "src" / "lib" / "keepframingtable.js"
WALK = "The fisherman walks slowly along the stone quay toward the lighthouse, then stops and looks at the boats."
IN_PLACE = "The fisherman stands still on the stone quay, turns his head to look at the boats moored on the right, then turns back toward the camera. He stays where he is."


def _prompt(text):
    return {"id": "p1", "shotId": "s1", "start": 0, "dur": 4, "strength": 75, "text": text}


def _codes(plans):
    return [warning["code"] for warning in plans.warnings]


@pytest.mark.parametrize(
    "text, moving",
    [
        (WALK, True),
        (IN_PLACE, False),
        ("She steps forward and smiles.", True),
        ("The dog comes closer to the camera.", True),
        ("He crosses the street.", True),
        ("He turns his head toward the boats.", False),
        ("She looks toward the lighthouse, then faces the camera.", False),
        ("", False),
        (None, False),
    ],
)
def test_an_instruction_asks_for_a_move_with_a_verb_of_moving_or_a_verb_and_a_direction(text, moving):
    assert keepframing.moves(text) is moving


def test_the_page_reads_an_identical_copy_of_the_words_of_moving():
    text = PAGE_TABLE.read_text(encoding="utf-8").strip()
    assert text.startswith("export default ") and text.endswith(";")
    assert json.loads(text[len("export default ") : -1]) == keepframing.load_table()


def test_a_shot_that_keeps_its_framing_sends_its_first_frame_as_its_last_too(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[{**SHOT, "keepFraming": True}], frames=[_frame("f1", "a", "first")], assets=_images(core))

    plans = _plans(core, doc)

    (plan,) = plans.shots
    media = plan.request["form_data"]["video_director"]["media"]
    assert plan.director_mode == "flf"
    assert [(entry["role"], entry["media"]["path"]) for entry in media] == [
        ("first", "generations/2026-10-17/g-a/1.png"),
        ("last", "generations/2026-10-17/g-a/1.png"),
    ]
    assert plans.warnings == []
    assert len(doc["frames"]) == 1


def test_without_the_option_a_first_frame_alone_stays_image_to_video(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[{**SHOT, "keepFraming": False}], frames=[_frame("f1", "a", "first")], assets=_images(core))

    (plan,) = _plans(core, doc).shots

    assert plan.director_mode == "i2v"


def test_a_last_frame_of_its_own_is_sent_and_said_instead_of_the_first(core, make_doc):
    core.use_wan()
    frames = [_frame("f1", "a", "first"), _frame("f2", "b", "last", time=4)]
    doc = make_doc(clips=[{**SHOT, "keepFraming": True}], frames=frames, assets=_images(core))

    plans = _plans(core, doc)

    media = plans.shots[0].request["form_data"]["video_director"]["media"]
    assert [entry["media"]["path"] for entry in media] == ["generations/2026-10-17/g-a/1.png", "generations/2026-10-17/g-b/2.png"]
    assert _codes(plans) == ["keep_framing_last_frame"]


def test_an_engine_without_a_last_frame_says_the_framing_is_not_kept(core, make_doc):
    preset_id = _wan_tier(core, modes={"t2v": {}, "i2v": {}})
    doc = make_doc(clips=[{**SHOT, "keepFraming": True}], frames=[_frame("f1", "a", "first")], assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id)

    assert plans.shots[0].director_mode == "i2v"
    assert "keep_framing_unavailable" in _codes(plans)


def test_a_cloud_model_keeps_the_framing_only_when_it_takes_a_last_frame(core, make_doc):
    doc = make_doc(clips=[{**SHOT, "keepFraming": True}], frames=[_frame("f1", "a", "first")], assets=_images(core))
    core.use_openrouter()
    with_last = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")
    core.use_openrouter(core.model_spec(last_frame=False))
    without_last = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert with_last.shots[0].director_mode == "flf" and "keep_framing_unavailable" not in _codes(with_last)
    assert without_last.shots[0].director_mode == "i2v" and "keep_framing_unavailable" in _codes(without_last)


@pytest.mark.parametrize(
    "keep, last, text, warned",
    [
        (True, None, WALK, True),
        (True, None, IN_PLACE, False),
        (False, "a", WALK, True),
        (False, "a", IN_PLACE, False),
        (False, "b", WALK, False),
        (True, "b", WALK, False),
    ],
    ids=["kept-and-walking", "kept-and-in-place", "same-last-and-walking", "same-last-in-place", "other-last-and-walking", "own-last-and-walking"],
)
def test_an_action_that_moves_is_said_to_be_undone_by_a_last_frame_that_is_the_first(core, make_doc, keep, last, text, warned):
    core.use_wan()
    frames = [_frame("f1", "a", "first")] + ([_frame("f2", last, "last", time=4)] if last else [])
    clip = {**SHOT, "keepFraming": True} if keep else dict(SHOT)
    doc = make_doc(clips=[clip], frames=frames, prompts=[_prompt(text)], assets=_images(core))

    plans = _plans(core, doc)

    assert ("action_undone" in _codes(plans)) is warned


def test_the_document_keeps_the_option_as_a_boolean(make_doc):
    validate_doc(make_doc(clips=[{**SHOT, "keepFraming": True}]))
    validate_doc(make_doc(clips=[{**SHOT, "keepFraming": False}]))
    with pytest.raises(DocError):
        validate_doc(make_doc(clips=[{**SHOT, "keepFraming": "yes"}]))
