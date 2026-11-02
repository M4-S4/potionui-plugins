import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.platform.util.video_transcode import TranscodeSpec, build_transcode_command

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / "video-producer"
PACKAGE = "video_producer_delivery_under_test"

SETTINGS = ("-vf", "-c:v", "-crf", "-preset", "-pix_fmt", "-movflags", "-c:a", "-b:a", "-f")


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


video = _plugin_module("backend.exports.video")


def _settings(command):
    return {option: command[command.index(option) + 1] for option in SETTINGS}


@pytest.mark.parametrize("size, fps", [((1920, 1080), 24), ((3840, 2160), 25), ((720, 1280), 30)])
def test_the_video_producer_delivery_run_keeps_the_settings_of_the_host_converter(tmp_path, size, fps):
    mezzanine, final = tmp_path / "mezzanine.mp4", tmp_path / "final.mp4"
    spec = TranscodeSpec(container="mp4", max_width=size[0], fps=float(fps), keep_audio=True)

    plugin = video.convert_command("ffmpeg", mezzanine, final, size, fps)
    host = build_transcode_command("ffmpeg", mezzanine, final, spec)

    assert _settings(plugin) == _settings(host)
