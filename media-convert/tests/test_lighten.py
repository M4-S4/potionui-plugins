from pathlib import Path
from types import SimpleNamespace

import pytest

from src.plugin_api import limits
from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import common, lighten
from tools.lighten import LightenVideo, Plan, plan, smallest_mb

from .conftest import make_video, need_encoders, params_for, piped, probe, run_ffmpeg, streams_of

TOOL = "media-convert.lighten"
UNIT = 20_000
LOCATION = "+48.8566+002.3522/"


@pytest.fixture
def small_unit(monkeypatch):
    monkeypatch.setattr(lighten, "MEGABYTE_SI", UNIT)
    return UNIT


def busy_video(path, *, seconds=4.0, size=(320, 240), fps=25, audio=True, extra=()):
    args = ["-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=pink:r=48000:a=0.3"]
    args += ["-vf", "noise=alls=30:allf=t", "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    run_ffmpeg(*args, *extra, path)
    return path


def lightened(ctx, path, **given):
    need_encoders("libx264", "aac")
    return LightenVideo().run([ctx.probe(path, "video")], params_for(TOOL, **given), ctx)[0]


def media_like(width, height, duration, fps=24.0, path=None):
    return SimpleNamespace(width=width, height=height, duration=duration, fps=fps, path=path)


def streams_like(rate=24.0, bit_rate=0):
    picture = common.Stream(index=0, kind="video", codec="h264", rate=rate)
    return common.Streams(streams=(picture,), tags={}, duration=None), common.Stream(index=1, kind="audio", codec="aac", channels=2, bit_rate=bit_rate)


def test_the_defaults_aim_at_16_mb_with_sound_and_without_metadata():
    assert params_for(TOOL) == {"target": 16, "keep_sound": True, "keep_metadata": False}
    assert lighten.TARGETS_MB == (8, 16, 18, 20, 30, 50)


@pytest.mark.parametrize("target", lighten.TARGETS_MB)
def test_every_target_gives_a_file_under_it(tmp_path, source_dir, small_unit, target):
    path = busy_video(source_dir / "busy.mp4")
    assert path.stat().st_size > 50 * UNIT
    ctx = ToolContext(tmp_path / "scratch")

    result = lightened(ctx, path, target=target)

    assert result.path.stat().st_size < target * UNIT
    found = probe(result.path)
    assert [s["codec_name"] for s in found["streams"]] == ["h264", "aac"]
    assert float(found["format"]["duration"]) == pytest.approx(4.0, abs=0.1)
    assert found["format"]["format_name"].startswith("mov,mp4")


def test_two_passes_share_their_statistics_in_the_scratch_folder_and_leave_nothing(ctx, source_dir, small_unit, tmp_path, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    here = tmp_path / "cwd"
    here.mkdir()
    monkeypatch.chdir(here)

    result = lightened(ctx, path, target=16)

    first, second = ctx.commands
    assert first[first.index("-pass") + 1] == "1" and second[second.index("-pass") + 1] == "2"
    prefix = first[first.index("-passlogfile") + 1]
    assert prefix == second[second.index("-passlogfile") + 1]
    assert prefix.startswith(str(ctx.scratch_dir))
    assert first[-3:] == ["-f", "null", "-"] and "-an" in first
    assert first[first.index("-b:v") + 1] == second[second.index("-b:v") + 1]
    assert sorted(item.name for item in ctx.scratch_dir.iterdir()) == [result.path.name]
    assert list(here.iterdir()) == []


def inflated(monkeypatch, factor):
    real = lighten.plan

    def bigger(*args):
        chosen = real(*args)
        return Plan(int(chosen.video_kbps * factor), chosen.audio_kbps, chosen.width, chosen.height)

    monkeypatch.setattr(lighten, "plan", bigger)


def test_a_result_over_the_target_is_encoded_once_more_with_less_bitrate(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    inflated(monkeypatch, 1.4)

    result = lightened(ctx, path, target=16)

    first, second, third = ctx.commands
    assert third[third.index("-pass") + 1] == "2"
    assert int(third[third.index("-b:v") + 1][:-1]) < int(second[second.index("-b:v") + 1][:-1])
    assert result.path.stat().st_size < 16 * UNIT
    assert result.path.name == Path(third[-1]).name
    assert sorted(item.name for item in ctx.scratch_dir.iterdir()) == [result.path.name]


def test_a_result_still_over_the_target_after_the_second_try_is_refused(ctx, source_dir, small_unit, monkeypatch, no_grants):
    path = busy_video(source_dir / "busy.mp4")
    inflated(monkeypatch, 1.4)
    monkeypatch.setattr(lighten, "SMALLEST_VIDEO_KBPS", 10_000)

    with pytest.raises(ToolFailed, match="^Media Converter could not bring this video under 16 MB; choose a larger size$"):
        lightened(ctx, path, target=16)

    assert len(ctx.commands) == 3
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_the_size_is_checked_on_the_file_written(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    real = LightenVideo.second_pass

    def padded(self, *args):
        out = real(self, *args)
        with out.open("ab") as handle:
            handle.write(b"\0" * (17 * UNIT))
        return out

    monkeypatch.setattr(LightenVideo, "second_pass", padded)

    with pytest.raises(ToolFailed, match="could not bring this video under 16 MB"):
        lightened(ctx, path, target=16)
    assert len(ctx.commands) == 3


def test_an_unreachable_target_is_refused_with_the_smallest_size_before_any_encoding(ctx, source_dir):
    path = make_video(source_dir / "long.mp4", seconds=600, size=(64, 48), fps=5)

    with pytest.raises(ToolFailed) as refused:
        lightened(ctx, path, target=8)

    assert refused.value.message == (
        "This video lasts 10 minutes: to fit in 8 MB, its picture would be too poor to watch. "
        "The smallest file Media Converter can make from it weighs about 17 MB; choose 18 MB or more"
    )
    assert ctx.commands == []


def test_the_refusal_offers_to_drop_the_sound_when_that_is_enough(tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(b"\0" * (60 * 1000 * 1000))
    with pytest.raises(ToolFailed) as refused:
        plan(media_like(1920, 1080, 700, path=source), *streams_like(), 16 * lighten.MEGABYTE_SI, 700)

    assert refused.value.message == (
        "This video lasts 12 minutes: to fit in 16 MB, its picture would be too poor to watch. "
        "The smallest file Media Converter can make from it weighs about 20 MB; choose 20 MB or more, or turn off Keep the sound"
    )
    silent = plan(media_like(1920, 1080, 700, path=source), streams_like()[0], None, 16 * lighten.MEGABYTE_SI, 700)
    assert silent.audio_kbps == 0 and silent.video_kbps >= lighten.MIN_VIDEO_KBPS


def test_a_video_too_long_for_every_target_is_told_to_be_trimmed():
    message = lighten.impossible(50 * lighten.MEGABYTE_SI, 3 * 3600, True).message

    assert message.endswith("; trim it into shorter parts first")
    assert "or turn off Keep the sound" not in message


def test_the_smallest_size_is_the_floor_bitrate_with_the_margin():
    assert smallest_mb(600, True) == 17
    assert smallest_mb(600, False) == 12
    assert smallest_mb(60, True) == 2


@pytest.mark.parametrize("target, side", [(8, (1280, 720)), (16, (1280, 720)), (20, (1920, 1080)), (50, (1920, 1080))])
def test_the_picture_shrinks_until_each_pixel_gets_enough_bits(tmp_path, target, side):
    source = tmp_path / "big.bin"
    source.write_bytes(b"\0" * (60 * 1000 * 1000))

    chosen = plan(media_like(1920, 1080, 60, path=source), *streams_like(), target * lighten.MEGABYTE_SI, 60)

    assert (chosen.width, chosen.height) == side
    assert chosen.audio_kbps == 128
    assert chosen.video_kbps + chosen.audio_kbps <= target * lighten.MEGABYTE_SI * 0.96 * 8 / 60 / 1000


def test_the_sound_gets_less_room_when_the_budget_is_tight(tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(b"\0" * (60 * 1000 * 1000))

    assert plan(media_like(640, 360, 180, path=source), *streams_like(), 8 * lighten.MEGABYTE_SI, 180).audio_kbps == 64
    assert plan(media_like(640, 360, 90, path=source), *streams_like(), 8 * lighten.MEGABYTE_SI, 90).audio_kbps == 96
    assert plan(media_like(640, 360, 60, path=source), *streams_like(bit_rate=48_000), 8 * lighten.MEGABYTE_SI, 60).audio_kbps == 48


def test_a_source_lighter_than_the_target_is_not_inflated(tmp_path):
    source = tmp_path / "small.bin"
    source.write_bytes(b"\0" * (1000 * 1000))

    chosen = plan(media_like(1280, 720, 10, path=source), *streams_like(), 50 * lighten.MEGABYTE_SI, 10)

    assert chosen.video_kbps + chosen.audio_kbps <= 1000 * 1000 * 8 / 10 / 1000 * lighten.SOURCE_GROWTH


def test_an_h264_mp4_already_under_the_target_is_copied_without_encoding(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-metadata", f"location={LOCATION}"))

    result = lightened(ctx, path, target=8)

    [command] = ctx.commands
    assert command[command.index("-c") + 1] == "copy"
    assert "-pass" not in command
    assert [s["codec_name"] for s in probe(result.path)["streams"]] == ["h264", "aac"]
    assert "location" not in (probe(result.path)["format"].get("tags") or {})


def test_a_copy_keeps_the_place_only_when_asked(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-metadata", f"location={LOCATION}"))

    result = lightened(ctx, path, target=8, keep_metadata=True)

    assert probe(result.path)["format"]["tags"]["location"] == LOCATION


def test_a_webm_under_the_target_is_encoded_again_in_h264(ctx, source_dir):
    need_encoders("libvpx-vp9", "libopus")
    path = source_dir / "clip.webm"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
        "-c:v", "libvpx-vp9", "-c:a", "libopus", path,
    )

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 2
    assert [s["codec_name"] for s in probe(result.path)["streams"]] == ["h264", "aac"]


@pytest.mark.parametrize("extra", [("-c:a", "libmp3lame"), ("-pix_fmt", "yuv444p"), ("-af", "aformat=channel_layouts=5.1")])
def test_a_small_mp4_that_would_not_play_everywhere_is_encoded_again(ctx, source_dir, extra):
    need_encoders("libmp3lame")
    path = source_dir / "clip.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", *extra, path,
    )

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 2
    video = streams_of(result.path, "video")[0]
    assert video["pix_fmt"] == "yuv420p"
    [sound] = streams_of(result.path, "audio")
    assert sound["codec_name"] == "aac" and sound["channels"] <= 2


def test_the_place_and_the_title_are_dropped_by_default_when_encoding(ctx, source_dir, small_unit):
    path = busy_video(source_dir / "busy.mp4", extra=("-metadata", f"location={LOCATION}", "-metadata", "title=Holiday"))

    plain = lightened(ctx, path, target=16)
    kept = lightened(ctx, path, target=16, keep_metadata=True)

    assert not {"location", "title"} & set(probe(plain.path)["format"].get("tags") or {})
    tags = probe(kept.path)["format"]["tags"]
    assert tags["location"] == LOCATION and tags["title"] == "Holiday"


def test_the_sound_follows_its_switch_and_a_silent_source_stays_silent(ctx, source_dir, small_unit):
    loud = busy_video(source_dir / "loud.mp4")
    silent = busy_video(source_dir / "silent.mp4", audio=False)

    assert streams_of(lightened(ctx, loud, target=16, keep_sound=False).path, "audio") == []
    assert streams_of(lightened(ctx, silent, target=16).path, "audio") == []
    assert len(streams_of(lightened(ctx, loud, target=16).path, "audio")) == 1


def test_surround_sound_is_mixed_down_to_stereo(ctx, source_dir, small_unit):
    path = source_dir / "surround.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=4", "-f", "lavfi", "-i", "anoisesrc=d=4:r=48000",
        "-vf", "noise=alls=30:allf=t", "-af", "aformat=channel_layouts=5.1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-c:a", "aac", "-b:a", "384k", path,
    )

    result = lightened(ctx, path, target=16)

    assert streams_of(result.path, "audio")[0]["channels"] == 2


def test_cancelling_between_the_two_passes_stops_the_run(tmp_path, source_dir, small_unit, no_grants):
    need_encoders("libx264", "aac")
    path = busy_video(source_dir / "busy.mp4")
    done = []
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: bool(done))
    real = ctx.runner.run

    def run(args, **kwargs):
        real(args, **dict(kwargs, is_cancelled=None))
        done.append(args)

    ctx.runner.run = run

    with pytest.raises(ToolCancelled):
        LightenVideo().run([ctx.probe(path, "video")], params_for(TOOL, target=16), ctx)

    assert len(done) == 1 and done[0][done[0].index("-pass") + 1] == "1"
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_the_progress_rises_through_both_passes(tmp_path, source_dir, small_unit):
    need_encoders("libx264", "aac")
    path = busy_video(source_dir / "busy.mp4", seconds=6.0)
    seen = []
    ctx = ToolContext(tmp_path / "scratch", progress=lambda value, label: seen.append(value))

    LightenVideo().run([ctx.probe(path, "video")], params_for(TOOL, target=16), ctx)

    assert seen and seen == sorted(seen)
    assert max(value for value in seen if value <= 0.4) > 0.1
    assert max(seen) > 0.6


def test_the_room_covers_the_target_and_the_pass_files(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    asked = []
    real = lighten.make_room

    def spy(ctx, cap, needed=0, unstoppable=0):
        asked.append((cap, needed))
        return real(ctx, cap, needed, unstoppable)

    monkeypatch.setattr(lighten, "make_room", spy)

    lightened(ctx, path, target=16)

    duration = common.longest(ctx.probe(path, "video").duration, common.read_streams(path).duration)
    assert asked == [(16 * UNIT + lighten.pass_log_bytes(duration, 25.0, 320, 240),) * 2]


def test_the_pass_files_are_counted_generously_and_stay_small_for_every_plan(tmp_path):
    assert lighten.pass_log_bytes(60, 24, 1920, 1080) > 2 * 11_800_000
    source = tmp_path / "big.bin"
    source.write_bytes(b"\0" * (100 * 1000 * 1000))
    for seconds in (5, 60, 600, 1800):
        for target in lighten.TARGETS_MB:
            try:
                chosen = plan(media_like(3840, 2160, seconds, fps=30.0, path=source), *streams_like(rate=30.0), target * lighten.MEGABYTE_SI, seconds)
            except ToolFailed:
                continue
            assert lighten.pass_log_bytes(seconds, 30.0, chosen.width, chosen.height) < 200 * 1000 * 1000


def test_a_plan_whose_largest_file_is_smaller_than_the_target_is_refused_before_encoding(ctx, source_dir, monkeypatch):
    path = busy_video(source_dir / "busy.mp4", seconds=60, size=(64, 48))
    monkeypatch.setattr(limits, "limit_status", lambda user_id, kind: (
        limits.LimitStatus(kind=kind, limit=5 * common.MEGABYTE, used=0) if kind == "upload_file_size" else limits.LimitStatus(kind=kind)
    ))
    ctx.user_id = "someone"

    with pytest.raises(ToolFailed, match="^The result would weigh more than 5 MB, the largest file you may keep"):
        lightened(ctx, path, target=8)
    assert ctx.commands == []


def test_the_thread_setting_bounds_both_passes(ctx, source_dir, small_unit, server_settings):
    server_settings["ffmpeg_threads"] = 2
    path = busy_video(source_dir / "busy.mp4")

    lightened(ctx, path, target=16)

    for command in ctx.commands:
        values = [value for flag, value in zip(command, command[1:]) if flag == "-threads"]
        assert values == ["2", "2"]


def test_a_video_longer_than_the_admin_limit_is_refused(ctx, source_dir, server_settings):
    server_settings["max_minutes"] = 1
    path = make_video(source_dir / "long.mp4", seconds=62, size=(64, 48), fps=5)

    with pytest.raises(ToolFailed, match="Media Converter takes files of up to 1 minute on this server"):
        lightened(ctx, path, target=8)


def test_a_video_whose_length_is_unknown_is_refused(ctx, source_dir, monkeypatch):
    path = make_video(source_dir / "clip.mp4", seconds=1.0, size=(64, 48))
    media = ctx.probe(path, "video").with_changes(duration=None)
    monkeypatch.setattr(lighten, "read_streams", lambda path: common.Streams(streams=common.read_streams(path).streams, tags={}, duration=None))

    with pytest.raises(ToolFailed, match="^Media Converter cannot read the length of this video$"):
        LightenVideo().run([media], params_for(TOOL), ctx)


def test_a_piped_video_that_states_no_length_is_refused_before_encoding(ctx, source_dir):
    need_encoders("libx264", "aac")
    path = piped(source_dir / "piped.mkv", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=2",
                 "-c:v", "libx264", "-preset", "ultrafast", "-f", "matroska")

    with pytest.raises(ToolFailed, match="^Media Converter cannot read the length of this video$"):
        lightened(ctx, path, target=8)
    assert ctx.commands == []
