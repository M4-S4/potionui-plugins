import asyncio
import copy

import pytest

from backend import director, estimate, generation, presets, takes, tracker
from backend.estimate import Order
from backend.projects import DocError, validate_doc

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}, {"id": "s3", "start": 8, "dur": 4}]
ORDER = {"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.WAN}


def _generate(client, project_id, **order):
    response = client.post(f"{BASE}/projects/{project_id}/generate", json={**ORDER, **order})
    assert response.status_code == 202, response.text
    return response.json()["data"]["takes"]


def _prioritize(client, project_id, take_id):
    return client.post(f"{BASE}/projects/{project_id}/takes/{take_id}/prioritize")


def _queue(client, project_id):
    response = client.get(f"{BASE}/projects/{project_id}/queue")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _tick():
    asyncio.run(tracker.Tracker().tick())


def _evaluate(core, doc, owner="user-1", caller=None, **fields):
    order = Order(**{"shots": ["s1", "s2"], "quality": "draft", "variants": 1, "preset_id": presets.WAN, **fields})
    return asyncio.run(estimate.evaluate(core.users[caller or owner], core.users[owner], doc, order))


def _with_engines(doc, **engines):
    for clip in doc["clips"]:
        if clip["id"] in engines:
            clip["engine"] = engines[clip["id"]]
    return doc


@pytest.fixture
def project(core, make_project):
    core.use_wan()
    return make_project(clips=SHOTS)


@pytest.fixture
def queued(client, core, project):
    created = _generate(client, project["id"], shots=["s1", "s2", "s3"], variants=1)
    created += _generate(client, project["id"], shots=["s3"], variants=1)
    return created


def test_a_new_take_has_priority_zero_and_the_api_shows_it(project_db):
    take = takes.create_take({"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render"})

    assert take["priority"] == 0
    assert takes.public(take)["priority"] == 0


def test_the_waiting_takes_come_by_priority_then_age(project_db):
    fields = {"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render"}
    first, second, third = (takes.create_take(fields) for _ in range(3))
    takes.prioritize(third)

    assert [take["id"] for take in takes.waiting("user-1")] == [third["id"], first["id"], second["id"]]


def test_moving_a_take_to_the_head_puts_its_priority_one_above_the_highest(project_db):
    fields = {"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render"}
    first, second, third = (takes.create_take(fields) for _ in range(3))

    assert takes.prioritize(third)["priority"] == 1
    assert takes.prioritize(second)["priority"] == 2
    assert takes.prioritize(second)["priority"] == 2
    assert [take["id"] for take in takes.waiting("user-1")] == [second["id"], third["id"], first["id"]]


def test_the_queue_of_another_user_is_left_alone(project_db):
    mine = takes.create_take({"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render"})
    theirs = takes.create_take({"project_id": "p-2", "shot_id": "s1", "user_id": "user-2", "quality": "draft", "kind": "render"})
    later = takes.create_take({"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render"})

    takes.prioritize(later)

    assert takes.get_take(theirs["id"])["priority"] == 0
    assert [take["id"] for take in takes.waiting("user-1")] == [later["id"], mine["id"]]


def test_the_pump_hands_the_take_moved_to_the_head_first(client, core, project, queued):
    s1, s2, s3, s3_again = queued
    assert [take["generation_id"] is not None for take in queued] == [True, True, False, False]

    response = _prioritize(client, project["id"], s3_again["id"])

    assert response.status_code == 200, response.text
    assert response.json()["data"]["take"]["priority"] == 1
    core.complete(s1["generation_id"])
    _tick()
    assert takes.get_take(s3_again["id"])["generation_id"] is not None
    assert takes.get_take(s3["id"])["generation_id"] is None


def test_a_take_already_handed_to_the_core_is_not_touched(client, project, queued):
    response = _prioritize(client, project["id"], queued[1]["id"])

    assert response.status_code == 200
    assert response.json()["data"]["take"]["priority"] == 0
    assert takes.get_take(queued[1]["id"])["priority"] == 0


def test_an_ended_take_cannot_move_to_the_head(client, project, queued):
    generation.cancel_local(takes.get_take(queued[2]["id"]))

    response = _prioritize(client, project["id"], queued[2]["id"])

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "take_not_queued"


def test_the_route_refuses_a_take_of_another_project_or_user(client, core, make_project, project, queued, app, make_user):
    other = make_project(clips=SHOTS)

    assert _prioritize(client, other["id"], queued[3]["id"]).status_code == 404
    user = make_user(user_id="user-2")
    from backend.core_bridge import get_current_active_user

    app.dependency_overrides[get_current_active_user] = lambda: user
    response = _prioritize(client, project["id"], queued[3]["id"])
    assert (response.status_code, response.json()["detail"]["error"]) == (404, "project_not_found")
    assert takes.get_take(queued[3]["id"])["priority"] == 0


def test_the_queue_lists_the_takes_in_flight_first_then_the_waiting_ones_in_pump_order(client, project, queued):
    s1, s2, s3, s3_again = queued
    _prioritize(client, project["id"], s3_again["id"])

    data = _queue(client, project["id"])

    assert [take["id"] for take in data["takes"]] == [s1["id"], s2["id"], s3_again["id"], s3["id"]]
    assert [take["queue_position"] for take in data["takes"]] == [None, None, 1, 2]
    assert data["slots"] == {"in_flight": 2, "max": 2}
    assert data["elsewhere"] == {"waiting": 0, "in_flight": 0}


def test_the_queue_counts_the_takes_of_the_owner_s_other_projects_in_the_places(client, core, make_project, project, queued):
    other = make_project(clips=SHOTS)
    (elsewhere,) = _generate(client, other["id"], shots=["s1"])
    _prioritize(client, other["id"], elsewhere["id"])

    data = _queue(client, project["id"])

    assert [take["queue_position"] for take in data["takes"]] == [None, None, 2, 3]
    assert data["elsewhere"] == {"waiting": 1, "in_flight": 0}


def test_build_plans_runs_each_shot_on_its_own_preset_and_model(core, make_doc):
    core.use_wan()
    core.use_ltx25()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": presets.LTX_2_5, "model": None})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "s3"], presets.WAN, "draft", overrides=True)

    assert plans.blocks == []
    assert [(plan.shot_id, plan.preset_id) for plan in plans.shots] == [
        ("s1", presets.WAN),
        ("s2", presets.LTX_2_5),
        ("s3", presets.WAN),
    ]
    assert [plan.request["preset_id"] for plan in plans.shots] == [presets.WAN, presets.LTX_2_5, presets.WAN]
    assert plans.preset.id == presets.WAN


def test_without_overrides_the_shot_engines_are_ignored(core, make_doc):
    core.use_wan()
    core.use_ltx25()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": presets.LTX_2_5, "quality": "final", "seed": 7})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], presets.WAN, "draft")

    assert [(plan.preset_id, plan.quality, plan.seed) for plan in plans.shots] == [(presets.WAN, "draft", None)] * 2


def test_a_shot_quality_replaces_the_project_one_for_that_shot_only(core, make_doc):
    core.use_wan()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"quality": "final"})
    plain_final = director.build_plans(core.users["user-1"], make_doc(clips=SHOTS), ["s2"], presets.WAN, "final")

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], presets.WAN, "draft", overrides=True)

    first, second = plans.shots
    assert (first.quality, first.resolution) == ("draft", "832x480")
    assert second.quality == "final"
    assert second.resolution == plain_final.shots[0].resolution != first.resolution


