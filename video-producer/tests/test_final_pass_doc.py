import copy
import json
from pathlib import Path

import pytest

from backend.projects import DocError, migrate, validate_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES / "final_pass_migration.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    return json.loads((FIXTURES / "starter_doc.json").read_text(encoding="utf-8"))


def test_a_document_may_keep_the_choice_of_its_final_pass(starter):
    validate_doc({**starter, "finalPass": {"method": "guided", "target": "hd720", "upscaler": "seedvr2"}})
    validate_doc({**starter, "finalPass": {}})


@pytest.mark.parametrize(
    "value, path, reason",
    [
        ({"method": "remaster"}, "$.finalPass.method", "'remaster' is not one of"),
        ({"target": "8k"}, "$.finalPass.target", "'8k' is not one of"),
        ({"upscaler": "turbo"}, "$.finalPass.upscaler", "'turbo' is not one of"),
        ({"redo": True}, "$.finalPass", "Additional properties are not allowed"),
        ("upscale", "$.finalPass", "'upscale' is not of type 'object'"),
    ],
)
def test_the_schema_refuses_a_malformed_final_pass_choice(starter, value, path, reason):
    with pytest.raises(DocError) as caught:
        validate_doc({**starter, "finalPass": value})

    assert caught.value.code == "invalid_doc"
    assert str(caught.value).startswith(f"{path}: ")
    assert reason in str(caught.value)


@pytest.mark.parametrize("case", CASES, ids=[json.dumps(case["value"]) for case in CASES])
def test_migrating_keeps_the_known_values_of_the_final_pass_and_drops_the_key_when_none_is_left_as_the_page_does(starter, case):
    starter["finalPass"] = case["value"]
    before = copy.deepcopy(starter)

    migrated = migrate(starter)

    assert starter == before
    assert migrated.get("finalPass") == case["expected"]
    assert ("finalPass" in migrated) is (case["expected"] is not None)
    assert {key: item for key, item in migrated.items() if key != "finalPass"} == {key: item for key, item in starter.items() if key != "finalPass"}
    validate_doc(migrated)
    assert migrate(migrated) is migrated
