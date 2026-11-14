from fractions import Fraction

import av
import numpy as np
import pytest
from PIL import Image

from potion_audit.media import preview_encoder, probe_image, probe_video, video_encoders, write_preview


def make_video(path, frames=12, fps=8, size=(96, 64), value=120):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=Fraction(fps, 1))
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        for index in range(frames):
            pixels = np.full((size[1], size[0], 3), value, dtype=np.uint8)
            pixels[:, : (index + 1) * 4] = 255
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return path


def test_probe_video_decodes_every_frame_and_reads_fps(tmp_path):
    info = probe_video(make_video(tmp_path / "clip.mp4"))
    assert info["decoded_frames"] == 12
    assert info["fps"] == 8.0
    assert (info["width"], info["height"]) == (96, 64)
    assert info["duration_seconds"] == pytest.approx(1.5, abs=0.2)
    assert info["not_black"] is True
    assert info["audio"] == []


def test_a_black_video_is_flagged(tmp_path):
    path = tmp_path / "black.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=Fraction(8, 1))
        stream.width, stream.height = 64, 64
        stream.pix_fmt = "yuv420p"
        for _ in range(4):
            frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    assert probe_video(path)["not_black"] is False


def test_the_preview_is_reduced_and_keeps_every_frame(tmp_path):
    source = make_video(tmp_path / "clip.mp4", size=(192, 128))
    preview = write_preview(source, tmp_path / "preview" / "clip.mp4", max_height=64)
    assert (preview["width"], preview["height"]) == (96, 64)
    assert preview["frames"] == 12
    info = probe_video(tmp_path / "preview" / "clip.mp4")
    assert info["decoded_frames"] == 12
    assert info["fps"] == 8.0
    assert info["duration_seconds"] == pytest.approx(1.5, abs=0.2)
    assert info["codec"] in {"h264", "mpeg4"}


def test_the_preview_encoder_prefers_libx264_then_falls_back():
    assert preview_encoder(["mpeg4", "libx264"]) == "libx264"
    assert preview_encoder(["mpeg4"]) == "mpeg4"
    with pytest.raises(RuntimeError):
        preview_encoder(["png"])


def test_the_bundled_ffmpeg_lists_video_encoders():
    names = video_encoders()
    assert "mpeg4" in names
    assert "png" in names


def test_probe_image_reads_size_and_black(tmp_path):
    Image.new("RGB", (40, 30), (0, 0, 0)).save(tmp_path / "black.png")
    Image.new("RGB", (40, 30), (90, 30, 160)).save(tmp_path / "potion.png")
    assert probe_image(tmp_path / "black.png")["not_black"] is False
    info = probe_image(tmp_path / "potion.png")
    assert (info["width"], info["height"], info["format"]) == (40, 30, "PNG")
    assert info["not_black"] is True
