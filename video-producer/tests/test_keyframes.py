import asyncio
from types import SimpleNamespace

import pytest

from backend import core_bridge, generation, keyframes, projects, takes, tracker
from src.plugin_api import FieldDescription, ModeDescription, PresetDescription, get_current_active_user
from src.plugin_api.cloud import CLOUD_ENGINE

BASE = "/api/plugins/video-producer"
QWEN = "01M31Y6WNM07EHAXXCDV1QVJVX"
FLUX3 = "01M506YWDFE0W3R42YPDXWRZYW"
QWEN_EDIT = "01K0W24A3RADXXABH16YQ7KF00"
GEMINI = "01M48T0Q8PFET5JD9Z2FDP8E11"
SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Arrival"}


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _plain(type, default=None, options=(), required=False):
    return {
        "type": type,
        "required": required,
        "default": default,
        "options": [{"value": value, "label": value} for value in options],
        "recommendations": [],
    }


def _model(name):
    return {"type": "model", "required": True, "default": None, "options": [], "recommendations": [{"sha256": f"{name}-sha", "filename": None}]}


def _pictures(name="source_image", max_items=10):
    return {**_plain("image", required=True), "multi": True, "max_items": max_items}


def qwen_fields(max_items=10):
    return {
        "speed_profile": _plain("select", "balanced", ("balanced", "turbo", "custom")),
        "seed": _plain("seed", -1),
        "quantity": _plain("stepper", 1),
        "diffusion_model": _model("qwen21_dit"),
        "text_encoder": _model("qwen3vl_8b"),
        "vae": _model("qwen21_vae"),
        "source_image": _pictures(max_items=max_items),
    }


def flux3_fields():
    fields = qwen_fields()
    fields["output_size"] = _plain("select", "match", ("match", "1024x1024", "1152x896", "896x1152", "1344x768", "768x1344"))
    return fields


def gemini_fields():
    return {
        "seed": _plain("seed", -1),
        "count": _plain("stepper", 1),
        "aspect_ratio": _plain("select"),
        "resolution": _plain("select"),
        "model": {**_model("model"), "recommendations": []},
        "references": _pictures("references"),
    }


def add_edit_preset(core, preset_id, name, fields, engine="native"):
    described = ModeDescription(
        default_form="custom",
        forms={
            "custom": {
                key: FieldDescription(type=spec["type"], required=spec["required"], multi=bool(spec.get("multi")))
                for key, spec in fields.items()
            }
        },
    )
    core.descriptions[preset_id] = PresetDescription(
        id=preset_id,
        name=name,
        vars={},
        modes={"txt2img": ModeDescription(default_form="custom", forms={"custom": {}}), "edit": described},
        engine=engine,
        category="image",
        requires={"recommended_vram_gb": 24},
    )
    core.fields[(preset_id, "edit")] = fields
    return core.descriptions[preset_id]


def nano_banana(model_id="cm-nano", max_images=14):
    return {
        "id": model_id,
        "name": "Nano Banana 2.1",
        "provider_model_id": "gemini-nano-banana-2.1",
        "params": [
            {"name": "aspect_ratio", "kind": "enum", "values": ["1:1", "16:9", "9:16"], "minimum": None, "maximum": None, "step": None, "default": "1:1", "tasks": []},
            {"name": "resolution", "kind": "enum", "values": ["1K", "2K"], "minimum": None, "maximum": None, "step": None, "default": "1K", "tasks": []},
        ],
        "max_images": max_images,
    }


@pytest.fixture
def cloud(core, monkeypatch):
    backends = [{"id": "b-google", "engine": CLOUD_ENGINE, "driver": "cloud.google"}]
    models = {"b-google": [nano_banana()]}
    monkeypatch.setattr(core_bridge, "enabled_backends", lambda: list(backends))
    monkeypatch.setattr(core_bridge, "cloud_edit_models", lambda backend_id: list(models.get(backend_id, [])))
    monkeypatch.setattr(core_bridge, "preset_driver", lambda preset_id: "cloud.google" if preset_id == GEMINI else None)
    add_edit_preset(core, GEMINI, "Gemini Images", gemini_fields(), engine=CLOUD_ENGINE)
    return SimpleNamespace(backends=backends, models=models)


