import json
import math
import random
import re
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import numpy
import pytest

from backend import core_bridge, projects, takes
from backend.chat import context, edits
from backend.dissolve import MAX_DISSOLVE, chained, cuts, dissolve_of, frames_of, joins, moved, placement, rounded, shown
from backend.exports import render
from backend.exports import video
from backend.exports.common import js_round
from backend.exports.media import files_of
from backend.exports.mix import write_impulse
from backend.exports.video import build_command, filter_graph, plan_parts, timeline

from . import dissolve_property
from .test_exports import FixtureResolver

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXPORTS = FIXTURES / "exports"
CASES = json.loads((FIXTURES / "dissolve_cases.json").read_text(encoding="utf-8"))
PROPERTY = json.loads((FIXTURES / "dissolve_property.json").read_text(encoding="utf-8"))
CADENCES = (24, 25, 30, 48, 50, 60)
LEGACY = json.loads((EXPORTS / "legacy-graphs.json").read_text(encoding="utf-8"))
ON_GRID = json.loads((EXPORTS / "on-grid-graphs.json").read_text(encoding="utf-8"))
ON_GRID_FRAMES = json.loads((EXPORTS / "on-grid-graphs-24-30.json").read_text(encoding="utf-8"))
PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt"}


def _clips(case):
    return [{"id": f"c{index}", **clip} for index, clip in enumerate(case["clips"])]


def _laid(case):
    return [{**clip, "start": start} for clip, start in zip(_clips(case), case["starts"])]


def _options(**fields):
    return {"format": "web", "resolution": "720p", "audio": {}, "stills": [], "impulse": "/tmp/out/reverb.wav", **fields}


def _doc(make_doc, clips, **fields):
    doc = make_doc(clips=clips)
    doc.update(fields)
    return doc


def _files(doc):
    return {clip["id"]: {"name": f"{clip['id']}.mp4", "path": f"/media/{clip['id']}.mp4"} for clip in doc["clips"]}


def _graph(doc, files=None, **options):
    return filter_graph(doc, _files(doc) if files is None else files, _options(**options), {**PATHS, "audio": {}}).split(";")


def _run(make_doc, durations, joins, **extra):
    clips = [{"id": f"c{index}", "assetId": f"a{index}", "dur": dur, **({"dissolve": join} if join else {})} for index, (dur, join) in enumerate(zip(durations, joins))]
    doc = _doc(make_doc, clips, **extra)
    edits.relayout(doc)
    return doc


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_shared_cases_give_the_dissolve_each_cut_plays_on_the_grid_of_the_document(case):
    clips = _laid(case)

    assert joins(clips) == pytest.approx(case["joins"], abs=1e-9)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_the_assistant_lays_the_shots_out_with_their_dissolves(case):
    doc = {"clips": [{**clip, "start": 99} for clip in _clips(case)], "prompts": [], "frames": []}

    edits.relayout(doc)

    assert [clip["start"] for clip in doc["clips"]] == pytest.approx(case["starts"], abs=1e-9)


def test_a_dissolve_moves_the_later_shots_and_their_prompts_but_not_the_sounds_titles_or_markers(make_doc):
    doc = _doc(
        make_doc,
        [{"id": "a", "dur": 4}, {"id": "b", "start": 4, "dur": 4}, {"id": "c", "start": 8, "dur": 4}],
        prompts=[{"id": "p", "shotId": "c", "start": 9, "dur": 1, "text": "x", "strength": 75}],
    )
    doc["audio"] = [{"id": "u", "assetId": None, "lane": "A1", "start": 9, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0}]
    doc["titles"] = [{"id": "t", "text": "T", "sub": "", "start": 9, "dur": 1}]
    doc["markers"] = [{"id": "m", "time": 9, "label": "M"}]
    doc["clips"][1]["dissolve"] = 1

    edits.relayout(doc)

    assert [clip["start"] for clip in doc["clips"]] == [0, 3, 7]
    assert doc["prompts"][0]["start"] == 8
    assert (doc["audio"][0]["start"], doc["titles"][0]["start"], doc["markers"][0]["time"]) == (9, 9, 9)


def test_the_document_takes_a_dissolve_up_to_two_seconds_on_a_shot(make_doc):
    doc = _doc(make_doc, [{"id": "a", "dur": 4}, {"id": "b", "start": 3, "dur": 4, "dissolve": MAX_DISSOLVE}])

    projects.validate_doc(doc)
    for right in (0, 0.08, 0.4, 1.2):
        doc["clips"][1]["dissolve"] = right
        projects.validate_doc(doc)
    for wrong in (-0.5, 0.04, 0.079, MAX_DISSOLVE + 0.04, "1", True):
        doc["clips"][1]["dissolve"] = wrong
        with pytest.raises(projects.DocError):
            projects.validate_doc(doc)


def test_a_dissolve_never_needs_a_migration(make_doc):
    doc = _doc(make_doc, [{"id": "a", "dur": 4}, {"id": "b", "start": 3, "dur": 4, "dissolve": 1}])

    assert projects.migrate(doc) is doc


async def _runs(case, limit, folder, monkeypatch):
    found = []

    def clean(text):
        return text.replace(str(folder), "<work>").replace("<work>\\", "<work>/")

    def relative(text):
        return "./" + text[2:] if text.startswith(".\\") else text

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        option = next(argument for argument in command if argument in (video.GRAPH_OPTION, video.LEGACY_GRAPH_OPTION))
        graph = Path(command[command.index(option) + 1]).read_text(encoding="utf-8")
        found.append({"command": [relative(clean(argument)) for argument in command], "graph": clean(graph), "total": round(total, 9)})
        return ""

    async def part_length(path, nominal):
        return nominal

    with monkeypatch.context() as patch:
        patch.setattr(video, "assemble", assemble)
        patch.setattr(video, "_part_length", part_length)
        if limit is not None:
            patch.setattr(video, "PART_INPUTS", limit)
        paths = {**case["paths"], "output": str(folder / "mezzanine.mkv"), "graph": str(folder / "graph.txt"), "audio": {}}
        await video.assemble_sequence(case["doc"], case["files"], case["options"], paths, folder, lambda progress, step: True)
    return found


@pytest.mark.parametrize("case", ON_GRID, ids=[case["name"] for case in ON_GRID])
async def test_a_project_on_the_grid_without_dissolve_gives_the_export_of_before_byte_for_byte_with_its_parts(case, tmp_path, monkeypatch):
    doc, files, options, paths = case["doc"], case["files"], case["options"], case["paths"]
    segments, total = timeline(doc)

    assert filter_graph(doc, files, options, paths) == case["graph"]
    assert build_command(doc, files, options, paths) == case["command"]
    assert total == case["total"]
    assert [[round(dur, 9), clip["id"] if clip else None] for dur, clip in segments] == case["segments"]
    assert [[[round(dur, 9), clip["id"] if clip else None] for dur, clip in group] for group in plan_parts(doc, files, options, segments, 1)] == case["parts of one input"]
    whole, halves = tmp_path / "whole", tmp_path / "halves"
    whole.mkdir()
    halves.mkdir()
    assert await _runs(case, None, whole, monkeypatch) == case["runs"]
    assert await _runs(case, 2, halves, monkeypatch) == case["runs in parts of two inputs"]


