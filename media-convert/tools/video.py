import math
import os
import time
from pathlib import Path
from typing import Callable, Optional

from src.plugin_api.media_tools import InvalidToolParams, MediaTool, ToolFailed

from .common import (
    H264_CRF,
    H264_PRESET,
    H265_CRF,
    H265_PRESET,
    MAX_SOUND_TRACKS,
    MAX_VIDEO_PIXELS,
    VIDEO_AAC_KBPS,
    VIDEO_FORMATS,
    VIDEO_OPUS_KBPS,
    VP9_CPU_USED,
    VP9_CRF,
    check_duration,
    check_length,
    check_size,
    count_frames,
    fit,
    guard,
    h265_allowed,
    input_args,
    limit_args,
    longest,
    make_room,
    max_seconds,
    max_side,
    metadata_args,
    output_cap,
    quality,
    read_streams,
    release,
    thread_args,
    threads,
)

H265_OFF = (
    "MP4 (H.265) is turned off on this server: an admin can allow it in Admin › Plugins › Media Converter › "
    "Settings. Choose MP4 (H.264) meanwhile"
)
ENCODE_SECONDS = 1800.0
H265_SHARE = 0.6
H265_PIXELS_PER_THREAD_SECOND = 2_500_000
H265_SAMPLES = (0.25, 0.5, 0.75)
H265_SAMPLE_SECONDS = 2.0
H265_SAMPLE_FRAMES = 120
CAP_FALLBACK_RATE = 60.0
FRAME_SLACK = 1.02


def video_codec_args(fmt: str, level: str) -> list[str]:
    if fmt == "hevc":
        return [
            "-c:v", "libx265", "-preset", H265_PRESET, "-crf", str(H265_CRF[level]),
            "-x265-params", f"pools={threads()}:log-level=error",
            "-pix_fmt", "yuv420p", "-profile:v", "main", "-tag:v", "hvc1",
        ]
    if fmt == "webm":
        return [
            "-c:v", "libvpx-vp9", "-crf", str(VP9_CRF[level]), "-b:v", "0",
            "-deadline", "good", "-cpu-used", str(VP9_CPU_USED), "-row-mt", "1", "-pix_fmt", "yuv420p",
        ]
    return [
        "-c:v", "libx264", "-preset", H264_PRESET, "-crf", str(H264_CRF[level]),
        "-pix_fmt", "yuv420p", "-profile:v", "high",
    ]


def audio_codec_args(fmt: str, level: str, tracks: list) -> list[str]:
    if not tracks:
        return []
    if fmt == "webm":
        args = ["-c:a", "libopus", "-b:a", f"{VIDEO_OPUS_KBPS[level]}k"]
        for number, track in enumerate(tracks):
            if track.channels > 2:
                args += [f"-ac:a:{number}", "2"]
        return args
    return ["-c:a", "aac", "-b:a", f"{VIDEO_AAC_KBPS[level]}k"]


def encode_budget(ctx) -> float:
    try:
        value = float(getattr(ctx.runner, "timeout", ENCODE_SECONDS))
    except (TypeError, ValueError, OverflowError):
        value = ENCODE_SECONDS
    if not math.isfinite(value) or value <= 0:
        value = ENCODE_SECONDS
    return min(value, ENCODE_SECONDS) * H265_SHARE


CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
CFS_QUOTA = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
CFS_PERIOD = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")


def quota_cores() -> Optional[int]:
    try:
        quota, period = CPU_MAX.read_text(encoding="ascii").split()[:2]
    except (OSError, ValueError):
        try:
            quota, period = CFS_QUOTA.read_text(encoding="ascii").strip(), CFS_PERIOD.read_text(encoding="ascii").strip()
        except OSError:
            return None
    try:
        allowed, length = int(quota), int(period)
    except ValueError:
        return None
    if allowed <= 0 or length <= 0:
        return None
    return max(1, math.ceil(allowed / length))


