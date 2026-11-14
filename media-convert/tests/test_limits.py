import pytest
from PIL import Image

from src.plugin_api.media_tools import ToolFailed

from tools import common
from tools.audio import ConvertAudio
from tools.extract_audio import ExtractAudio
from tools.image import ConvertImage
from tools.video import ConvertVideo

from .conftest import (
    encoders,
    frame_count,
    need_target,
    params_for,
    piped,
    probe,
    run_ffmpeg,
    streams_of,
)

SOUND_FORMATS = ["wav", "mp3", "flac", "m4a", "ogg"]
VIDEO_FORMATS = ["mp4", "mov", "webm"]
TOO_LONG = "lasts more than 1 minute; Media Converter takes files of up to 1 minute on this server"


def one_minute_sound(folder, seconds=60, declared=True):
    if declared:
        path = folder / f"sound-{seconds}.mkv"
        run_ffmpeg("-f", "lavfi", "-i", f"sine=duration={seconds}:sample_rate=44100", "-c:a", "flac", path)
        return path
    return piped(folder / f"piped-{seconds}.mkv", "-f", "lavfi", "-i", f"sine=duration={seconds}:sample_rate=44100", "-c:a", "flac", "-f", "matroska")


def one_minute_clip(folder, seconds=60, declared=True):
    args = ("-f", "lavfi", "-i", f"testsrc=size=64x48:rate=10:duration={seconds}", "-f", "lavfi", "-i", f"sine=duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "flac")
    if declared:
        path = folder / f"clip-{seconds}.mkv"
        run_ffmpeg(*args, path)
        return path
    return piped(folder / f"pclip-{seconds}.mkv", *args, "-f", "matroska")


@pytest.fixture
def one_minute(server_settings):
    server_settings["max_minutes"] = 1


@pytest.mark.parametrize("fmt", SOUND_FORMATS)
def test_a_sound_of_exactly_the_limit_converts_to_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    path = one_minute_sound(source_dir)

    made = ConvertAudio().run([ctx.probe(path, "audio")], params_for("media-convert.audio", format=fmt), ctx)[0]

    assert float(probe(made.path)["format"]["duration"]) == pytest.approx(60, abs=0.1)


@pytest.mark.parametrize("fmt", VIDEO_FORMATS)
def test_a_video_of_exactly_the_limit_converts_to_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    path = one_minute_clip(source_dir)

    made = ConvertVideo().run([ctx.probe(path, "video")], params_for("media-convert.video", format=fmt, quality="small"), ctx)[0]

    assert float(probe(made.path)["format"]["duration"]) == pytest.approx(60, abs=0.1)


@pytest.mark.parametrize("fmt", SOUND_FORMATS)
def test_the_sound_of_a_video_of_exactly_the_limit_is_extracted_to_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    path = one_minute_clip(source_dir)

    made = ExtractAudio().run([ctx.probe(path, "video")], params_for("media-convert.extract-audio", format=fmt), ctx)[0]

    assert float(probe(made.path)["format"]["duration"]) == pytest.approx(60, abs=0.1)


@pytest.mark.parametrize("fmt", SOUND_FORMATS)
def test_a_sound_just_over_the_limit_is_refused_for_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    declared = one_minute_sound(source_dir, 61)
    hidden = one_minute_sound(source_dir, 62, declared=False)
    params = params_for("media-convert.audio", format=fmt)

    with pytest.raises(ToolFailed, match="lasts 2 minutes"):
        ConvertAudio().run([ctx.probe(declared, "audio")], params, ctx)
    assert ctx.commands == []
    with pytest.raises(ToolFailed, match=TOO_LONG):
        ConvertAudio().run([ctx.probe(hidden, "audio")], params, ctx)
    [written] = ctx.scratch_dir.iterdir()
    assert float(probe(written)["format"]["duration"]) == pytest.approx(61, abs=0.1)


@pytest.mark.parametrize("fmt", VIDEO_FORMATS)
def test_a_video_just_over_the_limit_is_refused_for_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    declared = one_minute_clip(source_dir, 61)
    hidden = one_minute_clip(source_dir, 62, declared=False)
    params = params_for("media-convert.video", format=fmt, quality="small")

    with pytest.raises(ToolFailed, match="lasts 2 minutes"):
        ConvertVideo().run([ctx.probe(declared, "video")], params, ctx)
    assert ctx.commands == []
    with pytest.raises(ToolFailed, match=TOO_LONG):
        ConvertVideo().run([ctx.probe(hidden, "video")], params, ctx)


@pytest.mark.parametrize("fmt", SOUND_FORMATS)
def test_the_sound_of_a_video_just_over_the_limit_is_refused_for_every_format(ctx, source_dir, one_minute, fmt):
    need_target(fmt)
    declared = one_minute_clip(source_dir, 61)
    hidden = one_minute_clip(source_dir, 62, declared=False)
    params = params_for("media-convert.extract-audio", format=fmt)

    with pytest.raises(ToolFailed, match="lasts 2 minutes"):
        ExtractAudio().run([ctx.probe(declared, "video")], params, ctx)
    assert ctx.commands == []
    with pytest.raises(ToolFailed, match=TOO_LONG):
        ExtractAudio().run([ctx.probe(hidden, "video")], params, ctx)


def test_the_length_check_tolerates_half_a_second_but_never_the_second_ffmpeg_adds(one_minute):
    common.check_length(60.0)
    common.check_length(60.4)
    for seconds in (60.6, 61.0):
        with pytest.raises(ToolFailed, match=TOO_LONG):
            common.check_length(seconds)


@pytest.fixture
def short_picture_long_sound(source_dir):
    path = source_dir / "short-video.mp4"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=5", "-f", "lavfi", "-i", "sine=frequency=440:duration=150",
               "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path)
    return path


@pytest.mark.parametrize("tool,tool_id,fmt", [
    (ConvertVideo, "media-convert.video", "mp4"),
    (ExtractAudio, "media-convert.extract-audio", "m4a"),
])
def test_the_longest_known_length_is_checked_before_encoding(ctx, short_picture_long_sound, one_minute, tool, tool_id, fmt):
    need_target(fmt)
    media = ctx.probe(short_picture_long_sound, "video")
    assert media.duration < 60
    assert float(probe(short_picture_long_sound)["format"]["duration"]) == pytest.approx(150, abs=0.5)

    with pytest.raises(ToolFailed, match="This file lasts 3 minutes"):
        tool().run([media], params_for(tool_id, format=fmt), ctx)

    assert ctx.commands == []


def test_a_stream_that_grows_past_the_pixel_cap_is_never_decoded_at_that_size(ctx, source_dir):
    need_target("mp4")
    small, big = source_dir / "a.h264", source_dir / "b.h264"
    run_ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=1", "-c:v", "libx264", "-preset", "ultrafast", "-f", "h264", small)
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=4224x2304:r=10:d=1", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "-f", "h264", big)
    joined = source_dir / "joined.h264"
    joined.write_bytes(small.read_bytes() + big.read_bytes())
    path = source_dir / "switch.mkv"
    run_ffmpeg("-f", "h264", "-framerate", "10", "-i", joined, "-c", "copy", path)
    media = ctx.probe(path, "video")
    assert (media.width, media.height) == (64, 64)

    made = ConvertVideo().run([media], params_for("media-convert.video", format="mp4"), ctx)[0]

    args = ctx.commands[0]
    assert args[args.index("-max_pixels") + 1] == str(common.MAX_VIDEO_PIXELS)
    assert args.index("-max_pixels") < args.index("-i")
    assert frame_count(made.path) == 10


def test_a_video_at_the_pixel_cap_is_decoded_whole(ctx, source_dir):
    need_target("mp4")
    path = source_dir / "cap.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc2=s=4096x2304:r=10:d=0.5", "-c:v", "libx264", "-preset", "ultrafast", path)

    made = ConvertVideo().run([ctx.probe(path, "video")], params_for("media-convert.video", format="mp4", quality="small"), ctx)[0]

    assert (made.width, made.height) == (4096, 2304)
    assert frame_count(made.path) == 5


