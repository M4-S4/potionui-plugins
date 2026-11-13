import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.chat import edits
from backend.dissolve import GRID, filled, frames_of, joins, placement, read_at, rounded
from backend.exports import video
from backend.exports.mix import write_impulse
from backend.exports.video import build_command, filter_graph, timeline

from .test_dissolve import CADENCES, HAS_FFMPEG, _frame, _frames, _graph, _read_graph, _samples, _solid, _tone

KINDS = {
    "thousandths": lambda pick: round(pick.uniform(0.2, 4), 3),
    "hundredths": lambda pick: round(pick.uniform(0.2, 4), 2),
    "thirds": lambda pick: pick.randint(1, 12) / 3,
    "1/12800": lambda pick: pick.randint(2560, 51200) / 12800,
    "near a second": lambda pick: round(pick.uniform(0.97, 1.07), 2),
}


def _laid(make_doc, durations, fps, **fields):
    doc = make_doc(clips=[{"id": f"c{index:03d}", "assetId": f"a{index}", "dur": dur} for index, dur in enumerate(durations)])
    doc.update(fps=fps, **fields)
    edits.relayout(doc)
    return doc


def _files(doc):
    return {clip["id"]: {"name": f"{clip['id']}.mp4", "path": f"/media/{clip['id']}.mp4"} for clip in doc["clips"]}


def _options(**fields):
    return {"format": "web", "resolution": "720p", "audio": {}, "stills": [], "impulse": "/tmp/out/reverb.wav", **fields}


def _starts(doc):
    segments, _ = timeline(doc)
    rate, at, found, black = doc["fps"], 0, {}, []
    for dur, clip in segments:
        frames = dur * rate
        assert abs(frames - round(frames)) < 1e-6, (rate, dur)
        if clip is None:
            black.append((at, at + round(frames)))
        else:
            found[clip["id"]] = (at, at + round(frames))
        at += round(frames)
    return found, black, at


def _assert_frames(doc):
    rate = doc["fps"]
    found, black, end = _starts(doc)
    _, total = timeline(doc)
    assert end == frames_of(rounded(total), rate)
    clips = [clip for clip in doc["clips"] if clip["dur"] > 0]
    for before, clip in zip(clips, clips[1:]):
        first = frames_of(clip["start"], rate)
        assert found[clip["id"]][0] == first, (rate, clip["id"])
        assert abs(first / rate - clip["start"]) <= 0.5 / rate + 1e-9
        if clip["start"] - (before["start"] + before["dur"]) <= GRID + 1e-6:
            assert found[before["id"]][1] == first, (rate, before["id"])
    return found, black


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("kind", list(KINDS))
def test_off_the_grid_every_cut_falls_on_the_frame_of_its_start_with_no_black_and_no_drift(make_doc, kind, fps):
    pick = random.Random(f"120 {kind} {fps}")
    for _ in range(12):
        doc = _laid(make_doc, [KINDS[kind](pick) for _ in range(pick.randint(4, 30))], fps)
        if timeline(doc)[1] < 1.05:
            continue
        found, black = _assert_frames(doc)
        assert black == []
        assert len(found) == len(doc["clips"])


@pytest.mark.parametrize("fps", CADENCES)
async def test_a_long_run_off_the_grid_made_in_parts_joins_them_on_their_frames(make_doc, fps, tmp_path, monkeypatch):
    pick = random.Random(f"120 parts {fps}")
    doc = _laid(make_doc, [round(pick.uniform(0.4, 2), 3) for _ in range(video.PART_INPUTS + 17)], fps)
    spans = []

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        spans.append(total)
        return ""

    async def part_length(path, nominal):
        return nominal + 0.37

    monkeypatch.setattr(video, "assemble", assemble)
    monkeypatch.setattr(video, "_part_length", part_length)
    paths = {"ffmpeg": "/usr/bin/ffmpeg", "output": str(tmp_path / "m.mkv"), "graph": str(tmp_path / "g.txt"), "audio": {}}

    await video.assemble_sequence(doc, _files(doc), _options(), paths, tmp_path, lambda progress, step: True)

    _, total = timeline(doc)
    cut = frames_of(doc["clips"][video.PART_INPUTS]["start"], fps)
    assert [round(span * fps, 6) for span in spans[:2]] == [cut, frames_of(rounded(total), fps) - cut]
    assert spans[2] == total
    last = Path(paths["graph"]).read_text(encoding="utf-8").split(";")
    assert _read_graph(last, fps) == ({0: 0, 1: cut}, frames_of(rounded(total), fps))
    _assert_frames(doc)


