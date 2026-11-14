import threading

import psutil
import pytest

from src.plugin_api.media import upload_formats
from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import common
from tools.video import ConvertVideo

from .conftest import (
    make_video,
    need_encoders,
    need_target,
    params_for,
    piped,
    probe,
    run_ffmpeg,
    stream_bytes,
    streams_of,
)

TOOL = "media-convert.video"
EXPECTED = {
    "mp4": (".mp4", "mov,mp4,m4a,3gp,3g2,mj2", "h264", "aac", ("libx264", "aac")),
    "mov": (".mov", "mov,mp4,m4a,3gp,3g2,mj2", "h264", "aac", ("libx264", "aac")),
    "webm": (".webm", "matroska,webm", "vp9", "opus", ("libvpx-vp9", "libopus")),
}


def convert(ctx, path, **given):
    need_target(given.get("format", "mp4"))
    return ConvertVideo().run([ctx.probe(path, "video")], params_for(TOOL, **given), ctx)[0]


def rich_source(folder):
    subtitles = folder / "words.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:00,800\nHello\n\n", encoding="utf-8")
    path = folder / "rich.mkv"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=1",
        "-i", subtitles,
        "-map", "0", "-map", "1", "-map", "2", "-map", "3",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-c:s", "srt",
        "-metadata", "title=Holiday", "-metadata:s:a:1", "language=fra", path,
    )
    return path


@pytest.mark.parametrize("fmt", sorted(EXPECTED))
@pytest.mark.parametrize("source", ["clip.mp4", "clip.mov", "clip.mkv"])
def test_each_format_has_its_container_and_codecs(ctx, source_dir, fmt, source):
    suffix, container, video_codec, audio_codec, needed = EXPECTED[fmt]
    need_encoders("libx264", *needed)
    path = make_video(source_dir / source)

    result = convert(ctx, path, format=fmt)

    assert result.kind == "video" and result.path.suffix == suffix
    assert suffix in upload_formats()["video"]
    info = probe(result.path)
    assert info["format"]["format_name"] == container
    video = streams_of(result.path, "video")
    assert [s["codec_name"] for s in video] == [video_codec]
    assert video[0]["pix_fmt"] == "yuv420p"
    assert (video[0]["width"], video[0]["height"]) == (64, 48)
    assert [s["codec_name"] for s in streams_of(result.path, "audio")] == [audio_codec]


def test_mp4_and_mov_put_the_index_first_for_streaming(ctx, source_dir):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "clip.mkv")

    for fmt in ("mp4", "mov"):
        data = convert(ctx, path, format=fmt).path.read_bytes()
        assert data.find(b"moov") < data.find(b"mdat")


@pytest.mark.parametrize("fmt", sorted(EXPECTED))
def test_small_is_lighter_than_balanced_and_balanced_than_high(ctx, source_dir, fmt):
    need_encoders("libx264", *EXPECTED[fmt][4])
    path = make_video(source_dir / "busy.mp4", seconds=1.0, size=(160, 120), fps=15, source="testsrc2", extra=("-vf", "noise=alls=30:allf=t"))

    sizes = [convert(ctx, path, format=fmt, quality=level).path.stat().st_size for level in ("high", "balanced", "small")]

    assert sizes[0] > sizes[1] > sizes[2]


@pytest.mark.parametrize("size,limit,expected", [((160, 90), 64, (64, 36)), ((90, 160), 64, (36, 64)), ((64, 48), 640, (64, 48))])
def test_the_largest_side_shrinks_to_even_sizes_and_never_enlarges(ctx, source_dir, size, limit, expected):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "wide.mp4", size=size)
    params = {"format": "mp4", "quality": "small", "max_side": limit, "keep_metadata": True}

    result = ConvertVideo().run([ctx.probe(path, "video")], params, ctx)[0]

    video = streams_of(result.path, "video")[0]
    assert (video["width"], video["height"]) == expected


def test_a_listed_size_shrinks_a_large_video(ctx, source_dir):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "big.mp4", size=(1400, 700), seconds=0.2)

    result = convert(ctx, path, format="mp4", max_side=640, quality="small")

    assert (result.width, result.height) == (640, 320)


