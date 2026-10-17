import asyncio
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import core_bridge, takes
from backend.exports import jobs, video
from backend.exports.video import ExportError, build_command, filter_graph, frame_size, timeline

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mp4", "graph": "/tmp/out/graph.txt"}


def _options(fmt="web", resolution="720p", audio=None, stills=(), **probed):
    return {"format": fmt, "resolution": resolution, "audio": audio or {}, "stills": list(stills), **probed}


def _graph(doc, files, sounds=None, **options):
    return filter_graph(doc, files, _options(**options), {**PATHS, "audio": sounds or {}}).split(";")


def _inputs(command):
    return [command[index + 1] for index, item in enumerate(command) if item == "-i"]


def _doc(make_doc, clips, audio=(), lanes=None, **fields):
    doc = make_doc(clips=clips)
    doc["audio"] = [
        {"id": f"u{index}", "assetId": None, "lane": "A1", "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **item}
        for index, item in enumerate(audio)
    ]
    for lane_id, changes in (lanes or {}).items():
        doc["lanes"] = [{**lane, **changes} if lane["id"] == lane_id else lane for lane in doc["lanes"]]
    doc.update(fields)
    return doc


def _command(doc, files, sounds=None, **options):
    return build_command(doc, files, _options(**options), {**PATHS, "audio": sounds or {}})


@pytest.mark.parametrize(
    "aspect, fmt, resolution, size",
    [
        ("16:9", "web", "720p", (1280, 720)),
        ("16:9", "web", "1080p", (1920, 1080)),
        ("16:9", "web", "4K", (3840, 2160)),
        ("9:16", "web", "1080p", (1080, 1920)),
        ("1:1", "web", "720p", (720, 720)),
        ("2.39:1", "web", "1080p", (2580, 1080)),
        ("16:9", "social", "720p", (720, 1280)),
        ("16:9", "social", "1080p", (1080, 1920)),
        ("16:9", "social", "4K", (2160, 3840)),
    ],
)
def test_the_frame_follows_the_resolution_and_the_aspect(make_doc, aspect, fmt, resolution, size):
    assert frame_size(make_doc(aspect=aspect), fmt, resolution) == size


@pytest.mark.parametrize("aspect, size", [("4:1", (4320, 1080)), ("1:4", (1080, 4320)), ("4.01:1", (1920, 1080)), ("1:4.01", (1920, 1080)), ("1e400:1", (1920, 1080))])
def test_an_aspect_past_one_to_four_falls_back_to_16_9(make_doc, aspect, size):
    assert frame_size(make_doc(aspect=aspect), "web", "1080p") == size


def test_the_name_of_an_exported_video_cuts_its_slug_to_80_characters():
    assert video.file_name("Aube sur le port", "4K") == "Aube_sur_le_port_4K.mp4"
    assert video.file_name("x" * 300, "1080p") == f"{'x' * 80}_1080p.mp4"
    assert video.file_name("a" * 79 + " b", "720p") == f"{'a' * 79}_720p.mp4"


def test_the_resolution_defaults_to_the_projects_then_to_1080p(make_doc):
    doc = make_doc()

    assert (video.resolution_of(doc, "4K"), video.resolution_of(doc)) == ("4K", "1080p")
    assert video.resolution_of({**doc, "resolution": "720p"}) == "720p"
    assert video.resolution_of({**doc, "resolution": "1440p"}) == "1080p"


def test_the_timeline_fills_the_holes_between_shots_and_up_to_the_end_with_black(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2}, {"id": "c2", "start": 3, "dur": 1}], audio=[{"start": 3, "dur": 2.5}])

    segments, total = timeline(doc)

    assert [(round(dur, 6), clip and clip["id"]) for dur, clip in segments] == [(2, "c1"), (1, None), (1, "c2"), (1.5, None)]
    assert total == 5.5


