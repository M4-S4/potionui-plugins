import importlib

import pytest

from src.plugin_api.media import upload_formats
from src.plugin_api.media_tools import InvalidToolParams, MediaTool

import tools
from tools import common

from . import conftest
from .conftest import MANIFEST, PLUGIN_ROOT, TOOLS, make_video, need_encoders, params_for

ICONS_ON_BOTH_CORES = {"image", "film", "audio", "editor-music"}

SUFFIXES = {
    "media-convert.image": ("image", common.IMAGE_FORMATS),
    "media-convert.video": ("video", common.VIDEO_FORMATS),
    "media-convert.audio": ("audio", common.AUDIO_FORMATS),
    "media-convert.extract-audio": ("audio", common.AUDIO_FORMATS),
}


def options(tool_id, name):
    param = next(p for p in TOOLS[tool_id]["params"] if p["name"] == name)
    return [option["value"] for option in param["options"]]


def test_the_manifest_names_the_plugin_and_its_version():
    assert MANIFEST["id"] == tools.PLUGIN_ID == "media-convert"
    assert MANIFEST["version"] == tools.PLUGIN_VERSION == "0.1.1"
    assert MANIFEST["type"] == "backend-only"
    assert MANIFEST["license"] == "GPL-3.0"
    assert "pages" not in MANIFEST and "api" not in MANIFEST


def test_there_are_four_python_tools_without_a_component():
    assert sorted(TOOLS) == sorted(SUFFIXES)
    for entry in TOOLS.values():
        assert entry["python"] and "component" not in entry
        assert entry["cardinality"] == "one_to_one"


def test_no_tool_offers_replace_so_the_library_name_follows_the_new_format():
    for tool_id, (kind, _) in SUFFIXES.items():
        assert TOOLS[tool_id]["produces"] == kind


def test_tools_show_in_the_library_and_the_history_only():
    for entry in TOOLS.values():
        assert entry["scopes"] == ["library", "history"]


def test_extracting_the_sound_needs_a_video_with_sound():
    assert TOOLS["media-convert.extract-audio"]["requires"] == {"has_audio": True}
    assert TOOLS["media-convert.extract-audio"]["accepts"] == ["video"]


@pytest.mark.parametrize("tool_id", sorted(SUFFIXES))
def test_every_output_format_is_one_the_library_accepts(tool_id):
    kind, table = SUFFIXES[tool_id]
    accepted = upload_formats()[kind]
    assert sorted(options(tool_id, "format")) == sorted(table)
    for suffix in table.values():
        assert suffix in accepted


@pytest.mark.parametrize("tool_id", sorted(SUFFIXES))
def test_every_tool_class_loads_and_is_a_media_tool(tool_id):
    path, _, name = TOOLS[tool_id]["python"].partition(":")
    assert (PLUGIN_ROOT / path).is_file()
    module = importlib.import_module(path[:-3].replace("/", "."))
    assert issubclass(getattr(module, name), MediaTool)


@pytest.mark.parametrize("tool_id", sorted(SUFFIXES))
def test_the_quality_has_three_steps_and_no_number(tool_id):
    assert options(tool_id, "quality") == list(common.QUALITIES)
    assert all(not isinstance(value, (int, float)) for value in options(tool_id, "quality"))


def test_defaults_validate_through_the_core_rules():
    assert params_for("media-convert.image") == {
        "format": "jpeg", "quality": "balanced", "max_side": 0, "background": "#ffffff", "keep_metadata": True,
    }
    assert params_for("media-convert.video") == {
        "format": "mp4", "quality": "balanced", "max_side": 0, "keep_metadata": True,
    }
    assert params_for("media-convert.audio") == {"format": "mp3", "quality": "balanced", "keep_metadata": True}
    assert params_for("media-convert.extract-audio") == {"format": "m4a", "quality": "balanced", "keep_metadata": True}


def test_lossless_formats_hide_the_quality_and_jpeg_alone_shows_the_background():
    assert "quality" not in params_for("media-convert.image", format="png")
    assert "background" not in params_for("media-convert.image", format="webp")
    for fmt in common.LOSSLESS_AUDIO:
        assert "quality" not in params_for("media-convert.audio", format=fmt)
        assert "quality" not in params_for("media-convert.extract-audio", format=fmt)


def test_the_largest_side_is_a_fixed_list_and_never_free_text():
    for tool_id in ("media-convert.image", "media-convert.video"):
        assert options(tool_id, "max_side")[0] == 0
        with pytest.raises(InvalidToolParams):
            params_for(tool_id, max_side=777)
        with pytest.raises(InvalidToolParams):
            params_for(tool_id, format="gif")


def test_the_settings_match_the_code_defaults():
    settings = {entry["name"]: entry for entry in MANIFEST["settings"]}
    assert settings["ffmpeg_threads"]["default"] == common.DEFAULT_THREADS
    assert settings["ffmpeg_threads"]["max"] == common.MAX_THREADS
    assert settings["max_minutes"]["default"] == common.DEFAULT_MAX_MINUTES == 30
    assert settings["max_minutes"]["max"] == common.MAX_MINUTES == 30
    assert settings["load_notice"]["type"] == "info"


def test_the_readme_and_the_reference_are_the_plugin_documentation():
    assert MANIFEST["docs"] == [
        {"path": "README.md", "title": "Media Converter", "audience": "admin"},
        {"path": "docs/reference.md", "title": "Media Converter: reference", "audience": "admin"},
    ]
    for doc in MANIFEST["docs"]:
        assert (PLUGIN_ROOT / doc["path"]).is_file()


def test_a_missing_encoder_skips_the_test_and_names_the_encoder():
    with pytest.raises(pytest.skip.Exception, match="this ffmpeg has no imaginary-codec encoder"):
        need_encoders("imaginary-codec")


def test_every_icon_exists_in_the_menus_of_both_cores():
    assert {entry["icon"] for entry in TOOLS.values()} <= ICONS_ON_BOTH_CORES


def test_a_missing_encoder_while_making_a_source_skips_the_test(tmp_path, monkeypatch):
    monkeypatch.setattr(conftest, "encoders", lambda: frozenset({"aac"}))

    with pytest.raises(pytest.skip.Exception, match="this ffmpeg has no libx264 encoder"):
        make_video(tmp_path / "clip.mp4")