def test_odd_sizes_become_even(ctx, source_dir):
    need_encoders("libx264", "libvpx-vp9")
    path = source_dir / "odd.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=63x47:rate=10:duration=0.5", "-c:v", "libvpx-vp9", "-pix_fmt", "yuv444p", path)

    for fmt in ("mp4", "webm"):
        video = streams_of(convert(ctx, path, format=fmt).path, "video")[0]
        assert (video["width"], video["height"]) == (62, 46)


def test_the_rotation_is_applied_to_the_picture(ctx, source_dir):
    need_encoders("libx264", "aac")
    flat = make_video(source_dir / "flat.mp4", size=(64, 48))
    turned = source_dir / "turned.mp4"
    run_ffmpeg("-display_rotation", "90", "-i", flat, "-c", "copy", turned)
    assert ctx.probe(turned, "video").width == 48

    for keep in (True, False):
        video = streams_of(convert(ctx, turned, format="mp4", keep_metadata=keep).path, "video")[0]
        assert (video["width"], video["height"]) == (48, 64)
        assert not any("rotation" in side for side in video.get("side_data_list", []))


@pytest.mark.parametrize("fmt,subtitle", [("mp4", "mov_text"), ("mov", "mov_text"), ("webm", "webvtt")])
def test_kept_metadata_carries_tags_every_sound_track_and_text_subtitles(ctx, source_dir, fmt, subtitle):
    need_encoders("libx264", *EXPECTED[fmt][4])
    path = rich_source(source_dir)

    result = convert(ctx, path, format=fmt, keep_metadata=True)

    info = probe(result.path)
    assert (info["format"].get("tags") or {}).get("title") == "Holiday"
    audio = streams_of(result.path, "audio")
    assert len(audio) == 2
    assert (audio[1].get("tags") or {}).get("language") == "fra"
    assert [s["codec_name"] for s in streams_of(result.path, "subtitle")] == [subtitle]


@pytest.mark.parametrize("fmt", sorted(EXPECTED))
def test_metadata_off_keeps_the_picture_and_the_first_sound_track_only(ctx, source_dir, fmt):
    need_encoders("libx264", *EXPECTED[fmt][4])
    path = rich_source(source_dir)

    result = convert(ctx, path, format=fmt, keep_metadata=False)

    info = probe(result.path)
    assert "title" not in (info["format"].get("tags") or {})
    assert len(streams_of(result.path, "audio")) == 1
    assert streams_of(result.path, "subtitle") == []


def test_chapters_follow_the_metadata_switch(ctx, source_dir):
    need_encoders("libx264", "aac")
    chapters = source_dir / "chapters.txt"
    chapters.write_text(";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle=Intro\n", encoding="utf-8")
    plain = make_video(source_dir / "plain.mp4")
    path = source_dir / "chaptered.mp4"
    run_ffmpeg("-i", plain, "-i", chapters, "-map", "0", "-map_chapters", "1", "-c", "copy", path)

    assert [c["tags"]["title"] for c in probe(convert(ctx, path, keep_metadata=True).path)["chapters"]] == ["Intro"]
    assert probe(convert(ctx, path, keep_metadata=False).path)["chapters"] == []


def test_a_silent_video_stays_silent(ctx, source_dir):
    need_encoders("libx264", "libvpx-vp9")
    path = make_video(source_dir / "silent.mp4", audio=False)

    for fmt in ("mp4", "webm"):
        result = convert(ctx, path, format=fmt)
        assert streams_of(result.path, "audio") == []
        assert result.has_audio is False


def test_a_surround_sound_track_is_mixed_down_for_webm(ctx, source_dir):
    need_encoders("libx264", "libvpx-vp9", "libopus")
    path = make_video(source_dir / "surround.mp4", extra=("-af", "aformat=channel_layouts=5.1(side)"))

    audio = streams_of(convert(ctx, path, format="webm").path, "audio")

    assert audio[0]["channels"] == 2