def _picture(core, asset_id, value, width=1344, height=768, kind="image"):
    core.add_media({"kind": "library", "item_id": f"item-{asset_id}"}, value, media_type=kind)
    return {"id": asset_id, "kind": kind, "name": asset_id.title(), "origin": {"kind": "library", "itemId": f"item-{asset_id}"}, "width": width, "height": height}


@pytest.fixture
def scene(core, make_doc):
    assets = [
        _picture(core, "lea", "uploads/lea.png", 768, 1024),
        _picture(core, "cafe", "uploads/cafe.png"),
        _picture(core, "hat", "uploads/hat.png", 512, 512),
        _picture(core, "capture", "uploads/capture.png"),
        _picture(core, "street", "uploads/street.png"),
        _picture(core, "voice", "uploads/voice.wav", kind="audio"),
    ]
    references = [
        {"id": "r-lea", "name": "Léa", "space": "identite", "type": "Personnage", "assetId": "lea"},
        {"id": "r-cafe", "name": "Café", "space": "decors3d", "type": "Capture 3D", "assetId": "cafe"},
        {"id": "r-hat", "name": "Red hat", "space": "identite", "type": "Objet", "assetId": "hat", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "r-street", "name": "Street", "space": "decors3d", "type": "Capture 3D", "assetId": "street"},
        {"id": "r-voice", "name": "Voice", "space": "son", "type": "Voix", "role": "Son", "assetId": "voice"},
        {"id": "r-other", "name": "Other shot", "space": "identite", "type": "Personnage", "assetId": "lea", "scope": {"type": "shot", "shotId": "s2"}},
    ]
    clips = [{**SHOT, "referenceOverrides": {"exclude": ["r-street"]}}, {"id": "s2", "start": 4, "dur": 4}]
    prompts = [{"id": "p1", "shotId": "s1", "start": 0, "dur": 4, "text": "Léa walks into the café and sits by the window."}]
    return make_doc(clips=clips, prompts=prompts, assets=assets, references=references, direction={"palette": "Warm amber light."})


@pytest.fixture
def qwen(core):
    return add_edit_preset(core, QWEN, "Qwen-Image-2.1", qwen_fields())


def _order(**body):
    return keyframes.parse_order({"preset_id": QWEN, **body})


def _build(core, doc, **body):
    return keyframes.build(core.users["user-1"], doc, "s1", _order(**body))


def test_the_edit_presets_are_those_that_edit_from_several_pictures(client, core, qwen, cloud):
    add_edit_preset(core, FLUX3, "FLUX 3 Klein (experimental)", flux3_fields())
    add_edit_preset(core, "01SINGLE", "One picture", {**qwen_fields(), "source_image": {**_plain("image", required=True)}})
    add_edit_preset(core, "01ONE", "Multi of one", qwen_fields(max_items=1))
    core.use_wan()

    listed = client.get(f"{BASE}/me").json()["data"]["keyframe_presets"]

    assert [(preset["id"], preset["max_images"]) for preset in listed] == [(FLUX3, 10), (QWEN, 10), (GEMINI, 10)]
    assert listed[1] == {
        "id": QWEN,
        "name": "Qwen-Image-2.1",
        "engine": "native",
        "driver": None,
        "backend_id": None,
        "requires": {"recommended_vram_gb": 24},
        "max_images": 10,
        "models": [],
    }
    assert listed[2]["backend_id"] == "b-google" and listed[2]["models"] == [{"id": "cm-nano", "name": "Nano Banana 2.1", "max_images": 10}]


def test_a_cloud_edit_preset_without_an_edit_model_turned_on_is_not_offered(core, qwen, cloud):
    cloud.models["b-google"] = []

    assert [preset.id for preset in keyframes.edit_presets(core.users["user-1"])] == [QWEN]


