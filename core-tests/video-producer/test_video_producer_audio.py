import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.features.presets.loader import PresetTemplateLoader
from src.features.video_director.normalize import normalize_video_director
from src.pipelines.pipes.generator.video_minimax_h3.windows import build_director_plan, resolve_mux_audio

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_audio_under_test"
PRESETS = REPO_ROOT / "content" / "presets" / "marketplace"
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
catalog = _plugin_module("backend.catalog")
presets = _plugin_module("backend.presets")


def _preset(folder, preset_id):
    loader = PresetTemplateLoader([str(PRESETS / folder)], shared_path=str(SHARED_PRESETS))
    return next(preset for preset in loader.load_presets() if preset.id == preset_id)


@pytest.fixture(scope="module")
def ltx25():
    return _preset("LTX-2.5", presets.LTX_2_5)


@pytest.fixture(scope="module")
def h3():
    return _preset("MiniMax-H3", presets.MINIMAX_H3)


@pytest.fixture
def storage(tmp_path):
    (tmp_path / "uploads").mkdir()
    for name in ("mix.wav", "hero.png"):
        (tmp_path / "uploads" / name).write_bytes(b"0")
    return tmp_path


def _mixed(capabilities, preset_id, fps, seconds, first=True):
    document = director.audio_document(
        {
            "schema_version": 1,
            "mode": "t2v",
            "settings": {"fps": fps, "duration": seconds, "resolution": "832x480", "seed": 7},
            "segments": [{"id": director.SEGMENT_ID, "prompt": "Waves hit the harbour wall.", "negative_prompt": ""}],
            "media": [],
        },
        seconds,
        fps,
        capabilities,
    )
    request = {"preset_id": preset_id, "mode": "video", "form_data": {"video_director": document}}
    if first:
        request = core_bridge.bind_director_media(
            request, "first", {"value": "uploads/hero.png", "media_type": "image"}, segment_id=director.SEGMENT_ID, capabilities=capabilities
        )
    request["form_data"]["video_director"]["audio"] = [director.mux_entry("uploads/mix.wav", seconds)]
    return request["form_data"]["video_director"]


def test_the_shipped_ltx_2_5_and_minimax_h3_presets_say_their_director_mode_takes_an_audio_track(ltx25, h3):
    assert catalog.audio_mux(ltx25.vars) and catalog.audio_mux(h3.vars)


def test_the_core_keeps_the_mixed_sound_of_an_ltx_2_5_shot_as_one_mux_track_over_the_whole_shot(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_mixed(capabilities, presets.LTX_2_5, 25, 3.0), capabilities, str(storage))

    assert normalized["mode"] == "director"
    assert (normalized["segments"][0]["start"], normalized["segments"][0]["end"]) == (0.0, 3.0)
    (track,) = normalized["audio"]
    assert {key: track[key] for key in ("id", "role", "start", "trim_start", "length")} == {
        "id": "a-1",
        "role": "mux",
        "start": 0.0,
        "trim_start": 0.0,
        "length": 3.0,
    }
    assert Path(track["media"]["path"]) == storage / "uploads" / "mix.wav"
    assert [Path(path) for path in normalized["media_images"]] == [storage / "uploads" / "hero.png"]


def test_a_mixed_ltx_2_5_shot_without_a_frame_is_a_text_to_video_director_run(ltx25, storage):
    capabilities = ltx25.vars["video_director"]

    normalized = normalize_video_director(_mixed(capabilities, presets.LTX_2_5, 25, 1.0, first=False), capabilities, str(storage))

    assert normalized["media_images"] == [] and normalized["audio"][0]["length"] == 1.0
    assert normalized["settings"]["frame_count"] == 25


def test_the_ltx_2_5_pipeline_mixes_the_first_audio_entry_of_the_document():
    pipeline = (PRESETS / "LTX-2.5" / "modes" / "video" / "pipeline.yml").read_text(encoding="utf-8")

    assert "form.video_director.audio[0].media.path" in pipeline
    assert "audio_source: \"{% if (form.video_director.audio | length) > 0 %}file{% else %}generate{% endif %}\"" in pipeline


def test_minimax_h3_outside_its_reference_mode_lays_the_mixed_sound_over_its_one_window(h3, storage):
    capabilities = h3.vars["video_director"]

    normalized = normalize_video_director(_mixed(capabilities, presets.MINIMAX_H3, 24, 3.0), capabilities, str(storage))

    assert normalized["segments"][0]["frames"] == 72
    assert Path(resolve_mux_audio(normalized)) == storage / "uploads" / "mix.wav"
    plan = build_director_plan(normalized, default_seed=1)
    assert len(plan.windows) == 1 and Path(plan.mux_audio_path) == storage / "uploads" / "mix.wav"


def test_the_minimax_h3_reference_mode_takes_no_audio_track_in_its_document(h3):
    refs = h3.vars["video_director"]["preset_mode_overrides"]["refs"]["modes"]["director"]

    assert refs["audio"] is False
