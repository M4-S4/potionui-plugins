import json
import random
import re
from pathlib import Path

import pytest

from backend.dissolve import cuts, frames_of
from backend.exports import render
from backend.exports.common import js_round
from backend.exports.video import timeline

from .test_dissolve import CADENCES, _graph, _read_graph
from .test_export_frames import KINDS, _assert_frames, _laid, _pieces


def _exchange_frames(doc):
    fps = doc["fps"]
    media = {("clips", index): {"name": f"{clip['id']}.mp4", "path": f"{clip['id']}.mp4"} for index, clip in enumerate(doc["clips"])}
    ids = [clip["id"] for clip in doc["clips"]]
    edl = {}
    events = [line.split() for line in render("edl", doc, media).split("\r\n") if line[:3].isdigit()]
    for fields in events:
        frames = []
        for code in fields[-2:]:
            hours, minutes, seconds, rest = (int(part) for part in code.split(":"))
            frames.append(((hours * 60 + minutes) * 60 + seconds) * fps + rest)
        edl[ids[int(fields[0]) - 1]] = tuple(frames)
    fcpxml = {}
    for match in re.finditer(r'<asset-clip [^>]*?offset="(\d+)/\d+s"[^>]*?duration="(\d+)/\d+s"', render("fcpxml", doc, media)):
        fcpxml[ids[len(fcpxml)]] = (int(match.group(1)), int(match.group(1)) + int(match.group(2)))
    otio, at = {}, 0
    for item in json.loads(render("otio", doc, media))["tracks"]["children"][0]["children"]:
        if item["OTIO_SCHEMA"] == "Transition.1":
            continue
        length = item["source_range"]["duration"]["value"]
        otio[ids[len(otio)]] = (at, at + length)
        at += length
    return edl, otio, fcpxml


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("kind", list(KINDS))
def test_the_cuts_of_the_exchange_files_fall_on_the_frames_of_the_video_off_the_grid(make_doc, kind, fps):
    pick = random.Random(f"120 exchange {kind} {fps}")
    checked = 0
    for _ in range(8):
        doc = _laid(make_doc, [KINDS[kind](pick) for _ in range(pick.randint(4, 24))], fps, name="Exchange")
        if timeline(doc)[1] < 1.05:
            continue
        found, black = _assert_frames(doc)
        assert black == []
        for written in _exchange_frames(doc):
            assert written == found, (kind, fps)
        checked += 1
    assert checked >= 4


@pytest.mark.parametrize("fps", CADENCES)
def test_a_project_on_the_grid_keeps_the_times_of_its_shots_in_its_exchange_files(make_doc, fps):
    doc = _laid(make_doc, [1.04, 2.4, 0.8], fps, name="Exchange")

    assert cuts(doc["clips"], lambda seconds: js_round(seconds * fps)) == [None] * 3
    found, _ = _assert_frames(doc)
    for written in _exchange_frames(doc):
        assert written == found


SLOWED = json.loads((Path(__file__).resolve().parent / "fixtures" / "exports" / "on-grid-slowed.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fmt", ("edl", "otio", "fcpxml"))
def test_a_project_on_the_grid_at_25_fps_with_slowed_shots_keeps_the_exchange_files_of_version_0_5_0(fmt):
    assert [render(fmt, case["doc"], {}) for case in SLOWED] == [case[fmt] for case in SLOWED]


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("durations", ([1.01, 1.0, 1.0], [7 / 3, 2, 3, 2, 3, 5 / 3], [2.44, 1.41, 0.76, 0.89, 1.39]), ids=("three", "thirds", "five"))
def test_a_project_with_overlaps_of_the_layout_only_writes_the_frames_of_the_video_in_the_three_formats(make_doc, fps, durations):
    doc = _laid(make_doc, durations, fps, name="Exchange")

    found, black = _assert_frames(doc)

    assert black == []
    for written in _exchange_frames(doc):
        assert written == found, fps


def _timecode_frames(code, fps):
    hours, minutes, seconds, rest = (int(part) for part in code.split(":"))
    return ((hours * 60 + minutes) * 60 + seconds) * fps + rest


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("dur", (1.02, 1.013, 1.04))
def test_the_source_points_of_the_exchange_files_are_those_the_video_reads(make_doc, fps, dur):
    doc, _ = _pieces(make_doc, [dur] * 12, fps)
    doc["name"] = "Exchange"
    media = {("clips", index): {"name": "one.mp4", "path": "one.mp4"} for index in range(len(doc["clips"]))}
    graph = _graph(doc, {clip["id"]: {"name": "one.mp4", "path": "/media/one.mp4"} for clip in doc["clips"]})
    found, _ = _assert_frames(doc)
    reads = [float(part.split("trim=start=", 1)[1].split(":", 1)[0]) for part in graph if part.startswith("[0:v]trim=start=")]
    entries = [js_round(point * fps) for point in reads]
    exits = [entry + found[clip["id"]][1] - found[clip["id"]][0] for entry, clip in zip(entries, doc["clips"])]

    events = [line.split() for line in render("edl", doc, media).split("\r\n") if line[:3].isdigit()]
    assert [_timecode_frames(fields[-4], fps) for fields in events] == entries
    assert [_timecode_frames(fields[-3], fps) for fields in events] == exits
    otio = [item for item in json.loads(render("otio", doc, media))["tracks"]["children"][0]["children"] if item["OTIO_SCHEMA"] == "Clip.2"]
    assert [item["source_range"]["start_time"]["value"] for item in otio] == entries
    assert [int(start) for start in re.findall(r'<asset-clip [^>]*?start="(\d+)/\d+s"', render("fcpxml", doc, media))] == entries


@pytest.mark.parametrize("fps", (24, 25, 30))
def test_a_gap_of_less_than_a_step_written_by_hand_after_a_dissolve_is_closed_in_the_exchange_files_as_in_the_video(make_doc, fps):
    doc = make_doc(clips=[{"id": "a", "start": 0, "dur": 2}, {"id": "b", "start": 1.6, "dur": 2, "dissolve": 0.4}, {"id": "c", "start": 3.64, "dur": 2}])
    doc.update(fps=fps, name="Exchange")
    starts, _ = _read_graph(_graph(doc), fps)

    edits = cuts(doc["clips"], lambda seconds: js_round(seconds * fps))

    assert edits[1].end == frames_of(3.64, fps) == starts[2]
    edl, otio, fcpxml = _exchange_frames(doc)
    assert edl["b"][1] == edl["c"][0] == fcpxml["b"][1] == fcpxml["c"][0] == frames_of(3.64, fps)
