import io
import shutil
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import archive, drafts
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user
from tests.conftest import FIXTURES, read_header, template

PREFIX = "/api/plugins/preset-editor"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)
USER = User(id="u", username="u", email="u@test.com", password_hash="x", account_type=AccountType.USER)
NATIVE = FIXTURES / "minimal-native"


@pytest.fixture
def client(core):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _names(response):
    return sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist())


def test_a_draft_is_exported_as_a_zip_without_its_private_files(client, roots):
    draft = client.post(f"{PREFIX}/drafts", json={"mode": "copy", "from_id": "fixture-minimal-native", "name": "Copy", "model_dir": "M"}).json()["data"]

    response = client.get(f"{PREFIX}/drafts/{draft['draft_id']}/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == f'attachment; filename="{draft["preset_id"]}-draft.zip"'
    names = _names(response)
    assert "preset.yml" in names and "modes/txt2img/form.yml" in names
    assert drafts.META_FILE not in names


def test_a_local_preset_is_exported_but_not_a_marketplace_one(client, core, tmp_path):
    local = tmp_path / "local" / "Mine"
    shutil.copytree(NATIVE, local)
    core.templates["mine-preset"] = template("mine-preset", local, kind="local", origin_path="Mine", name="Mine")

    response = client.get(f"{PREFIX}/presets/mine-preset/export")

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="mine-preset.zip"'
    assert "preset.yml" in _names(response)
    assert client.get(f"{PREFIX}/presets/fixture-minimal-native/export").status_code == 409
    assert client.get(f"{PREFIX}/presets/missing-preset/export").status_code == 404


def test_exports_follow_the_media_viewer_rule(client, core):
    draft = client.post(f"{PREFIX}/drafts", json={"mode": "copy", "from_id": "fixture-minimal-native", "name": "Copy", "model_dir": "M"}).json()["data"]
    core.viewer = USER
    assert client.get(f"{PREFIX}/drafts/{draft['draft_id']}/export").status_code == 403
    core.viewer = None
    assert client.get(f"{PREFIX}/drafts/{draft['draft_id']}/export").status_code == 401


def test_an_archive_becomes_a_draft_that_keeps_its_id_and_is_linted(client, core, roots):
    data = archive.export_dir(NATIVE)

    response = client.post(f"{PREFIX}/drafts/import", files={"file": ("my preset.zip", data, "application/zip")}, data={"model_dir": "Imported", "variant_dir": "v1"})

    assert response.status_code == 201, response.text
    draft = response.json()["data"]
    assert (draft["preset_id"], draft["name"], draft["target_dir"], draft["source"]) == ("fixture-minimal-native", "Minimal native", "Imported/v1", "import:my preset.zip")
    assert "modes/txt2img/form.yml" in [item["path"] for item in draft["files"]]
    assert draft["last_lint"]["warnings"] == ["[WARNING] preset.yml: no tests.yml"]
    assert core.lint_calls == [drafts.load(roots, draft["draft_id"]).dir]
    assert not [path for path in roots.drafts.iterdir() if path.name.startswith(".import-")]


def test_an_import_can_rename_the_preset(client, roots):
    data = archive.export_dir(NATIVE)

    response = client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", data, "application/zip")}, data={"model_dir": "Imported", "preset_id": "renamed-preset", "name": "Renamed"})

    assert response.status_code == 201, response.text
    draft = response.json()["data"]
    assert (draft["preset_id"], draft["name"]) == ("renamed-preset", "Renamed")
    header = read_header(drafts.load(roots, draft["draft_id"]).dir)
    assert (header["id"], header["name"]) == ("renamed-preset", "Renamed")


def test_bad_imports_are_refused_and_leave_nothing_behind(client, roots):
    good = archive.export_dir(NATIVE)
    hostile = io.BytesIO()
    with zipfile.ZipFile(hostile, "w") as out:
        out.writestr("preset.yml", "schema: 1\n")
        out.writestr("../escape.yml", "x")

    assert client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", good, "application/zip")}, data={}).status_code == 422
    assert client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", good, "application/zip")}, data={"model_dir": "Imported", "preset_id": "x"}).status_code == 422
    assert client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", good, "application/zip")}, data={"model_dir": "../up"}).status_code == 422
    assert client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", hostile.getvalue(), "application/zip")}, data={"model_dir": "Imported"}).status_code == 400
    assert client.post(f"{PREFIX}/drafts/import", files={"file": ("p.zip", b"nope", "application/zip")}, data={"model_dir": "Imported"}).status_code == 400
    assert client.get(f"{PREFIX}/drafts").json()["data"] == []
    assert not any(path.name.startswith(".import-") for path in roots.drafts.iterdir()) if roots.drafts.exists() else True
