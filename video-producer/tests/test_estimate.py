import asyncio

import pytest

from backend import estimate, presets, takes
from backend.estimate import Order, OrderError

SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 6}]


def _order(**fields):
    return Order(**{"shots": ["s1", "s2"], "quality": "draft", "variants": 2, "preset_id": presets.WAN, **fields})


def _evaluate(core, doc, caller="user-1", owner="user-1", **fields):
    return asyncio.run(estimate.evaluate(core.users[caller], core.users[owner], doc, _order(**fields)))


def _codes(notes):
    return [item["code"] for item in notes]


WAN_DRAFT = {"preset_id": presets.WAN, "model_id": None, "profile": "FL2VA", "quality": "draft", "audio": None}
LTX_DRAFT = {**WAN_DRAFT, "preset_id": presets.LTX_2_5}


def test_a_native_estimate_has_the_contract_shape(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=SHOTS)

    payload = _evaluate(core, doc).payload

    assert payload["production"] == "ai"
    assert payload["shots"] == [
        {"shot_id": "s1", "director_mode": "t2v", "seconds": 4.0, "resolution": "832x480", "fps": 16, "guides": [], **WAN_DRAFT},
        {"shot_id": "s2", "director_mode": "t2v", "seconds": 6.0, "resolution": "832x480", "fps": 16, "guides": [], **WAN_DRAFT},
    ]
    assert payload["renders"] == []
    assert payload["vram"] == {
        "estimate_gb": 18.5,
        "free_gb": 22.0,
        "total_gb": 24.0,
        "budget_gb": None,
        "streams": False,
        "unknown": False,
        "backend_id": "b-local",
    }
    assert payload["time"] == {"seconds": None, "samples": 0}
    assert payload["quota"] == {
        "limit": 600,
        "used": 0,
        "remaining": 600.0,
        "exempt": False,
        "needed_minutes": round((4 + 6) * 10 / 60 * 2, 2),
        "applies": True,
        "blocks": False,
    }
    assert payload["cost"] is None
    assert payload["blocks"] == []
    assert _codes(payload["warnings"]) == ["fl2va_no_frame", "fl2va_no_frame", "time_unknown"]


def test_the_memory_is_previewed_as_the_owner_with_the_first_shot_request(core, make_doc):
    core.use_wan()

    _evaluate(core, make_doc(clips=SHOTS), caller="admin-1", owner="user-1")

    ((user_id, request),) = core.previewed
    assert user_id == "user-1"
    assert request["form_data"]["video_director"]["settings"]["duration"] == 4.0
    assert "idempotency_key" not in request


def test_a_model_larger_than_the_free_vram_streams_with_a_warning(core, make_doc):
    core.use_wan()
    core.memory = {**core.memory, "estimate": {"checkpoint_estimate_gb": 30.0}, "device": {"free_gb": 20.0, "total_gb": 24.0}}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert (payload["vram"]["streams"], payload["vram"]["unknown"]) == (True, False)
    assert payload["warnings"][-2] == {
        "code": "vram_stream",
        "message": "The model does not fit in the GPU memory it may use: it will stream through host RAM, slower.",
        "data": {"estimate_gb": 30.0, "free_gb": 20.0, "budget_gb": None, "total_gb": 24.0},
    }
    assert payload["blocks"] == []


@pytest.mark.parametrize("memory", [RuntimeError("no backend"), {"estimate": {"checkpoint_estimate_gb": None}, "device": {}, "backend": {}}])
def test_an_unknown_memory_estimate_warns_and_never_blocks(core, make_doc, memory):
    core.use_wan()
    core.memory = memory

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["vram"]["unknown"] is True and payload["vram"]["streams"] is False
    assert "vram_unknown" in _codes(payload["warnings"])
    assert payload["blocks"] == []


