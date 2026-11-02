import asyncio
import copy

import pytest

from backend import director, engine_options, estimate, presets, takes, tracker
from backend.estimate import Order
from backend.projects import DocError, validate_doc

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}]
SPEED = ("balanced", "distilled", "quality", "custom")
RECIPES = {"balanced": (24, 4.0), "distilled": (8, 1.0), "quality": (30, 3.0)}


def _spec(type, default=None, options=(), limits=None, reactions=None, **details):
    return {
        "type": type,
        "required": False,
        "default": default,
        "options": [{"value": value, "label": value.title()} for value in options],
        "recommendations": [],
        "label": None,
        "group": [],
        "audience": "simple",
        "hidden": False,
        "gate": None,
        "limits": limits or {},
        "reactions": reactions or [],
        "bound": False,
        **details,
    }


def _recipe(index):
    return [
        {"when": {"field": "speed_profile", "equals": profile}, "then": {"set_value": recipe[index], "set_disabled": False}}
        for profile, recipe in RECIPES.items()
    ]


def ltx_fields():
    return {
        "speed_profile": _spec("select", "balanced", SPEED, label="Speed"),
        "seed": _spec("seed", -1),
        "resolution": _spec("resolution", "768x512", ("768x512", "1280x704")),
        "fps": _spec("slider", 25, limits={"min": 1, "max": 60, "step": 1}),
        "generate_audio": _spec("checkbox", False),
        "steps": _spec("slider", 24, limits={"min": 1, "max": 100, "step": 1}, reactions=_recipe(0), audience="advanced"),
        "cfg": _spec("slider", 4.0, limits={"min": 1.0, "max": 20.0, "step": 0.5}, reactions=_recipe(1)),
        "sampler": _spec("sampler", "euler_ancestral", ("euler_ancestral", "euler")),
        "upscale": _spec("select", "off", ("off", "1.5x", "2.0x")),
        "manual_sigmas": _spec("textbox", ""),
        "model": {
            **_spec("model", required=True),
            "recommendations": [{"sha256": "ltx25-sha", "filename": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"}],
        },
        "text_encoder": {**_spec("model", required=True), "recommendations": [{"sha256": "gemma-sha", "filename": None}]},
        "video_vae": {**_spec("model", required=True), "recommendations": [{"sha256": "vae-sha", "filename": None}]},
        "audio_vae": {**_spec("model"), "recommendations": [{"sha256": "audio-vae-sha", "filename": None}]},
        "loras": _spec("lora_picker", [], limits={"strength_min": -2.0, "strength_max": 2.0, "max_items": 2, "model_type": "lora"}),
        "i2v_only": _spec("slider", 1, hidden=True),
    }


@pytest.fixture
def ltx(core):
    core.use_ltx25()
    core.fields[(presets.LTX_2_5, "video")] = ltx_fields()
    return core


def _doc(make_doc, options=None, **engines):
    doc = make_doc(clips=SHOTS)
    if options is not None:
        doc["engine"]["options"] = options
    for clip in doc["clips"]:
        if clip["id"] in engines:
            clip["engine"] = engines[clip["id"]]
    return doc


def _plans(core, doc, preset_id=presets.LTX_2_5, overrides=True, **fields):
    return director.build_plans(core.users["user-1"], doc, ["s1", "s2"], preset_id, "draft", overrides=overrides, **fields)


def _evaluate(core, doc, preset_id=presets.LTX_2_5):
    order = Order(shots=["s1", "s2"], quality="draft", variants=1, preset_id=preset_id)
    return asyncio.run(estimate.evaluate(core.users["user-1"], core.users["user-1"], doc, order))


def _form(plan):
    return plan.request_for()["form_data"]


def _invalid(plans):
    return [warning for warning in plans.warnings if warning["code"] == "engine_option_invalid"]


def test_a_project_may_set_the_options_of_its_preset_but_not_those_the_plugin_fills():
    fields = ltx_fields()

    names = [name for name, spec in fields.items() if engine_options.editable(name, spec)]

    assert names == ["speed_profile", "seed", "generate_audio", "steps", "cfg", "sampler", "upscale", "manual_sigmas", "model", "text_encoder", "video_vae", "audio_vae", "loras"]
    assert engine_options.editable("model", fields["model"], cloud=True) is False
    assert engine_options.editable("generate_audio", {**fields["generate_audio"], "bound": True}) is False
    for name in ("resolution", "fps", "video_director", "references", "quantity", "prompt", "aspect_ratio", "reference_image_budget"):
        assert engine_options.editable(name, _spec("select", options=("a",))) is False
    assert engine_options.editable("media", _spec("image")) is False


def test_each_option_is_checked_against_the_limits_of_its_field():
    fields = ltx_fields()
    valid = engine_options.valid

    assert valid(fields["steps"], 8) and valid(fields["steps"], 100) and valid(fields["steps"], 8.0)
    assert not valid(fields["steps"], 0) and not valid(fields["steps"], 101) and not valid(fields["steps"], 8.5)
    assert not valid(fields["steps"], True) and not valid(fields["steps"], "8") and not valid(fields["steps"], float("nan"))
    assert valid(fields["cfg"], 1.5) and not valid(fields["cfg"], 0.5)
    assert valid(fields["seed"], -1) and valid(fields["seed"], 2**31 - 1)
    assert not valid(fields["seed"], 2**31) and not valid(fields["seed"], -2) and not valid(fields["seed"], 4.0)
    assert valid(fields["generate_audio"], True) and not valid(fields["generate_audio"], 1)
    assert valid(fields["speed_profile"], "distilled") and not valid(fields["speed_profile"], "turbo")
    assert valid(fields["sampler"], "euler") and not valid(fields["sampler"], "dpm")
    assert valid(_spec("sampler"), "anything") and not valid(_spec("sampler"), "")
    assert valid(fields["manual_sigmas"], "1.0, 0.5, 0.0") and not valid(fields["manual_sigmas"], "x" * 2001)
    assert not valid(_spec("textbox", limits={"max_length": 4}), "12345")
    assert valid(fields["model"], "model:01ABC") and not valid(fields["model"], "model:") and not valid(fields["model"], "dit.safetensors")
    assert valid(fields["loras"], []) and valid(fields["loras"], [{"model": "model:l1", "strength": 1.5}])
    assert not valid(fields["loras"], [{"model": "model:l1", "strength": 2.5}])
    assert not valid(fields["loras"], [{"model": "l1.safetensors", "strength": 1.0}])
    assert not valid(fields["loras"], [{"model": "model:l1", "strength": 1.0, "enabled": True}])
    assert not valid(fields["loras"], [{"model": "model:l1", "strength": 1.0}] * 3)
    assert not valid(_spec("cloud_options"), {})


def test_the_conditions_of_a_reaction_read_like_the_core_reads_them():
    matches = engine_options.matches
    values = {"speed_profile": "distilled", "cfg": 4.0, "upscale": "off", "loras": []}

    assert matches({"field": "speed_profile", "equals": "distilled"}, values)
    assert matches({"field": "speed_profile", "operator": "not_equals", "value": "balanced"}, values)
    assert matches({"field": "cfg", "greater_than": 1}, values) and not matches({"field": "cfg", "less_than": "x"}, values)
    assert matches({"field": "upscale", "in": ["off", "1.5x"]}, values) and matches({"field": "loras", "is_empty": True}, values)
    assert matches({"logic": "OR", "conditions": [{"field": "cfg", "less_than": 1}, {"field": "upscale", "equals": "off"}]}, values)
    assert not matches({"logic": "AND", "conditions": [{"field": "cfg", "less_than": 1}, {"field": "upscale", "equals": "off"}]}, values)
    assert matches([{"field": "cfg", "equals": 4}, {"field": "upscale", "not_in": ["2.0x"]}], values)
    assert not matches({"field": "cfg", "equals": True}, {"cfg": 1})
    assert not matches({"field": "cfg", "unknown": 1}, values) and not matches("cfg > 1", values)


def test_the_steps_follow_the_speed_profile_unless_set_and_scale_the_work():
    fields = ltx_fields()

    assert engine_options.steps(fields, {}) == 24
    assert engine_options.steps(fields, {"speed_profile": "distilled"}) == 8
    assert engine_options.steps(fields, {"speed_profile": "distilled", "steps": 12}) == 12
    assert engine_options.resolved(fields, {"speed_profile": "quality"})["cfg"] == 3.0
    assert engine_options.work_scale(fields, {"speed_profile": "distilled"}) == pytest.approx(8 / 24)
    assert engine_options.work_scale(fields, {"steps": 48, "seed": 5, "video_director": {}}) == 2.0
    assert engine_options.work_scale({"cfg": fields["cfg"]}, {"cfg": 2.0}) == 1.0


def test_the_options_of_the_preset_go_into_the_request_of_each_shot(ltx, make_doc):
    options = {presets.LTX_2_5: {"speed_profile": "distilled", "cfg": 1.5, "upscale": "2.0x", "loras": [{"model": "model:l1", "strength": 0.8}]}}

    plans = _plans(ltx, _doc(make_doc, options))

    for plan in plans.shots:
        form = _form(plan)
        assert (form["speed_profile"], form["cfg"], form["upscale"]) == ("distilled", 1.5, "2.0x")
        assert form["loras"] == [{"model": "model:l1", "strength": 0.8}]
        assert form["model"] == "model:id-ltx25-sha"
        assert "steps" not in form
        assert plan.work_scale == pytest.approx(8 / 24)
    assert _invalid(plans) == []


def test_the_options_of_another_preset_and_the_fields_the_plugin_fills_are_left_alone(ltx, make_doc):
    ltx.use_wan()
    options = {
        presets.WAN: {"speed_profile": "fast"},
        presets.LTX_2_5: {"resolution": "1280x704", "fps": 60, "video_director": {"x": 1}, "unknown": 3, "i2v_only": 2},
    }

    (plan, _) = _plans(ltx, _doc(make_doc, options)).shots
    (plain, _) = _plans(ltx, _doc(make_doc)).shots
    form = _form(plan)

    assert form["resolution"] == plan.resolution == plain.resolution != "768x512"
    assert form["fps"] == 25 and form["video_director"]["settings"]["fps"] == 25
    assert "speed_profile" not in form and "unknown" not in form and "i2v_only" not in form
    assert plan.work_scale == 1.0


def test_an_option_that_no_longer_fits_its_field_is_left_out_with_a_warning(ltx, make_doc):
    options = {presets.LTX_2_5: {"steps": 500, "sampler": "dpm", "cfg": 2.0}}

    plans = _plans(ltx, _doc(make_doc, options))

    form = _form(plans.shots[0])
    assert "steps" not in form and "sampler" not in form and form["cfg"] == 2.0
    assert _invalid(plans) == [
        {
            "code": "engine_option_invalid",
            "message": "Some options of LTX-2.5 no longer fit their field and are left out: steps, sampler.",
            "data": {"preset_id": presets.LTX_2_5, "fields": ["steps", "sampler"]},
        }
    ]


def test_a_model_the_project_picks_stands_in_for_a_missing_recommended_file(ltx, make_doc):
    ltx.missing.add("gemma-sha")

    blocked = _plans(ltx, _doc(make_doc))
    picked = _plans(ltx, _doc(make_doc, {presets.LTX_2_5: {"text_encoder": "model:my-gemma"}}))

    assert [block["code"] for block in blocked.blocks] == ["missing_models"]
    assert picked.blocks == []
    assert _form(picked.shots[0])["text_encoder"] == "model:my-gemma"


def test_the_shot_settings_come_before_the_project_options(ltx, make_doc):
    ltx.use_wan()
    options = {presets.LTX_2_5: {"seed": 7, "steps": 12}, presets.WAN: {"speed_profile": "fast", "seed": 11}}
    doc = _doc(make_doc, options, s2={"preset": presets.WAN, "seed": 99})

    s1, s2 = _plans(ltx, doc).shots

    assert (s1.preset_id, s1.seed, _form(s1)["steps"]) == (presets.LTX_2_5, 7, 12)
    assert (s2.preset_id, s2.seed, _form(s2)["speed_profile"]) == (presets.WAN, 99, "fast")
    assert "steps" not in _form(s2)


def test_a_fixed_project_seed_seeds_the_takes_and_a_random_one_leaves_them_random(client, ltx, make_project, monkeypatch):
    from backend import generation, projects

    monkeypatch.setattr(generation, "new_seed", lambda: 999)
    project = make_project(clips=SHOTS)
    doc = copy.deepcopy(project["doc"])
    doc["engine"]["options"] = {presets.LTX_2_5: {"seed": 40}}
    saved = projects.save_project(project["id"], doc, project["version"])

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 2, "preset_id": presets.LTX_2_5})
    assert response.status_code == 202, response.text
    assert [take["seed"] for take in response.json()["data"]["takes"]] == [40, 41]

    doc["engine"]["options"] = {presets.LTX_2_5: {"seed": -1}}
    projects.save_project(project["id"], doc, saved["version"])
    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.LTX_2_5})
    assert [take["seed"] for take in response.json()["data"]["takes"]] == [999]


