import logging
from collections import namedtuple

import pytest

from src.plugin_api import limits
from src.plugin_api.media_tools import ToolContext, ToolFailed

from tools import audio, common
from tools.audio import ConvertAudio
from tools.image import ConvertImage
from tools.video import ConvertVideo

from tools.extract_audio import ExtractAudio

from .conftest import make_audio, make_video, need_target, noisy_image, params_for, piped, run_ffmpeg

Usage = namedtuple("Usage", "total used free")
MB = common.MEGABYTE
DISK_FULL = "The server cannot take this conversion now; try again later or ask an admin"


def fill(folder, size, name="earlier.bin"):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / name).open("wb") as handle:
        handle.truncate(size)


def free_space(monkeypatch, free):
    asked = []

    def usage(path):
        asked.append(path)
        return Usage(free * 4, free * 3, free)

    monkeypatch.setattr(common.shutil, "disk_usage", usage)
    return asked


def quota(monkeypatch, storage_left=None, largest=None, fail=False):
    asked = []

    def status(user_id, kind):
        asked.append((user_id, kind))
        if fail:
            raise RuntimeError("no plans here")
        if kind == "storage_bytes" and storage_left is not None:
            return limits.LimitStatus(kind=kind, limit=storage_left + 1000, used=1000)
        if kind == "upload_file_size" and largest is not None:
            return limits.LimitStatus(kind=kind, limit=largest)
        return limits.LimitStatus(kind=kind)

    monkeypatch.setattr(limits, "limit_status", status)
    return asked


def run_sound(ctx, path, **given):
    return ConvertAudio().run([ctx.probe(path, "audio")], params_for("media-convert.audio", **given), ctx)[0]


def outputs(ctx):
    return sorted(path.name for path in ctx.scratch_dir.iterdir() if path.name.startswith("out-"))


def test_the_run_budget_counts_every_file_already_in_the_scratch_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RUN_BUDGET", 100 * MB)
    ctx = ToolContext(tmp_path / "scratch")
    fill(ctx.scratch_dir, 30 * MB)
    fill(ctx.scratch_dir / "step", 20 * MB, "deeper.bin")

    found = {room.reason: room.size for room in common.rooms(ctx, 4 << 30)}

    assert found["run"] == 50 * MB
    room = common.make_room(ctx, 4 << 30)
    common.release(room)
    assert room == common.Room(50 * MB, "run")


def test_the_disk_room_keeps_the_reserve_and_is_shared_by_two_runs(tmp_path, monkeypatch):
    asked = free_space(monkeypatch, common.DISK_RESERVE + 600 * MB)
    ctx = ToolContext(tmp_path / "scratch")

    room = common.make_room(ctx, 4 << 30)
    common.release(room)

    assert room == common.Room(300 * MB, "disk")
    assert asked == [ctx.scratch_dir]
    assert 2 * room.size + common.DISK_RESERVE <= common.DISK_RESERVE + 600 * MB


def test_without_a_user_the_quota_is_not_read(tmp_path, monkeypatch):
    asked = quota(monkeypatch, storage_left=MB)

    assert [room.reason for room in common.rooms(ToolContext(tmp_path / "scratch"), 4 << 30)] == ["file", "run", "disk"]
    assert asked == []


def test_the_storage_left_counts_what_the_run_already_wrote(tmp_path, monkeypatch):
    asked = quota(monkeypatch, storage_left=40 * MB, largest=25 * MB)
    ctx = ToolContext(tmp_path / "scratch", user_id="someone")
    fill(ctx.scratch_dir, 10 * MB)

    found = {room.reason: room.size for room in common.rooms(ctx, 4 << 30)}

    assert found["storage"] == 30 * MB
    assert found["upload"] == 25 * MB
    room = common.make_room(ctx, 4 << 30)
    common.release(room)
    assert room == common.Room(25 * MB, "upload")
    assert ("someone", "storage_bytes") in asked and ("someone", "upload_file_size") in asked