@pytest.mark.parametrize("case", ON_GRID_FRAMES, ids=[case["name"] for case in ON_GRID_FRAMES])
async def test_a_project_on_the_grid_at_24_or_30_fps_keeps_the_export_on_whole_frames_of_version_0_5_1(case, tmp_path, monkeypatch):
    await test_a_project_on_the_grid_without_dissolve_gives_the_export_of_before_byte_for_byte_with_its_parts(case, tmp_path, monkeypatch)


def _last_shot_on_whole_frames(chain):
    return re.sub(r"(?<=[=])3\.5(?=[,\[:]|$)", "3.52", chain)


@pytest.mark.parametrize("case", LEGACY, ids=[case["name"] for case in LEGACY])
def test_a_project_of_before_whose_film_ends_on_half_a_frame_changes_only_its_last_shot_which_now_lasts_its_whole_frames(case):
    doc, files, options, paths = case["doc"], case["files"], case["options"], case["paths"]
    segments, total = timeline(doc)
    before, after = case["graph"].split(";"), filter_graph(doc, files, options, paths).split(";")
    last = len(segments) - 1

    assert (total, case["segments"][-1], segments[-1][0]) == (case["total"], 3.5, pytest.approx(3.52))
    assert [round(dur, 9) for dur, _ in segments[:-1]] == [round(dur, 9) for dur in case["segments"][:-1]]
    assert len(before) == len(after)
    changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
    assert [re.findall(r"\[[av]\d+\]$", after[index])[0] for index in changed] == [f"[v{last}]", f"[a{last}]"]
    assert all(_last_shot_on_whole_frames(before[index]) == after[index] for index in changed)
    command = build_command(doc, files, options, paths)
    assert [(old, new) for old, new in zip(case["command"], command) if old != new] == ([("3.75", "3.77")] if case["name"] == "gap-social-stills" else [])
    assert [len(group) for group in plan_parts(doc, files, options, segments, 1)] == [len(group) for group in case["parts"]]


def test_the_film_lasts_the_shots_less_their_dissolves(make_doc):
    doc = _run(make_doc, [2, 2, 1], [0, 1, 0])

    segments, total = timeline(doc)

    assert [dur for dur, _ in segments] == [2, 2, 1] and total == 4


def test_a_dissolve_joins_two_shots_by_xfade_and_their_sound_by_acrossfade_before_the_concat(make_doc):
    doc = _run(make_doc, [2, 2, 1], [0, 1, 0], fps=25)

    graph = _graph(doc)

    assert "[v0][v1]xfade=transition=fade:duration=1:offset=1[x0v1]" in graph
    assert "[a0][a1]acrossfade=d=1:c1=qsin:c2=qsin[x0a1]" in graph
    assert "[x0v1][x0a1][v2][a2]concat=n=2:v=1:a=1[vout][bed]" in graph


def test_a_run_of_dissolves_offsets_each_join_by_what_is_already_joined(make_doc):
    doc = _run(make_doc, [2, 3, 2, 1], [0, 0.6, 1, 0], fps=25)

    graph = _graph(doc)

    assert "[v0][v1]xfade=transition=fade:duration=0.6:offset=1.4[x0v1]" in graph
    assert "[x0v1][v2]xfade=transition=fade:duration=1:offset=3.4[x0v2]" in graph
    assert "[x0a1][a2]acrossfade=d=1:c1=qsin:c2=qsin[x0a2]" in graph
    assert "[x0v2][x0a2][v3][a3]concat=n=2:v=1:a=1[vout][bed]" in graph
    assert timeline(doc)[1] == pytest.approx(6.4)


def test_the_fades_of_a_dissolved_cut_are_left_out_and_the_others_kept(make_doc):
    doc = _run(make_doc, [2, 2, 2], [0, 1, 0], fps=25)
    for clip in doc["clips"]:
        clip.update(fadeIn=0.4, fadeOut=0.4)

    chains = {part.rsplit("[", 1)[1].rstrip("]"): part for part in _graph(doc) if ":v]trim=" in part}

    assert "fade=t=in" in chains["v0"] and "fade=t=out" not in chains["v0"]
    assert "fade=t=in" not in chains["v1"] and "fade=t=out" in chains["v1"]
    assert "fade=t=in" in chains["v2"] and "fade=t=out" in chains["v2"]


def test_a_dissolve_after_a_gap_or_on_the_first_shot_is_a_cut(make_doc):
    doc = _doc(make_doc, [{"id": "a", "assetId": "x", "dur": 2, "dissolve": 1}, {"id": "b", "assetId": "y", "start": 3, "dur": 2, "dissolve": 1}])

    graph = _graph(doc)

    assert not any("xfade" in part or "acrossfade" in part for part in graph)
    assert [dur for dur, _ in timeline(doc)[0]] == [2, 1, 2]


def test_the_limit_of_inputs_per_part_holds_inside_a_long_run_of_dissolves(make_doc):
    doc = _run(make_doc, [1] * 60, [0] + [0.4] * 59)
    segments, _ = timeline(doc)

    assert [len(group) for group in plan_parts(doc, _files(doc), _options(), segments)] == [40, 20]


async def test_a_long_run_of_dissolves_is_made_in_parts_that_the_last_run_joins_with_the_dissolve_between_them(make_doc, tmp_path, monkeypatch):
    doc = _run(make_doc, [1] * 60, [0] + [0.4] * 59, fps=25)
    commands = []

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        commands.append((command, total))
        return ""

    async def part_length(path, nominal):
        return nominal

    monkeypatch.setattr(video, "assemble", assemble)
    monkeypatch.setattr(video, "_part_length", part_length)
    paths = {**PATHS, "output": str(tmp_path / "m.mkv"), "graph": str(tmp_path / "g.txt"), "audio": {}}

    await video.assemble_sequence(doc, _files(doc), _options(), paths, tmp_path, lambda progress, step: True)

    assert [command.count("-i") for command, _ in commands] == [40, 20, 2]
    assert [total for _, total in commands] == pytest.approx([40 - 39 * 0.4, 20 - 19 * 0.4, 60 - 59 * 0.4])
    last = Path(paths["graph"]).read_text(encoding="utf-8").split(";")
    assert f"[v0][v1]xfade=transition=fade:duration=0.4:offset={40 - 39 * 0.4 - 0.4:g}[x0v1]" in last
    assert "[a0][a1]acrossfade=d=0.4:c1=qsin:c2=qsin[x0a1]" in last
    first, second = (tmp_path / video.PART_GRAPH.format(0, k) for k in (0, 1))
    assert first.read_text(encoding="utf-8").count("xfade=") == 39 and second.read_text(encoding="utf-8").count("xfade=") == 19


