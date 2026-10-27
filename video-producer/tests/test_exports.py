import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from backend.core_bridge import MediaRefError
from backend.exports import EXCHANGE, content_disposition, render, slug
from backend.exports.common import Timebase, js_json, js_number, js_round, seq_duration, timing_error
from backend.exports.media import file_of, files_of, url_basename

FOLDER = Path(__file__).resolve().parent / "fixtures" / "exports"
STORAGE = "/srv/potionui/storage"
FORMATS = ("fcpxml", "otio", "edl", "srt")


class FixtureResolver:
    def __init__(self, uploads, history=None):
        self.uploads = {upload["item_id"]: upload for upload in uploads}
        self.history = history or {}
        self.asked = []

    def resolve(self, ref):
        self.asked.append(dict(ref))
        if ref["kind"] == "history" and (ref["generation_id"], ref["file_id"]) in self.history:
            value = self.history[(ref["generation_id"], ref["file_id"])]
            return {"value": value, "media_type": "video", "original_filename": value.rsplit("/", 1)[-1], "origin": None}
        upload = self.uploads.get(ref.get("item_id")) if ref["kind"] == "library" else None
        if upload is None:
            raise MediaRefError("not_found", "The referenced media is not available")
        return {
            "value": upload["value"],
            "media_type": upload["media_type"],
            "original_filename": upload["original_filename"],
            "origin": None,
        }

    def path(self, kind, value):
        return f"{STORAGE}/{value}"


@pytest.fixture(scope="module")
def fixture():
    return json.loads((FOLDER / "reference-project.json").read_text(encoding="utf-8"))


@pytest.fixture
def resolver(fixture):
    return FixtureResolver(fixture["uploads"])


def _files(fixture, resolver, media="name"):
    return files_of(fixture["doc"], fixture["takes"], resolver, media=media)


def _clip(fixture, index):
    return fixture["doc"]["clips"][index]


@pytest.mark.parametrize("fmt", FORMATS)
def test_each_format_matches_its_golden_file_byte_for_byte(fixture, resolver, fmt):
    expected = (FOLDER / f"reference.{fmt}").read_bytes()

    assert render(fmt, fixture["doc"], _files(fixture, resolver)).encode("utf-8") == expected


def test_the_fixture_is_a_document_the_plugin_stores(fixture):
    from backend import projects

    projects.validate_doc(fixture["doc"])
    doc = fixture["doc"]
    assert len(doc["clips"]) == 4 and sum(1 for clip in doc["clips"] if clip["assetId"] is None) == 1
    assert [clip["stage"] for clip in doc["clips"]].count("source") == 1
    assert len({item["lane"] for item in doc["audio"]}) == 2 and len(doc["titles"]) == 2
    assert not any(key in asset for asset in doc["assets"] for key in ("synth", "transcript", "character", "lipSync"))


def test_the_fcpxml_is_well_formed_and_every_clip_points_at_a_declared_asset(fixture, resolver):
    text = render("fcpxml", fixture["doc"], _files(fixture, resolver))

    root = ElementTree.fromstring(text.encode("utf-8"))

    assert root.tag == "fcpxml" and root.get("version") == "1.10"
    declared = {element.get("id") for element in root.find("resources")}
    clips = root.findall(".//spine/asset-clip")
    assert len(clips) == 3 and len(root.findall(".//spine/gap")) == 1
    assert all(clip.get("ref") in declared for clip in clips)
    durations = [element.get(name) for element in root.iter() for name in ("duration", "offset", "start") if element.get(name)]
    assert all(re.fullmatch(r"\d+/25s|0s", value) for value in durations)


def test_the_otio_is_a_timeline_of_one_video_track_and_one_track_per_lane(fixture, resolver):
    timeline = json.loads(render("otio", fixture["doc"], _files(fixture, resolver)))

    assert timeline["OTIO_SCHEMA"] == "Timeline.1" and timeline["tracks"]["OTIO_SCHEMA"] == "Stack.1"
    video, *audio = timeline["tracks"]["children"]
    assert (video["name"], video["kind"]) == ("V1", "Video")
    assert [item["OTIO_SCHEMA"] for item in video["children"]] == ["Clip.2", "Clip.2", "Gap.1", "Clip.2"]
    assert [track["name"] for track in audio] == ["A1 · Dialogue", "A2 · Music", "A3 · Ambience", "A4 · SFX"]
    assert [item["OTIO_SCHEMA"] for item in audio[0]["children"]] == ["Gap.1", "Clip.2", "Gap.1", "Clip.2"]


def test_the_otio_reads_with_opentimelineio(fixture, resolver):
    otio = pytest.importorskip("opentimelineio")

    timeline = otio.adapters.read_from_string(render("otio", fixture["doc"], _files(fixture, resolver)), "otio_json")

    assert len(timeline.tracks) == 5 and len(timeline.video_tracks()[0]) == 4


