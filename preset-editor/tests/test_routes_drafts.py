import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import drafts, history, paths
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user
from tests.conftest import read_id

DRAFTS_URL = "/api/plugins/preset-editor/drafts"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


@pytest.fixture
def client(core):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _copy(client, **overrides):
    body = {"mode": "copy", "from_id": "fixture-minimal-native", "name": "My copy", "model_dir": "MyModel", "variant_dir": "v1"}
    body.update(overrides)
    return client.post(DRAFTS_URL, json=body)


def test_a_copy_draft_is_created_lint_included(client, core, roots):
    response = _copy(client)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert paths.DRAFT_ID_RE.match(data["draft_id"]) and paths.DRAFT_ID_RE.match(data["preset_id"])
    assert (data["name"], data["source"], data["target_dir"], data["created_by"]) == ("My copy", "copy_of:fixture-minimal-native", "MyModel/v1", "admin-1")
    assert data["last_lint"]["warnings"] == ["[WARNING] preset.yml: no tests.yml"]
    assert [f["path"] for f in data["files"]] == ["modes/txt2img/form.yml", "modes/txt2img/pipeline.yml", "modes/txt2img/tabs/main.yml", "preset.yml"]
    draft = drafts.load(roots, data["draft_id"])
    assert read_id(draft.dir) == data["preset_id"]
    assert core.lint_calls == [draft.dir]


def test_a_custom_id_is_kept(client):
    assert _copy(client, preset_id="my-custom-id").json()["data"]["preset_id"] == "my-custom-id"


@pytest.mark.parametrize(
    "overrides",
    [{"preset_id": "no"}, {"model_dir": "../x"}, {"variant_dir": "a/b"}, {"name": "   "}, {"mode": "blank"}, {"from_id": "x"}],
)
def test_a_bad_request_is_refused_by_validation(client, overrides):
    assert _copy(client, **overrides).status_code == 422


def test_copying_an_unknown_preset_is_a_404(client):
    response = _copy(client, from_id="never-seen")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"


def test_drafts_are_listed_fetched_and_deleted(client, roots):
    draft_id = _copy(client).json()["data"]["draft_id"]

    assert [d["draft_id"] for d in client.get(DRAFTS_URL).json()["data"]] == [draft_id]
    assert client.get(f"{DRAFTS_URL}/{draft_id}").json()["data"]["files"][-1]["path"] == "preset.yml"
    assert client.delete(f"{DRAFTS_URL}/{draft_id}").json() == {"success": True, "data": {"draft_id": draft_id}}
    assert client.get(DRAFTS_URL).json()["data"] == []
    for missing in (draft_id, "nope", "01M4NGDDGASNZ1SFY7236C95QW"):
        response = client.get(f"{DRAFTS_URL}/{missing}")
        assert response.status_code == 404 and response.json()["detail"]["error"] == "not_found"


def test_lint_reports_and_records(client, core, roots):
    draft_id = _copy(client).json()["data"]["draft_id"]
    core.lint = (["[ERROR] bad"], [])

    response = client.post(f"{DRAFTS_URL}/{draft_id}/lint")

    assert response.json() == {"success": True, "data": {"errors": ["[ERROR] bad"], "warnings": []}}
    assert drafts.load(roots, draft_id).last_lint["errors"] == ["[ERROR] bad"]


def test_publishing_writes_reloads_installs_and_marks_the_draft(client, core, roots):
    created = _copy(client).json()["data"]
    draft_id, preset_id = created["draft_id"], created["preset_id"]

    response = client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert (data["preset_id"], data["target_dir"], data["archived"], data["installed"]) == (preset_id, "MyModel/v1", None, True)
    assert data["preset"]["kind"] == "local" and data["preset"]["path"] == "MyModel/v1" and data["preset"]["name"] == "My copy"
    assert data["draft"]["published_at"].endswith("Z")
    assert read_id(roots.local_presets / "MyModel" / "v1") == preset_id
    assert core.reloads == 1 and core.installs == [(preset_id, "admin-1")]
    assert list(roots.staging.iterdir()) == []


def test_publishing_again_archives_the_previous_version_and_installs_once(client, core, roots):
    first = _copy(client, name="First").json()["data"]
    client.post(f"{DRAFTS_URL}/{first['draft_id']}/publish", json={})
    second = _copy(client, name="Second", preset_id=first["preset_id"]).json()["data"]

    response = client.post(f"{DRAFTS_URL}/{second['draft_id']}/publish", json={})

    data = response.json()["data"]
    assert paths.STAMP_RE.match(data["archived"]) and data["installed"] is True
    assert core.installs == [(first["preset_id"], "admin-1")]
    assert [e["name"] for e in history.list_entries(roots, first["preset_id"])] == ["First"]
    assert '"Second"' in (roots.local_presets / "MyModel" / "v1" / "preset.yml").read_text(encoding="utf-8")


def test_publishing_without_install_leaves_the_preset_uninstalled(client, core):
    draft_id = _copy(client).json()["data"]["draft_id"]

    data = client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={"install": False}).json()["data"]

    assert data["installed"] is False and core.installs == []


def test_the_install_setting_is_the_default(client, core):
    core.settings["install_after_publish"] = False
    draft_id = _copy(client).json()["data"]["draft_id"]

    assert client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={}).json()["data"]["installed"] is False


def test_lint_errors_block_publication(client, core, roots):
    draft_id = _copy(client).json()["data"]["draft_id"]
    core.lint = (["[ERROR] preset.yml: broken"], ["w"])

    response = client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "success": False, "error": "lint_errors", "message": "the preset has lint errors",
        "lint": {"errors": ["[ERROR] preset.yml: broken"], "warnings": ["w"]},
    }
    assert not roots.local_presets.exists() or list(roots.local_presets.iterdir()) == []
    assert core.reloads == 0


def test_an_id_collision_blocks_publication(client, core, roots):
    draft_id = _copy(client, preset_id="fixture-minimal-native").json()["data"]["draft_id"]

    response = client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={})

    assert response.status_code == 409 and response.json()["detail"]["error"] == "id_in_use"
    assert core.reloads == 0


def test_a_folder_collision_blocks_publication(client, core):
    first = _copy(client).json()["data"]["draft_id"]
    client.post(f"{DRAFTS_URL}/{first}/publish", json={})
    second = _copy(client, name="Other").json()["data"]["draft_id"]

    response = client.post(f"{DRAFTS_URL}/{second}/publish", json={})

    assert response.status_code == 409 and response.json()["detail"]["error"] == "target_in_use"


def test_a_catalogue_that_does_not_show_the_preset_is_reported(client, core):
    core.reload_registers = False
    draft_id = _copy(client).json()["data"]["draft_id"]

    response = client.post(f"{DRAFTS_URL}/{draft_id}/publish", json={})

    assert response.status_code == 500 and response.json()["detail"]["error"] == "publish_unverified"
    assert core.installs == []


def test_every_draft_route_needs_an_admin(core):
    app = FastAPI()
    app.include_router(router)
    user = User(id="u", username="u", email="u@test.com", password_hash="x", account_type=AccountType.USER)
    app.dependency_overrides[get_current_active_user] = lambda: user
    with TestClient(app) as client:
        assert client.get(DRAFTS_URL).status_code == 403
        assert client.post(DRAFTS_URL, json={}).status_code == 403
        assert client.post(f"{DRAFTS_URL}/01M4NGDDGASNZ1SFY7236C95QW/publish", json={}).status_code == 403
