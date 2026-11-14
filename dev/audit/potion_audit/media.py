from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

PREVIEW_ENCODERS = ("libx264", "h264", "libopenh264", "mpeg4")
BLACK_MEAN = 4.0


def video_encoders() -> list[str]:
    names = []
    for name in sorted(av.codecs_available):
        try:
            codec = av.Codec(name, "w")
        except ValueError:
            continue
        if codec.type == "video":
            names.append(name)
    return names


def preview_encoder(available: list[str] | None = None) -> str:
    names = set(video_encoders() if available is None else available)
    for name in PREVIEW_ENCODERS:
        if name in names:
            return name
    raise RuntimeError(f"no preview encoder among {', '.join(PREVIEW_ENCODERS)}")


def probe_video(path: Path) -> dict:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        rate = stream.average_rate or stream.guessed_rate
        declared_frames = stream.frames or None
        stream_duration = float(stream.duration * stream.time_base) if stream.duration and stream.time_base else None
        container_duration = container.duration / av.time_base if container.duration else None
        audio = [
            {"codec": audio_stream.codec_context.name, "rate": audio_stream.codec_context.sample_rate, "channels": audio_stream.codec_context.layout.nb_channels}
            for audio_stream in container.streams.audio
        ]
        decoded = 0
        means = []
        for frame in container.decode(stream):
            pixels = frame.to_ndarray(format="rgb24")
            means.append(float(pixels.mean()))
            decoded += 1
        return {
            "codec": stream.codec_context.name,
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "pix_fmt": stream.codec_context.pix_fmt,
            "fps": float(rate) if rate else None,
            "declared_frames": declared_frames,
            "decoded_frames": decoded,
            "duration_seconds": stream_duration or container_duration,
            "audio": audio,
            "mean_luma_min": min(means) if means else None,
            "mean_luma_max": max(means) if means else None,
            "not_black": bool(means) and max(means) > BLACK_MEAN,
        }


def write_preview(src: Path, dst: Path, max_height: int = 360, encoder: str | None = None, crf: int = 28) -> dict:
    codec_name = encoder or preview_encoder()
    dst.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(src)) as source, av.open(str(dst), "w", options={"movflags": "+faststart"}) as target:
        stream = source.streams.video[0]
        width = stream.codec_context.width
        height = stream.codec_context.height
        if height > max_height:
            width = int(round(width * max_height / height / 2)) * 2
            height = max_height
        rate = Fraction(stream.average_rate or stream.guessed_rate or 24)
        out = target.add_stream(codec_name, rate=rate)
        out.width = width
        out.height = height
        out.pix_fmt = "yuv420p"
        out.time_base = 1 / rate
        out.codec_context.time_base = 1 / rate
        if codec_name == "libx264":
            out.options = {"crf": str(crf), "preset": "veryfast"}
        frames = 0
        for frame in source.decode(stream):
            scaled = frame.reformat(width=width, height=height, format="yuv420p")
            scaled.pts = frames
            scaled.time_base = out.codec_context.time_base
            for packet in out.encode(scaled):
                target.mux(packet)
            frames += 1
        for packet in out.encode(None):
            target.mux(packet)
    return {"encoder": codec_name, "width": width, "height": height, "frames": frames, "size": dst.stat().st_size}


def probe_image(path: Path) -> dict:
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB"))
        return {
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "mean": float(pixels.mean()),
            "not_black": float(pixels.mean()) > BLACK_MEAN,
        }


THUMB_SIDE = 320
DISPLAY_SIDE = 1280
SSIM_WINDOW = 7
SSIM_C1 = (0.01 * 255) ** 2
SSIM_C2 = (0.03 * 255) ** 2


def video_frame(path: Path, index: int | None = None) -> Image.Image:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        wanted = index if index is not None else max(0, (stream.frames or 0) // 2)
        chosen = None
        for position, frame in enumerate(container.decode(stream)):
            chosen = frame
            if position >= wanted:
                break
        if chosen is None:
            raise ValueError(f"{path.name} has no video frame")
        return chosen.to_image()


def _fit(image: Image.Image, side: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((side, side), Image.Resampling.LANCZOS)
    return copy


def write_thumbnail(src: Path, dst: Path, kind: str, side: int = THUMB_SIDE) -> dict:
    if kind == "video":
        image = video_frame(src)
    else:
        with Image.open(src) as opened:
            image = opened.convert("RGBA") if opened.mode in {"RGBA", "LA", "P"} else opened.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    small = _fit(image, side)
    if small.mode == "RGBA":
        flat = Image.new("RGB", small.size, (128, 128, 128))
        flat.paste(small, mask=small.getchannel("A"))
        small = flat
    small.save(dst, "JPEG", quality=82)
    return {"width": small.width, "height": small.height, "size": dst.stat().st_size}


def write_display_image(src: Path, dst: Path, side: int = DISPLAY_SIDE) -> dict:
    with Image.open(src) as opened:
        image = opened.convert("RGBA") if opened.mode in {"RGBA", "LA", "P"} else opened.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    small = _fit(image, side)
    small.save(dst, "WEBP", quality=86)
    return {"width": small.width, "height": small.height, "size": dst.stat().st_size}


def gray_frames(path: Path, kind: str, count: int = 5) -> list[np.ndarray]:
    if kind == "image":
        with Image.open(path) as image:
            return [np.asarray(image.convert("L"), dtype=np.float64)]
    with av.open(str(path)) as container:
        frames = [np.asarray(frame.to_image().convert("L"), dtype=np.float64) for frame in container.decode(container.streams.video[0])]
    if len(frames) <= count:
        return frames
    picks = np.linspace(0, len(frames) - 1, count).round().astype(int)
    return [frames[index] for index in picks]


def _box_mean(values: np.ndarray, window: int) -> np.ndarray:
    total = np.pad(values, ((1, 0), (1, 0))).cumsum(axis=0).cumsum(axis=1)
    sums = total[window:, window:] - total[:-window, window:] - total[window:, :-window] + total[:-window, :-window]
    return sums / (window * window)


def ssim(first: np.ndarray, second: np.ndarray, window: int = SSIM_WINDOW) -> float:
    if first.shape != second.shape:
        raise ValueError(f"SSIM needs pictures of the same size, got {first.shape} and {second.shape}")
    a = first.astype(np.float64)
    b = second.astype(np.float64)
    mean_a = _box_mean(a, window)
    mean_b = _box_mean(b, window)
    var_a = _box_mean(a * a, window) - mean_a ** 2
    var_b = _box_mean(b * b, window) - mean_b ** 2
    cov = _box_mean(a * b, window) - mean_a * mean_b
    score = ((2 * mean_a * mean_b + SSIM_C1) * (2 * cov + SSIM_C2)) / ((mean_a ** 2 + mean_b ** 2 + SSIM_C1) * (var_a + var_b + SSIM_C2))
    return float(score.mean())


def media_ssim(first: Path, second: Path, kind: str) -> float:
    a = gray_frames(first, kind)
    b = gray_frames(second, kind)
    if len(a) != len(b):
        raise ValueError(f"{first.name} and {second.name} have different frame counts")
    return round(float(np.mean([ssim(x, y) for x, y in zip(a, b)])), 4)