def test_the_memory_is_not_previewed_when_models_are_missing(core, make_doc):
    core.use_wan()
    core.missing.add("vae-sha")

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert core.previewed == []
    assert payload["vram"]["unknown"] is True and "vram_unknown" not in _codes(payload["warnings"])
    assert _codes(payload["blocks"]) == ["missing_models"]


def test_the_time_is_the_median_measured_ratio_times_the_seconds_asked(core, make_doc):
    core.use_wan()
    for seconds, duration_ms in ((5.0, 50000), (4.0, 60000), (2.0, 60000)):
        takes.add_calibration(presets.WAN, "b-local", "832x480", seconds, duration_ms)
    takes.add_calibration(presets.WAN, "b-other", "832x480", 1.0, 999000)
    takes.add_calibration(presets.WAN, "b-local", "1280x720", 1.0, 999000)

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["time"] == {"seconds": 15.0 * (4 + 6) * 2, "samples": 3}
    assert payload["quota"]["needed_minutes"] == round(15.0 * (4 + 6) * 2 / 60, 2)
    assert "time_unknown" not in _codes(payload["warnings"])


def test_a_second_native_backend_does_not_inherit_the_measures_of_the_first(core, make_doc):
    core.use_wan()
    for _ in range(3):
        takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, 60000)
    core.memory = {**core.memory, "backend": {"id": "b-studio", "name": "Studio A6000", "engine": "native", "driver": "native.remote"}}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["vram"]["backend_id"] == "b-studio"
    assert payload["time"] == {"seconds": None, "samples": 0}
    assert "time_unknown" in _codes(payload["warnings"])
    assert payload["quota"]["needed_minutes"] == round((4 + 6) * 10 / 60 * 2, 2)


def test_each_native_backend_reads_only_its_own_measures(core, make_doc):
    core.use_wan()
    takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, 60000)
    takes.add_calibration(presets.WAN, "b-studio", "832x480", 4.0, 20000)
    takes.add_calibration(presets.WAN, "b-studio", "832x480", 4.0, 20000)
    studio = {**core.memory, "backend": {"id": "b-studio", "name": "Studio A6000", "engine": "native", "driver": "native.remote"}}

    local = _evaluate(core, make_doc(clips=SHOTS), variants=1).payload
    core.memory = studio
    remote = _evaluate(core, make_doc(clips=SHOTS), variants=1).payload

    assert local["time"] == {"seconds": 15.0 * (4 + 6), "samples": 1}
    assert remote["time"] == {"seconds": 5.0 * (4 + 6), "samples": 2}


@pytest.mark.parametrize("memory", [RuntimeError("no backend"), {"estimate": {"checkpoint_estimate_gb": 18.0}, "device": {"free_gb": 22.0}, "backend": {}}])
def test_without_the_backend_that_would_render_the_time_is_unknown_whatever_was_measured(core, make_doc, memory):
    core.use_wan()
    takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, 60000)
    core.memory = memory

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["vram"]["backend_id"] is None
    assert payload["time"] == {"seconds": None, "samples": 0}
    assert "time_unknown" in _codes(payload["warnings"])


def test_the_measures_are_read_only_for_a_named_backend():
    assert takes.calibration(presets.WAN, None, "832x480") == []
    assert takes.calibration(presets.WAN, "", "832x480") == []


def test_only_the_twenty_latest_measures_count(core, make_doc, monkeypatch):
    core.use_wan()
    moments = iter(f"2026-10-17T10:{minute:02d}:00+00:00" for minute in range(60))
    monkeypatch.setattr(takes, "_now", lambda: next(moments))
    for _ in range(5):
        takes.add_calibration(presets.WAN, "b-local", "832x480", 1.0, 100000)
    for _ in range(20):
        takes.add_calibration(presets.WAN, "b-local", "832x480", 1.0, 10000)

    payload = _evaluate(core, make_doc(clips=SHOTS), variants=1).payload

    assert payload["time"] == {"seconds": 100.0, "samples": 20}


