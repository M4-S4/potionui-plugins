import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from fastapi.testclient import TestClient

from backend import core_bridge, takes
from backend.core_bridge import LimitExceeded, MediaRefError
from backend.exports import EXCHANGE, content_disposition, jobs, render, slug, unicode_name, video
from backend.exports.fcpxml import media_url
from backend.exports.media import files_of
from backend.exports.mix import write_impulse
from backend.exports.video import ExportError, build_command, filter_graph, frame_size
from src.plugin_api import AccountType, get_current_active_user

BASE = "/api/plugins/video-producer"
STORAGE = "/srv/storage"
BACKSLASH = chr(92)
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
WINDOWS_COMMAND_LIMIT = 32767
FORMATS = tuple(EXCHANGE)
PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mkv", "graph": "/tmp/out/graph.txt"}
MAX_ARGUMENT = 131072


class Absent:
    def resolve(self, ref):
        raise MediaRefError("not_found", "The referenced media is not available")

    def path(self, kind, value):
        return f"{STORAGE}/{value}"


def _doc(make_doc, clips=(), **fields):
    doc = make_doc(
        clips=clips,
        assets=[{"id": "a1", "kind": "video", "name": "Asset", "generated": True, "quality": "draft", "resultId": "r1"}],
    )
    doc.update(fields)
    return doc


def _shot(index, **fields):
    return {"id": f"c{index}", "assetId": "a1", "start": index, "dur": 1, **fields}


def _files(doc, found=(), media="name"):
    return files_of(doc, list(found), Absent(), media=media)


def _all(doc, files=None):
    files = _files(doc) if files is None else files
    return {fmt: render(fmt, doc, files) for fmt in FORMATS}


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _frames(value):
    return 0 if value == "0s" else int(value.split("/")[0])


def _inputs(command):
    return [command[index + 1] for index, item in enumerate(command) if item == "-i"]


def _options(fmt="web", resolution="720p", audio=None, stills=()):
    return {"format": fmt, "resolution": resolution, "audio": audio or {}, "stills": list(stills), "impulse": "/tmp/out/reverb.wav"}


def _command(doc, files, sounds=None, **options):
    return build_command(doc, files, _options(**options), {**PATHS, "audio": sounds or {}})


def _script(doc, files, sounds=None, **options):
    return filter_graph(doc, files, _options(**options), {**PATHS, "audio": sounds or {}})


def _prepare(doc, files, folder, label, audio=None, sounds=None, fmt="web", resolution="720p", stills=(), lengths=None, ratio=None):
    options = {"format": fmt, "resolution": resolution, "ratio": ratio, "stills": list(stills), **(video.inspect(files) if lengths is None else {"lengths": lengths})}
    if audio is not None:
        options["audio"] = audio
    ffmpeg = shutil.which("ffmpeg")
    paths = {
        "ffmpeg": ffmpeg,
        "graph_option": video.graph_option(ffmpeg),
        "output": str(folder / f"{label}.mkv"),
        "graph": str(folder / f"{label}.graph"),
        "audio": sounds or {},
    }
    options["impulse"] = str(write_impulse(folder / "reverb.wav", 48000))
    sources = [entry["path"] for entry in files.values() if entry is not None] + list((sounds or {}).values())
    paths["cwd"] = video.common_folder(sources)
    Path(paths["graph"]).write_text(filter_graph(doc, files, options, paths), encoding="utf-8")
    return build_command(doc, files, options, paths), paths["cwd"]


def _with_audio(doc, items=(), lanes=None):
    doc["audio"] = [
        {"id": f"u{index}", "assetId": None, "lane": "A1", "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **item}
        for index, item in enumerate(items)
    ]
    for lane_id, changes in (lanes or {}).items():
        doc["lanes"] = [{**lane, **changes} if lane["id"] == lane_id else lane for lane in doc["lanes"]]
    return doc


def _reference():
    folder = Path(__file__).resolve().parent / "fixtures" / "exports"
    return json.loads((folder / "reference-project.json").read_text(encoding="utf-8")), folder


def test_every_clip_of_the_otio_carries_the_media_references_the_schema_requires():
    reference, _ = _reference()
    doc = reference["doc"]

    timeline = json.loads(render("otio", doc, files_of(doc, reference["takes"], Absent(), media="name")))

    clips = [child for track in timeline["tracks"]["children"] for child in track["children"] if child["OTIO_SCHEMA"] == "Clip.2"]
    assert len(clips) > 4
    assert all("media_references" in clip and clip.get("active_media_reference_key") in clip["media_references"] for clip in clips)


def test_the_reference_otio_reads_with_opentimelineio():
    otio = pytest.importorskip("opentimelineio")
    reference, folder = _reference()
    doc = reference["doc"]

    timeline = otio.adapters.read_from_string(render("otio", doc, files_of(doc, reference["takes"], Absent(), media="name")), "otio_json")

    assert len(timeline.tracks) == 5 and len(timeline.video_tracks()[0]) == 4


def test_the_golden_otio_is_what_render_writes_for_the_reference_project():
    reference, folder = _reference()
    doc = reference["doc"]

    text = render("otio", doc, files_of(doc, reference["takes"], Absent(), media="name"))

    assert json.loads(text) == json.loads((folder / "reference.otio").read_text(encoding="utf-8"))


def test_a_sequence_without_any_shot_exports_in_every_format(make_doc):
    doc = make_doc()

    texts = _all(doc, {})

    root = ElementTree.fromstring(texts["fcpxml"].encode("utf-8"))
    assert list(root.find(".//spine")) == [] and root.find(".//sequence").get("duration") == "25/25s"
    timeline = json.loads(texts["otio"])
    assert [track["children"] for track in timeline["tracks"]["children"]] == [[], [], [], [], []]
    assert texts["edl"].split("\r\n") == [f"TITLE: {doc['name'].upper()}", "FCM: NON-DROP FRAME", ""]
    assert texts["srt"] == ""


@pytest.mark.parametrize("fmt, empty", [("fcpxml", False), ("otio", False), ("edl", False), ("srt", True)])
def test_the_routes_answer_200_for_a_project_without_any_shot(client, store, make_project, make_doc, fmt, empty):
    project = make_project(doc=make_doc())

    response = client.get(f"{BASE}/projects/{project['id']}/exports/{fmt}")

    assert response.status_code == 200 and (response.content == b"") is empty


def test_two_hundred_shots_export_in_every_format_with_one_entry_each(make_doc):
    clips = [_shot(index, start=index * 0.5, dur=0.5, assetId="a1" if index % 2 == 0 else None) for index in range(200)]
    doc = _doc(make_doc, clips)
    started = time.monotonic()

    texts = _all(doc)

    assert time.monotonic() - started < 5
    root = ElementTree.fromstring(texts["fcpxml"].encode("utf-8"))
    assert len(root.findall(".//spine/asset-clip")) == 100 and len(root.findall(".//spine/gap")) == 100
    declared = {element.get("id") for element in root.find("resources")}
    assert all(clip.get("ref") in declared for clip in root.findall(".//spine/asset-clip"))
    video_track = json.loads(texts["otio"])["tracks"]["children"][0]["children"]
    assert [item["OTIO_SCHEMA"] for item in video_track].count("Clip.2") == 100 and len(video_track) == 200
    events = [line for line in texts["edl"].split("\r\n") if re.match(r"\d{3} ", line)]
    assert [line[:3] for line in events] == [f"{number:03d}" for number in range(1, 201)]
    records = [line.split()[-2] for line in events]
    assert records == sorted(records) and len(set(records)) == 200


NAMES = [
    "A]]>B",
    "<x>",
    "&amp;",
    "q\"uote's",
    "emoji \U0001f600",
    "\u00e9 \u00e0 \u00e7",
    "\u202e RTL",
    "\u2028",
    "a/b" + BACKSLASH + "c",
    "  padded  ",
    "\u65e5\u672c\u8a9e",
    "x" * 300,
]


@pytest.mark.parametrize("name", NAMES)
def test_a_name_with_markup_or_unicode_is_escaped_in_the_xml_and_quoted_in_the_json(make_doc, name):
    doc = _doc(make_doc, [_shot(0, label=name)], name=name)

    texts = _all(doc)

    root = ElementTree.fromstring(texts["fcpxml"].encode("utf-8"))
    assert root.find(".//project").get("name") == name
    assert root.find(".//spine/asset-clip").get("name") == name
    assert root.find(".//resources/asset").get("name") == name
    timeline = json.loads(texts["otio"])
    assert timeline["name"] == name and timeline["tracks"]["children"][0]["children"][0]["name"] == name
    assert texts["edl"].split("\r\n")[0] == f"TITLE: {name.upper()}"
    assert f"* FROM CLIP NAME: {name}" in texts["edl"]


@pytest.mark.parametrize("name", NAMES)
def test_the_download_header_of_any_name_is_plain_latin_1_with_the_utf8_name_encoded(name):
    header = content_disposition(name, "fcpxml")

    header.encode("latin-1")
    assert "\r" not in header and "\n" not in header
    ascii_part, _, encoded = header.partition("; filename*=UTF-8''")
    assert ascii_part == f'attachment; filename="{slug(name)}.fcpxml"'
    assert unquote(encoded) == f"{unicode_name(name)}.fcpxml"
    assert re.fullmatch(r"[A-Za-z0-9._-]+", slug(name))


@pytest.mark.parametrize("name", ["a\r\nb", "a\nb", "a\rb", "tab\there", "]]>\r\n<![CDATA["])
def test_a_line_break_or_a_tab_in_a_name_keeps_the_xml_and_the_json_valid(make_doc, name):
    doc = _doc(make_doc, [_shot(0, label=name)], name=name)

    texts = _all(doc)

    root = ElementTree.fromstring(texts["fcpxml"].encode("utf-8"))
    assert root.find(".//project").get("name") == re.sub(r"[\t\r\n]", " ", name.replace("\r\n", "\n"))
    assert json.loads(texts["otio"])["name"] == name


CONTROLS = ["ctrl\x01", "nul\x00", "bell\x07", "vtab\x0b", "esc\x1b", "\ufffe"]


@pytest.mark.parametrize("name", CONTROLS)
def test_characters_xml_cannot_hold_keep_the_fcpxml_well_formed(make_doc, name):
    doc = _doc(make_doc, [_shot(0, label=name)], name=name)

    ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))