def test_a_video_keeps_at_most_eight_sound_tracks(ctx, source_dir):
    need_target("mp4")
    inputs = ["-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=0.5"]
    maps = ["-map", "0:v"]
    for number in range(10):
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={300 + 50 * number}:duration=0.5"]
        maps += ["-map", f"{number + 1}:a"]
    path = source_dir / "tracks.mkv"
    run_ffmpeg(*inputs, *maps, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "flac", path)
    assert len(streams_of(path, "audio")) == 10

    kept = ConvertVideo().run([ctx.probe(path, "video")], params_for("media-convert.video", format="mp4", keep_metadata=True), ctx)[0]
    one = ConvertVideo().run([ctx.probe(path, "video")], params_for("media-convert.video", format="mp4", keep_metadata=False), ctx)[0]

    assert len(streams_of(kept.path, "audio")) == common.MAX_SOUND_TRACKS == 8
    assert len(streams_of(one.path, "audio")) == 1


@pytest.mark.parametrize("given", [{"format": "png"}, {"format": "png", "max_side": 640}, {"format": "jpeg"}])
def test_a_truncated_png_is_said_to_be_unreadable_whatever_the_format(ctx, source_dir, given):
    whole = source_dir / "noise.png"
    Image.effect_noise((256, 256), 64).convert("RGB").save(whole)
    data = whole.read_bytes()
    cut = source_dir / "cut.png"
    cut.write_bytes(data[: int(len(data) * 0.6)])

    with pytest.raises(ToolFailed, match="^This image cannot be read$"):
        ConvertImage().run([ctx.probe(cut, "image")], params_for("media-convert.image", **given), ctx)


def test_the_encoders_the_suite_relies_on_are_all_there():
    found = encoders()

    assert found, "ffmpeg -encoders listed nothing"
    for name in ("libx264", "libvpx-vp9", "aac", "libopus", "libmp3lame", "flac", "pcm_s16le", "pcm_s24le"):
        assert name in found, f"ffmpeg has no {name} encoder"