def test_the_edl_has_one_cmx_event_per_shot_and_bl_for_a_shot_without_file(fixture, resolver):
    text = render("edl", fixture["doc"], _files(fixture, resolver))

    lines = text.split("\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert lines[:2] == ["TITLE: AUBE & MARÉE", "FCM: NON-DROP FRAME"]
    events = [line for line in lines if re.fullmatch(r"\d{3}  \S+ +V {5}C {8}(\d\d:\d\d:\d\d:\d\d ?){4}", line)]
    assert [event.split()[1] for event in events] == ["VP001", "VP002", "BL", "VP004"]
    assert sum(line.startswith("* SOURCE FILE: ") for line in lines) == 3


def test_the_srt_numbers_its_cues_in_time_order(fixture, resolver):
    text = render("srt", fixture["doc"], {})

    blocks = text.strip("\n").split("\n\n")
    assert [block.split("\n")[0] for block in blocks] == ["1", "2"]
    assert all(re.fullmatch(r"\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}", block.split("\n")[1]) for block in blocks)
    assert blocks[1].split("\n")[2] == "Fin"


def test_the_srt_holds_the_titles_alone_whatever_the_locale(fixture):
    text = render("srt", fixture["doc"], {})

    assert render("srt", fixture["doc"], {}, locale="fr") == text
    assert "Marin" not in text


def test_a_take_names_its_real_file_and_gives_its_path_on_the_server(fixture, resolver):
    entry = file_of(fixture["doc"], _clip(fixture, 0), fixture["takes"], resolver)

    take = fixture["takes"][1]
    assert entry == {"name": "1.mp4", "path": f"{STORAGE}/{take['file_path']}"}
    assert resolver.asked == []


def test_a_library_source_names_its_stored_file_like_the_page_does(fixture, resolver):
    entry = file_of(fixture["doc"], _clip(fixture, 3), fixture["takes"], resolver)

    upload = fixture["uploads"][0]
    assert entry == {"name": upload["value"].split("/")[1], "path": upload["path"]}
    assert entry["name"] == url_basename(fixture["doc"]["assets"][2]["src"])
    assert resolver.asked == [{"kind": "library", "item_id": upload["item_id"]}]


def test_a_shot_without_asset_or_without_file_has_none(fixture, resolver, make_doc):
    doc = make_doc(
        clips=[{"id": "c1"}, {"id": "c2", "assetId": "a-empty"}, {"id": "c3", "assetId": "a-missing"}],
        assets=[{"id": "a-empty", "kind": "video", "name": "Placeholder"}],
    )

    assert [file_of(doc, clip, [], resolver) for clip in doc["clips"]] == [None, None, None]


def test_a_generated_asset_whose_take_is_unknown_keeps_the_prototype_name(resolver, make_doc):
    doc = make_doc(
        clips=[{"id": "c1", "assetId": "a1", "label": "Dawn · wide"}],
        assets=[{"id": "a1", "kind": "video", "name": "Take", "generated": True, "quality": "draft", "resultId": "r9"}],
    )

    assert file_of(doc, doc["clips"][0], [], resolver) == {"name": "Dawn_wide_draft_r9.mov", "path": "Dawn_wide_draft_r9.mov"}


def test_an_origin_that_no_longer_resolves_falls_back_to_the_name_in_its_url(resolver, make_doc):
    doc = make_doc(
        clips=[{"id": "c1", "assetId": "a1"}],
        assets=[{"id": "a1", "kind": "video", "name": "Gone", "src": "/api/media/uploads/my%20clip.mp4?t=1", "origin": {"kind": "library", "itemId": "lost"}}],
    )

    assert file_of(doc, doc["clips"][0], [], resolver) == {"name": "my clip.mp4", "path": "my clip.mp4"}


def test_a_history_source_that_is_not_a_take_resolves_through_its_origin(make_doc):
    resolver = FixtureResolver([], history={("g-9", "f-9"): "generations/2026-10-01/g-9/0.mp4"})
    doc = make_doc(
        clips=[{"id": "c1", "assetId": "a1"}],
        assets=[{"id": "a1", "kind": "video", "name": "Old", "origin": {"kind": "history", "generationId": "g-9", "fileId": "f-9"}}],
    )

    assert file_of(doc, doc["clips"][0], [], resolver) == {"name": "0.mp4", "path": f"{STORAGE}/generations/2026-10-01/g-9/0.mp4"}


def test_a_take_without_file_or_not_done_is_not_the_file_of_its_asset(fixture, resolver):
    takes = [{**take, "status": "failed"} if take["id"] == fixture["takes"][1]["id"] else take for take in fixture["takes"]]

    entry = file_of(fixture["doc"], _clip(fixture, 0), takes, resolver)

    assert entry == {"name": "1.mp4", "path": "1.mp4"}


def test_media_name_writes_names_and_media_path_writes_real_paths(fixture, resolver):
    by_name = _files(fixture, resolver, media="name")
    by_path = _files(fixture, resolver, media="path")

    assert [by_name[("clips", index)] and by_name[("clips", index)]["path"] for index in range(4)] == ["1.mp4", "1.mp4", None, "03927418-58f2-440f-9a15-456093037531.mp4"]
    assert [by_name[("audio", index)]["path"] for index in range(3)] == [upload["value"].split("/")[1] for upload in (fixture["uploads"][2], fixture["uploads"][1], fixture["uploads"][3])]
    assert all(entry is None or entry["path"].startswith(f"{STORAGE}/") for entry in by_path.values())
    edl = render("edl", fixture["doc"], by_path)
    assert f"* SOURCE FILE: {STORAGE}/generations/2026-10-17/" in edl
    otio = json.loads(render("otio", fixture["doc"], by_path))
    assert otio["tracks"]["children"][0]["children"][3]["media_references"]["DEFAULT_MEDIA"]["target_url"] == f"{STORAGE}/uploads/03927418-58f2-440f-9a15-456093037531.mp4"
    assert otio["tracks"]["children"][1]["children"][1]["media_references"]["DEFAULT_MEDIA"]["target_url"] == f"{STORAGE}/{fixture['uploads'][1]['value']}"


def test_fcpxml_writes_a_real_path_as_a_percent_encoded_file_url(make_doc):
    doc = make_doc(clips=[{"id": "c1", "assetId": "a1"}], assets=[{"id": "a1", "kind": "video", "name": "x"}])
    files = {("clips", 0): {"name": "plan été & co.mp4", "path": "/srv/store/plan été & co.mp4"}}

    text = render("fcpxml", doc, files)

    assert 'src="file:///srv/store/plan%20%C3%A9t%C3%A9%20&amp;%20co.mp4"' in text
    ElementTree.fromstring(text.encode("utf-8"))


def test_the_timebase_rounds_like_javascript_and_writes_non_drop_timecodes():
    assert [js_round(value) for value in (2.5, 3.5, -2.5, 0.49999999999999994, 87.5)] == [3, 4, -2, 0, 88]
    time = Timebase({"fps": 25})
    assert (time.rational(4.2), time.timecode(3725.52), time.frames(0.02)) == ("105/25s", "01:02:05:13", 1)
    assert Timebase({"fps": 24.0}).rational(1) == "24/24s"
    assert Timebase({"fps": 23.976}).rational(1) == "24/23.976s"


def test_numbers_and_json_are_written_the_way_javascript_writes_them():
    assert [js_number(value) for value in (25.0, -1.5, 0.1, 1e-7, 1e21, 123456789012345680000.0, 5e-7, 0.000001)] == [
        "25", "-1.5", "0.1", "1e-7", "1e+21", "123456789012345680000", "5e-7", "0.000001",
    ]
    assert js_json({"a": [], "b": {}, "c": [1, {"d": None}]}) == '{\n  "a": [],\n  "b": {},\n  "c": [\n    1,\n    {\n      "d": null\n    }\n  ]\n}'


def test_timing_error_names_a_frame_rate_or_a_time_that_cannot_be_counted(make_doc):
    doc = make_doc(clips=[{"id": "c1", "dur": 2}], assets=[{"id": "a1", "srcDur": 6}])
    huge = {**doc, "clips": [{**doc["clips"][0], "dur": 1e308}]}

    assert timing_error(doc) is None and timing_error({**doc, "fps": 0}, frames=False) is None
    assert {timing_error({**doc, "fps": fps}) for fps in (0, -25, True, None, "25", 10**400)} == {"$.fps: must be a positive number of frames per second"}
    assert timing_error(huge) == timing_error(huge, frames=False) == "$.clips[0]: its times are too large to be counted"
    assert timing_error({**doc, "titles": [{"id": "t1", "text": "", "sub": "", "start": 10**400, "dur": 1}]}) == "$.titles[0]: its times must be finite numbers"
    assert timing_error({**doc, "assets": [{"id": "a1", "srcDur": 1e307}]}) == "$.assets[0].srcDur: too large to be counted"


def test_the_sequence_lasts_at_least_one_second(make_doc):
    assert seq_duration(make_doc()) == 1
    assert seq_duration(make_doc(clips=[{"id": "c1", "start": 2, "dur": 3.5}])) == 5.5


def test_the_slug_is_ascii_and_the_header_carries_the_utf8_name_too():
    assert slug("Aube sur le port") == "Aube_sur_le_port"
    assert slug("Aube & marée / v2") == "Aube_maree_v2"
    assert slug("東京") == "video-producer" and slug("") == "video-producer"
    assert content_disposition("Aube & marée", "edl") == (
        "attachment; filename=\"Aube_maree.edl\"; filename*=UTF-8''Aube_%26_mar%C3%A9e.edl"
    )


def test_the_four_formats_have_their_content_types():
    assert {fmt: target.content_type for fmt, target in EXCHANGE.items()} == {
        "fcpxml": "application/xml",
        "otio": "application/json",
        "edl": "text/plain; charset=utf-8",
        "srt": "application/x-subrip",
    }
