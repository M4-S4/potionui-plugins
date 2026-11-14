import pytest
from PIL import Image

from tools.audio import ConvertAudio
from tools.image import ConvertImage
from tools.video import ConvertVideo

from .conftest import need_target, params_for, probe, run_ffmpeg, streams_of


def test_a_48_megapixel_photo_converts_at_full_size(ctx, source_dir):
    path = source_dir / "photo.jpg"
    Image.effect_noise((2000, 1500), 40).convert("RGB").resize((8000, 6000)).save(path, quality=90)

    made = ConvertImage().run([ctx.probe(path, "image")], params_for("media-convert.image", format="jpeg"), ctx)[0]

    assert (made.width, made.height) == (8000, 6000)


@pytest.mark.parametrize("size,rotation", [("3840x2160", None), ("3840x2160", "90"), ("4096x2160", None)])
def test_a_4k_phone_video_converts_at_full_size(ctx, source_dir, size, rotation):
    need_target("mp4")
    need_target("webm")
    flat = source_dir / "flat.mp4"
    run_ffmpeg("-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration=0.4", "-f", "lavfi", "-i", "sine=duration=0.4",
               "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", flat)
    path = source_dir / "phone.mp4"
    if rotation:
        run_ffmpeg("-display_rotation", rotation, "-i", flat, "-c", "copy", path)
    else:
        flat.rename(path)
    media = ctx.probe(path, "video")
    width, height = (int(side) for side in size.split("x"))
    expected = [height, width] if rotation else [width, height]
    assert [media.width, media.height] == expected

    for fmt in ("mp4", "webm"):
        made = ConvertVideo().run([media], params_for("media-convert.video", format=fmt, quality="small"), ctx)[0]
        picture = streams_of(made.path, "video")[0]
        assert [picture["width"], picture["height"]] == expected


def test_a_long_low_rate_mp3_becomes_a_wav_44_times_its_size(ctx, source_dir):
    need_target("mp3")
    path = source_dir / "talk.mp3"
    run_ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=1790:c=pink:r=44100:a=0.2", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "32k", path)

    made = ConvertAudio().run([ctx.probe(path, "audio")], params_for("media-convert.audio", format="wav"), ctx)[0]

    assert made.path.stat().st_size > 40 * path.stat().st_size
    assert float(probe(made.path)["format"]["duration"]) == pytest.approx(1790, abs=0.5)
