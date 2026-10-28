import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from backend import director, estimate, formats, keyframes, presets, projects, takes
from backend.exports import fcpxml, video

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PAGE_TABLE = PLUGIN_ROOT / "frontend" / "src" / "lib" / "formatstable.js"
CASES = json.loads((Path(__file__).parent / "fixtures" / "format_cases.json").read_text(encoding="utf-8"))
MIGRATION = json.loads((Path(__file__).parent / "fixtures" / "format_migration.json").read_text(encoding="utf-8"))
SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Opening"}
FFMPEG = shutil.which("ffmpeg")


def _plans(core, doc, preset_id=presets.WAN, quality="draft", **options):
    return director.build_plans(core.users["user-1"], doc, ["s1"], preset_id, quality, **options)


def _codes(warnings):
    return [item["code"] for item in warnings]


def _warning(warnings, code):
    return next(item for item in warnings if item["code"] == code)


def test_the_page_reads_an_identical_copy_of_the_table():
    text = PAGE_TABLE.read_text(encoding="utf-8").strip()
    assert text.startswith("export default ") and text.endswith(";")
    assert json.loads(text[len("export default ") : -1]) == formats.load_table()


def test_every_format_of_the_table_is_one_the_documents_keep_and_the_engines_cover_the_preset_ids():
    assert all(formats.format_value(name) == name for name in formats.FORMATS)
    assert formats.DEFAULT_FORMAT in formats.FORMATS and formats.SOCIAL_DEFAULT in formats.SOCIAL_FORMATS
    known = {preset for engine in formats.ENGINES.values() for preset in engine["presets"]}
    assert set(presets.MINIMAX_H3_PRESETS) | {presets.WAN, presets.LTX_2, presets.LTX_2_5, *presets.WAN_TIER_PRESETS} == known


@pytest.mark.parametrize("text, ratio", CASES["ratios"])
def test_a_format_reads_as_the_page_reads_it(text, ratio):
    assert formats.ratio_of(text) == ratio


@pytest.mark.parametrize("text, kept", CASES["values"])
def test_a_document_keeps_the_formats_the_page_keeps(text, kept):
    assert formats.format_value(text) == kept


@pytest.mark.parametrize("text, kept", CASES["resolutions"])
def test_a_document_keeps_the_resolutions_the_page_keeps(text, kept):
    assert formats.resolution_value(text) == kept


@pytest.mark.parametrize("name, resolution, size", CASES["delivery"])
def test_the_delivery_size_is_the_page_s(name, resolution, size):
    assert list(formats.delivery_size(formats.ratio_of(name), resolution)) == size


@pytest.mark.parametrize("case", CASES["plans"], ids=lambda case: f"{case['preset']}-{case['format']}-{case['setting']}")
def test_the_draft_and_final_sizes_are_the_page_s(case):
    options, preset_id, ratio = CASES["options"][case["options"]], CASES["presets"][case["preset"]], formats.ratio_of(case["format"])
    assert formats.draft_size(options, case["setting"], ratio, preset_id) == case["draft"]
    assert formats.final_size(options, ratio, preset_id) == case["final"]


@pytest.mark.parametrize("key, folder", [("wan13", "Wan2.1-T2V-1.3B-8GB"), ("wan5b", "Wan2.2-TI2V-5B-8GB")])
def test_the_shared_cases_carry_the_sizes_the_8_gb_presets_ship(key, folder):
    shipped = yaml.safe_load((PLUGIN_ROOT / "presets" / folder / "files" / "form" / "resolutions_480p.yml").read_text(encoding="utf-8"))

    assert CASES["options"][key] == [item["value"] for item in shipped]


@pytest.mark.parametrize("key, preset_id", [("wan13", presets.WAN21_T2V_1_3B_8GB), ("wan5b", presets.WAN22_TI2V_5B_8GB)])
def test_the_8_gb_presets_make_square_and_4_5_films_at_their_own_ratio(key, preset_id):
    options = CASES["options"][key]

    for name in ("1:1", "4:5"):
        ratio = formats.ratio_of(name)
        size = formats.parse_size(formats.final_size(options, ratio, preset_id))
        assert formats.fit(size[0] / size[1], ratio) == formats.EXACT, (key, name)
        assert formats.draft_size(options, "832x480", ratio, preset_id) == formats.final_size(options, ratio, preset_id), (key, name)


