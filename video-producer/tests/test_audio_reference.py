import asyncio
import copy
import hashlib
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from backend import core_bridge, director, estimate, generation, presets, soundtrack, takes, tracker
from backend.director import TrackCut
from backend.projects import DocError, validate_doc

BASE = "/api/plugins/video-producer"
RATE = 48000
HAS_FFMPEG = bool(shutil.which("ffmpeg"))
SHOT = {"id": "s1", "start": 2, "dur": 3, "label": "Harbour"}
LIBRARY = {
    "voice": "lib-voice",
    "music": "lib-music",
    "hero": "lib-hero",
    "rain": "lib-rain",
    "wind": "lib-wind",
    "stem": "lib-stem",
    "choir": "lib-choir",
    "step": "lib-step",
}
SILENT = {"code": "audio_track_silent", "message": "The reference track is silent under the shot: nothing of it is sent."}
HERO = {"id": "r-hero", "assetId": "hero", "scope": {"type": "global"}}


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


def _ffmpeg_wav(path: Path, seconds: float, expression: str) -> Path:
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"aevalsrc=exprs={expression}|{expression}:s={RATE}:d={seconds}",
            "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
    )
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
def levels(tmp_path, monkeypatch):
    folder = tmp_path / "levels"
    folder.mkdir()
    files = {
        "voice": _ffmpeg_wav(folder / "voice.wav", 8.0, "0.5*sin(2*PI*440*t)"),
        "stem": _ffmpeg_wav(folder / "stem.wav", 12.0, "if(gte(t\\,6)\\,0.3*sin(2*PI*550*t)\\,0)"),
        "choir": _ffmpeg_wav(folder / "choir.wav", 8.0, "0.0018*sin(2*PI*330*t)"),
        "step": _ffmpeg_wav(folder / "step.wav", 8.0, "if(between(t\\,1.5\\,1.51)\\,0.01*sin(2*PI*1000*t)\\,0)"),
    }

    def local(kind, value, target):
        return files.get(Path(value).stem)

    monkeypatch.setattr(core_bridge, "local_media_file", local)
    return files


@pytest.fixture
def measured(monkeypatch):
    commands = []
    run = soundtrack.peak

    async def counted(command):
        commands.append(command)
        return await run(command)

    monkeypatch.setattr(soundtrack, "peak", counted)
    return commands


@pytest.fixture
def slow_peaks(monkeypatch):
    state = {"running": 0, "most": 0, "calls": []}

    async def peak(command):
        state["calls"].append(command)
        state["running"] += 1
        state["most"] = max(state["most"], state["running"])
        await asyncio.sleep(0.05)
        state["running"] -= 1
        return -91.0

    monkeypatch.setattr(soundtrack, "peak", peak)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    return state


@pytest.fixture
def uploads(monkeypatch):
    saved = []

    async def save(user, path):
        saved.append((Path(path).name, hashlib.sha256(Path(path).read_bytes()).hexdigest()))
        return {"value": f"uploads/{Path(path).name}", "media_type": "audio", "original_filename": Path(path).name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save)
    return saved


@pytest.fixture
def ffmpeg_runs(monkeypatch):
    state = {"running": 0, "most": 0}
    assemble = soundtrack.assemble

    async def counted(command, *args, **kwargs):
        state["running"] += 1
        state["most"] = max(state["most"], state["running"])
        try:
            return await assemble(command, *args, **kwargs)
        finally:
            state["running"] -= 1

    monkeypatch.setattr(soundtrack, "assemble", counted)
    return state


def _shots_doc(make_doc, count, **options):
    doc = _doc(
        make_doc,
        [_item("v", "A1", 0, 8), _item("m", "A2", 0, 8, asset="music")],
        reference_lanes=("A1", "A2"),
        **options,
    )
    doc["clips"] = [{**doc["clips"][0], "id": f"s{index}", "start": 2 * (index - 1), "dur": 2, "label": f"Shot {index}"} for index in range(1, count + 1)]
    doc["prompts"] = [{**doc["prompts"][0], "id": f"p{index}", "shotId": f"s{index}"} for index in range(1, count + 1)]
    return doc


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