def test_a_line_break_in_a_name_or_a_path_cannot_forge_an_edl_event(make_doc):
    forged = "x\r\n002  FORGED   V     C        00:00:00:00 00:00:01:00 00:00:00:00 00:00:01:00"
    doc = _doc(make_doc, [_shot(0, label=forged)], name=forged)
    files = {("clips", 0): {"name": "m.mp4", "path": f"/srv/{forged}.mp4"}}

    lines = render("edl", doc, files).split("\r\n")

    events = [line for line in lines if re.match(r"\d{3} ", line)]
    assert len(events) == 1
    assert all(re.match(r"(TITLE: |FCM: |\d{3} |\* FROM CLIP NAME: |\* SOURCE FILE: |$)", line) for line in lines)


def test_a_blank_line_in_a_title_cannot_split_its_srt_cue(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    doc["titles"] = [{"id": "t1", "text": "one\n\ntwo", "sub": "", "start": 0, "dur": 2}]

    text = render("srt", doc, {})

    blocks = [block for block in text.split("\n\n") if block.strip()]
    assert len(blocks) == 1


def test_a_srt_cue_with_an_arrow_in_its_text_still_reads_as_one_cue(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    doc["titles"] = [{"id": "t1", "text": "a --> b", "sub": "", "start": 0, "dur": 2}]

    blocks = [block for block in render("srt", doc, {}).split("\n\n") if block.strip()]

    assert len(blocks) == 1 and blocks[0].split("\n")[2] == "a --> b"


FILE_PATHS = [
    "/srv/stor age/uploads/plan \u00e9t\u00e9.mp4",
    "/srv/100%/clip.mp4",
    "/srv/a&b/clip.mp4",
    "/srv/a'b/clip.mp4",
    '/srv/a"b/clip.mp4',
    "/srv/a<b>/clip.mp4",
    "/srv/a+b;c,d/clip.mp4",
    "/srv/\u65e5\u672c\u8a9e/\u30d3\u30c7\u30aa.mp4",
    "C:" + BACKSLASH + "Users" + BACKSLASH + "Bob" + BACKSLASH + "clip \u00e9.mp4",
    "C:/Users/Bob/Videos/clip \u00e9t\u00e9.mp4",
]


def _read_url(url):
    raw = url.replace("&amp;", "&").replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    parsed = urlparse(raw)
    assert parsed.scheme == "file" and parsed.netloc == ""
    return unquote(parsed.path), parsed.query, parsed.fragment


@pytest.mark.parametrize("path", FILE_PATHS)
def test_a_path_with_spaces_accents_or_symbols_reads_back_from_its_file_url(path):
    location, query, fragment = _read_url(media_url({"path": path}))

    expected = path.replace(BACKSLASH, "/")
    expected = f"/{expected}" if expected[1:3] == ":/" else expected
    assert (location, query, fragment) == (expected, "", "")


@pytest.mark.parametrize("path", ["/srv/a#b/clip.mp4", "/srv/a?b/clip.mp4", "/srv/dir#1/dir?2/clip.mp4"])
def test_a_hash_or_a_question_mark_in_a_path_stays_in_the_path_of_its_file_url(path):
    location, query, fragment = _read_url(media_url({"path": path}))

    assert (location, query, fragment) == (path, "", "")


def test_a_network_share_path_gives_a_two_slash_file_url():
    url = media_url({"path": BACKSLASH * 2 + "server" + BACKSLASH + "share" + BACKSLASH + "clip.mp4"})

    assert url == "file://server/share/clip.mp4"


def test_the_path_of_a_shot_is_written_as_it_is_in_the_edl_and_the_otio(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    path = "/srv/stor age/\u00e9t\u00e9 & co/100%.mp4"
    files = {("clips", 0): {"name": "100%.mp4", "path": path}}

    texts = _all(doc, files)

    assert f"* SOURCE FILE: {path}\r\n" in texts["edl"]
    assert json.loads(texts["otio"])["tracks"]["children"][0]["children"][0]["media_references"]["DEFAULT_MEDIA"]["target_url"] == path


@pytest.mark.parametrize("media", ["PATH", "Name", "", " path", "path ", "url", "true", "0"])
def test_a_media_mode_other_than_path_or_name_is_an_invalid_request(client, make_project, make_doc, media):
    project = make_project(doc=make_doc())

    response = client.get(f"{BASE}/projects/{project['id']}/exports/edl", params={"media": media})

    assert response.status_code == 422 and response.json()["detail"]["error"] == "invalid_request"


def test_a_repeated_media_parameter_takes_the_last_value(client, store, make_project, make_doc):
    project = make_project(doc=make_doc())

    response = client.get(f"{BASE}/projects/{project['id']}/exports/edl?media=bogus&media=name")

    assert response.status_code == 200


@pytest.mark.parametrize("fps", [24, 25, 30, 48, 50, 60])
def test_a_whole_frame_rate_gives_whole_rational_times(make_doc, fps):
    doc = _doc(make_doc, [_shot(0, dur=2.5), _shot(1, start=2.5, dur=1.2)], fps=fps)

    root = ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))

    times = [element.get(name) for element in root.iter() for name in ("frameDuration", "duration", "offset", "start") if element.get(name)]
    assert times and all(re.fullmatch(rf"\d+/{fps}s|0s", value) for value in times)


@pytest.mark.xfail(strict=True, reason="D5: Timebase.rational writes 48/23.976s, not a rational of whole numbers")
@pytest.mark.parametrize("fps", [23.976, 29.97, 59.94])
def test_a_broadcast_frame_rate_gives_whole_rational_times(make_doc, fps):
    doc = _doc(make_doc, [_shot(0, dur=2)], fps=fps)

    root = ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))

    times = [element.get(name) for element in root.iter() for name in ("frameDuration", "duration", "offset", "start") if element.get(name)]
    assert times and all(re.fullmatch(r"\d+/\d+s|0s", value) for value in times)


@pytest.mark.parametrize("fps", [23.976, 29.97, 59.94])
def test_a_broadcast_frame_rate_still_gives_frame_exact_otio_and_edl(make_doc, fps):
    doc = _doc(make_doc, [_shot(0, dur=2)], fps=fps)

    texts = _all(doc)

    assert json.loads(texts["otio"])["tracks"]["children"][0]["children"][0]["source_range"]["duration"] == {
        "OTIO_SCHEMA": "RationalTime.1",
        "rate": fps,
        "value": round(2 * fps),
    }
    assert "FCM: NON-DROP FRAME" in texts["edl"]


@pytest.fixture
def quiet(app, store):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("fmt", ["fcpxml", "otio", "edl"])
@pytest.mark.parametrize("fps", [0, -25])
def test_a_document_that_cannot_be_timed_is_refused_and_never_exported_as_garbage(quiet, make_project, make_doc, fmt, fps):
    project = make_project(doc=_doc(make_doc, [_shot(0)], fps=fps))

    response = quiet.get(f"{BASE}/projects/{project['id']}/exports/{fmt}")

    assert 400 <= response.status_code < 500


@pytest.mark.parametrize("fmt", ["fcpxml", "otio", "edl"])
def test_an_absurd_duration_is_refused_and_not_a_server_error(quiet, make_project, make_doc, fmt):
    project = make_project(doc=_doc(make_doc, [_shot(0, dur=1e308)]))

    response = quiet.get(f"{BASE}/projects/{project['id']}/exports/{fmt}")

    assert response.status_code < 500


def test_fractional_times_are_rounded_one_by_one_so_neighbours_can_miss_by_one_frame(make_doc):
    clips = [_shot(index, start=index * 0.333, dur=0.333) for index in range(12)]
    doc = _doc(make_doc, clips)

    root = ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))

    items = root.findall(".//spine/asset-clip")
    drift = [_frames(b.get("offset")) - _frames(a.get("offset")) - _frames(a.get("duration")) for a, b in zip(items, items[1:])]
    assert set(drift) == {0, 1}
    assert max(abs(value) for value in drift) <= 1


def test_a_shot_whose_asset_is_missing_is_a_gap_named_after_its_label_or_a_default(make_doc):
    doc = _doc(make_doc, [_shot(0, assetId="ghost", label="Ghost"), _shot(1, assetId="ghost")])

    root = ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))

    assert [(gap.get("name")) for gap in root.findall(".//spine/gap")] == ["Ghost", "Shot"]
    assert render("edl", doc, _files(doc)).count("  BL ") == 2