@pytest.mark.parametrize("case", CASES["picks"], ids=lambda case: f"{case['preset']}-{case['chosen']}")
def test_a_chosen_size_is_taken_or_left_out_as_the_page_does(case):
    choice = formats.pick_size(
        CASES["options"][case["options"]], formats.ratio_of(case["format"]), case["quality"], case["setting"], case["chosen"], CASES["presets"][case["preset"]]
    )
    assert (choice.size, choice.refused, choice.problem) == (case["size"], case["refused"], case["problem"])


@pytest.mark.parametrize("take, frame, framing, shown", CASES["fits"])
def test_the_film_shows_a_take_as_the_page_does(take, frame, framing, shown):
    assert formats.fit(formats.ratio_of(take), formats.ratio_of(frame), framing) == shown


@pytest.mark.parametrize("values, name, closest", CASES["closest"])
def test_the_closest_format_is_the_page_s(values, name, closest):
    assert formats.closest_format(values, formats.ratio_of(name)) == closest


@pytest.mark.parametrize("size, text", CASES["texts"])
def test_a_ratio_is_written_as_the_page_writes_it(size, text):
    assert formats.ratio_text(formats.ratio_of(size)) == text


@pytest.mark.parametrize("measured, wanted, scale", CASES["scales"])
def test_the_time_scale_is_the_page_s(measured, wanted, scale):
    assert round(formats.time_scale(measured, wanted), 9) == scale


@pytest.mark.parametrize("measured, wanted, nearest", CASES["nearest"])
def test_the_nearest_measured_size_is_the_page_s(measured, wanted, nearest):
    assert formats.nearest_measured(measured, wanted) == nearest


@pytest.mark.parametrize("value, kept", CASES["sizes"])
def test_the_chosen_sizes_keep_what_the_page_keeps(value, kept):
    assert formats.sizes_value(value) == kept


@pytest.mark.parametrize("case", MIGRATION["cases"], ids=[case["name"] for case in MIGRATION["cases"]])
def test_the_server_migrates_the_format_as_the_page_does(case):
    doc = copy.deepcopy(case["doc"])
    before = copy.deepcopy(doc)

    migrated = projects.migrate(doc)

    assert {key: migrated[key] for key in ("aspect", "resolution", "framing", "engine") if key in migrated} == case["expected"]
    assert doc == before


def test_a_migrated_document_with_the_new_keys_passes_the_schema(make_doc):
    doc = make_doc(aspect="2.39:1")
    doc.update(resolution="1440p", framing="bars")
    doc["engine"]["sizes"] = {presets.WAN: {"draft": "992x416", "final": "1488x624"}}

    projects.validate_doc(projects.migrate(doc))
    assert projects.migrate(doc) is doc
    with pytest.raises(projects.DocError):
        projects.validate_doc({**doc, "framing": "stretch"})
    with pytest.raises(projects.DocError):
        projects.validate_doc({**doc, "engine": {**doc["engine"], "sizes": {presets.WAN: {"draft": "big"}}}})


def test_a_scope_film_on_wan_drafts_at_832x480_and_warns_that_the_film_crops_the_takes(core, make_doc):
    core.use_wan()

    plans = _plans(core, make_doc(clips=[SHOT], aspect="2.39:1"))

    assert plans.shots[0].resolution == "832x480"
    assert _warning(plans.warnings, "aspect_cropped")["data"] == {"preset_id": presets.WAN, "size": "832x480", "made": "16:9", "aspect": "2.39:1", "loss": 27}


def test_the_framing_of_the_project_turns_the_crop_into_bars_and_a_16_9_film_has_no_framing_warning(core, make_doc):
    core.use_wan()
    scope = make_doc(clips=[SHOT], aspect="2.39:1")
    scope["framing"] = "bars"

    assert "aspect_bars" in _codes(_plans(core, scope).warnings)
    assert not {"aspect_bars", "aspect_cropped"} & set(_codes(_plans(core, make_doc(clips=[SHOT])).warnings))
    assert not {"aspect_bars", "aspect_cropped"} & set(_codes(_plans(core, make_doc(clips=[SHOT], aspect="9:16")).warnings))


def test_the_size_the_project_chose_for_a_preset_goes_into_the_request(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[SHOT], aspect="2.39:1")
    doc["engine"]["sizes"] = {presets.WAN: {"final": "1488x624"}}

    final = _plans(core, doc, quality="final")
    draft = _plans(core, doc)

    assert final.shots[0].resolution == "1488x624"
    assert final.shots[0].request["form_data"]["resolution"] == "1488x624"
    assert final.shots[0].request["form_data"]["video_director"]["settings"]["resolution"] == "1488x624"
    assert not {"aspect_bars", "aspect_cropped"} & set(_codes(final.warnings))
    assert draft.shots[0].resolution == "832x480"


