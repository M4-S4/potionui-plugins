import asyncio
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import core_bridge, director, generation, presets, projects, reception, soundtrack, takes, vreftrack
from backend.projects import DocError, validate_doc

HAS_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
MIGRATION = json.loads((Path(__file__).parent / "fixtures" / "vref_migration.json").read_text(encoding="utf-8"))
LIBRARY = {"walk": "lib-walk", "dock": "lib-dock", "own": "lib-own", "face": "lib-face", "rain": "lib-rain", "wind": "lib-wind", "hail": "lib-hail", "take": "lib-take"}


def _video(asset_id, origin=True):
    return {"id": asset_id, "kind": "video", "origin": {"kind": "library", "itemId": LIBRARY[asset_id]} if origin else None}


def _media(core):
    for name, item_id in LIBRARY.items():
        kind = "image" if name == "face" else "audio" if name in ("rain", "wind", "hail") else "video"
        suffix = {"image": "png", "audio": "wav", "video": "mp4"}[kind]
        core.add_media({"kind": "library", "item_id": item_id}, f"uploads/{name}.{suffix}", kind)


def _doc(make_doc, clips=None, tracks=(), items=(), references=(), assets=None, mode="Ref2VA", prompts=(), language="en"):
    doc = make_doc(
        clips=clips or [{"id": "s1", "start": 4, "dur": 4, "label": "Dock"}],
        references=references,
        assets=assets if assets is not None else [_video("walk"), _video("dock"), _video("own"), {"id": "face", "kind": "image", "origin": {"kind": "library", "itemId": "lib-face"}}],
        prompts=prompts,
        direction={"mode": mode},
        language=language,
    )
    doc["engine"].update(preset=presets.MINIMAX_H3, model=None)
    if tracks:
        doc["vrefTracks"] = [{"name": f"Track {track['slot']}", "role": "motion", **track} for track in tracks]
    if items:
        doc["vrefItems"] = [{"srcIn": 0, **item} for item in items]
    return doc


def _plans(core, doc, preset_id=presets.MINIMAX_H3, shots=("s1",)):
    return director.build_plans(core.users["user-1"], doc, list(shots), preset_id, "draft")


def _size(plan):
    return tuple(int(side) for side in plan.resolution.split("x"))


def _codes(plans, prefix=("video_", "audio_track")):
    return [(item["code"], (item.get("data") or {}).get("slot")) for item in plans.warnings if item["code"].startswith(prefix)]


def _walk(slot=1, role="motion", **extra):
    return {"id": f"t{slot}", "slot": slot, "role": role, **extra}


def _item(item_id, track, asset, start, dur, **extra):
    return {"id": item_id, "track": track, "assetId": asset, "start": start, "dur": dur, **extra}


def _instruction(text, shot="s1"):
    return {"id": f"p-{shot}", "shotId": shot, "start": 0, "dur": 4, "text": text}


@pytest.mark.parametrize("case", MIGRATION["cases"], ids=[case["name"] for case in MIGRATION["cases"]])
def test_the_server_migrates_the_tracks_as_the_page_does(case):
    doc = copy.deepcopy(case["doc"])
    before = copy.deepcopy(doc)

    migrated = projects.migrate(doc)

    assert {key: migrated[key] for key in (projects.VREF_TRACKS, projects.VREF_ITEMS) if key in migrated} == case["expected"]
    assert doc == before


def test_a_document_whose_tracks_need_nothing_is_the_same_object(make_doc):
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 4)])
    doc["clips"][0]["referenceOverrides"] = {"excludeVrefs": ["t1"]}

    assert projects.migrate(doc) is doc
    validate_doc(doc)


def test_the_schema_takes_three_tracks_at_most_of_known_slots_and_roles_and_items_from_a_take(make_doc):
    doc = _doc(
        make_doc,
        tracks=[_walk(1), _walk(2, "continuation", seconds=3.5, off=True), _walk(3)],
        items=[_item("i1", "t1", "walk", 0, 4, fromTake="take-1"), _item("i2", "t2", None, 4, 2, fromTake=None)],
    )
    doc["audio"] = [{"id": "a1", "assetId": "walk", "lane": "A1", "start": 0, "dur": 4, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, "reference": True, "fromTake": "take-1"}]
    validate_doc(doc)

    for broken in (
        {"vrefTracks": [*doc["vrefTracks"], _walk(1)]},
        {"vrefTracks": [{**doc["vrefTracks"][0], "slot": 4}]},
        {"vrefTracks": [{**doc["vrefTracks"][0], "role": "aspect"}]},
        {"vrefTracks": [{**doc["vrefTracks"][0], "seconds": 0}]},
        {"vrefItems": [{**doc["vrefItems"][0], "lane": "A1"}]},
    ):
        with pytest.raises(DocError):
            validate_doc({**doc, **broken})


