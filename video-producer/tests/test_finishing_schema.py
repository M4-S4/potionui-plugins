import copy
import json
from pathlib import Path

import pytest

from backend.projects import DocError, canonical, validate_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"

FINISHING = {
    "fixColors": {"on": True, "strength": 80},
    "lut": {"on": False, "ref": "warm.cube", "strength": 0.5},
    "look": {"on": True, "ref": "mine:01M77", "strength": 1},
    "vignette": {"on": True, "amount": 40, "radius": 50},
    "grain": {"on": True, "amount": 30, "size": 1.5},
}


@pytest.fixture
def starter():
    return json.loads((FIXTURES / "starter_doc.json").read_text(encoding="utf-8"))


def _with(doc, finishing):
    out = copy.deepcopy(doc)
    out["master"]["finishing"] = finishing
    return out


def test_a_project_without_finishing_is_valid_as_before(starter):
    assert "finishing" not in starter["master"]
    assert validate_doc(starter) == canonical(starter)


def test_the_finishing_choices_are_kept_in_the_master_of_the_project(starter):
    doc = _with(starter, FINISHING)

    assert json.loads(validate_doc(doc))["master"]["finishing"] == FINISHING


def test_an_empty_finishing_and_an_effect_with_its_switch_only_are_valid(starter):
    validate_doc(_with(starter, {}))
    validate_doc(_with(starter, {"grain": {"on": False}}))


@pytest.mark.parametrize(
    "finishing",
    [
        {"blur": {"on": True}},
        {"grain": {"amount": 30}},
        {"grain": {"on": True, "amount": 101}},
        {"grain": {"on": True, "size": 0.5}},
        {"lut": {"on": True, "strength": 1.5}},
        {"vignette": {"on": True, "softness": 20}},
        {"look": {"on": "yes"}},
    ],
)
def test_an_unknown_effect_field_or_an_out_of_range_value_is_refused(starter, finishing):
    with pytest.raises(DocError):
        validate_doc(_with(starter, finishing))
