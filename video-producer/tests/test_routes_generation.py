import asyncio

import pytest

from backend import presets, takes, tracker
from src.plugin_api import get_current_active_user

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 6}]
ORDER = {"shots": ["s1", "s2"], "quality": "draft", "variants": 1, "preset_id": presets.WAN}


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


@pytest.fixture
def project(core, make_project):
    core.use_wan()
    return make_project(clips=SHOTS)


def test_the_estimate_route_answers_the_contract_shape(client, core, project):
    response = client.post(f"{BASE}/projects/{project['id']}/estimate", json=ORDER)

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"shots", "vram", "time", "quota", "cost", "blocks", "warnings"}
    assert [shot["shot_id"] for shot in data["shots"]] == ["s1", "s2"]
    assert set(data["vram"]) == {"estimate_gb", "free_gb", "total_gb", "budget_gb", "streams", "unknown", "backend_id"}
    assert set(data["quota"]) == {"limit", "used", "remaining", "exempt", "needed_minutes", "applies", "blocks"}
    assert data["time"] == {"seconds": None, "samples": 0}
    assert data["blocks"] == [] and data["cost"] is None
    assert core.submitted == [] and takes.list_takes(project["id"]) == []


def test_the_estimate_route_reports_blocks_without_failing(client, core, project):
    response = client.post(f"{BASE}/projects/{project['id']}/estimate", json={**ORDER, "shots": []})

    assert response.status_code == 200
    assert [block["code"] for block in response.json()["data"]["blocks"]] == ["no_shots"]


@pytest.mark.parametrize("route", ["estimate", "generate"])
def test_a_malformed_body_answers_422(client, core, project, route):
    response = client.post(f"{BASE}/projects/{project['id']}/{route}", json={**ORDER, "variants": 0})

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "success": False,
        "error": "invalid_request",
        "message": "variants must be an integer from 1 to 16.",
    }


@pytest.mark.parametrize("route", ["estimate", "generate"])
def test_another_users_project_is_not_found(client, core, make_project, route):
    core.use_wan()
    other = make_project(user_id="user-2", clips=SHOTS)

    response = client.post(f"{BASE}/projects/{other['id']}/{route}", json=ORDER)

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"


def test_generate_answers_202_with_the_takes_and_starts_the_tracker(client, core, project):
    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={**ORDER, "label": "Pass 1"})

    assert response.status_code == 202
    created = response.json()["data"]["takes"]
    assert [(take["shot_id"], take["status"], take["generation_id"]) for take in created] == [
        ("s1", "queued", "gen-1"),
        ("s2", "queued", "gen-2"),
    ]
    assert set(created[0]) == set(takes.PUBLIC)
    assert len(core.scheduled) == 1


def test_generate_rechecks_every_block_and_answers_409(client, core, project):
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}
    core.missing.add("vae-sha")

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json=ORDER)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "blocked"
    assert [block["code"] for block in detail["data"]["blocks"]] == ["missing_models", "quota_exceeded"]
    assert takes.list_takes(project["id"]) == [] and core.submitted == [] and core.recorded == []


def test_an_admin_generates_on_a_users_project_as_its_owner(app, client, core, project):
    _as(app, core.users["admin-1"])

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json=ORDER)

    assert response.status_code == 202
    assert [user_id for user_id, _ in core.submitted] == ["user-1", "user-1"]
    assert all(record[0] == "user-1" for record in core.recorded)
    assert {take["id"] for take in takes.list_takes(project["id"])} == {take["id"] for take in response.json()["data"]["takes"]}


def test_an_admin_sees_the_cost_of_a_cloud_estimate(app, client, core, make_project):
    core.use_openrouter()
    project = make_project(clips=SHOTS)
    body = {**ORDER, "preset_id": presets.OPENROUTER_VIDEO, "model_id": "cm-veo"}

    as_user = client.post(f"{BASE}/projects/{project['id']}/estimate", json=body).json()["data"]
    _as(app, core.users["admin-1"])
    as_admin = client.post(f"{BASE}/projects/{project['id']}/estimate", json=body).json()["data"]

    assert as_user["cost"] is None
    assert as_admin["cost"] == {"total_usd": "1.20", "known": True, "message": None}


def test_a_project_whose_owner_is_gone_answers_409(app, client, core, project):
    del core.users["user-1"]
    _as(app, core.users["admin-1"])

    response = client.post(f"{BASE}/projects/{project['id']}/generate", json=ORDER)

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "owner_not_found"


def test_the_queue_lists_the_takes_in_flight_and_the_slots_of_the_owner(client, core, project, make_project, store):
    store[("max_parallel_jobs", None)] = "2"
    client.post(f"{BASE}/projects/{project['id']}/generate", json={**ORDER, "variants": 2})
    core.complete("gen-1")
    asyncio.run(tracker.Tracker().tick())

    response = client.get(f"{BASE}/projects/{project['id']}/queue")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [(take["shot_id"], take["variant"], take["status"]) for take in data["takes"]] == [
        ("s1", "B", "queued"),
        ("s2", "A", "queued"),
        ("s2", "B", "queued"),
    ]
    assert data["slots"] == {"in_flight": 2, "max": 2}


def test_the_queue_of_another_users_project_is_not_found(client, core, make_project):
    core.use_wan()
    other = make_project(user_id="user-2", clips=SHOTS)

    assert client.get(f"{BASE}/projects/{other['id']}/queue").status_code == 404