def test_a_motion_track_goes_after_the_videos_of_the_shot_and_before_those_of_the_project(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": "g", "space": "mouvement", "type": "Control video", "assetId": "dock", "role": "Mouvement", "scope": {"type": "global"}},
        {"id": "o", "space": "mouvement", "type": "Control video", "assetId": "own", "role": "Mouvement", "scope": {"type": "shot", "shotId": "s1"}},
    ]
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 12, srcIn=1.5)], references=references)

    plans = _plans(core, doc)
    plan = plans.shots[0]

    assert plan.request["form_data"]["references"] == ["uploads/own.mp4", "vtrack:t1", "uploads/dock.mp4"]
    assert plan.summary()["video"] == {"tracks": [1]} and plan.needs_cut and not plan.needs_audio
    [cut] = plan.video
    assert (cut.slot, cut.role, cut.frames, cut.start, cut.end, cut.size) == (1, "motion", 56, 4.0, 6.333333, _size(plan))
    assert [(piece.item_id, piece.asset_id, piece.source) for piece in cut.pieces] == [("i1", "walk", 5.5)]
    assert "<Video 2> is the source of the motion of [Shot 1]." in plan.prompt_text
    assert "<Video 2> (motion of [Shot 1]): attribute_transfer" in plan.prompt_text
    assert "The subjects move as in <Video 2>." in plan.prompt_text
    assert "summary: [reference generation] A 4-second shot" in plan.prompt_text
    assert _codes(plans) == []


def test_a_continuation_track_cuts_what_precedes_the_shot_and_adds_its_task_to_the_summary(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(
        make_doc,
        tracks=[_walk(2, "continuation", seconds=4)],
        items=[_item("i1", "t2", "walk", 0, 2.5), _item("i2", "t2", "dock", 3, 1, srcIn=2)],
        prompts=[_instruction("Lina walks on, as in @vref2.")],
    )

    plan = _plans(core, doc).shots[0]

    [cut] = plan.video
    assert (cut.frames, cut.start, cut.end) == (73, 0.458333, 4.0)
    assert [(piece.item_id, piece.start, piece.end, piece.source) for piece in cut.pieces] == [("i1", 0.458333, 2.5, 0.458333), ("i2", 3.0, 4.0, 2.0)]
    assert "summary: [video continuation] + [reference generation] A 4-second shot that continues <Video 1>, made from" in plan.prompt_text
    assert "<Video 1> is the footage that [Shot 1] continues." in plan.prompt_text
    assert "<Video 1> (continued by [Shot 1]): fully_preserved" in plan.prompt_text
    assert "[Shot 1] Lina walks on, as in <Video 1>. The shot continues from the last frame of <Video 1>." in plan.prompt_text
    assert "@vref" not in plan.prompt_text


def test_the_texts_of_a_track_follow_the_language_of_the_prompts(core, make_doc):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, tracks=[_walk(1, "continuation")], items=[_item("i1", "t1", "walk", 0, 4)], language="fr")

    prompt = _plans(core, doc).shots[0].prompt_text

    assert "summary: [video continuation] + [reference generation] Un plan de 4 secondes qui prolonge <Video 1>" in prompt
    assert "<Video 1> est la séquence que [Shot 1] prolonge." in prompt
    assert "Le plan prolonge la dernière image de <Video 1>." in prompt


def test_a_track_cited_but_not_sent_is_left_out_of_the_text_and_said(core, make_doc):
    core.use_h3()
    core.use_wan()
    _media(core)
    clips = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4, "engine": {"preset": presets.WAN, "model": None, "profile": "FL2VA"}}]
    doc = _doc(
        make_doc,
        clips=clips,
        tracks=[_walk(1), _walk(2)],
        items=[_item("i1", "t1", "walk", 0, 8), _item("i2", "t2", "dock", 0, 8)],
        prompts=[_instruction("@vref1 Lina waits like @VREF2.", "s1"), _instruction("Lina runs as in @vref1, then @vref3.", "s2")],
    )
    doc["clips"][0]["referenceOverrides"] = {"excludeVrefs": ["t2"]}

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], presets.MINIMAX_H3, "draft", overrides=True)
    by_shot = {plan.shot_id: plan for plan in plans.shots}
    warnings = sorted((item["data"]["shot_id"], item["code"], item["data"]["slot"]) for item in plans.warnings if item["code"].startswith("video_"))

    assert "[Shot 1] <Video 1> Lina waits like." in by_shot["s1"].prompt_text
    assert by_shot["s2"].prompt_text.startswith("Lina runs as in, then.")
    assert warnings == [
        ("s1", "video_tag_ignored", 2),
        ("s2", "video_tag_ignored", 1),
        ("s2", "video_tag_ignored", 3),
        ("s2", "video_track_ignored", 1),
        ("s2", "video_track_ignored", 2),
    ]
    assert director.cited_slots("@vref1 @vref12 x@vref2 @vref1") == [1]
    assert director.cite_tracks("Go @vref1", {1: "<Video 3>"}) == "Go <Video 3>"