@pytest.mark.parametrize("fps", CADENCES)
def test_the_error_of_a_cut_never_grows_with_the_number_of_shots(make_doc, fps):
    doc = _laid(make_doc, [1.02] * 24 + [0.97, 1.07, 1.01, 1.03] * 20, fps)

    found, black = _assert_frames(doc)

    errors = [abs(found[clip["id"]][0] / fps - clip["start"]) for clip in doc["clips"]]
    assert black == [] and max(errors) <= 0.5 / fps + 1e-9


@pytest.mark.parametrize("fps", (24, 25, 30))
def test_a_shot_of_3_1_s_then_one_of_2_s_cut_on_the_frame_of_3_12_s_with_no_black_frame(make_doc, fps):
    doc = _laid(make_doc, [3.1, 2], fps)

    assert [clip["start"] for clip in doc["clips"]] == [0, 3.12]
    found, black = _assert_frames(doc)
    assert black == [] and found == {"c000": (0, frames_of(3.12, fps)), "c001": (frames_of(3.12, fps), frames_of(5.12, fps))}


@pytest.mark.parametrize("fps", CADENCES)
def test_a_gap_of_a_second_stays_black_on_the_frames_of_its_bounds_and_a_late_first_shot_has_black_before_it(make_doc, fps):
    doc = _laid(make_doc, [1.3, 2.01, 0.97], fps)
    doc["clips"][0]["start"] = 0.4
    doc["clips"][1]["start"] = round(doc["clips"][1]["start"] + 0.4, 6)
    doc["clips"][2]["start"] = round(doc["clips"][2]["start"] + 1.4, 6)

    found, black = _assert_frames(doc)

    end = frames_of(rounded(doc["clips"][1]["start"] + doc["clips"][1]["dur"]), fps)
    assert black == [(0, frames_of(0.4, fps)), (end, frames_of(doc["clips"][2]["start"], fps))]
    assert found["c001"][1] == end and found["c002"][0] - end >= round(fps * 0.96)


@pytest.mark.parametrize("fps", CADENCES)
def test_a_gap_of_one_step_or_less_is_played_by_the_shot_before_and_a_longer_one_is_black(make_doc, fps):
    doc = make_doc(clips=[{"id": "a", "start": 0, "dur": 1.2}, {"id": "b", "start": 1.24, "dur": 1}, {"id": "c", "start": 2.2941, "dur": 1}])
    doc["fps"] = fps

    found, black, _ = _starts(doc)

    assert found["a"] == (0, frames_of(1.24, fps))
    assert found["b"] == (frames_of(1.24, fps), frames_of(2.24, fps))
    assert black == ([(frames_of(2.24, fps), frames_of(2.2941, fps))] if frames_of(2.2941, fps) > frames_of(2.24, fps) else [])


@pytest.mark.parametrize("fps", CADENCES)
def test_an_overlap_of_less_than_a_step_cuts_the_shot_before_on_the_start_of_the_next(make_doc, fps):
    doc = _laid(make_doc, [1.01, 1.0, 1.0], fps)
    assert doc["clips"][1]["start"] < doc["clips"][0]["dur"]

    found, black = _assert_frames(doc)

    assert black == [] and found["c000"] == (0, frames_of(doc["clips"][1]["start"], fps))


