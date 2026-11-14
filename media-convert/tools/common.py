import json
import logging
import math
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.plugin_api import limits
from src.plugin_api.media import find_ffmpeg
from src.plugin_api.media_tools import ToolCancelled, ToolFailed
from src.plugin_api.storage import plugin_settings

from . import PLUGIN_ID

QUALITIES = ("high", "balanced", "small")
DEFAULT_QUALITY = "balanced"

JPEG_QUALITY = {"high": 95, "balanced": 85, "small": 72}
WEBP_QUALITY = {"high": 92, "balanced": 80, "small": 65}
PNG_COMPRESSION = 6

H264_CRF = {"high": 18, "balanced": 23, "small": 28}
H264_PRESET = "medium"
VP9_CRF = {"high": 27, "balanced": 32, "small": 37}
VP9_CPU_USED = 4
VIDEO_AAC_KBPS = {"high": 192, "balanced": 160, "small": 128}
VIDEO_OPUS_KBPS = {"high": 160, "balanced": 128, "small": 96}

MP3_VBR = {"high": 0, "balanced": 2, "small": 5}
AAC_KBPS = {"high": 256, "balanced": 192, "small": 128}
OPUS_KBPS = {"high": 160, "balanced": 128, "small": 96}
FLAC_COMPRESSION = 5

IMAGE_FORMATS = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
IMAGE_NAMES = {"png": "PNG", "jpeg": "JPEG", "webp": "WebP"}
VIDEO_FORMATS = {"mp4": ".mp4", "mov": ".mov", "webm": ".webm"}
VIDEO_NAMES = {"mp4": "MP4", "mov": "MOV", "webm": "WebM"}
AUDIO_FORMATS = {"wav": ".wav", "mp3": ".mp3", "flac": ".flac", "m4a": ".m4a", "ogg": ".ogg"}
AUDIO_NAMES = {"wav": "WAV", "mp3": "MP3", "flac": "FLAC", "m4a": "M4A", "ogg": "OGG"}
LOSSLESS_AUDIO = ("wav", "flac")

DEMUXERS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mp3,wav,flac,ogg,aac"
TEXT_SUBTITLES = frozenset({"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"})

DEFAULT_THREADS = 4
MAX_THREADS = 16
DEFAULT_MAX_MINUTES = 30
MAX_MINUTES = 30
PROBE_TIMEOUT_SECONDS = 30

MAX_IMAGE_PIXELS = 8192 * 8192
MAX_VIDEO_PIXELS = 4096 * 2304
MAX_SOUND_TRACKS = 8
OUTPUT_RATIO = 32
OUTPUT_FLOOR = 1 << 30
OUTPUT_CEILING = 4 << 30
MEGABYTE = 1 << 20
GIGABYTE = 1 << 30
RUN_BUDGET = 8 << 30
DISK_RESERVE = 2 << 30
CONCURRENT_RUNS = 2
MIN_ROOM = 1 << 20
LENGTH_TOLERANCE = 0.5

logger = logging.getLogger("plugins.media-convert")


def quality(params: dict) -> str:
    value = params.get("quality") or DEFAULT_QUALITY
    return value if value in QUALITIES else DEFAULT_QUALITY


def max_side(params: dict) -> Optional[int]:
    value = params.get("max_side") or 0
    return int(value) if int(value) > 0 else None


def settings() -> dict:
    return plugin_settings(PLUGIN_ID) or {}


def threads() -> int:
    try:
        value = int(settings().get("ffmpeg_threads", DEFAULT_THREADS))
    except (TypeError, ValueError):
        value = DEFAULT_THREADS
    return min(MAX_THREADS, max(1, value))


def max_seconds() -> float:
    try:
        minutes = float(settings().get("max_minutes", DEFAULT_MAX_MINUTES))
    except (TypeError, ValueError):
        minutes = DEFAULT_MAX_MINUTES
    return min(float(MAX_MINUTES), max(1.0, minutes)) * 60.0


def minutes(count: int) -> str:
    return f"{count} minute" if count == 1 else f"{count} minutes"


def longest(*durations: Optional[float]) -> Optional[float]:
    known = [value for value in durations if value and value > 0]
    return max(known) if known else None


