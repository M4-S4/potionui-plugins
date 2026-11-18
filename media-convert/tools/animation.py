import math
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    MAX_VIDEO_PIXELS,
    MEGABYTE,
    fit,
    guard,
    input_args,
    make_room,
    output_cap,
    quality,
    read_streams,
    refuse,
    release,
    thread_args,
    threads,
)

ANIMATION_FORMATS = {"gif": ".gif", "webp": ".webp"}
ANIMATION_SIDES = (640, 480, 320)
DEFAULT_SIDE = 480
MAX_ANIMATION_SECONDS = 30.0
MIN_ANIMATION_SECONDS = 0.5
DEFAULT_ANIMATION_SECONDS = 10.0
MAX_ANIMATION_RATE = 25.0
FALLBACK_RATE = 12.0
RATE_STEPS = {"full": 1, "half": 2, "third": 3}
GIF_PALETTE = {
    "high": (256, "dither=sierra2_4a"),
    "balanced": (256, "dither=bayer:bayer_scale=5"),
    "small": (128, "dither=bayer:bayer_scale=5"),
}
WEBP_ANIMATION_QUALITY = {"high": 85, "balanced": 75, "small": 60}
WEBP_COMPRESSION = 4
GIF_BYTES_PER_PIXEL = 2
PALETTE_ROOM = MEGABYTE
PALETTE_DEMUXERS = "image2,png_pipe"


def seconds_text(value: float) -> str:
    return f"{value:g} s"


def output_rate(source_rate, step: str) -> float:
    rate = source_rate if source_rate and source_rate > 0 else FALLBACK_RATE
    divisor = math.ceil(rate / MAX_ANIMATION_RATE - 1e-9)
    return rate / (max(1, divisor) * RATE_STEPS.get(step, 1))


def rate_text(rate: float) -> str:
    return f"{rate:.6f}".rstrip("0").rstrip(".")


def span(params: dict, length) -> tuple[float, float]:
    start = float(params.get("start") or 0.0)
    wanted = float(params.get("length") or DEFAULT_ANIMATION_SECONDS)
    if not math.isfinite(start) or not math.isfinite(wanted):
        raise ToolFailed("The start and the length of the animation must be numbers of seconds")
    if start < 0:
        raise ToolFailed("The start of the animation cannot be before the start of the video")
    if wanted > MAX_ANIMATION_SECONDS:
        raise ToolFailed(
            f"An animation lasts {seconds_text(MAX_ANIMATION_SECONDS)} at most; choose a shorter length"
        )
    if wanted < MIN_ANIMATION_SECONDS:
        raise ToolFailed(f"An animation lasts at least {seconds_text(MIN_ANIMATION_SECONDS)}")
    if length and length > 0:
        if start >= length:
            raise ToolFailed(
                f"This video lasts {seconds_text(round(length, 1))}: the animation must start before its end"
            )
        wanted = min(wanted, length - start)
    return start, wanted


def frames_in(path: Path) -> int:
    try:
        with Image.open(path) as image:
            return int(getattr(image, "n_frames", 1))
    except (UnidentifiedImageError, OSError):
        return 0


class MakeAnimation(MediaTool):
    def run(self, inputs, params, ctx):
        return [self.animate(media, params, ctx) for media in inputs]

    def animate(self, media, params, ctx):
        fmt = params.get("format") or "gif"
        if fmt not in ANIMATION_FORMATS:
            raise ToolFailed(f"Media Converter cannot write {fmt} animations")
        level = quality(params)
        if not media.width or not media.height:
            raise ToolFailed("Media Converter cannot read the size of this video")
        if media.width * media.height > MAX_VIDEO_PIXELS:
            raise ToolFailed(
                f"This video is {media.width} × {media.height} pixels; Media Converter takes videos "
                "of up to 4096 × 2304 pixels (about 9.4 million)"
            )
        guard(ctx)
        streams = read_streams(media.path)
        picture = streams.video
        if picture is None:
            raise ToolFailed("This video has no picture to make an animation from")
        start, length = span(params, media.duration or streams.duration)
        side = int(params.get("max_side") or DEFAULT_SIDE)
        if side not in ANIMATION_SIDES:
            side = DEFAULT_SIDE
        width, height = fit(media.width, media.height, side, even=False)
        rate = output_rate(picture.rate or media.fps, params.get("frame_rate") or "full")
        frames = math.ceil(length * rate) + 1
        cap = min(output_cap(media.path), frames * width * height * GIF_BYTES_PER_PIXEL + MEGABYTE)
        picture_filter = f"fps={rate_text(rate)},scale={width}:{height}:flags=lanczos"
        source = [
            *thread_args(), "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            *input_args(media.path, MAX_VIDEO_PIXELS),
        ]
        out = ctx.new_path(ANIMATION_FORMATS[fmt])
        room = make_room(ctx, cap + (PALETTE_ROOM if fmt == "gif" else 0))
        try:
            if fmt == "gif":
                limit = self.gif(ctx, source, picture.index, picture_filter, level, length, room, out)
            else:
                limit = self.webp(ctx, source, picture.index, picture_filter, level, length, room, out)
            guard(ctx)
            written = out.stat().st_size if out.is_file() else 0
            if written >= limit:
                refuse(room, written)
        finally:
            release(room)
        if not written or frames_in(out) < 1:
            raise ToolFailed("This part of the video has no picture: choose another start")
        return ctx.probe(out, "image")

    def gif(self, ctx, source, index, picture_filter, level, length, room, out):
        colours, dither = GIF_PALETTE[level]
        palette = ctx.new_path(".png", stem="palette")
        ctx.scoped(0.0, 0.4).ffmpeg(
            [
                *source, "-map", f"0:{index}", "-an", "-sn", "-dn",
                "-vf", f"{picture_filter},palettegen=max_colors={colours}:stats_mode=diff",
                "-frames:v", "1", "-fs", str(PALETTE_ROOM), str(palette),
            ],
            duration=length,
        )
        guard(ctx)
        if not palette.is_file() or palette.stat().st_size == 0:
            raise ToolFailed("This part of the video has no picture: choose another start")
        left = room.size - palette.stat().st_size
        ctx.scoped(0.4, 1.0).ffmpeg(
            [
                *source,
                "-protocol_whitelist", "file", "-format_whitelist", PALETTE_DEMUXERS, "-i", str(palette.resolve()),
                "-filter_complex_threads", str(threads()),
                "-filter_complex",
                f"[0:{index}]{picture_filter}[picture];[picture][1:v]paletteuse={dither}:diff_mode=rectangle",
                "-an", "-sn", "-dn", "-map_metadata", "-1", "-loop", "0",
                "-t", f"{length:.3f}", "-fs", str(left), "-f", "gif", str(out),
            ],
            duration=length,
        )
        palette.unlink(missing_ok=True)
        return left

    def webp(self, ctx, source, index, picture_filter, level, length, room, out):
        ctx.ffmpeg(
            [
                *source, "-map", f"0:{index}", "-an", "-sn", "-dn", "-vf", picture_filter,
                "-c:v", "libwebp_anim", "-quality", str(WEBP_ANIMATION_QUALITY[level]),
                "-compression_level", str(WEBP_COMPRESSION), "-pix_fmt", "yuv420p", "-map_metadata", "-1", "-loop", "0",
                "-t", f"{length:.3f}", "-fs", str(room.size), "-f", "webp", str(out),
            ],
            duration=length,
        )
        return room.size
