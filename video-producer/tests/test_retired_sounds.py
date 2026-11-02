import copy
import json
from pathlib import Path

import pytest

from backend.projects import DocError, RETIRED_ASSET_KEYS, migrate, validate_doc, workshop_sound

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASE = json.loads((FIXTURES / "retired_sound_migration.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    return json.loads((FIXTURES / "starter_doc.json").read_text(encoding="utf-8"))


def _old(starter):
    doc = copy.deepcopy(starter)
    part = copy.deepcopy(CASE["doc"])
    doc["assets"], doc["audio"], doc["references"] = part["assets"], part["audio"], part["references"]
    for lane, mode in zip(doc["lanes"], part["laneModes"]):
        lane["automation"] = mode
    return doc


def test_an_older_document_with_sound_design_workshop_sounds_is_refused_until_migrated(starter):
    old = _old(starter)

    with pytest.raises(DocError):
        validate_doc(old)

    validate_doc(migrate(old))


def test_migrating_drops_the_workshop_sounds_with_their_items_and_leaves_their_references_without_media_as_the_page_does(starter):
    old = _old(starter)
    before = copy.deepcopy(old)

    migrated = migrate(old)

    assert old == before
    assert [asset["id"] for asset in migrated["assets"]] == CASE["expected"]["assets"]
    assert [item["id"] for item in migrated["audio"]] == CASE["expected"]["audio"]
    assert {reference["id"]: reference["assetId"] for reference in migrated["references"]} == CASE["expected"]["references"]
    assert not any(key in asset for asset in migrated["assets"] for key in RETIRED_ASSET_KEYS)
    assert not any("automation" in lane for lane in migrated["lanes"])
    assert migrated["clips"] is old["clips"]
    assert migrate(migrated) is migrated


def test_only_a_sound_with_a_synthesis_and_no_file_is_a_workshop_sound():
    assets = {asset["id"]: asset for asset in CASE["doc"]["assets"]}

    assert [asset_id for asset_id, asset in assets.items() if workshop_sound(asset)] == ["workshop-voice", "workshop-wind"]
    assert not workshop_sound({**assets["workshop-wind"], "src": "/api/media/uploads/wind.wav"})
    assert not workshop_sound(None)


def test_a_current_document_is_left_as_it_is(starter):
    assert migrate(starter) is starter