def server_cores() -> int:
    found = os.cpu_count() or 1
    try:
        found = min(found, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    limit = quota_cores()
    return max(1, min(found, limit) if limit else found)


def usable_threads() -> int:
    return max(1, min(threads(), server_cores()))


def minutes_text(seconds: float) -> str:
    count = max(1, math.ceil(seconds / 60))
    return f"{count} minute" if count == 1 else f"{count} minutes"


def too_slow(estimate: float) -> ToolFailed:
    return ToolFailed(
        f"MP4 (H.265) would take about {minutes_text(estimate)} to encode this video on this server, more than "
        "a conversion may take; choose a smaller Largest side, MP4 (H.264), or a shorter video"
    )


def sample_starts(seconds: float, length: float) -> list[float]:
    return [min(max(0.0, seconds * point - length / 2), max(0.0, seconds - length)) for point in H265_SAMPLES]


def sample_frames(frames: int, seconds: float) -> int:
    wanted = math.ceil(frames * H265_SAMPLE_SECONDS / seconds) if seconds > 0 else H265_SAMPLE_FRAMES
    return max(1, min(wanted, H265_SAMPLE_FRAMES, frames // len(H265_SAMPLES) or 1))


def check_h265_time(ctx, sample_args: Callable, width: int, height: int, frames: int, seconds: float, counted: bool) -> None:
    budget = encode_budget(ctx)
    if counted and width * height * frames <= H265_PIXELS_PER_THREAD_SECOND * usable_threads() * budget:
        return
    each = sample_frames(frames, seconds)
    length = each * seconds / frames
    slowest = 0.0
    for number, start in enumerate(sample_starts(seconds, length)):
        began = time.monotonic()
        ctx.scoped(number / len(H265_SAMPLES), (number + 1) / len(H265_SAMPLES)).ffmpeg(
            [*sample_args(start, each), "-f", "null", "-"], duration=length,
        )
        slowest = max(slowest, time.monotonic() - began)
        guard(ctx)
    estimate = slowest * frames / each
    if estimate > budget:
        raise too_slow(estimate)


class ConvertVideo(MediaTool):
    def check_params(self, params: dict) -> None:
        if params.get("format") == "hevc" and not h265_allowed():
            raise InvalidToolParams("format", H265_OFF)

    def run(self, inputs, params, ctx):
        return [self.convert(media, params, ctx) for media in inputs]

    def convert(self, media, params, ctx):
        fmt = params.get("format") or "mp4"
        if fmt not in VIDEO_FORMATS:
            raise ToolFailed(f"Media Converter cannot write {fmt} videos")
        if fmt == "hevc" and not h265_allowed():
            raise ToolFailed(H265_OFF)
        level = quality(params)
        keep = bool(params.get("keep_metadata", True))
        check_duration(media.duration)
        if not media.width or not media.height:
            raise ToolFailed("Media Converter cannot read the size of this video")
        if media.width * media.height > MAX_VIDEO_PIXELS:
            raise ToolFailed(
                f"This video is {media.width} × {media.height} pixels; Media Converter takes videos "
                "of up to 4096 × 2304 pixels (about 9.4 million)"
            )
        if min(fit(media.width, media.height, max_side(params), even=False)) < 2:
            raise ToolFailed("This video is too small: a converted video needs at least 2 pixels on each side")
        guard(ctx)
        streams = read_streams(media.path)
        check_duration(streams.duration)
        picture = streams.video
        if picture is None:
            raise ToolFailed("This video has no picture to convert")
        width, height = fit(media.width, media.height, max_side(params), even=True)
        tracks = streams.audio[:MAX_SOUND_TRACKS] if keep else streams.audio[:1]
        subtitles = streams.text_subtitles if keep else []
        args = [*thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), "-map", f"0:{picture.index}"]
        for stream in [*tracks, *subtitles]:
            args += ["-map", f"0:{stream.index}"]
        if (width, height) != (media.width, media.height):
            args += ["-vf", f"scale={width}:{height}:flags=lanczos"]
        args += ["-fps_mode", "vfr", *video_codec_args(fmt, level)]
        args += audio_codec_args(fmt, level, tracks)
        if subtitles:
            args += ["-c:s", "webvtt" if fmt == "webm" else "mov_text"]
        args += metadata_args(streams, None, keep)
        if fmt != "webm":
            args += ["-movflags", "+faststart"]
        out = ctx.new_path(VIDEO_FORMATS[fmt])
        room = make_room(ctx, output_cap(media.path))
        try:
            encoder = ctx
            if fmt == "hevc":
                sample = [*input_args(media.path, MAX_VIDEO_PIXELS), "-map", f"0:{picture.index}"]
                if (width, height) != (media.width, media.height):
                    sample += ["-vf", f"scale={width}:{height}:flags=lanczos"]
                sample += ["-an", "-sn", "-dn", *video_codec_args(fmt, level)]
                seconds = min(
                    longest(media.duration, streams.duration, picture.duration) or max_seconds(), max_seconds() + 1,
                )
                counted = count_frames(media.path, picture.index, ctx.is_cancelled)
                guard(ctx)
                frames = counted or math.ceil(seconds * (picture.rate or media.fps or CAP_FALLBACK_RATE) * FRAME_SLACK) + 2
                check_h265_time(
                    ctx.scoped(0.0, 0.05),
                    lambda start, count: [
                        *thread_args(), "-ss", f"{start:.3f}", *sample, "-frames:v", str(count), *thread_args()[:2],
                    ],
                    width, height, frames, seconds, counted is not None,
                )
                encoder = ctx.scoped(0.05, 1.0)
            args += [*limit_args(room), *thread_args()[:2], str(out)]
            encoder.ffmpeg(args, duration=media.duration)
            guard(ctx)
            check_size(out, room)
        finally:
            release(room)
        check_length(read_streams(out).duration)
        return ctx.probe(out, "video")