async def test_a_part_lasts_its_shots_less_its_dissolves(make_doc, tmp_path, monkeypatch):
    doc = _run(make_doc, [2, 2, 2, 2], [0, 1, 0, 1], fps=25)
    spans = []

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        spans.append(total)
        return ""

    async def part_length(path, nominal):
        return nominal

    monkeypatch.setattr(video, "assemble", assemble)
    monkeypatch.setattr(video, "_part_length", part_length)
    monkeypatch.setattr(video, "PART_INPUTS", 2)
    paths = {**PATHS, "output": str(tmp_path / "m.mkv"), "graph": str(tmp_path / "g.txt"), "audio": {}}

    await video.assemble_sequence(doc, _files(doc), _options(), paths, tmp_path, lambda progress, step: True)

    assert spans == [3, 3, 6]


def _fixture():
    fixture = json.loads((EXPORTS / "dissolve-project.json").read_text(encoding="utf-8"))
    return fixture, files_of(fixture["doc"], fixture["takes"], FixtureResolver(fixture["uploads"]), media="name")


def test_the_dissolve_project_is_a_document_the_plugin_stores():
    fixture, _ = _fixture()

    projects.validate_doc(fixture["doc"])
    assert joins(fixture["doc"]["clips"]) == [0, 1, 0.52, 1.48]
    assert [cut.overlap if cut else 0 for cut in cuts(fixture["doc"]["clips"], lambda s: js_round(s * 25))] == [0, 25, 13, 37]


@pytest.mark.parametrize("fmt", ("edl", "otio", "fcpxml"))
def test_each_exchange_format_writes_the_dissolves_as_its_golden_file(fmt):
    fixture, files = _fixture()

    assert render(fmt, fixture["doc"], files).encode("utf-8") == (EXPORTS / f"dissolve.{fmt}").read_bytes()


def test_the_layout_rounds_a_time_to_the_step_as_the_page_does_a_half_step_up_even_when_the_sum_that_gives_it_falls_just_below():
    cases = json.loads((FIXTURES / "snap_cases.json").read_text(encoding="utf-8"))

    assert [edits.snap(value) for value, _ in cases] == [snapped for _, snapped in cases]
    assert edits.snap(1.02 + 0.84) == 1.88
    pick = random.Random("120 snap shift")
    for _ in range(2000):
        x = round(pick.uniform(0, 50), pick.choice((2, 3)))
        steps = pick.randint(0, 400)
        assert edits.snap(x + steps * 0.04) == round(edits.snap(x) + steps * 0.04, 3), (x, steps)


def test_the_last_frame_of_a_shot_and_a_length_the_assistant_asks_are_rounded_as_the_page_rounds_them():
    assert edits.frame_time({"start": 1.48, "dur": 0.42}, "last") == 1.88
    doc = {"clips": [{"id": "c", "assetId": None, "start": 0, "dur": 5, "srcIn": 0}], "prompts": [], "frames": [], "assets": []}
    edits.resize(doc, doc["clips"][0], 0.58)
    assert doc["clips"][0]["dur"] == 0.6


def test_the_assistant_lays_out_a_merged_project_that_dissolves_where_the_page_merges_it():
    cases = json.loads((FIXTURES / "merge_dissolve_cases.json").read_text(encoding="utf-8"))

    for case in cases:
        doc = {"clips": [{**clip, "start": 0} for clip in case["merged"]], "prompts": [], "frames": []}
        edits.relayout(doc)
        assert [clip["start"] for clip in doc["clips"]] == case["starts"]
    assert sum(1 for case in cases if chained(case["merged"])) >= 100


def test_a_project_whose_lengths_sit_on_the_grid_keeps_its_layout_and_after_a_cut_the_next_shot_starts_where_the_one_before_ends():
    pick = random.Random("120 grid layout")
    for _ in range(300):
        durations = [round(pick.randint(5, 100) * 0.04, 2) for _ in range(pick.randint(2, 30))]
        doc = {"clips": [{"id": f"c{index}", "dur": dur} for index, dur in enumerate(durations)]}
        edits.relayout(doc)
        at = 0.0
        for clip, dur in zip(doc["clips"], durations):
            assert clip["start"] == round(at, 2)
            at += dur
    doc = {"clips": [{"id": "a", "dur": 1.02}, {"id": "b1", "dur": 0.84}, {"id": "b2", "dur": 1.56}]}
    edits.relayout(doc)
    assert [clip["start"] for clip in doc["clips"]] == [0, 1.04, 1.88]


@pytest.mark.parametrize("fmt", ("edl", "otio", "fcpxml"))
def test_each_exchange_format_closes_the_gaps_of_the_layout_as_the_video_in_its_golden_file(fmt):
    fixture = json.loads((EXPORTS / "gap-project.json").read_text(encoding="utf-8"))
    files = files_of(fixture["doc"], fixture["takes"], FixtureResolver(fixture["uploads"]), media="name")

    assert render(fmt, fixture["doc"], files).encode("utf-8") == (EXPORTS / f"gap.{fmt}").read_bytes()


@pytest.mark.parametrize("fmt", ("edl", "otio", "fcpxml"))
def test_each_exchange_format_of_a_project_that_only_overlaps_off_the_grid_follows_the_video_in_its_golden_file(fmt):
    fixture = json.loads((EXPORTS / "overlap-project.json").read_text(encoding="utf-8"))
    files = files_of(fixture["doc"], fixture["takes"], FixtureResolver(fixture["uploads"]), media="name")

    assert render(fmt, fixture["doc"], files).encode("utf-8") == (EXPORTS / f"overlap.{fmt}").read_bytes()


def test_the_edl_of_a_project_that_only_overlaps_cuts_on_the_frames_of_the_video_and_reads_the_sources_where_the_video_does():
    fixture = json.loads((EXPORTS / "overlap-project.json").read_text(encoding="utf-8"))
    files = files_of(fixture["doc"], fixture["takes"], FixtureResolver(fixture["uploads"]), media="name")
    doc = fixture["doc"]
    starts, _ = _read_graph(_graph(doc), doc["fps"])

    lines = render("edl", doc, files).split("\r\n")

    assert list(starts.values())[:4] == [0, 25, 61, 85]
    assert "001  VP001    V     C        00:00:00:12 00:00:01:13 00:00:00:00 00:00:01:01" in lines
    assert "004  VP004    V     C        00:00:00:00 00:00:02:01 00:00:03:13 00:00:05:14" in lines
    last = next(part for part in _graph(doc) if part.endswith("[v3]"))
    assert "trim=start=0:" in last and "tpad=start_mode" not in last


def test_the_edl_writes_a_dissolve_as_a_zero_length_cut_then_a_d_event_in_frames():
    fixture, files = _fixture()

    lines = render("edl", fixture["doc"], files).split("\r\n")

    assert "002  VP001    V     C        00:00:04:00 00:00:04:00 00:00:04:00 00:00:04:00" in lines
    assert "002  VP002    V     D    025 00:00:00:10 00:00:02:06 00:00:04:00 00:00:07:17" in lines
    assert "001  VP001    V     C        00:00:00:00 00:00:04:00 00:00:00:00 00:00:04:00" in lines
    assert "* TO CLIP NAME: Les mains du pêcheur" in lines