def test_a_shot_profile_replaces_the_project_one_for_that_shot_only(core, make_doc):
    core.use_h3()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"profile": "Hybrid AV"})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], presets.MINIMAX_H3, "draft", overrides=True)

    assert plans.blocks == []
    assert [(plan.shot_id, plan.profile) for plan in plans.shots] == [("s1", "FL2VA"), ("s2", "Hybrid AV")]
    assert plans.profile == "FL2VA"


def test_the_blocks_of_a_shot_engine_name_its_shots(core, make_doc):
    core.use_wan()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": "gone"}, s3={"profile": "Ref2VA"})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "s3"], presets.WAN, "draft", overrides=True)

    assert [plan.shot_id for plan in plans.shots] == ["s1"]
    assert [(block["code"], block["data"].get("shot_ids")) for block in plans.blocks] == [
        ("no_preset", ["s2"]),
        ("profile_unsupported", ["s3"]),
    ]


def test_the_project_preset_is_not_needed_when_every_shot_has_its_own(core, make_doc):
    core.use_wan()
    doc = _with_engines(make_doc(clips=SHOTS[:2]), s1={"preset": presets.WAN}, s2={"preset": presets.WAN})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], "removed-preset", "draft", overrides=True)

    assert plans.blocks == []
    assert [plan.preset_id for plan in plans.shots] == [presets.WAN, presets.WAN]


