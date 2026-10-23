import asyncio
import copy
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from backend import core_bridge, director, presets, soundtrack, takes
from backend.projects import DocError, validate_doc

BASE = "/api/plugins/video-producer"
RATE = 48000
HAS_FFMPEG = bool(shutil.which("ffmpeg"))
SHOT = {"id": "s1", "start": 2, "dur": 3, "label": "Harbour"}
LIBRARY = {"voice": "lib-voice", "music": "lib-music", "hero": "lib-hero", "rain": "lib-rain", "wind": "lib-wind"}


def _tone(path: Path, seconds: float, frequency: float = 440.0, amplitude: float = 0.5) -> Path:
    frames = int(seconds * RATE)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        data = bytearray()
        for index in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * index / RATE))
            data += struct.pack("<hh", value, value)
        handle.writeframes(bytes(data))
    return path


def _samples(path: Path, rate: int = RATE):
    with wave.open(str(path), "rb") as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (2, 2, rate)
        raw = handle.readframes(handle.getnframes())
    left = struct.unpack(f"<{len(raw) // 2}h", raw)[0::2]
    return [value / 32767 for value in left]


def _rms(samples, start: float, end: float) -> float:
    part = samples[int(start * RATE) : int(end * RATE)]
    return math.sqrt(sum(value * value for value in part) / len(part))


def _item(item_id, lane, start, dur, asset="voice", **fields):
    return {"id": item_id, "assetId": asset, "lane": lane, "start": start, "dur": dur, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, **fields}


def _sound_asset(asset_id, kind="audio"):
    return {"id": asset_id, "kind": kind, "name": f"{asset_id}.wav", "origin": {"kind": "library", "itemId": LIBRARY[asset_id]}, "srcDur": 8.0}


def _doc(make_doc, items=(), reference_lanes=("A1",), references=(), assets=("voice", "music"), mode="FL2VA", **lanes):
    doc = make_doc(
        clips=[SHOT],
        prompts=[{"id": "p", "shotId": "s1", "text": "Waves hit the harbour wall."}],
        references=list(references),
        assets=[_sound_asset(name) if name != "hero" else {**_sound_asset("hero", "image"), "name": "hero.png"} for name in assets],
        direction={"mode": mode},
    )
    doc["audio"] = list(items)
    for lane in doc["lanes"]:
        if lane["id"] in reference_lanes:
            lane["reference"] = True
        lane.update(lanes.get(lane["id"], {}))
    return doc


def _media(core):
    for name, item_id in LIBRARY.items():
        core.add_media({"kind": "library", "item_id": item_id}, f"uploads/{name}.{'png' if name == 'hero' else 'wav'}", "image" if name == "hero" else "audio")


def _plans(core, doc, preset_id, **options):
    return director.build_plans(core.users["user-1"], doc, ["s1"], preset_id, "draft", **options)


def _sound(plans):
    return [warning for warning in plans.warnings if warning["code"].startswith("audio_")]


def _codes(plans):
    return [warning["code"] for warning in _sound(plans)]


@pytest.fixture
def sounds(tmp_path, monkeypatch):
    folder = tmp_path / "sources"
    folder.mkdir()
    files = {name: _tone(folder / f"{name}.wav", 8.0, frequency) for name, frequency in (("voice", 440.0), ("music", 660.0), ("rain", 330.0), ("wind", 220.0))}

    def local(kind, value, target):
        return files.get(Path(value).stem)

    monkeypatch.setattr(core_bridge, "local_media_file", local)
    return files


@pytest.fixture
def stored(monkeypatch, tmp_path):
    saved = []

    async def save(user, path):
        keep = tmp_path / "library" / Path(path).name
        keep.parent.mkdir(exist_ok=True)
        shutil.copy(path, keep)
        saved.append(keep)
        return {"value": f"uploads/{keep.name}", "media_type": "audio", "original_filename": keep.name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save)
    return saved


def test_the_margin_is_read_from_the_project_and_held_between_0_and_10_seconds(make_doc):
    doc = make_doc()
    assert director.reference_margin(doc) == 0.0
    for given, read in ((2.5, 2.5), (-1, 0.0), (50, 10.0), (True, 0.0), ("3", 0.0), (float("nan"), 0.0)):
        doc["engine"]["referenceMargin"] = given
        assert director.reference_margin(doc) == read