def test_the_edit_request_sends_the_shot_pictures_settings_first_with_its_prompt(core, qwen, scene):
    built = _build(core, scene)

    assert built.blocks == []
    assert [(picture.asset_id, picture.role) for picture in built.pictures] == [("cafe", "setting"), ("lea", "character"), ("hat", "object")]
    request = built.plan.request
    assert request["preset_id"] == QWEN and request["mode"] == "edit"
    form = request["form_data"]
    assert form["source_image"] == ["uploads/cafe.png", "uploads/lea.png", "uploads/hat.png"]
    assert form["quantity"] == 1 and form["seed"] == -1
    assert {form[name] for name in ("diffusion_model", "text_encoder", "vae")} == {"model:id-qwen21_dit-sha", "model:id-qwen3vl_8b-sha", "model:id-qwen21_vae-sha"}
    assert request["prompts"][0]["positive"].split("\n") == [
        "The opening frame of a film shot, in a 16:9 frame.",
        "Léa walks into the café and sits by the window.",
        "Warm amber light.",
        "Image 1 shows the setting (Café): keep its place, light and colours.",
        "Keep the face, hair, body and costume of Léa from image 2.",
        "Keep the look of Red hat from image 3.",
        "One photographic still: no text, no caption, no border, no split panels.",
    ]
    assert built.plan.resolution == "1360x768" and built.warnings == []


def test_a_3d_capture_start_image_is_the_framing_and_the_end_image_starts_from_the_start_image(core, qwen, scene):
    scene["frames"] = [{"id": "f1", "shotId": "s1", "time": 0, "assetId": "capture", "role": "first", "strength": 100, "sceneId": "sc1"}]

    first = _build(core, scene)
    scene["frames"][0].pop("sceneId")
    plain = _build(core, scene)
    last = _build(core, scene, role="last")

    assert [picture.asset_id for picture in first.pictures] == ["capture", "cafe", "lea", "hat"]
    assert "Image 1 is the framing of the shot: keep its camera angle, layout, light and colours." in first.plan.prompt_text
    assert [picture.asset_id for picture in plain.pictures] == ["cafe", "lea", "hat"]
    assert [picture.role for picture in last.pictures] == ["frame", "setting", "character", "object"]
    assert last.plan.prompt_text.startswith("The closing frame of a film shot")
    assert "Image 1 is the opening frame of the same shot" in last.plan.prompt_text


def test_the_pictures_and_prompt_of_the_shot_editor_are_sent_in_their_order(core, qwen, scene):
    body = {
        "prompt": "Léa looks up, surprised.",
        "references": [
            {"asset_id": "lea", "role": "character", "name": "Léa"},
            {"asset_id": "voice", "role": "setting"},
            {"asset_id": "nowhere", "role": "setting"},
            {"asset_id": "street", "role": "setting", "name": "Street"},
        ],
    }

    built = _build(core, scene, **body)

    assert built.plan.request["form_data"]["source_image"] == ["uploads/lea.png", "uploads/street.png"]
    assert [(item["code"], item["data"]["asset_id"]) for item in built.warnings[:2]] == [
        ("reference_unavailable", "voice"),
        ("reference_unavailable", "nowhere"),
    ]
    assert "Léa looks up, surprised." in built.plan.prompt_text and "walks into" not in built.plan.prompt_text
    assert built.warnings[-1]["code"] == "aspect_mismatch"
    assert "Léa walks into the café" in _build(core, scene, prompt="  ").plan.prompt_text


def test_the_pictures_past_the_limit_of_the_model_are_left_out(core, scene):
    add_edit_preset(core, QWEN_EDIT, "Qwen-Image", qwen_fields(max_items=3))
    scene["references"].append({"id": "r-style", "name": "Look", "space": "identite", "type": "Style", "assetId": "street"})

    built = keyframes.build(core.users["user-1"], scene, "s1", keyframes.parse_order({"preset_id": QWEN_EDIT}))

    assert [picture.asset_id for picture in built.pictures] == ["cafe", "lea", "hat"]
    assert built.warnings[0]["code"] == "references_trimmed" and built.warnings[0]["data"] == {"sent": 3, "found": 4}