def test_the_fcpxml_puts_a_declared_cross_dissolve_between_the_clips_it_joins():
    fixture, files = _fixture()

    root = ElementTree.fromstring(render("fcpxml", fixture["doc"], files))
    spine = list(root.iter("spine"))[0]

    assert [child.tag for child in spine] == ["asset-clip", "transition", "asset-clip", "transition", "gap", "transition", "asset-clip"]
    effect = root.find("resources/effect")
    assert all(transition.find("filter-video").get("ref") == effect.get("id") for transition in spine.iter("transition"))
    clips = [child for child in spine if child.tag != "transition"]
    ends = [int(child.get("offset").split("/")[0]) + int(child.get("duration").split("/")[0]) for child in clips]
    assert ends[:-1] == [int(child.get("offset").split("/")[0]) for child in clips[1:]]
    assert ends[-1] == 318


def test_the_otio_reads_with_opentimelineio_and_places_each_clip_at_its_cut():
    otio = pytest.importorskip("opentimelineio")
    fixture, files = _fixture()

    track = otio.adapters.read_from_string(render("otio", fixture["doc"], files), "otio_json").tracks[0]

    transitions = [child for child in track if isinstance(child, otio.schema.Transition)]
    assert [(t.in_offset.value, t.out_offset.value) for t in transitions] == [(12, 13), (6, 7), (18, 19)]
    items = [child for child in track if not isinstance(child, otio.schema.Transition)]
    assert [track.range_of_child(item).start_time.value for item in items] == [0, 112, 198, 248]
    assert track.duration().value == 318


def _solid(folder: Path, name: str, color: str, tone: int, seconds: float, rate: int = 25) -> Path:
    path = folder / name
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r={rate}:d={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ]
    subprocess.run(command, check=True, timeout=60)
    return path


def _frame(path: Path, number: int):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vf", f"select=eq(n\\,{number}),scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    return tuple(subprocess.run(command, capture_output=True, check=True, timeout=60).stdout)


def _frames(path: Path) -> int:
    command = ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)]
    return int(subprocess.run(command, capture_output=True, check=True, text=True, timeout=60).stdout.strip())


def _samples(path: Path):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"]
    return numpy.frombuffer(subprocess.run(command, capture_output=True, check=True, timeout=60).stdout, dtype=numpy.float32)


def _tone(samples, start: float, end: float, frequency: int) -> float:
    window = samples[int(start * 48000) : int(end * 48000)]
    phase = numpy.exp(-2j * math.pi * frequency * numpy.arange(len(window)) / 48000)
    return float(abs(numpy.dot(window, phase)) / len(window))


@pytest.fixture
def solids(tmp_path):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg and ffprobe are not on the PATH")
    return _solid(tmp_path, "red.mp4", "red", 440, 2), _solid(tmp_path, "blue.mp4", "blue", 880, 2), _solid(tmp_path, "lime.mp4", "lime", 1320, 1)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_mixes_both_pictures_halfway_through_the_dissolve_and_keeps_the_sound_in_step(make_doc, solids, tmp_path):
    red, blue, lime = solids
    doc = _run(make_doc, [2, 2, 1], [0, 1, 0], fps=25, resolution="720p")
    files = {clip["id"]: {"name": path.name, "path": str(path)} for clip, path in zip(doc["clips"], solids)}
    output = tmp_path / "mezzanine.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")

    await video.assemble(build_command(doc, files, options, paths), 4.0)

    assert _frames(output) == 100
    probe = core_bridge.probe_video(output)
    assert probe.has_audio and abs(probe.duration - 4.0) < 0.05
    before, middle, after, last = _frame(output, 20), _frame(output, 37), _frame(output, 55), _frame(output, 90)
    assert before[0] > 200 and before[2] < 40 and after[2] > 200 and after[0] < 40
    assert 90 < middle[0] < 170 and 90 < middle[2] < 170 and middle[1] < 40
    assert last[1] > 200 and last[0] < 40
    samples = _samples(output)
    assert len(samples) == pytest.approx(4 * 48000, abs=48000 * 0.03)
    assert _tone(samples, 0.2, 0.8, 440) > 10 * _tone(samples, 0.2, 0.8, 880)
    assert _tone(samples, 2.2, 2.8, 880) > 10 * _tone(samples, 2.2, 2.8, 440)
    assert _tone(samples, 1.4, 1.6, 440) > 0.02 and _tone(samples, 1.4, 1.6, 880) > 0.02
    assert _tone(samples, 3.2, 3.8, 1320) > 10 * _tone(samples, 3.2, 3.8, 880)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_render_delivers_a_film_shortened_by_its_dissolves(make_doc, solids, monkeypatch, export_storage, make_user):
    doc = _run(make_doc, [2, 2, 1], [0, 1, 0], fps=25, resolution="720p")
    shots = {clip["id"]: {"name": path.name, "path": str(path), "still": False} for clip, path in zip(doc["clips"], solids)}
    monkeypatch.setattr(video.media, "local_inputs", lambda doc, found, resolver, folder: (shots, {}))
    monkeypatch.setattr(takes, "list_takes", lambda project_id: [])

    async def save_user_media(user, path):
        return {"value": "uploads/0f0e.mp4", "media_type": "video", "original_filename": Path(path).name, "origin": None, "ref": {"kind": "library", "item_id": "item-1"}}

    monkeypatch.setattr(core_bridge, "save_user_media", save_user_media)
    user = make_user()
    job = {"id": "job-1", "user_id": "user-1", "format": "web", "resolution": "720p"}

    result = await video.render(job, {"id": "p-1", "name": "Fondu", "doc": doc}, user, user, lambda progress, step: True)

    final = export_storage / "video_producer" / "exports" / "user-1" / "job-1" / result["file_name"]
    assert _frames(final) == 100
    middle = _frame(final, 37)
    assert 90 < middle[0] < 170 and 90 < middle[2] < 170


def _offsets(graph):
    found = []
    for part in graph:
        if "xfade=" in part:
            fields = dict(item.split("=", 1) for item in part.split("xfade=", 1)[1].split("[", 1)[0].split(":")[1:])
            found.append((float(fields["duration"]), float(fields["offset"])))
    return found


_LABEL = re.compile(r"\[([^\]]+)\]")


def _read_graph(graph, rate):
    lengths, joined = {}, {}
    for part in graph:
        labels = _LABEL.findall(part)
        if not labels or not re.fullmatch(r"v\d+", labels[-1]):
            if "xfade=" in part:
                fields = dict(item.split("=", 1) for item in part.split("xfade=", 1)[1].split("[", 1)[0].split(":")[1:])
                run, index = re.fullmatch(r"x(\d+)v(\d+)", labels[-1]).groups()
                joined.setdefault(int(run), []).append((int(index), float(fields["offset"])))
            continue
        body = part[: part.rindex("[")]
        length = body.split(":d=", 1)[1].split(",", 1)[0] if body.startswith("color=") else body.rsplit("trim=duration=", 1)[1].split(",", 1)[0]
        lengths[int(labels[-1][1:])] = float(length)
    final = next(part for part in graph if "concat=n=" in part)
    pieces = _LABEL.findall(final.split("concat=", 1)[0])[0::2]
    at, starts = 0.0, {}
    for piece in pieces:
        match = re.fullmatch(r"x(\d+)v(\d+)", piece)
        if match is None:
            index = int(piece[1:])
            starts[index] = at
            at += lengths[index]
            continue
        run = int(match.group(1))
        starts[run] = at
        for index, offset in joined[run]:
            starts[index] = at + offset
        last, offset = joined[run][-1]
        at += offset + lengths[last]
    return {index: round(start * rate) for index, start in starts.items()}, round(at * rate)


