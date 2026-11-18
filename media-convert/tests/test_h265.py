from types import SimpleNamespace

import pytest

from src.plugin_api import limits
from src.plugin_api.media_tools import InvalidToolParams, ToolCancelled, ToolContext, ToolFailed, validate_params

from tools import common, video
from tools.video import H265_OFF, ConvertVideo

from .conftest import MANIFEST, TOOLS, make_video, need_encoders, params_for, probe, run_ffmpeg, streams_of

TOOL = "media-convert.video"


@pytest.fixture
def allowed(server_settings):
    server_settings["allow_h265"] = True
    return server_settings


def convert(ctx, path, **given):
    need_encoders("libx265", "aac")
    return ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, format="hevc", **given), ctx)[0]


class Clock:
    def __init__(self, steps):
        self.steps = list(steps)
        self.now = 0.0

    def monotonic(self):
        value = self.now
        if self.steps:
            self.now += self.steps.pop(0)
        return value


class Quiet:
    def __init__(self):
        self.calls = []
        self.runner = SimpleNamespace(timeout=1800.0)

    def scoped(self, low, high):
        return self

    def ffmpeg(self, args, duration=None):
        self.calls.append(list(args))

    def is_cancelled(self):
        return False


def sampled(monkeypatch, steps, *, frames=None, seconds=100.0, budget=60.0):
    monkeypatch.setattr(video, "time", Clock(steps))
    monkeypatch.setattr(video, "encode_budget", lambda ctx: budget)
    fake = Quiet()
    video.check_h265_time(fake, lambda start, length: ["-ss", f"{start:.3f}", "-t", f"{length:.3f}"], 1920, 1080, frames, seconds)
    return fake


def test_the_setting_is_a_switch_that_is_off_by_default():
    entry = next(item for item in MANIFEST["settings"] if item["name"] == "allow_h265")
    assert entry["type"] == "boolean" and entry["default"] is False


@pytest.mark.parametrize("value", [None, False, "true", 1, "yes"])
def test_while_the_setting_is_off_h265_is_refused_before_any_encoding(ctx, source_dir, server_settings, value):
    if value is not None:
        server_settings["allow_h265"] = value
    path = make_video(source_dir / "clip.mp4", seconds=0.5)

    with pytest.raises(ToolFailed) as refused:
        ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, format="hevc"), ctx)

    assert refused.value.message == H265_OFF
    assert "Admin › Plugins › Media Converter › Settings" in H265_OFF and "MP4 (H.264)" in H265_OFF
    assert ctx.commands == []


def spec_with_impl():
    entry = TOOLS[TOOL]
    return SimpleNamespace(id=TOOL, label=entry["label"], params=entry.get("params") or [], impl=ConvertVideo())


def test_the_core_check_of_the_parameters_refuses_h265_while_the_setting_is_off(server_settings):
    with pytest.raises(InvalidToolParams) as refused:
        validate_params(spec_with_impl(), {"format": "hevc"})

    assert (refused.value.field, refused.value.message) == ("format", H265_OFF)
    assert validate_params(spec_with_impl(), {"format": "mp4"})["format"] == "mp4"
    server_settings["allow_h265"] = True
    assert validate_params(spec_with_impl(), {"format": "hevc"})["format"] == "hevc"


def test_the_other_formats_do_not_need_the_setting(ctx, source_dir):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "clip.mp4", seconds=0.5)

    ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, format="mp4"), ctx)

    assert ctx.commands


def test_an_allowed_h265_is_an_mp4_tagged_hvc1_with_aac_sound(ctx, source_dir, allowed):
    path = make_video(source_dir / "clip.mkv", seconds=1.0, size=(64, 48))

    result = convert(ctx, path)

    assert result.path.suffix == ".mp4"
    found = probe(result.path)
    assert found["format"]["format_name"].startswith("mov,mp4")
    picture = streams_of(result.path, "video")[0]
    assert (picture["codec_name"], picture["codec_tag_string"], picture["pix_fmt"]) == ("hevc", "hvc1", "yuv420p")
    assert picture["profile"] == "Main"
    assert [s["codec_name"] for s in streams_of(result.path, "audio")] == ["aac"]


