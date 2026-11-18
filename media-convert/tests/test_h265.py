import pytest

from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import video
from tools.video import H265_OFF, ConvertVideo

from .conftest import MANIFEST, make_video, need_encoders, params_for, probe, streams_of

TOOL = "media-convert.video"


@pytest.fixture
def allowed(server_settings):
    server_settings["allow_h265"] = True
    return server_settings


def convert(ctx, path, **given):
    need_encoders("libx265", "aac")
    return ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, format="hevc", **given), ctx)[0]


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


def test_a_long_video_is_timed_on_a_sample_first(ctx, source_dir, allowed, monkeypatch):
    monkeypatch.setattr(video, "H265_PIXELS_PER_THREAD_SECOND", 1)
    path = make_video(source_dir / "clip.mp4", seconds=6.0, size=(64, 48), fps=10)

    result = convert(ctx, path)

    sample, encode = ctx.commands
    assert sample[-3:] == ["-f", "null", "-"]
    assert sample[sample.index("-t") + 1] == "4.000"
    assert sample[sample.index("-x265-params") + 1] == encode[encode.index("-x265-params") + 1]
    assert "-an" in sample
    assert streams_of(result.path, "video")[0]["codec_name"] == "hevc"


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
    [sample] = ctx.commands
    assert sample[-3:] == ["-f", "null", "-"]
    assert not ctx.scratch_dir.exists() or list(ctx.scratch_dir.iterdir()) == []


def test_the_budget_follows_the_time_the_core_gives_one_encoding(tmp_path):
    ctx = ToolContext(tmp_path)

    assert video.encode_budget(ctx) == pytest.approx(ctx.runner.timeout * video.H265_SHARE)
    ctx.runner.timeout = 100.0
    assert video.encode_budget(ctx) == pytest.approx(60.0)


def test_the_estimate_counts_the_pixels_the_rate_and_the_threads(monkeypatch, server_settings):
    calls = []
    fake = type("Fake", (), {"ffmpeg": lambda self, args, duration=None: calls.append(args), "is_cancelled": lambda self: False})()
    monkeypatch.setattr(video, "encode_budget", lambda ctx: 1000.0)
    server_settings["ffmpeg_threads"] = 4
    limit = video.H265_PIXELS_PER_THREAD_SECOND * 4 * 1000.0

    video.check_h265_time(fake, lambda seconds: [], 1000, 1000, 10.0, limit / 1e7)
    assert calls == []
    video.check_h265_time(fake, lambda seconds: [], 1000, 1000, 10.0, limit / 1e7 + 1)
    assert len(calls) == 1


def test_cancelling_during_the_sample_stops_the_run(tmp_path, source_dir, allowed, monkeypatch):
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
