import importlib
import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from src.features.presets.children_paths import resolve_children_path
from src.features.presets.loader import PresetTemplateLoader
from src.features.recipes.schema import parse_recipe, validate_recipe_dict
from src.features.video_director.normalize import normalize_video_director

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_recipes_under_test"


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


catalog = _plugin_module("backend.catalog")
presets = _plugin_module("backend.presets")

RECIPES_ROOT = PLUGIN_ROOT / "recipes"
PRESETS_ROOT = PLUGIN_ROOT / "presets"
CORE_WAN_PRESET = REPO_ROOT / "content" / "presets" / "marketplace" / "Wan"
SHARED_PRESETS = REPO_ROOT / "content" / "presets" / "_shared"

RECIPE_PRESETS = {
    "vp-wan21-t2v-1-3b-8gb": presets.WAN21_T2V_1_3B_8GB,
    "vp-wan22-ti2v-5b-8gb": presets.WAN22_TI2V_5B_8GB,
    "vp-wan22-14b-lightning-12gb": presets.WAN22_14B_LIGHTNING_12GB,
    "vp-minimax-h3-12gb": presets.MINIMAX_H3_12GB,
    "vp-minimax-h3-fast-12gb": presets.MINIMAX_H3_FAST_12GB,
    "vp-wan22-14b-i2v": presets.WAN,
}
WITHOUT_SMOKE = {"vp-minimax-h3-12gb", "vp-minimax-h3-fast-12gb"}
WITH_SMOKE = sorted(set(RECIPE_PRESETS) - WITHOUT_SMOKE)
PATH_HINTS = {
    presets.WAN21_T2V_1_3B_8GB: "video-producer/Wan2.1-T2V-1.3B-8GB",
    presets.WAN22_TI2V_5B_8GB: "video-producer/Wan2.2-TI2V-5B-8GB",
    presets.WAN22_14B_LIGHTNING_12GB: "video-producer/Wan2.2-14B-Lightning-12GB",
    presets.MINIMAX_H3_12GB: "video-producer/MiniMax-H3-12GB",
    presets.MINIMAX_H3_FAST_12GB: "video-producer/MiniMax-H3-Fast-12GB",
    presets.WAN: "marketplace/Wan",
}
WEIGHT_KINDS = ("diffusion_model", "text_encoder", "vae")
SHA256 = re.compile(r"[0-9a-f]{64}")


def _raw(recipe_id):
    return yaml.safe_load((RECIPES_ROOT / f"{recipe_id}.yml").read_text(encoding="utf-8"))


def _recipe(recipe_id):
    return parse_recipe(_raw(recipe_id), source_path=str(RECIPES_ROOT / f"{recipe_id}.yml"))


def _files(artifact):
    return list(artifact.variants) or [artifact]


def _shipped_preset_ids():
    return {yaml.safe_load(path.read_text(encoding="utf-8"))["id"] for path in PRESETS_ROOT.rglob("preset.yml")}


@pytest.fixture(scope="module")
def loaded_presets():
    manifest = SimpleNamespace(id="video-producer", plugin_dir=str(PLUGIN_ROOT), presets=[{"path": "presets"}])
    registry = SimpleNamespace(get_enabled_plugins=lambda: [manifest])
    loader = PresetTemplateLoader([str(CORE_WAN_PRESET)], plugin_registry=registry, shared_path=str(SHARED_PRESETS))
    found = {preset.id: preset for preset in loader.load_presets()}
    assert loader.load_errors == {}
    return found


def _visible_fields(preset):
    [form] = preset.modes["video"].forms
    found = []

    def walk(fields):
        for field in fields:
            if field.visible is False:
                continue
            found.append(field)
            if isinstance(field.children, list):
                walk(field.children)

    walk(form.fields)
    return found


def _model_fields(preset):
    return [field for field in _visible_fields(preset) if field.type == "model"]


def _named(preset, name):
    [field] = [field for field in _visible_fields(preset) if field.name == name]
    return field


def _recommendations(field):
    return field.configuration.get("recommendations") or []


