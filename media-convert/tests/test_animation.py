from pathlib import Path

import pytest
from PIL import Image

from src.plugin_api.media_tools import InvalidToolParams, ToolCancelled, ToolContext, ToolFailed

from tools import animation, common
from tools.animation import MakeAnimation, output_rate

from .conftest import make_video, need_encoders, params_for, run_ffmpeg

TOOL = "media-convert.animation"
ENCODERS = {"gif": ("gif",), "webp": ("libwebp_anim",)}


def animate(ctx, path, raw=None, **given):
    fmt = given.get("format", "gif")
    need_encoders("libx264", *ENCODERS[fmt])
    chosen = dict(params_for(TOOL), **raw) if raw else params_for(TOOL, **given)
    return MakeAnimation().run([ctx.probe(path, "video")], chosen, ctx)[0]


def frames_of(path):
    with Image.open(path) as image:
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            image.load()
            durations.append(image.info.get("duration") or 0)
        return image.format, image.size, image.n_frames, image.info.get("loop"), sum(durations)


@pytest.mark.parametrize("fmt, kind", [("gif", "GIF"), ("webp", "WEBP")])
def test_each_format_loops_forever_with_the_frames_of_the_chosen_length(ctx, source_dir, fmt, kind):
    path = make_video(source_dir / "clip.mp4", seconds=3.0, size=(320, 240), fps=16)

    result = animate(ctx, path, format=fmt, length=2, max_side=320)

    assert result.kind == "image" and result.path.suffix == f".{fmt}"
    assert result.path.parent == ctx.scratch_dir
    found, size, frames, loop, total = frames_of(result.path)
    assert (found, size, loop) == (kind, (320, 240), 0)
    if fmt == "gif":
        assert result.has_alpha is False
        with Image.open(result.path) as image:
            assert "transparency" not in image.info
    assert abs(frames - 32) <= 1
    assert total == pytest.approx(2000, abs=130)


def test_the_largest_side_shrinks_and_never_enlarges(ctx, source_dir):
    large = make_video(source_dir / "large.mp4", seconds=1.0, size=(1280, 720), fps=10)
    small = make_video(source_dir / "small.mp4", seconds=1.0, size=(64, 48), fps=10)

    assert frames_of(animate(ctx, large, max_side=480).path)[1] == (480, 270)
    assert frames_of(animate(ctx, large, max_side=640).path)[1] == (640, 360)
    assert frames_of(animate(ctx, small, max_side=640).path)[1] == (64, 48)


@pytest.mark.parametrize(
    "source, step, expected",
    [
        (16, "full", 16), (16, "half", 8), (16, "third", 16 / 3),
        (24, "full", 24), (24, "half", 12), (24, "third", 8),
        (25, "full", 25), (30, "full", 15), (30, "half", 7.5),
        (60, "full", 20), (50, "full", 25), (30000 / 1001, "full", 15000 / 1001),
        (None, "full", 12), (0, "half", 6),
    ],
)
def test_the_frame_rate_divides_the_source_and_stays_at_25_or_less(source, step, expected):
    assert output_rate(source, step) == pytest.approx(expected)
    assert output_rate(source, step) <= 25


def test_the_frame_rate_reaches_ffmpeg_as_an_exact_fraction_of_the_source(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), fps=30)

    result = animate(ctx, path, length=2, frame_rate="half")

    assert abs(frames_of(result.path)[2] - 15) <= 1
    assert all("fps=7.5," in " ".join(command) for command in ctx.commands)


def test_the_length_is_capped_at_thirty_seconds_by_the_form_and_by_the_tool(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))

    with pytest.raises(InvalidToolParams, match="Length must be at most 30 s"):
        params_for(TOOL, length=31)
    with pytest.raises(ToolFailed, match="^An animation lasts 30 s at most; choose a shorter length$"):
        animate(ctx, path, raw={"length": 30.5})
    with pytest.raises(ToolFailed, match="^An animation lasts at least 0.5 s$"):
        animate(ctx, path, raw={"length": 0.1})
    assert ctx.commands == []