def test_a_guided_cut_takes_the_margin_on_both_sides_and_never_starts_before_zero(make_doc):
    doc = make_doc()
    doc["engine"]["referenceMargin"] = 1.5
    assert director.condition_window(doc, {"start": 2, "dur": 3}, 3.0) == (0.5, 6.5)
    assert director.condition_window(doc, {"start": 1, "dur": 3}, 3.0) == (0.0, 5.5)
    assert director.mux_window({"start": 2, "dur": 3}, 3.0) == (2.0, 5.0)


def test_the_cut_graph_plays_each_item_of_the_tracks_at_its_place_with_its_gain_and_fades_over_silence(make_doc):
    doc = _doc(
        make_doc,
        [
            _item("before", "A1", 0, 3, srcIn=1.5, gain=-6, fadeIn=0.5),
            _item("inside", "A1", 4, 0.5, gain=-3, fadeOut=0.2),
            _item("after", "A1", 9, 1),
            _item("other", "A2", 2, 3),
        ],
        A1={"vol": -2},
    )

    inputs, graph = soundtrack.mix_graph(doc, ["A1"], 2.0, 6.0, {"before": "/a.wav", "inside": "/b.wav", "after": "/c.wav", "other": "/d.wav"})

    assert inputs == ["-i", "/a.wav", "-i", "/b.wav"]
    assert graph.split(";") == [
        "anullsrc=r=48000:cl=stereo,atrim=duration=4[bed]",
        "[0:a]atrim=start=1.5:duration=3,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-8dB,afade=t=in:st=0:d=0.5,atrim=start=2,asetpts=PTS-STARTPTS,adelay=delays=0:all=1[m0]",
        "[1:a]atrim=start=0:duration=0.5,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-5dB,afade=t=out:st=0.3:d=0.2,adelay=delays=2000:all=1[m1]",
        "[bed][m0][m1]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[aout]",
    ]


def test_a_mixed_cut_adds_the_audio_references_from_their_beginning(make_doc):
    doc = _doc(make_doc, [_item("v", "A1", 2, 1)])

    inputs, graph = soundtrack.mix_graph(doc, ["A1"], 2.0, 5.0, {"v": "/v.wav"}, ["/rain.wav"])

    assert inputs == ["-i", "/v.wav", "-i", "/rain.wav"]
    assert graph.split(";")[2] == "[1:a]atrim=duration=3,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[m1]"


def test_the_cut_command_writes_a_stereo_wav_of_exactly_the_interval_at_48_khz_or_at_the_rate_asked(tmp_path):
    command = soundtrack.cut_command("ffmpeg", ["-i", "/v.wav"], "g", 3.5, tmp_path / "out.wav")

    assert command[command.index("-filter_complex") + 1] == "g"
    assert command[command.index("-t") + 1] == "3.5"
    assert command[-7:] == ["-c:a", "pcm_s16le", "-ac", "2", "-ar", "48000", str(tmp_path / "out.wav")]
    assert soundtrack.cut_command("ffmpeg", [], "g", 1, tmp_path / "out.wav", 32000)[-2] == "32000"
    assert soundtrack.convert_command("ffmpeg", "/rain.wav", tmp_path / "out.wav", 32000) == [
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", "/rain.wav", "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", "-ac", "2", "-ar", "32000", str(tmp_path / "out.wav"),
    ]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_ffmpeg_cuts_a_track_over_an_interval_with_its_gain_and_silence_where_nothing_plays(core, make_doc, tmp_path, sounds):
    _media(core)
    doc = _doc(make_doc, [_item("loud", "A1", 0, 2), _item("soft", "A1", 3, 1, gain=-20), _item("other", "A2", 0, 6, asset="music")])
    source = soundtrack._Sources(core.users["user-1"], doc, "p-1", tmp_path)

    path = asyncio.run(soundtrack.cut(shutil.which("ffmpeg"), source, ["A1"], 1.0, 4.5, "cut"))
    samples = _samples(path)

    assert len(samples) == int(3.5 * RATE)
    full = _rms(samples, 0.1, 0.9)
    assert full == pytest.approx(0.5 / math.sqrt(2), rel=0.05)
    assert _rms(samples, 1.1, 1.9) < 1e-4
    assert _rms(samples, 2.1, 2.9) / full == pytest.approx(0.1, rel=0.05)
    assert _rms(samples, 3.05, 3.45) < 1e-4


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_ffmpeg_keeps_the_fades_of_an_item_cut_in_its_middle(core, make_doc, tmp_path, sounds):
    _media(core)
    doc = _doc(make_doc, [_item("faded", "A1", 0, 2, fadeIn=2), _item("tail", "A1", 2, 2, fadeOut=1)])
    source = soundtrack._Sources(core.users["user-1"], doc, "p-1", tmp_path)

    samples = _samples(asyncio.run(soundtrack.cut(shutil.which("ffmpeg"), source, ["A1"], 1.0, 4.0, "cut")))

    plain = 0.5 / math.sqrt(2)
    assert 0.45 < _rms(samples, 0.0, 0.1) / plain < 0.6
    assert _rms(samples, 0.85, 0.95) / plain > 0.9
    assert _rms(samples, 1.2, 1.8) / plain == pytest.approx(1.0, rel=0.05)
    assert _rms(samples, 2.85, 2.98) / plain < 0.15