def test_a_shot_with_a_file_is_trimmed_fitted_graded_and_faded(make_doc):
    doc = _doc(
        make_doc,
        [{"id": "c1", "start": 0, "dur": 2.5, "srcIn": 0.5, "fadeIn": 0.4, "fadeOut": 0.6, "contrast": 120, "saturation": 80, "exposure": 0.4, "temperature": 25}],
        fps=24,
    )

    files = {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}}

    command, graph = _command(doc, files, audio={"c1": True}), _graph(doc, files, audio={"c1": True})

    assert _inputs(command) == ["/media/1.mp4"]
    assert graph[0] == (
        "[0:v]trim=start=0.5:duration=2.5,setpts=PTS-STARTPTS,fps=24,"
        "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=2.5,trim=duration=2.5,"
        "eq=contrast=1.2:saturation=0.8:brightness=0.05,colortemperature=temperature=6000:pl=1,"
        "fade=t=in:st=0:d=0.4,fade=t=out:st=1.9:d=0.6[v0]"
    )
    assert graph[1] == (
        "[0:a]atrim=start=0.5:duration=2.5,asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,apad=whole_dur=2.5,atrim=duration=2.5[a0]"
    )
    assert graph[2] == "[v0][a0]concat=n=1:v=1:a=1[vout][bed]"
    assert graph[3] == "[bed]anull[aout]"


def test_a_neutral_shot_has_no_look_and_no_fade(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2}])

    first = _graph(doc, {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}})[0]

    assert "eq=" not in first and "colortemperature" not in first and "fade=" not in first


def test_a_fade_shorter_than_a_hundredth_of_a_second_is_no_fade(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2, "fadeIn": 0.0099, "fadeOut": 0.01}], audio=[{"id": "voice", "fadeIn": 4e-7, "fadeOut": 0.01}])

    graph = _graph(doc, {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}}, sounds={"voice": "/media/voice.wav"})

    assert "fade=t=in" not in graph[0] and graph[0].endswith(",fade=t=out:st=1.99:d=0.01[v0]")
    assert "afade=t=in" not in graph[3] and "afade=t=out:st=0.99:d=0.01" in graph[3]


def test_social_crops_the_middle_of_the_picture_to_9_16(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 1}])

    first = _graph(doc, {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}}, fmt="social", resolution="1080p")[0]

    assert "scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2,crop=1080:1920" in first


def test_a_shot_without_file_is_black_and_silent_for_its_duration(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2}, {"id": "c2", "start": 2, "dur": 1.5}])

    files = {"c1": None, "c2": {"name": "2.mp4", "path": "/media/2.mp4"}}

    command, graph = _command(doc, files), _graph(doc, files)

    assert graph[0] == "color=c=black:s=1280x720:r=25:d=2,setsar=1,format=yuv420p[v0]"
    assert graph[1] == "anullsrc=r=48000:cl=stereo,atrim=duration=2[a0]"
    assert graph[3] == "anullsrc=r=48000:cl=stereo,atrim=duration=1.5[a1]"
    assert graph[4] == "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][bed]"
    assert _inputs(command) == ["/media/2.mp4"] and "[0:v]" in graph[2]


def test_a_still_image_is_looped_for_the_length_of_its_shot(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 3, "srcIn": 0.5}])

    command = _command(doc, {"c1": {"name": "a.png", "path": "/media/a.png"}}, stills=["c1"])

    position = command.index("/media/a.png")
    assert command[position - 7 : position] == ["-loop", "1", "-framerate", "25", "-t", "3.5", "-i"]


def test_the_audio_items_are_trimmed_delayed_set_to_gain_plus_lane_and_faded_then_mixed_without_normalising(make_doc):
    doc = _doc(
        make_doc,
        [{"id": "c1", "start": 0, "dur": 4}],
        audio=[
            {"id": "voice", "lane": "A1", "start": 1.25, "dur": 2, "srcIn": 0.5, "gain": -3, "fadeIn": 0.1, "fadeOut": 0.3},
            {"id": "music", "lane": "A2", "start": 0, "dur": 4, "srcIn": 0, "gain": -6},
        ],
        lanes={"A2": {"vol": -2}},
    )

    sounds = {"voice": "/media/voice.wav", "music": "/media/music.mp3"}

    command, graph = _command(doc, {"c1": None}, sounds=sounds), _graph(doc, {"c1": None}, sounds=sounds)

    assert _inputs(command) == ["/media/voice.wav", "/media/music.mp3"]
    assert graph[3] == (
        "[0:a]atrim=start=0.5:duration=2,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-3dB,afade=t=in:st=0:d=0.1,afade=t=out:st=1.7:d=0.3,adelay=delays=1250:all=1[m0]"
    )
    assert graph[4].endswith("volume=-8dB,adelay=delays=0:all=1[m1]")
    assert graph[5] == "[bed][m0][m1]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[aout]"


