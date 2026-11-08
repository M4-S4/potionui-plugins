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