def test_ref2va_sends_the_part_of_each_reference_track_under_the_shot_as_an_audio_reference(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 1, 5)], references=[{"id": "r-hero", "assetId": "hero", "scope": {"type": "global"}}], assets=("voice", "hero"), mode="Ref2VA")
    doc["engine"]["referenceMargin"] = 1

    plans = _plans(core, doc, presets.MINIMAX_H3)

    assert plans.blocks == []
    (plan,) = plans.shots
    assert plan.request["form_data"]["references"] == ["track:A1", "uploads/hero.png"]
    assert (plan.audio.behavior, plan.audio.start, plan.audio.end, plan.audio.lanes) == ("condition", 1.0, 6.0, ["A1"])
    assert "<Audio 1> is a reference sound for [Shot 1]." in plan.prompt_text
    assert "<Audio 1> (sound of [Shot 1]): reference" in plan.prompt_text
    assert _codes(plans) == ["audio_condition"]
    assert plan.summary()["audio"] == {"behavior": "condition", "lanes": ["A1"], "references": 0}


def test_ref2va_holds_three_sounds_the_shot_ones_first_then_its_tracks_then_the_global_ones_without_duplicates(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": "g-rain", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "global"}},
        {"id": "g-voice", "assetId": "voice", "space": "son", "type": "Voix", "scope": {"type": "global"}},
        {"id": "s-voice", "assetId": "voice", "space": "son", "type": "Voix", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "s-hero", "assetId": "hero", "scope": {"type": "shot", "shotId": "s1"}},
    ]
    doc = _doc(
        make_doc,
        [_item("a", "A1", 2, 3), _item("b", "A2", 2, 3, asset="music")],
        reference_lanes=("A1", "A2"),
        references=references,
        assets=("voice", "music", "hero", "rain"),
        mode="Ref2VA",
    )

    (plan,) = _plans(core, doc, presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/voice.wav", "uploads/hero.png", "track:A1", "track:A2"]
    assert plan.audio.lanes == ["A1", "A2"]
    assert "<Audio 3>" in plan.prompt_text and "<Audio 4>" not in plan.prompt_text


def test_a_fourth_sound_is_left_out_and_its_track_is_not_cut(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": name, "assetId": name, "space": "son", "type": "Voix", "scope": {"type": "shot", "shotId": "s1"}}
        for name in ("voice", "music", "rain")
    ] + [{"id": "s-hero", "assetId": "hero", "scope": {"type": "global"}}]
    doc = _doc(make_doc, [_item("a", "A1", 2, 3)], references=references, assets=("voice", "music", "rain", "hero"), mode="Ref2VA")

    (plan,) = _plans(core, doc, presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/voice.wav", "uploads/music.wav", "uploads/rain.wav", "uploads/hero.png"]
    assert plan.audio.lanes == [] and plan.audio.references == ["voice", "music", "rain"]
    assert plan.audio.sent == {"voice": "uploads/voice.wav", "music": "uploads/music.wav", "rain": "uploads/rain.wav"}


def test_ref2va_with_nothing_but_sound_is_blocked_since_a_picture_has_to_anchor_it(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, [_item("a", "A1", 2, 3)], mode="Ref2VA")

    plans = _plans(core, doc, presets.MINIMAX_H3)

    assert plans.shots == []
    assert plans.blocks == [
        {
            "code": "audio_only_references",
            "message": "Ref2VA needs a picture or a video next to the sound of this shot.",
            "data": {"shot_id": "s1"},
        }
    ]


def test_a_muted_track_or_a_track_silent_under_the_shot_sends_nothing_and_says_so(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("late", "A2", 6, 2, asset="music")], reference_lanes=("A1", "A2"), A1={"mute": True})
    doc["audio"].append(_item("v", "A1", 2, 3))

    plans = _plans(core, doc, presets.LTX_2_5)

    (plan,) = plans.shots
    assert plan.audio is None and plan.request["form_data"]["video_director"]["mode"] == "t2v"
    assert _sound(plans) == [
        {"code": "audio_track_muted", "message": "The reference track is muted: nothing of it is sent.", "data": {"shot_id": "s1", "lane_id": "A1"}},
        {
            "code": "audio_track_empty",
            "message": "The reference track has no sound under the shot: nothing of it is sent.",
            "data": {"shot_id": "s1", "lane_id": "A2"},
        },
    ]


def test_a_track_soloed_away_is_not_heard_and_a_shot_can_leave_a_track_out(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 3), _item("m", "A2", 2, 3, asset="music")], reference_lanes=("A1", "A2"), A3={"solo": True})

    assert _codes(_plans(core, doc, presets.LTX_2_5)) == ["audio_track_muted", "audio_track_muted"]

    doc["lanes"][2]["solo"] = False
    doc["clips"][0]["referenceOverrides"] = {"excludeLanes": ["A1"]}
    (plan,) = _plans(core, doc, presets.LTX_2_5).shots
    assert plan.audio.lanes == ["A2"]