def test_flux3_gets_the_output_size_closest_to_the_project_frame(core, scene):
    add_edit_preset(core, FLUX3, "FLUX 3 Klein (experimental)", flux3_fields())

    built = keyframes.build(core.users["user-1"], scene, "s1", keyframes.parse_order({"preset_id": FLUX3}))

    assert built.plan.request["form_data"]["output_size"] == "1344x768" and built.plan.resolution == "1344x768"


def test_a_square_first_picture_warns_that_the_image_will_be_square(core, qwen, scene):
    built = _build(core, scene, references=[{"asset_id": "hat", "role": "object", "name": "Red hat"}])

    assert built.plan.resolution == "1024x1024"
    assert built.warnings == [
        {
            "code": "aspect_mismatch",
            "message": "The image takes the aspect ratio of the first picture, not the project's.",
            "data": {"aspect": "16:9", "size": "1024x1024"},
        }
    ]


def test_a_cloud_edit_model_gets_the_references_and_the_project_aspect(core, cloud, scene):
    built = keyframes.build(core.users["user-1"], scene, "s1", keyframes.parse_order({"preset_id": GEMINI, "model_id": "cm-nano"}))

    form = built.plan.request["form_data"]
    assert form["model"] == "model:cm-nano" and form["references"] == ["uploads/cafe.png", "uploads/lea.png", "uploads/hat.png"]
    assert (form["aspect_ratio"], form["resolution"], form["count"]) == ("16:9", "1K", 1)
    assert built.plan.cloud and built.plan.cloud_task == "img_edit" and built.plan.cloud_params == {"aspect_ratio": "16:9", "resolution": "1K"}


def test_a_cloud_preset_needs_one_of_its_edit_models(core, cloud, scene):
    built = keyframes.build(core.users["user-1"], scene, "s1", keyframes.parse_order({"preset_id": GEMINI, "model_id": "cm-veo"}))

    assert [block["code"] for block in built.blocks] == ["no_model"]


@pytest.mark.parametrize(
    "state, expected",
    [
        (core_bridge.PresetState("x", "x", loaded=False, installed=False, assigned=False), "not_loaded"),
        (core_bridge.PresetState("x", "x", loaded=True, installed=False, assigned=False), "not_installed"),
        (core_bridge.PresetState("x", "x", loaded=True, installed=True, assigned=True), "not_assigned"),
    ],
)
def test_a_missing_edit_preset_says_why(client, core, scene, monkeypatch, state, expected):
    monkeypatch.setattr(core_bridge, "preset_state", lambda preset_id: state)
    project = projects.create_project("user-1", scene)

    estimate = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate", json={"preset_id": QWEN})
    started = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes", json={"preset_id": QWEN})

    block = estimate.json()["data"]["blocks"][0]
    assert block["code"] == "preset_missing" and block["data"] == {"preset_id": QWEN, "state": expected}
    assert started.status_code == 409 and started.json()["detail"]["data"]["blocks"][0]["code"] == "preset_missing"
    assert core.submitted == []


def test_a_preset_the_user_runs_without_a_multi_picture_edit_mode_is_not_an_edit_preset(core, scene, monkeypatch):
    monkeypatch.setattr(core_bridge, "preset_state", lambda preset_id: core_bridge.PresetState(preset_id, "Wan", True, True, True))
    core.use_wan()

    built = keyframes.build(core.users["user-1"], scene, "s1", keyframes.parse_order({"preset_id": "01KX47WANVIDEO0000000000TV"}))

    assert built.blocks[0]["data"]["state"] == "not_edit"


def test_missing_models_and_pictures_block_the_candidates(core, qwen, make_doc):
    core.missing.add("qwen3vl_8b-sha")
    bare = make_doc(clips=[SHOT])

    built = _build(core, bare)

    assert [block["code"] for block in built.blocks] == ["no_references"]
    assert built.plan is None