@pytest.mark.parametrize("raw", [{"start": float("nan")}, {"length": float("nan")}, {"start": float("inf")}, {"start": -1}])
def test_a_start_or_length_that_bypasses_the_form_is_checked_by_the_tool(ctx, source_dir, raw):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))

    with pytest.raises(ToolFailed):
        animate(ctx, path, raw=raw)
    assert ctx.commands == []


def test_thirty_seconds_are_taken_whole(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=31.0, size=(64, 48), fps=10, audio=False)

    result = animate(ctx, path, length=30)

    assert abs(frames_of(result.path)[2] - 300) <= 1
    assert all("-t" in command and command[command.index("-t") + 1] == "30.000" for command in ctx.commands)


def test_the_animation_stops_at_the_end_of_the_video(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), fps=10)

    result = animate(ctx, path, start=1.5, length=10)

    assert abs(frames_of(result.path)[2] - 5) <= 1


def test_a_start_past_the_end_is_refused_before_any_encoding(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), fps=10)

    with pytest.raises(ToolFailed, match="^This video lasts 2 s: the animation must start before its end$"):
        animate(ctx, path, start=2, length=5)
    assert ctx.commands == []


def test_the_start_is_taken_from_the_video(ctx, source_dir):
    path = source_dir / "halves.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:size=64x48:rate=10:duration=1",
        "-f", "lavfi", "-i", "color=c=blue:size=64x48:rate=10:duration=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path,
    )

    result = animate(ctx, path, start=1.2, length=0.5)

    with Image.open(result.path) as image:
        red, green, blue = image.convert("RGB").getpixel((32, 24))
    assert blue > 150 and red < 100


def test_the_gif_palette_is_written_in_the_scratch_folder_then_removed(ctx, source_dir, tmp_path, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    here = tmp_path / "cwd"
    here.mkdir()
    monkeypatch.chdir(here)

    result = animate(ctx, path, quality="small")

    first, second = ctx.commands
    palette = first[-1]
    assert palette.endswith(".png") and palette.startswith(str(ctx.scratch_dir))
    assert "palettegen=max_colors=128:stats_mode=diff" in " ".join(first)
    assert second[second.index(palette) - 1] == "-i"
    assert second[second.index(palette) - 2] == animation.PALETTE_DEMUXERS
    assert sorted(item.name for item in ctx.scratch_dir.iterdir()) == [result.path.name]
    assert list(here.iterdir()) == []


def test_the_webp_is_made_in_one_call_and_its_quality_follows_the_step(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))

    for level, value in (("high", "85"), ("balanced", "75"), ("small", "60")):
        before = len(ctx.commands)
        animate(ctx, path, format="webp", quality=level)
        [command] = ctx.commands[before:]
        assert command[command.index("-quality") + 1] == value
        assert command[command.index("-c:v") + 1] == "libwebp_anim"


@pytest.mark.parametrize("level, colours, dither", [
    ("high", 256, "dither=sierra2_4a"), ("balanced", 256, "dither=bayer:bayer_scale=5"), ("small", 128, "dither=bayer:bayer_scale=5"),
])
def test_each_gif_quality_has_its_palette_and_dither(ctx, source_dir, level, colours, dither):
    path = make_video(source_dir / "clip.mp4", seconds=0.5, size=(64, 48))

    animate(ctx, path, quality=level)

    first, second = (" ".join(command) for command in ctx.commands)
    assert f"palettegen=max_colors={colours}:" in first
    assert f"paletteuse={dither}:diff_mode=rectangle" in second


def test_the_thread_setting_bounds_both_calls(ctx, source_dir, server_settings):
    server_settings["ffmpeg_threads"] = 3
    path = make_video(source_dir / "clip.mp4", seconds=0.5, size=(64, 48))

    animate(ctx, path)

    for command in ctx.commands:
        assert command[command.index("-threads") + 1] == "3"
        assert command[command.index("-filter_threads") + 1] == "3"
    assert ctx.commands[1][ctx.commands[1].index("-filter_complex_threads") + 1] == "3"