def test_a_muted_lane_is_left_out_and_a_soloed_lane_plays_alone(make_doc):
    audio = [{"id": "voice", "lane": "A1"}, {"id": "music", "lane": "A2"}, {"id": "ambience", "lane": "A3"}]
    sounds = {"voice": "/v.wav", "music": "/m.wav", "ambience": "/a.wav"}

    muted = _command(_doc(make_doc, [{"id": "c1", "dur": 1}], audio=audio, lanes={"A2": {"mute": True}}), {"c1": None}, sounds=sounds)
    soloed = _command(
        _doc(make_doc, [{"id": "c1", "dur": 1}], audio=audio, lanes={"A1": {"solo": True}, "A3": {"solo": True, "mute": True}}),
        {"c1": None},
        sounds=sounds,
    )

    assert _inputs(muted) == ["/v.wav", "/a.wav"]
    assert _inputs(soloed) == ["/v.wav"]


def test_subtitles_are_never_burnt_in_and_an_item_without_file_is_skipped(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "dur": 1}], audio=[{"id": "voice"}])
    doc["titles"] = [{"id": "t1", "text": "Hello", "sub": "", "start": 0, "dur": 1}]

    text = " ".join([*_command(doc, {"c1": None}), *_graph(doc, {"c1": None})])

    assert "subtitles" not in text and "drawtext" not in text
    assert _inputs(_command(doc, {"c1": None})) == []


def test_the_mezzanine_is_h264_crf_14_with_aac_192k_at_the_project_rate_and_length(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2.5}], fps=30)

    command = _command(doc, {"c1": None})

    assert command[:9] == ["/usr/bin/ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    assert command[command.index("-filter_complex_script") + 1] == "/tmp/out/graph.txt" and "-filter_complex" not in command
    tail = command[command.index("-map") :]
    assert tail[:4] == ["-map", "[vout]", "-map", "[aout]"]
    assert tail[4:8] == ["-t", "2.5", "-r", "30"]
    assert " ".join(tail[8:]) == (
        "-c:v libx264 -preset veryfast -crf 14 -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -ac 2 "
        "-movflags +faststart /tmp/out/mezzanine.mp4"
    )


def test_a_shot_that_starts_past_the_end_of_its_source_is_black_and_opens_no_file(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2, "srcIn": 10}, {"id": "c2", "start": 2, "dur": 1}])
    files = {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}, "c2": {"name": "2.mp4", "path": "/media/2.mp4"}}

    command, graph = _command(doc, files, lengths={"c1": 1.0}), _graph(doc, files, lengths={"c1": 1.0})

    assert _inputs(command) == ["/media/2.mp4"]
    assert graph[:2] == ["color=c=black:s=1280x720:r=25:d=2,setsar=1,format=yuv420p[v0]", "anullsrc=r=48000:cl=stereo,atrim=duration=2[a0]"]
    assert graph[2].startswith("[0:v]trim=start=0:duration=1,")


def test_without_a_probed_length_the_length_of_the_asset_tells_where_its_source_ends(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 2, "srcIn": 4}], assets=[{"id": "a1", "kind": "video", "srcDur": 4}])

    command = _command(doc, {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}})

    assert _inputs(command) == []


@pytest.mark.parametrize("src_in, length, pad", [(0, 5, "0.04"), (1, 3, "2.04"), (0.5, None, "4")])
def test_the_freeze_only_covers_what_the_source_lacks_past_its_end(make_doc, src_in, length, pad):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 4, "srcIn": src_in}])

    first = _graph(doc, {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}}, lengths={} if length is None else {"c1": length})[0]

    assert f",tpad=stop_mode=clone:stop_duration={pad},trim=duration=4" in first


