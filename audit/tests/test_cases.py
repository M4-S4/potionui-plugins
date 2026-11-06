import json

import pytest

from potion_audit.cases import ZERO_SHA, CaseFileError, build_case_set, load_cases, model_fields_of
from potion_audit.config import DEFAULT_CASES

from conftest import MISSING_SHA, SDXL_SHA, WAN_DIT_SHA, WAN_ID, WAN_VAE_SHA, sample_case_set_data


def wan_models(data: dict) -> dict:
    case = next(case for case in data["cases"] if case["name"] == "wan-t2v")
    return {model["field"]: model for model in case["models"]}


def preset(key: str, preset_id: str, models: dict, model_fields: dict) -> dict:
    return {
        "key": key,
        "path": f"content/presets/marketplace/{key}",
        "origin": "core",
        "preset": {"id": preset_id, "name": key, "version": "1"},
        "modes": ["video"],
        "tests": {"cases": [{"name": "c", "mode": "video", "models": models}]},
        "model_fields": model_fields,
    }


def recipe(artifacts: list[dict], preset_id: str = WAN_ID, recipe_id: str = "r") -> dict:
    return {"path": f"content/recipes/marketplace/{recipe_id}.yml", "recipe": {"id": recipe_id, "presets": [{"preset_id": preset_id}], "artifacts": artifacts}}


def artifact(artifact_id: str, filename: str, model_type: str, sha: str | None, size: int) -> dict:
    return {"id": artifact_id, "filename": filename, "model_type": model_type, "size_bytes": size, "checksum": {"algorithm": "sha256", "value": sha}}


def test_a_zero_sha_takes_the_recipe_sha_the_form_recommends():
    model = wan_models(sample_case_set_data())["t2v_high_noise_model"]
    assert model["sha256"] == WAN_DIT_SHA
    assert model["size_bytes"] == 5000
    assert model["source"] == "recipe:wan-starter/wan-dit-high"


def test_a_nonzero_sha_gets_its_size_and_file_from_any_recipe():
    models = wan_models(sample_case_set_data())
    assert models["vae"]["sha256"] == WAN_VAE_SHA
    assert models["vae"]["size_bytes"] == 200
    assert models["text_encoder"]["filename"] == "umt5.safetensors"
    assert models["vae"]["source"] == "tests.yml"


def test_a_zero_sha_matches_an_artifact_by_the_words_of_its_field():
    data = build_case_set("r", "x", [preset("P", WAN_ID, {"low_noise_model": {"sha256": ZERO_SHA}}, {})], [recipe([
        artifact("dit-high", "wan_high_noise.safetensors", "diffusion_model", "1" * 64, 10),
        artifact("dit-low", "wan_low_noise.safetensors", "diffusion_model", "2" * 64, 20),
    ])])
    assert data["cases"][0]["models"][0]["sha256"] == "2" * 64


def test_an_ambiguous_zero_sha_stays_unresolved():
    data = build_case_set("r", "x", [preset("P", WAN_ID, {"high_noise_model": {"sha256": ZERO_SHA}}, {})], [recipe([
        artifact("t2v-high", "wan_t2v_high_noise.safetensors", "diffusion_model", "1" * 64, 10),
        artifact("i2v-high", "wan_i2v_high_noise.safetensors", "diffusion_model", "2" * 64, 20),
    ])])
    model = data["cases"][0]["models"][0]
    assert model["sha256"] == ZERO_SHA
    assert model["source"] == "unresolved"
    assert data["cases"][0]["undeclared_model_fields"] == []


def test_a_recipe_without_sha_gives_file_and_size_but_stays_unresolved():
    data = build_case_set("r", "x", [preset("P", WAN_ID, {"model": {"sha256": ZERO_SHA}}, {"model": {"model_type": "diffusion_model", "recommended": []}})], [recipe([
        artifact("gated-dit", "gated.safetensors", "diffusion_model", None, 21_000),
        artifact("gated-vae", "gated_vae.safetensors", "vae", None, 1_000),
    ])])
    model = data["cases"][0]["models"][0]
    assert model["sha256"] == ZERO_SHA
    assert model["filename"] == "gated.safetensors"
    assert model["size_bytes"] == 21_000
    assert model["source"].startswith("unresolved, recipe:r/gated-dit")


def test_case_model_fields_missing_from_the_preset_form_are_listed():
    data = build_case_set("r", "x", [preset("P", WAN_ID, {"high_noise_model": {"sha256": "1" * 64}}, {"t2v_high_noise_model": {"model_type": "diffusion_model", "recommended": []}})], [])
    assert data["cases"][0]["undeclared_model_fields"] == ["high_noise_model"]


def test_model_fields_are_collected_from_nested_form_documents():
    documents = [{"fields": [{"type": "section", "children": [{"name": "vae", "type": "model", "configuration": {"model_type": "vae", "recommendations": [{"sha256": "ABC"}]}}]}]}, None]
    assert model_fields_of(documents) == {"vae": {"model_type": "vae", "recommended": ["abc"]}}


def test_a_preset_without_tests_is_kept_with_no_case():
    data = sample_case_set_data()
    tools = next(item for item in data["presets"] if item["key"] == "ModelTools")
    assert tools["case_count"] == 0
    assert tools["tests_blob"] is None


def test_a_written_case_set_loads_back(case_set):
    assert case_set.source == {"label": "fake core", "ref": "f" * 40}
    assert [case.name for case in case_set.cases] == ["sdxl-slow", "sdxl-fast", "wan-t2v"]
    assert case_set.cases[0].models[0].sha256 == SDXL_SHA
    assert case_set.preset("Wan")["id"] == WAN_ID
    assert case_set.preset(WAN_ID)["key"] == "Wan"
    assert len(case_set.sha256) == 64
    assert MISSING_SHA in {ref.sha256 for case in case_set.cases for ref in case.models}


def test_a_case_file_of_another_schema_is_refused(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema": 99}), encoding="utf-8")
    with pytest.raises(CaseFileError, match="schema"):
        load_cases(path)


def test_the_committed_case_file_holds_the_core_and_plugin_presets():
    case_set = load_cases(DEFAULT_CASES)
    origins = {preset["origin"] for preset in case_set.presets}
    assert case_set.source["ref"].startswith("d7ff033de")
    assert {"core", "plugin:video-producer"} <= origins
    assert sum(1 for preset in case_set.presets if preset["origin"] == "core") == 24
    assert sum(1 for preset in case_set.presets if preset["origin"] == "plugin:video-producer") == 5
    wan = next(case for case in case_set.cases if case.preset_key == "Wan2.1-T2V-1.3B-8GB")
    assert all(ref.resolved for ref in wan.models)