def test_a_guided_shot_leaves_out_a_track_found_silent_under_it_and_numbers_the_other_sounds_without_a_gap(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(
        make_doc,
        [_item("a", "A1", 2, 3), _item("b", "A2", 2, 3, asset="music"), _item("c", "A3", 2, 3, asset="rain")],
        reference_lanes=("A1", "A2", "A3"),
        references=[HERO],
        assets=("voice", "music", "rain", "hero"),
        mode="Ref2VA",
    )

    plans = _plans(core, doc, presets.MINIMAX_H3, silent={"s1": ["A2"], "s2": ["A1"]})

    (plan,) = plans.shots
    assert plan.request["form_data"]["references"] == ["track:A1", "track:A3", "uploads/hero.png"]
    assert plan.audio.lanes == ["A1", "A3"] and plan.summary()["audio"]["lanes"] == ["A1", "A3"]
    assert "<Audio 1> is a reference sound for [Shot 1]." in plan.prompt_text
    assert "<Audio 2> is a reference sound for [Shot 1]." in plan.prompt_text
    assert "<Audio 3>" not in plan.prompt_text and "<Picture 1>" in plan.prompt_text
    assert _sound(plans) == [
        {**SILENT, "data": {"shot_id": "s1", "lane_id": "A2"}},
        {"code": "audio_condition", "message": "The sound of the shot guides the generation.", "data": {"shot_id": "s1"}},
    ]
    assert plans.track_cuts == [TrackCut("s1", "A1", 2.0, 5.0), TrackCut("s1", "A3", 2.0, 5.0)]


def test_a_silent_track_frees_its_place_for_the_next_sound_before_the_references_are_ranked(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": "s-voice", "assetId": "voice", "space": "son", "type": "Voix", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "s-hero", "assetId": "hero", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "g-rain", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "global"}},
    ]
    doc = _doc(
        make_doc,
        [_item("a", "A1", 2, 3, asset="music"), _item("b", "A2", 2, 3, asset="music")],
        reference_lanes=("A1", "A2"),
        references=references,
        assets=("voice", "music", "hero", "rain"),
        mode="Ref2VA",
    )
    assert _plans(core, doc, presets.MINIMAX_H3).shots[0].request["form_data"]["references"] == [
        "uploads/voice.wav", "uploads/hero.png", "track:A1", "track:A2",
    ]

    (plan,) = _plans(core, doc, presets.MINIMAX_H3, silent={"s1": ["A1"]}).shots

    assert plan.request["form_data"]["references"] == ["uploads/voice.wav", "uploads/hero.png", "track:A2", "uploads/rain.wav"]
    assert (plan.audio.lanes, plan.audio.references) == (["A2"], ["voice", "rain"])
    assert "<Audio 3> is a reference sound for [Shot 1]." in plan.prompt_text and "<Audio 4>" not in plan.prompt_text


def test_the_tracks_a_guided_shot_would_cut_are_listed_past_the_limit_on_sounds_and_when_the_shot_is_blocked(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": name, "assetId": name, "space": "son", "type": "Voix", "scope": {"type": "shot", "shotId": "s1"}}
        for name in ("voice", "music", "rain")
    ] + [HERO]
    full = _doc(make_doc, [_item("a", "A1", 2, 3)], references=references, assets=("voice", "music", "rain", "hero"), mode="Ref2VA")
    full["engine"]["referenceMargin"] = 1
    assert _plans(core, full, presets.MINIMAX_H3).track_cuts == [TrackCut("s1", "A1", 1.0, 6.0)]

    only = _doc(make_doc, [_item("a", "A1", 2, 3), _item("b", "A2", 2, 3, asset="music")], reference_lanes=("A1", "A2"), mode="Ref2VA")
    plans = _plans(core, only, presets.MINIMAX_H3)
    assert [block["code"] for block in plans.blocks] == ["audio_only_references"]
    assert plans.track_cuts == [TrackCut("s1", "A1", 2.0, 5.0), TrackCut("s1", "A2", 2.0, 5.0)]

    some = _plans(core, only, presets.MINIMAX_H3, silent={"s1": ["A1"]})
    assert [block["code"] for block in some.blocks] == ["audio_only_references"]
    none = _plans(core, only, presets.MINIMAX_H3, silent={"s1": ["A1", "A2"]})
    assert [block["code"] for block in none.blocks] == ["no_references"]
    assert none.track_cuts == [] and _codes(none) == ["audio_track_silent", "audio_track_silent"]


def test_a_guided_shot_whose_tracks_are_all_silent_goes_like_a_shot_without_sound(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, [_item("a", "A1", 2, 3)], references=[HERO], assets=("voice", "hero"), mode="Ref2VA")

    plans = _plans(core, doc, presets.MINIMAX_H3, silent={"s1": ["A1"]})

    (plan,) = plans.shots
    assert plans.blocks == [] and plan.audio is None and not plan.needs_audio
    assert plan.request["form_data"]["references"] == ["uploads/hero.png"]
    assert "<Audio" not in plan.prompt_text
    assert _sound(plans) == [{**SILENT, "data": {"shot_id": "s1", "lane_id": "A1"}}]


def test_a_mixed_shot_takes_no_measure_and_mixes_its_tracks_as_before(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("a", "A1", 2, 3)])

    plans = _plans(core, doc, presets.LTX_2_5, silent={"s1": ["A1"]})

    (plan,) = plans.shots
    assert plans.track_cuts == [] and plan.audio.lanes == ["A1"] and _codes(plans) == ["audio_mux"]


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