def test_the_prompts_route_says_the_label_each_track_of_a_shot_goes_as(core, client, make_doc, make_project):
    core.use_h3()
    core.use_wan()
    _media(core)
    references = [{"id": "o", "space": "mouvement", "type": "Control video", "assetId": "own", "role": "Mouvement", "scope": {"type": "shot", "shotId": "s1"}}]
    clips = [{"id": "s1", "start": 4, "dur": 4}, {"id": "s2", "start": 8, "dur": 4, "engine": {"preset": presets.WAN, "model": None, "profile": "FL2VA"}}]
    doc = _doc(
        make_doc,
        clips=clips,
        tracks=[_walk(1), _walk(3, "continuation")],
        items=[_item("i1", "t1", "walk", 0, 12), _item("i3", "t3", "dock", 0, 12)],
        references=references,
        prompts=[_instruction("Lina walks as in @vref3.", "s1")],
    )
    project = make_project(doc=doc)

    response = client.post(f"/api/plugins/video-producer/projects/{project['id']}/prompts", json={"shots": ["s1", "s2"], "preset_id": presets.MINIMAX_H3, "doc": doc})

    composed = {item["shot_id"]: item for item in response.json()["data"]["prompts"]}
    assert composed["s1"]["video_tracks"] == [{"slot": 1, "track_id": "t1", "label": "<Video 2>"}, {"slot": 3, "track_id": "t3", "label": "<Video 3>"}]
    assert "Lina walks as in <Video 3>." in composed["s1"]["prompt"]
    assert composed["s2"]["video_tracks"] == []


def test_a_start_image_is_not_asked_for_the_tracks_the_shot_cites(make_doc):
    from backend import keyframes

    doc = _doc(make_doc, prompts=[_instruction("Lina turns, as in @vref1.")])

    assert "@vref" not in keyframes.keyframe_prompt(doc, doc["clips"][0], [], "first")


def test_the_reference_tracks_past_the_limit_on_sounds_are_said(core, make_doc):
    core.use_h3()
    _media(core)
    sounds = [{"id": name, "kind": "audio", "origin": {"kind": "library", "itemId": LIBRARY[name]}} for name in ("rain", "wind", "hail")]
    references = [
        {"id": f"r-{name}", "space": "son", "type": "Ambiance", "assetId": name, "role": "Son", "scope": {"type": "shot", "shotId": "s1"}} for name in ("rain", "wind", "hail")
    ]
    references.append({"id": "r-face", "space": "identite", "type": "Personnage", "assetId": "face", "role": "Identité", "scope": {"type": "shot", "shotId": "s1"}})
    doc = _doc(make_doc, references=references, assets=[*sounds, {"id": "face", "kind": "image", "origin": {"kind": "library", "itemId": "lib-face"}}])
    doc["lanes"][0]["reference"] = True
    doc["audio"] = [{"id": "a1", "assetId": "rain", "lane": "A1", "start": 0, "dur": 12, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0}]

    plans = _plans(core, doc)

    assert "track:A1" not in plans.shots[0].request["form_data"]["references"]
    assert [item["data"] for item in plans.warnings if item["code"] == "audio_track_trimmed"] == [{"shot_id": "s1", "lane_id": "A1"}]


def test_three_videos_of_the_shot_trim_the_track_and_an_unreadable_or_short_one_is_said(core, make_doc):
    core.use_h3()
    _media(core)
    references = [
        {"id": f"o{index}", "space": "mouvement", "type": "Control video", "assetId": asset, "role": "Mouvement", "scope": {"type": "shot", "shotId": "s1"}}
        for index, asset in enumerate(("walk", "dock", "own"), 1)
    ]
    doc = _doc(
        make_doc,
        tracks=[_walk(1), _walk(2), _walk(3, "continuation")],
        items=[_item("i1", "t1", "take", 4, 4), _item("i2", "t2", "gone", 4, 4), _item("i3", "t3", "take", 3, 1)],
        references=references,
        assets=[_video("walk"), _video("dock"), _video("own"), _video("take"), _video("gone", origin=False)],
    )

    plans = _plans(core, doc)

    assert plans.shots[0].video == []
    assert _codes(plans) == [("video_track_missing", 2), ("video_track_short", 3), ("video_track_trimmed", 1)]