@pytest.mark.parametrize("fail", [False, True])
def test_an_unlimited_user_or_an_unreadable_plan_leaves_the_quota_out(tmp_path, monkeypatch, caplog, fail):
    quota(monkeypatch, fail=fail)
    ctx = ToolContext(tmp_path / "scratch", user_id="admin")

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        assert [room.reason for room in common.rooms(ctx, 4 << 30)] == ["file", "run", "disk"]

    found = [record for record in caplog.records if record.name == "plugins.media-convert"]
    if fail:
        assert [record.getMessage() for record in found] == [
            "Media Converter could not read the storage_bytes limit and converts without it: RuntimeError",
            "Media Converter could not read the upload_file_size limit and converts without it: RuntimeError",
        ]
        assert all(record.levelno == logging.WARNING for record in found)
    else:
        assert found == []


def test_a_plan_that_cannot_be_read_leaves_a_line_in_the_log_and_the_conversion_goes_on(tmp_path, source_dir, monkeypatch, caplog):
    quota(monkeypatch, fail=True)
    path = make_audio(source_dir / "a.mp3", codec_args=("-c:a", "libmp3lame"))
    ctx = ToolContext(tmp_path / "scratch", user_id="someone")

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        made = run_sound(ctx, path, format="flac")

    assert made.path.is_file()
    lines = [record.getMessage() for record in caplog.records if record.name == "plugins.media-convert"]
    assert "Media Converter could not read the storage_bytes limit and converts without it: RuntimeError" in lines
    assert not any("someone" in line for line in lines)


@pytest.mark.parametrize(
    "reason,text",
    [
        ("run", "This run would write more than 8 GB, the most Media Converter writes in one run; convert fewer items at a time"),
        ("disk", DISK_FULL),
        ("storage", "This result would not fit in what is left of your storage; free some space or convert fewer items at a time"),
        ("upload", "The result would weigh more than 25 MB, the largest file you may keep; choose a lighter format"),
        ("file", "The result would weigh more than 25 MB, the most Media Converter writes for this file; choose a lighter format"),
    ],
)
def test_each_bound_says_what_to_do(reason, text):
    assert common.room_message(common.Room(25 * MB, reason)) == text


@pytest.mark.parametrize("size,text", [(8 << 30, "8 GB"), (4 << 30, "4 GB"), (325 * MB + 5, "325 MB"), (512 * 1024, "512 KB"), (10, "1 KB")])
def test_sizes_are_written_in_the_largest_unit_that_keeps_them_whole(size, text):
    assert common.size_text(size) == text


