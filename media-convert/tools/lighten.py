import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    H264_PRESET,
    LENGTH_TOLERANCE,
    MAX_VIDEO_PIXELS,
    MEGABYTE,
    check_duration,
    fit,
    guard,
    input_args,
    longest,
    make_room,
    max_seconds,
    metadata_args,
    read_streams,
    refuse,
    release,
    thread_args,
)

TARGETS_MB = (8, 16, 18, 20, 30, 50)
DEFAULT_TARGET_MB = 16
MEGABYTE_SI = 1000 * 1000
MARGIN = 0.04
SOURCE_GROWTH = 1.5
AUDIO_STEPS_KBPS = ((1000, 128), (500, 96), (0, 64))
MIN_AUDIO_KBPS = 64
MIN_VIDEO_KBPS = 150
SMALLEST_VIDEO_KBPS = 32
BITS_PER_PIXEL = 0.04
SIDES = (1920, 1280, 960, 640, 480)
FALLBACK_RATE = 30.0
PASS_BYTES_PER_MACROBLOCK = 2
PASS_BYTES_PER_FRAME = 512
COPY_CONTAINERS = (".mp4", ".mov", ".m4v")
COPY_PIXELS = ("yuv420p", "yuvj420p")


@dataclass(frozen=True)
class Plan:
    video_kbps: int
    audio_kbps: int
    width: int
    height: int


def target_bytes(params: dict) -> int:
    value = int(params.get("target") or DEFAULT_TARGET_MB)
    if value not in TARGETS_MB:
        raise ToolFailed(f"Media Converter cannot aim at {value} MB")
    return value * MEGABYTE_SI


def length_text(seconds: float) -> str:
    if seconds < 120:
        return f"{math.ceil(seconds)} seconds"
    return f"{math.ceil(seconds / 60)} minutes"


def audio_kbps(total_kbps: float, track) -> int:
    if track is None:
        return 0
    rate = next(kbps for floor, kbps in AUDIO_STEPS_KBPS if total_kbps >= floor)
    if track.bit_rate:
        rate = min(rate, max(32, math.ceil(track.bit_rate / 1000)))
    return rate


def smallest_mb(duration: float, with_sound: bool) -> int:
    kbps = MIN_VIDEO_KBPS + (MIN_AUDIO_KBPS if with_sound else 0)
    return math.ceil(kbps * 1000 * duration / 8 / (1 - MARGIN) / MEGABYTE_SI)


def impossible(target: int, duration: float, with_sound: bool) -> ToolFailed:
    smallest = smallest_mb(duration, with_sound)
    larger = [size for size in TARGETS_MB if size >= smallest]
    message = (
        f"This video lasts {length_text(duration)}: to fit in {target // MEGABYTE_SI} MB, its picture would be "
        f"too poor to watch. The smallest file Media Converter can make from it weighs about {smallest} MB"
    )
    if larger:
        message += f"; choose {larger[0]} MB or more"
    else:
        message += "; trim it into shorter parts first"
    if with_sound and smallest_mb(duration, False) <= target // MEGABYTE_SI:
        message += ", or turn off Keep the sound"
    return ToolFailed(message)


def plan(media, streams, track, target: int, duration: float) -> Plan:
    budget = target * (1 - MARGIN)
    target_kbps = budget * 8 / duration / 1000
    audio_at_target = audio_kbps(target_kbps, track)
    if target_kbps - audio_at_target < MIN_VIDEO_KBPS:
        raise impossible(target, duration, track is not None)
    source_kbps = Path(media.path).stat().st_size * 8 / duration / 1000
    total = min(target_kbps, source_kbps * SOURCE_GROWTH)
    audio = min(audio_kbps(total, track), audio_at_target)
    video = max(SMALLEST_VIDEO_KBPS, int(total - audio))
    rate = (streams.video.rate if streams.video else None) or media.fps or FALLBACK_RATE
    for side in (max(media.width, media.height), *SIDES):
        if side > max(media.width, media.height):
            continue
        width, height = fit(media.width, media.height, side, even=True)
        if video * 1000 / (width * height * rate) >= BITS_PER_PIXEL:
            break
    return Plan(video, audio, width, height)


def pass_log_bytes(duration: float, rate: float, width: int, height: int) -> int:
    frames = math.ceil(min(duration, max_seconds() + 1) * rate) + 1
    macroblocks = math.ceil(width / 16) * math.ceil(height / 16)
    return frames * (macroblocks * PASS_BYTES_PER_MACROBLOCK + PASS_BYTES_PER_FRAME) + MEGABYTE


def copyable(media, streams, track) -> bool:
    picture = streams.video
    if Path(media.path).suffix.lower() not in COPY_CONTAINERS or picture is None:
        return False
    if picture.codec != "h264" or picture.pix_fmt not in COPY_PIXELS:
        return False
    return track is None or (track.codec == "aac" and track.channels <= 2)


def scratch_files(prefix: Path) -> list:
    return sorted(prefix.parent.glob(prefix.name + "-*"))