def test_a_quota_too_small_for_the_takes_blocks(core, make_doc):
    core.use_wan()
    core.quota = {"limit": 30, "used": 28, "remaining": 2.0, "exempt": False, "resets_at": None}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["quota"]["blocks"] is True
    assert payload["blocks"] == [
        {
            "code": "quota_exceeded",
            "message": "These takes need 3.33 GPU minutes; 2 remain this month.",
            "data": {"needed_minutes": 3.33, "remaining": 2.0},
        }
    ]


def test_an_exempt_or_unlimited_user_is_never_blocked_by_the_quota(core, make_doc):
    core.use_wan()
    core.quota = {"limit": 30, "used": None, "remaining": None, "exempt": True, "resets_at": None}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["quota"]["exempt"] is True and payload["quota"]["blocks"] is False
    assert payload["blocks"] == []


def test_a_cloud_estimate_needs_no_quota_nor_vram(core, make_doc):
    core.use_openrouter()
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}

    payload = _evaluate(core, make_doc(clips=SHOTS), preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo").payload

    assert payload["quota"]["applies"] is False and payload["quota"]["needed_minutes"] == 0
    assert payload["quota"]["blocks"] is False
    assert payload["vram"] == {
        "estimate_gb": None,
        "free_gb": None,
        "total_gb": None,
        "budget_gb": None,
        "streams": False,
        "unknown": True,
        "backend_id": None,
    }
    assert core.previewed == []
    assert "vram_unknown" not in _codes(payload["warnings"])
    assert payload["cost"] is None


def test_an_admin_sees_the_cost_of_a_cloud_run_for_every_take(core, make_doc):
    core.use_openrouter()

    payload = _evaluate(core, make_doc(clips=SHOTS), caller="admin-1", preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo").payload

    assert payload["cost"] == {"total_usd": "1.20", "known": True, "message": None}
    ((model_id, shots),) = core.costed
    assert model_id == "cm-veo"
    assert shots == [
        {"task": "txt2video", "params": {"duration_s": 4.0, "resolution": "720p", "aspect_ratio": "16:9"}},
        {"task": "txt2video", "params": {"duration_s": 4.0, "resolution": "720p", "aspect_ratio": "16:9"}},
        {"task": "txt2video", "params": {"duration_s": 6.0, "resolution": "720p", "aspect_ratio": "16:9"}},
        {"task": "txt2video", "params": {"duration_s": 6.0, "resolution": "720p", "aspect_ratio": "16:9"}},
    ]


def test_the_cost_says_why_it_is_unknown(core, make_doc):
    core.use_openrouter()
    core.cost = ValueError("At most 64 shots can be estimated at once.")

    payload = _evaluate(core, make_doc(clips=SHOTS), caller="admin-1", preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo").payload

    assert payload["cost"] == {"total_usd": None, "known": False, "message": "At most 64 shots can be estimated at once."}


def test_a_native_preset_has_no_cost_even_for_an_admin(core, make_doc):
    core.use_wan()

    assert _evaluate(core, make_doc(clips=SHOTS), caller="admin-1").payload["cost"] is None
    assert core.costed == []


def test_blocks_keep_every_shot_out_of_the_estimate(core, make_doc):
    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["shots"] == [] and _codes(payload["blocks"]) == ["no_preset"]
    assert payload["time"] == {"seconds": None, "samples": 0}
    assert "time_unknown" not in _codes(payload["warnings"])


def test_take_minutes_fall_back_to_ten_seconds_of_work_per_second():
    assert estimate.take_minutes(6.0, None) == 1.0
    assert estimate.take_minutes(6.0, 20.0) == 2.0


@pytest.mark.parametrize(
    "body, message",
    [
        (None, "The request body must be a JSON object."),
        ({"shots": "s1"}, "shots must be a list of shot ids."),
        ({"shots": ["s1", ""]}, "shots must be a list of shot ids."),
        ({"shots": ["s1"], "quality": "best"}, "quality must be one of: draft, final."),
        ({"shots": ["s1"], "quality": "draft", "variants": 0}, "variants must be an integer from 1 to 16."),
        ({"shots": ["s1"], "quality": "draft", "variants": True}, "variants must be an integer from 1 to 16."),
        ({"shots": ["s1"], "quality": "draft", "variants": 17}, "variants must be an integer from 1 to 16."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1}, "preset_id must be a preset id."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": "p", "model_id": 3}, "model_id must be a model id or null."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": "p", "label": "x" * 201}, "label must be a string of at most 200 characters."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": "p", "production": "Rendu 3D"}, "production must be one of: ai, render3d, render3d_ai."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1, "production": "render3d_ai"}, "preset_id must be a preset id."),
        ({"shots": ["s1"], "quality": "draft", "variants": 1, "production": "render3d", "preset_id": 3}, "preset_id must be a preset id."),
    ],
)
def test_a_malformed_order_is_refused(body, message):
    with pytest.raises(OrderError, match=message):
        estimate.parse_order(body)


def test_an_order_keeps_what_it_asks_for():
    order = estimate.parse_order(
        {"shots": [], "quality": "final", "variants": 3, "preset_id": "p", "model_id": None, "label": "Pass 2", "other": 1}
    )

    assert order == Order(shots=[], quality="final", variants=3, preset_id="p", model_id=None, label="Pass 2", production="ai")


@pytest.mark.parametrize("production, preset_id", [("ai", "p"), ("render3d", None), ("render3d", "p"), ("render3d_ai", "p")])
def test_an_order_names_its_production_mode_and_the_3d_render_needs_no_preset(production, preset_id):
    body = {"shots": ["s1"], "quality": "draft", "variants": 1, "production": production}
    if preset_id is not None:
        body["preset_id"] = preset_id

    order = estimate.parse_order(body)

    assert (order.production, order.preset_id) == (production, preset_id)


def _guided_doc(make_doc, stale=False, asset=True):
    assets = [{"id": "guide-video", "kind": "video", "origin": {"kind": "library", "itemId": "lib-guide"}, "srcDur": 4.0}] if asset else []
    controls = [{"id": "c1", "shotId": "s1", "stale": stale, "planId": "p1", "assetId": "guide-video" if asset else None}]
    return make_doc(clips=SHOTS, assets=assets, controls=controls)


def test_the_3d_render_estimate_lists_the_renders_the_shots_take_without_preset_minutes_or_memory(core, make_doc):
    payload = _evaluate(core, _guided_doc(make_doc), preset_id=None, production="render3d").payload

    assert payload["production"] == "render3d"
    assert payload["shots"] == []
    assert payload["renders"] == [{"shot_id": "s1", "control_id": "c1", "plan_id": "p1", "asset_id": "guide-video"}]
    assert payload["blocks"] == []
    assert _codes(payload["warnings"]) == ["render_missing"]
    assert payload["warnings"][0]["data"] == {"shot_id": "s2"}
    assert (payload["quota"]["applies"], payload["quota"]["needed_minutes"], payload["vram"]["unknown"]) == (False, 0.0, True)
    assert payload["time"] == {"seconds": None, "samples": 0} and payload["cost"] is None
    assert core.previewed == []


def test_the_3d_render_estimate_is_blocked_when_no_shot_has_a_fresh_render(core, make_doc):
    payload = _evaluate(core, _guided_doc(make_doc, stale=True), preset_id=None, production="render3d").payload

    assert _codes(payload["blocks"]) == ["no_render"]
    assert _codes(payload["warnings"]) == ["stale_guide", "render_missing", "render_missing"]


def test_the_3d_render_and_ai_estimate_is_blocked_without_a_refs_preset(core, make_doc):
    core.use_wan()

    payload = _evaluate(core, _guided_doc(make_doc), production="render3d_ai").payload

    assert payload["production"] == "render3d_ai"
    assert payload["blocks"] == [
        {
            "code": "refs_preset_needed",
            "message": "The 3D render + AI mode needs a MiniMax-H3 preset with its References mode, or LTX-2.5.",
            "data": {"preset_id": presets.WAN},
        }
    ]
    assert payload["shots"] == [] and payload["quota"]["needed_minutes"] == 0.0


def test_the_3d_render_and_ai_estimate_on_ltx_2_5_lists_a_director_shot_with_its_guide(core, make_doc):
    core.use_ltx25()
    core.add_media({"kind": "library", "item_id": "lib-guide"}, "uploads/guide.mp4", "video")

    payload = _evaluate(core, _guided_doc(make_doc), preset_id=presets.LTX_2_5, production="render3d_ai").payload

    assert (payload["production"], payload["blocks"]) == ("render3d_ai", [])
    assert payload["shots"] == [
        {"shot_id": "s1", "director_mode": "director", "seconds": 4.0, "resolution": "832x480", "fps": 25, "guides": ["c1"], **LTX_DRAFT},
        {"shot_id": "s2", "director_mode": "t2v", "seconds": 6.0, "resolution": "832x480", "fps": 25, "guides": [], **LTX_DRAFT},
    ]
    assert [(item["code"], item["data"]["shot_id"]) for item in payload["warnings"] if "shot_id" in (item.get("data") or {})] == [
        ("layout_no_frame", "s1"),
        ("render_missing", "s2"),
        ("fl2va_no_frame", "s2"),
    ]


@pytest.mark.parametrize(
    "device, budget, capacity",
    [
        ({"free_gb": None, "total_gb": 12.0}, {"configured_gb": 10.0}, {"budget_gb": 10.0, "total_gb": 12.0}),
        ({"free_gb": None, "total_gb": None}, {"configured_gb": 10.0}, {"budget_gb": 10.0, "total_gb": None}),
        ({"free_gb": None, "total_gb": 12.0}, {"configured_gb": None}, {"budget_gb": None, "total_gb": 12.0}),
    ],
)
def test_without_free_vram_the_budget_or_the_total_tells_a_model_will_stream(core, make_doc, device, budget, capacity):
    core.use_wan()
    core.memory = {**core.memory, "estimate": {"checkpoint_estimate_gb": 45.3}, "device": device, "budget": budget}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert payload["vram"] == {
        "estimate_gb": 45.3,
        "free_gb": None,
        "streams": True,
        "unknown": False,
        "backend_id": "b-local",
        **capacity,
    }
    (stream,) = [warning for warning in payload["warnings"] if warning["code"] == "vram_stream"]
    assert stream["data"] == {"estimate_gb": 45.3, "free_gb": None, **capacity}
    assert "vram_unknown" not in _codes(payload["warnings"]) and payload["blocks"] == []


def test_a_model_within_the_budget_does_not_stream(core, make_doc):
    core.use_wan()
    core.memory = {**core.memory, "estimate": {"checkpoint_estimate_gb": 8.0}, "device": {"free_gb": None, "total_gb": 12.0}, "budget": {"configured_gb": 10.0}}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert (payload["vram"]["streams"], payload["vram"]["unknown"], payload["vram"]["budget_gb"]) == (False, False, 10.0)
    assert not {"vram_stream", "vram_unknown"} & set(_codes(payload["warnings"]))


def test_an_estimate_with_no_free_total_or_budget_is_unknown(core, make_doc):
    core.use_wan()
    core.memory = {**core.memory, "estimate": {"checkpoint_estimate_gb": 45.3}, "device": {"free_gb": None, "total_gb": None}, "budget": {}}

    payload = _evaluate(core, make_doc(clips=SHOTS)).payload

    assert (payload["vram"]["estimate_gb"], payload["vram"]["streams"], payload["vram"]["unknown"]) == (45.3, False, True)
    assert "vram_unknown" in _codes(payload["warnings"]) and "vram_stream" not in _codes(payload["warnings"])