def test_a_mixed_shot_sends_the_audio_vae_the_ltx_pipeline_loads_to_mux_and_a_silent_one_does_not(core, make_doc):
    core.use_ltx25()
    _media(core)

    (mixed,) = _plans(core, _doc(make_doc, [_item("v", "A1", 2, 3)]), presets.LTX_2_5).shots
    (silent,) = _plans(core, _doc(make_doc, reference_lanes=()), presets.LTX_2_5).shots

    assert mixed.request["form_data"]["audio_vae"] == "model:id-ltx25_audio_vae-sha"
    assert "audio_vae" not in silent.request["form_data"]


def test_a_mixed_shot_without_the_audio_vae_installed_is_blocked(core, make_doc):
    core.use_ltx25()
    _media(core)
    core.missing.add("ltx25_audio_vae-sha")

    plans = _plans(core, _doc(make_doc, [_item("v", "A1", 2, 3)]), presets.LTX_2_5)

    assert [block["code"] for block in plans.blocks] == ["missing_models"]
    assert plans.blocks[0]["data"] == {"fields": ["audio_vae"]}


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


def test_the_peak_command_reads_the_cut_graph_at_the_rate_it_is_written_and_writes_nothing():
    assert soundtrack.peak_command("ffmpeg", ["-i", "/v.wav"], "g[aout]", 3.5, 32000) == [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-nostats",
        "-i", "/v.wav",
        "-filter_complex", "g[aout];[aout]aresample=32000,volumedetect[peak]",
        "-map", "[peak]",
        "-t", "3.5",
        "-f", "null", "-",
    ]


def test_the_measured_peaks_are_kept_for_the_cuts_last_used(monkeypatch):
    monkeypatch.setattr(soundtrack, "PEAK_CACHE", 2)
    soundtrack._remember(("user-1", "graph-0"), -0.0)
    soundtrack._remember(("user-1", "graph-1"), -1.0)
    assert soundtrack._recall(("user-1", "graph-0")) == -0.0
    soundtrack._remember(("user-1", "graph-2"), -2.0)

    assert soundtrack._PEAKS == {("user-1", "graph-0"): -0.0, ("user-1", "graph-2"): -2.0}
    assert soundtrack._recall(("user-1", "graph-1")) is None


