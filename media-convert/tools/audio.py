from pathlib import Path

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    AAC_KBPS,
    AUDIO_FORMATS,
    AUDIO_NAMES,
    FLAC_COMPRESSION,
    LOSSLESS_AUDIO,
    MEGABYTE,
    MP3_VBR,
    OPUS_KBPS,
    OUTPUT_CEILING,
    check_duration,
    check_length,
    check_size,
    guard,
    input_args,
    limit_args,
    longest,
    make_room,
    max_seconds,
    metadata_args,
    output_cap,
    quality,
    read_streams,
    release,
    thread_args,
)

SAME_SUFFIXES = {"wav": (".wav",), "flac": (".flac",)}
EMPTY_SOUND = "This sound is empty: there is nothing to convert"
EMPTY_FROM_VIDEO = "The sound of this video is empty: there is nothing to extract"
LOSSY_BYTES_PER_SECOND = 64000
SOUND_MARGIN = 1.02


def codec_args(fmt: str, level: str, bit_depth, channels: int) -> list[str]:
    if fmt == "wav":
        return ["-c:a", "pcm_s24le" if (bit_depth or 0) > 16 else "pcm_s16le"]
    if fmt == "flac":
        return ["-c:a", "flac", "-compression_level", str(FLAC_COMPRESSION)]
    if fmt == "mp3":
        args = ["-c:a", "libmp3lame", "-q:a", str(MP3_VBR[level])]
    elif fmt == "m4a":
        args = ["-c:a", "aac", "-b:a", f"{AAC_KBPS[level]}k"]
    else:
        args = ["-c:a", "libopus", "-b:a", f"{OPUS_KBPS[level]}k"]
    if fmt == "ogg" and channels > 2:
        args += ["-ac", "2"]
    return args


def sample_width(fmt: str, bit_depth) -> int:
    if fmt == "wav":
        return 3 if (bit_depth or 0) > 16 else 2
    if fmt == "flac":
        return 2 if bit_depth and bit_depth <= 16 else 4
    return 2


def sound_cap(fmt: str, bit_depth, track, source, duration) -> int:
    if not track.sample_rate or not track.channels:
        return output_cap(source)
    per_second = track.sample_rate * track.channels * sample_width(fmt, bit_depth)
    if fmt not in LOSSLESS_AUDIO:
        per_second = max(per_second, LOSSY_BYTES_PER_SECOND)
    cap = min(OUTPUT_CEILING, int((max_seconds() + 1) * per_second * SOUND_MARGIN) + MEGABYTE)
    return cap if duration else min(cap, output_cap(source))


def sound_needed(fmt: str, bit_depth, track, duration) -> int:
    if fmt != "wav" or not track.sample_rate or not track.channels or not duration:
        return 0
    seconds = min(duration, max_seconds())
    return int(seconds * track.sample_rate * track.channels * sample_width(fmt, bit_depth))


def encode_audio(media, params, ctx, *, from_video: bool):
    fmt = params.get("format") or ("m4a" if from_video else "mp3")
    if fmt not in AUDIO_FORMATS:
        raise ToolFailed(f"Media Converter cannot write {fmt} sound files")
    if not from_video and fmt in LOSSLESS_AUDIO and Path(media.path).suffix.lower() in SAME_SUFFIXES[fmt]:
        raise ToolFailed(f"This sound is already a {AUDIO_NAMES[fmt]} file; choose another format")
    level = quality(params)
    keep = bool(params.get("keep_metadata", True))
    check_duration(media.duration)
    guard(ctx)
    streams = read_streams(media.path)
    if not streams.audio:
        raise ToolFailed("This video has no sound to extract" if from_video else "This file has no sound")
    check_duration(streams.duration)
    track = streams.audio[0]
    out = ctx.new_path(AUDIO_FORMATS[fmt])
    duration = longest(media.duration, streams.duration)
    room = make_room(
        ctx,
        sound_cap(fmt, media.bit_depth, track, media.path, duration),
        needed=sound_needed(fmt, media.bit_depth, track, duration),
    )
    try:
        args = [*thread_args(), *input_args(media.path), "-map", f"0:{track.index}", "-vn", "-sn", "-dn"]
        args += codec_args(fmt, level, media.bit_depth, track.channels)
        args += metadata_args(streams, track, keep)
        if fmt == "m4a":
            args += ["-movflags", "+faststart"]
        args += [*limit_args(room), *thread_args()[:2], str(out)]
        ctx.ffmpeg(args, duration=media.duration)
        guard(ctx)
        check_size(out, room)
    finally:
        release(room)
    try:
        result = read_streams(out)
    except ToolFailed:
        result = None
    if result is None or not result.audio or not result.duration:
        raise ToolFailed(EMPTY_FROM_VIDEO if from_video else EMPTY_SOUND)
    check_length(result.duration)
    return ctx.probe(out, "audio")


class ConvertAudio(MediaTool):
    def run(self, inputs, params, ctx):
        return [encode_audio(media, params, ctx, from_video=False) for media in inputs]
