import asyncio
from types import SimpleNamespace

import pytest

from backend import core_bridge, director, estimate, final_pass, generation, presets, soundtrack, takes, tracker
from backend.estimate import Order
from backend.final_pass import PassError
from backend.generation import Blocked

SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4, "firstFromPrevious": False}]
BASE = "/api/plugins/video-producer"


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _drafts(core, make_project, preset_id=presets.WAN, clips=SHOTS, **parts):
    project = make_project(clips=clips, **parts)
    user = core.users["user-1"]
    order = Order(shots=[clip["id"] for clip in clips], quality="draft", variants=1, preset_id=preset_id)
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    created = asyncio.run(generation.start(user, project, evaluation))
    while any(take["status"] in takes.ACTIVE for take in takes.list_takes(project["id"])):
        for take in takes.list_active(project["id"]):
            if take["generation_id"] and take["generation_id"] not in core.files:
                core.complete(take["generation_id"])
                ref = {"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}
                core.add_media(ref, f"generations/x/{take['generation_id']}.mp4", "VIDEO")
        _tick()
    return project, [takes.get_take(take["id"]) for take in created]


def _pass(core, project, sources, owner="user-1", **fields):
    order = final_pass.Order(**{"takes": [source["id"] for source in sources], "method": "upscale", "target": "fhd1080", **fields})
    return asyncio.run(final_pass.evaluate(core.users[owner], project, order, [takes.get_take(source["id"]) for source in sources]))


def _start(core, evaluation, project, owner="user-1"):
    return asyncio.run(final_pass.start(core.users[owner], project, evaluation))


@pytest.fixture
def guided(core, monkeypatch):
    core.use_ltx25()
    framed = []

    async def extract_frame(user, ref, at="last"):
        framed.append((user.id, ref, at))
        return {"value": f"uploads/first-{len(framed)}.png", "media_type": "image"}

    monkeypatch.setattr(core_bridge, "extract_frame", extract_frame)
    monkeypatch.setattr(core_bridge, "media_file_path", lambda kind, value: f"/storage/{value}")
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: SimpleNamespace(has_audio=False))
    return framed


@pytest.mark.parametrize(
    "body, message",
    [
        (None, "JSON object"),
        ({"takes": [], "method": "upscale", "target": "fhd1080"}, "non-empty list"),
        ({"takes": ["t1", ""], "method": "upscale", "target": "fhd1080"}, "non-empty list"),
        ({"takes": ["t1"], "method": "remaster", "target": "fhd1080"}, "method must be one of: upscale, render, guided."),
        ({"takes": ["t1"], "method": "upscale", "target": "8k"}, "target must be one of"),
        ({"takes": ["t1"], "method": "upscale", "target": "fhd1080", "upscaler": "turbo"}, "upscaler must be one of: auto, seedvr2, rtx, engine."),
        ({"takes": ["t1"], "method": "upscale", "target": "fhd1080", "rtx_source": "raw"}, "rtx_source must be one of: compressed, clean."),
    ],
)
def test_a_malformed_final_pass_is_refused(body, message):
    with pytest.raises(PassError) as caught:
        final_pass.parse_order(body)

    assert message in str(caught.value)


def test_an_order_keeps_each_take_once_in_its_order_with_the_automatic_upscaler():
    order = final_pass.parse_order({"takes": ["b", "a", "b"], "method": "render", "target": "hd720"})

    assert order == final_pass.Order(takes=["b", "a"], method="render", target="hd720", upscaler="auto", rtx_source="compressed")
    assert final_pass.parse_order({"takes": ["a"], "method": "upscale", "target": "hd720", "rtx_source": "clean"}).rtx_source == "clean"


