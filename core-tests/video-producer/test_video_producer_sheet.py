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
PACKAGE = "video_producer_sheet_under_test"
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
catalog = _plugin_module("backend.catalog")
presets = _plugin_module("backend.presets")
reception = _plugin_module("backend.reception")


@pytest.fixture(scope="module")
def ltx25():
    loader = PresetTemplateLoader([str(LTX25_PRESET)], shared_path=str(SHARED_PRESETS))
    return next(preset for preset in loader.load_presets() if preset.id == presets.LTX_2_5)


@pytest.fixture
def storage(tmp_path):
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "sheet.mp4").write_bytes(b"0")
    return tmp_path


def test_the_shipped_ltx_2_5_offers_ref2va_through_the_reference_sheet(ltx25):
    description = PresetDescription(id=ltx25.id, name=ltx25.name, vars=dict(ltx25.vars), modes=dict.fromkeys(ltx25.modes), engine="native")

    assert reception.SHEET["presets"] == [presets.LTX_2_5]
    assert catalog.profiles(description.id, description.vars, list(ltx25.modes)) == [catalog.FL2VA, catalog.REF2VA]
    assert catalog.run_modes(description.id, description.vars, list(ltx25.modes), "native") == ["video"]


def test_the_core_normalizes_a_sheet_take_into_one_ic_lora_reference_of_the_take_size_without_first_frame(ltx25, storage):
    capabilities = ltx25.vars["video_director"]
    frames = reception.sheet_frames(5.0)
    document = director.sheet_document("### Target Description\n\nA boat leaves the port.", 24, frames / 24, "768x448", "model:ingredients", "uploads/sheet.mp4")

    normalized = normalize_video_director(document, capabilities, str(storage))

    assert normalized["mode"] == "director"
    assert (normalized["settings"]["fps"], normalized["settings"]["frame_count"], normalized["settings"]["resolution"]) == (24, 121, "768x448")
    (entry,) = normalized["ic_lora"]
    assert (entry["id"], entry["lora"], entry["strength"]) == ("ic-sheet", {"model": "model:ingredients", "strength": 1.0}, 1.0)
    assert Path(entry["reference"]["path"]) == storage / "uploads" / "sheet.mp4"
    assert normalized["media_images"] == []
    assert normalized["media_placements"] == [{"source": "video", "index": 0, "frame": "first", "strength": 1.0, "role": "reference"}]