def test_ltx_2_5_lays_the_sound_of_the_shot_onto_its_take_through_a_director_document(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 0, 10)], references=[{"id": "g", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "global"}}], assets=("voice", "rain"))
    doc["engine"]["referenceMargin"] = 2

    plans = _plans(core, doc, presets.LTX_2_5)

    (plan,) = plans.shots
    document = plan.request["form_data"]["video_director"]
    assert (document["mode"], document["segments"][0]["start"], document["segments"][0]["end"]) == ("director", 0.0, 3.0)
    assert "audio" not in document
    assert (plan.audio.behavior, plan.audio.start, plan.audio.end, plan.audio.lanes, plan.audio.references) == ("mux", 2.0, 5.0, ["A1"], ["rain"])
    assert plan.director_mode == "t2v"
    assert _sound(plans) == [
        {"code": "audio_mux", "message": "The sound of the shot is mixed onto the take, not used as a guide.", "data": {"shot_id": "s1"}}
    ]


def test_a_mixed_shot_keeps_its_first_and_last_frames_on_the_segment_of_its_director_document(core, make_doc):
    core.use_ltx25()
    _media(core)
    core.add_media({"kind": "library", "item_id": "lib-a"}, "uploads/a.png", "image")
    core.add_media({"kind": "library", "item_id": "lib-b"}, "uploads/b.png", "image")
    doc = _doc(make_doc, [_item("v", "A1", 2, 3)])
    doc["assets"] += [
        {**_sound_asset("voice"), "id": "a", "kind": "image", "origin": {"kind": "library", "itemId": "lib-a"}},
        {**_sound_asset("voice"), "id": "b", "kind": "image", "origin": {"kind": "library", "itemId": "lib-b"}},
    ]
    doc["frames"] = [
        {"id": "f1", "shotId": "s1", "time": 2, "assetId": "a", "role": "first", "strength": 75},
        {"id": "f2", "shotId": "s1", "time": 5, "assetId": "b", "role": "last", "strength": 75},
    ]

    (plan,) = _plans(core, doc, presets.LTX_2_5).shots

    media = plan.request["form_data"]["video_director"]["media"]
    assert plan.director_mode == "flf"
    assert [(entry["role"], entry["segment_id"], entry["media"]["path"]) for entry in media] == [
        ("first", "seg-1", "uploads/a.png"),
        ("last", "seg-1", "uploads/b.png"),
    ]


def test_minimax_h3_outside_its_reference_mode_mixes_through_a_chained_director_document(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 3)])

    (plan,) = _plans(core, doc, presets.MINIMAX_H3).shots

    document = plan.request["form_data"]["video_director"]
    assert (document["mode"], document["segments"][0]["frames"], plan.audio.behavior) == ("director", 72, "mux")
    assert "start" not in document["segments"][0]