def check_duration(duration: Optional[float]) -> None:
    limit = max_seconds()
    if duration and duration > limit + LENGTH_TOLERANCE:
        raise ToolFailed(
            f"This file lasts {minutes(math.ceil(duration / 60))}; "
            f"Media Converter takes files of up to {minutes(int(limit // 60))} on this server"
        )


def output_cap(source: Path) -> int:
    return min(OUTPUT_CEILING, max(OUTPUT_FLOOR, OUTPUT_RATIO * Path(source).stat().st_size))


def size_text(count: int) -> str:
    if count >= GIGABYTE and count % GIGABYTE == 0:
        return f"{count // GIGABYTE} GB"
    if count >= MEGABYTE:
        return f"{count // MEGABYTE} MB"
    return f"{max(1, count // 1024)} KB"


@dataclass(eq=False)
class Grant:
    folder: Path
    size: int
    base: int

    def left(self) -> int:
        return max(0, self.size - max(0, scratch_bytes(self.folder) - self.base))


@dataclass(frozen=True)
class Room:
    size: int
    reason: str
    free: Optional[int] = field(default=None, compare=False)
    grant: Optional[Grant] = field(default=None, compare=False, repr=False)


GRANTS: set = set()
GRANTS_LOCK = threading.Lock()


def promised() -> int:
    return sum(grant.left() for grant in list(GRANTS))


def scratch_bytes(folder: Path) -> int:
    total = 0
    for path in Path(folder).rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def storage_limit(user_id: Optional[str], kind: str):
    if not user_id:
        return None
    try:
        return limits.limit_status(user_id, kind)
    except Exception as error:
        logger.warning(
            "Media Converter could not read the %s limit and converts without it: %s", kind, type(error).__name__
        )
        return None


