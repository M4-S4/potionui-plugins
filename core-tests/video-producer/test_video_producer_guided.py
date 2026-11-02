import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.features.presets.loader import PresetTemplateLoader
from src.features.video_director.normalize import normalize_video_director
from src.plugin_api import PresetDescription

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_guided_under_test"
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
    (tmp_path / "generations").mkdir()
    for name in ("uploads/first.png", "uploads/sound.wav", "generations/draft.mp4"):
        (tmp_path / name).write_bytes(b"0")
    return tmp_path


def _request(capabilities, sound=False):
    seconds = director.guided_frames(5.1666, 24) / 24
    document = director.guided_document("A boat leaves the port at dawn.", 24, seconds, "1280x720", "model:ic-lora", "generations/draft.mp4")
    if sound:
        document["audio"] = [director.mux_entry("uploads/sound.wav", seconds)]
    request = {"preset_id": presets.LTX_2_5, "mode": "video", "form_data": {"video_director": document}}
    return core_bridge.bind_director_media(
        request, "first", {"value": "uploads/first.png", "media_type": "image"}, segment_id=director.SEGMENT_ID, capabilities=capabilities
    )


def test_the_guided_preset_is_the_shipped_ltx_2_5_whose_director_mode_takes_ic_lora(ltx25, monkeypatch):
    description = PresetDescription(id=ltx25.id, name=ltx25.name, vars=dict(ltx25.vars), modes=dict.fromkeys(ltx25.modes), engine="native")
    monkeypatch.setattr(core_bridge, "list_presets", lambda user: [description])

    preset = director.guided_preset(object())

    assert preset is not None and preset.id == presets.LTX_2_5
    assert preset.main_mode == "video"


def test_the_core_normalizes_a_guided_final_into_its_first_frame_then_the_draft_as_ic_lora_reference(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_request(capabilities)["form_data"]["video_director"], capabilities, str(storage))

    assert normalized["mode"] == "director"
    assert (normalized["settings"]["fps"], normalized["settings"]["frame_count"]) == (24, 121)
    (entry,) = normalized["ic_lora"]
    assert (entry["lora"], entry["strength"]) == ({"model": "model:ic-lora", "strength": 1.0}, 1.0)
    assert Path(entry["reference"]["path"]) == storage / "generations" / "draft.mp4"
    assert [Path(path) for path in normalized["media_images"]] == [storage / "uploads" / "first.png"]
    assert normalized["media_placements"] == [
        {"source": "image", "index": 0, "frame": "first", "strength": 1.0, "role": "keyframe"},
        {"source": "video", "index": 0, "frame": "first", "strength": 1.0, "role": "reference"},
    ]


def test_a_guided_final_carries_the_sound_of_its_draft_as_a_mixed_track(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_request(capabilities, sound=True)["form_data"]["video_director"], capabilities, str(storage))

    (track,) = normalized["audio"]
    assert (track["role"], track["start"], track["length"]) == ("mux", 0.0, 121 / 24)
    assert Path(track["media"]["path"]) == storage / "uploads" / "sound.wav"
    assert normalized["ic_lora"][0]["strength"] == 1.0