def _resolution_values(preset):
    values = []
    for entry in _named(preset, "resolution").configuration["files"]:
        path = resolve_children_path(entry["path"], Path(preset.path), SHARED_PRESETS)
        values += [item["value"] for item in yaml.safe_load(path.read_text(encoding="utf-8"))]
    return values


def test_the_manifest_declares_the_recipes_folder():
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))

    assert manifest["recipes"] == [{"path": "recipes"}]
    assert sorted(path.stem for path in RECIPES_ROOT.glob("*.yml")) == sorted(RECIPE_PRESETS)


def test_the_recipe_ids_are_unique_and_prefixed_with_vp():
    ids = [_raw(recipe_id)["id"] for recipe_id in sorted(RECIPE_PRESETS)]

    assert ids == sorted(RECIPE_PRESETS)
    assert len(set(ids)) == len(ids)
    assert all(recipe_id.startswith("vp-") for recipe_id in ids)


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_a_recipe_validates_with_the_schema_of_the_core(recipe_id):
    assert validate_recipe_dict(_raw(recipe_id)) == []


def test_every_shipped_preset_has_a_recipe():
    assert _shipped_preset_ids() <= set(RECIPE_PRESETS.values())


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_a_recipe_targets_a_preset_of_the_plugin_or_the_wan_preset_of_the_core(recipe_id, loaded_presets):
    recipe = _recipe(recipe_id)
    preset_id = RECIPE_PRESETS[recipe_id]

    assert preset_id in _shipped_preset_ids() | {presets.WAN}
    assert preset_id in loaded_presets
    assert [(ref.preset_id, ref.path_hint, ref.assign_to_owner) for ref in recipe.presets] == [(preset_id, PATH_HINTS[preset_id], True)]
    if recipe_id in WITHOUT_SMOKE:
        assert recipe.smoke is None
    else:
        assert (recipe.smoke.preset_id, recipe.smoke.mode) == (preset_id, "video")
    assert "video" in loaded_presets[preset_id].modes
    assert "video-producer" in {plugin.id for plugin in recipe.plugins}


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_a_recipe_installs_and_tries_its_preset_without_the_render_step_of_the_core(recipe_id):
    recipe = _recipe(recipe_id)
    preset_id = RECIPE_PRESETS[recipe_id]
    by_kind = {}
    for step in recipe.steps:
        by_kind.setdefault(step.kind, []).append(step)

    assert "pipeline.render" not in by_kind
    assert [step.params["preset_id"] for step in by_kind["preset.ensure"]] == [preset_id]
    if recipe_id in WITHOUT_SMOKE:
        assert "generation.smoke" not in by_kind
        assert recipe.steps[-1].kind == "preset.ensure"
    else:
        assert [(step.params["preset_id"], step.params["mode"]) for step in by_kind["generation.smoke"]] == [(preset_id, "video")]
        assert recipe.steps[-1].kind == "generation.smoke"
    artifact_ids = [artifact.id for artifact in recipe.artifacts]
    assert [step.params["artifact_ids"] for step in by_kind["artifacts.plan"]] == [artifact_ids]
    assert [step.params["artifact_ids"] for step in by_kind["artifacts.fetch"]] == [artifact_ids]


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_every_file_of_a_recipe_has_a_size_and_a_lowercase_sha256(recipe_id):
    recipe = _recipe(recipe_id)

    assert recipe.artifacts
    for artifact in recipe.artifacts:
        for file in _files(artifact):
            assert file.size_bytes and file.size_bytes > 0, file.filename
            assert file.checksum.algorithm == "sha256", file.filename
            assert SHA256.fullmatch(file.checksum.value), file.filename
            assert file.provider_hint["source"] == "huggingface", file.filename


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_every_weight_of_a_recipe_is_a_recommendation_of_a_model_picker_of_its_preset(recipe_id, loaded_presets):
    recipe = _recipe(recipe_id)
    recommended = {}
    for field in _model_fields(loaded_presets[RECIPE_PRESETS[recipe_id]]):
        for item in _recommendations(field):
            assert SHA256.fullmatch(item["sha256"]), (field.name, item["name"])
            recommended.setdefault((field.configuration["model_type"], item["name"]), set()).add(item["sha256"])

    weights = [artifact for artifact in recipe.artifacts if artifact.kind in WEIGHT_KINDS]

    assert weights
    for artifact in weights:
        for file in _files(artifact):
            assert recommended.get((artifact.kind, file.filename)) == {file.checksum.value}, (artifact.id, file.filename)


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_a_recipe_downloads_a_recommended_file_for_every_weight_picker_of_its_preset(recipe_id, loaded_presets):
    recipe = _recipe(recipe_id)
    installed = {kind: {file.filename for artifact in recipe.artifacts if artifact.kind == kind for file in _files(artifact)} for kind in WEIGHT_KINDS}

    for field in _model_fields(loaded_presets[RECIPE_PRESETS[recipe_id]]):
        names = {item["name"] for item in _recommendations(field)}
        kind = field.configuration["model_type"]
        if kind in WEIGHT_KINDS and names:
            assert names & installed[kind], field.name