def test_a_cut_reads_its_sources_from_the_start_and_only_a_measure_deep_into_an_item_seeks(make_doc):
    late = _item("late", "A1", 21.01, 400, srcIn=3.5, gain=-3, fadeIn=2, fadeOut=30)
    trimmed = _item("trimmed", "A1", 21, 300, srcIn=100.25, fadeIn=1.5)
    near = _item("near", "A1", 0, 30)
    doc = _doc(make_doc, [late], A1={"vol": -2})

    inputs, graph = soundtrack.mix_graph(doc, ["A1"], 380.37, 387.37, {"late": "/late.wav"})
    measured, measuring = soundtrack.mix_graph(doc, ["A1"], 380.37, 387.37, {"late": "/late.wav"}, seek=True)

    assert inputs == ["-i", "/late.wav"]
    assert graph.split(";")[1] == (
        "[0:a]atrim=start=3.5:duration=400,asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-5dB,afade=t=in:st=0:d=2,afade=t=out:st=370:d=30,atrim=start=359.36,asetpts=PTS-STARTPTS,adelay=delays=0:all=1[m0]"
    )
    assert measured == ["-ss", "361.5", "-i", "/late.wav"]
    assert measuring.split(";")[1] == (
        "[0:a]atrim=start=0:duration=42,asetpts=PTS-STARTPTS+358/TB,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "volume=-5dB,afade=t=in:st=0:d=2,afade=t=out:st=370:d=30,atrim=start=359.36,asetpts=PTS-STARTPTS,adelay=delays=0:all=1[m0]"
    )
    assert measuring.split(";")[0::2] == graph.split(";")[0::2]
    assert soundtrack.seek_point(trimmed, 21.0) == 99.25
    assert soundtrack.sound_chain(trimmed, {}, 21.0, 99.25)[:2] == ["atrim=start=1:duration=300", "asetpts=PTS-STARTPTS"]
    assert [soundtrack.seek_point(near, origin) for origin in (5.0, 10.99, 11.0)] == [0.0, 0.0, 10.0]
    assert soundtrack.sound_chain(late, {}, 0.0) == soundtrack.sound_chain(late, {}, 0.0, 0.0)
    assert soundtrack.sound_chain(late, {}, 0.0)[:2] == ["atrim=start=3.5:duration=400", "asetpts=PTS-STARTPTS"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize(
    "suffix, codec",
    [("wav", ["-c:a", "pcm_s16le"]), ("mp3", ["-c:a", "libmp3lame", "-q:a", "2"]), ("m4a", ["-c:a", "aac", "-b:a", "160k"])],
    ids=["wav", "mp3-vbr", "aac"],
)
def test_the_peak_measured_from_the_seek_point_is_the_peak_of_the_cut_sent_which_reads_from_the_start(core, make_doc, tmp_path, monkeypatch, suffix, codec):
    _media(core)
    chirp = "0.3*sin(2*PI*(220+3*t)*t)+0.05*sin(2*PI*1234*t+sin(t))"
    source = tmp_path / f"stem.{suffix}"
    subprocess.run(
        [shutil.which("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"aevalsrc=exprs={chirp}|{chirp}:s=44100:d=70", *codec, str(source)],
        check=True,
    )
    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, target: source)
    doc = _doc(make_doc, [_item("late", "A1", 1.01, 66, srcIn=2.25, gain=-3, fadeIn=2, fadeOut=20)], A1={"vol": -2})
    sources = soundtrack._Sources(core.users["user-1"], doc, "p-1", tmp_path)
    ffmpeg = shutil.which("ffmpeg")
    commands = []
    assemble, peak = soundtrack.assemble, soundtrack.peak

    async def cut(command, *args, **kwargs):
        commands.append(command)
        return await assemble(command, *args, **kwargs)

    async def measure(command):
        commands.append(command)
        return await peak(command)

    monkeypatch.setattr(soundtrack, "assemble", cut)
    monkeypatch.setattr(soundtrack, "peak", measure)

    for start, end in ((40.37, 44.37), (55.0, 70.0)):
        level = asyncio.run(soundtrack.track_peak(ffmpeg, sources, TrackCut("s1", "A1", start, end)))
        sent = asyncio.run(soundtrack.cut(ffmpeg, sources, ["A1"], start, end, f"cut-{start}", rate=soundtrack.H3_RATE))
        heard = 20 * math.log10(max(map(abs, _samples(sent, soundtrack.H3_RATE))))

        assert "-ss" in commands[-2] and "-ss" not in commands[-1]
        assert heard > -30 and abs(level - heard) <= 0.5


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_ffmpeg_reads_the_peak_of_a_track_cut_as_it_is_mixed_and_a_sparse_or_discreet_sound_is_not_silent(core, make_doc, tmp_path, levels, export_storage):
    _media(core)
    doc = _doc(
        make_doc,
        [
            _item("v", "A1", 0, 8),
            _item("s", "A2", 0, 12, asset="stem"),
            _item("c", "A3", 0, 8, asset="choir"),
            _item("p", "A4", 0, 8, asset="step"),
            _item("q", "A1", 9, 8, gain=-30),
        ],
        reference_lanes=("A1", "A2", "A3", "A4"),
        assets=("voice", "stem", "choir", "step"),
        A1={"vol": -30},
        A2={"vol": -2},
        A3={"vol": 0},
        A4={"vol": 0},
    )
    sources = soundtrack._Sources(core.users["user-1"], doc, "p-1", tmp_path)
    ffmpeg = shutil.which("ffmpeg")

    def level(lane, start, end):
        return asyncio.run(soundtrack.track_peak(ffmpeg, sources, TrackCut("s1", lane, start, end)))

    assert level("A1", 2, 5) == pytest.approx(-36.0, abs=0.3)
    assert level("A1", 10, 13) == pytest.approx(-66.0, abs=0.5)
    assert level("A2", 2, 5) <= -90
    assert level("A2", 5, 8) == pytest.approx(-12.5, abs=0.3)
    assert level("A3", 2, 5) == pytest.approx(-54.9, abs=0.3)
    assert level("A4", 0, 3) == pytest.approx(-40.0, abs=0.5)

    cuts = [TrackCut("s1", lane, start, end) for lane, start, end in (("A1", 2, 5), ("A1", 10, 13), ("A2", 2, 5), ("A2", 5, 8), ("A3", 2, 5), ("A4", 0, 3))]
    silent = asyncio.run(soundtrack.silent_lanes(core.users["user-1"], "p-1", doc, [TrackCut(f"shot-{index}", cut.lane_id, cut.start, cut.end) for index, cut in enumerate(cuts)]))
    assert silent == {"shot-1": ["A1"], "shot-2": ["A2"]}


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_the_estimate_measures_each_guided_track_once_leaves_out_the_silent_one_and_keeps_the_discreet_one(core, make_doc, levels, measured, export_storage):
    core.use_h3()
    _media(core)
    user = core.users["user-1"]
    doc = _doc(
        make_doc,
        [_item("v", "A1", 2, 3), _item("s", "A2", 0, 12, asset="stem"), _item("c", "A3", 2, 3, asset="choir")],
        reference_lanes=("A1", "A2", "A3"),
        references=[HERO],
        assets=("voice", "stem", "choir", "hero"),
        mode="Ref2VA",
        A3={"vol": 0},
    )
    order = estimate.parse_order({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.MINIMAX_H3})

    evaluation = asyncio.run(estimate.evaluate(user, user, doc, order, "p-1"))

    (plan,) = evaluation.plans.shots
    assert plan.request["form_data"]["references"] == ["track:A1", "track:A3", "uploads/hero.png"]
    assert evaluation.payload["shots"][0]["audio"] == {"behavior": "condition", "lanes": ["A1", "A3"], "references": 0}
    assert {**SILENT, "data": {"shot_id": "s1", "lane_id": "A2"}} in evaluation.payload["warnings"]
    assert "<Audio 2> is a reference sound for [Shot 1]." in plan.prompt_text and "<Audio 3>" not in plan.prompt_text
    assert len(measured) == 3
    work = export_storage / "video_producer" / "audio" / "user-1"
    assert list(work.iterdir()) == []

    shutil.rmtree(work)
    again = asyncio.run(estimate.evaluate(user, user, doc, order, "p-1"))
    assert again.payload["warnings"] == evaluation.payload["warnings"] and len(measured) == 3
    assert not work.exists()

    doc["audio"][2]["gain"] = -10
    quieter = asyncio.run(estimate.evaluate(user, user, doc, order, "p-1"))
    assert len(measured) == 4
    assert quieter.plans.shots[0].request["form_data"]["references"] == ["track:A1", "uploads/hero.png"]
    assert [warning["data"]["lane_id"] for warning in quieter.payload["warnings"] if warning["code"] == "audio_track_silent"] == ["A2", "A3"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_a_track_whose_cut_cannot_be_measured_is_kept_and_a_mixed_shot_measures_nothing(core, make_doc, levels, measured, monkeypatch, export_storage):
    _media(core)
    user = core.users["user-1"]
    doc = _doc(make_doc, [_item("s", "A1", 0, 12, asset="stem")], references=[HERO], assets=("stem", "hero"), mode="Ref2VA")
    cut = TrackCut("s1", "A1", 2.0, 5.0)
    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, target: None)

    assert asyncio.run(soundtrack.silent_lanes(user, "p-1", doc, [cut])) == {}
    assert measured == []
    assert asyncio.run(soundtrack.peak([shutil.which("ffmpeg"), "-hide_banner", "-i", str(export_storage / "gone.wav"), "-f", "null", "-"])) is None
    measured.clear()

    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, target: levels.get(Path(value).stem))
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)
    assert asyncio.run(soundtrack.silent_lanes(user, "p-1", doc, [cut])) == {}

    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: shutil.which("ffmpeg"))
    core.use_ltx25()
    doc["direction"]["mode"] = "FL2VA"
    order = estimate.parse_order({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.LTX_2_5})
    evaluation = asyncio.run(estimate.evaluate(user, user, doc, order, "p-1"))
    assert evaluation.plans.shots[0].audio.lanes == ["A1"] and measured == []
    assert "audio_track_silent" not in [warning["code"] for warning in evaluation.payload["warnings"]]


