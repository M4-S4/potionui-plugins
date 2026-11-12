import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pytest
import yaml

from backend import catalog, presets
from src.plugin_api.presets import lint_preset_dir

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PRESETS_ROOT = PLUGIN_ROOT / "presets"
CORE_PRESETS = PLUGIN_ROOT.parents[2] / "presets" / "marketplace"
CORE_SOURCES = {
    "MiniMax-H3-12GB": "MiniMax-H3",
    "MiniMax-H3-Fast-12GB": "MiniMax-H3-Fast",
    "Wan2.1-T2V-1.3B-8GB": "Wan",
    "Wan2.2-14B-Lightning-12GB": "Wan",
    "Wan2.2-14B-Lightning-I2V-12GB": "Wan",
    "Wan2.2-TI2V-5B-8GB": "Wan",
}

H3_MODES = ("t2v", "i2v", "flf", "director")
WAN_MODES = ("t2v",)
IMAGE_MODES = ("i2v", "flf")
FIRST_FRAME_MODES = ("t2v", "i2v")
LIGHTNING_I2V_LORAS = {
    "i2v_loras_high": ["models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"],
    "i2v_loras_low": ["models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"],
}


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
    modes: Tuple[str, ...] = ("video",)

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
        director_modes=FIRST_FRAME_MODES,
        profiles=("FL2VA",),
        max_duration=5,
    ),
    "Wan2.2-14B-Lightning-12GB": Tier(
        id=presets.WAN22_14B_LIGHTNING_12GB,
        name="Wan 2.2 14B Lightning (12 GB)",
        min_vram_gb=12,
        recommended_vram_gb=16,
        ram_gb=64,
        family_tag="wan",
        fps_var="default_fps",
        fps=16,
        frames=81,
        director_modes=WAN_MODES,
        profiles=("FL2VA",),
        max_duration=5,
    ),
    "Wan2.2-14B-Lightning-I2V-12GB": Tier(
        id=presets.WAN22_14B_LIGHTNING_I2V_12GB,
        name="Wan 2.2 14B Lightning I2V (12 GB)",
        min_vram_gb=12,
        recommended_vram_gb=16,
        ram_gb=64,
        family_tag="wan",
        fps_var="default_fps",
        fps=16,
        frames=81,
        director_modes=IMAGE_MODES,
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
        profiles=("FL2VA", "Ref2VA", "Hybrid AV"),
        max_duration=15,
        modes=("video", "refs", "extend"),
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
TEXT_FOLDERS = sorted(folder for folder in WAN_FOLDERS if TIERS[folder].director_modes == WAN_MODES)


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
    assert manifest["modes"] == list(tier.modes)
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


@pytest.mark.parametrize("folder", TEXT_FOLDERS)
def test_a_wan_tier_preset_generates_from_text_only_for_at_most_5_seconds(folder):
    variables = _manifest(folder)["vars"]

    assert catalog.director_modes(variables) == ["t2v"]
    assert catalog.profiles(TIERS[folder].id, variables, ["video"]) == ["FL2VA"]
    assert catalog.preset_limits(variables)["max_duration"] == 5


def test_the_5b_tier_starts_a_shot_from_text_or_from_its_first_frame_with_the_same_file_in_both_pickers():
    folder = "Wan2.2-TI2V-5B-8GB"
    variables = _manifest(folder)["vars"]
    generation = yaml.safe_load((PRESETS_ROOT / folder / "modes" / "video" / "tabs" / "generation.yml").read_text(encoding="utf-8"))
    models = {field["name"]: field for section in generation["fields"] for field in section.get("children") or [] if field.get("type") == "model"}

    assert catalog.director_modes(variables) == ["t2v", "i2v"]
    assert catalog.companions(variables) == {}
    assert [item["sha256"] for item in models["i2v_high_noise_model"]["configuration"]["recommendations"]] == [
        item["sha256"] for item in models["t2v_high_noise_model"]["configuration"]["recommendations"]
    ]
    assert "recommendations" not in models["i2v_low_noise_model"]["configuration"]
    assert variables["video_director"]["timing"]["one_frame_tail"] == {
        "model_field": "i2v_high_noise_model",
        "sha256": [models["i2v_high_noise_model"]["configuration"]["recommendations"][0]["sha256"]],
    }


def _loras(folder):
    loras = yaml.safe_load((PRESETS_ROOT / folder / "modes" / "video" / "tabs" / "lora.yml").read_text(encoding="utf-8"))
    return {field["name"]: [row["model"] for row in field["default"]] for section in loras["fields"] for field in section["children"]}


def test_the_text_presets_are_the_two_text_only_wan_tiers_and_the_lightning_one_hands_its_image_shots_to_its_companion():
    lightning = _manifest("Wan2.2-14B-Lightning-12GB")["vars"]
    companion = _manifest("Wan2.2-14B-Lightning-I2V-12GB")["vars"]

    assert TEXT_FOLDERS == ["Wan2.1-T2V-1.3B-8GB", "Wan2.2-14B-Lightning-12GB"]
    assert catalog.companions(lightning) == {"i2v": presets.WAN22_14B_LIGHTNING_I2V_12GB, "flf": presets.WAN22_14B_LIGHTNING_I2V_12GB}
    assert catalog.companions(companion) == {"t2v": presets.WAN22_14B_LIGHTNING_12GB}
    assert all(catalog.companions(_manifest(folder)["vars"]) == {} for folder in TIERS if not folder.startswith("Wan2.2-14B-Lightning"))
    assert catalog.reachable_modes(lightning, {presets.WAN22_14B_LIGHTNING_I2V_12GB}) == ["t2v", "i2v", "flf"]
    assert catalog.reachable_modes(lightning, ()) == ["t2v"]


def test_the_lightning_text_preset_keeps_its_text_to_video_loras_and_its_companion_selects_the_image_to_video_ones():
    text, image = _loras("Wan2.2-14B-Lightning-12GB"), _loras("Wan2.2-14B-Lightning-I2V-12GB")

    assert (text["i2v_loras_high"], text["i2v_loras_low"]) == ([], [])
    assert [name for name in text["t2v_loras_high"] + text["t2v_loras_low"] if "_t2v_lightx2v_" in name] == text["t2v_loras_high"] + text["t2v_loras_low"]
    assert {name: image[name] for name in LIGHTNING_I2V_LORAS} == LIGHTNING_I2V_LORAS
    assert (image["t2v_loras_high"], image["t2v_loras_low"]) == ([], [])


def test_the_lightning_companion_runs_its_image_to_video_loras_in_four_steps_and_the_sizes_of_the_text_preset():
    text, image = (_manifest(folder) for folder in ("Wan2.2-14B-Lightning-12GB", "Wan2.2-14B-Lightning-I2V-12GB"))
    sizes = [(PRESETS_ROOT / folder / "files" / "form" / "resolutions_540p.yml").read_bytes() for folder in ("Wan2.2-14B-Lightning-12GB", "Wan2.2-14B-Lightning-I2V-12GB")]

    assert text["speed_profiles"] == {
        "fast": {"steps": 6, "guidance": 1.0, "sampler": "unipc"},
        "custom": {"steps": 6, "guidance": 1.0, "sampler": "unipc"},
    }
    assert image["speed_profiles"] == {
        "fast": {"steps": 4, "guidance": 1.0, "sampler": "unipc"},
        "custom": {"steps": 4, "guidance": 1.0, "sampler": "unipc"},
    }
    assert sizes[0] == sizes[1]
    assert max(int(width) * int(height) for width, height in (line.split('"')[1].split("x") for line in sizes[1].decode().splitlines() if "value" in line)) == 960 * 544


def _findings(lines):
    return {re.sub(r"^\[\w+\] .*?\.yml: ", "", line) for line in lines}


@pytest.mark.parametrize("folder", sorted(TIERS))
def test_a_shipped_preset_lints_without_error_and_warns_only_where_the_core_preset_it_copies_does(folder):
    errors, warnings = lint_preset_dir(str(PRESETS_ROOT / folder))
    _, core_warnings = lint_preset_dir(str(CORE_PRESETS / CORE_SOURCES[folder]))

    assert errors == []
    assert _findings(warnings) <= _findings(core_warnings)


def test_every_shipped_preset_names_the_core_preset_it_copies():
    assert sorted(CORE_SOURCES) == sorted(TIERS)
    assert all((CORE_PRESETS / source / "preset.yml").is_file() for source in CORE_SOURCES.values())


def test_the_12_gb_h3_preset_runs_ref2va_through_its_refs_mode():
    manifest = _manifest("MiniMax-H3-12GB")
    variables = manifest["vars"]

    assert catalog.REFS_MODE in manifest["modes"]
    assert variables["video_director"]["preset_modes"] == ["video", "refs"]
    assert catalog.profiles(presets.MINIMAX_H3_12GB, variables, manifest["modes"]) == ["FL2VA", "Ref2VA", "Hybrid AV"]
    assert catalog.main_mode(variables, manifest["modes"]) == "video"
    assert (PRESETS_ROOT / "MiniMax-H3-12GB" / "modes" / "refs" / "pipeline.yml").is_file()