@pytest.mark.parametrize(
    "engine",
    [{"preset": ""}, {"profile": "Painting"}, {"quality": "best"}, {"seed": -1}, {"seed": 2**31}, {"seed": True}, "wan"],
)
def test_a_malformed_shot_engine_is_read_as_the_project_one(core, make_doc, engine):
    doc = make_doc(clips=SHOTS[:1])
    doc["clips"][0]["engine"] = engine

    assert director.shot_engine(doc, "s1") == {}


def test_a_shot_preset_brings_its_model_and_a_native_one_has_none(make_doc):
    doc = _with_engines(make_doc(clips=SHOTS[:2]), s1={"preset": presets.OPENROUTER_VIDEO, "model": "cm-veo"}, s2={"preset": presets.WAN})

    assert director.shot_engine(doc, "s1") == {"preset": presets.OPENROUTER_VIDEO, "model": "cm-veo"}
    assert director.shot_engine(doc, "s2") == {"preset": presets.WAN, "model": None}


def test_the_takes_of_a_shot_run_on_its_engine_and_quality(client, core, make_project, monkeypatch):
    core.use_wan()
    core.use_ltx25()
    project = make_project(clips=SHOTS)
    doc = _with_engines(copy.deepcopy(project["doc"]), s2={"preset": presets.LTX_2_5, "quality": "final"})
    from backend import projects

    projects.save_project(project["id"], doc, project["version"])

    created = _generate(client, project["id"], shots=["s1", "s2"], variants=1)

    assert [(take["shot_id"], take["preset_id"], take["quality"], take["label"]) for take in created] == [
        ("s1", presets.WAN, "draft", "draft"),
        ("s2", presets.LTX_2_5, "final", "candidate"),
    ]
    assert [request["preset_id"] for _, request in core.submitted] == [presets.WAN, presets.LTX_2_5]


def test_a_fixed_seed_is_taken_by_the_first_take_and_the_next_seeds_by_the_others(client, core, make_project, monkeypatch):
    core.use_wan()
    monkeypatch.setattr(generation, "new_seed", lambda: 999)
    project = make_project(clips=SHOTS)
    from backend import projects

    doc = _with_engines(copy.deepcopy(project["doc"]), s1={"seed": 2**31 - 1})
    projects.save_project(project["id"], doc, project["version"])

    created = _generate(client, project["id"], shots=["s1", "s2"], variants=2)

    assert [(take["shot_id"], take["seed"]) for take in created] == [("s1", 2**31 - 1), ("s1", 0), ("s2", 999), ("s2", 999)]
    seeds = [request["form_data"]["seed"] for _, request in core.submitted]
    assert seeds == [2**31 - 1, 0]


def test_generating_again_with_a_fixed_seed_gives_the_same_seeds(client, core, make_project):
    core.use_wan()
    project = make_project(clips=SHOTS)
    from backend import projects

    projects.save_project(project["id"], _with_engines(copy.deepcopy(project["doc"]), s1={"seed": 42}), project["version"])

    first = _generate(client, project["id"], shots=["s1"], variants=2)
    again = _generate(client, project["id"], shots=["s1"], variants=2)

    assert [take["seed"] for take in first] == [take["seed"] for take in again] == [42, 43]
    assert [take["variant"] for take in first + again] == ["A", "B", "C", "D"]


def test_a_retry_keeps_the_engine_of_its_take_not_the_shot_s_new_one(client, core, make_project):
    core.use_wan()
    core.use_ltx25()
    project = make_project(clips=SHOTS)
    (take,) = _generate(client, project["id"], shots=["s1"])
    core.fail(take["generation_id"])
    _tick()
    from backend import projects

    current = projects.get_project(project["id"])
    projects.save_project(project["id"], _with_engines(copy.deepcopy(current["doc"]), s1={"preset": presets.LTX_2_5, "seed": 5}), current["version"])

    response = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert response.status_code == 202, response.text
    retried = response.json()["data"]["take"]
    assert (retried["preset_id"], retried["seed"]) == (presets.WAN, take["seed"])


def test_the_estimate_reports_each_shot_engine(core, make_doc):
    core.use_wan()
    core.use_ltx25()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": presets.LTX_2_5, "quality": "final"})

    payload = _evaluate(core, doc).payload

    assert [(shot["shot_id"], shot["preset_id"], shot["quality"]) for shot in payload["shots"]] == [
        ("s1", presets.WAN, "draft"),
        ("s2", presets.LTX_2_5, "final"),
    ]
    assert [request["preset_id"] for _, request in core.previewed] == [presets.WAN, presets.LTX_2_5]