def _assert_on_time(doc, files=None):
    rate = doc["fps"]
    graph = _graph(doc, files)
    starts, end = _read_graph(graph, rate)
    segments, _ = timeline(doc)
    shots = {clip["id"]: starts[index] for index, (_, clip) in enumerate(segments) if clip is not None}
    for clip in doc["clips"]:
        if clip["id"] in shots:
            assert shots[clip["id"]] == frames_of(clip["start"], rate), (rate, clip["id"], shots[clip["id"]], clip["start"])
    assert end == frames_of(max(1, *(round(clip["start"] + clip["dur"], 6) for clip in doc["clips"])), rate), rate
    chains = {_LABEL.findall(part)[-1]: part for part in graph if _LABEL.findall(part) and re.fullmatch(r"v\d+", _LABEL.findall(part)[-1])}
    for index, (_, clip) in enumerate(segments):
        if clip is not None and clip.get(video.JOIN):
            assert "fade=t=in" not in chains[f"v{index}"] and "fade=t=out" not in chains[f"v{index - 1}"], (rate, clip["id"])
    return graph


@pytest.mark.parametrize("fps", CADENCES)
def test_at_every_cadence_each_shot_of_the_graph_starts_on_the_frame_of_its_time_in_the_document(make_doc, fps):
    doc = _run(make_doc, [2] * 11, [0] + [0.4] * 10, fps=fps)
    graph = _graph(doc)
    _, total = timeline(doc)

    assert total == pytest.approx(18)
    _assert_on_time(doc)
    starts = [clip["start"] for clip in doc["clips"]]
    assert [round(offset * fps) for _, offset in _offsets(graph)] == [frames_of(start, fps) for start in starts[1:]]
    assert [round(duration * fps) for duration, _ in _offsets(graph)] == [frames_of(start + 0.4, fps) - frames_of(start, fps) for start in starts[1:]]


@pytest.mark.parametrize("fps", CADENCES)
def test_after_a_shot_of_3_1_s_the_dissolve_keeps_its_length_and_the_shots_follow_end_to_end_at_every_cadence(make_doc, fps):
    doc = _run(make_doc, [3.1, 4, 2], [0, 1, 0], fps=fps)

    assert [clip["start"] for clip in doc["clips"]] == [0, 2.1, 6.1]
    assert joins(doc["clips"]) == [0, 1, 0]
    assert len(_offsets(_graph(doc))) == 1
    _assert_on_time(doc)


@pytest.mark.parametrize("fps", CADENCES)
def test_the_shots_of_a_run_last_the_frames_between_their_own_times_so_nothing_drifts(make_doc, fps):
    doc = _run(make_doc, [1.06] * 30, [0] + [0.4] * 29, fps=fps)
    segments, _ = timeline(doc)

    lengths = [frames_of(dur, fps) for dur, _ in segments]
    expected = [frames_of(clip["start"] + clip["dur"], fps) - frames_of(clip["start"], fps) for clip in doc["clips"]]
    assert lengths == expected
    sounds = [part.split("atrim=duration=")[1].split("[")[0] for part in _graph(doc) if part.startswith("anullsrc")]
    assert [round(float(dur) * fps) for dur in sounds] == expected
    _assert_on_time(doc)


def test_two_dissolves_around_a_short_shot_meet_when_it_has_no_frame_of_its_own(make_doc):
    doc = _run(make_doc, [4, 0.96, 4], [0, 1, 1], fps=24)

    assert [clip["start"] for clip in doc["clips"]] == [0, 3.52, 4]
    assert [round(d * 24) for d, _ in _offsets(_graph(doc))] == [12, 12]
    _assert_on_time(doc)


@pytest.mark.parametrize("first", (1.01, 1.02, 1.03, 2.98, 3.1, 4.06))
@pytest.mark.parametrize("fps", CADENCES)
def test_the_two_dissolves_of_a_short_shot_never_overlap_after_shots_off_the_grid(make_doc, first, fps):
    doc = _run(make_doc, [first, 0.96, 4, 1.07, 0.5], [0, 1, 1, 2, 1], fps=fps)
    files = {("clips", index): {"name": f"{index}.mp4", "path": f"{index}.mp4"} for index in range(len(doc["clips"]))}
    clips = doc["clips"]

    for before, shot, after in zip(clips, clips[1:], clips[2:]):
        assert before["start"] + before["dur"] <= after["start"] + 1e-9, (before["id"], after["id"])
        assert frames_of(before["start"] + before["dur"], fps) <= frames_of(after["start"], fps)
    edits_of = cuts(clips, lambda s: js_round(s * fps))
    for cut_of in edits_of:
        assert cut_of is not None and cut_of.end - cut_of.start >= 0
    for before, after in zip(edits_of, edits_of[1:]):
        if before.overlap and after.overlap:
            assert after.start - after.head >= before.start - before.head + before.overlap
    for line in render("edl", doc, files).split("\r\n"):
        if re.match(r"\d{3}  VP", line):
            fields = line.split()
            assert fields[-1] >= fields[-2], line
    _assert_on_time(doc)