def test_an_asset_no_shot_uses_is_not_declared_in_the_fcpxml(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    doc["assets"].append({**doc["assets"][0], "id": "a2", "name": "Unused"})

    root = ElementTree.fromstring(render("fcpxml", doc, _files(doc)).encode("utf-8"))

    assert [asset.get("name") for asset in root.findall(".//resources/asset")] == ["Asset"]


def test_audio_that_points_at_nothing_gives_no_subtitle_and_an_unnamed_otio_clip(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    _with_audio(doc, [{"id": "u0", "assetId": "ghost", "dur": 1}])

    texts = _all(doc)

    assert texts["srt"] == ""
    dialogue = json.loads(texts["otio"])["tracks"]["children"][1]["children"][0]
    assert dialogue["OTIO_SCHEMA"] == "Clip.2" and "name" not in dialogue


def test_audio_on_a_lane_the_document_does_not_declare_is_left_out_of_the_otio_and_of_the_video(make_doc):
    doc = _doc(make_doc, [_shot(0)])
    _with_audio(doc, [{"id": "u0", "lane": "A9"}])

    tracks = json.loads(render("otio", doc, _files(doc)))["tracks"]["children"]

    assert [track["name"].split(" ")[0] for track in tracks] == ["V1", "A1", "A2", "A3", "A4"]
    assert all(track["children"] == [] for track in tracks[1:])
    assert video.audible(doc) == []


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_a_take_that_is_not_done_never_gives_its_path(make_doc, status):
    doc = _doc(make_doc, [_shot(0)])
    take = {"id": "r1", "status": status, "file_path": "generations/g/1.mp4", "generation_id": "g", "file_id": "f"}

    files = _files(doc, [take], media="path")

    assert files[("clips", 0)] == {"name": "Asset_draft_r1.mov", "path": "Asset_draft_r1.mov"}


@pytest.mark.parametrize("file_path", [None, ""])
def test_a_done_take_without_a_file_never_gives_a_path(make_doc, file_path):
    doc = _doc(make_doc, [_shot(0)])
    take = {"id": "r1", "status": "done", "file_path": file_path, "generation_id": "g", "file_id": "f"}

    files = _files(doc, [take], media="path")

    assert files[("clips", 0)] == {"name": "Asset_draft_r1.mov", "path": "Asset_draft_r1.mov"}


def test_an_asset_that_is_not_generated_and_has_no_file_is_a_gap_and_a_bl_reel(make_doc):
    doc = make_doc(clips=[_shot(0)], assets=[{"id": "a1", "kind": "video", "name": "Placeholder"}])

    files = files_of(doc, [], Absent(), media="path")

    assert files == {("clips", 0): None}
    assert "  BL " in render("edl", doc, files)


def test_two_shots_with_the_same_id_each_keep_their_own_file(make_doc):
    doc = make_doc(
        clips=[{"id": "dup", "assetId": "a1", "start": 0, "dur": 1}, {"id": "dup", "assetId": "a2", "start": 1, "dur": 1}],
        assets=[
            {"id": "a1", "kind": "video", "name": "First", "src": "/api/media/uploads/first.mp4"},
            {"id": "a2", "kind": "video", "name": "Second", "src": "/api/media/uploads/second.mp4"},
        ],
    )

    edl = render("edl", doc, _files(doc))

    assert "* SOURCE FILE: first.mp4" in edl and "* SOURCE FILE: second.mp4" in edl


def _real_fixture(make_doc, count):
    clips = [_shot(index, start=index * 0.5, dur=0.5, contrast=110, saturation=90, exposure=0.5, temperature=5, fadeIn=0.1, fadeOut=0.1) for index in range(count)]
    doc = _doc(make_doc, clips)
    files = {clip["id"]: {"name": "x.mp4", "path": f"{STORAGE}/generations/2026-10-17/01M53W7F92902CHR2CG3GKDBTW/1.mp4"} for clip in clips}
    return doc, files, {clip["id"]: True for clip in clips}


def test_two_hundred_shots_build_one_graph_that_ffmpeg_reads_from_a_file(make_doc):
    doc, files, audio = _real_fixture(make_doc, 200)

    command, graph = _command(doc, files, audio=audio), _script(doc, files, audio=audio)

    assert len(_inputs(command)) == 200 and f"concat=n={200}:v=1:a=1" in graph
    assert command[command.index("-filter_complex_script") + 1] == PATHS["graph"] and graph not in command


@pytest.mark.parametrize("count", [240, 320, 800])
def test_a_long_sequence_still_fits_in_the_arguments_of_a_single_ffmpeg_run(make_doc, count):
    doc, files, audio = _real_fixture(make_doc, count)

    command = _command(doc, files, audio=audio)

    assert max(len(argument.encode("utf-8")) for argument in command) < MAX_ARGUMENT


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.requires_ffmpeg
async def test_a_long_sequence_assembles_when_ffmpeg_is_started_from_the_command_the_plugin_builds(make_doc, tmp_path):
    source = _clip(tmp_path, "src.mp4", "160x120", 1.0, True)
    clips = [_shot(index, start=index * 0.04, dur=0.04, contrast=110, fadeIn=0.01, fadeOut=0.01, temperature=5) for index in range(400)]
    doc = _doc(make_doc, clips)
    files = {clip["id"]: {"name": "src.mp4", "path": str(source)} for clip in clips}
    command, cwd = _prepare(doc, files, tmp_path, "long", audio={clip["id"]: True for clip in clips})

    await video.assemble(command, 16.0, None, None, cwd)

    assert abs(core_bridge.probe_video(tmp_path / "long.mkv").duration - 16.0) < 0.2


def _long_folder(tmp_path):
    folder = tmp_path / ("a-long-folder-for-the-takes-" * 2) / ("and-a-longer-one-inside-" * 2)
    folder.mkdir(parents=True)
    return folder


def _distinct_sources(make_doc, tmp_path, count):
    source = _clip(tmp_path, "src.mp4", "160x120", 1.0, True)
    folder = _long_folder(tmp_path)
    clips = [_shot(index, start=index * 0.04, dur=0.04, contrast=110, fadeIn=0.01, fadeOut=0.01, temperature=5) for index in range(count)]
    files = {}
    for clip in clips:
        copy = folder / f"take-{clip['id']}.mp4"
        shutil.copyfile(source, copy)
        files[clip["id"]] = {"name": copy.name, "path": str(copy)}
    return _doc(make_doc, clips), files, clips


def test_four_hundred_shots_of_four_hundred_files_in_a_long_folder_fit_in_a_windows_command_line(make_doc, tmp_path):
    doc, files, clips = _distinct_sources(make_doc, tmp_path, 400)
    audio = {clip["id"]: True for clip in clips}
    options = _options(audio=audio)
    sources = [entry["path"] for entry in files.values()]
    absolute = {**PATHS, "output": str(tmp_path / "out.mp4"), "graph": str(tmp_path / "out.graph"), "audio": {}}
    relative = {**absolute, "cwd": video.common_folder(sources)}

    long_line = build_command(doc, files, options, absolute)
    short_line = build_command(doc, files, options, relative)

    assert sum(len(argument) + 1 for argument in long_line) > WINDOWS_COMMAND_LIMIT
    assert sum(len(argument) + 1 for argument in short_line) < WINDOWS_COMMAND_LIMIT
    assert len(_inputs(short_line)) == 400 and len(set(_inputs(short_line))) == 400
    assert not any(str(tmp_path) in argument for argument in _inputs(short_line))


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.requires_ffmpeg
async def test_four_hundred_shots_of_four_hundred_files_in_a_long_folder_assemble(make_doc, tmp_path):
    doc, files, clips = _distinct_sources(make_doc, tmp_path, 400)
    length = core_bridge.probe_video(Path(files[clips[0]["id"]]["path"])).duration
    command, cwd = _prepare(
        doc, files, tmp_path, "distinct", audio={clip["id"]: True for clip in clips}, lengths={clip["id"]: length for clip in clips}
    )

    await video.assemble(command, 16.0, None, None, cwd)

    assert sum(len(argument) + 1 for argument in command) < WINDOWS_COMMAND_LIMIT
    assert abs(core_bridge.probe_video(tmp_path / "distinct.mkv").duration - 16.0) < 0.2


def _recorded(monkeypatch):
    commands = []
    real = video.assemble

    async def assemble(command, *args, **kwargs):
        commands.append(list(command))
        return await real(command, *args, **kwargs)

    monkeypatch.setattr(video, "assemble", assemble)
    return commands


def _sequence_paths(folder, label, sounds):
    ffmpeg = shutil.which("ffmpeg")
    return {
        "ffmpeg": ffmpeg,
        "graph_option": video.graph_option(ffmpeg),
        "output": str(folder / f"{label}.mkv"),
        "graph": str(folder / f"{label}.graph"),
        "audio": sounds,
    }


def _colored(folder, name, color, tone):
    path = folder / name
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x120:r=25:d=1", "-f", "lavfi", "-i", f"sine=frequency={tone}:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ]
    subprocess.run(command, check=True, timeout=60)
    return path


def _rgb_at(path, seconds):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seconds), "-i", str(path),
        "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    return tuple(subprocess.run(command, capture_output=True, check=True, timeout=60).stdout)


def _mean_volume(path):
    command = ["ffmpeg", "-hide_banner", "-i", str(path), "-map", "0:a", "-af", "volumedetect", "-f", "null", "-"]
    run = subprocess.run(command, capture_output=True, text=True, timeout=60)
    return float(re.search(r"mean_volume: (-?[\d.]+) dB", run.stderr).group(1))