def test_the_cut_is_written_at_the_size_of_the_take_by_default_and_at_the_canvas_when_the_rule_says_so(core, make_doc, monkeypatch):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 12)])

    assert reception.VIDEO_TRACKS["size"] == reception.DRAFT
    draft = _plans(core, doc).shots[0]
    vertical = _plans(core, {**doc, "aspect": "9:16"}).shots[0]
    monkeypatch.setitem(reception.VIDEO_TRACKS, "size", reception.CANVAS)
    canvas = _plans(core, doc).shots[0]
    tall = _plans(core, {**doc, "aspect": "9:16"}).shots[0]

    assert draft.video[0].size == _size(draft)
    assert vertical.video[0].size == _size(vertical)
    assert canvas.video[0].size == (1344, 768)
    assert tall.video[0].size == (768, 1344)


def test_the_cut_follows_the_ratio_of_the_takes_not_the_format_of_the_film(core, make_doc, monkeypatch):
    core.use_h3()
    _media(core)
    doc = {**_doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 12)]), "aspect": "2.39:1"}

    plan = _plans(core, doc).shots[0]
    monkeypatch.setitem(reception.VIDEO_TRACKS, "size", reception.CANVAS)
    canvas = _plans(core, doc).shots[0]

    assert plan.resolution == "832x480"
    assert plan.video[0].size == (832, 480)
    assert canvas.video[0].size == (1344, 768)


def test_without_ffmpeg_a_shot_that_sends_a_track_is_blocked(core, make_doc, monkeypatch):
    core.use_h3()
    _media(core)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 12)])

    plans = _plans(core, doc)

    assert [(block["code"], block["data"]) for block in plans.blocks] == [("video_ffmpeg_missing", {"shot_ids": ["s1"]})]


def test_the_cut_graph_reads_each_part_from_its_source_and_holds_exactly_the_frames():
    graph = vreftrack.cut_graph([(0.5, 2.0), (2.0, 2.5)], 56, (832, 480))

    assert graph.startswith("[0:v:0]trim=start=0.5:end=2,setpts=PTS-STARTPTS,fps=24,scale=832:480:force_original_aspect_ratio=increase:flags=lanczos,crop=832:480")
    assert "[1:v:0]trim=start=2:end=2.5," in graph
    assert graph.endswith("[v0][v1]concat=n=2:v=1:a=0,tpad=stop_mode=clone:stop=24,trim=end_frame=56,setpts=PTS-STARTPTS[vout]")
    command = vreftrack.cut_command("ffmpeg", ["-i", "a.mp4"], graph, 56, Path("out.mp4"))
    assert command[-7:] == ["-pix_fmt", "yuv420p", "-r", "24", "-frames:v", "56", "out.mp4"] and "-an" in command


def _source(path: Path, seconds: float, size: str = "640x360", rate: int = 30, sound: bool = False) -> Path:
    inputs = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}"]
    if sound:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}"]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-c:v", "libx264", "-pix_fmt", "yuv420p", *(["-c:a", "aac"] if sound else []), str(path)], check=True)
    return path


