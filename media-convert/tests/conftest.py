import functools
import importlib
import json
import re
import shutil
import subprocess
import sys
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

for _key in list(sys.modules):
    if _key.split(".", 1)[0] == "tools":
        del sys.modules[_key]

if str(PLUGIN_ROOT) in sys.path:
    sys.path.remove(str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT))

importlib.invalidate_caches()
import tools

from src.plugin_api.media import find_ffmpeg
from src.plugin_api.media_tools import ToolContext, validate_params

MANIFEST = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))
TOOLS = {entry["id"]: entry for entry in MANIFEST["media_tools"]}
ENCODER_LINE = re.compile(r"^\s*[VAS][A-Z.]{5}\s+(\S+)")
CODEC_FLAGS = ("-c", "-c:v", "-c:a", "-c:s", "-codec", "-vcodec", "-acodec")
ROOMY_DISK = namedtuple("Usage", "total used free")(256 << 30, 192 << 30, 64 << 30)
TARGET_ENCODERS = {
    "mp4": ("libx264", "aac"),
    "mov": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
    "wav": ("pcm_s16le", "pcm_s24le"),
    "mp3": ("libmp3lame",),
    "flac": ("flac",),
    "m4a": ("aac",),
    "ogg": ("libopus",),
}


def ffmpeg_binary():
    found = find_ffmpeg()
    if not found:
        pytest.skip("ffmpeg is not available")
    return found


def ffprobe_binary():
    ffmpeg = Path(ffmpeg_binary())
    sibling = ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe"))
    found = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    if not found:
        pytest.skip("ffprobe is not available")
    return found


@functools.lru_cache(maxsize=1)
def encoders():
    result = subprocess.run([ffmpeg_binary(), "-hide_banner", "-encoders"], capture_output=True, text=True)
    return frozenset(m.group(1) for m in map(ENCODER_LINE.match, result.stdout.splitlines()) if m)


def need_encoders(*names):
    missing = [name for name in names if name not in encoders()]
    if missing:
        pytest.skip(f"this ffmpeg has no {', '.join(missing)} encoder")


def need_target(fmt):
    need_encoders(*TARGET_ENCODERS[fmt])


def codecs_in(args):
    args = [str(arg) for arg in args]
    return [value for flag, value in zip(args, args[1:]) if flag in CODEC_FLAGS and value != "copy"]


def run_ffmpeg(*args):
    need_encoders(*codecs_in(args))
    subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *map(str, args)],
        check=True, capture_output=True,
    )


def piped(path, *args):
    need_encoders(*codecs_in(args))
    with open(path, "wb") as out:
        subprocess.run(
            [ffmpeg_binary(), "-hide_banner", "-nostdin", "-loglevel", "error", *map(str, args), "pipe:1"],
            stdout=out, check=True,
        )
    return Path(path)


def stream_bytes(path, selector):
    result = subprocess.run(
        [ffprobe_binary(), "-v", "error", "-select_streams", selector, "-show_entries", "packet=size", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return sum(int(line.split(",")[0]) for line in result.stdout.split() if line.strip())


def probe(path):
    result = subprocess.run(
        [ffprobe_binary(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", str(path)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def streams_of(path, kind):
    return [s for s in probe(path)["streams"] if s["codec_type"] == kind]


def frame_count(path):
    result = subprocess.run(
        [ffprobe_binary(), "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip().split(",")[0])


def make_video(path, *, seconds=1.0, size=(64, 48), fps=10, audio=True, extra=(), source="testsrc"):
    args = ["-f", "lavfi", "-i", f"{source}=size={size[0]}x{size[1]}:rate={fps}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}"]
    args += ["-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-b:a", "96k"]
    args += [*extra, str(path)]
    run_ffmpeg(*args)
    return Path(path)


def make_audio(path, *, seconds=1.0, codec_args=(), rate=44100, channels=1, extra=()):
    layout = {1: "mono", 2: "stereo", 6: "5.1"}[channels]
    run_ffmpeg(
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}:duration={seconds}",
        "-af", f"aformat=channel_layouts={layout}", *codec_args, *extra, str(path),
    )
    return Path(path)


def make_image(path, *, size=(64, 48), mode="RGB", color=(200, 40, 40), **save):
    Image.new(mode, size, color).save(path, **save)
    return Path(path)


def noisy_image(path, *, size=(256, 192), **save):
    image = Image.effect_noise(size, 64).convert("RGB")
    image.save(path, **save)
    return Path(path)


def spec_for(tool_id):
    entry = TOOLS[tool_id]
    return SimpleNamespace(id=tool_id, label=entry["label"], params=entry.get("params") or [], impl=None)


def params_for(tool_id, **given):
    return validate_params(spec_for(tool_id), given)


@pytest.fixture(autouse=True)
def server_settings(monkeypatch):
    from tools import common

    values = {"ffmpeg_threads": 4, "max_minutes": 30}
    monkeypatch.setattr(common, "plugin_settings", lambda plugin_id: values)
    return values


@pytest.fixture(autouse=True)
def roomy_disk(monkeypatch):
    from tools import common

    monkeypatch.setattr(common.shutil, "disk_usage", lambda path: ROOMY_DISK)
    return ROOMY_DISK


@pytest.fixture(autouse=True)
def no_grants(monkeypatch):
    from tools import common

    fresh = set()
    monkeypatch.setattr(common, "GRANTS", fresh)
    return fresh


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(tmp_path / "scratch")


@pytest.fixture
def source_dir(tmp_path):
    folder = tmp_path / "sources"
    folder.mkdir()
    return folder