def _output_of(command):
    return Path(command[-1]).name


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.requires_ffmpeg
@pytest.mark.parametrize("limit, rounds", [(4, 1), (2, 3)])
async def test_a_sequence_assembled_in_parts_matches_its_single_run_in_picture_timing_and_sound(make_doc, tmp_path, monkeypatch, limit, rounds):
    colors = ["red", "lime", "blue"]
    clips, files = [], {}
    for index in range(9):
        source = _colored(tmp_path, f"shot-{index}.mp4", colors[index % 3], 300 + 100 * index)
        clips.append(_shot(index, start=index * 0.5, dur=0.5, srcIn=0.2, fadeIn=0.1 if index == 4 else 0))
        files[f"c{index}"] = {"name": source.name, "path": str(source)}
    sounds = {}
    for index in range(5):
        tone = tmp_path / f"tone-{index}.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={500 + 50 * index}:duration=1", str(tone)], check=True, timeout=60)
        sounds[f"u{index}"] = str(tone)
    doc = _with_audio(_doc(make_doc, clips), [{"start": index * 0.8, "dur": 0.6, "gain": -6} for index in range(5)])
    options = {"format": "web", "resolution": "720p", "stills": [], **video.inspect(files), "impulse": str(write_impulse(tmp_path / "reverb.wav", 48000))}
    whole, parted = _sequence_paths(tmp_path, "whole", sounds), _sequence_paths(tmp_path, "parted", sounds)
    await video.assemble_sequence(doc, files, options, whole, tmp_path, lambda progress, step: True)
    monkeypatch.setattr(video, "PART_INPUTS", limit)
    monkeypatch.setattr(video, "MIX_INPUTS", 2)
    commands, steps = _recorded(monkeypatch), []

    await video.assemble_sequence(doc, files, options, parted, tmp_path, lambda progress, step: steps.append((progress, step)) or True)

    parts = [command for command in commands if _output_of(command).startswith("part-")]
    premixes = [command for command in commands if _output_of(command).startswith("lanes-")]
    assert {_output_of(command).split("-")[1] for command in parts} == {str(level) for level in range(rounds)}
    assert parts and all(len(_inputs(command)) <= limit for command in parts)
    assert len(premixes) == 3 and all(len(_inputs(command)) <= 2 for command in premixes)
    assert _output_of(commands[-1]) == "parted.mkv" and len(commands) == len(parts) + len(premixes) + 1
    first, second = core_bridge.probe_video(tmp_path / "whole.mkv"), core_bridge.probe_video(tmp_path / "parted.mkv")
    assert abs(first.duration - second.duration) < 0.05 and abs(second.duration - 4.5) < 0.1
    for index in range(9):
        expected = _rgb_at(tmp_path / "whole.mkv", index * 0.5 + 0.3)
        assert max(expected) > 200 and max(abs(a - b) for a, b in zip(expected, _rgb_at(tmp_path / "parted.mkv", index * 0.5 + 0.3))) < 12
    assert abs(_mean_volume(tmp_path / "whole.mkv") - _mean_volume(tmp_path / "parted.mkv")) < 0.5
    assert [progress for progress, _ in steps] == sorted(progress for progress, _ in steps)
    assert all(step == ("mix" if progress >= video.MIX_FROM else "assemble") for progress, step in steps)
    assert steps[-1][0] == pytest.approx(video.ASSEMBLE_SHARE, abs=2)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.requires_ffmpeg
async def test_seven_hundred_shots_of_seven_hundred_files_assemble_in_runs_of_forty_inputs_and_short_command_lines(make_doc, tmp_path, monkeypatch):
    doc, files, clips = _distinct_sources(make_doc, tmp_path, 700)
    options = {"format": "web", "resolution": "720p", "stills": [], "audio": {clip["id"]: True for clip in clips}, "lengths": {clip["id"]: 1.0 for clip in clips}}
    paths = {**_sequence_paths(tmp_path, "long", {}), "cwd": video.common_folder(entry["path"] for entry in files.values())}
    commands = _recorded(monkeypatch)

    await video.assemble_sequence(doc, files, options, paths, tmp_path, lambda progress, step: True)

    assert len(commands) == 19 and max(len(_inputs(command)) for command in commands) <= video.PART_INPUTS
    assert max(len(subprocess.list2cmdline(command)) for command in commands) < WINDOWS_COMMAND_LIMIT // 4
    assert abs(core_bridge.probe_video(tmp_path / "long.mkv").duration - 28.0) < 0.2


HOSTILE = [
    "semi;colon.mp4",
    "br[ack]et.mp4",
    "quo'te.mp4",
    "com,ma.mp4",
    "eq=ual.mp4",
    "col:on.mp4",
    "sp ace \u00e9t\u00e9.mp4",
    "-hostile.mp4",
    "new\nline.mp4",
    "percent%s.mp4",
    "$(touch pwned).mp4",
    "`touch pwned`.mp4",
    "lavfi.mp4",
    "concat:a|b.mp4",
    BACKSLASH.join(["win", "style.mp4"]),
]


@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("name", HOSTILE)
def test_a_hostile_file_name_is_only_ever_the_value_of_an_input_option(make_doc, name, relative):
    doc = _doc(make_doc, [_shot(0), _shot(1)])
    path = name if relative else f"{STORAGE}/{name}"
    files = {"c0": {"name": name, "path": path}, "c1": None}
    command, graph = _command(doc, files, audio={"c0": True}), _script(doc, files, audio={"c0": True})

    assert command[0] == "/usr/bin/ffmpeg" and all(isinstance(argument, str) for argument in command)
    position = command.index(path)
    assert command[position - 1] == "-i" and command.count(path) == 1
    assert not any(part in graph for part in (name, path, "pwned", STORAGE))


@pytest.mark.parametrize("name", HOSTILE)
def test_a_hostile_file_name_from_a_working_folder_is_a_relative_path_behind_a_dot_slash(make_doc, tmp_path, name):
    doc = _doc(make_doc, [_shot(0), _shot(1)])
    path = str(tmp_path / "takes" / name)
    files = {"c0": {"name": name, "path": path}, "c1": None}
    paths = {**PATHS, "audio": {}, "cwd": str(tmp_path / "takes"), "output": str(tmp_path / "work" / "m.mp4"), "graph": str(tmp_path / "work" / "g.txt")}

    command = build_command(doc, files, _options(audio={"c0": True}), paths)

    argument = os.path.join(os.curdir, name)
    position = command.index(argument)
    assert command[position - 1] == "-i" and command.count(argument) == 1 and argument.startswith(os.curdir + os.sep)
    assert not any(str(tmp_path) in part for part in _inputs(command))


def test_no_text_of_the_document_reaches_the_graph(make_doc):
    marker = "MARKER;[x]'\"=,:"
    doc = _doc(make_doc, [_shot(0, label=marker)], name=marker, synopsis=marker)
    doc["assets"][0]["name"] = marker
    doc["titles"] = [{"id": "t1", "text": marker, "sub": marker, "start": 0, "dur": 1}]
    _with_audio(doc, [{"id": "u0", "assetId": "a1"}])

    files, sounds = {"c0": {"name": "x", "path": "/srv/x.mp4"}}, {"u0": "/srv/y.wav"}

    assert "MARKER" not in " ".join(_command(doc, files, sounds=sounds)) and "MARKER" not in _script(doc, files, sounds=sounds)


@pytest.mark.parametrize("fade_in, fade_out", [(10, 10), (2, 2), (1.5, 1.5), (0.25, 10), (10, 0)])
def test_fades_longer_than_the_shot_are_cut_to_the_shot(make_doc, fade_in, fade_out):
    doc = _doc(make_doc, [_shot(0, dur=2, fadeIn=fade_in, fadeOut=fade_out)])
    _with_audio(doc, [{"id": "u0", "assetId": "a1", "dur": 2, "fadeIn": fade_in, "fadeOut": fade_out}])

    graph = _script(doc, {"c0": {"name": "x", "path": "/srv/x.mp4"}}, sounds={"u0": "/srv/y.wav"})

    fades = re.findall(r"a?fade=t=(in|out):st=([\d.]+):d=([\d.]+)", graph)
    assert fades
    for kind, start, duration in fades:
        assert 0 <= float(start) and 0 < float(duration) <= 2 and float(start) + float(duration) <= 2 + 1e-9


@pytest.mark.parametrize("gain", [-58, -30, 0, 12, 60, 1e30])
def test_an_extreme_gain_is_written_as_a_plain_number_of_decibels(make_doc, gain):
    doc = _doc(make_doc, [_shot(0, dur=2)])
    _with_audio(doc, [{"id": "u0", "assetId": "a1", "dur": 1, "gain": gain}], lanes={"A1": {"vol": 0}})

    graph = _script(doc, {"c0": {"name": "x", "path": "/srv/x.mp4"}}, sounds={"u0": "/srv/y.wav"})

    volume = re.search(r"volume=(\S+?)dB", graph).group(1)
    assert re.fullmatch(r"-?\d+(\.\d+)?", volume) and float(volume) == pytest.approx(gain)


def _heard(doc):
    return [item["id"] for item, _ in video.audible(doc)]


def _three_lanes(make_doc, **lanes):
    doc = _doc(make_doc, [_shot(0, dur=3)])
    return _with_audio(
        doc,
        [{"id": "u1", "lane": "A1"}, {"id": "u2", "lane": "A2"}, {"id": "u3", "lane": "A3"}],
        lanes=lanes,
    )


def test_every_lane_muted_leaves_the_bed_alone(make_doc):
    doc = _three_lanes(make_doc, A1={"mute": True}, A2={"mute": True}, A3={"mute": True})

    graph = _script(doc, {"c0": {"name": "x", "path": "/srv/x.mp4"}}, sounds={"u1": "/a", "u2": "/b", "u3": "/c"})

    assert _heard(doc) == [] and graph.split(";")[-1] == "[bed]anull[aout]"


