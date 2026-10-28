import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import bible, catalog, core_bridge, director, engine_options, presets, reception, sheetvideo, soundtrack
from backend.catalog import FL2VA, REF2VA

HAS_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
LIBRARY = {"f1": "lib-f1", "f2": "lib-f2", "f3": "lib-f3", "g1": "lib-g1", "h1": "lib-h1", "k1": "lib-k1", "q1": "lib-q1"}
SHOT = {"id": "s1", "start": 0, "dur": 5, "label": "Quay"}
INSTRUCTION = "Fisher mends a net on the quay, then looks out to sea."


def _picture(name):
    return {"id": f"a-{name}", "kind": "image", "name": name, "origin": {"kind": "library", "itemId": LIBRARY[name]}}


def _reference(name):
    return {"id": name, "name": name, "space": "identite", "type": "image", "assetId": f"a-{name}", "scope": None}


def _media(core):
    for name, item in LIBRARY.items():
        core.add_media({"kind": "library", "item_id": item}, f"uploads/{name}.png", "IMAGE")


def _doc(make_doc, characters=("c-f",), place="p-q", props="", frames=()):
    names = list(LIBRARY)
    doc = make_doc(
        clips=[{**SHOT, "cast": {"characters": list(characters), "place": place}}],
        prompts=[{"id": "p", "shotId": "s1", "text": INSTRUCTION}],
        references=[_reference(name) for name in names],
        assets=[_picture(name) for name in names],
        frames=frames,
    )
    doc["bible"] = {
        "characters": [
            {"id": "c-f", "label": "Fisher", "text": "an old fisherman with a white beard and a yellow oilskin", "props": props, "references": ["f1", "f2", "f3"]},
            {"id": "c-g", "label": "Girl", "text": "a girl in a red coat", "references": ["g1"]},
            {"id": "c-n", "label": "Nobody", "text": "a man in grey", "references": []},
            {"id": "c-h", "label": "Hal", "text": "a sailor", "references": ["h1"]},
            {"id": "c-k", "label": "Kim", "text": "a cook", "references": ["k1"]},
        ],
        "places": [{"id": "p-q", "label": "Quay", "text": "a stone harbour quay with a red lighthouse", "references": ["q1"]}],
    }
    doc["engine"].update(preset=presets.LTX_2_5, model=None, profile=REF2VA)
    return doc


def _plans(core, doc, quality="draft"):
    return director.build_plans(core.users["user-1"], doc, ["s1"], presets.LTX_2_5, quality, profile=REF2VA)


def _codes(plans):
    return [item["code"] for item in plans.warnings if item["code"].startswith("sheet_")]


def test_the_sheet_follows_the_size_rate_and_length_the_ingredients_ic_lora_was_trained_at():
    assert reception.sheet_size(16 / 9) == (768, 448)
    assert reception.sheet_size(768 / 448) == (768, 448)
    assert reception.sheet_size(1.0) == (576, 576)
    assert reception.sheet_size(9 / 16) == (448, 768)
    assert reception.sheet_size(0) == (768, 448)
    assert [reception.sheet_frames(seconds) for seconds in (5.0, 5.04, 3.0, 4.0, 0.0)] == [121, 121, 73, 97, 1]
    assert reception.takes_sheet(bible.LTX, REF2VA) and not reception.takes_sheet(bible.H3, REF2VA) and not reception.takes_sheet(bible.LTX, FL2VA)
    assert reception.takes_references(REF2VA) and reception.takes_references(REF2VA, bible.H3) and not reception.takes_references(REF2VA, bible.LTX)
    assert reception.layout(bible.LTX, REF2VA) == bible.SHEET_LAYOUT
    assert reception.layout(bible.LTX, FL2VA) == bible.CAST_LAYOUT


