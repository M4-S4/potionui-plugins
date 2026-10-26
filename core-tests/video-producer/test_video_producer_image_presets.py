import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.plugin_api.presets as plugin_presets
from src.features.presets.loader import PresetTemplateLoader
from src.plugin_api import AccountType

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_image_presets_under_test"
MARKETPLACE = REPO_ROOT / "content" / "presets" / "marketplace"
SHARED_PRESETS = REPO_ROOT / "content" / "presets" / "_shared"
IMAGE_PRESETS = ("Anima", "Flux1", "Flux2", "Flux3", "Krea2", "MOSS-Image", "QwenImage", "QwenImage-2.1", "SDXL", "ZImage")

INSTALLED_FILES = {
    "anima-aesthetic-v1.1.safetensors",
    "anima-turbo-v1.1.safetensors",
    "flux-2-klein-4b.safetensors",
    "krea2_turbo_fp8_scaled.safetensors",
    "moss_image_sft_bf16.safetensors",
    "qwen_image_2.1_bf16.safetensors",
    "qwen_image_2512_fp8_e4m3fn.safetensors",
    "z_image_turbo_bf16.safetensors",
    "qwen3vl_4b_fp8_scaled.safetensors",
    "qwen3vl_8b_bf16.safetensors",
    "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "qwen_3_06b_base.safetensors",
    "qwen_3_4b.safetensors",
    "ae.safetensors",
    "flux2-vae.safetensors",
    "qwen_image_2.1_vae_bf16.safetensors",
    "qwen_image_vae.safetensors",
}


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


core_bridge = _plugin_module("backend.core_bridge")
keyframes = _plugin_module("backend.keyframes")


@pytest.fixture(scope="module")
def templates():
    loader = PresetTemplateLoader([str(MARKETPLACE / name) for name in IMAGE_PRESETS], shared_path=str(SHARED_PRESETS))
    return {template.id: template for template in loader.load_presets()}


@pytest.fixture
def shipped(templates, monkeypatch):
    repository = SimpleNamespace(find_preset_by_id=templates.get, preset_loader=SimpleNamespace(shared_path=SHARED_PRESETS))
    container = SimpleNamespace(file_preset_repository=repository)
    monkeypatch.setattr(plugin_presets, "get_container", lambda: container)
    monkeypatch.setattr(core_bridge, "api_hooks", SimpleNamespace(get_container=lambda: container))
    descriptions = [plugin_presets.describe_preset(preset_id) for preset_id in templates]
    monkeypatch.setattr(core_bridge, "list_presets", lambda user: descriptions)
    monkeypatch.setattr(core_bridge, "enabled_backends", lambda: [])
    monkeypatch.setattr(core_bridge, "installed_model_id", lambda sha256: None)
    monkeypatch.setattr(core_bridge, "installed_model_for_file", lambda filename: f"id-{filename}" if filename in INSTALLED_FILES else None)
    return SimpleNamespace(id="admin-1", account_type=AccountType.ADMIN)


def test_the_shipped_image_presets_with_the_weights_of_the_test_machine_offer_three_models_and_say_why_the_others_cannot(shipped):
    listed = keyframes.image_presets(shipped)

    assert [(preset.name, preset.mode, preset.max_images, preset.reason) for preset in listed if preset.usable] == [
        ("Flux2", "img2img", 1, None),
        ("Qwen-Image", "img2img", 1, None),
        ("Qwen-Image-2.1", "edit", 10, None),
    ]
    unusable = {preset.name: (preset.mode, preset.reason) for preset in listed if not preset.usable}
    assert unusable["FLUX 3 Klein (experimental)"] == ("edit", "missing_models")
    assert unusable["Flux1"] == ("img2img", "missing_models")
    for name in ("Anima", "Krea-2", "MOSS-Image", "SDXL", "Z-Image"):
        assert unusable[name] == (None, "no_image_mode"), name
    assert len(listed) == len(IMAGE_PRESETS)


def test_a_shipped_edit_preset_takes_several_pictures_and_an_image_to_image_one_takes_one(shipped):
    by_name = {preset.name: preset for preset in keyframes.image_presets(shipped)}

    assert (by_name["Qwen-Image-2.1"].field, by_name["Qwen-Image-2.1"].max_images) == ("source_image", 10)
    assert (by_name["Flux2"].field, by_name["Flux2"].max_images) == ("source_image", 1)
    assert by_name["FLUX 3 Klein (experimental)"].max_images == 10 and "diffusion_model" in by_name["FLUX 3 Klein (experimental)"].missing
    assert by_name["FLUX 3 Klein (experimental)"].output_sizes[:2] == ("1024x1024", "1152x896")