def rooms(ctx, cap: int) -> list:
    folder = Path(ctx.scratch_dir)
    folder.mkdir(parents=True, exist_ok=True)
    written = scratch_bytes(folder)
    found = [Room(int(cap), "file"), Room(RUN_BUDGET - written, "run")]
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        free = None
    if free is not None:
        found.append(Room((free - DISK_RESERVE - promised()) // CONCURRENT_RUNS, "disk", free))
    storage = storage_limit(ctx.user_id, "storage_bytes")
    if storage is not None and storage.remaining is not None:
        found.append(Room(int(storage.remaining) - written, "storage"))
    upload = storage_limit(ctx.user_id, "upload_file_size")
    if upload is not None and upload.limited:
        found.append(Room(int(upload.limit), "upload"))
    return found


def room_message(room: Room) -> str:
    if room.reason == "run":
        return (
            f"This run would write more than {size_text(RUN_BUDGET)}, the most Media Converter writes "
            "in one run; convert fewer items at a time"
        )
    if room.reason == "disk":
        return "The server cannot take this conversion now; try again later or ask an admin"
    if room.reason == "storage":
        return (
            "This result would not fit in what is left of your storage; free some space "
            "or convert fewer items at a time"
        )
    if room.reason == "upload":
        return (
            f"The result would weigh more than {size_text(room.size)}, the largest file you may keep; "
            "choose a lighter format"
        )
    return (
        f"The result would weigh more than {size_text(room.size)}, the most Media Converter writes "
        "for this file; choose a lighter format"
    )


def refuse(room: Room, needed: int) -> None:
    if room.reason == "disk":
        logger.warning(
            "Media Converter refused a conversion for lack of disk space: %s bytes free, %s bytes kept free, "
            "%s bytes for this conversion, at least %s bytes needed",
            room.free, DISK_RESERVE, room.size, needed,
        )
    raise ToolFailed(room_message(room))


def make_room(ctx, cap: int, needed: int = 0, unstoppable: int = 0) -> Room:
    with GRANTS_LOCK:
        found = rooms(ctx, cap)
        for item in found:
            if item.reason == "disk" and item.size < unstoppable:
                refuse(item, unstoppable)
        room = min(found, key=lambda item: item.size)
        if room.size < max(MIN_ROOM, needed):
            refuse(room, max(MIN_ROOM, needed))
        folder = Path(ctx.scratch_dir)
        grant = Grant(folder, max(room.size, unstoppable), scratch_bytes(folder))
        GRANTS.add(grant)
    return Room(room.size, room.reason, room.free, grant)


def release(room: Room) -> None:
    with GRANTS_LOCK:
        GRANTS.discard(room.grant)


def limit_args(room: Room) -> list[str]:
    return ["-t", f"{max_seconds() + 1:.3f}", "-fs", str(room.size)]


def check_size(out: Path, room: Room) -> None:
    written = Path(out).stat().st_size
    if written >= room.size:
        refuse(room, written)


def check_length(duration: Optional[float]) -> None:
    limit = max_seconds()
    if duration and duration > limit + LENGTH_TOLERANCE:
        raise ToolFailed(
            f"This file lasts more than {minutes(int(limit // 60))}; "
            f"Media Converter takes files of up to {minutes(int(limit // 60))} on this server"
        )


def guard(ctx) -> None:
    if ctx.is_cancelled():
        raise ToolCancelled()


def fit(width: int, height: int, limit: Optional[int], even: bool) -> tuple[int, int]:
    if limit and max(width, height) > limit:
        scale = limit / max(width, height)
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
    if even:
        width, height = max(2, width - width % 2), max(2, height - height % 2)
    return width, height


def input_args(path: Path, max_pixels: Optional[int] = None) -> list[str]:
    decoder = ["-max_pixels", str(max_pixels)] if max_pixels else []
    return [
        "-protocol_whitelist", "file", "-format_whitelist", DEMUXERS, *decoder, "-i", str(Path(path).resolve()),
    ]


def thread_args() -> list[str]:
    count = str(threads())
    return ["-threads", count, "-filter_threads", count]


@dataclass(frozen=True)
class Stream:
    index: int
    kind: str
    codec: str
    channels: int = 0
    sample_rate: int = 0
    attached: bool = False
    tags: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Streams:
    streams: tuple
    tags: dict
    duration: Optional[float] = None

    @property
    def video(self) -> Optional[Stream]:
        return next((s for s in self.streams if s.kind == "video" and not s.attached), None)

    @property
    def audio(self) -> list:
        return [s for s in self.streams if s.kind == "audio"]

    @property
    def text_subtitles(self) -> list:
        return [s for s in self.streams if s.kind == "subtitle" and s.codec in TEXT_SUBTITLES]

    @property
    def other_subtitles(self) -> list:
        return [s for s in self.streams if s.kind == "subtitle" and s.codec not in TEXT_SUBTITLES]


def ffprobe_binary() -> str:
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        sibling = Path(ffmpeg).with_name(Path(ffmpeg).name.replace("ffmpeg", "ffprobe"))
        if sibling.is_file():
            return str(sibling)
    found = shutil.which("ffprobe")
    if not found:
        raise ToolFailed("ffprobe is not available on this server")
    return found


def read_streams(path: Path) -> Streams:
    command = [
        ffprobe_binary(), "-v", "error", "-protocol_whitelist", "file", "-format_whitelist", DEMUXERS,
        "-print_format", "json", "-show_format", "-show_streams", str(Path(path).resolve()),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=PROBE_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
        payload = json.loads(result.stdout or "{}") if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = None
    if payload is None:
        raise ToolFailed("Media Converter cannot read this file")
    streams = tuple(
        Stream(
            index=int(item.get("index", 0)),
            kind=str(item.get("codec_type") or ""),
            codec=str(item.get("codec_name") or ""),
            channels=int(item.get("channels") or 0),
            sample_rate=int(item.get("sample_rate") or 0),
            attached=bool((item.get("disposition") or {}).get("attached_pic")),
            tags=dict(item.get("tags") or {}),
        )
        for item in payload.get("streams") or []
    )
    container = payload.get("format") or {}
    try:
        duration = float(container.get("duration")) if container.get("duration") else None
    except (TypeError, ValueError):
        duration = None
    return Streams(streams=streams, tags=dict(container.get("tags") or {}), duration=duration)


def metadata_args(streams: Streams, audio: Optional[Stream], keep: bool) -> list[str]:
    if not keep:
        return ["-map_metadata", "-1", "-map_chapters", "-1"]
    if not streams.tags and audio is not None and audio.tags:
        return ["-map_metadata", f"0:s:{audio.index}", "-map_chapters", "0"]
    return ["-map_metadata", "0", "-map_chapters", "0"]