def test_the_sheet_puts_the_characters_in_a_band_across_the_top_and_the_place_across_the_bottom():
    assert reception.sheet_layout((768, 448), [2], True) == ([(8, 8, 372, 234), (388, 8, 372, 234)], (8, 250, 752, 190))
    assert reception.sheet_layout((768, 448), [2, 1, 1], True)[0] == [(8, 8, 182, 234), (198, 8, 182, 234), (388, 8, 182, 234), (578, 8, 182, 234)]
    assert reception.sheet_layout((768, 448), [1], False) == ([(8, 8, 752, 432)], None)
    assert reception.sheet_layout((768, 448), [], True) == ([], (8, 8, 752, 432))


def test_a_sheet_counts_for_the_measured_factor_in_the_time_of_its_take():
    form = {"video_director": {"ic_lora": [{"id": reception.SHEET_ID}]}}
    assert reception.sheet_work(form) == 2.1
    assert reception.sheet_work({"video_director": {"ic_lora": [{"id": director.GUIDE_ID}]}}) == 1.0
    assert reception.sheet_work({}) == 1.0


def test_ltx_2_5_offers_ref2va_when_its_director_mode_takes_an_ic_lora(core):
    core.use_ltx25()
    director_modes = {"video_director": {"preset_modes": ["video"], "modes": {"t2v": {}, "director": {"ic_lora": True}}}}
    assert catalog.profiles(presets.LTX_2_5, director_modes, ["video"]) == [FL2VA, REF2VA]
    assert catalog.profiles(presets.LTX_2_5, {"video_director": {"preset_modes": ["video"], "modes": {"t2v": {}}}}, ["video"]) == [FL2VA]
    assert catalog.profiles(presets.LTX_2, director_modes, ["video"]) == [FL2VA]
    assert catalog.run_modes(presets.LTX_2_5, director_modes, ["video"], None) == ["video"]


def test_a_ref2va_shot_on_ltx_2_5_is_made_from_its_reference_sheet_in_one_distilled_pass_without_first_frame(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc)

    plans = _plans(core, doc)

    assert plans.blocks == []
    (plan,) = plans.shots
    assert (plan.director_mode, plan.preset_mode, plan.resolution, plan.fps, plan.seconds) == ("director", "video", "768x448", 24.0, round(121 / 24, 6))
    form = plan.request["form_data"]
    document = form["video_director"]
    assert document["mode"] == "director" and document["media"] == []
    assert document["settings"] == {"fps": 24.0, "duration": round(121 / 24, 6), "resolution": "768x448", "seed": -1}
    assert document["ic_lora"] == [
        {
            "id": "ic-sheet",
            "lora": {"model": f"model:id-{reception.SHEET['lora']}", "strength": 1.0},
            "reference": {"path": "sheet:s1", "relative_path": "sheet:s1", "type": "video"},
            "strength": 1.0,
        }
    ]
    assert {name: form[name] for name in ("speed_profile", "steps", "cfg", "sampler", "resolution", "fps")} == {
        "speed_profile": "distilled",
        "steps": 8,
        "cfg": 1.0,
        "sampler": "euler_ancestral",
        "resolution": "768x448",
        "fps": 24.0,
    }
    assert "references" not in form
    assert plan.sheet.trace() == {
        "size": [768, 448],
        "frames": 121,
        "fps": 24.0,
        "panels": [
            {"reference_id": "f1", "asset_id": "a-f1", "card_id": "c-f", "kind": "characters", "box": [8, 8, 372, 234]},
            {"reference_id": "f2", "asset_id": "a-f2", "card_id": "c-f", "kind": "characters", "box": [388, 8, 372, 234]},
            {"reference_id": "q1", "asset_id": "a-q1", "card_id": "p-q", "kind": "places", "box": [8, 250, 752, 190]},
        ],
    }
    assert plan.needs_cut and plan.summary()["sheet"]["frames"] == 121
    assert plan.reference.layout == bible.SHEET_LAYOUT
    assert plan.prompt_text == (
        "### Reference Sheet Description "
        "**Top Row Left (Character):** A frontal close-up of the face of an old fisherman with a white beard and a yellow oilskin. "
        "**Top Row Right (Character):** The same character shown full body, standing, front view. "
        "**Bottom Row (Setting):** A stone harbour quay with a red lighthouse. "
        "### Target Description "
        f"{INSTRUCTION} Fisher: an old fisherman with a white beard and a yellow oilskin. Setting — Quay: a stone harbour quay with a red lighthouse."
    )
    assert plan.work_scale == pytest.approx(8 / 24 * 2.1)
    assert _codes(plans) == []