def test_the_estimate_reports_memory_time_quota_and_the_pictures_sent(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)

    data = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate", json={"preset_id": QWEN, "count": 3}).json()["data"]

    assert set(data) == {"shot_id", "role", "count", "preset", "model_id", "resolution", "prompt", "references", "vram", "time", "quota", "cost", "blocks", "warnings"}
    assert data["preset"] == {"id": QWEN, "name": "Qwen-Image-2.1", "cloud": False}
    assert [(item["rank"], item["asset_id"], item["role"]) for item in data["references"]] == [(1, "cafe", "setting"), (2, "lea", "character"), (3, "hat", "object")]
    assert data["vram"]["estimate_gb"] == 18.5 and data["vram"]["backend_id"] == "b-local"
    assert data["time"] == {"seconds": None, "per_candidate": None, "samples": 0}
    assert data["quota"]["needed_minutes"] == 3.0 and data["quota"]["applies"] is True
    assert [warning["code"] for warning in data["warnings"]] == ["time_unknown"] and data["blocks"] == [] and data["cost"] is None
    assert core.previewed[0][1]["mode"] == "edit"


def test_the_estimate_blocks_candidates_past_the_quota_and_missing_models(client, core, qwen, scene):
    core.quota = {"limit": 10, "used": 9.5, "remaining": 0.5, "exempt": False, "resets_at": None}
    core.missing.add("qwen21_vae-sha")
    project = projects.create_project("user-1", scene)

    data = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate", json={"preset_id": QWEN}).json()["data"]

    assert [block["code"] for block in data["blocks"]] == ["missing_models", "quota_exceeded"]
    assert data["vram"]["unknown"] is True and core.previewed == []


def test_an_admin_sees_what_cloud_candidates_cost(app, client, core, cloud, scene):
    project = projects.create_project("user-1", scene)
    body = {"preset_id": GEMINI, "model_id": "cm-nano", "count": 2}
    route = f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate"

    as_user = client.post(route, json=body).json()["data"]
    _as(app, core.users["admin-1"])
    as_admin = client.post(route, json=body).json()["data"]

    assert as_user["cost"] is None and as_user["quota"]["applies"] is False
    assert as_admin["cost"] == {"total_usd": "1.20", "known": True, "message": None}
    assert core.costed == [("cm-nano", [{"task": "img_edit", "params": {"aspect_ratio": "16:9", "resolution": "1K"}}] * 2)]


def _complete_image(core, generation_id, duration_ms=90000):
    core.states[generation_id] = {
        "id": generation_id,
        "status": "completed",
        "progress": 1.0,
        "backend_id": "b-local",
        "started_at": "2026-10-24T10:00:00+00:00",
        "duration_ms": duration_ms,
    }
    core.files[generation_id] = [
        {
            "id": f"file-{generation_id}",
            "file_type": "IMAGE",
            "mime_type": "image/png",
            "file_path": f"generations/2026-10-24/{generation_id}/0.png",
            "thumbnail_medium": f"generations/2026-10-24/{generation_id}/thumb.webp",
            "width": 1360,
            "height": 768,
        }
    ]


def _generate(client, project, **body):
    response = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes", json={"preset_id": QWEN, **body})
    assert response.status_code == 202, response.json()
    return response.json()["data"]["takes"]


def test_the_candidates_are_keyframe_takes_with_seeds_in_a_row(client, core, qwen, scene):
    scene["clips"][0]["engine"] = {"seed": 41}
    project = projects.create_project("user-1", scene)

    created = _generate(client, project, count=3)

    assert [(take["kind"], take["variant"], take["seed"], take["mode"], take["label"]) for take in created] == [
        ("keyframe", "A", 41, "edit", "draft"),
        ("keyframe", "B", 42, "edit", "draft"),
        ("keyframe", "C", 43, "edit", "draft"),
    ]
    assert [request["form_data"]["seed"] for _, request in core.submitted] == [41, 42]
    assert [request["idempotency_key"] for _, request in core.submitted] == [f"vp:{created[0]['id']}", f"vp:{created[1]['id']}"]
    assert [record[2:] for record in core.recorded] == [(1.0, f"video-producer:{take['id']}") for take in created]
    assert len(core.scheduled) == 1