def test_overlapping_estimates_share_each_measure_and_at_most_four_run_at_a_time(core, make_doc, sounds, slow_peaks, export_storage):
    _media(core)
    user = core.users["user-1"]
    doc = _doc(make_doc, [_item("v", "A1", 0, 8)], reference_lanes=("A1",))
    cuts = [TrackCut(f"s{index}", "A1", index * 0.5, index * 0.5 + 3) for index in range(10)]

    async def both():
        return await asyncio.gather(*(soundtrack.silent_lanes(user, "p-1", doc, cuts) for _ in range(2)))

    first, second = asyncio.run(both())

    assert first == second == {f"s{index}": ["A1"] for index in range(10)}
    assert len(slow_peaks["calls"]) == 10 and slow_peaks["most"] == soundtrack.MEASURES == 4
    assert soundtrack._RUNNING == {} and list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


def test_a_measure_goes_on_when_its_estimate_is_dropped_and_the_next_estimate_awaits_it(core, make_doc, sounds, slow_peaks, export_storage):
    _media(core)
    user = core.users["user-1"]
    doc = _doc(make_doc, [_item("v", "A1", 0, 8)], reference_lanes=("A1",))
    cuts = [TrackCut(f"s{index}", "A1", index * 0.5, index * 0.5 + 3) for index in range(6)]

    async def dropped_then_again():
        dropped = asyncio.ensure_future(soundtrack.silent_lanes(user, "p-1", doc, cuts))
        while not slow_peaks["calls"]:
            await asyncio.sleep(0.005)
        dropped.cancel()
        with pytest.raises(asyncio.CancelledError):
            await dropped
        running = len(soundtrack._RUNNING)
        return running, await soundtrack.silent_lanes(user, "p-1", doc, cuts)

    running, silent = asyncio.run(dropped_then_again())

    assert running == 6 and silent == {f"s{index}": ["A1"] for index in range(6)}
    assert len(slow_peaks["calls"]) == 6 and len(soundtrack._PEAKS) == 6


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("preset", [presets.MINIMAX_H3, presets.LTX_2_5], ids=["guided", "mixed"])
def test_the_sounds_of_the_shots_are_cut_four_at_a_time_into_the_uploads_and_requests_of_one_cut_after_the_other(
    core, make_doc, sounds, uploads, ffmpeg_runs, export_storage, monkeypatch, preset
):
    if preset == presets.MINIMAX_H3:
        core.use_h3()
    else:
        core.use_ltx25()
    _media(core)
    references = [HERO, {"id": "s-rain", "assetId": "rain", "space": "son", "type": "Ambiance", "scope": {"type": "shot", "shotId": "s2"}}]
    doc = _shots_doc(make_doc, 4, references=references, assets=("voice", "music", "rain", "hero"), mode="Ref2VA" if preset == presets.MINIMAX_H3 else "FL2VA")
    planned = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "s3", "s4"], preset, "draft").shots
    project = {"id": "p-1", "doc": doc}
    runs = {}
    for slots in (1, 4):
        monkeypatch.setattr(soundtrack, "MEASURES", slots)
        plans = copy.deepcopy(planned)
        uploads.clear()
        ffmpeg_runs["most"] = 0
        asyncio.run(soundtrack.attach_all(core.users["user-1"], project, plans))
        forms = [plan.request["form_data"].get("references") or plan.request["form_data"]["video_director"]["audio"] for plan in plans]
        runs[slots] = (list(uploads), forms, ffmpeg_runs["most"])

    assert runs[4][:2] == runs[1][:2] and (runs[1][2], runs[4][2]) == (1, 4)
    names = [name for name, _ in runs[4][0]]
    if preset == presets.MINIMAX_H3:
        assert names == [f"vp-sound-shot-0{index}-{suffix}.wav" for index in range(1, 5) for suffix in (("a1", "a2", "sound1") if index == 2 else ("a1", "a2"))]
        assert runs[4][1][1] == ["uploads/vp-sound-shot-02-sound1.wav", "uploads/vp-sound-shot-02-a1.wav", "uploads/vp-sound-shot-02-a2.wav", "uploads/hero.png"]
    else:
        assert names == [f"vp-sound-shot-0{index}-mix.wav" for index in range(1, 5)]
        assert runs[4][1][1] == [director.mux_entry("uploads/vp-sound-shot-02-mix.wav", 2.0)]
    assert list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