class LightenVideo(MediaTool):
    def run(self, inputs, params, ctx):
        return [self.lighten(media, params, ctx) for media in inputs]

    def lighten(self, media, params, ctx):
        target = target_bytes(params)
        keep_sound = bool(params.get("keep_sound", True))
        keep = bool(params.get("keep_metadata", False))
        check_duration(media.duration)
        if not media.width or not media.height:
            raise ToolFailed("Media Converter cannot read the size of this video")
        if media.width * media.height > MAX_VIDEO_PIXELS:
            raise ToolFailed(
                f"This video is {media.width} × {media.height} pixels; Media Converter takes videos "
                "of up to 4096 × 2304 pixels (about 9.4 million)"
            )
        guard(ctx)
        streams = read_streams(media.path)
        check_duration(streams.duration)
        if streams.video is None:
            raise ToolFailed("This video has no picture to convert")
        duration = longest(media.duration, streams.duration)
        if not duration:
            raise ToolFailed("Media Converter cannot read the length of this video")
        track = streams.audio[0] if keep_sound and streams.audio else None
        if Path(media.path).stat().st_size < target and copyable(media, streams, track):
            copied = self.copy(media, streams, track, keep, target, ctx)
            if copied is not None:
                return copied
        return self.encode(media, streams, track, keep, target, duration, ctx)

    def mapping(self, media, streams, track) -> list[str]:
        args = ["-map", f"0:{streams.video.index}"]
        if track is not None:
            args += ["-map", f"0:{track.index}"]
        return args

    def copy(self, media, streams, track, keep, target, ctx):
        out = ctx.new_path(".mp4")
        room = make_room(ctx, target, needed=Path(media.path).stat().st_size)
        try:
            ctx.ffmpeg(
                [
                    *input_args(media.path), *self.mapping(media, streams, track), "-sn", "-dn", "-c", "copy",
                    *metadata_args(streams, None, keep), "-movflags", "+faststart",
                    "-t", f"{max_seconds() + 1:.3f}", "-fs", str(room.size), str(out),
                ],
                duration=media.duration,
            )
            guard(ctx)
            written = out.stat().st_size
        finally:
            release(room)
        if written >= target:
            out.unlink(missing_ok=True)
            return None
        return ctx.probe(out, "video")

    def encode(self, media, streams, track, keep, target, duration, ctx):
        chosen = plan(media, streams, track, target, duration)
        rate = streams.video.rate or media.fps or FALLBACK_RATE
        logs = pass_log_bytes(duration, rate, chosen.width, chosen.height)
        prefix = ctx.new_path("", stem="pass")
        room = make_room(ctx, target + logs, needed=target + logs)
        outputs = []
        try:
            self.first_pass(media, streams, chosen, prefix, ctx.scoped(0.0, 0.4))
            guard(ctx)
            out = self.second_pass(media, streams, track, keep, chosen, prefix, room, ctx.scoped(0.4, 0.9))
            outputs.append(out)
            guard(ctx)
            written = out.stat().st_size
            if written >= target:
                budget = target * (1 - MARGIN)
                cut = math.ceil((written - budget) * 8 / duration / 1000) + 1
                retry = Plan(max(SMALLEST_VIDEO_KBPS, chosen.video_kbps - cut), chosen.audio_kbps, chosen.width, chosen.height)
                out.unlink(missing_ok=True)
                out = self.second_pass(media, streams, track, keep, retry, prefix, room, ctx.scoped(0.9, 1.0))
                outputs.append(out)
                guard(ctx)
                written = out.stat().st_size
            if written >= target:
                raise ToolFailed(
                    f"Media Converter could not bring this video under {target // MEGABYTE_SI} MB; "
                    "choose a larger size"
                )
            if written >= self.limit(room, prefix):
                refuse(room, written)
        except BaseException:
            for path in outputs:
                path.unlink(missing_ok=True)
            raise
        finally:
            for path in scratch_files(prefix):
                path.unlink(missing_ok=True)
            release(room)
        made = read_streams(out).duration
        if made is None or made < duration - LENGTH_TOLERANCE:
            out.unlink(missing_ok=True)
            refuse(room, target)
        return ctx.probe(out, "video")

    def video_args(self, media, chosen: Plan, prefix: Path, number: int) -> list[str]:
        args = []
        if (chosen.width, chosen.height) != (media.width, media.height):
            args += ["-vf", f"scale={chosen.width}:{chosen.height}:flags=lanczos"]
        return [
            *args, "-fps_mode", "vfr", "-c:v", "libx264", "-preset", H264_PRESET,
            "-b:v", f"{chosen.video_kbps}k", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-pass", str(number), "-passlogfile", str(prefix),
        ]

    def first_pass(self, media, streams, chosen, prefix, ctx):
        ctx.ffmpeg(
            [
                *thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), "-map", f"0:{streams.video.index}",
                "-an", "-sn", "-dn", *self.video_args(media, chosen, prefix, 1),
                "-t", f"{max_seconds() + 1:.3f}", *thread_args()[:2], "-f", "null", "-",
            ],
            duration=media.duration,
        )

    def limit(self, room, prefix: Path) -> int:
        return room.size - sum(path.stat().st_size for path in scratch_files(prefix))

    def second_pass(self, media, streams, track, keep, chosen, prefix, room, ctx) -> Path:
        out = ctx.new_path(".mp4")
        sound = []
        if track is not None:
            sound = ["-c:a", "aac", "-b:a", f"{chosen.audio_kbps}k"]
            if track.channels > 2:
                sound += ["-ac", "2"]
        ctx.ffmpeg(
            [
                *thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), *self.mapping(media, streams, track),
                "-sn", "-dn", *self.video_args(media, chosen, prefix, 2), *sound,
                *metadata_args(streams, None, keep), "-movflags", "+faststart",
                "-t", f"{max_seconds() + 1:.3f}", "-fs", str(self.limit(room, prefix)), *thread_args()[:2], str(out),
            ],
            duration=media.duration,
        )
        return out