def test_a_soloed_lane_without_any_item_silences_every_other_lane(make_doc):
    doc = _three_lanes(make_doc, A4={"solo": True})

    assert _heard(doc) == []


def test_two_soloed_lanes_play_together(make_doc):
    doc = _three_lanes(make_doc, A1={"solo": True}, A3={"solo": True})

    assert _heard(doc) == ["u1", "u3"]


def test_a_lane_both_muted_and_soloed_stays_muted(make_doc):
    doc = _three_lanes(make_doc, A1={"solo": True, "mute": True}, A2={"solo": True})

    assert _heard(doc) == ["u2"]


@pytest.mark.parametrize("gain", [-1000, -59, -60])
def test_an_item_at_a_gain_down_to_silence_is_not_mixed_as_the_page_plays_it(make_doc, gain):
    doc = _three_lanes(make_doc)
    doc["audio"][0]["gain"] = gain

    assert _heard(doc) == ["u2", "u3"]


def test_the_lane_volume_is_the_fader_of_its_strip_after_its_items_are_summed(make_doc):
    doc = _three_lanes(make_doc, A1={"vol": -6.5})
    doc["audio"][0]["gain"] = 2.25

    graph = _script(doc, {"c0": {"name": "x", "path": "/srv/x.mp4"}}, sounds={"u1": "/a", "u2": "/b", "u3": "/c"}).split(";")

    item = next(chain for chain in graph if chain.endswith("[m0]"))
    strip = next(chain for chain in graph if chain.startswith("[m0]apad="))
    assert "volume=2.25dB" in item and "-6.5" not in item
    assert "volume=-6.5dB" in strip


def test_an_item_shorter_than_a_microsecond_is_not_mixed(make_doc):
    doc = _three_lanes(make_doc)
    doc["audio"][0]["dur"] = 1e-9

    assert _heard(doc) == ["u2", "u3"]


ASPECTS = ["16:9", "9:16", "1:1", "4:5", "5:4", "21:9", "2.39:1", "1.85:1", "4:3", "3:4", "16/9", "1920x1080", "weird", "", "0:0"]


@pytest.mark.parametrize("fmt", ["web", "social"])
@pytest.mark.parametrize("resolution", ["720p", "1080p", "1440p", "4K"])
@pytest.mark.parametrize("aspect", ASPECTS)
def test_every_aspect_gives_an_even_frame_inside_the_16_9_box_of_its_resolution(make_doc, aspect, resolution, fmt):
    doc = _doc(make_doc, [_shot(0)], aspect=aspect)
    base = {"720p": 720, "1080p": 1080, "1440p": 1440, "4K": 2160}[resolution]

    width, height = frame_size(doc, fmt, resolution)
    short, long = sorted((width, height))

    assert width % 2 == 0 and height % 2 == 0 and 2 <= width <= 7680 and 2 <= height <= 7680
    assert short <= base and long <= base * 16 // 9
    assert short == base or long == base * 16 // 9


def test_a_social_export_is_always_nine_by_sixteen_whatever_the_project_aspect(make_doc):
    for aspect in ("16:9", "1:1", "21:9", "4:5", "weird"):
        doc = _doc(make_doc, [_shot(0)], aspect=aspect)

        assert frame_size(doc, "social", "1080p") == (1080, 1920)


@pytest.mark.parametrize("aspect", ["20:1", "100:1", "9999:1", "1:100", "1:9999"])
def test_an_absurd_aspect_cannot_ask_for_a_frame_of_gigapixels(make_doc, aspect):
    doc = _doc(make_doc, [_shot(0)], aspect=aspect)

    try:
        width, height = frame_size(doc, "web", "4K")
    except ValueError:
        return

    assert width * height <= 7680 * 4320


def test_an_aspect_too_large_for_a_float_does_not_crash_the_job_planner(make_doc):
    doc = _doc(make_doc, [_shot(0)], aspect="1e400:1")

    try:
        frame_size(doc, "web", "1080p")
    except OverflowError:
        pytest.fail("the frame size of an overflowing aspect raised OverflowError")


def test_the_file_name_of_an_export_fits_the_255_bytes_of_a_file_system(tmp_path):
    name = video.file_name("x" * 300, "1080p")

    assert len(name.encode("utf-8")) <= 255
    (tmp_path / name).write_bytes(b"x")


def _clip(folder, name, size="160x120", seconds=1.0, tone=True, rate=25):
    path = folder / name
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}"]
    if tone:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)]
    subprocess.run(command, check=True, timeout=60)
    return path


def _sound(folder):
    path = folder / "voice.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=2", str(path)], check=True, timeout=60)
    return path


async def _assemble(doc, files, tmp_path, label, audio=None, sounds=None, fmt="web", resolution="720p", stills=(), ratio=None):
    command, cwd = _prepare(doc, files, tmp_path, label, audio=audio, sounds=sounds, fmt=fmt, resolution=resolution, stills=stills, ratio=ratio)
    _, total = video.timeline(doc)
    await asyncio.wait_for(video.assemble(command, total, None, None, cwd), timeout=120)
    return tmp_path / f"{label}.mkv", total