def _probe(path: Path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,width,height,nb_read_frames,r_frame_rate", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)["streams"]


@pytest.fixture
def films(tmp_path, monkeypatch):
    folder = tmp_path / "films"
    folder.mkdir()
    files = {
        "walk": _source(folder / "walk.mp4", 6.0),
        "dock": _source(folder / "dock.mp4", 4.0, "480x480", 25),
        "take": _source(folder / "take.mp4", 4.0, sound=True),
    }

    def local(kind, value, target):
        return files.get(Path(value).stem)

    monkeypatch.setattr(core_bridge, "local_media_file", local)
    return files


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    saved = []

    async def save(user, path):
        keep = tmp_path / "library" / Path(path).name
        keep.parent.mkdir(exist_ok=True)
        shutil.copy(path, keep)
        saved.append(keep)
        return {"value": f"uploads/{keep.name}", "media_type": "video", "original_filename": keep.name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save)
    return saved


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("size", [reception.CANVAS, reception.DRAFT])
def test_ffmpeg_writes_the_cut_of_a_track_with_exactly_its_frames_at_its_size_and_without_sound(core, make_doc, films, uploads, export_storage, monkeypatch, size):
    core.use_h3()
    _media(core)
    monkeypatch.setitem(reception.VIDEO_TRACKS, "size", size)
    doc = _doc(make_doc, tracks=[_walk(1, "continuation", seconds=4)], items=[_item("i1", "t1", "walk", 0, 2.5, srcIn=1), _item("i2", "t1", "dock", 3, 1, srcIn=2)])
    plan = _plans(core, doc).shots[0]

    asyncio.run(soundtrack.attach_all(core.users["user-1"], {"id": "p-1", "doc": doc}, [plan]))

    [stored] = uploads
    assert stored.name == "vp-vref-shot-01-vref1.mp4"
    assert plan.request["form_data"]["references"] == ["uploads/vp-vref-shot-01-vref1.mp4"]
    [stream] = _probe(stored)
    width, height = plan.video[0].size
    assert (stream["codec_type"], stream["width"], stream["height"], int(stream["nb_read_frames"]), stream["r_frame_rate"]) == ("video", width, height, 73, "24/1")
    assert (width, height) == ((1344, 768) if size == reception.CANVAS else tuple(int(side) for side in plan.resolution.split("x")))
    assert list((export_storage / "video_producer" / "audio" / "user-1").iterdir()) == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_ffmpeg_cuts_a_motion_track_under_each_shot_and_a_take_can_also_lay_its_sound_on_a_reference_track(core, make_doc, films, uploads, export_storage):
    core.use_h3()
    _media(core)
    clips = [{"id": "s1", "start": 0, "dur": 3}, {"id": "s2", "start": 3, "dur": 3}]
    doc = _doc(make_doc, clips=clips, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 6)], assets=[_video("walk"), _video("take")])
    doc["lanes"][0]["reference"] = True
    doc["audio"] = [{"id": "a1", "assetId": "take", "lane": "A1", "start": 0, "dur": 4, "srcIn": 0, "fadeIn": 0, "fadeOut": 0, "gain": 0, "fromTake": "take-1"}]
    plans = _plans(core, doc, shots=("s1", "s2")).shots

    asyncio.run(soundtrack.attach_all(core.users["user-1"], {"id": "p-1", "doc": doc}, plans))

    assert [path.name for path in uploads] == ["vp-sound-shot-01-a1.wav", "vp-vref-shot-01-vref1.mp4", "vp-sound-shot-02-a1.wav", "vp-vref-shot-02-vref1.mp4"]
    assert [plan.request["form_data"]["references"] for plan in plans] == [
        ["uploads/vp-sound-shot-01-a1.wav", "uploads/vp-vref-shot-01-vref1.mp4"],
        ["uploads/vp-sound-shot-02-a1.wav", "uploads/vp-vref-shot-02-vref1.mp4"],
    ]
    assert [int(_probe(path)[0]["nb_read_frames"]) for path in uploads if path.suffix == ".mp4"] == [56, 56]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_a_track_whose_video_is_gone_at_the_cut_blocks_the_generation_with_its_shot(core, make_doc, films, uploads, export_storage):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "own", 0, 12)])
    plan = _plans(core, doc).shots[0]

    with pytest.raises(generation.Blocked) as caught:
        asyncio.run(generation.with_sound(core.users["user-1"], {"id": "p-1", "doc": doc}, [plan]))

    assert [(block["code"], block["data"]) for block in caught.value.blocks] == [("video_source_missing", {"shot_id": "s1"})]
    assert uploads == []


def test_a_take_keeps_what_it_received_of_the_tracks(core, make_doc, make_project):
    core.use_h3()
    _media(core)
    doc = _doc(make_doc, tracks=[_walk()], items=[_item("i1", "t1", "walk", 0, 12)])
    project = make_project(doc=doc)
    plan = _plans(core, doc).shots[0]
    plan.preset_id = presets.MINIMAX_H3

    take = generation.create(
        core.users["user-1"], project["id"], plan, preset_id=presets.MINIMAX_H3, quality="draft", kind="shot", seed=7, variant="A", minutes=0
    )

    trace = {"slot": 1, "track_id": "t1", "role": "motion", "start": 4.0, "end": 6.333333, "frames": 56, "seconds": 2.333333, "size": list(_size(plan)), "items": ["i1"]}
    assert take["video_refs"] == [trace]
    assert takes.public(take)["video_refs"] == [trace]
    assert takes.get_take(take["id"])["video_refs"] == [trace]