def test_a_shot_without_picture_is_black_with_the_sound_of_its_file_or_silent_without_it(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2, "srcIn": 0.5}, {"id": "c2", "start": 2, "dur": 1}])
    files = {"c1": {"name": "v.wav", "path": "/media/v.wav"}, "c2": {"name": "w.wav", "path": "/media/w.wav"}}
    options = {"audio": {"c1": True, "c2": False}, "blind": ["c1", "c2"]}

    command, graph = _command(doc, files, **options), _graph(doc, files, **options)

    assert _inputs(command) == ["/media/v.wav"]
    assert graph[0] == "color=c=black:s=1280x720:r=25:d=2,setsar=1,format=yuv420p[v0]"
    assert graph[1].startswith("[0:a]atrim=start=0.5:duration=2,") and graph[1].endswith("[a0]")
    assert graph[2:4] == ["color=c=black:s=1280x720:r=25:d=1,setsar=1,format=yuv420p[v1]", "anullsrc=r=48000:cl=stereo,atrim=duration=1[a1]"]


def test_inspect_probes_each_file_once_for_its_sound_its_picture_and_its_length(monkeypatch):
    found = {"/a.mp4": SimpleNamespace(duration=5.0, has_audio=True), "/b.mp4": SimpleNamespace(duration=0.0, has_audio=False)}
    probed = []
    monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe")
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: probed.append(str(path)) or found.get(str(path)))
    shots = {
        "c1": {"path": "/a.mp4", "still": False},
        "c2": {"path": "/a.mp4", "still": False},
        "c3": {"path": "/b.mp4", "still": False},
        "c4": {"path": "/voice.wav", "still": False},
        "c5": {"path": "/s.png", "still": True},
        "c6": None,
        "c7": {"path": "/a.mp4", "still": False, "sound": True},
    }

    assert video.inspect(shots) == {
        "audio": {"c1": True, "c2": True, "c3": False, "c4": True, "c7": True},
        "blind": ["c4", "c7"],
        "lengths": {"c1": 5.0, "c2": 5.0, "c7": 5.0},
    }
    assert probed == ["/a.mp4", "/b.mp4", "/voice.wav"]


def test_without_ffprobe_only_a_sound_asset_is_taken_for_a_shot_without_picture(monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: None)
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: pytest.fail("probed without ffprobe"))

    found = video.inspect({"c1": {"path": "/a.mp4", "still": False}, "c2": {"path": "/v.wav", "still": False, "sound": True}})

    assert found == {"audio": {"c1": False, "c2": True}, "blind": ["c2"], "lengths": {}}


def test_the_last_useful_line_of_stderr_is_kept_to_300_characters():
    assert video.last_line("frame=1\n\n  Error opening input: No such file  \n\n") == "Error opening input: No such file"
    assert len(video.last_line("x" * 400)) == 300 and video.last_line("") == ""


def test_numbers_for_ffmpeg_have_no_trailing_zeros():
    assert [video.num(value) for value in (2, 2.5, 0.1 + 0.2, -0.0, 6500 - 15 * 20, 1 / 3)] == ["2", "2.5", "0.3", "0", "6200", "0.333333"]


def _make_clip(folder: Path, name: str, size: str, tone: bool) -> Path:
    path = folder / name
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:duration=1"]
    if tone:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac", "-shortest"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True, timeout=60)
    return path


def _sine(folder: Path) -> Path:
    path = folder / "voice.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=1", str(path)],
        check=True,
        timeout=60,
    )
    return path


@pytest.fixture
def clips(tmp_path):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg and ffprobe are not on the PATH")
    return _make_clip(tmp_path, "a.mp4", "320x240", True), _make_clip(tmp_path, "b.mp4", "640x360", False), _sine(tmp_path)