@pytest.mark.parametrize("fps", CADENCES)
@pytest.mark.parametrize("first", (2, 1.019, 3.1, 0.97))
@pytest.mark.parametrize("durations", ([3.1, 2, 2, 2], [1.02] * 12, [1.01, 2.03, 0.97, 3.1, 1.06, 2.99, 1.02]), ids=("3.1 s", "1.02 s", "mixed"))
def test_cuts_after_a_dissolve_leave_no_black_lose_no_frame_and_do_not_drift(make_doc, fps, first, durations):
    asks = [0, 1, *([0] * (len(durations) - 1))]
    asks[len(asks) // 2] = 0.6
    doc = _run(make_doc, [first, *durations], asks, fps=fps)
    clips = doc["clips"]
    segments, _ = timeline(doc)

    assert [clip is not None for _, clip in segments] == [True] * len(clips)
    assert all(not moved(clip, place) for clip, place in zip(clips, placement(clips)))
    for before, clip in zip(clips, clips[1:]):
        assert clip["start"] == round(before["start"] + before["dur"] - dissolve_of(before, clip), 6)
    expected = sum(clip["dur"] for clip in clips) - sum(dissolve_of(before, clip) for before, clip in zip(clips, clips[1:]))
    assert clips[-1]["start"] + clips[-1]["dur"] == pytest.approx(expected, abs=1e-5)
    _assert_on_time(doc)


def test_forty_dissolves_of_0_4_s_on_shots_of_1_01_s_end_the_film_at_24_8_s(make_doc):
    doc = _run(make_doc, [1.01] * 40, [0] + [0.4] * 39, fps=24)
    clips = doc["clips"]

    assert clips[-1]["start"] + clips[-1]["dur"] == pytest.approx(24.8, abs=1e-6)
    assert set(joins(clips)[1:]) == {0.4}
    assert timeline(doc)[1] == pytest.approx(24.8, abs=1e-6)
    _assert_on_time(doc)


@pytest.mark.parametrize("seed", range(4))
def test_a_long_run_drawn_at_random_ends_at_the_sum_of_its_lengths_less_its_dissolves(make_doc, seed):
    rng = random.Random(seed)
    durations = [round(rng.uniform(0.16, 6), 2) for _ in range(200)]
    asks = [0, *(rng.choice([0, 0, 0.4, 0.6, 1, 1.2, 2, round(rng.uniform(0.08, 2), 2)]) for _ in range(199))]
    doc = _run(make_doc, durations, asks, fps=rng.choice(CADENCES))
    clips = doc["clips"]

    expected = sum(durations) - sum(dissolve_of(before, clip) for before, clip in zip(clips, clips[1:]))
    assert clips[-1]["start"] + clips[-1]["dur"] == pytest.approx(expected, abs=1e-4)
    assert sum(joins(clips)) == pytest.approx(sum(dissolve_of(before, clip) for before, clip in zip(clips, clips[1:])), abs=1e-4)
    _assert_on_time(doc)


def test_the_edl_ends_a_cut_on_the_frame_the_next_shot_starts_on_as_the_video_does(make_doc):
    doc = _run(make_doc, [1.4, 1.53, 2], [0, 0.4, 0], fps=50)
    files = {("clips", index): {"name": f"{index}.mp4", "path": f"{index}.mp4"} for index in range(3)}

    assert [clip["start"] for clip in doc["clips"]] == [0, 1, 2.53]
    events = [line.split() for line in render("edl", doc, files).split("\r\n") if re.match(r"\d{3}  VP", line)]
    assert events[-2][-1] == events[-1][-2] == "00:00:02:26"
    _assert_on_time(doc)


def test_in_a_project_that_dissolves_a_first_frame_sits_on_the_exact_start_of_its_shot(make_doc):
    doc = _run(make_doc, [2.539, 2, 2], [0, 1, 0], fps=24)
    clip = doc["clips"][2]

    edits.place_frame(doc, clip, "first", "image")

    assert clip["start"] == 3.539
    assert [frame["time"] for frame in doc["frames"]] == [3.539]
    legacy = _run(make_doc, [2.539, 2], [0, 0], fps=24)
    edits.place_frame(legacy, legacy["clips"][1], "first", "image")
    assert [frame["time"] for frame in legacy["frames"]] == [edits.snap(legacy["clips"][1]["start"])]


HAND = [
    {"fps": 24, "durations": [3.1, 4, 2], "asks": [0, 1, 0], "starts": [0, 2.1, 6.1], "joins": [0, 1, 0], "frames": [0, 50, 146], "total": 194, "bare": []},
    {"fps": 30, "durations": [2, 2, 2, 2], "asks": [0, 0.4, 0.4, 0.4], "starts": [0, 1.6, 3.2, 4.8], "joins": [0, 0.4, 0.4, 0.4], "frames": [0, 48, 96, 144], "total": 204, "bare": []},
    {"fps": 25, "durations": [2, 2, 1.6, 2], "asks": [0, 1, 0.6, 1], "gap": 1, "speed": 2, "starts": [0, 1, 2.4, 4.2], "joins": [0, 1, 0.6, 0], "frames": [0, 25, 60, 105], "total": 155, "bare": [1]},
    {"fps": 48, "durations": [4, 0.96, 4], "asks": [0, 1, 1], "starts": [0, 3.52, 4], "joins": [0, 0.48, 0.48], "frames": [0, 169, 192], "total": 384, "bare": []},
]


@pytest.mark.parametrize("case", HAND, ids=[f"{case['fps']} fps, {len(case['durations'])} shots" for case in HAND])
def test_documents_written_by_hand_play_each_shot_on_the_frame_counted_by_hand(make_doc, case):
    doc = _run(make_doc, case["durations"], case["asks"], fps=case["fps"])
    if case.get("gap"):
        doc["clips"][-1]["start"] = round(doc["clips"][-1]["start"] + case["gap"], 6)
    if "speed" in case:
        doc["clips"][case["speed"]]["speed"] = 0.5
    files = {clip["id"]: {"name": f"{clip['id']}.mp4", "path": f"/media/{clip['id']}.mp4"} for index, clip in enumerate(doc["clips"]) if index not in case["bare"]}
    graph = _graph(doc, files)

    assert [clip["start"] for clip in doc["clips"]] == case["starts"]
    assert joins(doc["clips"]) == case["joins"]
    starts, end = _read_graph(graph, case["fps"])
    segments, _ = timeline(doc)
    assert [starts[index] for index, (_, clip) in enumerate(segments) if clip is not None] == case["frames"]
    assert end == case["total"]


@pytest.mark.parametrize("fps", CADENCES)
def test_changing_the_cadence_after_choosing_a_dissolve_keeps_it_and_its_place(make_doc, fps):
    doc = _run(make_doc, [2, 2.4, 3], [0, 1, 0.6], fps=25)
    starts = [clip["start"] for clip in doc["clips"]]

    doc["fps"] = fps

    assert joins(doc["clips"]) == [0, 1, 0.6]
    edits.relayout(doc)
    assert [clip["start"] for clip in doc["clips"]] == starts
    assert len(_offsets(_graph(doc))) == 2
    _assert_on_time(doc)


@pytest.mark.parametrize("fps", (24, 48))
def test_at_24_and_48_fps_the_prompts_and_frames_linked_to_a_shot_stay_on_its_start(make_doc, fps):
    doc = _run(make_doc, [2, 2, 2, 2], [0, 0, 0, 0], fps=fps)
    doc["prompts"] = [{"id": f"p{index}", "shotId": clip["id"], "start": clip["start"], "dur": clip["dur"], "strength": 75, "text": "x"} for index, clip in enumerate(doc["clips"])]
    doc["frames"] = [{"id": f"f{index}", "shotId": clip["id"], "time": clip["start"], "assetId": None, "role": "First frame", "strength": 75} for index, clip in enumerate(doc["clips"])]
    for clip, ask in zip(doc["clips"][1:], (0.4, 1, 0.6)):
        clip["dissolve"] = ask

    edits.relayout(doc)

    starts = [clip["start"] for clip in doc["clips"]]
    assert starts == [0, 1.6, 2.6, 4]
    assert [prompt["start"] for prompt in doc["prompts"]] == starts
    assert [frame["time"] for frame in doc["frames"]] == starts


def test_the_seeded_documents_of_the_property_test_are_what_the_server_makes_of_them():
    assert dissolve_property.make() == PROPERTY


@pytest.mark.parametrize("index", range(len(PROPERTY["docs"])))
def test_seeded_documents_play_each_shot_on_the_frame_of_its_time_at_every_cadence(make_doc, index):
    case = PROPERTY["docs"][index]
    doc = _doc(make_doc, [{"id": f"c{k}", "assetId": f"a{k}", "start": start, **clip} for k, (clip, start) in enumerate(zip(case["clips"], case["starts"]))])
    clips = doc["clips"]
    files = {clip["id"]: {"name": f"{clip['id']}.mp4", "path": f"/media/{clip['id']}.mp4"} for k, clip in enumerate(clips) if k not in case["bare"]}

    shifted = {int(key) for key in case["gaps"]}
    assert all(join > 0 for k, (join, before, clip) in enumerate(zip(case["joins"][1:], clips, clips[1:]), 1) if dissolve_of(before, clip) and k not in shifted)
    for k, (before, after) in enumerate(zip(clips, clips[2:])):
        if case["joins"][k + 1] and case["joins"][k + 2]:
            assert before["start"] + before["dur"] <= after["start"] + 1e-6
    for fps in PROPERTY["fps"]:
        doc["fps"] = fps
        if any(case["joins"]):
            _assert_on_time(doc, files)
        assert len(_offsets(_graph(doc, files))) == sum(1 for join in case["joins"] if join)


def test_a_document_shows_the_dissolve_its_starts_overlap_and_a_bare_overlap_cuts_at_the_later_start(make_doc):
    doc = _doc(make_doc, [{"id": "a", "assetId": "x", "start": 0, "dur": 4}, {"id": "b", "assetId": "y", "start": 4, "dur": 4, "dissolve": 1}], fps=25)
    files = {("clips", 0): {"name": "a.mp4", "path": "a.mp4"}, ("clips", 1): {"name": "b.mp4", "path": "b.mp4"}}
    assert joins(doc["clips"]) == [0, 0] and not any("xfade" in part for part in _graph(doc))
    assert " D " not in render("edl", doc, files) and "Transition" not in render("otio", doc, files) and "<transition" not in render("fcpxml", doc, files)

    doc["clips"][1]["start"] = 3.8

    assert joins(doc["clips"]) == [0, 0.2]
    assert _offsets(_graph(doc)) == [(0.2, 3.8)]
    assert "002  VP002    V     D    005 00:00:00:00 00:00:04:00 00:00:03:20 00:00:07:20" in render("edl", doc, files).split("\r\n")
    _assert_on_time(doc)

    doc["clips"].append({**doc["clips"][1], "id": "c", "assetId": "z", "start": 7, "dur": 2})
    del doc["clips"][2]["dissolve"]
    files[("clips", 2)] = {"name": "c.mp4", "path": "c.mp4"}

    assert [(place.start, place.end) for place in placement(doc["clips"])] == [(0, 4), (3.8, 7), (7, 9)]
    assert [round(dur * 25) for dur, _ in timeline(doc)[0]] == [100, 80, 50]
    assert "002  VP002    V     D    005 00:00:00:00 00:00:03:05 00:00:03:20 00:00:07:00" in render("edl", doc, files).split("\r\n")
    _assert_on_time(doc)


def test_the_otio_writes_each_dissolve_as_a_transition_between_clips_cut_at_its_middle():
    fixture, files = _fixture()

    children = json.loads(render("otio", fixture["doc"], files))["tracks"]["children"][0]["children"]

    assert [child["OTIO_SCHEMA"] for child in children] == ["Clip.2", "Transition.1", "Clip.2", "Transition.1", "Gap.1", "Transition.1", "Clip.2"]
    transitions = [child for child in children if child["OTIO_SCHEMA"] == "Transition.1"]
    assert [(t["transition_type"], t["in_offset"]["value"], t["out_offset"]["value"]) for t in transitions] == [("SMPTE_Dissolve", 12, 13), ("SMPTE_Dissolve", 6, 7), ("SMPTE_Dissolve", 18, 19)]
    items = [child for child in children if child["OTIO_SCHEMA"] != "Transition.1"]
    assert [item["source_range"]["duration"]["value"] for item in items] == [112, 86, 50, 70]
    assert [item["source_range"]["start_time"]["value"] for item in items] == [0, 16, 0, 24]


def test_the_assistant_hears_the_length_of_the_film_less_its_dissolves_and_nothing_else():
    from backend.chat import context

    shots = [{"id": "a", "start": 0, "dur": 4}, {"id": "b", "start": 3, "dur": 4, "dissolve": 1}, {"id": "c", "start": 7, "dur": 2}]
    labels = {"a": "A", "b": "B", "c": "C"}

    assert context._shots(shots, labels, 4000)[0] == "Shots (3, 9 s), in timeline order:"
    assert context._shots([{**shot, "dissolve": 0} for shot in shots], labels, 4000)[0] == "Shots (3, 10 s), in timeline order:"
    assert [context._shot_at(shots, time)["id"] for time in (3.2, 3.5, 4)] == ["a", "b", "b"]


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_at_24_fps_lasts_the_frames_the_document_lays_out_with_its_sound_in_step(make_doc, tmp_path):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg and ffprobe are not on the PATH")
    sources = [_solid(tmp_path, f"{color}.mp4", color, tone, 2, 24) for color, tone in (("red", 440), ("blue", 880), ("lime", 1320))]
    doc = _run(make_doc, [2, 2, 1], [0, 0.4, 0], fps=24, resolution="720p")
    assert [clip["start"] for clip in doc["clips"]] == [0, 1.6, 3.6]
    files = {clip["id"]: {"name": path.name, "path": str(path)} for clip, path in zip(doc["clips"], sources)}
    output = tmp_path / "mezzanine.mkv"
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")
    _, total = timeline(doc)

    await video.assemble(build_command(doc, files, options, paths), total)

    assert total == pytest.approx(4.6) and _frames(output) == 110
    middle = _frame(output, 43)
    assert 90 < middle[0] < 170 and 90 < middle[2] < 170
    assert _frame(output, 37)[0] > 200 and _frame(output, 49)[2] > 200
    assert _frame(output, 85)[2] > 200 and _frame(output, 86)[1] > 200 and _frame(output, 86)[2] < 60
    samples = _samples(output)
    assert len(samples) == pytest.approx(110 / 24 * 48000, abs=48000 * 0.01)
    assert _tone(samples, 4.0, 4.5, 1320) > 10 * _tone(samples, 4.0, 4.5, 880)


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_in_parts_keeps_the_dissolve_between_two_parts(make_doc, tmp_path, monkeypatch):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg and ffprobe are not on the PATH")
    colors = (("red", 440), ("blue", 880), ("lime", 1320), ("yellow", 660))
    sources = [_solid(tmp_path, f"{color}.mp4", color, tone, 1) for color, tone in colors]
    doc = _run(make_doc, [1, 1, 1, 1], [0, 0.4, 0.4, 0.4], fps=25, resolution="720p")
    files = {clip["id"]: {"name": path.name, "path": str(path), "still": False} for clip, path in zip(doc["clips"], sources)}
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    output = tmp_path / "mezzanine.mkv"
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    monkeypatch.setattr(video, "PART_INPUTS", 2)

    await video.assemble_sequence(doc, files, options, paths, tmp_path, lambda progress, step: True)

    assert (tmp_path / video.PART_NAME.format(0, 1)).exists() and _frames(output) == 70
    boundary = _frame(output, 35)
    assert 90 < boundary[2] < 170 and 90 < boundary[1] < 200 and boundary[0] < 60
    assert _frame(output, 26)[2] > 200 and _frame(output, 44)[1] > 200


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_export_in_parts_at_24_fps_joins_the_parts_on_the_frames_of_the_document(make_doc, tmp_path, monkeypatch):
    colors = (("red", 440), ("blue", 880), ("lime", 1320), ("yellow", 660))
    sources = [_solid(tmp_path, f"{color}.mp4", color, tone, 2, 24) for color, tone in colors]
    doc = _run(make_doc, [1.1, 1.3, 0.9, 1.22], [0, 0.4, 0.4, 0.4], fps=24, resolution="720p")
    files = {clip["id"]: {"name": path.name, "path": str(path), "still": False} for clip, path in zip(doc["clips"], sources)}
    options = {"format": "web", "resolution": "720p", **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    output = tmp_path / "mezzanine.mkv"
    paths = {"ffmpeg": shutil.which("ffmpeg"), "graph_option": video.graph_option(shutil.which("ffmpeg")), "output": str(output), "graph": str(tmp_path / "graph.txt"), "audio": {}}
    monkeypatch.setattr(video, "PART_INPUTS", 2)
    places = placement(doc["clips"])
    _, total = timeline(doc)

    await video.assemble_sequence(doc, files, options, paths, tmp_path, lambda progress, step: True)

    first, second = (tmp_path / video.PART_NAME.format(0, k) for k in (0, 1))
    assert _frames(first) == frames_of(places[1].end, 24)
    assert _frames(second) == frames_of(places[3].end, 24) - frames_of(places[2].start, 24)
    assert _frames(output) == frames_of(total, 24)
    start, end = frames_of(places[2].start, 24), frames_of(places[1].end, 24)
    assert _frame(output, start - 1)[2] > 200 and _frame(output, start - 1)[1] < 60
    middle = _frame(output, (start + end) // 2)
    assert 60 < middle[2] < 200 and 60 < middle[1] < 220
    assert _frame(output, end)[1] > 200 and _frame(output, end)[2] < 60
    last = frames_of(places[3].start, 24)
    assert _frame(output, last - 1)[1] > 200 and _frame(output, last - 1)[0] < 60
    assert _frame(output, frames_of(total, 24) - 1)[0] > 200 and _frame(output, frames_of(total, 24) - 1)[1] > 200


def test_the_server_rounds_a_tie_to_the_millionth_away_from_zero_as_the_page_does():
    assert round(2.0078125, 6) == 2.007812
    assert [rounded(value) for value in (2.0078125, 0.0234375, -2.0078125, 1.5, 10 / 3, 1.048)] == [2.007813, 0.023438, -2.007813, 1.5, 3.333333, 1.048]
    doc = {"clips": [{"id": "a", "dur": 3.0078125}, {"id": "b", "dur": 2.0234375, "dissolve": 1}], "prompts": [], "frames": []}
    edits.relayout(doc)
    assert [clip["start"] for clip in doc["clips"]] == [0, 2.007813]
    assert [doc for doc in PROPERTY["docs"] if doc["clips"][0]["dur"] == 3.0078125][0]["laid"][:2] == [0, 2.007813]


def test_the_export_never_plays_a_dissolve_longer_than_the_rule(make_doc):
    alone = _doc(make_doc, [{"id": "a", "assetId": "x", "start": 0, "dur": 150}, {"id": "b", "assetId": "y", "start": 80, "dur": 150, "dissolve": 0.08}], fps=25)
    plain = _doc(make_doc, [{"id": "a", "assetId": "x", "start": 0, "dur": 150}, {"id": "b", "assetId": "y", "start": 80, "dur": 150}], fps=25)
    assert joins(alone["clips"]) == [0, 0]
    assert not any("xfade" in part for part in _graph(alone))
    assert _graph(alone) == _graph(plain)
    segments = lambda doc: ([(dur, clip and clip["id"]) for dur, clip in timeline(doc)[0]], timeline(doc)[1])
    assert segments(alone) == segments(plain) == ([(80, "a"), (150, "b")], 230)

    run = _doc(make_doc, [{"id": "a", "assetId": "x", "start": 0, "dur": 4}, {"id": "b", "assetId": "y", "start": 3, "dur": 4, "dissolve": 1}, {"id": "c", "assetId": "z", "start": 5.5, "dur": 4, "dissolve": 1}], fps=25)
    assert joins(run["clips"]) == [0, 1, 0]
    assert [(place.start, place.end) for place in placement(run["clips"])] == [(0, 4), (3, 5.5), (5.5, 9.5)]
    graph = ";".join(_graph(run))
    assert graph.count("xfade=") == 1 and "xfade=transition=fade:duration=1:" in graph
    run["clips"][2]["start"] = 6.4
    assert joins(run["clips"]) == [0, 1, 0.6]
    run["clips"][2]["start"] = 6
    assert joins(run["clips"]) == [0, 1, 1]


def test_the_assistant_measures_the_dissolves_on_the_exact_times_the_page_sends():
    shots = [{"id": "a", "start": 0, "dur": 1.048}, {"id": "b", "start": 0.528, "dur": 1.226, "dissolve": 1}, {"id": "c", "start": 1.554, "dur": 0.411, "dissolve": 1}]
    assert joins(shots) == [0, 0.52, 0.2]
    hundredths = [{**shot, "start": round(shot["start"], 2), "dur": round(shot["dur"], 2)} for shot in shots]
    assert joins(hundredths) == [0, 0.52, 0]
    page = {"projectId": "p1", "name": "Ties", "shots": [{**shot, "label": shot["id"], "stage": "todo"} for shot in shots]}
    text = context.build_context({"video_producer": page}, None, "u1")
    assert f"Shots (3, {round(1.048 + 1.226 + 0.411 - 0.72, 2):g} s)" in text


def test_a_huge_length_the_schema_accepts_never_breaks_the_rounding_nor_the_assistant():
    assert [rounded(value) for value in (1e22, -1e30, 1e15, 123456789.1234565)] == [1e22, -1e30, 1e15, 123456789.123456]
    shots = [{"id": "a", "label": "a", "stage": "todo", "start": 0, "dur": 1e22}, {"id": "b", "label": "b", "stage": "todo", "start": 1e22, "dur": 4, "dissolve": 1}]
    assert joins(shots) == [0, 0]
    assert "Shots (2," in context.build_context({"video_producer": {"projectId": "p1", "name": "Huge", "shots": shots}}, None, "u1")