def test_a_size_the_engine_would_refuse_is_left_out_with_a_warning(core, make_doc):
    core.use_h3()
    doc = make_doc(clips=[SHOT])
    doc["engine"]["sizes"] = {presets.MINIMAX_H3: {"final": "1920x1080"}}

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3, quality="final")

    assert plans.shots[0].resolution == "1344x768"
    assert _warning(plans.warnings, "engine_size_invalid")["data"] == {"preset_id": presets.MINIMAX_H3, "quality": "final", "size": "1920x1080", "reason": "area"}


def test_ltx_is_sent_a_size_on_its_grid_and_the_take_records_it(core, make_doc):
    core.use_ltx25()

    plan = _plans(core, make_doc(clips=[SHOT]), preset_id=presets.LTX_2_5, quality="final").shots[0]

    assert plan.resolution == "1280x704"
    assert plan.request["form_data"]["resolution"] == "1280x704"


@pytest.mark.parametrize("aspect, made, code", [("1:1", "16:9", "aspect_bars"), ("4:5", "9:16", "aspect_cropped"), ("9:16", "9:16", None)])
def test_a_cloud_model_takes_its_closest_format_and_says_so(core, make_doc, aspect, made, code):
    core.use_openrouter()

    plans = _plans(core, make_doc(clips=[{"id": "s1", "start": 0, "dur": 5}], aspect=aspect), preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert plans.shots[0].request["form_data"]["aspect_ratio"] == made
    assert plans.shots[0].cloud_params["aspect_ratio"] == made
    if code is None:
        assert not {"aspect_unsupported", "aspect_bars", "aspect_cropped"} & set(_codes(plans.warnings))
    else:
        assert _warning(plans.warnings, "aspect_unsupported")["data"] == {"preset_id": presets.OPENROUTER_VIDEO, "model_id": "cm-veo", "made": made, "aspect": aspect}
        assert code in _codes(plans.warnings)


def test_the_working_ratio_of_a_shot_follows_its_engine(core, make_doc):
    core.use_wan()
    core.use_openrouter()
    user = core.users["user-1"]
    scope = make_doc(clips=[SHOT], aspect="2.39:1")
    scope["engine"]["preset"] = presets.WAN
    square = make_doc(clips=[SHOT], aspect="1:1")
    square["engine"].update(preset=presets.OPENROUTER_VIDEO, model="cm-veo")

    assert director.working_ratio(user, scope, "s1") == pytest.approx(1280 / 720)
    assert director.working_ratio(user, square, "s1") == pytest.approx(16 / 9)
    assert director.working_ratio(user, make_doc(clips=[SHOT], aspect="4:5"), "s1") == pytest.approx(0.8)


def test_a_start_image_is_asked_in_the_ratio_of_the_takes_with_the_part_the_film_keeps(make_doc):
    doc = make_doc(clips=[SHOT], aspect="2.39:1")
    french = make_doc(clips=[SHOT], aspect="2.39:1", language="fr")

    prompt = keyframes.keyframe_prompt(doc, doc["clips"][0], [], keyframes.FIRST, "A harbour at dawn.", 16 / 9)
    plain = keyframes.keyframe_prompt(make_doc(clips=[SHOT]), doc["clips"][0], [], keyframes.FIRST, "A harbour at dawn.", 1.7333)

    assert prompt.splitlines()[:2] == [
        "The opening frame of a film shot, in a 16:9 frame.",
        "The film keeps only its central 2.39:1 part: keep the action there.",
    ]
    assert plain.splitlines()[0] == "The opening frame of a film shot, in a 16:9 frame."
    assert "central" not in plain
    assert keyframes.keyframe_prompt(french, doc["clips"][0], [], keyframes.FIRST, "x", 16 / 9).splitlines()[1] == (
        "Le film n'en garde que la partie centrale au format 2.39:1 : y garder l'action."
    )


def test_a_size_never_measured_takes_the_time_of_the_closest_one_scaled_by_area(project_db):
    for seconds, duration_ms in ((5.0, 50000), (4.0, 40000)):
        takes.add_calibration(presets.WAN, "b-local", "832x480", seconds, duration_ms)
    takes.add_calibration(presets.WAN, "b-local", "1344x768", 5.0, 200000)

    found = estimate.calibration(presets.WAN, "b-local", "960x544")
    exact = estimate.calibration(presets.WAN, "b-local", "832x480")

    assert (exact.ratio, exact.samples, exact.measured) == (10.0, 2, None)
    assert found.measured == "832x480" and found.samples == 2
    assert found.ratio == pytest.approx(10.0 * formats.time_scale("832x480", "960x544"))
    assert estimate.calibration(presets.WAN, "b-other", "960x544").ratio is None
    assert estimate.calibration(presets.WAN, "b-local", "720p").ratio is None


def test_the_estimate_warns_when_the_time_of_a_size_is_reckoned_from_another(core, make_doc, store):
    core.use_wan()
    store[("draft_resolution", None)] = "960x544"
    takes.add_calibration(presets.WAN, "b-local", "832x480", 5.0, 50000)
    order = estimate.parse_order({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.WAN})

    import asyncio

    payload = asyncio.run(estimate.evaluate(core.users["user-1"], core.users["user-1"], make_doc(clips=[SHOT]), order)).payload

    assert payload["time"]["seconds"] == pytest.approx(round(10.0 * formats.time_scale("832x480", "960x544") * 4, 1))
    assert _warning(payload["warnings"], "size_unmeasured")["data"] == {"preset_id": presets.WAN, "size": "960x544", "measured": "832x480"}
    assert "time_unknown" not in _codes(payload["warnings"])


@pytest.mark.parametrize(
    "aspect, fmt, resolution, ratio, size",
    [
        ("2.39:1", "web", "1080p", None, (1920, 804)),
        ("2.39:1", "master", "4K", None, (3840, 1606)),
        ("1.85:1", "web", "1440p", None, (2560, 1384)),
        ("4:3", "archive", "1080p", None, (1440, 1080)),
        ("16:9", "social", "1080p", None, (1080, 1920)),
        ("16:9", "social", "1080p", "4:5", (1080, 1350)),
        ("2.39:1", "social", "720p", "1:1", (720, 720)),
        ("9:16", "web", "1440p", None, (1440, 2560)),
        ("12:1", "web", "1080p", None, (1920, 1080)),
    ],
)
def test_the_export_frame_fits_the_16_9_box_of_its_resolution(make_doc, aspect, fmt, resolution, ratio, size):
    assert video.frame_size(make_doc(aspect=aspect), fmt, resolution, ratio) == size


def test_a_social_video_of_another_ratio_names_it_and_the_others_do_not():
    assert video.file_name("Aube", "1080p", "social", ratio="4:5") == "Aube_1080p_4x5.mp4"
    assert video.file_name("Aube", "1080p", "social", ratio="9:16") == "Aube_1080p.mp4"
    assert video.file_name("Aube", "1080p", "web", ratio="4:5") == "Aube_1080p.mp4"
    assert video.file_name("Aube", "1440p", "social", stems=True, ratio="1:1") == "Aube_1440p_1x1_social_stems.zip"
    assert video.download_name("Aube", "1080p", "social", False, "1:1") == "Aube_1080p_1x1"


@pytest.mark.parametrize("fmt, ratio", [("web", "4:5"), ("social", "4:3"), ("social", 1), ("master", "9:16")])
def test_a_ratio_is_only_for_a_social_video_of_the_table(make_user, fmt, ratio):
    from fastapi import HTTPException

    from backend import routes_exports

    with pytest.raises(HTTPException) as refused:
        routes_exports.queue_video(make_user(), "p-1", fmt, None, False, ratio)

    assert refused.value.status_code == 422


def test_a_job_keeps_the_ratio_of_its_social_video(project_db):
    from backend.exports import jobs

    social = jobs.create_job("p-1", "user-1", "social", "1440p", False, "4:5")
    web = jobs.create_job("p-2", "user-1", "web", "1080p")

    assert (jobs.public(social)["ratio"], jobs.public(social)["resolution"]) == ("4:5", "1440p")
    assert jobs.public(web)["ratio"] is None


def test_the_fit_filter_crops_always_for_social_and_follows_the_framing_otherwise(make_doc):
    doc = make_doc(aspect="2.39:1")
    bars = {**doc, "framing": "bars"}
    crop = {**doc, "framing": "crop"}

    assert video.fit_share(doc, "social") == 0.0
    assert video.fit_share(doc, "web") == pytest.approx(0.7)
    assert video.fit_share(bars, "master") == pytest.approx(0.97)
    assert video.fit_share(crop, "archive") == 0.0
    assert video.fit_filter(1080, 1920, 0) == "scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2:flags=lanczos,crop=1080:1920"
    assert video.fit_filter(1920, 804, 0.7) == (
        "scale=w='if(gte(min(a,2.38806)/max(a,2.38806),0.7),ceil(max(1920,804*a)/2)*2,trunc(min(1920,804*a)/2)*2)'"
        ":h='if(gte(min(a,2.38806)/max(a,2.38806),0.7),ceil(max(804,1920/a)/2)*2,trunc(min(804,1920/a)/2)*2)':flags=lanczos,"
        "crop=w='min(iw,1920)':h='min(ih,804)',pad=1920:804:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def _fitted(tmp_path, source, width, height, keep):
    picture = tmp_path / f"{source}-{width}x{height}-{keep}.png"
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=white:s={source}:d=1", "-vf", f"{video.fit_filter(width, height, keep)},format=gray", "-frames:v", "1", str(picture)],
        check=True,
    )
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(picture), "-f", "rawvideo", "-pix_fmt", "gray", "-"], check=True, capture_output=True).stdout
    assert len(raw) == width * height
    return raw


