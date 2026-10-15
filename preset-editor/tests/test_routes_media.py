import io

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend import drafts
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user

DRAFTS_URL = "/api/plugins/preset-editor/drafts"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


def _png(width=1400, height=700):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


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


def _upload(client, draft, role, name, data, **fields):
    return client.post(f"{DRAFTS_URL}/{draft['draft_id']}/media", files={"file": (name, data, "image/png")}, data={"role": role, **fields})


def test_a_cover_upload_writes_the_file_declares_it_and_lints(client, draft, core, roots):
    response = _upload(client, draft, "cover", "cover.png", _png())

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["path"] == "public/cover.webp" and data["media"]["cover"] == "public/cover.webp"
    assert "public/cover.webp" in [f["path"] for f in data["files"]]
    assert data["lint"]["errors"] == []
    manifest = drafts.load(roots, draft["draft_id"]).dir / "preset.yml"
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["media"] == {"cover": "public/cover.webp"}


def test_gallery_uploads_take_a_caption_and_a_mode_and_are_listed(client, draft):
    _upload(client, draft, "gallery", "Shot one.png", _png(), caption="First shot", mode="txt2img")
    _upload(client, draft, "gallery", "shot two.png", _png())

    listed = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/media").json()["data"]

    assert listed["cover"] is None
    assert listed["gallery"] == [
        {"src": "public/examples/Shot-one.webp", "caption": "First shot", "mode": "txt2img"},
        {"src": "public/examples/shot-two.webp"},
    ]
    assert [entry["roles"] for entry in listed["files"]] == [["gallery"], ["gallery"]]


def test_a_draft_media_file_is_served_only_from_public(client, draft):
    _upload(client, draft, "cover", "cover.png", _png())

    served = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/public/public/cover.webp")

    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    assert served.headers["cache-control"] == "no-store" and served.content[:4] == b"RIFF"
    assert client.get(f"{DRAFTS_URL}/{draft['draft_id']}/public/preset.yml").status_code == 400
    assert client.get(f"{DRAFTS_URL}/{draft['draft_id']}/public/public/missing.webp").status_code == 404


def test_bad_uploads_are_refused(client, draft):
    assert _upload(client, draft, "cover", "notes.yml", b"x").status_code == 400
    assert _upload(client, draft, "cover", "broken.png", b"nope").status_code == 400
    assert _upload(client, draft, "logo", "a.png", _png()).status_code == 400
    assert _upload(client, draft, "gallery", "big.png", b"x" * (20 * 1024 * 1024 + 1)).status_code == 413


def test_deleting_a_media_file_removes_its_reference(client, draft, roots):
    _upload(client, draft, "cover", "cover.png", _png())
    _upload(client, draft, "gallery", "g.png", _png(), caption="g")

    response = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/media/public/cover.webp")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["media"]["cover"] is None and [item["src"] for item in data["media"]["gallery"]] == ["public/examples/g.webp"]
    assert "public/cover.webp" not in [f["path"] for f in data["files"]]
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/media/public/cover.webp").status_code == 404
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/media/preset.yml").status_code == 400


def test_declaring_media_picks_the_cover_and_orders_the_gallery_among_the_files(client, draft, roots):
    first = _upload(client, draft, "gallery", "a.png", _png()).json()["data"]["path"]
    second = _upload(client, draft, "gallery", "b.png", _png()).json()["data"]["path"]

    response = client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"cover": second, "gallery": [{"src": second, "caption": " B ", "seed": 7}, {"src": first, "mode": "txt2img"}]})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["media"]["cover"] == second
    assert data["media"]["gallery"] == [{"src": second, "caption": "B", "seed": 7}, {"src": first, "mode": "txt2img"}]
    assert data["lint"]["errors"] == []
    manifest = drafts.load(roots, draft["draft_id"]).dir / "preset.yml"
    assert yaml.safe_load(manifest.read_text(encoding="utf-8"))["media"]["cover"] == second

    cleared = client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"cover": None, "gallery": []})
    assert cleared.status_code == 200 and cleared.json()["data"]["media"] == {"cover": None, "gallery": [], "files": cleared.json()["data"]["media"]["files"]}
    assert "media" not in yaml.safe_load(manifest.read_text(encoding="utf-8"))


def test_declaring_a_file_that_is_not_there_or_not_media_is_refused(client, draft):
    _upload(client, draft, "gallery", "a.png", _png())

    assert client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"cover": "public/examples/missing.webp"}).status_code == 404
    assert client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"cover": "preset.yml"}).status_code == 400
    assert client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"gallery": [{"src": "public/examples/a.webp"}, {"src": "public/examples/a.webp"}]}).status_code == 400
    assert client.put(f"{DRAFTS_URL}/{draft['draft_id']}/media", json={"gallery": [{"src": "public/examples/a.webp", "mode": "Bad Mode"}]}).status_code == 422
    listed = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/media").json()["data"]
    assert listed["cover"] is None and [item["src"] for item in listed["gallery"]] == ["public/examples/a.webp"]


def test_media_routes_need_an_admin(core):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = lambda: User(id="u", username="u", email="u@test.com", password_hash="x", account_type=AccountType.USER)
    with TestClient(app) as client:
        assert client.get(f"{DRAFTS_URL}/01M4NGDDGASNZ1SFY7236C95QW/media").status_code == 403
        assert client.put(f"{DRAFTS_URL}/01M4NGDDGASNZ1SFY7236C95QW/media", json={}).status_code == 403
        core.viewer = User(id="u", username="u", email="u@test.com", password_hash="x", account_type=AccountType.USER)
        assert client.get(f"{DRAFTS_URL}/01M4NGDDGASNZ1SFY7236C95QW/public/public/cover.webp").status_code == 403
        core.viewer = None
        assert client.get(f"{DRAFTS_URL}/01M4NGDDGASNZ1SFY7236C95QW/public/public/cover.webp").status_code == 401
