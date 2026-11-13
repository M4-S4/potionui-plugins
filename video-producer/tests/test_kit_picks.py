import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from backend.director import media_ref
from backend.projects import DocError, canonical, migrate, validate_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PICKS = json.loads((FIXTURES / "kit_picks.json").read_text(encoding="utf-8"))
EMPTY = json.loads((FIXTURES / "empty_doc.json").read_text(encoding="utf-8"))


def _accepted(kits, allowed):
    seen = set()
    refs = []
    for kit in kits:
        for item in sorted(kit["items"], key=lambda entry: entry["position"]):
            if item["kind"] == "text" or item["missing"] or not item["media_ref"] or item["kind"] not in allowed:
                continue
            if item["media_ref"] in seen:
                continue
            seen.add(item["media_ref"])
            refs.append((item["kind"], item["media_ref"]))
    return refs


def _doc(assets):
    doc = copy.deepcopy(EMPTY)
    doc["assets"] = copy.deepcopy(assets)
    return doc


def test_the_fixture_covers_full_and_empty_kits_every_kind_deleted_files_repeated_names_one_file_in_two_items_of_a_kit_and_one_file_in_two_kits():
    cases = PICKS["cases"]
    kits = [kit for case in cases for kit in case["kits"]]
    assert len(cases) == 8
    assert max(len(kit["items"]) for kit in kits) == 50 and min(len(kit["items"]) for kit in kits) == 0
    items = [item for kit in kits for item in kit["items"]]
    assert {item["kind"] for item in items} == {"image", "video", "audio", "text"}
    assert any(item["missing"] and item["media_ref"] is None for item in items)
    assert any(max(Counter(item["name"] for item in kit["items"]).values(), default=0) > 1 for kit in kits)
    assert any(max(Counter(item["media_ref"] for item in kit["items"] if item["media_ref"]).values(), default=0) > 1 for kit in kits)
    two = [case for case in cases if len(case["kits"]) == 2]
    assert two and set.intersection(*({item["media_ref"] for item in kit["items"] if item["media_ref"]} for kit in two[0]["kits"]))


@pytest.mark.parametrize("index", range(len(PICKS["cases"])))
def test_a_whole_kit_enters_the_project_as_its_accepted_media_in_kit_order_and_the_document_stays_valid(index):
    case = PICKS["cases"][index]
    doc = _doc(case["assets"])

    assert validate_doc(doc) == canonical(doc)
    assert migrate(copy.deepcopy(doc)) == doc
    assert [(asset["kind"], asset["origin"]["itemId"]) for asset in doc["assets"]] == _accepted(case["kits"], case["allowed"])
    assert all(asset["origin"] == {"kind": "library", "itemId": asset["origin"]["itemId"]} for asset in doc["assets"])
    assert all(media_ref(asset["origin"]) == {"kind": "library", "item_id": asset["origin"]["itemId"]} for asset in doc["assets"])
    assert all((asset["fps"] is not None) == (asset["kind"] == "video") for asset in doc["assets"])
    assert case["left"]["text"] == sum(1 for kit in case["kits"] for item in kit["items"] if item["kind"] == "text")


def test_an_asset_that_kept_the_kit_origin_would_be_refused_by_the_server_schema():
    case = next(case for case in PICKS["cases"] if case["assets"])
    doc = _doc(case["assets"])
    item = next(item for kit in case["kits"] for item in kit["items"] if item["media_ref"])
    doc["assets"][0]["origin"] = {"kind": "kit", "kitId": item["kit_id"], "itemId": item["id"]}

    with pytest.raises(DocError):
        validate_doc(doc)