def _real_doc(make_doc):
    return _doc(
        make_doc,
        [
            {"id": "c1", "assetId": "a1", "start": 0, "dur": 1, "fadeIn": 0.2, "contrast": 120},
            {"id": "c2", "assetId": "a2", "start": 1, "dur": 1, "temperature": 10, "fadeOut": 0.3},
        ],
        audio=[{"id": "voice", "lane": "A1", "start": 0.5, "dur": 0.5, "gain": -6, "fadeOut": 0.1}],
        resolution="720p",
    )


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_two_one_second_clips_assemble_into_a_two_second_720p_mezzanine_with_sound(make_doc, clips, tmp_path):
    first, second, voice = clips
    doc = _real_doc(make_doc)
    output = tmp_path / "mezzanine.mp4"
    files = {"c1": {"name": first.name, "path": str(first)}, "c2": {"name": second.name, "path": str(second)}}
    options = {"format": "web", "resolution": "720p", **video.inspect(files)}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {"voice": str(voice)}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")
    command = build_command(doc, files, options, paths)
    shares = []

    await video.assemble(command, 2.0, shares.append)

    probe = core_bridge.probe_video(output)
    assert (probe.width, probe.height, round(probe.fps), probe.has_audio, probe.video_codec) == (1280, 720, 25, True, "h264")
    assert abs(probe.duration - 2.0) < 0.1
    assert shares and shares[-1] == pytest.approx(1.0, abs=0.05)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_render_assembles_transcodes_and_stores_a_social_export(make_doc, clips, monkeypatch, export_storage, make_user):
    first, second, voice = clips
    doc = _real_doc(make_doc)
    shots = {
        "c1": {"name": first.name, "path": str(first), "still": False},
        "c2": {"name": second.name, "path": str(second), "still": False},
    }
    monkeypatch.setattr(video.media, "local_inputs", lambda doc, found, resolver, folder: (shots, {"voice": str(voice)}))
    monkeypatch.setattr(takes, "list_takes", lambda project_id: [])
    stored = []

    async def save_user_media(user, path):
        stored.append((user.id, Path(path).name, Path(path).stat().st_size))
        return {"value": "uploads/0f0e.mp4", "media_type": "video", "original_filename": Path(path).name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save_user_media)
    monkeypatch.setattr(core_bridge, "upload_item", lambda user_id, value: {"item_id": "item-1", "filename": "x", "width": 720, "height": 1280})
    steps = []
    job = {"id": "job-1", "user_id": "user-1", "format": "social", "resolution": "720p"}
    project = {"id": "p-1", "name": "Aube sur le port", "doc": doc}
    user = make_user()

    result = await video.render(job, project, user, user, lambda progress, step: steps.append((progress, step)) or True)

    final = export_storage / "video_producer" / "exports" / "user-1" / "job-1" / "Aube_sur_le_port_720p.mp4"
    probe = core_bridge.probe_video(final)
    assert (probe.width, probe.height, probe.has_audio, probe.video_codec) == (720, 1280, True, "h264")
    assert abs(probe.duration - 2.0) < 0.15
    assert result == {
        "file_name": "Aube_sur_le_port_720p.mp4",
        "file_size": final.stat().st_size,
        "media_item_id": "item-1",
        "media_url": "/api/media/uploads/0f0e.mp4",
    }
    assert stored == [("user-1", "Aube_sur_le_port_720p.mp4", final.stat().st_size)]
    assert not (final.parent / video.MEZZANINE).exists() and not (final.parent / video.GRAPH).exists()
    assert steps[0] == (0, "assemble") and steps[-2:] == [(70, "transcode"), (95, "store")]
    assert all(step == ("mix" if progress >= 50 else "assemble") for progress, step in steps[:-2])


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_killing_the_assembly_stops_ffmpeg_and_fails_the_run(tmp_path):
    command = [
        shutil.which("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-f", "lavfi", "-re", "-i", "testsrc2=size=640x360:rate=25:duration=60", "-c:v", "libx264", str(tmp_path / "long.mp4"),
    ]
    processes = []

    def on_progress(share):
        if processes and processes[-1] is not None and processes[-1].returncode is None:
            processes[-1].kill()

    with pytest.raises(ExportError) as caught:
        await asyncio.wait_for(video.assemble(command, 60.0, on_progress, processes.append), timeout=30)

    assert caught.value.code == "ffmpeg_failed"
    assert processes[-1] is None and processes[0].returncode is not None


async def test_a_missing_ffmpeg_fails_the_assembly_with_its_reason(tmp_path):
    with pytest.raises(ExportError) as caught:
        await video.assemble([str(tmp_path / "no-ffmpeg"), "-version"], 1.0)

    assert caught.value.code == "ffmpeg_failed" and caught.value.message


@pytest.fixture
def stored_jobs(core, export_storage):
    return core


def _job(project_id="p-1", user_id="user-1", fmt="web", resolution="1080p"):
    return jobs.create_job(project_id, user_id, fmt, resolution)


def test_a_new_job_is_queued_with_the_contract_shape(stored_jobs):
    job = _job()

    public = jobs.public(job)
    assert set(public) == {"id", "project_id", "format", "resolution", "status", "progress", "step", "file", "media", "error", "created_at", "finished_at"}
    assert (public["status"], public["progress"], public["step"], public["file"], public["media"], public["error"]) == ("queued", 0, None, None, None, None)


def test_one_project_has_one_export_in_flight(stored_jobs):
    first = _job()

    assert _job() is None
    assert _job(project_id="p-2") is not None
    jobs.settle(first["id"], "failed", error_code="ffmpeg_failed", error_message="x")
    assert _job() is not None


def test_jobs_are_claimed_oldest_first_and_settle_only_once(stored_jobs):
    first, second = _job(project_id="p-1"), _job(project_id="p-2")

    claimed = jobs.claim_next()

    assert claimed["id"] == first["id"] and (claimed["status"], claimed["step"]) == ("running", "assemble")
    assert jobs.update_running(first["id"], progress=42.0, step="mix") is True
    assert jobs.update_running(second["id"], progress=1.0) is False
    assert jobs.settle(first["id"], "done", progress=100.0, step=None, file_name="a.mp4", file_size=10, media_item_id="i", media_url="/api/media/uploads/a.mp4")
    assert jobs.settle(first["id"], "failed") is False
    done = jobs.public(jobs.get_job(first["id"]))
    assert done["status"] == "done" and done["finished_at"]
    assert done["file"] == {"name": "a.mp4", "size": 10, "url": f"/api/plugins/video-producer/exports/{first['id']}/file"}
    assert done["media"] == {"kind": "library", "item_id": "i", "url": "/api/media/uploads/a.mp4"}
    assert jobs.claim_next()["id"] == second["id"] and jobs.claim_next() is None


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.killed = 0

    def kill(self):
        self.killed += 1
        self.returncode = -9


def test_cancelling_a_running_job_kills_its_ffmpeg_process(stored_jobs):
    job = _job()
    jobs.claim_next()
    process = FakeProcess()
    jobs._PROCESSES[job["id"]] = process

    cancelled = jobs.cancel(jobs.get_job(job["id"]))

    assert process.killed == 1
    assert cancelled["status"] == "cancelled"
    assert jobs.public(cancelled)["error"] == {"code": "cancelled", "message": "The export was cancelled."}
    assert jobs.cancel(cancelled)["status"] == "cancelled" and process.killed == 1


def _fill(folder: Path, megabytes: float):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "export.mp4").write_bytes(b"\0" * int(megabytes * 1024 * 1024))