def test_the_options_apply_to_a_retry_from_the_current_document(client, ltx, make_project):
    from backend import generation, projects

    project = make_project(clips=SHOTS)
    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.LTX_2_5})
    (take,) = response.json()["data"]["takes"]
    ltx.fail(take["generation_id"])
    asyncio.run(tracker.Tracker().tick())
    current = projects.get_project(project["id"])
    doc = copy.deepcopy(current["doc"])
    doc["engine"]["options"] = {presets.LTX_2_5: {"cfg": 2.5}}
    projects.save_project(project["id"], doc, current["version"])

    response = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert response.status_code == 202, response.text
    assert ltx.submitted[-1][1]["form_data"]["cfg"] == 2.5
    assert response.json()["data"]["take"]["seed"] == take["seed"]
    assert generation.takes.get_take(response.json()["data"]["take"]["id"])["request"]["form_data"]["cfg"] == 2.5


def test_the_estimate_times_the_takes_with_the_steps_their_options_ask_for(ltx, make_doc):
    resolution = _plans(ltx, _doc(make_doc)).shots[0].resolution
    takes.add_calibration(presets.LTX_2_5, "b-local", resolution, 4.0, 120000)

    plain = _evaluate(ltx, _doc(make_doc))
    distilled = _evaluate(ltx, _doc(make_doc, {presets.LTX_2_5: {"speed_profile": "distilled"}}))
    doubled = _evaluate(ltx, _doc(make_doc, {presets.LTX_2_5: {"steps": 48}}))

    assert plain.payload["time"]["seconds"] == 240.0
    assert distilled.payload["time"]["seconds"] == 80.0
    assert doubled.payload["time"]["seconds"] == 480.0
    assert plain.minutes == {"s1": 2.0, "s2": 2.0}
    assert distilled.minutes == {"s1": round(2.0 / 3, 3), "s2": round(2.0 / 3, 3)}
    assert estimate.plan_minutes(distilled.plans.shots[0], presets.LTX_2_5, "b-local") == round(2.0 / 3, 3)