@pytest.mark.parametrize("count", [1, 3, 16])
def test_the_thread_setting_bounds_the_x265_pool(ctx, source_dir, allowed, count):
    allowed["ffmpeg_threads"] = count
    path = make_video(source_dir / "clip.mp4", seconds=0.5)

    convert(ctx, path)

    [command] = ctx.commands
    assert command[command.index("-x265-params") + 1] == f"pools={count}:log-level=error"
    assert command[command.index("-threads") + 1] == str(count)


@pytest.mark.parametrize("level, crf", [("high", "22"), ("balanced", "26"), ("small", "30")])
def test_each_quality_has_its_crf(ctx, source_dir, allowed, level, crf):
    path = make_video(source_dir / "clip.mp4", seconds=0.5)

    convert(ctx, path, quality=level)

    [command] = ctx.commands
    assert command[command.index("-crf") + 1] == crf
    assert command[command.index("-preset") + 1] == "medium"


def test_a_short_video_is_encoded_without_a_trial(ctx, source_dir, allowed):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(320, 240), fps=25)

    convert(ctx, path)

    assert len(ctx.commands) == 1


def test_a_long_video_is_timed_on_three_parts_with_the_same_threads_and_pool(ctx, source_dir, allowed, monkeypatch):
    allowed["ffmpeg_threads"] = 3
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)
    path = make_video(source_dir / "clip.mp4", seconds=12.0, size=(64, 48), fps=10)

    result = convert(ctx, path)

    *samples, encode = ctx.commands
    assert len(samples) == 3
    starts = [float(sample[sample.index("-ss") + 1]) for sample in samples]
    assert starts == pytest.approx([2.0, 5.0, 8.0], abs=0.05)
    for sample in samples:
        assert sample[-3:] == ["-f", "null", "-"] and "-an" in sample
        assert sample.index("-ss") < sample.index("-i") and sample[sample.index("-t") + 1] == "2.000"
        assert [value for flag, value in zip(sample, sample[1:]) if flag == "-threads"] == ["3", "3"]
        assert sample[sample.index("-x265-params") + 1] == encode[encode.index("-x265-params") + 1] == "pools=3:log-level=error"
    assert streams_of(result.path, "video")[0]["codec_name"] == "hevc"


def test_the_estimate_follows_the_slowest_part(monkeypatch):
    with pytest.raises(ToolFailed) as refused:
        sampled(monkeypatch, [0.1, 0.2, 2.0, 0.1, 0.1, 0.2], seconds=100.0, budget=60.0)

    assert refused.value.message.startswith("MP4 (H.265) would take about 2 minutes ")
    sampled(monkeypatch, [0.1, 0.2, 1.0, 0.1, 0.1, 0.2], seconds=100.0, budget=60.0)


def test_an_estimate_equal_to_the_budget_passes_and_one_just_above_is_refused(monkeypatch):
    sampled(monkeypatch, [1.25, 1.25, 1.25, 1.25, 1.25, 1.25], seconds=96.0, budget=60.0)
    with pytest.raises(ToolFailed):
        sampled(monkeypatch, [1.25, 1.25, 1.3125, 1.25, 1.25, 1.25], seconds=96.0, budget=60.0)


def test_a_video_that_opens_on_a_still_picture_is_timed_where_it_is_heavy(ctx, source_dir, allowed, monkeypatch):
    path = source_dir / "still-then-busy.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "color=c=gray:size=320x240:rate=25:duration=4",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=8",
        "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path,
    )
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)

    convert(ctx, path)

    starts = [float(sample[sample.index("-ss") + 1]) for sample in ctx.commands[:3]]
    assert sum(1 for start in starts if start >= 4.0) == 2


