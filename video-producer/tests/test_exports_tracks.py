import asyncio
import json

import pytest

from backend.exports import render, video
from backend.exports.video import audible, build_command, clip_heard, filter_graph
from backend.projects import DocError, migrate, validate_doc

PATHS = {"ffmpeg": "/usr/bin/ffmpeg", "output": "/tmp/out/mezzanine.mp4", "graph": "/tmp/out/graph.txt"}

SHOT = {"name": "1.mp4", "path": "/media/1.mp4"}

ULIDS = ["01JB0000000000000000000001", "01JB0000000000000000000002", "01JB0000000000000000000003"]


def _options(audio=None, **probed):
    return {"format": "web", "resolution": "720p", "audio": audio or {}, "stills": [], **probed}


def _graph(doc, files, sounds=None, **options):
    return filter_graph(doc, files, _options(**options), {**PATHS, "audio": sounds or {}}).split(";")


def _inputs(doc, files, sounds=None, **options):
    command = build_command(doc, files, _options(**options), {**PATHS, "audio": sounds or {}})
    return [command[index + 1] for index, item in enumerate(command) if item == "-i"]


def _doc(make_doc, clips, audio=(), lanes=None, video_track=None):
    doc = make_doc(clips=clips)
    doc["audio"] = [
        {"id": f"u{index}", "assetId": None, "lane": "A1", "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **item}
        for index, item in enumerate(audio)
    ]
    for lane_id, changes in (lanes or {}).items():
        doc["lanes"] = [{**lane, **changes} if lane["id"] == lane_id else lane for lane in doc["lanes"]]
    if video_track is not None:
        doc["video"] = video_track
    return doc


def _mixed(make_doc, clips=({"id": "c1", "start": 0, "dur": 2},), **fields):
    doc = _doc(make_doc, list(clips), audio=[{"id": "voice", "lane": "A1"}, {"id": "music", "lane": "A2"}], **fields)
    return doc, {"voice": "/v.wav", "music": "/m.wav"}


def _shot_sound(graph, index=0):
    return next(chain for chain in graph if chain.endswith(f"[a{index}]"))


def test_an_audio_item_whose_lane_is_gone_is_silent_as_in_the_preview(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "dur": 1}], audio=[{"id": "voice", "lane": "A1"}, {"id": "orphan", "lane": "gone"}])
    sounds = {"voice": "/v.wav", "orphan": "/o.wav"}

    assert [item["id"] for item, _ in audible(doc)] == ["voice"]
    assert _inputs(doc, {"c1": None}, sounds=sounds) == ["/v.wav"]


def test_with_every_lane_deleted_only_the_shots_are_heard(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2}], audio=[{"id": "voice", "lane": "A1"}])
    doc["lanes"] = []

    assert audible(doc) == []
    assert _inputs(doc, {"c1": SHOT}, sounds={"voice": "/v.wav"}, audio={"c1": True}) == ["/media/1.mp4"]
    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds={"voice": "/v.wav"}, audio={"c1": True})).startswith("[0:a]atrim=")


def test_a_document_from_before_the_video_track_plays_the_shot_sound(make_doc):
    doc, sounds = _mixed(make_doc)

    assert "video" not in doc and "mute" not in doc["clips"][0]
    assert clip_heard(doc, doc["clips"][0])
    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True})).startswith("[0:a]atrim=start=0:duration=2,")
    assert _inputs(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True}) == ["/media/1.mp4", "/v.wav", "/m.wav"]