def test_the_estimate_times_each_shot_with_the_measures_of_its_preset(core, make_doc):
    core.use_wan()
    core.use_ltx25()
    takes.add_calibration(presets.WAN, "b-local", "832x480", 4.0, 40000)
    takes.add_calibration(presets.LTX_2_5, "b-local", "832x480", 4.0, 120000)
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": presets.LTX_2_5})

    evaluation = _evaluate(core, doc)

    assert evaluation.minutes == {"s1": round(4 * 10 / 60, 3), "s2": round(4 * 30 / 60, 3)}
    assert evaluation.payload["time"]["seconds"] == 40.0 + 120.0
    assert evaluation.payload["quota"]["needed_minutes"] == round(4 * 10 / 60 + 4 * 30 / 60, 2)


def test_the_quota_counts_only_the_shots_on_a_local_engine(core, make_doc):
    core.use_wan()
    core.use_openrouter()
    doc = _with_engines(make_doc(clips=SHOTS), s2={"preset": presets.OPENROUTER_VIDEO, "model": "cm-veo"})

    payload = _evaluate(core, doc, shot_variants={"s1": 3}).payload

    assert payload["blocks"] == []
    assert payload["quota"]["applies"] is True
    assert payload["quota"]["needed_minutes"] == round(4 * 10 / 60 * 3, 2)


def test_only_the_local_takes_reserve_minutes(client, core, make_project):
    core.use_wan()
    core.use_openrouter()
    project = make_project(clips=SHOTS)
    from backend import projects

    doc = _with_engines(copy.deepcopy(project["doc"]), s2={"preset": presets.OPENROUTER_VIDEO, "model": "cm-veo"})
    projects.save_project(project["id"], doc, project["version"])

    created = _generate(client, project["id"], shots=["s1", "s2"])

    assert [(take["preset_id"], take["model_id"], take["units_reserved"] > 0) for take in created] == [
        (presets.WAN, None, True),
        (presets.OPENROUTER_VIDEO, "cm-veo", False),
    ]


def test_the_cost_of_cloud_shots_is_summed_over_their_models(core, make_doc):
    core.use_wan()
    core.use_openrouter()
    core.models["cm-kling"] = core.model_spec("cm-kling")
    doc = _with_engines(
        make_doc(clips=SHOTS),
        s1={"preset": presets.OPENROUTER_VIDEO, "model": "cm-veo"},
        s2={"preset": presets.OPENROUTER_VIDEO, "model": "cm-kling"},
    )

    payload = _evaluate(core, doc, caller="admin-1", shots=["s1", "s2", "s3"]).payload

    assert sorted(model_id for model_id, _ in core.costed) == ["cm-kling", "cm-veo"]
    assert payload["cost"] == {"total_usd": "2.40", "known": True, "message": None}


def test_a_doc_whose_shots_set_their_engine_is_valid(make_doc):
    doc = _with_engines(
        make_doc(clips=SHOTS),
        s1={"preset": presets.WAN, "model": None, "backend": "b-local", "profile": "Ref2VA", "quality": "final", "seed": 0},
        s2={},
        s3={"seed": 2**31 - 1},
    )

    validate_doc(doc)


@pytest.mark.parametrize(
    "engine",
    [
        {"variants": 2},
        {"preset": ""},
        {"profile": "Painting"},
        {"quality": "Standard"},
        {"seed": -1},
        {"seed": 2**31},
        {"seed": 1.5},
        {"model": 3},
        None,
    ],
)
def test_a_malformed_shot_engine_is_refused(make_doc, engine):
    doc = make_doc(clips=SHOTS[:1])
    doc["clips"][0]["engine"] = engine

    with pytest.raises(DocError):
        validate_doc(doc)


def test_a_doc_without_hybrid_weights_profiles_or_dead_engine_settings_is_valid(make_doc):
    doc = make_doc(clips=SHOTS[:1])
    del doc["hybrid"], doc["profiles"]
    doc["engine"] = {"quality": "draft", "variants": 2, "backend": "", "preset": None, "model": None}

    validate_doc(doc)


def test_an_older_doc_with_hybrid_weights_profiles_and_every_engine_setting_stays_valid(make_doc):
    doc = make_doc(clips=SHOTS[:1])

    assert {"hybrid", "profiles"} <= set(doc) and "steps" in doc["engine"]
    validate_doc(doc)