@pytest.fixture
def failing_cuts(monkeypatch, tmp_path):
    state = {"started": [], "cancelled": [], "delays": {}, "failures": {}}

    async def cut(ffmpeg, sources, lanes, start, end, name, references=(), rate=48000):
        state["started"].append(name)
        try:
            await asyncio.sleep(state["delays"].get(name, 0.01))
        except asyncio.CancelledError:
            state["cancelled"].append(name)
            raise
        if name in state["failures"]:
            raise soundtrack.SoundError(state["failures"][name], f"{name} failed.")
        path = sources.folder / f"{name}.wav"
        _tone(path, 0.05)
        return path

    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(soundtrack, "cut", cut)
    return state


def test_the_first_sound_that_fails_in_the_order_of_the_shots_blocks_and_nothing_from_it_on_is_stored(core, make_doc, sounds, uploads, failing_cuts, export_storage):
    core.use_h3()
    _media(core)
    doc = _shots_doc(make_doc, 4, references=[HERO], assets=("voice", "music", "hero"), mode="Ref2VA")
    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "s3", "s4"], presets.MINIMAX_H3, "draft").shots
    failing_cuts["delays"] = {"vp-sound-shot-02-a2": 0.3, "vp-sound-shot-04-a1": 0.0}
    failing_cuts["failures"] = {"vp-sound-shot-02-a2": "audio_cut_failed", "vp-sound-shot-04-a1": "audio_source_missing"}

    with pytest.raises(generation.Blocked) as caught:
        asyncio.run(generation.with_sound(core.users["user-1"], {"id": "p-1", "doc": doc}, plans))

    assert caught.value.blocks == [{"code": "audio_cut_failed", "message": "vp-sound-shot-02-a2 failed.", "data": {"shot_id": "s2"}}]
    assert [name for name, _ in uploads] == ["vp-sound-shot-01-a1.wav", "vp-sound-shot-01-a2.wav", "vp-sound-shot-02-a1.wav"]
    assert len(failing_cuts["started"]) == 8 and plans[0].request["form_data"]["references"][0] == "uploads/vp-sound-shot-01-a1.wav"
    assert plans[1].request["form_data"]["references"][0] == "track:A1"
    assert list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