def test_a_spent_run_budget_refuses_before_any_encoding(tmp_path, source_dir, monkeypatch):
    monkeypatch.setattr(common, "RUN_BUDGET", 40 * MB)
    ctx = ToolContext(tmp_path / "scratch")
    fill(ctx.scratch_dir, 40 * MB - MB // 2)
    sound = make_audio(source_dir / "a.mp3", codec_args=("-c:a", "libmp3lame"))
    clip = make_video(source_dir / "a.mp4")
    picture = noisy_image(source_dir / "a.png", size=(64, 64))

    for tool, media, params in (
        (ConvertAudio(), ctx.probe(sound, "audio"), params_for("media-convert.audio", format="flac")),
        (ConvertVideo(), ctx.probe(clip, "video"), params_for("media-convert.video", format="mov")),
        (ConvertImage(), ctx.probe(picture, "image"), params_for("media-convert.image", format="jpeg")),
    ):
        with pytest.raises(ToolFailed, match="convert fewer items at a time"):
            tool.run([media], params, ctx)

    assert ctx.commands == []
    assert outputs(ctx) == []


def test_writing_stops_where_the_run_budget_ends(tmp_path, source_dir, monkeypatch):
    path = piped(source_dir / "noise.flac", "-f", "lavfi", "-i", "anoisesrc=d=20:c=white:r=44100", "-ac", "2", "-c:a", "flac", "-f", "flac")
    monkeypatch.setattr(common, "RUN_BUDGET", 6 * MB)
    ctx = ToolContext(tmp_path / "scratch")
    fill(ctx.scratch_dir, 4 * MB)

    with pytest.raises(ToolFailed, match="convert fewer items at a time"):
        run_sound(ctx, path, format="wav")

    [written] = outputs(ctx)
    size = (ctx.scratch_dir / written).stat().st_size
    assert 2 * MB <= size < 2 * MB + 256 * 1024
    assert ctx.commands[0][ctx.commands[0].index("-fs") + 1] == str(2 * MB)


def test_a_wav_known_to_be_too_heavy_for_the_room_left_is_refused_before_encoding(tmp_path, source_dir, monkeypatch):
    path = make_audio(source_dir / "talk.mp3", seconds=20, channels=2, codec_args=("-c:a", "libmp3lame"))
    monkeypatch.setattr(common, "RUN_BUDGET", 3 * MB)
    ctx = ToolContext(tmp_path / "scratch")

    with pytest.raises(ToolFailed, match="convert fewer items at a time"):
        run_sound(ctx, path, format="wav")
    assert ctx.commands == []

    monkeypatch.setattr(common, "RUN_BUDGET", 4 * MB)
    made = run_sound(ctx, path, format="wav")
    assert 3 * MB < made.path.stat().st_size < 4 * MB


def test_below_the_disk_reserve_nothing_is_encoded(tmp_path, source_dir, monkeypatch):
    sound = make_audio(source_dir / "a.mp3", codec_args=("-c:a", "libmp3lame"))
    picture = noisy_image(source_dir / "a.png", size=(64, 64))
    free_space(monkeypatch, common.DISK_RESERVE + MB)
    ctx = ToolContext(tmp_path / "scratch")

    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        run_sound(ctx, sound, format="m4a")
    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        ConvertImage().run([ctx.probe(picture, "image")], params_for("media-convert.image", format="jpeg"), ctx)

    assert ctx.commands == []
    assert outputs(ctx) == []


def test_a_full_disk_tells_the_user_what_to_do_and_the_log_what_was_free(tmp_path, source_dir, monkeypatch, caplog):
    sound = make_audio(source_dir / "a.mp3", codec_args=("-c:a", "libmp3lame"))
    free = common.DISK_RESERVE + MB
    free_space(monkeypatch, free)
    ctx = ToolContext(tmp_path / "scratch")

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        with pytest.raises(ToolFailed) as refused:
            run_sound(ctx, sound, format="m4a")

    assert str(refused.value) == DISK_FULL
    assert not any(char.isdigit() for char in str(refused.value))
    [line] = [record for record in caplog.records if record.name == "plugins.media-convert"]
    assert line.levelno == logging.WARNING
    assert line.getMessage() == (
        "Media Converter refused a conversion for lack of disk space: "
        f"{free} bytes free, {2 << 30} bytes kept free, 0 bytes promised to conversions still running, {MB // 2} bytes for this conversion, at least {MB} bytes needed"
    )


def test_a_result_cut_by_the_disk_room_is_logged_with_what_it_reached(tmp_path, source_dir, monkeypatch, caplog):
    path = piped(source_dir / "noise.flac", "-f", "lavfi", "-i", "anoisesrc=d=20:c=white:r=44100", "-ac", "2", "-c:a", "flac", "-f", "flac")
    free = common.DISK_RESERVE + 4 * MB
    free_space(monkeypatch, free)
    ctx = ToolContext(tmp_path / "scratch")

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
            run_sound(ctx, path, format="wav")

    [written] = outputs(ctx)
    size = (ctx.scratch_dir / written).stat().st_size
    assert size >= 2 * MB
    [line] = [record.getMessage() for record in caplog.records if record.name == "plugins.media-convert"]
    assert line == (
        "Media Converter refused a conversion for lack of disk space: "
        f"{free} bytes free, {2 << 30} bytes kept free, 0 bytes promised to conversions still running, {2 * MB} bytes for this conversion, at least {size} bytes needed"
    )


def test_an_image_is_written_only_when_the_disk_can_hold_its_largest_possible_result(tmp_path, source_dir, monkeypatch):
    picture = noisy_image(source_dir / "big.png", size=(1024, 1024))
    ctx = ToolContext(tmp_path / "scratch")
    params = params_for("media-convert.image", format="webp")
    free_space(monkeypatch, common.DISK_RESERVE + 2 * 5 * MB)

    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        ConvertImage().run([ctx.probe(picture, "image")], params, ctx)
    assert outputs(ctx) == []

    free_space(monkeypatch, common.DISK_RESERVE + 2 * 8 * MB)
    assert ConvertImage().run([ctx.probe(picture, "image")], params, ctx)[0].path.is_file()


def test_ffmpeg_never_gets_more_than_half_the_space_above_the_reserve(tmp_path, source_dir, monkeypatch):
    need_target("mp4")
    clip = make_video(source_dir / "a.mp4")
    free_space(monkeypatch, common.DISK_RESERVE + 10 * MB)
    ctx = ToolContext(tmp_path / "scratch")

    ConvertVideo().run([ctx.probe(clip, "video")], params_for("media-convert.video", format="mp4"), ctx)

    args = ctx.commands[0]
    assert args[args.index("-fs") + 1] == str(5 * MB)


def test_a_wav_that_would_not_fit_in_the_storage_left_is_refused_before_encoding(tmp_path, source_dir, monkeypatch):
    path = make_audio(source_dir / "talk.mp3", seconds=20, channels=2, codec_args=("-c:a", "libmp3lame"))
    quota(monkeypatch, storage_left=3 * MB)
    ctx = ToolContext(tmp_path / "scratch", user_id="someone")

    with pytest.raises(ToolFailed, match="would not fit in what is left of your storage"):
        run_sound(ctx, path, format="wav")

    assert ctx.commands == []


def test_writing_stops_when_the_storage_left_is_reached(tmp_path, source_dir, monkeypatch):
    path = piped(source_dir / "noise.mkv", "-f", "lavfi", "-i", "anoisesrc=d=20:c=white:r=44100", "-ac", "2", "-c:a", "flac", "-f", "matroska")
    quota(monkeypatch, storage_left=2 * MB)
    ctx = ToolContext(tmp_path / "scratch", user_id="someone")

    with pytest.raises(ToolFailed, match="would not fit in what is left of your storage"):
        run_sound(ctx, path, format="flac")

    [written] = outputs(ctx)
    assert (ctx.scratch_dir / written).stat().st_size < 2 * MB + 256 * 1024


def test_an_image_heavier_than_the_largest_file_a_user_may_keep_is_refused(tmp_path, source_dir, monkeypatch):
    picture = noisy_image(source_dir / "noise.jpg", size=(1024, 1024), quality=95)
    quota(monkeypatch, largest=MB + MB // 2)
    ctx = ToolContext(tmp_path / "scratch", user_id="someone")

    with pytest.raises(ToolFailed, match="the largest file you may keep"):
        ConvertImage().run([ctx.probe(picture, "image")], params_for("media-convert.image", format="png", max_side=0), ctx)

    small = ConvertImage().run([ctx.probe(picture, "image")], params_for("media-convert.image", format="jpeg", max_side=640), ctx)
    assert small[0].path.stat().st_size < MB


def stream(rate=44100, channels=2):
    return common.Stream(index=0, kind="audio", codec="mp3", channels=channels, sample_rate=rate)


@pytest.mark.parametrize(
    "fmt,depth,rate,channels,cap",
    [
        ("wav", 16, 44100, 2, 325_098_904),
        ("wav", None, 44100, 2, 325_098_904),
        ("wav", 24, 96000, 2, 1_059_172_096),
        ("flac", 16, 48000, 6, 1_059_172_096),
        ("flac", None, 44100, 2, 649_149_232),
        ("flac", 24, 44100, 2, 649_149_232),
        ("mp3", None, 44100, 2, 325_098_904),
        ("ogg", None, 8000, 1, 118_617_856),
        ("m4a", None, 8000, 1, 118_617_856),
    ],
)
@pytest.mark.parametrize("duration", [1790.0, None])
def test_the_cap_of_a_sound_comes_from_its_stream_and_the_length_limit(tmp_path, fmt, depth, rate, channels, cap, duration):
    source = tmp_path / "tiny.flac"
    source.write_bytes(b"x" * 25000)

    assert audio.sound_cap(fmt, depth, stream(rate, channels), source, duration) == cap


def test_the_cap_of_a_sound_without_a_known_rate_keeps_the_rule_of_the_source_size(tmp_path):
    source = tmp_path / "odd.flac"
    source.write_bytes(b"x" * 25000)

    assert audio.sound_cap("wav", 16, stream(0, 2), source, 1790.0) == common.output_cap(source) == common.OUTPUT_FLOOR
    assert audio.sound_cap("wav", 16, stream(44100, 0), source, None) == common.OUTPUT_FLOOR


def test_a_sound_of_unknown_length_never_gets_more_than_the_rule_of_its_source(tmp_path):
    source = tmp_path / "hd.flac"
    source.write_bytes(b"x" * 596_758)
    track = common.Stream(index=0, kind="audio", codec="flac", channels=8, sample_rate=192000)

    assert audio.sound_cap("wav", 24, track, source, None) == common.output_cap(source) == 1 << 30
    assert audio.sound_cap("wav", 24, track, source, 1790.0) == 4 << 30

    big = tmp_path / "big.flac"
    with big.open("wb") as handle:
        handle.truncate(64 * MB)
    assert audio.sound_cap("wav", 24, track, big, None) == 2 << 30


def test_a_seven_point_one_sound_that_states_no_length_gets_the_cap_of_its_source(tmp_path, source_dir):
    path = piped(source_dir / "hd.flac", "-f", "lavfi", "-i", "anullsrc=r=192000:cl=7.1", "-t", "1", "-sample_fmt", "s32",
                 "-c:a", "flac", "-f", "flac")
    ctx = ToolContext(tmp_path / "scratch")
    media = ctx.probe(path, "audio")
    assert not media.duration
    assert not common.read_streams(path).duration

    run_sound(ctx, media.path, format="wav")

    args = ctx.commands[0]
    assert args[args.index("-fs") + 1] == str(1 << 30)


def test_the_same_sound_with_a_known_length_keeps_the_cap_of_its_stream(tmp_path, source_dir):
    path = source_dir / "hd.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "anullsrc=r=192000:cl=7.1", "-t", "1", "-sample_fmt", "s32", "-c:a", "flac", path)
    ctx = ToolContext(tmp_path / "scratch")
    assert ctx.probe(path, "audio").duration

    run_sound(ctx, path, format="wav")

    args = ctx.commands[0]
    assert args[args.index("-fs") + 1] == str(4 << 30)


def test_the_longest_of_the_two_known_lengths_decides_whether_a_wav_fits_before_encoding(tmp_path, source_dir, monkeypatch, server_settings):
    server_settings["max_minutes"] = 1
    path = source_dir / "short-picture.mp4"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=5", "-f", "lavfi", "-i", "sine=frequency=440:duration=50",
               "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path)
    ctx = ToolContext(tmp_path / "scratch")
    media = ctx.probe(path, "video")
    assert media.duration < 10
    assert common.read_streams(path).duration == pytest.approx(50, abs=0.5)
    free_space(monkeypatch, common.DISK_RESERVE + 2 * 3 * MB)

    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        ExtractAudio().run([media], params_for("media-convert.extract-audio", format="wav"), ctx)

    assert ctx.commands == []


def test_a_tiny_source_now_gets_a_cap_its_stream_can_fill_and_no_more(tmp_path, source_dir):
    path = piped(source_dir / "silence.flac", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=5.1", "-t", "59", "-sample_fmt", "s16", "-c:a", "flac", "-f", "flac")
    assert path.stat().st_size < 128 * 1024
    ctx = ToolContext(tmp_path / "scratch")

    made = run_sound(ctx, path, format="wav")

    args = ctx.commands[0]
    cap = int(args[args.index("-fs") + 1])
    assert cap == 1_059_172_096
    assert cap < common.OUTPUT_FLOOR
    assert made.path.stat().st_size == pytest.approx(59 * 48000 * 6 * 2, rel=0.01)


def test_seven_point_one_at_192_khz_for_thirty_minutes_is_refused_before_encoding(tmp_path, source_dir, monkeypatch):
    path = make_audio(source_dir / "hd.flac", seconds=1, rate=192000, channels=6, codec_args=("-c:a", "flac", "-sample_fmt", "s32"))
    ctx = ToolContext(tmp_path / "scratch")
    media = ctx.probe(path, "audio").with_changes(duration=1790.0)
    track = common.Stream(index=0, kind="audio", codec="flac", channels=8, sample_rate=192000)
    monkeypatch.setattr(audio, "read_streams", lambda found: common.Streams(streams=(track,), tags={}, duration=1790.0))

    with pytest.raises(ToolFailed, match="more than 4 GB, the most Media Converter writes for this file"):
        ConvertAudio().run([media], params_for("media-convert.audio", format="wav"), ctx)

    assert ctx.commands == []