def _file(path):
    return {"name": path.name, "path": str(path)}


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
class TestRealAssemblies:
    @pytest.mark.parametrize(
        "aspect, fmt, resolution, ratio, framing, size",
        [
            ("2.39:1", "web", "720p", None, None, (1280, 536)),
            ("1.85:1", "master", "1440p", None, "bars", (2560, 1384)),
            ("4:3", "archive", "720p", None, "crop", (960, 720)),
            ("16:9", "social", "720p", "4:5", None, (720, 900)),
            ("2.39:1", "social", "1080p", "1:1", None, (1080, 1080)),
        ],
    )
    async def test_the_formats_and_sizes_assemble_to_their_frame(self, make_doc, tmp_path, aspect, fmt, resolution, ratio, framing, size):
        wide = _clip(tmp_path, "w.mp4", "320x180", 1.0, True, 25)
        square = _clip(tmp_path, "s.mp4", "240x240", 1.0, False, 25)
        doc = _doc(make_doc, [_shot(0), _shot(1)], aspect=aspect, **({"framing": framing} if framing else {}))

        output, total = await _assemble(
            doc, {"c0": _file(wide), "c1": _file(square)}, tmp_path, "formats", audio={"c0": True, "c1": False}, fmt=fmt, resolution=resolution, ratio=ratio
        )

        probe = core_bridge.probe_video(output)
        assert (probe.width, probe.height) == size and abs(probe.duration - total) < 0.1

    async def test_sources_of_every_shape_assemble_to_the_length_of_the_sequence(self, make_doc, tmp_path):
        stereo = _clip(tmp_path, "a.mp4", "320x240", 1.0, True, 25)
        odd = _clip(tmp_path, "b.mp4", "333x187", 1.0, True, 10)
        silent = _clip(tmp_path, "c.mp4", "640x360", 1.0, False, 30)
        doc = _doc(make_doc, [_shot(0), _shot(1), _shot(2)])

        output, total = await _assemble(
            doc, {"c0": _file(stereo), "c1": _file(odd), "c2": _file(silent)}, tmp_path, "shapes", audio={"c0": True, "c1": True, "c2": False}
        )

        probe = core_bridge.probe_video(output)
        assert (probe.width, probe.height, probe.has_audio) == (1280, 720, True) and abs(probe.duration - total) < 0.1

    async def test_a_shot_longer_than_its_source_freezes_on_the_last_picture(self, make_doc, tmp_path):
        source = _clip(tmp_path, "a.mp4")
        doc = _doc(make_doc, [_shot(0, dur=4)])

        output, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "freeze", audio={"c0": True})

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    async def test_fades_longer_than_the_shots_assemble(self, make_doc, tmp_path):
        source = _clip(tmp_path, "a.mp4")
        doc = _doc(make_doc, [_shot(0, dur=2, fadeIn=10, fadeOut=10)])
        _with_audio(doc, [{"id": "u0", "assetId": "a1", "dur": 1, "fadeIn": 10, "fadeOut": 10}])

        output, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "fades", audio={"c0": True}, sounds={"u0": str(_sound(tmp_path))})

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    @pytest.mark.parametrize("gain, lane", [(-30, -30), (12, 6), (-60, 0), (60, 0)])
    async def test_a_gain_from_the_slider_range_to_the_extremes_assembles(self, make_doc, tmp_path, gain, lane):
        source = _clip(tmp_path, "a.mp4")
        doc = _doc(make_doc, [_shot(0, dur=2)])
        _with_audio(doc, [{"id": "u0", "assetId": "a1", "dur": 1, "gain": gain}], lanes={"A1": {"vol": lane}})

        output, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "gain", audio={"c0": True}, sounds={"u0": str(_sound(tmp_path))})

        assert core_bridge.probe_video(output).has_audio

    async def test_an_absurd_gain_fails_the_export_with_the_reason_of_ffmpeg(self, make_doc, tmp_path):
        source = _clip(tmp_path, "a.mp4")
        doc = _doc(make_doc, [_shot(0, dur=2)])
        _with_audio(doc, [{"id": "u0", "assetId": "a1", "dur": 1, "gain": 1000}])
        mezzanine, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "gain", audio={"c0": True}, sounds={"u0": str(_sound(tmp_path))})

        with pytest.raises(ExportError) as caught:
            await video.convert(shutil.which("ffmpeg"), mezzanine, tmp_path / "gain.mp4", (1280, 720), 25, total, lambda progress, step: True)

        assert caught.value.code == "transcode_failed" and caught.value.message

    @pytest.mark.parametrize(
        "look",
        [
            {"contrast": 50, "saturation": 0, "exposure": -2, "temperature": -100},
            {"contrast": 150, "saturation": 200, "exposure": 2, "temperature": 100},
        ],
    )
    async def test_the_extremes_of_the_color_sliders_assemble(self, make_doc, tmp_path, look):
        source = _clip(tmp_path, "a.mp4")
        doc = _doc(make_doc, [_shot(0, **look)])

        output, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "look", audio={"c0": True})

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    @pytest.mark.parametrize(
        "look, luma, blue, red",
        [
            ({"temperature": 100}, 0, -1, 1),
            ({"temperature": -100}, 0, 1, -1),
            ({"exposure": 2}, 1, 0, 0),
            ({"exposure": -2}, -1, 0, 0),
        ],
    )
    async def test_the_look_of_a_shot_moves_the_picture_the_way_the_page_previews_it(self, make_doc, tmp_path, look, luma, blue, red):
        grey = tmp_path / "grey.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x120:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(grey)], check=True, timeout=60)

        def stats(path):
            run = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-frames:v", "1", "-vf", "signalstats,metadata=mode=print:file=-", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {key: float(re.search(rf"signalstats\.{key}=([\d.]+)", run.stdout).group(1)) for key in ("YAVG", "UAVG", "VAVG")}

        neutral, _ = await _assemble(_doc(make_doc, [_shot(0)], framing="bars"), {"c0": _file(grey)}, tmp_path, "neutral")
        graded, _ = await _assemble(_doc(make_doc, [_shot(0, **look)], framing="bars"), {"c0": _file(grey)}, tmp_path, "graded")

        before, after = stats(neutral), stats(graded)
        sign = lambda value, tolerance: (value > tolerance) - (value < -tolerance)
        assert sign(after["YAVG"] - before["YAVG"], 3) == luma
        assert sign(after["UAVG"] - before["UAVG"], 2) == blue
        assert sign(after["VAVG"] - before["VAVG"], 2) == red

    async def test_zero_saturation_removes_the_color_of_the_picture(self, make_doc, tmp_path):
        colorful = _clip(tmp_path, "c.mp4", "160x120", 1.0, False)

        output, _ = await _assemble(_doc(make_doc, [_shot(0, saturation=0)]), {"c0": _file(colorful)}, tmp_path, "mono")

        run = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(output), "-frames:v", "1", "-vf", "signalstats,metadata=mode=print:file=-", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        chroma = [float(re.search(rf"signalstats\.{key}=([\d.]+)", run.stdout).group(1)) for key in ("UAVG", "VAVG")]
        assert all(abs(value - 128) <= 1.5 for value in chroma)

    async def test_a_still_image_is_held_for_the_length_of_its_shot(self, make_doc, tmp_path):
        picture = tmp_path / "s.png"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=100x100", "-frames:v", "1", str(picture)], check=True, timeout=60)
        doc = _doc(make_doc, [_shot(0, dur=2)])

        output, total = await _assemble(doc, {"c0": _file(picture)}, tmp_path, "still", stills=["c0"])

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    @pytest.mark.parametrize("fmt, aspect, size", [("web", "9:16", (720, 1280)), ("social", "16:9", (720, 1280)), ("social", "9:16", (720, 1280))])
    async def test_a_nine_by_sixteen_frame_assembles(self, make_doc, tmp_path, fmt, aspect, size):
        source = _clip(tmp_path, "a.mp4", "320x240")
        doc = _doc(make_doc, [_shot(0, dur=2)], aspect=aspect)

        output, total = await _assemble(doc, {"c0": _file(source)}, tmp_path, "tall", audio={"c0": True}, fmt=fmt)

        probe = core_bridge.probe_video(output)
        assert (probe.width, probe.height) == size and abs(probe.duration - total) < 0.1

    async def test_thirty_shots_of_one_file_assemble(self, make_doc, tmp_path):
        source = _clip(tmp_path, "a.mp4")
        clips = [_shot(index, start=index * 0.5, dur=0.5) for index in range(30)]
        doc = _doc(make_doc, clips)

        output, total = await _assemble(doc, {clip["id"]: _file(source) for clip in clips}, tmp_path, "many", audio={clip["id"]: True for clip in clips})

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    async def test_a_shot_whose_asset_is_a_sound_file_assembles_as_silence_and_black(self, make_doc, tmp_path):
        doc = _doc(make_doc, [_shot(0, dur=2)])

        output, total = await _assemble(doc, {"c0": _file(_sound(tmp_path))}, tmp_path, "sound", audio={"c0": True})

        assert abs(core_bridge.probe_video(output).duration - total) < 0.1

    async def test_a_sub_microsecond_fade_does_not_become_a_one_second_fade(self, make_doc, tmp_path):
        source = _clip(tmp_path, "a.mp4", "160x120", 2.0)
        doc = _doc(make_doc, [_shot(0, dur=2, fadeIn=4e-7)])
        output, _ = await _assemble(doc, {"c0": _file(source)}, tmp_path, "tiny", audio={"c0": True})
        reference, _ = await _assemble(_doc(make_doc, [_shot(0, dur=2)]), {"c0": _file(source)}, tmp_path, "plain", audio={"c0": True})

        def brightness(path):
            run = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.3", "-i", str(path), "-frames:v", "1", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return float(re.search(r"YAVG=([\d.]+)", run.stdout).group(1))

        assert brightness(output) == pytest.approx(brightness(reference), abs=3)


def _limited(gigabytes):
    import resource

    def apply():
        resource.setrlimit(resource.RLIMIT_AS, (int(gigabytes * 2**30), int(gigabytes * 2**30)))

    return apply


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS and preexec_fn exist on POSIX only")
def test_a_shot_that_starts_after_the_end_of_its_source_does_not_swallow_the_memory_of_the_server(make_doc, tmp_path):
    source = _clip(tmp_path, "a.mp4")
    doc = _doc(make_doc, [_shot(0, srcIn=10), _shot(1)])
    files = {"c0": _file(source), "c1": _file(source)}
    command, cwd = _prepare(doc, files, tmp_path, "late", audio={"c0": True, "c1": True})
    command = [argument for argument in command if argument not in ("-progress", "pipe:1")]
    # glibc reserves an arena of address space per thread, which RLIMIT_AS counts like memory
    environment = {**os.environ, "MALLOC_ARENA_MAX": "2"}

    run = subprocess.run(command, capture_output=True, timeout=120, preexec_fn=_limited(2), env=environment, cwd=cwd)

    assert run.returncode == 0 and abs(core_bridge.probe_video(tmp_path / "late.mkv").duration - 2.0) < 0.2


@pytest.fixture
def host(core, export_storage, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(core_bridge, "media_file_path", lambda kind, value: f"{STORAGE}/{value}")
    return core


@pytest.fixture
def exportable(host, make_project, make_doc):
    def make(generation="g1", user_id="user-1"):
        doc = make_doc(
            clips=[{"id": "c1", "assetId": "a1", "start": 0, "dur": 2, "stage": "final"}],
            assets=[{"id": "a1", "kind": "video", "name": "Take", "origin": {"kind": "history", "generationId": generation, "fileId": "f1"}}],
        )
        created = make_project(user_id=user_id, doc=doc)
        takes.create_take(
            {
                "project_id": created["id"],
                "user_id": user_id,
                "shot_id": "c1",
                "quality": "final",
                "kind": "render",
                "status": "done",
                "generation_id": generation,
                "file_id": "f1",
                "file_path": f"generations/2026-10-17/{generation}/1.mp4",
            }
        )
        return created

    return make


@pytest.fixture
def project(exportable):
    return exportable()


def _start(client, project_id, **body):
    return client.post(f"{BASE}/projects/{project_id}/exports/video", json={"format": "web", **body})


def _folder(job, size, name="mezzanine.mp4"):
    folder = video.job_folder(job)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"\0" * size)
    return folder


def _finish(job_id, status="done", size=11):
    job = jobs.get_job(job_id)
    if job["status"] == "queued":
        jobs.claim_next()
    fields = {"file_name": "x_1080p.mp4", "file_size": size, "progress": 100.0, "step": None} if status == "done" else {"error_code": "ffmpeg_failed", "error_message": "x"}
    jobs.settle(job_id, status, **fields)
    return jobs.get_job(job_id)


def test_eight_simultaneous_exports_of_one_project_queue_exactly_one(client, project, host):
    barrier = threading.Barrier(8)
    answers = []

    def post():
        barrier.wait()
        response = _start(client, project["id"])
        answers.append((response.status_code, response.json()))

    threads = [threading.Thread(target=post) for _ in range(8)]
    [thread.start() for thread in threads]
    [thread.join(30) for thread in threads]

    assert sorted(code for code, _ in answers) == [202] + [409] * 7
    assert {body["detail"]["error"] for code, body in answers if code == 409} == {"export_running"}
    assert len(jobs.list_project(project["id"])) == 1


def test_sixteen_threads_creating_a_job_for_one_project_get_one_job(project, host):
    barrier = threading.Barrier(16)
    created = []

    def create():
        barrier.wait()
        created.append(jobs.create_job(project["id"], "user-1", "web", "720p"))

    threads = [threading.Thread(target=create) for _ in range(16)]
    [thread.start() for thread in threads]
    [thread.join(30) for thread in threads]

    assert len([job for job in created if job is not None]) == 1


