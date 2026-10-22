import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.features.presets.loader import PresetTemplateLoader
from src.features.video_director.normalize import normalize_video_director

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_layout_under_test"
LTX25_PRESET = REPO_ROOT / "content" / "presets" / "marketplace" / "LTX-2.5"
SHARED_PRESETS = REPO_ROOT / "content" / "presets" / "_shared"


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


director = _plugin_module("backend.director")
core_bridge = _plugin_module("backend.core_bridge")
presets = _plugin_module("backend.presets")


@pytest.fixture(scope="module")
def ltx25():
    loader = PresetTemplateLoader([str(LTX25_PRESET)], shared_path=str(SHARED_PRESETS))
    return next(preset for preset in loader.load_presets() if preset.id == presets.LTX_2_5)


@pytest.fixture
def storage(tmp_path):
    (tmp_path / "uploads").mkdir()
    for name in ("orbit.mp4", "hero.png"):
        (tmp_path / "uploads" / name).write_bytes(b"0")
    return tmp_path


def _request(capabilities, first=True):
    document = director.layout_document("The hut at dawn.", 24, 4.0, "832x480", "model:ic-lora", "uploads/orbit.mp4")
    request = {"preset_id": presets.LTX_2_5, "mode": "video", "form_data": {"video_director": document}}
    if first:
        request = core_bridge.bind_director_media(
            request, "first", {"value": "uploads/hero.png", "media_type": "image"}, segment_id=director.SEGMENT_ID, capabilities=capabilities
        )
    return request


def test_the_layout_preset_is_the_shipped_ltx_2_5_whose_director_mode_takes_ic_lora(ltx25):
    preset = director.Preset(id=ltx25.id, name=ltx25.name, engine="native", variables=dict(ltx25.vars), modes=tuple(ltx25.modes))

    assert director.layout_preset(preset)
    assert preset.main_mode == "video"


def test_the_core_normalizes_a_layout_shot_into_a_first_keyframe_then_the_guide_video_as_ic_lora_reference(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_request(capabilities)["form_data"]["video_director"], capabilities, str(storage))

    assert normalized["mode"] == "director"
    assert normalized["segments"][0]["prompt"] == "The hut at dawn."
    assert (normalized["settings"]["fps"], normalized["settings"]["frame_count"]) == (24, 97)
    (entry,) = normalized["ic_lora"]
    assert (entry["lora"], entry["strength"]) == ({"model": "model:ic-lora", "strength": 1.0}, 1.0)
    assert Path(entry["reference"]["path"]) == storage / "uploads" / "orbit.mp4"
    assert [Path(path) for path in normalized["media_images"]] == [storage / "uploads" / "hero.png"]
    assert [Path(path) for path in normalized["media_videos"]] == [storage / "uploads" / "orbit.mp4"]
    assert normalized["media_placements"] == [
        {"source": "image", "index": 0, "frame": "first", "strength": 1.0, "role": "keyframe"},
        {"source": "video", "index": 0, "frame": "first", "strength": 1.0, "role": "reference"},
    ]


def test_a_layout_shot_without_a_first_frame_conditions_on_its_guide_video_alone(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_request(capabilities, first=False)["form_data"]["video_director"], capabilities, str(storage))

    assert normalized["media_images"] == []
    assert normalized["media_placements"] == [{"source": "video", "index": 0, "frame": "first", "strength": 1.0, "role": "reference"}]