def test_the_command_reads_local_files_only_and_bounds_its_threads(ctx, source_dir, server_settings):
    need_encoders("libx264", "aac")
    server_settings["ffmpeg_threads"] = 3
    path = make_video(source_dir / "clip.mp4")

    convert(ctx, path, format="mov")

    command = ctx.commands[-1]
    position = command.index("-i")
    assert command[position + 1] == str(path.resolve())
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert command.index("-protocol_whitelist") < position
    assert "hls" not in command[command.index("-format_whitelist") + 1].split(",")
    assert command.count("-threads") == 2 and command[command.index("-threads") + 1] == "3"
    assert command[command.index("-preset") + 1] == "medium"
    assert not any("nvenc" in part or "qsv" in part or "vaapi" in part for part in command)


def test_the_thread_count_stays_inside_its_bounds(ctx, source_dir, server_settings):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "clip.mp4")

    server_settings["ffmpeg_threads"] = 64
    convert(ctx, path)
    server_settings["ffmpeg_threads"] = 0
    convert(ctx, path)

    assert [command[command.index("-threads") + 1] for command in ctx.commands] == ["16", "1"]


def test_a_video_longer_than_the_setting_is_refused_before_encoding(ctx, source_dir, server_settings):
    need_encoders("libx264", "aac")
    server_settings["max_minutes"] = 1
    path = make_video(source_dir / "clip.mp4")
    media = ctx.probe(path, "video").with_changes(duration=61.0)

    with pytest.raises(ToolFailed, match="lasts 2 minutes; Media Converter takes files of up to 1 minute on this server"):
        ConvertVideo().run([media], params_for(TOOL), ctx)

    assert ctx.commands == []


def encoders_writing(marker):
    found = []
    for process in psutil.process_iter(["cmdline"]):
        try:
            if any(marker in part for part in (process.info["cmdline"] or [])):
                found.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def test_cancelling_stops_the_encoder_and_leaves_no_result(tmp_path, source_dir):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "long.mp4", seconds=40.0, size=(640, 360), fps=25, source="testsrc2")
    started = threading.Event()
    stop = threading.Event()
    scratch = tmp_path / "scratch"

    def progress(fraction, label):
        if fraction > 0:
            started.set()

    context = ToolContext(scratch, progress=progress, is_cancelled=stop.is_set)
    media = context.probe(path, "video")
    outcome = {}

    def work():
        try:
            ConvertVideo().run([media], params_for(TOOL, quality="high"), context)
            outcome["result"] = "finished"
        except ToolCancelled:
            outcome["result"] = "cancelled"

    worker = threading.Thread(target=work)
    worker.start()
    assert started.wait(60)
    seen = []
    for _ in range(100):
        seen = encoders_writing(tmp_path.name)
        if seen or not worker.is_alive():
            break
        threading.Event().wait(0.02)
    assert seen
    stop.set()
    worker.join(30)

    assert outcome["result"] == "cancelled"
    assert not encoders_writing(tmp_path.name)


@pytest.mark.parametrize("fmt", ["mp4", "webm"])
def test_each_quality_step_changes_the_picture_alone(ctx, source_dir, fmt):
    need_target(fmt)
    path = make_video(
        source_dir / "busy.mkv", seconds=1.0, size=(160, 120), fps=15, audio=False, source="testsrc2",
        extra=("-vf", "noise=alls=30:allf=t"),
    )

    sizes = [stream_bytes(convert(ctx, path, format=fmt, quality=level).path, "v:0") for level in ("high", "balanced", "small")]

    assert sizes[0] > sizes[1] > sizes[2]


@pytest.mark.parametrize("fmt", ["mp4", "webm"])
def test_each_quality_step_changes_the_sound_of_a_video_alone(ctx, source_dir, fmt):
    need_target(fmt)
    path = source_dir / "noisy.mkv"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=3", "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:r=48000",
        "-ac", "2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "flac", path,
    )

    sizes = [stream_bytes(convert(ctx, path, format=fmt, quality=level).path, "a:0") for level in ("high", "balanced", "small")]

    assert sizes[0] > sizes[1] > sizes[2]


@pytest.mark.parametrize("fmt", ["mp4", "webm"])
@pytest.mark.parametrize("pix_fmt", ["yuv444p", "yuv422p", "yuv420p10le"])
def test_every_picture_format_comes_out_in_eight_bit_four_two_zero(ctx, source_dir, fmt, pix_fmt):
    path = source_dir / "deep.mkv"
    run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=0.5", "-pix_fmt", pix_fmt, "-c:v", "ffv1", path)

    video = streams_of(convert(ctx, path, format=fmt).path, "video")[0]

    assert video["pix_fmt"] == "yuv420p"
    if fmt == "mp4":
        assert video["profile"] == "High"