def test_the_estimate_without_measures_scales_the_reserved_minutes_too(ltx, make_doc):
    evaluation = _evaluate(ltx, _doc(make_doc, {presets.LTX_2_5: {"steps": 12}}))

    assert evaluation.payload["time"]["seconds"] is None
    assert evaluation.minutes == {"s1": round(4 * 10 * 0.5 / 60, 3), "s2": round(4 * 10 * 0.5 / 60, 3)}


def test_a_measure_counts_as_one_made_at_the_steps_of_the_defaults(client, ltx, make_project):
    from backend import projects

    project = make_project(clips=SHOTS)
    doc = copy.deepcopy(project["doc"])
    doc["engine"]["options"] = {presets.LTX_2_5: {"speed_profile": "distilled"}}
    projects.save_project(project["id"], doc, project["version"])
    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.LTX_2_5})
    (take,) = response.json()["data"]["takes"]

    ltx.complete(take["generation_id"], duration_ms=40000, seconds=4.0)
    asyncio.run(tracker.Tracker().tick())

    assert takes.get_take(take["id"])["status"] == "done"
    ((seconds, duration_ms),) = takes.calibration(presets.LTX_2_5, "b-local", take["resolution"])
    assert (seconds, duration_ms) == (pytest.approx(4.0 / 3), 40000)
    ratio, count = estimate.calibrated_ratio(presets.LTX_2_5, "b-local", take["resolution"])
    assert (ratio, count) == (pytest.approx(30.0), 1)


