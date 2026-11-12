import copy
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from backend import core_bridge, starter
from backend.projects import canonical, migrate, validate_doc
from src.plugin_api import get_current_active_user

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACK = PLUGIN_ROOT.parent / "audit" / "pack" / "v1" / "pack.toml"
URL = "/api/plugins/video-producer/starter/images"
NAMES = ["lumi.jpg", "bottle.jpg", "bottle-gold.jpg"]


def _detail(response):
    return response.json()["detail"]


def _as(app, make_user, user_id):
    app.dependency_overrides[get_current_active_user] = lambda: make_user(user_id=user_id)


BOTTLES = {
    "bottle": ("b14769ce4e5ebc685c1a20b3b869b247aac432908e05c0a14df22ebe89cf8b73", 153282),
    "bottle-gold": ("c8d238cd18b893c32bb2eb4141e1a178559c54ebf80902ab45ccb8c98a3d05fd", 134545),
}


@pytest.mark.skipif(not PACK.is_file(), reason="the audit pack is not next to the plugin")
def test_the_portrait_of_lumi_is_the_audit_pack_input_byte_for_byte():
    inputs = tomllib.loads(PACK.read_text(encoding="utf-8"))["inputs"]

    data = starter.image_path("lumi").read_bytes()
    assert hashlib.sha256(data).hexdigest() == inputs["lumi"]["sha256"]
    assert len(data) == inputs["lumi"]["size_bytes"]