def test_the_candidates_stay_out_of_the_video_takes(client, core, qwen, scene):
    core.use_wan()
    project = projects.create_project("user-1", scene)
    created = _generate(client, project)

    listed = client.get(f"{BASE}/projects/{project['id']}/takes").json()["data"]["takes"]
    candidates = client.get(f"{BASE}/projects/{project['id']}/shots/s1/keyframes").json()["data"]["takes"]
    queue = client.get(f"{BASE}/projects/{project['id']}/queue").json()["data"]

    assert listed == [] and takes.list_takes(project["id"]) == []
    assert [take["id"] for take in candidates] == [take["id"] for take in created]
    assert queue["takes"] == [] and [take["id"] for take in queue["keyframes"]] == [take["id"] for take in created]
    assert queue["slots"]["in_flight"] == 2
    assert generation.next_variants(project["id"], "s1", "draft", 1) == ["A"]


def test_a_finished_candidate_keeps_its_image_and_calibrates_the_next_estimate(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)
    created = _generate(client, project)
    _complete_image(core, created[0]["generation_id"])

    asyncio.run(tracker.Tracker().tick())

    done = takes.get_take(created[0]["id"])
    assert done["status"] == "done" and done["file_path"].endswith("/0.png") and (done["width"], done["height"]) == (1360, 768)
    assert takes.public(done)["url"] == f"/api/media/generations/{done['generation_id']}/0.png"
    assert core.notified[-1]["message"] == "[lib.default.project]: the start image candidate A is ready."
    estimate = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate", json={"preset_id": QWEN}).json()["data"]
    assert estimate["time"] == {"seconds": 180.0, "per_candidate": 90.0, "samples": 1}
    assert estimate["quota"]["needed_minutes"] == 3.0