def test_a_generation_dropped_while_its_sounds_are_cut_stops_the_cuts_and_leaves_no_work_folder(core, make_doc, sounds, uploads, failing_cuts, export_storage):
    core.use_h3()
    _media(core)
    doc = _shots_doc(make_doc, 4, references=[HERO], assets=("voice", "music", "hero"), mode="Ref2VA")
    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "s3", "s4"], presets.MINIMAX_H3, "draft").shots
    failing_cuts["delays"] = {f"vp-sound-shot-0{index}-{lane}": 5.0 for index in range(1, 5) for lane in ("a1", "a2")}

    async def dropped():
        task = asyncio.ensure_future(soundtrack.attach_all(core.users["user-1"], {"id": "p-1", "doc": doc}, plans))
        while len(failing_cuts["started"]) < soundtrack.MEASURES:
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(dropped())

    assert len(failing_cuts["started"]) == 4 and sorted(failing_cuts["cancelled"]) == sorted(failing_cuts["started"])
    assert uploads == [] and list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_a_generation_and_its_retry_never_send_the_cut_of_a_silent_track(client, core, make_doc, make_project, levels, measured, stored, export_storage):
    core.use_h3()
    _media(core)
    doc = _doc(
        make_doc,
        [_item("v", "A1", 2, 3), _item("s", "A2", 0, 12, asset="stem")],
        reference_lanes=("A1", "A2"),
        references=[HERO],
        assets=("voice", "stem", "hero"),
        mode="Ref2VA",
    )
    project = make_project(doc=doc)

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.MINIMAX_H3})

    assert response.status_code == 202, response.text
    (take,) = takes.list_takes(project["id"])
    assert take["request"]["form_data"]["references"] == ["uploads/vp-sound-shot-01-a1.wav", "uploads/hero.png"]
    assert "<Audio 1>" in take["prompt_text"] and "<Audio 2>" not in take["prompt_text"]
    assert [path.name for path in stored] == ["vp-sound-shot-01-a1.wav"] and len(measured) == 2

    soundtrack._PEAKS.clear()
    core.fail(take["generation_id"])
    asyncio.run(tracker.Tracker().tick())
    retried = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert retried.status_code == 202, retried.text
    again = takes.get_take(retried.json()["data"]["take"]["id"])
    assert again["request"]["form_data"]["references"] == ["uploads/vp-sound-shot-01-a1.wav", "uploads/hero.png"]
    assert [path.name for path in stored] == ["vp-sound-shot-01-a1.wav"] * 2 and len(measured) == 4


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


def _slices_doc(make_doc, mode="FL2VA", **lanes):
    return _doc(
        make_doc,
        [
            _item("inherit", "A1", 1, 2.5),
            _item("off", "A1", 3.5, 2, reference=False),
            _item("on", "A2", 2, 3, asset="music", reference=True),
            _item("plain", "A2", 0, 2, asset="music"),
            _item("quiet", "A3", 2, 3, asset="rain", reference=False),
        ],
        reference_lanes=("A1", "A3"),
        references=[HERO],
        assets=("voice", "music", "rain", "hero"),
        mode=mode,
        **lanes,
    )


def test_an_item_flag_wins_over_its_track_and_an_item_without_one_follows_its_track(make_doc):
    doc = _slices_doc(make_doc)

    assert [item["id"] for item in director.lane_items(doc, "A1", 0, 10)] == ["inherit"]
    assert [item["id"] for item in director.lane_items(doc, "A2", 0, 10)] == ["on"]
    assert director.lane_items(doc, "A3", 0, 10) == []
    assert [lane["id"] for lane in director.reference_lanes(doc, "s1", 2, 5)] == ["A1", "A2"]
    assert [lane["id"] for lane in director.reference_lanes(doc, "s1", 3.6, 5)] == ["A2"]
    assert [lane["id"] for lane in director.reference_lanes(doc, "s1", 6, 9)] == ["A1", "A3"]
    assert director.item_reference({"reference": True}, {}) and not director.item_reference({"reference": False}, {"reference": True})
    assert director.item_reference({}, {"reference": True}) and not director.item_reference({"reference": "yes"}, {})