def test_exports_of_several_projects_wait_in_the_order_they_were_asked(client, exportable, job_clock):
    projects_asked = [exportable(f"g{number}") for number in range(4)]
    for asked in projects_asked:
        assert _start(client, asked["id"]).status_code == 202

    claimed = [jobs.claim_next()["project_id"] for _ in range(4)]

    assert claimed == [asked["id"] for asked in projects_asked] and jobs.claim_next() is None


def test_cancelling_a_queued_job_frees_the_project_clears_its_folder_and_is_skipped_by_the_runner(client, project, host):
    job = _start(client, project["id"]).json()["data"]["job"]
    folder = _folder(jobs.get_job(job["id"]), 10)

    cancelled = client.delete(f"{BASE}/exports/{job['id']}").json()["data"]["job"]

    assert cancelled["status"] == "cancelled" and cancelled["finished_at"] and not folder.exists()
    assert jobs.claim_next() is None
    assert client.get(f"{BASE}/exports/{job['id']}/file").json()["detail"]["error"] == "not_ready"
    assert _start(client, project["id"]).status_code == 202


class Process:
    pid = 2**31 - 1

    def __init__(self):
        self.returncode = None
        self.killed = 0

    def kill(self):
        self.killed += 1
        self.returncode = -9


def test_cancelling_a_running_job_kills_its_process_and_nothing_can_revive_it(client, project, host):
    job = _start(client, project["id"]).json()["data"]["job"]
    jobs.claim_next()
    process = jobs._PROCESSES[job["id"]] = Process()
    assert jobs.update_running(job["id"], progress=40.0, step="mix")

    answer = client.delete(f"{BASE}/exports/{job['id']}")

    assert answer.json()["data"]["job"]["status"] == "cancelled" and process.killed == 1
    assert not jobs.update_running(job["id"], progress=50.0, step="mix")
    assert not jobs.settle(job["id"], "done", file_name="x.mp4", file_size=1)
    assert not jobs.settle(job["id"], "failed", error_code="ffmpeg_failed", error_message="x")
    now = client.get(f"{BASE}/exports/{job['id']}").json()["data"]["job"]
    assert (now["status"], now["file"], now["error"]["code"]) == ("cancelled", None, "cancelled")


def test_cancelling_twice_while_running_kills_once_then_removes_the_job(client, project, host):
    job = _start(client, project["id"]).json()["data"]["job"]
    jobs.claim_next()
    process = jobs._PROCESSES[job["id"]] = Process()

    client.delete(f"{BASE}/exports/{job['id']}")
    second = client.delete(f"{BASE}/exports/{job['id']}")

    assert process.killed == 1 and second.json()["data"] == {"deleted": job["id"]}


