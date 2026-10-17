from pathlib import Path

import pytest
import yaml

from backend import catalog, presets
from src.plugin_api.presets import lint_preset_dir

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRESETS_ROOT = PLUGIN_ROOT / "presets"

SHIPPED = {
    "MiniMax-H3-12GB": (presets.MINIMAX_H3_12GB, "MiniMax-H3 (12 GB)"),
    "MiniMax-H3-Fast-12GB": (presets.MINIMAX_H3_FAST_12GB, "MiniMax-H3-Fast (12 GB)"),
}


def _manifest(folder):
    return yaml.safe_load((PRESETS_ROOT / folder / "preset.yml").read_text(encoding="utf-8"))


def test_the_manifest_declares_the_presets_folder():
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))

    assert manifest["presets"] == [{"path": "presets"}]
    assert sorted(path.parent.name for path in PRESETS_ROOT.rglob("preset.yml")) == sorted(SHIPPED)


@pytest.mark.parametrize("folder", sorted(SHIPPED))
def test_a_shipped_preset_carries_the_id_and_name_the_backend_knows(folder):
    preset_id, name = SHIPPED[folder]
    manifest = _manifest(folder)

    assert (manifest["id"], manifest["name"]) == (preset_id, name)
    assert preset_id in presets.MINIMAX_H3_PRESETS and preset_id in presets.VIDEO_DIRECTOR_PRESETS


@pytest.mark.parametrize("folder", sorted(SHIPPED))
def test_a_shipped_preset_declares_the_12_gb_profile(folder):
    manifest = _manifest(folder)

    assert catalog.memory_profile(manifest["vars"]) == "12 GB"
    assert manifest["requires"] == {"min_vram_gb": 12, "recommended_vram_gb": 12}
    assert manifest["tags"][:2] == ["12gb", "low-vram"]
    assert manifest["modes"] == ["video"]
    assert (manifest["vars"]["fps"], manifest["vars"]["default_frames"]) == (24, 124)
    assert catalog.main_mode(manifest["vars"], manifest["modes"]) == "video"


@pytest.mark.parametrize("folder", sorted(SHIPPED))
def test_a_shipped_preset_lints_without_error(folder):
    errors, warnings = lint_preset_dir(str(PRESETS_ROOT / folder))

    assert errors == []
    assert warnings == []