def test_a_take_without_a_request_or_with_an_unknown_mode_counts_as_made_at_the_defaults(ltx):
    assert engine_options.take_scale({"preset_id": presets.LTX_2_5, "mode": "video"}) == 1.0
    assert engine_options.take_scale({"preset_id": presets.LTX_2_5, "mode": "nope", "request": {"form_data": {"steps": 8}}}) == 1.0
    assert engine_options.take_scale({"preset_id": presets.LTX_2_5, "mode": "video", "request": {"form_data": {"steps": 12}}}) == 0.5


def test_the_schema_keeps_options_per_preset_and_refuses_malformed_ones(make_doc):
    doc = make_doc(clips=SHOTS)
    doc["engine"]["options"] = {
        presets.LTX_2_5: {"speed_profile": "distilled", "steps": 12, "cfg": 1.5, "generate_audio": True, "loras": [{"model": "model:l1", "strength": 0.5}]},
        presets.WAN: {},
    }
    validate_doc(doc)

    for options in (
        [],
        {"": {}},
        {presets.WAN: []},
        {presets.WAN: {"": 1}},
        {presets.WAN: {"steps": None}},
        {presets.WAN: {"seed": {"value": 1}}},
        {presets.WAN: {"loras": [{"model": "model:l1"}]}},
        {presets.WAN: {"loras": [{"model": "model:l1", "strength": 1.0, "enabled": True}]}},
    ):
        broken = copy.deepcopy(doc)
        broken["engine"]["options"] = options
        with pytest.raises(DocError):
            validate_doc(broken)


def test_an_older_document_without_options_stays_valid(make_doc):
    doc = make_doc(clips=SHOTS)
    doc["engine"].pop("options", None)

    validate_doc(doc)