def test_the_sheet_forces_the_upscale_off_and_the_distilled_recipe_over_the_project_options(core, make_doc):
    core.use_ltx25()
    core.fields[(presets.LTX_2_5, "video")]["upscale"] = {
        "type": "select",
        "required": False,
        "default": "x2",
        "options": [{"value": "off", "label": "OFF"}, {"value": "x2", "label": "X2"}],
        "recommendations": [],
    }
    _media(core)
    doc = _doc(make_doc)
    doc["engine"]["options"] = {presets.LTX_2_5: {"steps": 30, "upscale": "x2"}}

    form = _plans(core, doc).shots[0].request["form_data"]

    assert (form["upscale"], form["steps"], form["speed_profile"]) == ("off", 8, "distilled")


def test_the_sheet_says_what_it_leaves_out(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc, characters=("c-f", "c-g", "c-n", "c-h", "c-k"), props="a coiled rope", frames=[{"id": "fr", "shotId": "s1", "time": 0, "assetId": "a-g1", "role": "first"}])

    plans = _plans(core, doc)

    (plan,) = plans.shots
    assert [(panel.card_id, panel.reference_id) for panel in plan.sheet.panels] == [("c-f", "f1"), ("c-f", "f2"), ("c-g", "g1"), ("c-h", "h1"), ("p-q", "q1")]
    assert _codes(plans) == ["sheet_card_without_image", "sheet_crowded", "sheet_props_text_only", "sheet_first_frame"]
    crowded = next(item for item in plans.warnings if item["code"] == "sheet_crowded")
    assert crowded["data"]["left_out"] == ["Kim"]
    assert "**Top Row Panel 3 (Character):** A frontal close-up of the face of a girl in a red coat. **Top Row Panel 4 (Character):** A frontal close-up of the face of a sailor. " in plan.prompt_text
    assert plan.request["form_data"]["video_director"]["media"] == []


def test_a_shot_without_any_picture_on_its_cards_is_blocked(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc, characters=("c-n",), place=None)

    plans = _plans(core, doc)

    assert [block["code"] for block in plans.blocks] == ["sheet_no_image"]


def test_without_the_ingredients_ic_lora_a_sheet_shot_is_blocked_with_the_file_to_install(core, make_doc):
    core.use_ltx25()
    _media(core)
    core.missing.add(reception.SHEET["lora"])

    plans = _plans(core, _doc(make_doc))

    assert [(block["code"], block["data"]["file"], block["data"]["repo"]) for block in plans.blocks] == [
        ("sheet_lora_missing", reception.SHEET["lora"], "Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients")
    ]


def test_a_sheet_shot_is_not_rendered_again_at_the_final_size(core, make_doc):
    core.use_ltx25()
    _media(core)

    plans = _plans(core, _doc(make_doc), quality="final")

    assert [block["code"] for block in plans.blocks] == ["sheet_final_size"]


def test_another_aspect_makes_the_sheet_at_the_closest_size_and_says_so(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc)
    doc["aspect"] = "1:1"

    plans = _plans(core, doc)

    assert plans.shots[0].resolution == "576x576"
    assert _codes(plans) == ["sheet_off_bucket"]


def test_the_sheet_part_of_the_prompt_can_be_replaced_by_the_shot(core, make_doc):
    core.use_ltx25()
    _media(core)
    doc = _doc(make_doc)
    composed = _plans(core, doc).shots[0].reference.composed
    doc["clips"][0]["referencePrompt"] = {"layout": "sheet", "parts": {"sheet": "**Top Row (Character):** Mine.", "cast": ""}, "base": composed}

    plan = _plans(core, doc).shots[0]

    assert plan.prompt_text == f"### Reference Sheet Description **Top Row (Character):** Mine. ### Target Description {INSTRUCTION}"