def test_room_is_made_by_deleting_the_oldest_finished_exports_first(stored_jobs):
    old, newer, running = _job(project_id="p-1"), _job(project_id="p-2"), _job(project_id="p-3")
    for job in (old, newer):
        jobs.settle(job["id"], "done", file_name="export.mp4", file_size=1)
    for job, size in ((old, 1.5), (newer, 1.5), (running, 0.5)):
        _fill(video.job_folder(job), size)

    assert jobs.make_room("user-1", 3 * 1024 * 1024) is True

    assert jobs.get_job(old["id"]) is None and not video.job_folder(old).exists()
    assert jobs.get_job(newer["id"]) is not None and jobs.get_job(running["id"]) is not None
    assert jobs.make_room("user-1", 400 * 1024) is False
    assert jobs.get_job(newer["id"]) is None and jobs.get_job(running["id"])["status"] == "queued"


def test_the_quota_counts_only_the_users_own_cache(stored_jobs):
    other = _job(user_id="user-2")
    _fill(video.job_folder(other), 2)

    assert jobs.usage("user-1") == 0 and jobs.make_room("user-1", 1024 * 1024) is True


async def test_a_job_that_renders_is_done_with_its_file_and_its_owner_is_told(stored_jobs, make_project, monkeypatch):
    project = make_project()
    job = jobs.create_job(project["id"], "user-1", "web", "720p")
    claimed = jobs.claim_next()
    seen = []

    async def render(job, project, owner, requester, report, on_process=None):
        seen.append((owner.id, requester.id, report(30, "assemble"), report(60, "mix")))
        assert jobs.get_job(job["id"])["progress"] == 60
        return {"file_name": "x_720p.mp4", "file_size": 7, "media_item_id": "item-9", "media_url": "/api/media/uploads/z.mp4"}

    monkeypatch.setattr(video, "render", render)

    await jobs.execute(claimed)

    done = jobs.public(jobs.get_job(job["id"]))
    assert (done["status"], done["progress"], done["step"]) == ("done", 100, None)
    assert done["media"]["item_id"] == "item-9" and done["file"]["size"] == 7
    assert seen == [("user-1", "user-1", True, True)]
    assert [(note["notification_type"], note["level"], note["metadata"]["job_id"]) for note in stored_jobs.notified] == [
        ("video-producer.export_done", "success", job["id"])
    ]


