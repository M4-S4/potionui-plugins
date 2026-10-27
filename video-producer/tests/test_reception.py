import copy
import json
from pathlib import Path

import pytest

from backend import bible, catalog, director, reception

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PAGE_TABLE = PLUGIN_ROOT / "frontend" / "src" / "lib" / "reception.json"
SHARED = json.loads((Path(__file__).parent / "fixtures" / "reception_cases.json").read_text(encoding="utf-8"))
ME_URL = "/api/plugins/video-producer/me"


def _prompts_url(project_id):
    return f"/api/plugins/video-producer/projects/{project_id}/prompts"


def _engines(core):
    core.use_wan()
    core.use_ltx25()
    core.use_h3()
    core.use_openrouter()


def test_the_page_reads_an_identical_copy_of_the_table():
    assert json.loads(PAGE_TABLE.read_text(encoding="utf-8")) == reception.load_table()


def test_the_table_names_kinds_profiles_layouts_and_families_the_plugin_knows():
    table = reception.TABLE

    assert set(table["limits"]) == set(director.LABELS)
    assert set(table["references"]) <= set(catalog.PROFILES)
    assert {rule["layout"] for rule in table["layouts"]} <= set(bible.LAYOUTS)
    assert {family for rule in table["layouts"] for family in rule.get("families", ())} <= {bible.H3, bible.CLOUD}
    assert set(table["layouts"][-1]) == {"layout"}
    assert director.REFERENCE_LIMITS == reception.LIMITS


def test_each_engine_writes_the_part_made_from_its_references_in_the_layout_of_the_table():
    assert reception.layout(bible.H3, catalog.REF2VA) == bible.REFS_LAYOUT
    assert {reception.layout(bible.H3, profile) for profile in (None, catalog.FL2VA, catalog.HYBRID_AV)} == {bible.SUBJECTS_LAYOUT}
    assert {
        reception.layout(family, profile)
        for family in (bible.WAN, bible.LTX, bible.CLOUD, bible.OTHER)
        for profile in (None, catalog.FL2VA, catalog.HYBRID_AV)
    } == {bible.CAST_LAYOUT}
    assert [profile for profile in catalog.PROFILES if reception.takes_references(profile)] == [catalog.REF2VA]


def test_the_engines_of_the_shared_cases_are_what_the_page_reads_from_me(core, client):
    _engines(core)

    presets = {item["id"]: item for item in client.get(ME_URL).json()["data"]["presets"]}

    for engine in SHARED["engines"].values():
        item = presets[engine["preset"]]
        assert (item["engine"] == "cloud", item["audio_mux"], item["profiles"]) == (engine["cloud"], engine["audio_mux"], engine["profiles"])


def _doc(make_doc, source):
    doc = make_doc(clips=source["clips"], assets=source["assets"], references=source["references"], direction=source["direction"])
    doc["engine"].update(source["engine"])
    if "bible" in source:
        doc["bible"] = copy.deepcopy(source["bible"])
    return doc


def _media(core, doc):
    values = {}
    for asset in doc["assets"]:
        origin = asset.get("origin")
        if origin:
            values[asset["id"]] = f"uploads/{origin['itemId']}"
            core.add_media({"kind": "library", "item_id": origin["itemId"]}, values[asset["id"]], asset["kind"])
    return values


def _received(doc, shot_id, composed, plan, values):
    excluded = director.excluded_references(doc, shot_id)
    own = [ref for ref in doc["references"] if (ref.get("scope") or {}).get("shotId") == shot_id]
    shared = [ref for ref in doc["references"] if (ref.get("scope") or {}).get("type") != "shot"]
    kept = [ref for ref in doc["references"] if ref in own or (ref in shared and ref["id"] not in excluded)]
    sent = plan.request["form_data"].get("references") or []
    guided = plan.director_mode == catalog.REFS_MODE
    mixed = plan.audio.references if plan.audio is not None and plan.audio.behavior == director.MUX else []
    return {
        "layout": composed["reference"]["layout"],
        "ignoredLayout": any(item["code"] == "reference_prompt_ignored" for item in composed["warnings"]),
        "sent": [ref["id"] for ref in kept if values.get(ref["assetId"]) in sent],
        "trimmed": [ref["id"] for ref in kept if guided and ref["assetId"] in values and values[ref["assetId"]] not in sent],
        "mixed": [ref["id"] for ref in kept if ref["assetId"] in mixed],
        "excluded": [ref["id"] for ref in shared if ref["id"] in excluded],
    }


@pytest.mark.parametrize("case", SHARED["cases"], ids=[case["name"] for case in SHARED["cases"]])
def test_what_each_shot_receives_matches_the_cases_the_page_is_tested_on(core, client, make_doc, make_project, case):
    _engines(core)
    doc = _doc(make_doc, case["doc"])
    values = _media(core, doc)
    engine = doc["engine"]
    shots = [clip["id"] for clip in doc["clips"]]
    project = make_project(doc=doc)

    response = client.post(_prompts_url(project["id"]), json={"shots": shots, "preset_id": engine["preset"], "model_id": engine.get("model"), "doc": doc})
    plans = director.build_plans(core.users["user-1"], doc, shots, engine["preset"], "draft", engine.get("model"), overrides=True)

    data = response.json()["data"]
    composed = {item["shot_id"]: item for item in data["prompts"]}
    planned = {plan.shot_id: plan for plan in plans.shots}
    blocked = {shot_id for block in data["blocks"] for shot_id in (block.get("data") or {}).get("shot_ids", [])}
    found = {
        shot_id: _received(doc, shot_id, composed[shot_id], planned[shot_id], values) if shot_id in composed else {"blocked": shot_id in blocked}
        for shot_id in shots
    }
    assert found == case["expected"]
    assert set(composed) == set(planned)
