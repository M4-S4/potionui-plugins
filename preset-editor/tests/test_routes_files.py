import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import drafts, files, paths
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user
from tests.test_scaffold import FAMILY

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


@pytest.fixture
def draft(client):
    body = {"mode": "copy", "from_id": "fixture-minimal-native", "name": "My copy", "model_dir": "MyModel", "variant_dir": "v1"}
    return client.post(DRAFTS_URL, json=body).json()["data"]


def _file_url(draft, path):
    return f"{DRAFTS_URL}/{draft['draft_id']}/files/{path}"


def test_a_text_file_is_read_with_its_etag(client, draft, roots):
    response = client.get(_file_url(draft, "modes/txt2img/form.yml"))

    assert response.status_code == 200
    data = response.json()["data"]
    expected = (drafts.load(roots, draft["draft_id"]).dir / "modes" / "txt2img" / "form.yml").read_bytes()
    assert (data["path"], data["content"], data["etag"], data["size"]) == ("modes/txt2img/form.yml", expected.decode(), files.etag_of(expected), len(expected))


def test_writing_needs_the_etag_and_returns_the_next_one_with_a_lint(client, draft, core, roots):
    current = client.get(_file_url(draft, "preset.yml")).json()["data"]

    refused = client.put(_file_url(draft, "preset.yml"), json={"content": "schema: 1\n"})
    assert refused.status_code == 428
    assert refused.json()["detail"]["etag"] == current["etag"]

    written = client.put(_file_url(draft, "preset.yml"), json={"content": current["content"] + "tags: [x]\n"}, headers={"If-Match": current["etag"]})
    assert written.status_code == 200, written.text
    data = written.json()["data"]
    assert data["etag"] != current["etag"] and data["lint"] == {"errors": [], "warnings": ["[WARNING] preset.yml: no tests.yml"]}
    assert core.lint_calls[-1] == drafts.load(roots, draft["draft_id"]).dir

    stale = client.put(_file_url(draft, "preset.yml"), json={"content": "other\n"}, headers={"If-Match": current["etag"]})
    assert stale.status_code == 412
    assert stale.json()["detail"]["etag"] == data["etag"]
    assert stale.json()["detail"]["content"].endswith("tags: [x]\n")


def test_a_new_file_is_created_without_an_etag(client, draft):
    response = client.put(_file_url(draft, "modes/txt2img/tabs/extra.yml"), json={"content": "fields: []\n"})

    assert response.status_code == 200, response.text
    assert client.get(_file_url(draft, "modes/txt2img/tabs/extra.yml")).json()["data"]["content"] == "fields: []\n"


@pytest.mark.parametrize("path, status, code", [("modes\\x.yml", 400, "invalid_path"), ("public/cover.png", 400, "not_text"), ("modes/nope.yml", 404, "not_found")])
def test_bad_reads_are_refused(client, draft, path, status, code):
    response = client.get(_file_url(draft, path))

    assert response.status_code == status and response.json()["detail"]["error"] == code


def test_deleting_a_file_updates_the_tree_and_never_touches_the_manifest(client, draft):
    response = client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml"))

    assert response.status_code == 200
    assert "modes/txt2img/tabs/main.yml" not in [f["path"] for f in response.json()["data"]["files"]]
    assert response.json()["data"]["lint"]["errors"] == []
    assert client.delete(_file_url(draft, "preset.yml")).status_code == 400
    assert client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml")).status_code == 404


def test_a_mode_is_added_from_the_skeleton_and_removed_with_its_folder(client, draft, roots):
    added = client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})

    assert added.status_code == 201, added.text
    data = added.json()["data"]
    assert data["modes"] == ["txt2img", "img2img"]
    assert "modes/img2img/tabs/main.yml" in [f["path"] for f in data["files"]]
    manifest = drafts.load(roots, draft["draft_id"]).dir / "preset.yml"
    assert files.manifest_modes(manifest.read_text(encoding="utf-8")) == ["txt2img", "img2img"]
    assert client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"}).status_code == 409
    assert client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "Bad Name"}).status_code == 422

    removed = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img")

    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["modes"] == ["txt2img"]
    assert not (manifest.parent / "modes" / "img2img").exists()
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img").status_code == 409
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/nope").status_code == 404