def test_a_muted_video_track_silences_every_shot_and_leaves_the_lanes(make_doc):
    clips = [{"id": "c1", "start": 0, "dur": 1}, {"id": "c2", "start": 1, "dur": 1}]
    doc, sounds = _mixed(make_doc, clips, video_track={"mute": True, "solo": False})
    files = {"c1": SHOT, "c2": {"name": "2.mp4", "path": "/media/2.mp4"}}

    graph = _graph(doc, files, sounds=sounds, audio={"c1": True, "c2": True})

    assert _shot_sound(graph, 0) == "anullsrc=r=48000:cl=stereo,atrim=duration=1[a0]"
    assert _shot_sound(graph, 1) == "anullsrc=r=48000:cl=stereo,atrim=duration=1[a1]"
    assert _inputs(doc, files, sounds=sounds, audio={"c1": True, "c2": True}) == ["/media/1.mp4", "/media/2.mp4", "/v.wav", "/m.wav"]


def test_a_muted_shot_is_silent_and_the_next_shot_keeps_its_sound(make_doc):
    clips = [{"id": "c1", "start": 0, "dur": 1, "mute": True}, {"id": "c2", "start": 1, "dur": 1}]
    doc = _doc(make_doc, clips)
    files = {"c1": SHOT, "c2": {"name": "2.mp4", "path": "/media/2.mp4"}}

    graph = _graph(doc, files, audio={"c1": True, "c2": True})

    assert _shot_sound(graph, 0) == "anullsrc=r=48000:cl=stereo,atrim=duration=1[a0]"
    assert _shot_sound(graph, 1).startswith("[1:a]atrim=start=0:duration=1,")


def test_a_muted_shot_without_picture_opens_no_file(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2, "mute": True}])
    files = {"c1": {"name": "v.wav", "path": "/media/v.wav"}}

    assert _inputs(doc, files, audio={"c1": True}, blind=["c1"]) == []
    assert _graph(doc, files, audio={"c1": True}, blind=["c1"])[:2] == [
        "color=c=black:s=1280x720:r=25:d=2,setsar=1,format=yuv420p[v0]",
        "anullsrc=r=48000:cl=stereo,atrim=duration=2[a0]",
    ]


def test_a_soloed_audio_lane_silences_the_shots(make_doc):
    doc, sounds = _mixed(make_doc, lanes={"A1": {"solo": True}})

    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True})) == "anullsrc=r=48000:cl=stereo,atrim=duration=2[a0]"
    assert _inputs(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True}) == ["/media/1.mp4", "/v.wav"]


def test_a_soloed_video_track_silences_the_lanes_and_keeps_the_shots(make_doc):
    doc, sounds = _mixed(make_doc, video_track={"mute": False, "solo": True})

    assert audible(doc) == []
    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True})).startswith("[0:a]atrim=")
    assert _inputs(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True}) == ["/media/1.mp4"]


def test_a_soloed_video_track_and_a_soloed_lane_play_together(make_doc):
    doc, sounds = _mixed(make_doc, lanes={"A2": {"solo": True}}, video_track={"mute": False, "solo": True})

    assert [item["id"] for item, _ in audible(doc)] == ["music"]
    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True})).startswith("[0:a]atrim=")
    assert _inputs(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True}) == ["/media/1.mp4", "/m.wav"]


def test_mute_wins_over_solo_on_the_video_track(make_doc):
    doc, sounds = _mixed(make_doc, video_track={"mute": True, "solo": True})

    assert audible(doc) == []
    assert _shot_sound(_graph(doc, {"c1": SHOT}, sounds=sounds, audio={"c1": True})) == "anullsrc=r=48000:cl=stereo,atrim=duration=2[a0]"


def test_the_shot_sound_follows_the_fades_of_its_shot(make_doc):
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2.5, "srcIn": 0.5, "fadeIn": 0.4, "fadeOut": 0.6}])

    assert _shot_sound(_graph(doc, {"c1": SHOT}, audio={"c1": True})) == (
        "[0:a]atrim=start=0.5:duration=2.5,asetpts=PTS-STARTPTS,aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,apad=whole_dur=2.5,atrim=duration=2.5,"
        "afade=t=in:st=0:d=0.4,afade=t=out:st=1.9:d=0.6[a0]"
    )


