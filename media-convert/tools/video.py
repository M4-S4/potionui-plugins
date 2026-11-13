from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    H264_CRF,
    H264_PRESET,
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
    input_args,
    limit_args,
    max_side,
    metadata_args,
    quality,
    read_streams,
    thread_args,
)


def video_codec_args(fmt: str, level: str) -> list[str]:
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


class ConvertVideo(MediaTool):
    def run(self, inputs, params, ctx):
        return [self.convert(media, params, ctx) for media in inputs]

    def convert(self, media, params, ctx):
        fmt = params.get("format") or "mp4"
        if fmt not in VIDEO_FORMATS:
            raise ToolFailed(f"Media Converter cannot write {fmt} videos")
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
        picture = streams.video
        if picture is None:
            raise ToolFailed("This video has no picture to convert")
        width, height = fit(media.width, media.height, max_side(params), even=True)
        tracks = streams.audio if keep else streams.audio[:1]
        subtitles = streams.text_subtitles if keep else []
        args = [*thread_args(), *input_args(media.path), "-map", f"0:{picture.index}"]
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
        args += [*limit_args(media.path), *thread_args()[:2], str(out)]
        ctx.ffmpeg(args, duration=media.duration)
        guard(ctx)
        check_size(out, media.path)
        check_length(read_streams(out).duration)
        return ctx.probe(out, "video")