def test_an_engine_without_audio_in_its_director_mode_ignores_the_sound_and_says_so(core, make_doc):
    core.use_wan()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 3)])

    plans = _plans(core, doc, presets.WAN)

    (plan,) = plans.shots
    assert plan.audio.behavior == "ignored" and not plan.needs_audio
    assert plan.request["form_data"]["video_director"]["mode"] == "t2v"
    assert _sound(plans) == [{"code": "audio_ignored", "message": "This engine ignores the sound of the shot.", "data": {"shot_id": "s1"}}]


def test_a_cloud_model_ignores_the_sound(core, make_doc):
    core.use_openrouter()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 3)])

    plans = director.build_plans(core.users["user-1"], doc, ["s1"], presets.OPENROUTER_VIDEO, "draft", "cm-veo")

    assert _codes(plans) == ["audio_ignored"]


def test_a_shot_with_no_sound_says_nothing_about_it(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc, reference_lanes=())

    plans = _plans(core, doc, presets.LTX_2_5)

    assert _sound(plans) == [] and plans.shots[0].audio is None


def test_without_ffmpeg_a_shot_that_must_cut_its_sound_is_blocked(core, make_doc, monkeypatch):
    core.use_ltx25()
    _media(core)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    plans = _plans(core, _doc(make_doc, [_item("v", "A1", 2, 3)]), presets.LTX_2_5)

    assert plans.blocks == [
        {
            "code": "audio_ffmpeg_missing",
            "message": "ffmpeg is not available on this server: the sound of the shots cannot be cut.",
            "data": {"shot_ids": ["s1"]},
        }
    ]


def test_the_mux_entry_is_the_shape_the_core_director_document_takes():
    assert director.mux_entry("uploads/mix.wav", 3.0) == {
        "id": "a-1",
        "role": "mux",
        "start": 0.0,
        "trim_start": 0.0,
        "length": 3.0,
        "media": {"path": "uploads/mix.wav", "relative_path": "uploads/mix.wav", "type": "audio"},
    }


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_attaching_a_guided_shot_stores_each_track_cut_and_each_sound_at_32_khz_in_place_of_what_the_plan_sent(core, make_doc, sounds, stored, export_storage):
    core.use_h3()
    _media(core)
    doc = _doc(
        make_doc,
        [_item("v", "A1", 1, 5), _item("m", "A2", 2, 2, asset="music")],
        reference_lanes=("A1", "A2"),
        references=[
            {"id": "r-hero", "assetId": "hero", "scope": {"type": "global"}},
            {"id": "r-rain", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "shot", "shotId": "s1"}},
        ],
        assets=("voice", "music", "hero", "rain"),
        mode="Ref2VA",
    )
    doc["engine"]["referenceMargin"] = 0.5
    (plan,) = _plans(core, doc, presets.MINIMAX_H3).shots
    assert plan.request["form_data"]["references"] == ["uploads/rain.wav", "track:A1", "track:A2", "uploads/hero.png"]

    asyncio.run(soundtrack.attach(core.users["user-1"], {"id": "p-1", "doc": doc}, plan))

    assert plan.request["form_data"]["references"] == [
        "uploads/vp-sound-shot-01-sound1.wav",
        "uploads/vp-sound-shot-01-a1.wav",
        "uploads/vp-sound-shot-01-a2.wav",
        "uploads/hero.png",
    ]
    lengths = {path.name: len(_samples(path, soundtrack.H3_RATE)) for path in stored}
    assert lengths == {"vp-sound-shot-01-a1.wav": 4 * soundtrack.H3_RATE, "vp-sound-shot-01-a2.wav": 4 * soundtrack.H3_RATE, "vp-sound-shot-01-sound1.wav": 8 * soundtrack.H3_RATE}
    assert list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_attaching_a_mixed_shot_stores_one_mix_and_puts_it_in_the_director_document(core, make_doc, sounds, stored, export_storage):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 1)], references=[{"id": "g", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "global"}}], assets=("voice", "rain"))
    (plan,) = _plans(core, doc, presets.LTX_2_5).shots

    asyncio.run(soundtrack.attach(core.users["user-1"], {"id": "p-1", "doc": doc}, plan))

    assert plan.request["form_data"]["video_director"]["audio"] == [director.mux_entry("uploads/vp-sound-shot-01-mix.wav", 3.0)]
    samples = _samples(stored[0])
    assert len(samples) == 3 * RATE
    assert _rms(samples, 0.1, 0.9) > _rms(samples, 1.1, 2.9) > 0.1