def test_a_job_that_ends_a_moment_before_the_cancel_stays_done_and_is_removed_by_it(client, project, host):
    job = _start(client, project["id"]).json()["data"]["job"]
    _folder(jobs.get_job(job["id"]), 5, "x_1080p.mp4")
    _finish(job["id"])

    answer = client.delete(f"{BASE}/exports/{job['id']}")

    assert answer.json()["data"] == {"deleted": job["id"]} and jobs.get_job(job["id"]) is None


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
async def test_a_real_ffmpeg_is_killed_by_the_cancel_and_the_runner_goes_on(client, project, host, monkeypatch):
    job = _start(client, project["id"]).json()["data"]["job"]
    spawned = []

    async def render_slowly(job, project, owner, requester, report, on_process=None):
        command = [shutil.which("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats", "-f", "lavfi", "-re", "-i", "testsrc2=size=320x240:rate=25:duration=120", "-c:v", "libx264", "-f", "null", "-"]
        await video.assemble(command, 120.0, lambda share: report(share * 70, "assemble"), lambda process: (spawned.append(process), on_process(process)))

    monkeypatch.setattr(video, "render", render_slowly)
    runner = asyncio.ensure_future(jobs.RUNNER.run())
    for _ in range(100):
        if spawned:
            break
        await asyncio.sleep(0.1)
    assert spawned and spawned[0] is not None and spawned[0].returncode is None

    answer = await asyncio.to_thread(client.delete, f"{BASE}/exports/{job['id']}")
    await asyncio.wait_for(runner, timeout=20)

    assert answer.json()["data"]["job"]["status"] == "cancelled"
    assert spawned[0].returncode is not None and jobs._PROCESSES == {}
    assert jobs.get_job(job["id"])["status"] == "cancelled" and not video.job_folder(jobs.get_job(job["id"])).exists()
    assert [item for item in host.notified if item["notification_type"].endswith("export_failed")] == []


def test_the_quota_is_a_strict_bound_on_the_bytes_already_cached(client, project, host, store):
    store[("export_dir_quota_mb", None)] = "1"
    other = jobs.create_job("other-project", "user-1", "web", "720p")
    _folder(other, 1024 * 1024 - 1)

    below = _start(client, project["id"])
    client.delete(f"{BASE}/exports/{below.json()['data']['job']['id']}")
    (video.job_folder(other) / "more").write_bytes(b"\0")
    exact = _start(client, project["id"])

    assert below.status_code == 202
    assert exact.status_code == 429 and exact.json()["detail"]["data"] == {"quota_mb": 1}


def test_eviction_takes_the_oldest_finished_exports_first_and_stops_as_soon_as_the_cache_fits(client, project, host, store, job_clock):
    store[("export_dir_quota_mb", None)] = "1"
    ids = []
    for status in ("failed", "done", "cancelled", "done"):
        job = jobs.create_job("other-project", "user-1", "web", "720p")
        ids.append(job["id"])
        if status == "done":
            _folder(job, 600 * 1024, "x_1080p.mp4")
        _finish(job["id"], status)

    answer = _start(client, project["id"])

    assert answer.status_code == 202
    assert [jobs.get_job(job_id) is None for job_id in ids] == [True, True, False, False]


def test_eviction_never_touches_a_job_that_is_queued_or_running(client, project, host, store):
    store[("export_dir_quota_mb", None)] = "1"
    running = jobs.create_job("p-running", "user-1", "web", "720p")
    _folder(running, 600 * 1024)
    jobs.claim_next()
    queued = jobs.create_job("p-queued", "user-1", "web", "720p")
    _folder(queued, 600 * 1024)

    answer = _start(client, project["id"])

    assert answer.status_code == 429
    assert jobs.get_job(running["id"])["status"] == "running" and jobs.get_job(queued["id"])["status"] == "queued"
    assert video.job_folder(running).exists() and video.job_folder(queued).exists()


def test_another_users_job_cannot_be_read_downloaded_or_cancelled(app, client, project, host, make_user):
    job = _start(client, project["id"]).json()["data"]["job"]
    _folder(jobs.get_job(job["id"]), 5)
    _as(app, make_user(user_id="user-2"))

    answers = [client.get(f"{BASE}/exports/{job['id']}"), client.get(f"{BASE}/exports/{job['id']}/file"), client.delete(f"{BASE}/exports/{job['id']}")]

    assert [answer.status_code for answer in answers] == [404, 404, 404]
    assert {answer.json()["detail"]["error"] for answer in answers} == {"job_not_found"}
    assert jobs.get_job(job["id"])["status"] == "queued" and client.get(f"{BASE}/projects/{project['id']}/exports").status_code == 404


def test_an_administrator_can_cancel_the_job_of_a_user(app, client, project, host, make_user):
    job = _start(client, project["id"]).json()["data"]["job"]
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    answer = client.delete(f"{BASE}/exports/{job['id']}")

    assert answer.json()["data"]["job"]["status"] == "cancelled"


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_the_file_of_a_job_that_is_not_done_is_not_ready(client, project, host, status):
    job = _start(client, project["id"]).json()["data"]["job"]
    if status == "running":
        jobs.claim_next()
    elif status == "failed":
        _finish(job["id"], "failed")
    elif status == "cancelled":
        client.delete(f"{BASE}/exports/{job['id']}")

    answer = client.get(f"{BASE}/exports/{job['id']}/file")

    assert answer.status_code == 409 and answer.json()["detail"]["error"] == "not_ready"


def test_the_file_of_a_done_job_whose_file_is_gone_is_not_found(client, project, host):
    job = _start(client, project["id"]).json()["data"]["job"]
    folder = _folder(jobs.get_job(job["id"]), 5, "x_1080p.mp4")
    _finish(job["id"])
    (folder / "x_1080p.mp4").unlink()

    answer = client.get(f"{BASE}/exports/{job['id']}/file")

    assert answer.status_code == 404 and answer.json()["detail"]["error"] == "job_not_found"


BODIES = [
    pytest.param(None, id="no-body"),
    pytest.param([], id="list"),
    pytest.param("web", id="string"),
    pytest.param(5, id="number"),
    pytest.param({}, id="empty-object"),
    pytest.param({"format": None}, id="format-null"),
    pytest.param({"format": ["web"]}, id="format-list"),
    pytest.param({"format": {"a": 1}}, id="format-object"),
    pytest.param({"format": "WEB"}, id="format-case"),
    pytest.param({"format": "web", "resolution": 1080}, id="resolution-number"),
    pytest.param({"format": "web", "resolution": ["720p"]}, id="resolution-list"),
    pytest.param({"format": "web", "resolution": "720P"}, id="resolution-case"),
    pytest.param({"format": "web", "resolution": ""}, id="resolution-empty"),
    pytest.param({"format": "prores"}, id="format-unknown"),
    pytest.param({"format": "web", "stems": "true"}, id="stems-text"),
    pytest.param({"format": "web", "stems": None}, id="stems-null"),
]


@pytest.mark.parametrize("body", BODIES)
def test_a_malformed_export_request_is_an_invalid_request_and_queues_nothing(client, project, host, body):
    response = client.post(f"{BASE}/projects/{project['id']}/exports/video", json=body)

    assert response.status_code == 422 and response.json()["detail"]["error"] == "invalid_request"
    assert jobs.list_project(project["id"]) == []


def test_a_null_resolution_takes_the_one_of_the_project(client, project, host):
    response = _start(client, project["id"], resolution=None)

    assert response.status_code == 202 and response.json()["data"]["job"]["resolution"] == "1080p"


def test_a_resolution_the_project_does_not_know_falls_back_to_1080p(client, project):
    from backend import projects

    doc = projects.get_project(project["id"])["doc"]
    projects.save_project(project["id"], {**doc, "resolution": "8K ultra"}, projects.get_project(project["id"])["version"])

    response = _start(client, project["id"])

    assert response.json()["data"]["job"]["resolution"] == "1080p"


def test_an_export_of_an_unknown_or_foreign_project_is_not_found(app, client, project, host, make_user):
    assert _start(client, "nope").status_code == 404
    _as(app, make_user(user_id="user-2"))
    assert _start(client, project["id"]).status_code == 404


def test_when_the_application_loop_is_not_there_the_job_stays_queued_and_the_next_request_starts_it(client, project, host, monkeypatch):
    def refuse(coroutine):
        coroutine.close()
        raise RuntimeError("no application loop yet")

    monkeypatch.setattr(core_bridge, "run_on_app_loop", refuse)
    answer = _start(client, project["id"])

    assert answer.status_code == 202 and not jobs.RUNNER.active
    assert jobs.get_job(answer.json()["data"]["job"]["id"])["status"] == "queued"
    monkeypatch.setattr(core_bridge, "run_on_app_loop", host.run_on_app_loop)
    jobs.ensure_running()
    assert jobs.RUNNER.active


async def test_a_job_whose_owner_no_longer_exists_fails_instead_of_stopping_the_runner(project, host):
    job = jobs.create_job(project["id"], "ghost-user", "web", "720p")
    claimed = jobs.claim_next()

    await jobs.execute(claimed)

    done = jobs.get_job(job["id"])
    assert done["status"] == "failed" and done["error_code"] == "ffmpeg_failed"
    assert not video.job_folder(done).exists()


async def test_an_unexpected_error_in_one_job_fails_it_and_the_runner_takes_the_next(project, host, make_project, make_doc, monkeypatch):
    other = make_project(doc=make_doc())
    first = jobs.create_job(project["id"], "user-1", "web", "720p")
    second = jobs.create_job(other["id"], "user-1", "web", "720p")
    seen = []

    async def render(job, project, owner, requester, report, on_process=None):
        seen.append(job["id"])
        if job["id"] == first["id"]:
            raise RuntimeError("boom\nsecond line of the trace")
        return {"file_name": "x.mp4", "file_size": 1, "media_item_id": "m", "media_url": "/u"}

    monkeypatch.setattr(video, "render", render)

    await jobs.RUNNER.run()

    assert seen == [first["id"], second["id"]]
    failed = jobs.get_job(first["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "ffmpeg_failed", "second line of the trace")
    assert jobs.get_job(second["id"])["status"] == "done" and not jobs.RUNNER.active


class Frames:
    def __init__(self):
        self.asked = []
        self.error = None
        self.item = {"item_id": "item-1", "filename": "f.png", "width": 832, "height": 480}

    async def extract_frame(self, user, ref, at="last"):
        self.asked.append((user.id, dict(ref), at))
        if self.error is not None:
            raise self.error
        return {"value": "uploads/7d1e.png", "media_type": "image", "original_filename": "f.png", "origin": None}

    def upload_item(self, user_id, value):
        return self.item


SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}, {"id": "s3", "start": 8, "dur": 4}]


@pytest.fixture
def frames(core, monkeypatch):
    found = Frames()
    monkeypatch.setattr(core_bridge, "extract_frame", found.extract_frame)
    monkeypatch.setattr(core_bridge, "upload_item", found.upload_item)
    return found


@pytest.fixture
def storyboard(core, make_project):
    return make_project(clips=SHOTS)


def _take(project_id, shot_id, generation_id="g-1", status="done", file_id="UNSET"):
    done = status == "done"
    return takes.create_take(
        {
            "project_id": project_id,
            "shot_id": shot_id,
            "user_id": "user-1",
            "quality": "draft",
            "kind": "render",
            "status": status,
            "generation_id": generation_id,
            "file_id": (f"f-{generation_id}" if done else None) if file_id == "UNSET" else file_id,
            "file_path": f"generations/2026-10-17/{generation_id}/1.mp4" if done else None,
        }
    )


def _seam(client, project_id, shot_id="s2", body=None, raw=None):
    url = f"{BASE}/projects/{project_id}/shots/{shot_id}/seam-frame"
    if raw is not None:
        return client.post(url, content=raw, headers={"content-type": "application/json"})
    return client.post(url, json=body)


def test_the_first_shot_has_no_frame_to_take_from_before_it(client, storyboard, frames):
    _take(storyboard["id"], "s1")

    response = _seam(client, storyboard["id"], shot_id="s1")

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_previous_take"
    assert frames.asked == []


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_a_previous_shot_whose_takes_are_not_finished_has_no_previous_take(client, storyboard, frames, status):
    _take(storyboard["id"], "s1", status=status)

    response = _seam(client, storyboard["id"])

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_previous_take"


def test_a_legacy_take_without_a_file_id_is_not_a_source_of_frames(client, storyboard, frames):
    _take(storyboard["id"], "s1", file_id=None)

    response = _seam(client, storyboard["id"])

    assert response.status_code == 409 and frames.asked == []


@pytest.mark.parametrize("at", [0, -0.0, 0.04, 3.5, 9999, 1e308])
def test_any_non_negative_instant_goes_to_the_core_unchanged_even_past_the_end_of_the_take(client, storyboard, frames, at):
    take = _take(storyboard["id"], "s1")

    response = _seam(client, storyboard["id"], body={"source": {"take_id": take["id"], "at": at}})

    assert response.status_code == 200 and frames.asked[0][2] == at


@pytest.mark.parametrize("raw", ['1e999', '-1e999', 'NaN', 'Infinity', '-Infinity', '-0.001', '"10"', '"NaN"', 'null', 'true', '[]', '{}'])
def test_an_instant_that_is_not_finite_or_not_a_number_is_an_invalid_request(client, storyboard, frames, raw):
    take = _take(storyboard["id"], "s1")

    response = _seam(client, storyboard["id"], raw=f'{{"source": {{"take_id": "{take["id"]}", "at": {raw}}}}}')

    assert response.status_code == 422 and response.json()["detail"]["error"] == "invalid_request"
    assert frames.asked == []


@pytest.mark.parametrize("code", ["invalid_ref", "not_found", "not_a_video", "extract_failed", "invalid_purpose", "upload_rejected", "something_new"])
def test_every_code_of_the_core_comes_back_as_a_502_extract_failed_carrying_it(client, storyboard, frames, code):
    _take(storyboard["id"], "s1")
    frames.error = MediaRefError(code, f"core said {code}")

    response = _seam(client, storyboard["id"])

    detail = response.json()["detail"]
    assert response.status_code == 502
    assert (detail["error"], detail["data"], detail["message"]) == ("extract_failed", {"code": code}, f"core said {code}")


def test_a_full_storage_plan_comes_back_as_a_502_extract_failed(client, storyboard, frames):
    _take(storyboard["id"], "s1")
    frames.error = LimitExceeded([{"message": "plan full"}], "storage", None)

    response = _seam(client, storyboard["id"])

    assert response.status_code == 502 and response.json()["detail"]["data"] == {"code": "limit_exceeded"}


def test_a_frame_stored_without_a_library_item_is_not_announced_as_a_success(client, storyboard, frames):
    _take(storyboard["id"], "s1")
    frames.item = None

    response = _seam(client, storyboard["id"])

    assert response.status_code != 200 or response.json()["data"]["media"]["item_id"]


def test_a_chosen_take_that_belongs_to_another_shot_is_ignored(client, storyboard, frames):
    from backend import projects

    wrong = _take(storyboard["id"], "s3", "g-wrong")
    right = _take(storyboard["id"], "s1", "g-right")
    stored = projects.get_project(storyboard["id"])
    doc = {**stored["doc"], "clips": [{**clip, "take": wrong["id"]} if clip["id"] == "s1" else clip for clip in stored["doc"]["clips"]]}
    projects.save_project(storyboard["id"], doc, stored["version"])

    response = _seam(client, storyboard["id"])

    assert response.status_code == 200 and frames.asked[0][1]["generation_id"] == right["generation_id"]


def test_a_take_deleted_after_it_was_chosen_falls_back_to_the_latest_finished_take(client, storyboard, frames):
    from backend import projects

    first = _take(storyboard["id"], "s1", "g-1")
    second = _take(storyboard["id"], "s1", "g-2")
    stored = projects.get_project(storyboard["id"])
    doc = {**stored["doc"], "clips": [{**clip, "take": "gone"} if clip["id"] == "s1" else clip for clip in stored["doc"]["clips"]]}
    projects.save_project(storyboard["id"], doc, stored["version"])

    response = _seam(client, storyboard["id"])

    assert response.status_code == 200 and frames.asked[0][1]["generation_id"] == second["generation_id"] != first["generation_id"]
