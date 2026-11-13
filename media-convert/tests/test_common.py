from pathlib import Path

import pytest

from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import common

from .conftest import make_audio


@pytest.mark.parametrize(
    "size,limit,even,expected",
    [
        ((4000, 3000), 1920, False, (1920, 1440)),
        ((3000, 4000), 1920, False, (1440, 1920)),
        ((800, 600), 1920, False, (800, 600)),
        ((801, 601), None, True, (800, 600)),
        ((1999, 1001), 1280, True, (1280, 640)),
        ((3, 1), 2, True, (2, 2)),
        ((1, 1), None, True, (2, 2)),
    ],
)
def test_fit_shrinks_to_the_largest_side_never_enlarges_and_rounds_to_even(size, limit, even, expected):
    assert common.fit(*size, limit, even) == expected


def test_the_input_is_read_from_a_local_absolute_path_only(tmp_path):
    args = common.input_args(Path("relative.mp4"))

    assert args[:2] == ["-protocol_whitelist", "file"]
    assert args[2] == "-format_whitelist" and "hls" not in args[3] and "concat" not in args[3]
    assert args[4] == "-i" and Path(args[5]).is_absolute()


def test_quality_falls_back_to_balanced_when_the_dialog_hides_it():
    assert common.quality({}) == "balanced"
    assert common.quality({"quality": "small"}) == "small"
    assert common.quality({"quality": "loud"}) == "balanced"


def test_the_quality_tables_cover_every_step():
    tables = (
        common.JPEG_QUALITY, common.WEBP_QUALITY, common.H264_CRF, common.VP9_CRF, common.VIDEO_AAC_KBPS,
        common.VIDEO_OPUS_KBPS, common.MP3_VBR, common.AAC_KBPS, common.OPUS_KBPS,
    )
    for table in tables:
        assert sorted(table) == sorted(common.QUALITIES)


def test_the_largest_side_zero_means_the_original_size():
    assert common.max_side({"max_side": 0}) is None
    assert common.max_side({}) is None
    assert common.max_side({"max_side": 1280}) == 1280


def test_the_duration_limit_comes_from_the_setting(server_settings):
    server_settings["max_minutes"] = 5
    common.check_duration(300.0)
    common.check_duration(None)
    with pytest.raises(ToolFailed, match="lasts 6 minutes"):
        common.check_duration(300.5)


def test_missing_settings_use_the_defaults(monkeypatch):
    monkeypatch.setattr(common, "plugin_settings", lambda plugin_id: {})

    assert common.threads() == common.DEFAULT_THREADS
    assert common.max_seconds() == common.DEFAULT_MAX_MINUTES * 60


def test_the_settings_are_read_under_the_plugin_id(monkeypatch):
    asked = []
    monkeypatch.setattr(common, "plugin_settings", lambda plugin_id: asked.append(plugin_id) or {"ffmpeg_threads": 2})

    assert common.threads() == 2
    assert asked == ["media-convert"]


def test_a_cancelled_run_stops_at_the_guard(tmp_path):
    with pytest.raises(ToolCancelled):
        common.guard(ToolContext(tmp_path, is_cancelled=lambda: True))
    common.guard(ToolContext(tmp_path))


def test_metadata_args_pick_the_stream_tags_of_an_ogg_source():
    track = common.Stream(index=0, kind="audio", codec="vorbis", tags={"title": "Song"})
    streams = common.Streams(streams=(track,), tags={})

    assert common.metadata_args(streams, track, True)[:2] == ["-map_metadata", "0:s:0"]
    assert common.metadata_args(common.Streams((track,), {"title": "x"}), track, True)[:2] == ["-map_metadata", "0"]
    assert common.metadata_args(streams, track, False) == ["-map_metadata", "-1", "-map_chapters", "-1"]


def test_the_length_setting_never_goes_past_the_thirty_minutes_the_core_allows(server_settings):
    server_settings["max_minutes"] = 600
    assert common.max_seconds() == 30 * 60
    server_settings["max_minutes"] = 0
    assert common.max_seconds() == 60


@pytest.mark.parametrize(
    "source_bytes,cap",
    [(1000, 1 << 30), (64 << 20, 2 << 30), (1 << 30, 4 << 30)],
)
def test_the_output_cap_grows_with_the_source_between_a_floor_and_a_ceiling(tmp_path, source_bytes, cap):
    path = tmp_path / "source.bin"
    with path.open("wb") as handle:
        handle.truncate(source_bytes)

    assert common.output_cap(path) == cap
    assert common.limit_args(path) == ["-t", "1801.000", "-fs", str(cap)]


def test_the_list_of_containers_ffmpeg_may_open_is_exactly_this_one():
    assert common.DEMUXERS.split(",") == [
        "mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi", "mp3", "wav", "flac", "ogg", "aac",
    ]


def hostile_files(folder):
    sound = make_audio(folder / "witness.wav", seconds=2, codec_args=("-c:a", "pcm_s16le"))
    playlist = folder / "list.m3u8"
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:2", "#EXTINF:2,", sound.resolve().as_posix(), "#EXT-X-ENDLIST", ""]
    playlist.write_text("\n".join(lines), encoding="utf-8")
    concat = folder / "list.ffconcat"
    concat.write_text(f"ffconcat version 1.0\nfile '{sound.name}'\n", encoding="utf-8")
    return [playlist, concat]


def test_ffprobe_refuses_a_playlist_or_a_concat_list(source_dir):
    for path in hostile_files(source_dir):
        with pytest.raises(ToolFailed, match="cannot read this file"):
            common.read_streams(path)


def test_ffmpeg_refuses_to_encode_a_playlist_or_a_concat_list(ctx, source_dir):
    for path in hostile_files(source_dir):
        out = ctx.new_path(".wav")
        with pytest.raises(ToolFailed):
            ctx.ffmpeg([*common.input_args(path), "-c:a", "pcm_s16le", str(out)])
        assert not out.exists() or out.stat().st_size == 0