@pytest.mark.parametrize("code", ["ffmpeg_failed", "transcode_failed", "store_failed"])
async def test_a_job_that_fails_keeps_its_code_and_last_line_and_its_owner_is_told(stored_jobs, make_project, monkeypatch, code):
    project = make_project()
    job = jobs.create_job(project["id"], "user-1", "social", "1080p")
    _fill(video.job_folder(job), 0.1)

    async def render(*args, **kwargs):
        raise ExportError(code, "Invalid data found when processing input")

    monkeypatch.setattr(video, "render", render)

    await jobs.execute(jobs.claim_next())

    failed = jobs.public(jobs.get_job(job["id"]))
    assert failed["status"] == "failed"
    assert failed["error"] == {"code": code, "message": "Invalid data found when processing input"}
    assert not video.job_folder(job).exists()
    assert [note["notification_type"] for note in stored_jobs.notified] == ["video-producer.export_failed"]


async def test_a_job_cancelled_while_it_renders_stays_cancelled_and_nobody_is_told(stored_jobs, make_project, monkeypatch):
    project = make_project()
    job = jobs.create_job(project["id"], "user-1", "web", "720p")

    async def render(job, project, owner, requester, report, on_process=None):
        process = FakeProcess()
        on_process(process)
        jobs.cancel(jobs.get_job(job["id"]))
        assert process.killed == 1
        on_process(None)
        raise ExportError("ffmpeg_failed", "Exiting normally, received signal 9.")

    monkeypatch.setattr(video, "render", render)

    await jobs.execute(jobs.claim_next())

    assert jobs.get_job(job["id"])["status"] == "cancelled"
    assert stored_jobs.notified == [] and jobs._PROCESSES == {}


async def test_the_runner_works_through_the_queue_one_job_at_a_time(stored_jobs, make_project, monkeypatch):
    first, second = make_project(), make_project()
    ids = [jobs.create_job(project["id"], "user-1", "web", "720p")["id"] for project in (first, second)]
    running = []

    async def render(job, project, owner, requester, report, on_process=None):
        running.append(sum(1 for item in jobs.list_active() if item["status"] == "running"))
        return {"file_name": "x.mp4", "file_size": 1, "media_item_id": None, "media_url": None}

    monkeypatch.setattr(video, "render", render)

    assert jobs.RUNNER.start() is True
    assert jobs.RUNNER.start() is False
    await stored_jobs.scheduled[0]

    assert running == [1, 1]
    assert [jobs.get_job(job_id)["status"] for job_id in ids] == ["done", "done"]
    assert jobs.RUNNER.active is False and jobs.RUNNER.start() is True


def test_at_startup_jobs_left_running_fail_and_the_queue_resumes(stored_jobs, make_project):
    left = jobs.create_job(make_project()["id"], "user-1", "web", "720p")
    jobs.claim_next()
    waiting = jobs.create_job(make_project()["id"], "user-1", "web", "720p")

    assert jobs.recover() == 1

    stopped = jobs.get_job(left["id"])
    assert (stopped["status"], stopped["error_code"]) == ("failed", "ffmpeg_failed")
    assert jobs.get_job(waiting["id"])["status"] == "queued"
    assert [coroutine.__qualname__ for coroutine in stored_jobs.scheduled] == ["Runner.run"]
