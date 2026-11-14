import random

import pytest

from tools.video import ConvertVideo

from .conftest import frame_count, need_encoders, params_for, probe, run_ffmpeg, streams_of

SEED = 130
CASES = 6
FPS = (10, 24, 25, 30)
DURATIONS = (1 / 3, 0.5, 0.7)
FORMATS = ("mp4", "mov", "webm")


def cases():
    rng = random.Random(SEED)
    drawn = []
    for number in range(CASES):
        fps = rng.choice(FPS)
        duration = rng.choice(DURATIONS) if number % 2 else round(1 / fps + 0.001, 3)
        width, height = rng.randrange(17, 161, 2), rng.randrange(17, 121, 2)
        limit = rng.choice((0, 0, 32))
        drawn.append((width, height, fps, duration, limit, FORMATS[number % len(FORMATS)]))
    return drawn


@pytest.mark.parametrize("width,height,fps,duration,limit,fmt", cases())
def test_drawn_sizes_and_durations_read_back_even_and_as_long_as_the_source(
    ctx, source_dir, width, height, fps, duration, limit, fmt
):
    need_encoders("libx264", "libvpx-vp9", "aac", "libopus")
    assert width % 2 and height % 2
    path = source_dir / "drawn.mkv"
    run_ffmpeg(
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-t", str(duration), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv444p", "-c:a", "aac", path,
    )
    params = {**params_for("media-convert.video", format=fmt, quality="small"), "max_side": limit}

    result = ConvertVideo().run([ctx.probe(path, "video")], params, ctx)[0]

    video = streams_of(result.path, "video")[0]
    assert video["width"] % 2 == 0 and video["height"] % 2 == 0
    if limit:
        assert max(video["width"], video["height"]) <= limit
    else:
        assert (video["width"], video["height"]) == (width - 1, height - 1)
    assert frame_count(result.path) == frame_count(path)
    source_seconds = float(probe(path)["format"]["duration"])
    result_seconds = float(probe(result.path)["format"]["duration"])
    assert abs(result_seconds - source_seconds) <= 1 / fps