def test_a_mode_whose_files_another_mode_loads_is_kept(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    form = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "form.yml"
    form.write_text(form.read_text(encoding="utf-8").replace("modes/img2img/tabs/main.yml", "modes/txt2img/tabs/main.yml"), encoding="utf-8")

    refused = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img")

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["modes/img2img/form.yml"]
    assert "modes/img2img/form.yml" in refused.json()["detail"]["message"]
    assert (form.parent.parent / "txt2img" / "tabs" / "main.yml").is_file()
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img").status_code == 200


def test_a_family_mode_is_added_with_the_family_tabs(client, draft):
    body = {"mode": "img2img", "family": {**FAMILY.__dict__, "model_slots": list(FAMILY.model_slots), "sampler_choices": list(FAMILY.sampler_choices)}}

    response = client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json=body)

    assert response.status_code == 201, response.text
    assert "modes/img2img/tabs/lora.yml" in [f["path"] for f in response.json()["data"]["files"]]


def test_a_blank_native_draft_is_scaffolded(client, roots):
    body = {"mode": "blank", "name": "Fresh", "model_dir": "Fresh", "variant_dir": "v1", "modes": ["txt2img", "img2img"]}

    response = client.post(DRAFTS_URL, json=body)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["source"] == "blank" and paths.DRAFT_ID_RE.match(data["preset_id"])
    assert [f["path"] for f in data["files"]] == [
        "description.md", "modes/img2img/form.yml", "modes/img2img/pipeline.yml", "modes/img2img/tabs/main.yml",
        "modes/txt2img/form.yml", "modes/txt2img/pipeline.yml", "modes/txt2img/tabs/main.yml", "preset.yml",
    ]
    header = drafts.read_header(drafts.load(roots, data["draft_id"]).dir)
    assert (header["id"], header["name"], header["engine"], header["category"], header["modes"]) == (data["preset_id"], "Fresh", "native", "image", ["txt2img", "img2img"])


def test_a_blank_cloud_draft_needs_a_driver_and_known_modes(client):
    base = {"mode": "blank", "name": "Cloud", "model_dir": "Cloud", "engine": "cloud", "modes": ["txt2video"]}

    assert client.post(DRAFTS_URL, json=base).status_code == 422
    assert client.post(DRAFTS_URL, json={**base, "driver": "cloud.openrouter", "modes": ["nope"]}).status_code == 422
    assert client.post(DRAFTS_URL, json={**base, "driver": "native.x"}).status_code == 422

    response = client.post(DRAFTS_URL, json={**base, "driver": "cloud.openrouter"})

    assert response.status_code == 201, response.text
    paths_written = [f["path"] for f in response.json()["data"]["files"]]
    assert paths_written == ["description.md", "modes/txt2video/form.yml", "modes/txt2video/pipeline.yml", "preset.yml"]


def test_a_blank_family_draft_gets_the_family_tabs(client):
    family = {**FAMILY.__dict__, "model_slots": list(FAMILY.model_slots), "sampler_choices": list(FAMILY.sampler_choices)}
    body = {"mode": "blank", "name": "Z", "model_dir": "ZImage", "modes": ["txt2img"], "family": family}

    response = client.post(DRAFTS_URL, json=body)

    assert response.status_code == 201, response.text
    assert "modes/txt2img/tabs/generation.yml" in [f["path"] for f in response.json()["data"]["files"]]
    assert client.post(DRAFTS_URL, json={**body, "engine": "comfyui"}).status_code == 422


def test_the_shared_reference_lists_the_fragments_and_the_cloud_blocks(client, tmp_path, monkeypatch):
    shared = tmp_path / "_shared"
    (shared / "resolutions").mkdir(parents=True)
    (shared / "resolutions" / "sdxl.yml").write_text("options: []\n", encoding="utf-8")
    (shared / "cloud" / "tabs").mkdir(parents=True)
    (shared / "cloud" / "tabs" / "image.yml").write_text("fields: []\n", encoding="utf-8")
    (shared / "notes.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(paths, "SHARED_DIR", shared)

    data = client.get("/api/plugins/preset-editor/reference/shared").json()["data"]

    assert data["root"] == "{{ paths._shared }}"
    assert data["files"] == ["cloud/tabs/image.yml", "resolutions/sdxl.yml"]
    assert "tabs/image.yml" in data["cloud_blocks"] and "models/txt2img.yml" in data["cloud_blocks"]
