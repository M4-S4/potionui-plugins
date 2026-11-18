import math
import time
from typing import Callable

from src.plugin_api.media_tools import MediaTool, ToolFailed

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
H265_SAMPLE_SECONDS = 4.0
FALLBACK_RATE = 30.0


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
    return float(getattr(ctx.runner, "timeout", ENCODE_SECONDS) or ENCODE_SECONDS) * H265_SHARE


def minutes_text(seconds: float) -> str:
    count = max(1, math.ceil(seconds / 60))
    return f"{count} minute" if count == 1 else f"{count} minutes"


def too_slow(estimate: float) -> ToolFailed:
    return ToolFailed(
        f"MP4 (H.265) would take about {minutes_text(estimate)} to encode this video on this server, more than "
        "a conversion may take; choose a smaller Largest side, MP4 (H.264), or a shorter video"
    )


def check_h265_time(ctx, sample_args: Callable, width: int, height: int, rate: float, duration) -> None:
    if not duration:
        duration = max_seconds()
    seconds = min(duration, max_seconds() + 1)
    budget = encode_budget(ctx)
    if width * height * rate * seconds <= H265_PIXELS_PER_THREAD_SECOND * threads() * budget:
        return
    sample = min(H265_SAMPLE_SECONDS, seconds)
    started = time.monotonic()
    ctx.ffmpeg([*sample_args(sample), "-f", "null", "-"], duration=sample)
    estimate = (time.monotonic() - started) * seconds / sample
    guard(ctx)
    if estimate > budget:
        raise too_slow(estimate)


class ConvertVideo(MediaTool):
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
        encoder = ctx
        if fmt == "hevc":
            sample = [*thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), "-map", f"0:{picture.index}"]
            if (width, height) != (media.width, media.height):
                sample += ["-vf", f"scale={width}:{height}:flags=lanczos"]
            sample += ["-an", "-sn", "-dn", *video_codec_args(fmt, level)]
            check_h265_time(
                ctx.scoped(0.0, 0.05), lambda seconds: [*sample, "-t", f"{seconds:.3f}", *thread_args()[:2]],
                width, height, picture.rate or media.fps or FALLBACK_RATE, longest(media.duration, streams.duration),
            )
            encoder = ctx.scoped(0.05, 1.0)
        out = ctx.new_path(VIDEO_FORMATS[fmt])
        room = make_room(ctx, output_cap(media.path))
        try:
            args += [*limit_args(room), *thread_args()[:2], str(out)]
            encoder.ffmpeg(args, duration=media.duration)
            guard(ctx)
            check_size(out, room)
        finally:
            release(room)
        check_length(read_streams(out).duration)
        return ctx.probe(out, "video")