def test_a_sound_whose_file_is_gone_fails_the_attach(core, make_doc, monkeypatch, stored, export_storage):
    core.use_ltx25()
    _media(core)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, folder: None)
    doc = _doc(make_doc, [_item("v", "A1", 2, 1)])
    (plan,) = _plans(core, doc, presets.LTX_2_5).shots

    with pytest.raises(soundtrack.SoundError) as caught:
        asyncio.run(soundtrack.attach(core.users["user-1"], {"id": "p-1", "doc": doc}, plan))

    assert caught.value.code == "audio_source_missing" and stored == []


@pytest.fixture
def cuts(monkeypatch, tmp_path):
    made = []

    async def cut(ffmpeg, sources, lanes, start, end, name, references=()):
        made.append((list(lanes), start, end, list(references)))
        path = sources.folder / f"{name}.wav"
        _tone(path, 0.1)
        return path

    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(soundtrack, "cut", cut)
    return made


def test_a_generation_cuts_and_stores_the_sound_of_a_shot_once_for_all_its_drafts(client, core, make_doc, make_project, cuts, stored, export_storage):
    core.use_ltx25()
    _media(core)
    project = make_project(doc=_doc(make_doc, [_item("v", "A1", 2, 3)]))

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 3, "preset_id": presets.LTX_2_5})

    assert response.status_code == 202, response.text
    assert cuts == [(["A1"], 2.0, 5.0, [])] and len(stored) == 1
    documents = [take["request"]["form_data"]["video_director"] for take in takes.list_takes(project["id"])]
    assert len(documents) == 3 and len(core.submitted) == 2
    assert all(document["audio"] == [director.mux_entry(f"uploads/{stored[0].name}", 3.0)] for document in documents)


def test_a_sound_that_cannot_be_stored_blocks_the_generation_and_creates_no_take(client, core, make_doc, make_project, cuts, monkeypatch, export_storage):
    core.use_ltx25()
    _media(core)

    async def refuse(user, path):
        raise core_bridge.MediaRefError("upload_rejected", "Upload quota reached")

    monkeypatch.setattr(core_bridge, "save_user_media", refuse)
    project = make_project(doc=_doc(make_doc, [_item("v", "A1", 2, 3)]))

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 2, "preset_id": presets.LTX_2_5})

    assert response.status_code == 409
    assert response.json()["detail"]["data"]["blocks"] == [{"code": "audio_store_failed", "message": "Upload quota reached", "data": {"shot_id": "s1"}}]
    assert core.submitted == []


def test_the_schema_takes_the_sound_space_a_reference_track_its_margin_and_the_tracks_a_shot_leaves_out(make_doc):
    doc = _doc(make_doc, [_item("v", "A1", 2, 3)], references=[{"id": "g", "assetId": "rain", "space": "son", "type": "Ambiance", "role": "Son", "scope": {"type": "global"}}], assets=("voice", "rain"))
    doc["engine"]["referenceMargin"] = 2.5
    doc["clips"][0]["referenceOverrides"] = {"exclude": ["g"], "excludeLanes": ["A1"]}

    validate_doc(doc)

    for change in (
        lambda d: d["references"][0].update(space="audio"),
        lambda d: d["lanes"][0].update(reference="yes"),
        lambda d: d["engine"].update(referenceMargin=-1),
        lambda d: d["engine"].update(referenceMargin=11),
        lambda d: d["engine"].update(referenceMargin="2"),
        lambda d: d["clips"][0]["referenceOverrides"].update(excludeLanes=["A1", "A1"]),
        lambda d: d["clips"][0]["referenceOverrides"].update(excludeLanes="A1"),
    ):
        broken = copy.deepcopy(doc)
        change(broken)
        with pytest.raises(DocError):
            validate_doc(broken)


def test_the_presets_say_whether_their_director_mode_takes_an_audio_track(core):
    from backend import catalog

    assert catalog.audio_mux(core.use_ltx25().vars) and catalog.audio_mux(core.use_h3().vars)
    assert not catalog.audio_mux(core.use_wan().vars)
    assert not catalog.audio_mux({})