@pytest.mark.parametrize("fps", CADENCES)
def test_a_slowed_shot_off_the_grid_reads_its_source_at_its_speed_over_its_frames(make_doc, fps):
    doc = _laid(make_doc, [1.01, 2.03, 0.99], fps)
    doc["clips"][1].update(speed=0.5, srcIn=0.37)

    graph = _graph(doc)
    found, black = _assert_frames(doc)

    first, last = found["c001"]
    chain = next(part for part in graph if part.endswith("[v1]"))
    assert f"trim=start=0.37:duration={video.num((last - first) / fps * 0.5)}," in chain
    assert "setpts=(PTS-STARTPTS)/0.5" in chain and black == []


@pytest.mark.parametrize("fps", CADENCES)
def test_the_fades_to_black_of_a_shot_off_the_grid_end_on_its_cut_and_it_reads_its_source_from_where_its_first_frame_falls(make_doc, fps):
    doc = _laid(make_doc, [1.3, 3.1, 2], fps)
    doc["clips"][1].update(fadeIn=0.5, fadeOut=0.7, srcIn=1.234)

    graph = _graph(doc, audio={clip["id"]: True for clip in doc["clips"]})
    found, _ = _assert_frames(doc)

    length = video.num((found["c001"][1] - found["c001"][0]) / fps)
    point = video.num(1.234 + found["c001"][0] / fps - doc["clips"][1]["start"])
    picture = next(part for part in graph if part.endswith("[v1]"))
    sound = next(part for part in graph if part.endswith("[a1]"))
    assert f"trim=start={point}:duration={length}," in picture and f"atrim=start={point}:duration={length}," in sound
    assert f"fade=t=out:st={video.num((found['c001'][1] - found['c001'][0]) / fps - 0.7)}:d=0.7" in picture
    assert "fade=t=in:st=0:d=0.5" in picture and "afade=t=in:st=0:d=0.5" in sound


@pytest.mark.parametrize("fps", (24, 30))
def test_the_sound_tracks_keep_their_document_times_and_the_crossfade_of_the_master(make_doc, fps):
    doc = _laid(make_doc, [1.02] * 6, fps)
    doc["lanes"] = [{"id": "A1", "name": "Music", "role": "Musique", "vol": 0, "pan": 0, "mute": False, "solo": False}]
    doc["audio"] = [
        {"id": "m1", "assetId": None, "lane": "A1", "start": 0.5, "dur": 2.3, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0},
        {"id": "m2", "assetId": None, "lane": "A1", "start": 2.8, "dur": 2.1, "srcIn": 0.4, "fadeIn": 0, "fadeOut": 0, "gain": 0},
    ]
    doc["master"] = {**(doc.get("master") or {}), "crossfade": 0.5}
    paths = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/m.mkv", "graph": "/tmp/out/g.txt", "audio": {"m1": "/media/m1.wav", "m2": "/media/m2.wav"}}

    graph = filter_graph(doc, _files(doc), _options(), paths).split(";")

    music = [part for part in graph if part.startswith(("[6:a]", "[7:a]")) or "acrossfade=d=0.5:" in part or part.startswith("[m0j1]")]
    assert [part.split("]", 1)[1].split(",", 1)[0] for part in music[:2]] == ["atrim=start=0:duration=2.55", "atrim=start=0.15:duration=2.35"]
    assert any("acrossfade=d=0.5:" in part for part in music)
    assert any(part.startswith("[m0j1]adelay=delays=500:all=1") for part in music)
    _assert_frames(doc)


@pytest.mark.parametrize("fps", CADENCES)
def test_a_project_that_dissolves_keeps_its_cuts_and_a_gap_of_less_than_a_step_written_by_hand_after_a_dissolve_has_no_black(make_doc, fps):
    doc = make_doc(clips=[{"id": "a", "dur": 2}, {"id": "b", "dur": 3.1, "dissolve": 1}, {"id": "c", "dur": 2}, {"id": "d", "dur": 1.02}])
    doc["fps"] = fps
    edits.relayout(doc)
    assert joins(doc["clips"]) == [0, 1, 0, 0]

    def cut():
        segments, _ = timeline(doc)
        starts, _ = _read_graph(_graph(doc), fps)
        assert all(clip is not None for _, clip in segments)
        third = starts[2]
        assert round(sum(dur for dur, _ in segments[:2]) * fps) - segments[1][1][video.JOIN] == third
        return third

    assert cut() == frames_of(4.1, fps)
    doc["clips"][2]["start"], doc["clips"][3]["start"] = 4.12, 6.12
    assert cut() == frames_of(4.12, fps)


