import asyncio
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from backend import cadence, final_pass, formats, generation, presets, projects, renditions, takes
from backend.chat import edits
from backend.exports import render
from backend.exports.video import filter_graph

from .test_cadence import _drafts, _media, _tick
from .test_renditions import placed

CASES = json.loads((Path(__file__).parent / "fixtures" / "speed_migration.json").read_text(encoding="utf-8"))
PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt", "audio": {}}
BASE = "/api/plugins/video-producer"


def _slow(project, shot_id, speed):
    doc = projects.get_project(project["id"])["doc"]
    doc["clips"] = [{**clip, "speed": speed} if clip["id"] == shot_id else clip for clip in doc["clips"]]
    stored = projects.get_project(project["id"])
    projects.save_project(project["id"], doc, stored["version"])
    return projects.get_project(project["id"])


def _shot(project, shot_id):
    return renditions.shot_of(project, shot_id)


def test_the_speeds_come_from_the_formats_table():
    assert formats.SPEEDS == (1.0, 0.5, 0.25)
    assert formats.SLOW_SPEEDS == (0.5, 0.25)
    assert [formats.speed_of(clip) for clip in ({}, {"speed": 0.5}, {"speed": 0.25}, {"speed": 0.75}, {"speed": True}, None)] == [1.0, 0.5, 0.25, 1.0, 1.0, 1.0]


def test_the_speed_of_a_shot_is_kept_only_when_it_is_a_slow_speed_of_the_table(make_doc):
    for case in CASES:
        doc = make_doc(clips=[{"id": "s1", "start": 0, "dur": 4, "speed": case["value"]}])
        migrated = projects.migrate(doc)["clips"][0]
        assert migrated.get("speed") == case["expected"]
        assert ("speed" in migrated) == (case["expected"] is not None)
        projects.validate_doc(projects.migrate(doc))
    with pytest.raises(projects.DocError):
        projects.validate_doc(make_doc(clips=[{"id": "s1", "start": 0, "dur": 4, "speed": 0.75}]))


@pytest.mark.parametrize(
    "film, speed, take_fps, needed",
    [
        (25, None, 16, 25.0),
        (25, None, 25, None),
        (25, 0.5, 16, 50.0),
        (25, 0.5, 25, 50.0),
        (25, 0.5, 50, None),
        (25, 0.25, 16, 100.0),
        (24, 0.5, 24, 48.0),
        (60, 0.25, 24, 240.0),
        (23.976, 0.5, 16, None),
    ],
)
def test_a_slowed_shot_needs_the_film_s_frame_rate_divided_by_its_speed(film, speed, take_fps, needed):
    clip = {"id": "s1"} if speed is None else {"id": "s1", "speed": speed}
    assert cadence.needed_fps({"fps": film}, clip, take_fps) == needed


@pytest.mark.parametrize(
    "take_fps, fps, film, steps",
    [
        (16, 25, 25, [(25.0, None)]),
        (16, 50, 25, [(50.0, None)]),
        (24, 48, 24, [(48.0, None)]),
        (25, 100, 25, [(100.0, 4)]),
        (16, 100, 25, [(25.0, None), (100.0, 4)]),
        (24, 96, 48, [(48.0, None), (96.0, 2)]),
        (48, 96, 48, [(96.0, 2)]),
        (24, 240, 60, [(60.0, None), (240.0, 4)]),
    ],
)
def test_past_60_fps_a_version_is_a_multiple_of_the_film_s_rate_made_from_the_take_or_its_version_at_that_rate(take_fps, fps, film, steps):
    assert cadence.passes(take_fps, fps, film) == steps


def test_a_rate_that_is_no_multiple_the_interpolators_make_is_refused():
    with pytest.raises(ValueError):
        cadence.passes(16, 75, 25)


