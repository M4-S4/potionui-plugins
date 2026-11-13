import pytest

from src.plugin_api.media import upload_formats
from src.plugin_api.media_tools import ToolFailed

from tools.audio import ConvertAudio

from .conftest import make_audio, need_encoders, params_for, probe, run_ffmpeg, streams_of

TOOL = "media-convert.audio"
EXPECTED = {
    "wav": (".wav", "wav", "pcm_s16le", "pcm_s16le"),
    "mp3": (".mp3", "mp3", "mp3", "libmp3lame"),
    "flac": (".flac", "flac", "flac", "flac"),
    "m4a": (".m4a", "mov,mp4,m4a,3gp,3g2,mj2", "aac", "aac"),
    "ogg": (".ogg", "ogg", "opus", "libopus"),
}
SOURCES = {
    "tone.wav": ("-c:a", "pcm_s16le"),
    "tone.mp3": ("-c:a", "libmp3lame"),
    "tone.flac": ("-c:a", "flac"),
    "tone.m4a": ("-c:a", "aac"),
    "tone.ogg": ("-c:a", "libvorbis"),
    "tone.aac": ("-c:a", "aac"),
}
TAGS = ("-metadata", "title=Song", "-metadata", "artist=Someone")


def convert(ctx, path, **given):
    return ConvertAudio().run([ctx.probe(path, "audio")], params_for(TOOL, **given), ctx)[0]


def tags(path):
    info = probe(path)
    found = dict(info["format"].get("tags") or {})
    for stream in info["streams"]:
        found.update(stream.get("tags") or {})
    return {key.lower(): value for key, value in found.items()}


def cases(sources):
    return [
        (fmt, source)
        for fmt in sorted(EXPECTED)
        for source in sources
        if not (fmt in ("wav", "flac") and source.endswith(EXPECTED[fmt][0]))
    ]


@pytest.mark.parametrize("fmt,source", cases(sorted(SOURCES)))
def test_each_format_has_its_container_and_codec(ctx, source_dir, fmt, source):
    suffix, container, codec, encoder = EXPECTED[fmt]
    need_encoders(encoder, SOURCES[source][1])
    path = make_audio(source_dir / source, codec_args=SOURCES[source])

    result = convert(ctx, path, format=fmt)

    assert result.kind == "audio" and result.path.suffix == suffix
    assert suffix in upload_formats()["audio"]
    assert probe(result.path)["format"]["format_name"] == container
    assert [s["codec_name"] for s in streams_of(result.path, "audio")] == [codec]
    assert streams_of(result.path, "video") == []


@pytest.mark.parametrize("fmt", ["mp3", "m4a", "ogg"])
def test_small_is_lighter_than_balanced_and_balanced_than_high(ctx, source_dir, fmt):
    need_encoders(EXPECTED[fmt][3])
    path = source_dir / "noise.wav"
    run_ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:r=44100", "-ac", "2", path)

    sizes = [convert(ctx, path, format=fmt, quality=level).path.stat().st_size for level in ("high", "balanced", "small")]

    assert sizes[0] > sizes[1] > sizes[2]


@pytest.mark.parametrize("bits,codec", [(16, "pcm_s16le"), (24, "pcm_s24le")])
def test_wav_keeps_the_bit_depth_of_a_deep_source(ctx, source_dir, bits, codec):
    sample = {16: "s16", 24: "s32"}[bits]
    path = make_audio(source_dir / f"deep{bits}.flac", codec_args=("-c:a", "flac", "-sample_fmt", sample, *(("-bits_per_raw_sample", "24") if bits == 24 else ())))

    result = convert(ctx, path, format="wav")

    assert streams_of(result.path, "audio")[0]["codec_name"] == codec


@pytest.mark.parametrize("fmt,source", cases(["tagged.flac", "tagged.ogg", "tagged.mp3"]))
def test_kept_metadata_carries_the_title_and_artist(ctx, source_dir, fmt, source):
    need_encoders(EXPECTED[fmt][3], "libvorbis", "libmp3lame")
    codec = {"flac": ("-c:a", "flac"), "ogg": ("-c:a", "libvorbis"), "mp3": ("-c:a", "libmp3lame")}[source.split(".")[1]]
    path = make_audio(source_dir / source, codec_args=codec, extra=TAGS)
    assert tags(path)["title"] == "Song"

    found = tags(convert(ctx, path, format=fmt, keep_metadata=True).path)

    assert found.get("title") == "Song" and found.get("artist") == "Someone"


@pytest.mark.parametrize("fmt", sorted(EXPECTED))
def test_metadata_off_drops_the_tags(ctx, source_dir, fmt):
    need_encoders(EXPECTED[fmt][3], "libmp3lame")
    path = make_audio(source_dir / "tagged.mp3", codec_args=("-c:a", "libmp3lame"), extra=TAGS)

    found = tags(convert(ctx, path, format=fmt, keep_metadata=False).path)

    assert "title" not in found and "artist" not in found


@pytest.mark.parametrize("fmt", ["wav", "flac"])
def test_a_lossless_file_is_not_converted_to_its_own_format(ctx, source_dir, fmt):
    path = make_audio(source_dir / f"tone.{fmt}", codec_args=("-c:a", "pcm_s16le" if fmt == "wav" else "flac"))

    with pytest.raises(ToolFailed, match=f"already a {fmt.upper()} file"):
        convert(ctx, path, format=fmt)


def test_a_lossy_file_can_be_compressed_again_in_its_own_format(ctx, source_dir):
    need_encoders("libmp3lame")
    path = make_audio(source_dir / "rich.mp3", seconds=3, channels=2, codec_args=("-c:a", "libmp3lame", "-q:a", "0"))

    result = convert(ctx, path, format="mp3", quality="small")

    assert result.path.stat().st_size < path.stat().st_size


@pytest.mark.parametrize("fmt,channels", [("mp3", 2), ("ogg", 2), ("m4a", 6), ("flac", 6), ("wav", 6)])
def test_surround_sound_is_mixed_down_only_where_the_format_needs_it(ctx, source_dir, fmt, channels):
    need_encoders(EXPECTED[fmt][3])
    path = make_audio(source_dir / "surround.m4a", channels=6, codec_args=("-c:a", "aac"))

    result = convert(ctx, path, format=fmt)

    assert streams_of(result.path, "audio")[0]["channels"] == channels


def test_a_sound_longer_than_the_setting_is_refused(ctx, source_dir, server_settings):
    server_settings["max_minutes"] = 2
    path = make_audio(source_dir / "tone.wav", codec_args=("-c:a", "pcm_s16le"))
    media = ctx.probe(path, "audio").with_changes(duration=600.0)

    with pytest.raises(ToolFailed, match="lasts 10 minutes"):
        ConvertAudio().run([media], params_for(TOOL), ctx)