def test_a_document_without_clips_is_a_film_of_black(make_doc):
    doc = make_doc()
    doc.pop("clips")
    doc["audio"] = [{"id": "m", "assetId": None, "lane": "A1", "start": 0, "dur": 2.02, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0}]

    segments, total = timeline(doc)

    assert total == pytest.approx(2.02) and [(round(dur * 25), clip) for dur, clip in segments] == [(51, None)]


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("after", (1.2, 2.0, 3.48, 7.12, 10.0))
def test_a_gap_of_one_step_and_a_millionth_is_played_by_the_shot_before_and_one_of_two_millionths_is_black_wherever_it_falls(make_doc, fps, after):
    def black(gap):
        doc = make_doc(clips=[{"id": "a", "start": 0, "dur": after}, {"id": "b", "start": round(after + gap, 6), "dur": 1}])
        doc["fps"] = fps
        found, black, _ = _starts(doc)
        assert found["b"][0] == frames_of(round(after + gap, 6), fps)
        return black

    bounds = (frames_of(after, fps), frames_of(round(after + 0.040002, 6), fps))
    assert black(0.04) == []
    assert black(0.040001) == []
    assert black(0.040002) == ([bounds] if bounds[1] > bounds[0] else [])
    rule = [filled(placement([{"start": 0, "dur": after}, {"start": round(after + gap, 6), "dur": 1}]))[0] for gap in (0.04, 0.040001, 0.040002)]
    assert rule == [True, True, False]


def _pieces(make_doc, durations, fps, **extra):
    at, clips = 0.0, []
    for index, dur in enumerate(durations):
        clips.append({"id": f"p{index:02d}", "assetId": "one", "dur": dur, "srcIn": round(at, 6), **extra.get(index, {})})
        at += dur
    doc = make_doc(clips=clips)
    doc["fps"] = fps
    doc["assets"] = [{"id": "one", "kind": "video", "name": "one.mp4", "srcDur": 1000}]
    edits.relayout(doc)
    return doc, {clip["id"]: {"name": "one.mp4", "path": "/media/one.mp4"} for clip in clips}


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("dur", (1.2, 1.04, 1.0, 0.96, 1.02, 1.013))
def test_contiguous_pieces_of_one_file_share_one_input_and_read_it_on_from_one_piece_to_the_next(make_doc, fps, dur):
    doc, files = _pieces(make_doc, [dur] * 45, fps)
    paths = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/m.mkv", "graph": "/tmp/out/g.txt", "audio": {}}
    heard = _options(audio={clip["id"]: True for clip in doc["clips"]})
    segments, _ = timeline(doc)
    found, _ = _assert_frames(doc)

    assert build_command(doc, files, heard, paths).count("-i") == 1
    assert len(video.plan_parts(doc, files, heard, segments)) == 1
    graph = filter_graph(doc, files, heard, paths).split(";")
    pictures = [float(part.split("trim=start=", 1)[1].split(":", 1)[0]) for part in graph if part.startswith("[0:v]trim=start=")]
    sounds = [float(part.split("atrim=start=", 1)[1].split(":", 1)[0]) for part in graph if part.startswith("[0:a]atrim=start=")]
    expected = [max(clip["srcIn"] + found[clip["id"]][0] / fps - clip["start"], 0) for clip in doc["clips"]]
    assert pictures == pytest.approx(expected, abs=1e-6) and sounds == pytest.approx(expected, abs=1e-6)
    continuous = 0
    for index, (before, after) in enumerate(zip(doc["clips"], doc["clips"][1:])):
        if after["srcIn"] == rounded(before["srcIn"] + before["dur"]) and after["start"] == rounded(before["start"] + before["dur"]):
            assert pictures[index + 1] == pytest.approx(pictures[index] + segments[index][0], abs=1e-6)
            continuous += 1
    assert continuous or dur not in (1.2, 1.04, 1.0, 0.96)