def test_the_two_bottles_are_the_wide_pair_made_for_the_starter_project():
    for name, (digest, size) in BOTTLES.items():
        data = starter.image_path(name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
        assert len(data) == size, name


def test_the_plugin_ships_the_three_images_of_the_starter_project():
    assert [starter.image_path(name).name for name in starter.IMAGES] == NAMES
    assert sorted(path.name for path in starter.FOLDER.iterdir()) == sorted(NAMES)
    for name in starter.IMAGES:
        assert starter.image_path(name).read_bytes()[:3] == b"\xff\xd8\xff", name


def test_the_route_stores_the_three_images_in_the_library_of_the_caller(client, media_store):
    response = client.post(URL)

    assert response.status_code == 200, response.text
    images = response.json()["data"]["images"]
    assert list(images) == ["lumi", "bottle", "bottle-gold"]
    assert [(item["user_id"], item["name"]) for item in media_store.saved] == [("user-1", name) for name in NAMES]
    assert [item["data"] for item in media_store.saved] == [starter.image_path(name).read_bytes() for name in starter.IMAGES]
    assert images["lumi"] == {
        "kind": "library",
        "item_id": "item-1",
        "media_type": "image",
        "url": "/api/media/uploads/0001-lumi.jpg",
        "filename": "lumi.jpg",
        "width": 832,
        "height": 468,
        "origin": {"kind": "library", "itemId": "item-1"},
    }
    assert [images[name]["origin"]["itemId"] for name in starter.IMAGES] == ["item-1", "item-2", "item-3"]


def test_a_second_account_gets_its_own_copies(app, client, media_store, make_user):
    client.post(URL)
    _as(app, make_user, "user-2")

    response = client.post(URL)

    assert response.status_code == 200, response.text
    assert [item["user_id"] for item in media_store.saved] == ["user-1"] * 3 + ["user-2"] * 3
    assert [response.json()["data"]["images"][name]["origin"]["itemId"] for name in starter.IMAGES] == ["item-4", "item-5", "item-6"]


def test_asking_again_sends_the_same_three_files_so_the_library_can_answer_its_items(client, media_store):
    first = client.post(URL).json()["data"]["images"]
    second = client.post(URL).json()["data"]["images"]

    assert [item["data"] for item in media_store.saved[:3]] == [item["data"] for item in media_store.saved[3:]]
    assert [item["filename"] for item in first.values()] == [item["filename"] for item in second.values()] == NAMES


def test_an_image_the_library_refuses_fails_the_route_with_its_name_and_reason(client, media_store, monkeypatch):
    async def save(user, path):
        if Path(path).name == "bottle-gold.jpg":
            raise core_bridge.MediaRefError("upload_rejected", "The file is too large for your plan")
        return await media_store.save_user_media(user, path)

    monkeypatch.setattr(core_bridge, "save_user_media", save)

    response = client.post(URL)

    assert response.status_code == 502
    assert _detail(response) == {
        "success": False,
        "error": "starter_images_failed",
        "message": "The file is too large for your plan",
        "data": {"image": "bottle-gold", "code": "upload_rejected"},
    }


def test_a_full_storage_plan_fails_the_route_as_limit_exceeded(client, monkeypatch):
    async def save(user, path):
        raise core_bridge.LimitExceeded([{"message": "plan full"}], "storage", None)

    monkeypatch.setattr(core_bridge, "save_user_media", save)

    response = client.post(URL)

    assert response.status_code == 502
    assert _detail(response)["data"] == {"image": "lumi", "code": "limit_exceeded"}


def test_a_missing_image_fails_the_route_with_its_name(client, media_store, monkeypatch, tmp_path):
    (tmp_path / "lumi.jpg").write_bytes(starter.image_path("lumi").read_bytes())
    monkeypatch.setattr(starter, "FOLDER", tmp_path)

    response = client.post(URL)

    assert response.status_code == 502
    assert _detail(response)["data"] == {"image": "bottle", "code": "missing"}
    assert [item["name"] for item in media_store.saved] == ["lumi.jpg"]


def test_a_stored_image_without_a_library_item_fails_the_route(client, monkeypatch):
    async def save(user, path):
        return {"value": "uploads/x.jpg", "media_type": "image", "original_filename": Path(path).name, "origin": None, "ref": None, "width": 1, "height": 1}

    monkeypatch.setattr(core_bridge, "save_user_media", save)

    response = client.post(URL)

    assert response.status_code == 502
    assert _detail(response)["data"] == {"image": "lumi", "code": "store_failed"}


def test_the_starter_document_passes_the_server_migration_unchanged_and_points_only_to_what_it_holds():
    doc = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_lumi.json").read_text(encoding="utf-8"))

    assert validate_doc(doc) == canonical(doc)
    assert migrate(copy.deepcopy(doc)) == doc
    assets = {asset["id"]: asset for asset in doc["assets"]}
    references = {reference["id"]: reference for reference in doc["references"]}
    [lumi] = doc["bible"]["characters"]
    [workshop] = doc["bible"]["places"]
    assert [asset["origin"]["itemId"] for asset in doc["assets"]] == ["starter-lumi", "starter-bottle", "starter-bottle-gold"]
    assert [assets[reference["assetId"]]["name"] for reference in doc["references"]] == ["lumi.jpg", "bottle.jpg"]
    assert [references[reference_id]["type"] for reference_id in lumi["references"]] == ["Personnage"]
    assert [clip["cast"] for clip in doc["clips"]] == [
        {"place": workshop["id"]},
        {"place": workshop["id"]},
        {"characters": [lumi["id"]], "place": workshop["id"]},
        {"place": workshop["id"]},
    ]
    shot = doc["clips"][3]
    assert [(frame["shotId"], frame["role"], assets[frame["assetId"]]["name"]) for frame in doc["frames"]] == [
        (shot["id"], "first", "bottle.jpg"),
        (shot["id"], "last", "bottle-gold.jpg"),
    ]
    assert [prompt["shotId"] for prompt in doc["prompts"]] == [clip["id"] for clip in doc["clips"]]
    assert [clip.get("firstFromPrevious") for clip in doc["clips"]] == [None, True, False, False]


@pytest.mark.parametrize("module", ["backend.api", "backend.exports.video", "backend.exports.media", "backend.frame_grab", "backend.starter"])
def test_each_module_that_reaches_the_starter_route_imports_first_in_a_fresh_interpreter(module):
    paths = [str(PLUGIN_ROOT), *[path for path in sys.path if path]]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONDONTWRITEBYTECODE": "1"}

    result = subprocess.run([sys.executable, "-B", "-c", f"import {module}"], cwd=os.getcwd(), env=env, capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stderr[-2000:]


def test_the_route_needs_a_signed_in_user(app, client, media_store):
    app.dependency_overrides.pop(get_current_active_user)

    response = client.post(URL)

    assert response.status_code == 401
    assert media_store.saved == []