def _dark(line):
    return sum(1 for value in line if value < 128)


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
@pytest.mark.parametrize(
    "source, width, height, keep, across, down",
    [
        ("1280x720", 1920, 804, 0.7, 0, 0),
        ("1280x720", 1920, 804, 0.97, 492, 0),
        ("1280x720", 1080, 1080, 0.7, 0, 474),
        ("1280x704", 1920, 1080, 0.97, 0, 0),
        ("640x480", 1080, 1080, 0.7, 0, 0),
        ("480x832", 1080, 1350, 0.7, 0, 0),
        ("1280x720", 1080, 1350, 0, 0, 0),
        ("832x480", 2560, 1072, 0.7, 0, 0),
    ],
)
def test_ffmpeg_fits_a_picture_to_the_frame_by_cropping_or_with_bars(tmp_path, source, width, height, keep, across, down):
    raw = _fitted(tmp_path, source, width, height, keep)
    middle = height // 2

    assert abs(_dark(raw[middle * width : (middle + 1) * width]) - across) <= 4
    assert abs(_dark(raw[width // 2 :: width]) - down) <= 4


@pytest.mark.skipif(FFMPEG is None or shutil.which("ffprobe") is None, reason="ffmpeg and ffprobe are not installed")
@pytest.mark.parametrize(
    "aspect, fmt, resolution, ratio, size, name",
    [
        ("2.39:1", "web", "1080p", None, (1920, 804), "Aube_1080p.mp4"),
        ("16:9", "social", "1440p", "4:5", (1440, 1800), "Aube_1440p_4x5.mp4"),
        ("9:16", "master", "1440p", None, (1440, 2560), "Aube_1440p.mov"),
        ("4:3", "archive", "720p", None, (960, 720), "Aube_720p_archive.mp4"),
    ],
)
async def test_a_real_export_delivers_the_frame_of_its_format(make_doc, make_user, export_storage, monkeypatch, tmp_path, aspect, fmt, resolution, ratio, size, name):
    shot = tmp_path / "shot.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(shot)], check=True, timeout=60)
    doc = make_doc(clips=[{"id": "c1", "start": 0, "dur": 1}], aspect=aspect)
    doc["resolution"] = resolution
    monkeypatch.setattr(video.media, "local_inputs", lambda doc, found, resolver, folder: ({"c1": {"name": shot.name, "path": str(shot), "still": False}}, {}))
    monkeypatch.setattr(takes, "list_takes", lambda project_id: [])

    async def stored(user, path):
        return {"value": f"uploads/{path.name}"}

    monkeypatch.setattr(video.core_bridge, "save_user_media", stored)
    monkeypatch.setattr(video.core_bridge, "upload_item", lambda user_id, value: {"item_id": "item-1"})
    user = make_user()
    job = {"id": "job-1", "user_id": "user-1", "format": fmt, "resolution": resolution, "stems": False, "ratio": ratio}

    result = await video.render(job, {"id": "p-1", "name": "Aube", "doc": doc}, user, user, lambda progress, step: True)

    output = export_storage / "video_producer" / "exports" / "user-1" / "job-1" / result["file_name"]
    dimensions = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output)],
        check=True, capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    assert result["file_name"] == name
    assert tuple(int(side) for side in dimensions.split(",")) == size


def test_the_fcpxml_frame_is_the_delivery_frame_and_only_a_16_9_one_is_named(make_doc):
    scope = {**make_doc(aspect="2.39:1"), "resolution": "1080p"}
    wide = {**make_doc(aspect="16:9"), "resolution": "1440p"}

    assert fcpxml.frame(scope) == (1920, 804) and fcpxml.format_name(scope, "25") == ""
    assert fcpxml.frame(wide) == (2560, 1440) and fcpxml.format_name(wide, "25") == ' name="FFVideoFormat1440p25"'
    assert '<format id="r1" frameDuration="1/25s" width="1920" height="804"/>' in fcpxml.render({**scope, "fps": 25}, {})