def test_ref2va_sends_only_the_items_set_or_left_as_a_reference_and_the_tracks_they_make(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _slices_doc(make_doc, mode="Ref2VA")

    plans = _plans(core, doc, presets.MINIMAX_H3)

    (plan,) = plans.shots
    assert plan.request["form_data"]["references"] == ["track:A1", "track:A2", "uploads/hero.png"]
    assert plan.audio.lanes == ["A1", "A2"]
    assert plans.track_cuts == [TrackCut("s1", "A1", 2.0, 5.0), TrackCut("s1", "A2", 2.0, 5.0)]
    assert _codes(plans) == ["audio_condition"]
    inputs, graph = soundtrack.mix_graph(doc, plan.audio.lanes, 2.0, 5.0, {key: f"/{key}.wav" for key in ("inherit", "off", "on", "plain", "quiet")})
    assert inputs == ["-i", "/inherit.wav", "-i", "/on.wav"]
    assert graph.count("amix=inputs=3") == 1

    for item in doc["audio"]:
        item["reference"] = False
    (alone,) = _plans(core, doc, presets.MINIMAX_H3).shots
    assert alone.request["form_data"]["references"] == ["uploads/hero.png"] and alone.audio is None


def test_a_mixed_shot_mixes_only_the_items_sent_and_its_take_follows_the_same_rule(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _slices_doc(make_doc)

    plans = _plans(core, doc, presets.LTX_2_5)

    (plan,) = plans.shots
    assert (plan.audio.behavior, plan.audio.lanes) == ("mux", ["A1", "A2"])
    assert _codes(plans) == ["audio_mux"]
    inputs, _ = soundtrack.mix_graph(doc, plan.audio.lanes, 2.0, 5.0, {key: f"/{key}.wav" for key in ("inherit", "off", "on", "plain", "quiet")})
    assert inputs == ["-i", "/inherit.wav", "-i", "/on.wav"]

    doc["audio"][0]["reference"] = False
    doc["audio"][2].pop("reference")
    plans = _plans(core, doc, presets.LTX_2_5)
    assert plans.shots[0].audio is None and _sound(plans) == []


def test_the_track_warnings_follow_the_items_sent(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _slices_doc(make_doc, A2={"mute": True})
    doc["lanes"][3]["reference"] = True

    plans = _plans(core, doc, presets.LTX_2_5)

    assert [(warning["code"], warning["data"].get("lane_id")) for warning in _sound(plans)] == [
        ("audio_track_muted", "A2"),
        ("audio_track_empty", "A4"),
        ("audio_mux", None),
    ]
    assert plans.shots[0].audio.lanes == ["A1"]

    core.use_wan()
    lone = _doc(make_doc, [_item("later", "A2", 8, 2, asset="music", reference=True)], reference_lanes=())
    assert _sound(_plans(core, lone, presets.WAN)) == []
    lone["audio"][0]["start"] = 3
    assert _codes(_plans(core, lone, presets.WAN)) == ["audio_ignored"]


def test_the_measure_of_a_track_and_its_cache_key_read_only_the_items_sent(core, make_doc, slow_peaks, sounds, export_storage):
    _media(core)
    user = core.users["user-1"]
    doc = _doc(make_doc, [_item("v", "A1", 2, 3), _item("m", "A1", 2, 3, asset="music", reference=False)], reference_lanes=("A1",))
    cut = TrackCut("s1", "A1", 2.0, 5.0)
    sources = soundtrack._Sources(user, doc, "p-1", None)

    signature = sources.signature("A1", 2.0, 5.0)
    assert [part for part in signature if part.startswith("library:")] == ["library:uploads/voice.wav"]

    asyncio.run(soundtrack.silent_lanes(user, "p-1", doc, [cut]))
    (command,) = slow_peaks["calls"]
    assert [command[index + 1] for index, part in enumerate(command) if part == "-i"] == [str(sounds["voice"])]

    doc["audio"][1].pop("reference")
    assert soundtrack._Sources(user, doc, "p-1", None).signature("A1", 2.0, 5.0) != signature
    doc["audio"][0]["reference"] = False
    doc["audio"][1]["reference"] = False
    assert soundtrack._Sources(user, doc, "p-1", None).signature("A1", 2.0, 5.0) is None


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_a_track_whose_loud_item_is_switched_off_is_measured_silent_under_a_guided_shot(core, make_doc, levels, measured, export_storage):
    _media(core)
    user = core.users["user-1"]
    doc = _doc(make_doc, [_item("v", "A1", 2, 3, reference=False), _item("s", "A1", 0, 12, asset="stem")], assets=("voice", "stem"))
    cut = TrackCut("s1", "A1", 2.0, 5.0)

    assert asyncio.run(soundtrack.silent_lanes(user, "p-1", doc, [cut])) == {"s1": ["A1"]}
    assert asyncio.run(soundtrack.track_peak(shutil.which("ffmpeg"), soundtrack._Sources(user, doc, "p-1", export_storage), cut)) <= -90

    doc["audio"][0].pop("reference")
    assert asyncio.run(soundtrack.silent_lanes(user, "p-1", doc, [cut])) == {}
    assert len(measured) == 3


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_attaching_a_mixed_shot_leaves_the_items_switched_off_out_of_the_mix(core, make_doc, sounds, stored, export_storage):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, [_item("v", "A1", 2, 1, reference=False), _item("m", "A2", 3, 2, asset="music", reference=True)], reference_lanes=("A1",))
    (plan,) = _plans(core, doc, presets.LTX_2_5).shots
    assert plan.audio.lanes == ["A2"]

    asyncio.run(soundtrack.attach(core.users["user-1"], {"id": "p-1", "doc": doc}, plan))

    samples = _samples(stored[0])
    assert len(samples) == 3 * RATE
    assert _rms(samples, 0.1, 0.9) < 1e-4
    assert _rms(samples, 1.1, 2.9) == pytest.approx(0.5 / math.sqrt(2) * 10 ** (-2 / 20), rel=0.05)


def test_the_schema_takes_an_optional_reference_flag_on_an_audio_item(make_doc):
    doc = _doc(make_doc, [_item("v", "A1", 2, 3, reference=False), _item("w", "A2", 5, 1, reference=True), _item("x", "A3", 6, 1)])

    validate_doc(doc)

    for value in ("yes", 1, None):
        broken = copy.deepcopy(doc)
        broken["audio"][0]["reference"] = value
        with pytest.raises(DocError):
            validate_doc(broken)
