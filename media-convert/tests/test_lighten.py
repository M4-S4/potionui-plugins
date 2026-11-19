import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.plugin_api import limits
from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import common, lighten
from tools.lighten import LightenVideo, Plan, frame_cap, frames_to_encode, impossible, pass_log_bytes, plan, smallest_mb

from .conftest import lying_rate, make_video, need_encoders, params_for, piped, probe, run_ffmpeg, streams_of

TOOL = "media-convert.lighten"
UNIT = 20_000
LOCATION = "+48.8566+002.3522/"
MILLION = 1000 * 1000


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


def streams_like(rate=24.0, bit_rate=0, codec="h264"):
    picture = common.Stream(index=0, kind="video", codec=codec, rate=rate)
    return common.Streams(streams=(picture,), tags={}, duration=None), common.Stream(index=1, kind="audio", codec="aac", channels=2, bit_rate=bit_rate)


def heavy_file(tmp_path, size=60 * MILLION):
    source = tmp_path / "big.bin"
    with source.open("wb") as handle:
        handle.truncate(size)
    return source


def watch_runner(ctx, after):
    real = ctx.runner.run

    def run(args, **kwargs):
        try:
            return real(args, **kwargs)
        finally:
            after(list(args))

    ctx.runner.run = run


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
    assert first[first.index("-frames:v") + 1] == str(-(-100 * 102 // 100) + 2)
    assert "-frames:v" not in second
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


def sized_second_pass(monkeypatch, size):
    real = LightenVideo.second_pass

    def sized(self, *args):
        real(self, *args)
        out = args[7]
        with out.open("r+b") as handle:
            handle.truncate(size)

    monkeypatch.setattr(LightenVideo, "second_pass", sized)


def test_the_size_is_checked_on_the_file_written(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    sized_second_pass(monkeypatch, 17 * UNIT)

    with pytest.raises(ToolFailed, match="could not bring this video under 16 MB"):
        lightened(ctx, path, target=16)
    assert len(ctx.commands) == 3


def test_a_result_of_exactly_the_target_counts_as_too_heavy(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    sized_second_pass(monkeypatch, 16 * UNIT)

    with pytest.raises(ToolFailed, match="could not bring this video under 16 MB"):
        lightened(ctx, path, target=16)
    assert len(ctx.commands) == 3


def test_a_second_pass_cut_by_its_room_is_refused_with_a_message_of_this_tool(ctx, source_dir, small_unit, monkeypatch, no_grants):
    path = busy_video(source_dir / "busy.mp4")
    grown = []

    def after(args):
        if "-pass" in args and args[args.index("-pass") + 1] == "1":
            mbtree = Path(args[args.index("-passlogfile") + 1] + "-0.log.mbtree")
            with mbtree.open("ab") as handle:
                handle.write(bytes(pass_log_bytes(frame_cap(4.0, 25.0), 320, 240) + 8 * UNIT))
            grown.append(mbtree)

    watch_runner(ctx, after)

    with pytest.raises(ToolFailed, match=f"^{lighten.ROOM_TEXT}$"):
        lightened(ctx, path, target=16)

    second = ctx.commands[1]
    assert grown and int(second[second.index("-fs") + 1]) < 9 * UNIT
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_an_unreachable_target_is_refused_with_the_smallest_size_before_any_encoding(ctx, source_dir):
    path = make_video(source_dir / "long.mp4", seconds=600, size=(64, 48), fps=5)

    with pytest.raises(ToolFailed) as refused:
        lightened(ctx, path, target=8)

    assert refused.value.message == (
        "This video lasts 10 minutes: to fit in 8 MB, its picture would be too poor to watch. "
        "The smallest file Media Converter can make from it weighs about 17 MB; choose 18 MB or more"
    )
    assert ctx.commands == []


def test_the_smallest_size_counts_the_sound_the_source_really_has(tmp_path):
    source = heavy_file(tmp_path)
    picture, thin = streams_like(bit_rate=32_000)

    with pytest.raises(ToolFailed) as refused:
        plan(media_like(640, 360, 600, path=source), picture, thin, 8 * MILLION, 600, 600)

    assert refused.value.message.endswith("weighs about 15 MB; choose 16 MB or more")
    plan(media_like(640, 360, 600, path=source), picture, thin, 16 * MILLION, 600, 600)
    plan(media_like(640, 360, 600, path=source), picture, thin, 15 * MILLION, 600, 600)
    with pytest.raises(ToolFailed):
        plan(media_like(640, 360, 600, path=source), picture, thin, 14 * MILLION, 600, 600)


def test_the_refusal_offers_to_drop_the_sound_when_that_is_enough(tmp_path):
    source = heavy_file(tmp_path)
    with pytest.raises(ToolFailed) as refused:
        plan(media_like(1920, 1080, 700, path=source), *streams_like(), 16 * MILLION, 700, 700)

    assert refused.value.message == (
        "This video lasts 12 minutes: to fit in 16 MB, its picture would be too poor to watch. "
        "The smallest file Media Converter can make from it weighs about 20 MB; choose 20 MB or more, or turn off Keep the sound"
    )
    silent = plan(media_like(1920, 1080, 700, path=source), streams_like()[0], None, 16 * MILLION, 700, 700)
    assert silent.audio_kbps == 0 and silent.video_kbps >= lighten.MIN_VIDEO_KBPS


def test_a_video_too_long_for_every_size_with_sound_but_not_without_is_told_both(tmp_path):
    message = impossible(50 * MILLION, 1797, streams_like()[1]).message

    assert message.endswith("weighs about 51 MB; turn off Keep the sound, or trim it into shorter parts first")
    plan(media_like(640, 360, 1797, path=heavy_file(tmp_path)), streams_like()[0], None, 50 * MILLION, 1797, 1797)


def test_a_video_too_long_for_every_size_with_sound_is_told_which_size_works_without(tmp_path):
    message = impossible(30 * MILLION, 1797, streams_like()[1]).message

    assert message.endswith(
        "weighs about 51 MB; turn off Keep the sound and choose 50 MB or more, or trim it into shorter parts first"
    )
    with pytest.raises(ToolFailed):
        plan(media_like(640, 360, 1797, path=heavy_file(tmp_path)), streams_like()[0], None, 30 * MILLION, 1797, 1797)


def test_a_video_too_long_for_every_target_is_told_to_be_trimmed():
    message = impossible(50 * MILLION, 3 * 3600, streams_like()[1]).message

    assert message.endswith("; trim it into shorter parts first")
    assert "or turn off Keep the sound" not in message


def test_the_smallest_size_is_the_floor_bitrate_with_the_margin():
    sound = streams_like()[1]
    assert smallest_mb(600, sound) == 17
    assert smallest_mb(600, None) == 12
    assert smallest_mb(60, sound) == 2
    assert smallest_mb(600, replace(sound, bit_rate=32_000)) == 15


@pytest.mark.parametrize("target, side", [(8, (1280, 720)), (16, (1280, 720)), (20, (1920, 1080)), (50, (1920, 1080))])
def test_the_picture_shrinks_until_each_pixel_gets_enough_bits(tmp_path, target, side):
    chosen = plan(media_like(1920, 1080, 60, path=heavy_file(tmp_path)), *streams_like(), target * MILLION, 60, 60)

    assert (chosen.width, chosen.height) == side
    assert chosen.audio_kbps == 128
    assert chosen.video_kbps + chosen.audio_kbps <= target * MILLION * 0.96 * 8 / 60 / 1000


def test_a_light_source_keeps_the_size_the_target_allows(tmp_path):
    source = heavy_file(tmp_path, 800 * 1000)
    picture, _ = streams_like(rate=24.0, codec="vp9")

    chosen = plan(media_like(1920, 1080, 60, path=source), picture, None, 16 * MILLION, 60, 60)

    assert (chosen.width, chosen.height) == (1920, 1080)
    assert chosen.video_kbps <= 800 * 1000 * 8 / 60 / 1000 * 1.5


def test_the_sound_gets_less_room_when_the_budget_is_tight(tmp_path):
    source = heavy_file(tmp_path)

    assert plan(media_like(640, 360, 180, path=source), *streams_like(), 8 * MILLION, 180, 180).audio_kbps == 64
    assert plan(media_like(640, 360, 90, path=source), *streams_like(), 8 * MILLION, 90, 90).audio_kbps == 96
    assert plan(media_like(640, 360, 60, path=source), *streams_like(bit_rate=48_000), 8 * MILLION, 60, 60).audio_kbps == 48


@pytest.mark.parametrize("codec, growth", [("h264", 1.0), ("vp9", 1.5), ("hevc", 1.5)])
def test_a_source_lighter_than_the_target_is_not_inflated(tmp_path, codec, growth):
    source = heavy_file(tmp_path, 1000 * 1000)
    picture, sound = streams_like(codec=codec)

    chosen = plan(media_like(1280, 720, 10, path=source), picture, sound, 50 * MILLION, 10, 10)

    assert chosen.video_kbps + chosen.audio_kbps <= 1000 * 1000 * 8 / 10 / 1000 * growth * 0.96


def test_an_h264_video_with_mp3_sound_comes_out_lighter_than_it_was(ctx, source_dir):
    need_encoders("libmp3lame")
    path = source_dir / "mp3.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=6", "-f", "lavfi", "-i", "sine=duration=6",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "libmp3lame", "-b:a", "128k", path,
    )

    result = lightened(ctx, path, target=16)

    assert len(ctx.commands) == 2
    assert result.path.stat().st_size < path.stat().st_size


def test_an_h264_mp4_already_under_the_target_is_copied_without_encoding(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p", "-metadata", f"location={LOCATION}"))

    result = lightened(ctx, path, target=8)

    [command] = ctx.commands
    assert command[command.index("-c") + 1] == "copy"
    assert "-pass" not in command
    assert [s["codec_name"] for s in probe(result.path)["streams"]] == ["h264", "aac"]
    assert "location" not in (probe(result.path)["format"].get("tags") or {})


def test_a_copy_cut_by_its_room_is_refused_and_not_published(ctx, source_dir, monkeypatch, no_grants):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p"))
    real = lighten.make_room

    def tight(ctx, cap, needed=0, unstoppable=0, scratch=0):
        room = real(ctx, cap, needed, unstoppable, scratch)
        return replace(room, size=needed // 2)

    monkeypatch.setattr(lighten, "make_room", tight)

    with pytest.raises(ToolFailed, match=f"^{lighten.ROOM_TEXT}$"):
        lightened(ctx, path, target=8)
    [command] = ctx.commands
    assert command[command.index("-c") + 1] == "copy"
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_a_copy_that_reaches_the_target_is_encoded_instead(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p"))

    def after(args):
        if "-c" in args and args[args.index("-c") + 1] == "copy":
            with open(args[-1], "r+b") as handle:
                handle.truncate(8 * MILLION)

    watch_runner(ctx, after)

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 3
    assert result.path.stat().st_size < 8 * MILLION
    assert "-pass" in ctx.commands[-1]


def test_a_copy_keeps_the_place_only_when_asked(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p", "-metadata", f"location={LOCATION}"))

    result = lightened(ctx, path, target=8, keep_metadata=True)

    assert len(ctx.commands) == 1
    assert probe(result.path)["format"]["tags"]["location"] == LOCATION


def test_an_h264_and_aac_video_in_another_container_is_encoded_again(ctx, source_dir):
    path = make_video(source_dir / "clip.mkv", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p"))

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 2
    assert [s["codec_name"] for s in probe(result.path)["streams"]] == ["h264", "aac"]


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


@pytest.mark.parametrize("extra, channels", [
    (("-c:a", "libmp3lame"), 1),
    (("-af", "aformat=channel_layouts=5.1"), 2),
    (("-pix_fmt", "yuv444p"), 1),
    (("-pix_fmt", "yuv420p10le"), 1),
])
def test_a_small_mp4_that_would_not_play_everywhere_is_encoded_again(ctx, source_dir, extra, channels):
    need_encoders("libmp3lame")
    path = source_dir / "clip.mp4"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", *extra, path,
    )

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 2
    assert streams_of(result.path, "video")[0]["pix_fmt"] == "yuv420p"
    [sound] = streams_of(result.path, "audio")
    assert sound["codec_name"] == "aac" and sound["channels"] == channels


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


def sound_longer_than_picture(folder):
    path = folder / "longer.mkv"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=2", "-f", "lavfi", "-i", "sine=duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", path,
    )
    return path


def test_a_sound_longer_than_the_picture_is_kept_whole_or_left_out(ctx, source_dir):
    path = sound_longer_than_picture(source_dir)

    with_sound = lightened(ctx, path, target=8)
    without = lightened(ctx, path, target=8, keep_sound=False)

    assert float(probe(with_sound.path)["format"]["duration"]) == pytest.approx(4.0, abs=0.1)
    assert float(probe(without.path)["format"]["duration"]) == pytest.approx(2.0, abs=0.1)
    assert streams_of(without.path, "audio") == []


def test_the_length_planned_is_that_of_the_tracks_kept(source_dir):
    path = sound_longer_than_picture(source_dir)
    streams = common.read_streams(path)

    assert lighten.encoded_seconds(streams, None, 9.0) == pytest.approx(2.0, abs=0.05)
    assert lighten.encoded_seconds(streams, streams.audio[0], 9.0) == pytest.approx(4.0, abs=0.05)
    bare = common.Streams(streams=(replace(streams.video, duration=None),), tags={}, duration=4.0)
    assert lighten.encoded_seconds(bare, None, 9.0) == 9.0


def test_the_first_pass_is_bounded_by_the_frames_the_file_really_holds(ctx, source_dir):
    path = sound_longer_than_picture(source_dir)

    lightened(ctx, path, target=8, keep_sound=False)

    first = ctx.commands[0]
    assert common.count_frames(path, 0) == 50
    assert first[first.index("-frames:v") + 1] == "53"


def test_without_a_frame_count_the_bound_follows_the_stated_rate(ctx, source_dir, monkeypatch):
    path = sound_longer_than_picture(source_dir)
    monkeypatch.setattr(lighten, "count_frames", lambda *args: None)
    streams = common.read_streams(path)

    assert frames_to_encode(ctx.probe(path, "video"), streams, 2.0) == frame_cap(2.0, 25.0)


def test_a_first_pass_that_reaches_its_bound_is_refused_before_the_second(ctx, source_dir, small_unit, monkeypatch, no_grants):
    path = busy_video(source_dir / "busy.mp4")
    monkeypatch.setattr(lighten, "count_frames", lambda *args: 10)

    with pytest.raises(ToolFailed, match="^This video does not hold what its file states"):
        lightened(ctx, path, target=16)

    [first] = ctx.commands
    assert first[first.index("-frames:v") + 1] == "13"
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_a_file_that_states_too_low_a_frame_rate_is_lightened_within_its_room(ctx, source_dir, monkeypatch):
    path = lying_rate(source_dir)
    assert common.read_streams(path).video.rate == pytest.approx(1.0)
    held = []
    real = lighten.make_room

    def spy(ctx, cap, needed=0, unstoppable=0, scratch=0):
        held.append(scratch)
        return real(ctx, cap, needed, unstoppable, scratch)

    monkeypatch.setattr(lighten, "make_room", spy)
    written = []

    def after(args):
        if "-pass" in args and args[args.index("-pass") + 1] == "1":
            written.append(sum(p.stat().st_size for p in ctx.scratch_dir.glob("pass-*")))

    watch_runner(ctx, after)

    result = lightened(ctx, path, target=8, keep_sound=False)

    [scratch] = held
    assert written and written[0] <= scratch
    assert scratch == pass_log_bytes(-(-150 * 102 // 100) + 2, 320, 240)
    assert common.count_frames(result.path, 0) == 150
    assert sorted(item.name for item in ctx.scratch_dir.iterdir()) == [result.path.name]


def test_a_result_shorter_than_its_source_is_refused_with_the_cause(ctx, source_dir, small_unit, monkeypatch, no_grants):
    path = busy_video(source_dir / "busy.mp4")
    real = lighten.read_streams

    def shorter(found):
        streams = real(found)
        if Path(found).parent == ctx.scratch_dir:
            picture = replace(streams.video, duration=1.0)
            return common.Streams(streams=(picture, *streams.audio), tags=streams.tags, duration=1.0)
        return streams

    monkeypatch.setattr(lighten, "read_streams", shorter)

    with pytest.raises(ToolFailed, match="^This video does not hold what its file states"):
        lightened(ctx, path, target=16)

    assert len(ctx.commands) == 2
    assert list(ctx.scratch_dir.iterdir()) == []
    assert not no_grants


def test_the_frames_are_counted_only_once_the_quota_and_the_disk_allow_the_size(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    counted = []
    monkeypatch.setattr(lighten, "count_frames", lambda *args: counted.append(args) or 100)
    quota(monkeypatch, ctx, storage=10 * UNIT)

    with pytest.raises(ToolFailed, match="what is left of your storage"):
        lightened(ctx, path, target=16)
    assert counted == [] and ctx.commands == []

    quota(monkeypatch, ctx)
    monkeypatch.setattr(common.shutil, "disk_usage", lambda folder: SimpleNamespace(free=common.DISK_RESERVE + 10 * UNIT))
    with pytest.raises(ToolFailed, match="^The server cannot take this conversion now"):
        lightened(ctx, path, target=16)
    assert counted == [] and ctx.commands == []


def test_cancelling_while_the_frames_are_counted_stops_the_run(tmp_path, source_dir, small_unit, monkeypatch, no_grants):
    need_encoders("libx264", "aac")
    path = busy_video(source_dir / "busy.mp4")
    stop = []
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: bool(stop))
    media = ctx.probe(path, "video")
    seen = []

    def stopped(found, index, is_cancelled=None):
        stop.append(1)
        seen.append(is_cancelled())
        raise ToolCancelled()

    monkeypatch.setattr(lighten, "count_frames", stopped)

    with pytest.raises(ToolCancelled):
        LightenVideo().run([media], params_for(TOOL, target=16), ctx)
    assert seen == [True]
    assert ctx.commands == []
    assert not no_grants


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


def test_cancelling_during_the_second_pass_leaves_nothing(tmp_path, source_dir, small_unit, no_grants):
    need_encoders("libx264", "aac")
    path = busy_video(source_dir / "busy.mp4")
    ctx = ToolContext(tmp_path / "scratch")
    real = ctx.runner.run

    def run(args, **kwargs):
        if "-pass" in args and args[args.index("-pass") + 1] == "2":
            Path(args[-1]).write_bytes(bytes(1000))
            raise ToolCancelled()
        return real(args, **kwargs)

    ctx.runner.run = run

    with pytest.raises(ToolCancelled):
        LightenVideo().run([ctx.probe(path, "video")], params_for(TOOL, target=16), ctx)

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

    def spy(ctx, cap, needed=0, unstoppable=0, scratch=0):
        asked.append((cap, needed, scratch))
        return real(ctx, cap, needed, unstoppable, scratch)

    monkeypatch.setattr(lighten, "make_room", spy)

    lightened(ctx, path, target=16)

    logs = pass_log_bytes(-(-100 * 102 // 100) + 2, 320, 240)
    assert asked == [(16 * UNIT + logs, 16 * UNIT + logs, logs)]


def test_the_pass_files_are_counted_generously_and_stay_small_for_every_plan(tmp_path):
    assert pass_log_bytes(frame_cap(60, 24), 1920, 1080) > 2 * 11_800_000
    source = heavy_file(tmp_path, 100 * MILLION)
    for seconds in (5, 60, 600, 1800):
        for target in lighten.TARGETS_MB:
            try:
                chosen = plan(media_like(3840, 2160, seconds, fps=30.0, path=source), *streams_like(rate=30.0), target * MILLION, seconds, seconds)
            except ToolFailed:
                continue
            assert pass_log_bytes(frame_cap(seconds, 30.0), chosen.width, chosen.height) < 200 * MILLION


def quota(monkeypatch, ctx, storage=None, largest=None):
    def status(user_id, kind):
        if kind == "storage_bytes" and storage is not None:
            return limits.LimitStatus(kind=kind, limit=storage, used=0)
        if kind == "upload_file_size" and largest is not None:
            return limits.LimitStatus(kind=kind, limit=largest, used=0)
        return limits.LimitStatus(kind=kind)

    monkeypatch.setattr(limits, "limit_status", status)
    ctx.user_id = "someone"


def test_the_pass_files_do_not_count_against_the_storage_left_to_the_user(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    quota(monkeypatch, ctx, storage=40 * UNIT)

    result = lightened(ctx, path, target=30)

    assert result.path.stat().st_size < 30 * UNIT


def test_a_largest_file_equal_to_the_target_is_allowed(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    quota(monkeypatch, ctx, largest=50 * UNIT)

    result = lightened(ctx, path, target=50)

    assert result.path.stat().st_size < 50 * UNIT


def test_a_largest_file_under_the_target_names_the_size_to_choose(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    quota(monkeypatch, ctx, largest=20 * UNIT)

    with pytest.raises(ToolFailed, match="^Your files may weigh at most 20 MB; choose 20 MB or less$"):
        lightened(ctx, path, target=30)
    assert ctx.commands == []


def test_too_little_storage_left_is_refused_with_a_message_of_this_tool(ctx, source_dir, small_unit, monkeypatch):
    path = busy_video(source_dir / "busy.mp4")
    quota(monkeypatch, ctx, storage=10 * UNIT)

    with pytest.raises(ToolFailed, match="^This video would not fit in what is left of your storage; free some space or choose a smaller size$"):
        lightened(ctx, path, target=16)
    assert ctx.commands == []


def test_a_plan_whose_largest_file_is_smaller_than_every_size_is_refused_before_encoding(ctx, source_dir, monkeypatch):
    path = busy_video(source_dir / "busy.mp4", seconds=60, size=(64, 48))
    quota(monkeypatch, ctx, largest=5 * common.MEGABYTE)

    with pytest.raises(ToolFailed, match="^Your files may weigh at most 5.2 MB, less than the smallest size Lighten for sending makes$"):
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


def test_stream_lengths_are_read_from_the_container_tags_too(source_dir):
    path = sound_longer_than_picture(source_dir)

    streams = common.read_streams(path)

    assert streams.video.duration == pytest.approx(2.0, abs=0.05)
    assert streams.audio[0].duration == pytest.approx(4.0, abs=0.05)


def test_a_held_file_changes_no_lightened_result(ctx, source_dir, small_unit, monkeypatch, no_grants, held_scratch):
    path = busy_video(source_dir / "busy.mp4")
    inflated(monkeypatch, 1.4)

    result = lightened(ctx, path, target=16)

    assert len(ctx.commands) == 3
    assert result.path.name == Path(ctx.commands[-1][-1]).name
    assert result.path.stat().st_size < 16 * UNIT
    assert Path(ctx.commands[1][-1]).name in held_scratch and any(name.startswith("pass-") for name in held_scratch)
    assert not no_grants


def test_a_held_copy_is_still_encoded_instead(ctx, source_dir, no_grants, held_scratch):
    path = make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p"))

    def after(args):
        if "-c" in args and args[args.index("-c") + 1] == "copy":
            with open(args[-1], "r+b") as handle:
                handle.truncate(8 * MILLION)

    watch_runner(ctx, after)

    result = lightened(ctx, path, target=8)

    assert len(ctx.commands) == 3 and "-pass" in ctx.commands[-1]
    assert result.path.stat().st_size < 8 * MILLION
    assert Path(ctx.commands[0][-1]).name in held_scratch
    assert not no_grants


def over_twice(ctx, source_dir, monkeypatch):
    monkeypatch.setattr(lighten, "MEGABYTE_SI", UNIT)
    inflated(monkeypatch, 1.4)
    monkeypatch.setattr(lighten, "SMALLEST_VIDEO_KBPS", 10_000)
    return busy_video(source_dir / "busy.mp4"), 16, "Media Converter could not bring this video under 16 MB; choose a larger size"


def copy_without_room(ctx, source_dir, monkeypatch):
    real = lighten.make_room

    def tight(ctx, cap, needed=0, unstoppable=0, scratch=0):
        return replace(real(ctx, cap, needed, unstoppable, scratch), size=needed // 2)

    monkeypatch.setattr(lighten, "make_room", tight)
    return make_video(source_dir / "clip.mp4", seconds=2.0, size=(64, 48), extra=("-pix_fmt", "yuv420p")), 8, lighten.ROOM_TEXT


def shorter_result(ctx, source_dir, monkeypatch):
    monkeypatch.setattr(lighten, "MEGABYTE_SI", UNIT)
    real = lighten.read_streams

    def shorter(found):
        streams = real(found)
        if Path(found).parent == ctx.scratch_dir:
            picture = replace(streams.video, duration=1.0)
            return common.Streams(streams=(picture, *streams.audio), tags=streams.tags, duration=1.0)
        return streams

    monkeypatch.setattr(lighten, "read_streams", shorter)
    return busy_video(source_dir / "busy.mp4"), 16, lighten.NOT_AS_STATED


@pytest.mark.parametrize("scenario", [over_twice, copy_without_room, shorter_result])
def test_a_held_file_keeps_the_refusal_of_lighten(ctx, source_dir, monkeypatch, no_grants, held_scratch, scenario):
    path, target, message = scenario(ctx, source_dir, monkeypatch)

    with pytest.raises(ToolFailed) as caught:
        lightened(ctx, path, target=target)

    assert str(caught.value) == message
    assert held_scratch
    assert not no_grants


@pytest.mark.parametrize("error", [ToolCancelled(), ToolFailed("Failed to encode the media")], ids=["cancelled", "failed"])
def test_a_held_file_keeps_the_error_that_stopped_lighten(tmp_path, source_dir, small_unit, no_grants, held_scratch, error):
    need_encoders("libx264", "aac")
    path = busy_video(source_dir / "busy.mp4")
    ctx = ToolContext(tmp_path / "scratch")
    real = ctx.runner.run
    stopped = []

    def run(args, **kwargs):
        if "-pass" in args and args[args.index("-pass") + 1] == "2":
            stopped.append(Path(args[-1]))
            stopped[-1].write_bytes(bytes(1000))
            raise error
        return real(args, **kwargs)

    ctx.runner.run = run

    with pytest.raises(type(error)) as caught:
        LightenVideo().run([ctx.probe(path, "video")], params_for(TOOL, target=16), ctx)

    assert caught.value is error
    assert stopped[0].name in held_scratch and any(name.startswith("pass-") for name in held_scratch)
    assert not no_grants


def test_a_held_file_is_told_in_the_log_without_its_path(ctx, source_dir, small_unit, monkeypatch, no_grants, held_scratch, caplog):
    path = busy_video(source_dir / "busy.mp4")
    inflated(monkeypatch, 1.4)

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        result = lightened(ctx, path, target=16)

    assert result.path.stat().st_size < 16 * UNIT
    found = [record for record in caplog.records if record.name == "plugins.media-convert"]
    assert held_scratch and len(found) == len(held_scratch)
    assert {record.getMessage() for record in found} == {"Media Converter could not remove a working file: PermissionError"}
    assert all(record.levelno == logging.WARNING for record in found)
    assert not any(name in record.getMessage() for record in found for name in (str(ctx.scratch_dir), *held_scratch))
    assert not no_grants
