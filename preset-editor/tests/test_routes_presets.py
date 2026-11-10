import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import drafts, history
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user
from tests.conftest import FIXTURES, read_id, template

PRESETS_URL = "/api/plugins/preset-editor/presets"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


@pytest.fixture
def client(core):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def local_preset(core, roots):
    target = roots.local_presets / "Local" / "v1"
    shutil.copytree(FIXTURES / "minimal-native", target)
    manifest = target / "preset.yml"
    manifest.write_text(drafts.rewrite_top_level(manifest.read_text(encoding="utf-8"), {"id": "local-one", "name": "Local one"}), encoding="utf-8")
    core.rescan_local()
    return target


def test_editing_a_local_preset_opens_a_draft_on_its_folder(client, local_preset, roots):
    response = client.post(f"{PRESETS_URL}/local-one/edit")

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert (data["preset_id"], data["name"], data["source"], data["target_dir"]) == ("local-one", "Local one", "edit_of:local-one", "Local/v1")
    assert data["last_lint"] is not None
    assert read_id(drafts.load(roots, data["draft_id"]).dir) == "local-one"


def test_only_a_local_preset_can_be_edited_in_place(client):
    response = client.post(f"{PRESETS_URL}/fixture-minimal-native/edit")

    assert response.status_code == 409 and response.json()["detail"]["error"] == "not_local"
    assert client.post(f"{PRESETS_URL}/never-seen/edit").status_code == 404
    assert client.post(f"{PRESETS_URL}/no/edit").status_code == 400


def test_deleting_a_local_preset_uninstalls_archives_and_reloads(client, core, local_preset, roots):
    core.installed.add("local-one")

    response = client.delete(f"{PRESETS_URL}/local-one")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["preset_id"] == "local-one" and data["uninstalled"] is True
    assert core.uninstalls == [("local-one", "admin-1")] and core.reloads == 1
    assert not (roots.local_presets / "Local").exists()
    assert [e["stamp"] for e in history.list_entries(roots, "local-one")] == [data["archived"]]
    assert core.templates.get("local-one") is None


def test_deleting_an_uninstalled_preset_skips_the_uninstall(client, core, local_preset):
    assert client.delete(f"{PRESETS_URL}/local-one").json()["data"]["uninstalled"] is False
    assert core.uninstalls == []


def test_only_a_local_preset_can_be_deleted(client, core, roots):
    assert client.delete(f"{PRESETS_URL}/fixture-minimal-native").status_code == 409
    assert client.delete(f"{PRESETS_URL}/never-seen").status_code == 404


@pytest.fixture
def local_mirror(core, local_preset):
    core.templates["local-one-mirror"] = template(
        "local-one-mirror", local_preset, kind="local", origin_path="Local/v1", name="Local one, mirrored",
        source_preset_id="local-one",
    )
    core.installed.update({"local-one", "local-one-mirror"})
    return core.templates["local-one-mirror"]


def test_deleting_a_mirror_is_refused_before_the_uninstall_and_keeps_the_folder_of_its_source(client, core, local_mirror, local_preset, roots):
    response = client.delete(f"{PRESETS_URL}/local-one-mirror")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert (detail["error"], detail["source_preset_id"]) == ("mirror", "local-one")
    assert "Admin → Presets" in detail["message"] and "'local-one'" in detail["message"]
    assert core.uninstalls == [] and core.reloads == 0
    assert read_id(local_preset) == "local-one"
    assert history.list_entries(roots, "local-one-mirror") == [] and history.list_entries(roots, "local-one") == []


def test_a_preset_whose_folder_holds_another_preset_is_not_deleted(client, core, local_preset, roots):
    core.templates["stray-one"] = template("stray-one", local_preset, kind="local", origin_path="Local/v1")
    core.installed.add("stray-one")

    response = client.delete(f"{PRESETS_URL}/stray-one")

    assert response.status_code == 409 and response.json()["detail"]["error"] == "not_its_folder"
    assert "'local-one'" in response.json()["detail"]["message"]
    assert core.uninstalls == [] and read_id(local_preset) == "local-one"
    assert history.list_entries(roots, "stray-one") == []


def test_a_preset_loaded_from_another_folder_than_its_origin_says_is_not_deleted(client, core, local_preset, roots):
    core.templates["local-one"] = template("local-one", local_preset, kind="local", origin_path="Other/v1")

    response = client.delete(f"{PRESETS_URL}/local-one")

    assert response.status_code == 409 and response.json()["detail"]["error"] == "not_its_folder"
    assert read_id(local_preset) == "local-one"


def test_history_lists_versions_and_restores_one_as_a_draft(client, core, local_preset, roots, monkeypatch):
    monkeypatch.setattr(history, "stamp_now", lambda: "20261015T100000.000007")
    client.delete(f"{PRESETS_URL}/local-one")

    listed = client.get(f"{PRESETS_URL}/local-one/history").json()["data"]
    assert [(e["stamp"], e["reason"], e["target_dir"], e["name"]) for e in listed] == [
        ("20261015T100000.000007", "delete", "Local/v1", "Local one"),
    ]

    response = client.post(f"{PRESETS_URL}/local-one/history/20261015T100000.000007/restore")

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert (data["preset_id"], data["name"], data["source"], data["target_dir"]) == ("local-one", "Local one", "restore_of:local-one@20261015T100000.000007", "Local/v1")
    assert read_id(drafts.load(roots, data["draft_id"]).dir) == "local-one"
    assert data["last_lint"] is not None


def test_restoring_targets_the_folder_the_preset_lives_in_now(client, core, local_preset, roots, monkeypatch):
    monkeypatch.setattr(history, "stamp_now", lambda: "20261015T100000.000008")
    history.archive(roots, local_preset, preset_id="local-one", target_dir="Old/place", reason="publish")

    data = client.post(f"{PRESETS_URL}/local-one/history/20261015T100000.000008/restore").json()["data"]

    assert data["target_dir"] == "Local/v1"


def test_an_unknown_version_cannot_be_restored(client):
    response = client.post(f"{PRESETS_URL}/local-one/history/20261015T100000.000001/restore")

    assert response.status_code == 404 and response.json()["detail"]["error"] == "not_found"
    assert client.post(f"{PRESETS_URL}/local-one/history/..%2Fx/restore").status_code in (404, 400)


def test_every_preset_route_needs_an_admin(core):
    app = FastAPI()
    app.include_router(router)
    user = User(id="u", username="u", email="u@test.com", password_hash="x", account_type=AccountType.USER)
    app.dependency_overrides[get_current_active_user] = lambda: user
    with TestClient(app) as client:
        assert client.get(f"{PRESETS_URL}/local-one/history").status_code == 403
        assert client.delete(f"{PRESETS_URL}/local-one").status_code == 403
        assert client.post(f"{PRESETS_URL}/local-one/edit").status_code == 403