def test_the_premix_of_many_items_keeps_the_solo_so_the_soloed_shots_and_lanes_stay_heard(make_doc, monkeypatch, tmp_path):
    async def ran(*args, **kwargs):
        return None

    monkeypatch.setattr(video, "MIX_INPUTS", 1)
    monkeypatch.setattr(video, "assemble", ran)
    doc = _doc(
        make_doc,
        [{"id": "c1", "start": 0, "dur": 2}],
        audio=[{"id": "voice", "lane": "A1"}, {"id": "more", "lane": "A1"}, {"id": "music", "lane": "A2"}],
        lanes={"A1": {"solo": True}},
        video_track={"mute": False, "solo": True},
    )
    sounds = {"voice": str(tmp_path / "v.wav"), "more": str(tmp_path / "w.wav"), "music": str(tmp_path / "m.wav")}

    mixed, files = asyncio.run(video._premix(doc, sounds, {**PATHS, "graph_option": "-/filter_complex"}, tmp_path, 2.0, None))

    assert sorted(files) == ["lanes-0", "lanes-1"]
    assert [item["id"] for item, _ in audible(mixed)] == ["lanes-0", "lanes-1"]
    assert clip_heard(mixed, doc["clips"][0])


def test_without_any_solo_the_premix_does_not_turn_one_on(make_doc, monkeypatch, tmp_path):
    async def ran(*args, **kwargs):
        return None

    monkeypatch.setattr(video, "MIX_INPUTS", 1)
    monkeypatch.setattr(video, "assemble", ran)
    doc = _doc(make_doc, [{"id": "c1", "start": 0, "dur": 2}], audio=[{"id": "voice", "lane": "A1"}, {"id": "music", "lane": "A2"}])
    sounds = {"voice": str(tmp_path / "v.wav"), "music": str(tmp_path / "m.wav")}

    mixed, _ = asyncio.run(video._premix(doc, sounds, {**PATHS, "graph_option": "-/filter_complex"}, tmp_path, 2.0, None))

    assert mixed["lanes"] == [{"id": "lanes", "vol": 0, "solo": False}]
    assert clip_heard(mixed, doc["clips"][0])


def test_the_otio_names_the_audio_tracks_by_position_whatever_their_ids(make_doc):
    doc = make_doc()
    doc["lanes"] = [{**lane, "id": ULIDS[index]} for index, lane in enumerate(doc["lanes"][:3])]
    doc["audio"] = [{"id": "u1", "assetId": None, "lane": ULIDS[2], "start": 0, "dur": 1, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0}]

    tracks = json.loads(render("otio", doc, {}))["tracks"]["children"][1:]
    del doc["lanes"][1]
    after = json.loads(render("otio", doc, {}))["tracks"]["children"][1:]

    assert [track["name"].split(" · ")[0] for track in tracks] == ["A1", "A2", "A3"]
    assert [track["name"].split(" · ")[0] for track in after] == ["A1", "A2"]
    assert [len(track["children"]) for track in after] == [0, 1]


def test_the_video_track_and_the_shot_mute_are_valid_and_need_no_migration(make_doc):
    doc = make_doc(clips=[{"id": "c1", "mute": True}, {"id": "c2", "mute": False}])
    doc["video"] = {"mute": False, "solo": True}
    doc["lanes"] = [{**lane, "id": ULIDS[index]} for index, lane in enumerate(doc["lanes"][:3])]

    validate_doc(doc)
    assert migrate(doc) is doc


@pytest.mark.parametrize(
    "change",
    [
        lambda doc: doc.update(video={"mute": False}),
        lambda doc: doc.update(video={"mute": False, "solo": False, "vol": 0}),
        lambda doc: doc.update(video={"mute": "no", "solo": False}),
        lambda doc: doc["clips"][0].update(mute=None),
    ],
)
def test_a_malformed_video_track_or_shot_mute_is_refused(make_doc, change):
    doc = make_doc(clips=[{"id": "c1"}])
    change(doc)

    with pytest.raises(DocError):
        validate_doc(doc)