def test_a_shot_reads_its_source_from_where_the_film_reaches_it_as_the_page_does():
    assert [read_at(1.02, 1.02, 24, 24), read_at(0, 1.02, 24, 24), read_at(0.37, 1.04, 26, 25), read_at(0.4, 1.04, 25, 24, 0.5)] == [1.0, -0.02, 0.37, 0.400834]


def _numbered(folder, rate, frames):
    path = folder / f"numbered-{rate}.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"nullsrc=s=128x72:r={rate}:d={frames / rate},format=gray,geq=lum='16+16*N',format=yuv420p",
        "-f", "lavfi", "-i", f"sine=frequency=880:sample_rate=48000:duration={frames / rate}",
        "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(path),
    ], check=True, timeout=60)
    return path


@pytest.mark.parametrize("fps", (24, 30, 48, 60))
def test_a_shot_whose_first_frame_falls_before_the_start_of_its_source_reads_it_from_0_and_its_sound_waits_in_silence(make_doc, fps):
    start = round((fps + 0.4) / fps, 6)
    doc = make_doc(clips=[{"id": "a", "assetId": "a", "start": 0, "dur": start, "srcIn": 0}, {"id": "b", "assetId": "b", "start": start, "dur": 1, "srcIn": 0}])
    doc["fps"] = fps
    first = frames_of(start, fps)
    lead = rounded(start - first / fps)
    assert first == fps and lead > 0

    graph = _graph(doc, audio={"a": True, "b": True})

    picture = next(part for part in graph if part.endswith("[v1]"))
    sound = next(part for part in graph if part.endswith("[a1]"))
    length = (frames_of(start + 1, fps) - first) / fps
    assert picture.startswith("[1:v]trim=start=0:") and "tpad=start_mode" not in picture
    assert sound.startswith(f"[1:a]atrim=start=0:duration={video.num(length - lead)},") and f"adelay=delays={round(lead * 48000)}S:all=1," in sound


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("fps", (24, 48, 60))
async def test_a_real_export_of_a_shot_whose_first_frame_falls_before_the_start_of_its_source_shows_its_frames_from_the_first_on(make_doc, tmp_path, fps):
    red = _solid(tmp_path, "red.mp4", "red", 440, 2, fps)
    numbered = _numbered(tmp_path, fps, 12)
    start = round((fps + 0.4) / fps, 6)
    shown = 8
    doc = make_doc(clips=[{"id": "a", "assetId": "a", "start": 0, "dur": start, "srcIn": 0}, {"id": "b", "assetId": "b", "start": start, "dur": round(shown / fps, 6), "srcIn": 0}])
    doc.update(fps=fps, resolution="720p")
    doc["assets"] = [{"id": "a", "kind": "video", "name": red.name, "srcDur": 2}, {"id": "b", "kind": "video", "name": numbered.name, "srcDur": 12 / fps}]
    files = {"a": {"name": red.name, "path": str(red)}, "b": {"name": numbered.name, "path": str(numbered)}}
    output = tmp_path / "mezzanine.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "audio": {"a": True, "b": True}, "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")
    _, total = timeline(doc)

    await video.assemble(build_command(doc, files, options, paths), total)

    levels = [_frame(numbered, n)[0] for n in range(12)]
    numbers = [min(range(12), key=lambda n: abs(levels[n] - _frame(output, fps + k)[0])) for k in range(shown - 1)]
    assert numbers == list(range(shown - 1)), numbers
    samples = _samples(output)
    assert float(abs(samples[48000 + 2 : int(start * 48000) - 2]).max()) < 1e-3
    assert _tone(samples, start + 0.005, start + shown / fps - 0.01, 880) > 0.05