def test_the_measure_of_a_sheet_take_counts_as_one_made_without_the_sheet(core, make_doc):
    core.use_ltx25()
    _media(core)
    plan = _plans(core, _doc(make_doc)).shots[0]
    take = {"preset_id": presets.LTX_2_5, "mode": "video", "request": plan.request}

    assert engine_options.take_scale(take) == pytest.approx(8 / 24 * 2.1)


def test_the_sheet_graph_scales_each_picture_into_its_box_without_cropping():
    sheet = director.SheetPlan((768, 448), 121, 24.0, [director.SheetPanel("f1", "a-f1", "c-f", bible.CHARACTERS, (8, 8, 372, 234))])

    command = sheetvideo.sheet_command("ffmpeg", ["face.png"], sheet, Path("out.mp4"))

    assert command[command.index("-filter_complex") + 1] == (
        "[1:v]scale=372:234:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,setsar=1,format=yuv420p[p1];"
        "[0:v][p1]overlay=x=8+(372-overlay_w)/2:y=8+(234-overlay_h)/2:eof_action=repeat:format=yuv420[b1];"
        "[b1]format=yuv420p,setsar=1[vout]"
    )
    assert command[command.index("-frames:v") + 1] == "121"
    assert ["-f", "lavfi", "-i", "color=c=black:s=768x448:r=24"] == command[9:13]


def _still(path: Path, color: str, size: str) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}", "-frames:v", "1", str(path)], check=True)
    return path


def _gray(path: Path, width: int, height: int, frame: int) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True,
        capture_output=True,
    ).stdout[: width * height]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_ffmpeg_writes_the_sheet_as_a_still_video_of_the_take_size_and_frames_and_puts_it_in_the_request(core, make_doc, tmp_path, monkeypatch, export_storage):
    core.use_ltx25()
    _media(core)
    folder = tmp_path / "pictures"
    folder.mkdir()
    files = {
        "f1": _still(folder / "f1.png", "white", "512x512"),
        "f2": _still(folder / "f2.png", "white", "300x600"),
        "q1": _still(folder / "q1.png", "white", "800x400"),
    }
    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, target: files.get(Path(value).stem))
    saved = []

    async def save(user, path):
        keep = tmp_path / "library" / Path(path).name
        keep.parent.mkdir(exist_ok=True)
        shutil.copy(path, keep)
        saved.append(keep)
        return {"value": f"uploads/{keep.name}", "media_type": "video", "original_filename": keep.name, "origin": None}

    monkeypatch.setattr(core_bridge, "save_user_media", save)
    doc = _doc(make_doc)
    plan = _plans(core, doc).shots[0]

    asyncio.run(soundtrack.attach_all(core.users["user-1"], {"id": "p-1", "doc": doc}, [plan]))

    [stored] = saved
    assert stored.name == "vp-sheet-shot-01-sheet.mp4"
    assert plan.request["form_data"]["video_director"]["ic_lora"][0]["reference"] == {
        "path": "uploads/vp-sheet-shot-01-sheet.mp4",
        "relative_path": "uploads/vp-sheet-shot-01-sheet.mp4",
        "type": "video",
    }
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,width,height,nb_read_frames,r_frame_rate", "-of", "json", str(stored)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )["streams"]
    assert [(s["codec_type"], s["width"], s["height"], int(s["nb_read_frames"]), s["r_frame_rate"]) for s in probe] == [("video", 768, 448, 121, "24/1")]
    for frame in (0, 120):
        pixels = _gray(stored, 768, 448, frame)
        at = lambda x, y: pixels[y * 768 + x]
        assert at(2, 2) < 30 and at(766, 446) < 30
        assert at(8 + 186, 8 + 117) > 220 and at(388 + 186, 8 + 117) > 220 and at(384, 250 + 95) > 220
        assert at(388 + 5, 8 + 117) < 30