def test_cancelling_between_the_palette_and_the_gif_stops_the_run(tmp_path, source_dir, no_grants):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    need_encoders("gif")
    done = []
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: bool(done))
    real = ctx.runner.run

    def run(args, **kwargs):
        real(args, **dict(kwargs, is_cancelled=None))
        done.append(args)

    ctx.runner.run = run

    with pytest.raises(ToolCancelled):
        MakeAnimation().run([ctx.probe(path, "video")], params_for(TOOL), ctx)

    assert len(done) == 1 and done[0][-1].endswith(".png")
    assert not no_grants


def test_a_gif_that_outgrows_its_room_is_refused(ctx, source_dir, monkeypatch):
    path = source_dir / "noise.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "nullsrc=size=320x240:rate=25", "-vf", "geq=random(1)*255:128:128",
        "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10", "-pix_fmt", "yuv420p", path,
    )
    monkeypatch.setattr(common, "RUN_BUDGET", 2 * common.MEGABYTE)

    with pytest.raises(ToolFailed, match="^This run would write more than 2 MB"):
        animate(ctx, path, length=4, max_side=320)

    second = ctx.commands[-1]
    assert int(second[second.index("-fs") + 1]) < 2 * common.MEGABYTE


def test_the_room_covers_the_palette_and_the_largest_gif(ctx, source_dir, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(320, 240), fps=10)
    asked = []
    real = animation.make_room

    def spy(ctx, cap, *args, **kwargs):
        asked.append(cap)
        return real(ctx, cap, *args, **kwargs)

    monkeypatch.setattr(animation, "make_room", spy)

    animate(ctx, path, length=2, max_side=320, frame_rate="full")
    animate(ctx, path, format="webp", length=2, max_side=320, frame_rate="full")

    frames = 2 * 10 + 1
    largest = frames * 320 * 240 * animation.GIF_BYTES_PER_PIXEL + common.MEGABYTE
    assert asked == [largest + animation.PALETTE_ROOM, largest]


def test_a_video_without_picture_is_refused(ctx, source_dir, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    media = ctx.probe(path, "video")
    monkeypatch.setattr(animation, "read_streams", lambda path: common.Streams(streams=(), tags={}, duration=1.0))

    with pytest.raises(ToolFailed, match="^This video has no picture to make an animation from$"):
        MakeAnimation().run([media], params_for(TOOL), ctx)


def test_a_part_that_gives_no_file_is_refused(ctx, source_dir, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    monkeypatch.setattr(MakeAnimation, "webp", lambda self, ctx, *args: args[-2].size)

    with pytest.raises(ToolFailed, match="^This part of the video has no picture: choose another start$"):
        animate(ctx, path, format="webp")


def test_a_held_palette_changes_no_animation(ctx, source_dir, no_grants, held_scratch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))

    result = animate(ctx, path, quality="small")

    first, second = ctx.commands
    assert held_scratch == [Path(first[-1]).name]
    assert frames_of(result.path)[0] == "GIF"
    assert not no_grants


def test_a_held_palette_keeps_the_refusal_of_a_gif_too_large(ctx, source_dir, monkeypatch, no_grants, held_scratch):
    path = source_dir / "noise.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "nullsrc=size=320x240:rate=25", "-vf", "geq=random(1)*255:128:128",
        "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10", "-pix_fmt", "yuv420p", path,
    )
    monkeypatch.setattr(common, "RUN_BUDGET", 2 * common.MEGABYTE)

    with pytest.raises(ToolFailed) as caught:
        animate(ctx, path, length=4, max_side=320)

    assert str(caught.value) == "This run would write more than 2 MB, the most Media Converter writes in one run; convert fewer items at a time"
    assert held_scratch == [Path(ctx.commands[0][-1]).name]
    assert not no_grants


def test_a_held_palette_keeps_the_cancel_that_stopped_the_animation(tmp_path, source_dir, no_grants, held_scratch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    need_encoders("gif")
    done = []
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: len(done) == 2)
    real = ctx.runner.run

    def run(args, **kwargs):
        real(args, **dict(kwargs, is_cancelled=None))
        done.append(args)

    ctx.runner.run = run

    with pytest.raises(ToolCancelled):
        MakeAnimation().run([ctx.probe(path, "video")], params_for(TOOL), ctx)

    assert len(done) == 2
    assert held_scratch == [Path(done[0][-1]).name]
    assert not no_grants
