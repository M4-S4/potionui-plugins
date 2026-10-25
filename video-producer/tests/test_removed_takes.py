import copy
import json
from pathlib import Path

import pytest

from backend.projects import DocError, migrate, validate_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES / "removed_takes_migration.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    return json.loads((FIXTURES / "starter_doc.json").read_text(encoding="utf-8"))


def _error(doc):
    with pytest.raises(DocError) as caught:
        validate_doc(doc)
    return caught.value


def test_a_document_may_list_the_takes_whose_video_the_user_removed(starter):
    starter["removedTakes"] = ["01KX9TAKE00000000000000001", "01KX9TAKE00000000000000002"]

    validate_doc(starter)
    validate_doc({**starter, "removedTakes": []})


@pytest.mark.parametrize(
    "value, path, reason",
    [
        (["t1", "t1"], "$.removedTakes", "has non-unique elements"),
        (["t1", ""], "$.removedTakes[1]", "should be non-empty"),
        (["t1", 7], "$.removedTakes[1]", "7 is not of type 'string'"),
        ("t1", "$.removedTakes", "'t1' is not of type 'array'"),
        (None, "$.removedTakes", "None is not of type 'array'"),
    ],
)
def test_the_schema_refuses_a_malformed_list_of_removed_takes(starter, value, path, reason):
    starter["removedTakes"] = value

    error = _error(starter)

    assert error.code == "invalid_doc"
    assert str(error).startswith(f"{path}: ")
    assert reason in str(error)


def test_migrating_leaves_a_document_with_or_without_removed_takes_as_it_is(starter):
    assert migrate(starter) is starter
    removed = {**starter, "removedTakes": ["t1", "t2"]}
    assert migrate(removed) is removed


@pytest.mark.parametrize("case", CASES, ids=[json.dumps(case["value"]) for case in CASES])
def test_migrating_keeps_the_removed_takes_as_distinct_ids_and_drops_the_key_when_none_is_left_as_the_page_does(starter, case):
    starter["removedTakes"] = case["value"]
    before = copy.deepcopy(starter)

    migrated = migrate(starter)

    assert starter == before
    assert migrated.get("removedTakes") == case["expected"]
    assert ("removedTakes" in migrated) is (case["expected"] is not None)
    assert {key: item for key, item in migrated.items() if key != "removedTakes"} == {key: item for key, item in starter.items() if key != "removedTakes"}
    assert migrated["clips"] is starter["clips"]
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_a_project_keeps_its_removed_takes_when_it_is_created_saved_and_read(project_db, store, starter):
    from backend import projects

    starter["removedTakes"] = ["t1"]
    created = projects.create_project("user-1", starter)
    assert created["doc"]["removedTakes"] == ["t1"]

    starter["removedTakes"] = ["t1", "t2", "t1"]
    saved = projects.save_project(created["id"], starter, created["version"])
    assert saved["version"] == 2
    assert projects.get_project(created["id"])["doc"]["removedTakes"] == ["t1", "t2"]

    starter["removedTakes"] = []
    saved = projects.save_project(created["id"], starter, saved["version"])
    stored = projects.get_project(created["id"])["doc"]
    assert saved["version"] == 3
    assert "removedTakes" not in stored

    unchanged = projects.save_project(created["id"], {**stored, "removedTakes": []}, saved["version"])
    assert unchanged["unchanged"] is True