def test_the_final_pass_upscales_every_take_with_one_target_and_reserves_their_minutes(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    submitted = len(core.submitted)

    evaluation = _pass(core, project, drafts)
    created = _start(core, evaluation, project)

    assert evaluation.payload["blocks"] == []
    assert [shot["shot_id"] for shot in evaluation.payload["shots"]] == ["s1", "s2"]
    assert {(shot["method"], shot["preset_id"], shot["mode"], shot["sound"]) for shot in evaluation.payload["shots"]} == {
        ("upscale", presets.SEEDVR2, "video_upscale", False)
    }
    assert [(take["shot_id"], take["parent_take_id"], take["kind"], take["quality"], take["label"]) for take in created] == [
        ("s1", drafts[0]["id"], "upscale", "final", "candidate"),
        ("s2", drafts[1]["id"], "upscale", "final", "candidate"),
    ]
    assert [(take["seed"], take["variant"]) for take in created] == [(draft["seed"], draft["variant"]) for draft in drafts]
    assert [request["form_data"]["resolution_target"] for _, request in core.submitted[submitted:]] == ["fhd1080", "fhd1080"]
    assert all(take["units_reserved"] == round(4 * 10 / 60, 3) for take in created)
    assert evaluation.payload["quota"]["needed_minutes"] == round(2 * 4 * 10 / 60, 2)


def test_the_final_pass_estimate_reports_time_memory_and_quota_like_a_generation(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    takes.add_calibration(presets.SEEDVR2, "b-local", "1872x1080", 4.0, 480000)

    payload = _pass(core, project, drafts).payload

    assert payload["time"] == {"seconds": 960.0, "samples": 1}
    assert payload["vram"]["estimate_gb"] == 18.5 and payload["vram"]["backend_id"] == "b-local"
    assert [shot["minutes"] for shot in payload["shots"]] == [8.0, 8.0]
    assert payload["quota"]["needed_minutes"] == 16.0 and payload["quota"]["blocks"] is False
    assert "time_unknown" not in [warning["code"] for warning in payload["warnings"]]


def test_a_block_shared_by_several_takes_names_all_their_shots_and_nothing_starts(core, make_project):
    core.use_wan()
    project, drafts = _drafts(core, make_project)

    evaluation = _pass(core, project, drafts)

    assert evaluation.payload["blocks"] == [
        {
            "code": "no_preset",
            "message": "The upscaler preset is not available to you.",
            "data": {"preset_id": presets.SEEDVR2, "shot_ids": ["s1", "s2"]},
        }
    ]
    with pytest.raises(Blocked):
        _start(core, evaluation, project)
    assert len(takes.list_takes(project["id"])) == 2


def test_missing_model_fields_of_several_takes_are_gathered_in_one_block(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    core.fields[(presets.SEEDVR2, "video_upscale")]["vae"] = {**core.fields[(presets.SEEDVR2, "video_upscale")]["vae"], "recommendations": [{"sha256": "gone", "filename": None}]}
    core.missing.add("gone")

    (block,) = _pass(core, project, drafts).payload["blocks"]

    assert (block["code"], block["data"]) == ("missing_models", {"fields": ["vae"], "shot_ids": ["s1", "s2"]})


def test_the_final_pass_is_blocked_by_the_quota_of_all_its_takes(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    core.quota = {"limit": 10, "used": 5, "remaining": 10.0, "exempt": False, "resets_at": None}
    takes.add_calibration(presets.SEEDVR2, "b-local", "1872x1080", 4.0, 480000)

    evaluation = _pass(core, project, drafts)

    assert [block["code"] for block in evaluation.payload["blocks"]] == ["quota_exceeded"]
    assert evaluation.payload["quota"]["needed_minutes"] == 16.0
    with pytest.raises(Blocked):
        _start(core, evaluation, project)


def test_an_unfinished_take_or_one_with_a_final_already_running_blocks_with_its_shot(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    _start(core, _pass(core, project, drafts[:1]), project)
    queued = takes.create_take({"project_id": project["id"], "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render"})

    codes = [(block["code"], block["data"]["shot_ids"]) for block in _pass(core, project, [drafts[0], queued]).payload["blocks"]]

    assert codes == [("final_running", ["s1"]), ("take_not_done", ["s2"])]


def test_the_seedvr2_upscaler_also_enlarges_the_takes_of_the_base_h3_preset(core, make_project):
    core.use_h3()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project, preset_id=presets.MINIMAX_H3, clips=SHOTS[:1], direction={"mode": "Hybrid AV"})

    auto = _pass(core, project, drafts).payload["shots"][0]
    forced = _pass(core, project, drafts, upscaler="seedvr2").payload["shots"][0]

    assert (auto["preset_id"], auto["mode"]) == (presets.MINIMAX_H3, "upscale")
    assert (forced["preset_id"], forced["mode"]) == (presets.SEEDVR2, "video_upscale")


def test_a_retried_upscale_keeps_the_upscaler_its_take_was_made_with(core, make_project):
    core.use_h3()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project, preset_id=presets.MINIMAX_H3, clips=SHOTS[:1], direction={"mode": "Hybrid AV"})
    (final,) = _start(core, _pass(core, project, drafts, upscaler="seedvr2"), project)
    core.fail(final["generation_id"])
    _tick()

    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(final["id"])))

    assert (retried["preset_id"], retried["mode"], retried["parent_take_id"]) == (presets.SEEDVR2, "video_upscale", drafts[0]["id"])


def test_an_rtx_pass_follows_the_kind_of_source_asked_for_and_a_retry_keeps_it(core, make_project):
    core.use_wan()
    core.use_rtx()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])
    (final,) = _start(core, _pass(core, project, drafts, upscaler="rtx", rtx_source="clean"), project)
    assert takes.get_take(final["id"])["request"]["form_data"]["intent"] == "upscale"
    core.fail(final["generation_id"])
    _tick()

    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(final["id"])))

    assert (retried["preset_id"], retried["request"]["form_data"]["intent"]) == (presets.RTX_UPSCALE, "upscale")


