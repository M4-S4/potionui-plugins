import pytest

from src.plugin_api.media_tools import ToolFailed

from tools.extract_audio import ExtractAudio

from .conftest import make_video, need_encoders, params_for, probe, run_ffmpeg, streams_of

TOOL = "media-convert.extract-audio"
EXPECTED = {
    "wav": (".wav", "pcm_s16le", "pcm_s16le"),
    "mp3": (".mp3", "mp3", "libmp3lame"),
    "flac": (".flac", "flac", "flac"),
    "m4a": (".m4a", "aac", "aac"),
    "ogg": (".ogg", "opus", "libopus"),
}


def extract(ctx, path, **given):
    return ExtractAudio().run([ctx.probe(path, "video")], params_for(TOOL, **given), ctx)[0]


@pytest.mark.parametrize("fmt", sorted(EXPECTED))
@pytest.mark.parametrize("source", ["clip.mp4", "clip.mkv", "clip.webm"])
def test_the_sound_of_a_video_comes_out_alone_in_each_format(ctx, source_dir, fmt, source):
    suffix, codec, encoder = EXPECTED[fmt]
    need_encoders("libx264", "libvpx-vp9", "libopus", encoder)
    vp9 = ("-c:v", "libvpx-vp9", "-c:a", "libopus") if source.endswith(".webm") else ()
    path = make_video(source_dir / source, seconds=1.0, extra=vp9)

    result = extract(ctx, path, format=fmt)

    assert result.kind == "audio" and result.path.suffix == suffix
    assert streams_of(result.path, "video") == []
    assert [s["codec_name"] for s in streams_of(result.path, "audio")] == [codec]
    assert abs(float(probe(result.path)["format"]["duration"]) - 1.0) < 0.1


def test_a_video_without_sound_is_refused_with_a_clear_message(ctx, source_dir):
    path = make_video(source_dir / "silent.mp4", audio=False)

    with pytest.raises(ToolFailed, match="This video has no sound to extract"):
        extract(ctx, path)


@pytest.mark.parametrize("keep", [True, False])
def test_the_title_of_the_video_follows_the_metadata_switch(ctx, source_dir, keep):
    path = make_video(source_dir / "tagged.mp4", extra=("-metadata", "title=Holiday"))

    tags = probe(extract(ctx, path, format="mp3", keep_metadata=keep).path)["format"].get("tags") or {}

    assert (tags.get("title") == "Holiday") is keep


def test_only_the_first_sound_track_is_extracted(ctx, source_dir):
    need_encoders("libx264", "aac")
    path = source_dir / "two.mkv"
    run_ffmpeg(
        "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=2",
        "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path,
    )

    result = extract(ctx, path, format="wav")

    assert len(streams_of(result.path, "audio")) == 1
    assert abs(float(probe(result.path)["format"]["duration"]) - 1.0) < 0.1
