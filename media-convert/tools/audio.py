from pathlib import Path

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    AAC_KBPS,
    AUDIO_FORMATS,
    AUDIO_NAMES,
    FLAC_COMPRESSION,
    LOSSLESS_AUDIO,
    MP3_VBR,
    OPUS_KBPS,
    check_duration,
    check_length,
    check_size,
    guard,
    input_args,
    limit_args,
    metadata_args,
    quality,
    read_streams,
    thread_args,
)

SAME_SUFFIXES = {"wav": (".wav",), "flac": (".flac",)}
EMPTY_SOUND = "This sound is empty: there is nothing to convert"
EMPTY_FROM_VIDEO = "The sound of this video is empty: there is nothing to extract"


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
    check_duration(streams.duration)
    if not streams.audio:
        raise ToolFailed("This video has no sound to extract" if from_video else "This file has no sound")
    track = streams.audio[0]
    out = ctx.new_path(AUDIO_FORMATS[fmt])
    args = [*thread_args(), *input_args(media.path), "-map", f"0:{track.index}", "-vn", "-sn", "-dn"]
    args += codec_args(fmt, level, media.bit_depth, track.channels)
    args += metadata_args(streams, track, keep)
    if fmt == "m4a":
        args += ["-movflags", "+faststart"]
    args += [*limit_args(media.path), *thread_args()[:2], str(out)]
    ctx.ffmpeg(args, duration=media.duration)
    guard(ctx)
    check_size(out, media.path)
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