def test_a_multiplier_request_sends_no_target_frame_rate(core, make_project):
    core.use_wan()
    core.use_video_tools()
    _, drafts = _drafts(core, make_project)

    request, _ = cadence.build_request(core.users["user-1"], drafts[0], 100, "rife", 4)

    assert (request["form_data"]["target_fps"], request["form_data"]["factor"]) == (0, 4)


def test_a_shot_slowed_to_half_speed_gets_one_version_at_twice_the_film_s_rate(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    project = _slow(project, "s1", 0.5)

    rendition = renditions.order(core.users["user-1"], project, drafts[0], None, _shot(project, "s1"))

    assert (rendition["fps"], rendition["factor"], rendition["source_rendition_id"], rendition["status"]) == (50.0, None, None, "queued")
    assert rendition["request"]["form_data"]["target_fps"] == 50
    assert renditions.list_for_take(drafts[0]["id"]) == [renditions.get(rendition["id"])]


def test_a_shot_slowed_to_a_quarter_gets_the_version_at_the_film_s_rate_then_four_times_it(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    project = _slow(project, "s1", 0.25)
    owner = core.users["user-1"]

    slow = renditions.order(owner, project, drafts[0], None, _shot(project, "s1"))
    base = renditions.get(slow["source_rendition_id"])

    assert (base["fps"], base["factor"], base["status"]) == (25.0, None, "queued")
    assert (slow["fps"], slow["factor"], slow["status"], slow["request"]) == (100.0, 4, "waiting", None)

    _tick()
    generation_id = renditions.get(base["id"])["generation_id"]
    core.complete(generation_id, fps=25.0)
    _media(core, generation_id)
    _tick()

    ready = renditions.get(slow["id"])
    assert ready["status"] in ("queued", "running")
    assert ready["request"]["form_data"]["input_video"] == f"generations/x/{generation_id}.mp4"
    assert (ready["request"]["form_data"]["target_fps"], ready["request"]["form_data"]["factor"]) == (0, 4)


def test_the_slow_version_is_cancelled_when_the_version_it_was_made_from_fails(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    project = _slow(project, "s1", 0.25)

    slow = renditions.order(core.users["user-1"], project, drafts[0], None, _shot(project, "s1"))
    _tick()
    core.fail(renditions.get(slow["source_rendition_id"])["generation_id"])
    _tick()

    ended = renditions.get(slow["id"])
    assert (ended["status"], ended["error_code"]) == ("cancelled", "source_ended")


def test_a_take_already_at_the_film_s_rate_is_multiplied_in_one_pass(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project, fps=25.0)
    project = _slow(project, "s1", 0.25)

    slow = renditions.order(core.users["user-1"], project, drafts[0], None, _shot(project, "s1"))

    assert (slow["fps"], slow["factor"], slow["source_rendition_id"], slow["status"]) == (100.0, 4, None, "queued")


def test_each_shot_reads_the_version_at_the_rate_it_needs(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    project = _slow(project, "s2", 0.5)
    owner = core.users["user-1"]
    project = placed(project, drafts)
    conform = renditions.order(owner, project, drafts[0], None, _shot(project, "s1"))
    slowed = renditions.order(owner, project, drafts[1], None, _shot(project, "s2"))
    _tick()
    for item in (conform, slowed):
        core.complete(renditions.get(item["id"])["generation_id"])
    _tick()

    found = renditions.shot_versions(project["id"], project["doc"], takes.list_takes(project["id"]))

    assert {shot: (version["take_id"], version["fps"]) for shot, version in found.items()} == {
        "s1": (drafts[0]["id"], 25.0),
        "s2": (drafts[1]["id"], 50.0),
    }


def test_the_final_pass_counts_the_slowed_shots_among_those_it_brings_to_their_rate(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    project = _slow(project, "s2", 0.5)
    order = final_pass.Order(takes=[take["id"] for take in drafts], method="upscale", target="fhd1080", conform=True)
    owner = core.users["user-1"]

    evaluation = asyncio.run(final_pass.evaluate(owner, project, order, drafts))
    created = asyncio.run(final_pass.start(owner, project, evaluation))

    assert (evaluation.payload["cadence"]["shots"], evaluation.payload["cadence"]["slowed"]) == (["s1", "s2"], ["s2"])
    assert [[item["fps"] for item in renditions.list_for_take(take["id"])] for take in created] == [[25.0], [50.0]]


def test_a_slowed_shot_reads_the_seconds_of_source_its_speed_covers_and_drops_its_take_s_sound(make_doc):
    doc = make_doc(clips=[{"id": "c1", "start": 0, "dur": 4, "srcIn": 0.5, "speed": 0.5}], aspect="16:9")
    doc["fps"] = 25
    files = {"c1": {"name": "1.mp4", "path": "/media/1.mp4"}}
    options = {"format": "web", "resolution": "720p", "audio": {"c1": True}, "stills": [], "impulse": "/tmp/out/reverb.wav", "lengths": {"c1": 2.0}}

    graph = filter_graph(doc, files, options, PATHS).split(";")

    assert graph[0].startswith("[0:v]trim=start=0.5:duration=2,setpts=(PTS-STARTPTS)/0.5,fps=25,")
    assert ",tpad=stop_mode=clone:stop_duration=1.04,trim=duration=4" in graph[0]
    assert graph[1].startswith("anullsrc=")


def test_the_exchange_files_carry_the_speed_of_a_slowed_shot(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 4, "srcIn": 1, "speed": 0.5}], assets=[{"id": "a1", "kind": "video", "name": "x", "srcDur": 6}])
    doc["fps"] = 25
    files = {("clips", 0): {"name": "1.mp4", "path": "/srv/1.mp4"}}

    edl = render("edl", doc, files).split("\r\n")
    otio = json.loads(render("otio", doc, files))
    fcpxml = render("fcpxml", doc, files)

    assert edl[3] == "001  VP001    V     C        00:00:01:00 00:00:03:00 00:00:00:00 00:00:04:00"
    assert edl[4] == "M2   VP001          012.5                00:00:01:00"
    clip = otio["tracks"]["children"][0]["children"][0]
    assert clip["source_range"]["duration"]["value"] == 50
    assert clip["effects"] == [{"OTIO_SCHEMA": "LinearTimeWarp.1", "name": "", "effect_name": "LinearTimeWarp", "metadata": {}, "time_scalar": 0.5}]
    assert '<timeMap><timept time="25/25s" value="25/25s" interp="linear"/><timept time="125/25s" value="75/25s" interp="linear"/></timeMap></asset-clip>' in fcpxml
    ElementTree.fromstring(fcpxml.encode("utf-8"))


def test_the_otio_of_a_slowed_shot_reads_with_opentimelineio(make_doc):
    otio = pytest.importorskip("opentimelineio")
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 4, "srcIn": 1, "speed": 0.25}], assets=[{"id": "a1", "kind": "video", "name": "x", "srcDur": 6}])
    doc["fps"] = 25

    timeline = otio.adapters.read_from_string(render("otio", doc, {("clips", 0): {"name": "1.mp4", "path": "/srv/1.mp4"}}), "otio_json")

    [clip] = timeline.video_tracks()[0]
    assert clip.effects[0].time_scalar == 0.25


def test_the_assistant_bounds_a_slowed_shot_by_the_source_its_speed_covers(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 2, "srcIn": 1, "speed": 0.5}], assets=[{"id": "a1", "kind": "video", "srcDur": 5}])
    taken = make_doc(clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 2, "srcIn": 1, "speed": 0.25}], assets=[{"id": "a1", "kind": "video", "srcDur": 5, "generated": True}])

    assert edits.duration_limit(doc, doc["clips"][0]) == (8.0, "source")
    assert edits.take_length(taken, taken["clips"][0]) == 16.0