def test_a_render_pass_renders_each_shot_again_at_the_largest_size_with_its_seed(core, make_project):
    core.use_wan()
    project, drafts = _drafts(core, make_project)

    created = _start(core, _pass(core, project, drafts, method="render"), project)

    assert [(take["kind"], take["resolution"], take["seed"]) for take in created] == [
        ("render", "1280x720", draft["seed"]) for draft in drafts
    ]


def test_a_guided_pass_follows_the_draft_with_the_layout_to_render_ic_lora_from_its_first_frame(core, make_project, guided):
    core.use_wan()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])
    submitted = len(core.submitted)

    evaluation = _pass(core, project, drafts, method="guided")
    (take,) = _start(core, evaluation, project)

    assert evaluation.payload["blocks"] == []
    assert (take["kind"], take["quality"], take["preset_id"], take["parent_take_id"]) == ("guided", "final", presets.LTX_2_5, drafts[0]["id"])
    assert (take["resolution"], take["shot_revision"], take["seed"]) == ("1280x704", drafts[0]["shot_revision"], drafts[0]["seed"])
    request = core.submitted[submitted][1]
    form = request["form_data"]
    document = form["video_director"]
    assert (request["preset_id"], request["mode"], document["mode"]) == (presets.LTX_2_5, "video", "director")
    assert (form["fps"], form["resolution"], document["settings"]["duration"]) == (16.0, "1280x704", round(65 / 16, 6))
    assert (form["speed_profile"], form["steps"], form["cfg"], form["sampler"]) == ("distilled", 8, 1.0, "euler_ancestral")
    (entry,) = document["ic_lora"]
    assert entry["lora"] == {"model": f"model:id-{director.GUIDE_LORA}", "strength": 1.0} and entry["strength"] == 1.0
    assert entry["reference"]["path"] == f"generations/x/{drafts[0]['generation_id']}.mp4"
    assert [(item["role"], item["media"]["path"]) for item in document["media"]] == [("first", "uploads/first-1.png")]
    assert guided == [("user-1", {"kind": "history", "generation_id": drafts[0]["generation_id"], "file_id": drafts[0]["file_id"]}, 0.0)]
    assert "audio" not in document and "generate_audio" not in form


def test_a_guided_final_starts_from_the_shots_own_first_frame_while_the_draft_still_matches_it(core, make_project, guided):
    core.use_wan()
    core.add_media({"kind": "library", "item_id": "hero"}, "uploads/hero.png")
    project, drafts = _drafts(
        core,
        make_project,
        clips=SHOTS[:1],
        frames=[{"id": "f1", "shotId": "s1", "time": 0, "assetId": "a-hero", "role": "first"}],
        assets=[{"id": "a-hero", "kind": "image", "origin": {"kind": "library", "itemId": "hero"}}],
    )

    (take,) = _start(core, _pass(core, project, drafts, method="guided"), project)

    assert drafts[0]["director_mode"] == "i2v"
    document = core.submitted[-1][1]["form_data"]["video_director"]
    assert [(item["role"], item["media"]["path"]) for item in document["media"]] == [("first", "uploads/hero.png")]
    assert guided == []


def test_a_guided_final_mixes_the_sound_of_its_draft_onto_the_new_take(core, make_project, guided, monkeypatch):
    core.use_wan()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])
    project["doc"]["assets"].append({"id": f"gen-{drafts[0]['id']}", "kind": "video", "resultId": drafts[0]["id"]})
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: SimpleNamespace(has_audio=True))
    cut = []

    async def attach_all(owner, project, plans):
        for plan in plans:
            if plan.needs_audio:
                cut.append((plan.audio.references, plan.audio.length))
                soundtrack._apply(plan, {director.MUX: "uploads/draft-sound.wav"})

    monkeypatch.setattr(soundtrack, "attach_all", attach_all)

    evaluation = _pass(core, project, drafts, method="guided")
    _start(core, evaluation, project)

    assert evaluation.payload["shots"][0]["sound"] is True
    assert cut == [([f"gen-{drafts[0]['id']}"], round(65 / 16, 6))]
    form = core.submitted[-1][1]["form_data"]
    assert form["video_director"]["audio"] == [director.mux_entry("uploads/draft-sound.wav", round(65 / 16, 6))]
    assert form["audio_vae"] == "model:id-ltx25_audio_vae-sha"


