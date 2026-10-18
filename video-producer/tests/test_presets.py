from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest
import yaml

from backend import catalog, presets
from src.plugin_api.presets import lint_preset_dir

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRESETS_ROOT = PLUGIN_ROOT / "presets"

H3_MODES = ("t2v", "i2v", "flf", "director")
WAN_MODES = ("t2v",)


@dataclass(frozen=True)
class Tier:
    id: str
    name: str
    min_vram_gb: int
    recommended_vram_gb: int
    ram_gb: Optional[int]
    family_tag: str
    fps_var: str
    fps: int
    frames: int
    director_modes: Tuple[str, ...]
    profiles: Tuple[str, ...]
    max_duration: int

    @property
    def is_wan(self):
        return self.family_tag == "wan"

    @property
    def requires(self):
        ram = {} if self.ram_gb is None else {"min_ram_gb": self.ram_gb}
        return {"min_vram_gb": self.min_vram_gb, "recommended_vram_gb": self.recommended_vram_gb, **ram}

    @property
    def profile(self):
        return f"{self.min_vram_gb} GB" + ("" if self.ram_gb is None else f" · {self.ram_gb} GB RAM")

    @property
    def ram_tags(self):
        return [] if self.ram_gb is None else [f"ram-{self.ram_gb}gb"]

    @property
    def leading_tags(self):
        return [f"{self.min_vram_gb}gb", "low-vram", *self.ram_tags, self.family_tag][:3]


TIERS = {
    "Wan2.1-T2V-1.3B-8GB": Tier(
        id=presets.WAN21_T2V_1_3B_8GB,
        name="Wan 2.1 T2V 1.3B (8 GB)",
        min_vram_gb=8,
        recommended_vram_gb=12,
        ram_gb=32,
        family_tag="wan",
        fps_var="default_fps",
        fps=16,
        frames=81,
        director_modes=WAN_MODES,
        profiles=("FL2VA",),
        max_duration=5,
    ),
    "Wan2.2-TI2V-5B-8GB": Tier(
        id=presets.WAN22_TI2V_5B_8GB,
        name="Wan 2.2 TI2V 5B (8 GB)",
        min_vram_gb=8,
        recommended_vram_gb=12,
        ram_gb=32,
        family_tag="wan",
        fps_var="default_fps",
        fps=24,
        frames=121,
        director_modes=WAN_MODES,
        profiles=("FL2VA",),
        max_duration=5,
    ),
    "MiniMax-H3-12GB": Tier(
        id=presets.MINIMAX_H3_12GB,
        name="MiniMax-H3 (12 GB)",
        min_vram_gb=12,
        recommended_vram_gb=12,
        ram_gb=64,
        family_tag="minimax",
        fps_var="fps",
        fps=24,
        frames=124,
        director_modes=H3_MODES,
        profiles=("FL2VA", "Hybrid AV"),
        max_duration=15,
    ),
    "MiniMax-H3-Fast-12GB": Tier(
        id=presets.MINIMAX_H3_FAST_12GB,
        name="MiniMax-H3-Fast (12 GB)",
        min_vram_gb=12,
        recommended_vram_gb=12,
        ram_gb=64,
        family_tag="minimax",
        fps_var="fps",
        fps=24,
        frames=124,
        director_modes=H3_MODES,
        profiles=("FL2VA", "Hybrid AV"),
        max_duration=15,
    ),
}

WAN_FOLDERS = sorted(folder for folder, tier in TIERS.items() if tier.is_wan)


def _manifest(folder):
    return yaml.safe_load((PRESETS_ROOT / folder / "preset.yml").read_text(encoding="utf-8"))


def test_the_manifest_declares_the_presets_folder():
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))

    assert manifest["presets"] == [{"path": "presets"}]
    assert sorted(path.parent.name for path in PRESETS_ROOT.rglob("preset.yml")) == sorted(TIERS)


@pytest.mark.parametrize("folder", sorted(TIERS))
def test_a_shipped_preset_carries_the_id_and_name_the_backend_knows(folder):
    tier = TIERS[folder]
    manifest = _manifest(folder)

    assert (manifest["id"], manifest["name"]) == (tier.id, tier.name)
    assert tier.id in presets.VIDEO_DIRECTOR_PRESETS
    assert (tier.id in presets.WAN_TIER_PRESETS, tier.id in presets.MINIMAX_H3_PRESETS) == (tier.is_wan, not tier.is_wan)


def test_the_backend_lists_exactly_the_presets_of_the_table():
    assert sorted(presets.WAN_TIER_PRESETS) == sorted(tier.id for tier in TIERS.values() if tier.is_wan)
    assert {tier.id for tier in TIERS.values() if not tier.is_wan} <= set(presets.MINIMAX_H3_PRESETS)
    assert set(presets.WAN_TIER_PRESETS) <= set(presets.VIDEO_DIRECTOR_PRESETS)
    assert not set(presets.WAN_TIER_PRESETS) & set(presets.MINIMAX_H3_PRESETS)
    assert presets.WAN not in presets.WAN_TIER_PRESETS


@pytest.mark.parametrize("folder", sorted(TIERS))
def test_a_shipped_preset_declares_its_hardware_tier(folder):
    tier = TIERS[folder]
    manifest = _manifest(folder)
    variables = manifest["vars"]

    assert catalog.memory_profile(variables) == tier.profile
    assert manifest["requires"] == tier.requires
    assert manifest["tags"][:3] == tier.leading_tags
    assert [tag for tag in manifest["tags"] if tag.startswith("ram-")] == tier.ram_tags
    assert manifest["modes"] == ["video"]
    assert (variables[tier.fps_var], variables["default_frames"]) == (tier.fps, tier.frames)
    assert catalog.preset_fps(variables) == tier.fps
    assert catalog.main_mode(variables, manifest["modes"]) == "video"


@pytest.mark.parametrize("folder", sorted(TIERS))
def test_a_shipped_preset_declares_the_director_modes_and_limits_it_runs(folder):
    tier = TIERS[folder]
    manifest = _manifest(folder)
    variables = manifest["vars"]

    assert catalog.director_modes(variables) == list(tier.director_modes)
    assert catalog.profiles(tier.id, variables, manifest["modes"]) == list(tier.profiles)
    assert catalog.preset_limits(variables)["max_duration"] == tier.max_duration
    assert catalog.preset_limits(variables)["default_fps"] == tier.fps


@pytest.mark.parametrize("folder", WAN_FOLDERS)
def test_a_wan_tier_preset_generates_from_text_only_for_at_most_5_seconds(folder):
    variables = _manifest(folder)["vars"]

    assert catalog.director_modes(variables) == ["t2v"]
    assert catalog.profiles(TIERS[folder].id, variables, ["video"]) == ["FL2VA"]
    assert catalog.preset_limits(variables)["max_duration"] == 5


@pytest.mark.parametrize("folder", sorted(TIERS))
def test_a_shipped_preset_lints_without_error(folder):
    errors, warnings = lint_preset_dir(str(PRESETS_ROOT / folder))

    assert errors == []
    assert warnings == []