@pytest.mark.parametrize("recipe_id", sorted(RECIPE_PRESETS))
def test_the_loras_of_a_recipe_are_the_ones_its_preset_selects_by_default(recipe_id, loaded_presets):
    recipe = _recipe(recipe_id)
    selected = [
        item["model"].rsplit("/", 1)[-1]
        for field in _visible_fields(loaded_presets[RECIPE_PRESETS[recipe_id]])
        if field.type == "lora_picker"
        for item in field.default or []
    ]

    assert sorted(file.filename for artifact in recipe.artifacts if artifact.kind == "lora" for file in _files(artifact)) == sorted(selected)


def test_the_lightning_recipe_downloads_the_lora_of_each_expert_the_preset_selects(loaded_presets):
    recipe = _recipe("vp-wan22-14b-lightning-12gb")
    preset = loaded_presets[presets.WAN22_14B_LIGHTNING_12GB]
    high = [item["model"].rsplit("/", 1)[-1] for item in _named(preset, "t2v_loras_high").default]
    low = [item["model"].rsplit("/", 1)[-1] for item in _named(preset, "t2v_loras_low").default]
    loras = [artifact.filename for artifact in recipe.artifacts if artifact.kind == "lora"]

    assert all(item["model"].startswith("models/loras/") for name in ("t2v_loras_high", "t2v_loras_low") for item in _named(preset, name).default)
    assert len(high) == len(low) == 1
    assert "high_noise" in high[0] and "low_noise" in low[0]
    assert sorted(loras) == sorted(high + low)
    assert all(artifact.required for artifact in recipe.artifacts if artifact.kind == "lora")


@pytest.mark.parametrize("recipe_id", WITH_SMOKE)
def test_the_smoke_form_is_a_one_second_text_to_video_document_at_the_fps_of_the_preset(recipe_id, loaded_presets, tmp_path):
    recipe = _recipe(recipe_id)
    preset = loaded_presets[RECIPE_PRESETS[recipe_id]]
    form = recipe.smoke.form
    document = form["video_director"]
    [segment] = document["segments"]

    assert document["schema_version"] == 1 and document["mode"] == "t2v"
    assert document["settings"]["fps"] == catalog.preset_fps(preset.vars)
    assert document["settings"]["duration"] == 1
    assert document["settings"]["resolution"] == form["resolution"]
    assert document["settings"]["seed"] == recipe.smoke.seed
    assert document["media"] == []
    assert segment["prompt"].strip() and segment["negative_prompt"] == ""
    assert not recipe.smoke.prompt or recipe.smoke.prompt == segment["prompt"]
    assert form["resolution"] in _resolution_values(preset)
    assert form.get("speed_profile", _named(preset, "speed_profile").default) in {
        option["value"] for option in _named(preset, "speed_profile").configuration["options"]
    }
    normalized = normalize_video_director(document, preset.vars["video_director"], str(tmp_path))
    assert normalized["mode"] == "t2v" and normalized["settings"]["fps"] == document["settings"]["fps"]