@pytest.mark.parametrize(
    "missing, code",
    [("preset", "guided_unavailable"), ("lora", "guide_lora_missing")],
)
def test_a_guided_pass_needs_ltx_2_5_and_the_layout_to_render_ic_lora(core, make_project, guided, missing, code):
    core.use_wan()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])
    if missing == "preset":
        core.descriptions.pop(presets.LTX_2_5)
    else:
        core.missing.add(director.GUIDE_LORA)

    (block,) = _pass(core, project, drafts, method="guided").payload["blocks"]

    assert block["code"] == code and block["data"]["shot_ids"] == ["s1"]
    if missing == "lora":
        assert (block["data"]["file"], block["data"]["repo"]) == (director.GUIDE_LORA, director.GUIDE_REPO)


def test_a_failed_guided_final_is_retried_from_its_draft(core, make_project, guided):
    core.use_wan()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])
    (take,) = _start(core, _pass(core, project, drafts, method="guided"), project)
    core.fail(take["generation_id"])
    _tick()

    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(take["id"])))

    assert (retried["kind"], retried["parent_take_id"], retried["preset_id"]) == ("guided", drafts[0]["id"], presets.LTX_2_5)
    assert len(guided) == 2


def test_a_single_take_can_be_made_final_by_a_guided_render(core, make_project, guided):
    core.use_wan()
    project, drafts = _drafts(core, make_project, clips=SHOTS[:1])

    final = asyncio.run(generation.final(core.users["user-1"], project, drafts[0], "guided", "hd720"))

    assert (final["kind"], final["mode"], final["parent_take_id"]) == ("guided", "video", drafts[0]["id"])


def test_the_guided_frames_are_the_1_plus_8k_frames_closest_to_the_draft():
    assert [director.guided_frames(seconds, fps) for seconds, fps in ((4.0, 16), (5.1666, 24), (0.01, 24), (3.0, 24), (3.15, 24))] == [65, 121, 1, 73, 73]


def test_the_routes_estimate_then_start_a_final_pass(client, core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    body = {"takes": [draft["id"] for draft in drafts], "method": "upscale", "target": "qhd1440"}

    estimated = client.post(f"{BASE}/projects/{project['id']}/final-pass/estimate", json=body)
    started = client.post(f"{BASE}/projects/{project['id']}/final-pass", json=body)

    assert estimated.status_code == 200 and [shot["take_id"] for shot in estimated.json()["data"]["shots"]] == body["takes"]
    assert started.status_code == 202
    assert [take["parent_take_id"] for take in started.json()["data"]["takes"]] == body["takes"]
    assert set(started.json()["data"]["takes"][0]) == set(takes.PUBLIC)


def test_the_routes_refuse_a_blocked_malformed_or_unknown_final_pass(client, core, make_project):
    core.use_wan()
    project, drafts = _drafts(core, make_project)
    url = f"{BASE}/projects/{project['id']}/final-pass"

    blocked = client.post(url, json={"takes": [drafts[0]["id"]], "method": "upscale", "target": "fhd1080"})
    malformed = client.post(url, json={"takes": [drafts[0]["id"]], "method": "upscale"})
    unknown = client.post(url, json={"takes": ["nope"], "method": "upscale", "target": "fhd1080"})

    assert blocked.status_code == 409 and blocked.json()["detail"]["data"]["blocks"][0]["data"]["shot_ids"] == ["s1"]
    assert malformed.status_code == 422 and malformed.json()["detail"]["error"] == "invalid_request"
    assert unknown.status_code == 404 and unknown.json()["detail"]["error"] == "take_not_found"
    assert len(takes.list_takes(project["id"])) == 2


def test_another_users_project_has_no_final_pass(client, core, make_project):
    core.use_wan()
    other = make_project(user_id="user-2", clips=SHOTS)

    response = client.post(f"{BASE}/projects/{other['id']}/final-pass/estimate", json={"takes": ["t"], "method": "render", "target": "hd720"})

    assert response.status_code == 404 and response.json()["detail"]["error"] == "project_not_found"


def test_two_final_passes_that_each_fit_the_quota_cannot_both_reserve_it(core, make_project, monkeypatch):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    monkeypatch.setattr(estimate, "take_minutes", lambda seconds, ratio: 8.0)
    core.meter(10.0)
    evaluations = [_pass(core, project, [draft]) for draft in drafts]
    assert [evaluation.payload["blocks"] for evaluation in evaluations] == [[], []]
    sound = generation.with_sound

    async def slow(*args):
        await asyncio.sleep(0.01)
        return await sound(*args)

    monkeypatch.setattr(generation, "with_sound", slow)
    user = core.users["user-1"]

    async def together():
        return await asyncio.gather(*(final_pass.start(user, project, evaluation) for evaluation in evaluations), return_exceptions=True)

    results = asyncio.run(together())

    assert [[take["units_reserved"] for take in result] for result in results if isinstance(result, list)] == [[8.0]]
    assert [[block["code"] for block in result.blocks] for result in results if isinstance(result, Blocked)] == [["quota_exceeded"]]
    assert len([take for take in takes.list_takes(project["id"]) if take["quality"] == "final"]) == 1