def test_a_video_larger_than_four_k_is_refused_before_anything_runs(ctx, source_dir):
    path = make_video(source_dir / "clip.mp4")
    media = ctx.probe(path, "video").with_changes(width=4097, height=2304)

    with pytest.raises(ToolFailed, match=r"This video is 4097 × 2304 pixels; Media Converter takes videos of up to 4096 × 2304"):
        ConvertVideo().run([media], params_for(TOOL), ctx)

    assert ctx.commands == []


def test_a_video_of_exactly_four_k_area_is_converted(ctx, source_dir):
    need_target("mp4")
    path = make_video(source_dir / "clip.mp4")
    media = ctx.probe(path, "video").with_changes(width=4096, height=2304)

    result = ConvertVideo().run([media], params_for(TOOL, max_side=640), ctx)[0]

    assert result.path.is_file()


@pytest.mark.parametrize("size,limit", [((64, 1), 0), ((2000, 3), 640)])
def test_a_video_thinner_than_two_pixels_is_refused(ctx, source_dir, size, limit):
    path = source_dir / "thin.mkv"
    run_ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size[0]}x{size[1]}:rate=10:duration=0.3", "-c:v", "ffv1", path)

    with pytest.raises(ToolFailed, match="at least 2 pixels on each side"):
        convert(ctx, path, format="mp4", max_side=limit)

    assert ctx.commands == []


def test_a_video_that_does_not_declare_its_length_is_stopped_at_the_limit(ctx, source_dir, server_settings):
    need_target("mp4")
    server_settings["max_minutes"] = 1
    path = piped(
        source_dir / "long.mkv", "-f", "lavfi", "-i", "color=c=black:s=32x32:r=5:d=75",
        "-c:v", "libx264", "-preset", "ultrafast", "-f", "matroska",
    )
    media = ctx.probe(path, "video")
    assert media.duration is None

    with pytest.raises(ToolFailed, match="lasts more than 1 minute; Media Converter takes files of up to 1 minute"):
        ConvertVideo().run([media], params_for(TOOL, format="mp4"), ctx)

    [written] = ctx.scratch_dir.iterdir()
    assert float(probe(written)["format"]["duration"]) <= 61.5


@pytest.mark.parametrize("fmt", ["mp4", "mov"])
def test_a_result_heavier_than_the_cap_is_refused_and_writing_stops_at_the_cap(tmp_path, source_dir, monkeypatch, fmt):
    need_target(fmt)
    path = make_video(
        source_dir / "busy.mp4", seconds=4.0, size=(640, 360), fps=25, audio=False, source="testsrc2",
        extra=("-vf", "noise=alls=30:allf=t", "-crf", "26"),
    )
    whole = convert(ToolContext(tmp_path / "whole"), path, format=fmt, quality="high").path.stat().st_size
    monkeypatch.setattr(common, "OUTPUT_FLOOR", 1 << 20)
    monkeypatch.setattr(common, "OUTPUT_RATIO", 0)
    cap = common.output_cap(path)
    assert cap == 1 << 20 and whole > 3 * cap
    ctx = ToolContext(tmp_path / "scratch")

    with pytest.raises(ToolFailed, match="would weigh more than 1 MB, the most Media Converter writes for this file"):
        convert(ctx, path, format=fmt, quality="high")

    [written] = ctx.scratch_dir.iterdir()
    assert cap <= written.stat().st_size < 2 * cap

def test_a_cancel_that_arrives_as_the_encoder_ends_publishes_nothing(tmp_path, source_dir):
    need_target("mp4")
    path = make_video(source_dir / "clip.mp4")
    stop = {"now": False}
    context = ToolContext(tmp_path / "scratch", is_cancelled=lambda: stop["now"])
    encode = context.ffmpeg

    def ffmpeg(args, duration=None):
        encode(args, duration=duration)
        stop["now"] = True

    context.ffmpeg = ffmpeg

    with pytest.raises(ToolCancelled):
        ConvertVideo().run([context.probe(path, "video")], params_for(TOOL), context)