def test_a_candidate_whose_generation_made_no_image_fails(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)
    created = _generate(client, project)
    core.complete(created[0]["generation_id"])
    core.files[created[0]["generation_id"]] = [item for item in core.files[created[0]["generation_id"]] if item["file_type"] == "VIDEO"]

    asyncio.run(tracker.Tracker().tick())

    failed = takes.get_take(created[0]["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "no_output", "The generation finished without an image.")


def test_a_candidate_is_labelled_kept_or_rejected_but_never_final(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)
    created = _generate(client, project)
    _complete_image(core, created[0]["generation_id"])
    asyncio.run(tracker.Tracker().tick())
    route = f"{BASE}/projects/{project['id']}/takes/{created[0]['id']}"

    kept = client.post(f"{route}/label", json={"label": "candidate"})
    final = client.post(f"{route}/label", json={"label": "final"})
    chosen = client.post(f"{route}/choose", json={"chosen": True})
    made = client.post(f"{route}/final", json={"method": "upscale", "target": "fhd1080"})

    assert kept.status_code == 200 and kept.json()["data"]["take"]["label"] == "candidate"
    assert [response.status_code for response in (final, chosen, made)] == [409, 409, 409]
    assert {response.json()["detail"]["error"] for response in (final, chosen, made)} == {"keyframe_take"}


def test_a_failed_candidate_is_retried_with_the_same_request_and_seed(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)
    created = _generate(client, project)
    core.fail(created[0]["generation_id"])
    asyncio.run(tracker.Tracker().tick())

    response = client.post(f"{BASE}/takes/{created[0]['id']}/retry")

    assert response.status_code == 202
    retried = response.json()["data"]["take"]
    assert (retried["kind"], retried["seed"], retried["variant"]) == ("keyframe", created[0]["seed"], "A")
    first, again = core.submitted[0][1], core.submitted[-1][1]
    assert again["form_data"] == first["form_data"] and again["idempotency_key"] == f"vp:{retried['id']}"


def test_the_candidate_letters_follow_the_ones_already_used(client, core, qwen, scene):
    project = projects.create_project("user-1", scene)
    _generate(client, project)

    again = _generate(client, project)

    assert [take["variant"] for take in again] == ["C", "D"]


@pytest.mark.parametrize(
    "body, message",
    [
        ({"preset_id": QWEN, "count": 5}, "count must be an integer from 2 to 4."),
        ({"preset_id": QWEN, "count": 1}, "count must be an integer from 2 to 4."),
        ({"preset_id": QWEN, "role": "middle"}, "role must be one of: first, last."),
        ({"preset_id": ""}, "preset_id must be a preset id."),
        ({"preset_id": QWEN, "references": [{"role": "setting"}]}, "Each reference needs an asset_id."),
        ({"preset_id": QWEN, "references": [{"asset_id": "a", "role": "hero"}]}, "A reference role must be one of: frame, setting, character, object, style."),
    ],
)
def test_a_malformed_body_answers_422(client, core, qwen, scene, body, message):
    project = projects.create_project("user-1", scene)

    response = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes/estimate", json=body)

    assert response.status_code == 422 and response.json()["detail"]["message"] == message


def test_an_unknown_shot_or_another_users_project_is_not_found(app, client, core, qwen, scene):
    project = projects.create_project("user-1", scene)

    unknown = client.post(f"{BASE}/projects/{project['id']}/shots/nope/keyframes", json={"preset_id": QWEN})
    _as(app, core.users["user-2"])
    other = client.post(f"{BASE}/projects/{project['id']}/shots/s1/keyframes", json={"preset_id": QWEN})

    assert (unknown.status_code, unknown.json()["detail"]["error"]) == (404, "shot_not_found")
    assert (other.status_code, other.json()["detail"]["error"]) == (404, "project_not_found")
    assert core.submitted == []


def test_the_project_remembers_the_edit_preset_and_model_of_its_start_images(make_doc):
    doc = make_doc(clips=[SHOT])
    doc["engine"]["keyframes"] = {"preset": GEMINI, "model": "cm-nano"}

    assert '"keyframes":{"model":"cm-nano","preset":"01M48T0Q8PFET5JD9Z2FDP8E11"}' in projects.validate_doc(doc).replace(" ", "")
    doc["engine"]["keyframes"] = {"preset": GEMINI, "steps": 4}
    with pytest.raises(projects.DocError):
        projects.validate_doc(doc)


def _bridge(monkeypatch, **parts):
    container = SimpleNamespace(**parts)
    monkeypatch.setattr(core_bridge, "api_hooks", SimpleNamespace(get_container=lambda: container))


def test_the_bridge_lists_the_cloud_models_that_edit_from_references_with_their_limit(monkeypatch):
    def entry(model_id, tasks, inputs):
        spec = SimpleNamespace(params=(), inputs=inputs)
        return SimpleNamespace(model_id=model_id, label=model_id.title(), provider_model_id=f"google/{model_id}", tasks=list(tasks), spec=spec)

    reference = SimpleNamespace(role="reference", tasks=frozenset({"img_edit"}), max_items=14)
    frame = SimpleNamespace(role="first_frame", tasks=frozenset({"img2video"}), max_items=1)
    entries = [entry("nano", ("txt2img", "img_edit"), (reference,)), entry("veo", ("img2video",), (frame,)), entry("bare", ("img_edit",), ())]
    _bridge(monkeypatch, cloud_catalog=SimpleNamespace(repository=SimpleNamespace(list_enabled=lambda backend_id: entries)))

    assert core_bridge.cloud_edit_models("b-google") == [
        {"id": "nano", "name": "Nano", "provider_model_id": "google/nano", "params": [], "max_images": 14},
        {"id": "bare", "name": "Bare", "provider_model_id": "google/bare", "params": [], "max_images": 0},
    ]


def test_the_bridge_gives_a_multiple_field_its_most_items(monkeypatch, tmp_path):
    def form_field(name, type, configuration=None):
        return SimpleNamespace(name=name, type=type, required=True, default=None, configuration=configuration, children=None)

    form = SimpleNamespace(name="custom", default=True, order=0, fields=[form_field("source_image", "image", {"multi": True, "max_items": 10}), form_field("seed", "seed")])
    template = SimpleNamespace(path=str(tmp_path), modes={"edit": SimpleNamespace(forms=[form])})
    repository = SimpleNamespace(find_preset_by_id=lambda preset_id: template, preset_loader=SimpleNamespace(shared_path=tmp_path))
    _bridge(monkeypatch, file_preset_repository=repository)

    fields = core_bridge.preset_form_fields(QWEN, "edit")

    assert (fields["source_image"]["multi"], fields["source_image"]["max_items"]) == (True, 10)
    assert "multi" not in fields["seed"] and "max_items" not in fields["seed"]