def test_a_video_that_would_take_too_long_is_refused_after_the_sample(ctx, source_dir, allowed, monkeypatch):
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)
    monkeypatch.setattr(video, "encode_budget", lambda ctx: 0.5)
    path = make_video(source_dir / "clip.mp4", seconds=60.0, size=(320, 240), fps=25, audio=False)

    with pytest.raises(ToolFailed) as refused:
        convert(ctx, path)

    assert refused.value.message.startswith("MP4 (H.265) would take about ")
    assert refused.value.message.endswith(
        " to encode this video on this server, more than a conversion may take; "
        "choose a smaller Largest side, MP4 (H.264), or a shorter video"
    )
    assert len(ctx.commands) == 3 and all(sample[-3:] == ["-f", "null", "-"] for sample in ctx.commands)
    assert [item.name for item in ctx.scratch_dir.iterdir()] == []


def test_the_shortcut_counts_the_frames_the_file_holds_and_the_cores_of_the_server(monkeypatch, server_settings):
    server_settings["ffmpeg_threads"] = 16
    monkeypatch.setattr(video.os, "cpu_count", lambda: 2)
    limit = video.H265_PIXELS_PER_THREAD_SECOND * 2 * 60.0

    assert sampled(monkeypatch, [0.0] * 6, frames=int(limit // (1920 * 1080))).calls == []
    assert len(sampled(monkeypatch, [0.0] * 6, frames=int(limit // (1920 * 1080)) + 1).calls) == 3
    assert len(sampled(monkeypatch, [0.0] * 6, frames=None).calls) == 3


def test_the_frames_counted_are_the_frames_in_the_file(ctx, source_dir, allowed, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), fps=10)
    seen = []
    real = video.check_h265_time

    def spy(ctx, sample_args, width, height, frames, seconds):
        seen.append(frames)
        return real(ctx, sample_args, width, height, frames, seconds)

    monkeypatch.setattr(video, "check_h265_time", spy)

    convert(ctx, path)

    assert seen == [20]


def test_the_trial_waits_for_the_room_and_a_full_storage_refuses_first(ctx, source_dir, allowed, monkeypatch):
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)
    path = make_video(source_dir / "clip.mp4", seconds=6.0, size=(64, 48), fps=10)
    monkeypatch.setattr(limits, "limit_status", lambda user_id, kind: (
        limits.LimitStatus(kind=kind, limit=1, used=1) if kind == "storage_bytes" else limits.LimitStatus(kind=kind)
    ))
    ctx.user_id = "someone"

    with pytest.raises(ToolFailed, match="what is left of your storage"):
        convert(ctx, path)
    assert ctx.commands == []


@pytest.mark.parametrize("value, budget", [
    ("absent", 1080.0), (None, 1080.0), (0, 1080.0), (-5, 1080.0), (1e12, 1080.0), (float("inf"), 1080.0),
    (float("nan"), 1080.0), ("abc", 1080.0), ("900", 540.0), (900, 540.0), (100.0, 60.0),
])
def test_the_budget_follows_the_time_the_core_gives_one_encoding_and_falls_back_on_odd_values(value, budget):
    runner = SimpleNamespace() if value == "absent" else SimpleNamespace(timeout=value)

    assert video.encode_budget(SimpleNamespace(runner=runner)) == pytest.approx(budget)


def test_the_budget_of_the_real_runner(tmp_path):
    assert video.encode_budget(ToolContext(tmp_path)) == pytest.approx(1800.0 * video.H265_SHARE)


def test_cancelling_during_the_sample_stops_the_run(tmp_path, source_dir, allowed, monkeypatch, no_grants):
    need_encoders("libx265", "aac")
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)
    path = make_video(source_dir / "clip.mp4", seconds=6.0, size=(64, 48), fps=10)
    done = []
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: bool(done))
    real = ctx.runner.run

    def run(args, **kwargs):
        real(args, **dict(kwargs, is_cancelled=None))
        done.append(args)

    ctx.runner.run = run

    with pytest.raises(ToolCancelled):
        ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, format="hevc"), ctx)

    assert len(done) == 1 and done[0][-1] == "-"
    assert not no_grants


def test_a_frame_count_that_cannot_be_read_gives_none(source_dir):
    path = source_dir / "not-a-video.mp4"
    path.write_bytes(b"not a video")

    assert common.count_frames(path, 0) is None