@pytest.mark.parametrize("fps", CADENCES)
def test_a_file_taken_up_again_later_over_a_part_of_its_source_already_read_opens_its_own_input_as_in_version_0_5_0(make_doc, fps):
    doc = make_doc(clips=[
        {"id": "a", "assetId": "one", "dur": 0.68, "srcIn": 1.24},
        {"id": "b", "assetId": "two", "dur": 1.2, "srcIn": 0},
        {"id": "c", "assetId": "one", "dur": 1.0, "srcIn": 1.88},
        {"id": "d", "assetId": "one", "dur": 1.0, "srcIn": 2.88},
    ])
    doc["fps"] = fps
    edits.relayout(doc)
    files = {clip["id"]: {"name": f"{clip['assetId']}.mp4", "path": f"/media/{clip['assetId']}.mp4"} for clip in doc["clips"]}
    paths = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/m.mkv", "graph": "/tmp/out/g.txt", "audio": {}}

    command = build_command(doc, files, _options(), paths)

    assert [command[i + 1] for i, part in enumerate(command) if part == "-i"] == ["/media/one.mp4", "/media/two.mp4", "/media/one.mp4"]


@pytest.mark.parametrize("fps", CADENCES)
def test_pieces_of_one_file_that_go_back_in_it_still_open_an_input_each(make_doc, fps):
    doc, files = _pieces(make_doc, [1.04, 1.04, 1.04], fps)
    doc["clips"][2]["srcIn"] = 0.5
    paths = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/m.mkv", "graph": "/tmp/out/g.txt", "audio": {}}

    assert build_command(doc, files, _options(), paths).count("-i") == 2


@pytest.mark.parametrize("fps", (24, 25, 30))
def test_the_fade_out_of_the_last_shot_ends_where_the_film_is_cut(make_doc, fps):
    last = round((round(2.6 * fps) + 0.5) / fps, 6)
    doc = _laid(make_doc, [1.0, last], fps)
    doc["clips"][1]["fadeOut"] = 0.25
    doc["clips"][0]["fadeOut"] = 0.25

    graph = _graph(doc, audio={clip["id"]: True for clip in doc["clips"]})
    found, _ = _assert_frames(doc)
    _, total = timeline(doc)

    start = found["c001"][0] / fps
    assert found["c001"][1] / fps > total
    for label in ("[v1]", "[a1]"):
        chain = next(part for part in graph if part.endswith(label))
        assert f"fade=t=out:st={video.num(total - start - 0.25)}:d=0.25" in chain
    first = next(part for part in graph if part.endswith("[v0]"))
    assert f"fade=t=out:st={video.num(found['c000'][1] / fps - 0.25)}:d=0.25" in first


@pytest.mark.parametrize("fps", (24, 25, 30))
def test_a_very_short_last_shot_keeps_its_fade_in_and_fades_out_by_the_end_of_the_film(make_doc, fps):
    last = round((round(0.2 * fps) - 0.4) / fps, 6)
    doc = _laid(make_doc, [1.0, last], fps)
    doc["clips"][1].update(fadeIn=0.2, fadeOut=0.1)

    graph = _graph(doc, audio={clip["id"]: True for clip in doc["clips"]})
    found, _ = _assert_frames(doc)
    _, total = timeline(doc)

    span = (found["c001"][1] - found["c001"][0]) / fps
    until = total - found["c001"][0] / fps
    assert found["c001"][1] / fps > total and until < min(0.2, span)
    for label, name in (("[v1]", "fade"), ("[a1]", "afade")):
        chain = next(part for part in graph if part.endswith(label))
        assert f"{name}=t=in:st=0:d={video.num(min(0.2, span))}" in chain
        assert f"{name}=t=out:st={video.num(until - 0.1)}:d=0.1" in chain


@pytest.mark.parametrize("fps", (24, 25, 30))
def test_shots_pushed_past_the_end_of_the_film_are_left_out_and_no_fade_is_negative(make_doc, fps):
    doc = make_doc(clips=[{"id": k, "assetId": k, "start": 0, "dur": 2, "srcIn": 0, "fadeIn": 0.3 if k == "c" else 0, "fadeOut": 0.3 if k == "b" else 0} for k in "abc"])
    doc["fps"] = fps

    segments, total = timeline(doc)
    graph = _graph(doc, audio={k: True for k in "abc"})

    assert total == 2 and [(round(dur * fps), clip["id"]) for dur, clip in segments] == [(2 * fps, "a")]
    assert not any(re.search(r"(?:d|st)=-", part) for part in graph)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_of_shots_written_on_one_start_with_fades_succeeds(make_doc, tmp_path):
    white = _solid(tmp_path, "white.mp4", "white", 440, 2.5)
    doc = make_doc(clips=[{"id": k, "assetId": "w", "start": 0, "dur": 2, "srcIn": 0, "fadeIn": 0.3 if k == "c" else 0, "fadeOut": 0.3 if k == "b" else 0} for k in "abc"])
    doc.update(fps=24, resolution="720p")
    doc["assets"] = [{"id": "w", "kind": "video", "name": white.name, "srcDur": 2.5}]
    files = {k: {"name": white.name, "path": str(white)} for k in "abc"}
    output = tmp_path / "mezzanine.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "audio": {k: True for k in "abc"}, "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")

    await video.assemble(build_command(doc, files, options, paths), 2)

    assert _frames(output) == 48


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_that_ends_on_half_a_frame_fades_its_last_shot_out_by_the_cut(make_doc, tmp_path):
    white = _solid(tmp_path, "white.mp4", "white", 440, 4)
    doc = _laid(make_doc, [3.5], 25, resolution="720p")
    doc["clips"][0]["fadeOut"] = 0.25
    files = {"c000": {"name": white.name, "path": str(white)}}
    output = tmp_path / "mezzanine.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")

    await video.assemble(build_command(doc, files, options, paths), 3.5)

    assert _frames(output) == 88
    assert max(_frame(output, 87)) < 0.12 * 255
    assert max(_frame(output, 80)) > 0.4 * 255


@pytest.fixture
def red_and_blue(tmp_path):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg and ffprobe are not on the PATH")
    return _solid(tmp_path, "red.mp4", "red", 440, 3.1), _solid(tmp_path, "blue.mp4", "blue", 880, 2)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.parametrize("fps", (24, 25, 30))
async def test_a_real_export_of_3_1_s_then_2_s_has_no_black_frame_and_the_blue_shot_starts_with_its_sound_on_its_frame(make_doc, red_and_blue, tmp_path, fps):
    doc = _laid(make_doc, [3.1, 2], fps, resolution="720p")
    doc["assets"] = [{"id": f"a{index}", "kind": "video", "name": path.name, "srcDur": dur} for index, (path, dur) in enumerate(zip(red_and_blue, (3.1, 2)))]
    files = {clip["id"]: {"name": path.name, "path": str(path)} for clip, path in zip(doc["clips"], red_and_blue)}
    output = tmp_path / f"mezzanine-{fps}.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "audio": {clip["id"]: True for clip in doc["clips"]}, "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")

    await video.assemble(build_command(doc, files, options, paths), 5.12)

    cut = frames_of(3.12, fps)
    assert _frames(output) == frames_of(5.12, fps)
    for number in range(cut - 3, cut + 3):
        pixel = _frame(output, number)
        assert max(pixel) > 150, (fps, number, pixel)
        assert (pixel[0] > 150) == (number < cut), (fps, number, pixel)
    samples = _samples(output)
    step = 0.5 / fps
    assert _tone(samples, cut / fps - 0.2, cut / fps - step, 440) > 10 * _tone(samples, cut / fps - 0.2, cut / fps - step, 880)
    assert _tone(samples, cut / fps + step, cut / fps + 0.2, 880) > 10 * _tone(samples, cut / fps + step, cut / fps + 0.2, 440)
