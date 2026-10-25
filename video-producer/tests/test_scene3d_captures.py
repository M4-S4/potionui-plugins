import asyncio
import os
import time

import pytest

from backend import core_bridge
from backend.scene3d import captures, storage

BASE = "/api/plugins/video-producer"


@pytest.fixture
def project(core, make_project, export_storage, media_store):
    return make_project()


def test_the_sweep_deletes_the_work_files_left_without_a_write_for_an_hour_and_leaves_the_rest(project, samples):
    work = storage.work_folder(project["id"])
    work.mkdir(parents=True)
    (work / "copy-01M5OLDCOPY00000000000000.ply").write_bytes(b"x")
    (work / "copy-01M5NEWCOPY00000000000000.ply").write_bytes(b"x")
    renders = storage.project_folder(project["id"]) / "renders" / "01M5OLDRENDER0000000000000"
    renders.mkdir(parents=True)
    assert storage.STALE_SECONDS == 3600
    hour_ago, minutes_ago, day_ago = time.time() - 3660, time.time() - 3540, time.time() - 25 * 3600
    os.utime(work / "copy-01M5OLDCOPY00000000000000.ply", (hour_ago, hour_ago))
    os.utime(work / "copy-01M5NEWCOPY00000000000000.ply", (minutes_ago, minutes_ago))
    os.utime(renders, (day_ago, day_ago))
    scene_file = storage.project_folder(project["id"]) / "01M5SCENEFILE0000000000000.ply"
    scene_file.write_bytes(samples.ply())
    os.utime(scene_file, (day_ago, day_ago))

    assert storage.sweep_work() == 1

    assert [path.name for path in work.iterdir()] == ["copy-01M5NEWCOPY00000000000000.ply"]
    assert scene_file.is_file() and renders.is_dir()


def test_the_tracker_sweeps_the_scene_storage_every_ten_minutes(monkeypatch):
    import threading

    from backend import scene3d, tracker

    assert tracker.SWEEP_INTERVAL == 600
    swept, stop = [], threading.Event()
    monkeypatch.setattr(scene3d, "sweep", lambda: swept.append("swept") or 0)
    monkeypatch.setattr(tracker, "SWEEP_INTERVAL", 0)

    async def tick(self):
        return False

    async def sleep(seconds):
        if len(swept) >= 2:
            stop.set()

    monkeypatch.setattr(tracker.Tracker, "tick", tick)
    monkeypatch.setattr(tracker.asyncio, "sleep", sleep)

    asyncio.run(tracker.Tracker().run(stop))

    assert swept == ["swept", "swept"]


def test_a_failed_sweep_is_logged_and_the_tracker_goes_on(monkeypatch, caplog):
    from backend import scene3d, tracker

    def sweep():
        raise OSError("disk gone")

    monkeypatch.setattr(scene3d, "sweep", sweep)

    assert asyncio.run(tracker.Tracker().sweep()) == 0
    assert "Could not sweep the scene storage" in caplog.text


def test_the_sweep_ignores_a_storage_without_scenes(export_storage):
    assert storage.sweep_work() == 0


def test_on_ready_fails_the_splat_jobs_a_stop_left_and_sweeps_the_old_work_files(core, client, project, scheduled, caplog):
    from hooks import lifecycle_hooks
    from backend.scene3d import jobs
    from src.plugin_api import HookContext

    jobs._insert({"id": "01M5JOBNEVERSTARTED0000000", "project_id": project["id"], "scene_id": "s", "user_id": "user-1", "status": "queued", "progress": 0, "units_reserved": 0, "created_at": storage.now()})
    work = storage.work_folder(project["id"])
    work.mkdir(parents=True)
    old = work / "copy-01M5OLDCOPY00000000000000.ply"
    old.write_bytes(b"x")
    day_ago = time.time() - 25 * 3600
    os.utime(old, (day_ago, day_ago))
    caplog.set_level("INFO", logger="plugins.video-producer")

    lifecycle_hooks.on_ready(HookContext(hook_name="plugin.lifecycle.ready", plugin_id="video-producer", data={}))

    assert jobs.get_job("01M5JOBNEVERSTARTED0000000")["status"] == "failed"
    assert list(work.iterdir()) == []
    assert "1 splat job(s) interrupted by the last stop marked failed" in caplog.text


def test_a_png_capture_is_stored_in_the_owner_library_under_its_name(client, project, samples, media_store, export_storage):
    png = samples.png()

    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(png), "name": "Hut – wide angle"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["media"] == {
        "kind": "library",
        "item_id": "item-1",
        "media_type": "image",
        "url": "/api/media/uploads/0001-Hut_wide_angle.png",
        "filename": "Hut_wide_angle.png",
        "width": 832,
        "height": 468,
        "origin": {"kind": "library", "itemId": "item-1"},
    }
    assert [(saved["user_id"], saved["name"], saved["data"]) for saved in media_store.saved] == [("user-1", "Hut_wide_angle.png", png)]
    assert list(storage.work_folder(project["id"]).iterdir()) == []


@pytest.mark.parametrize(
    "name, stem",
    [
        ("-vf", "vf"),
        ("--help me", "help_me"),
        (".hidden", "hidden"),
        ("-.-y", "y"),
        ("*-x", "x"),
        ("-", "capture"),
        ("- -", "capture"),
        ("-NUL", "_NUL"),
        ("Hut – wide angle", "Hut_wide_angle"),
        ("a" * 79 + ".b", "a" * 79),
    ],
)
def test_a_file_name_never_starts_with_a_dash_or_a_dot(name, stem):
    assert captures.file_stem(name, "capture") == stem


def test_a_capture_without_a_name_is_called_capture(client, project, samples, media_store):
    client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(samples.png())})

    assert media_store.saved[0]["name"] == "capture.png"


@pytest.mark.parametrize(
    "png",
    [None, 3, "data:image/png;base64,***", "data:image/jpeg;base64,/9j/4AAQ", "data:image/png;base64,aGVsbG8="],
)
def test_a_capture_that_is_not_a_png_data_url_is_refused(client, project, media_store, png):
    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": png, "name": "x"})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"
    assert media_store.saved == []


def test_a_capture_over_its_size_limit_is_refused(client, project, samples, media_store, monkeypatch):
    png = samples.png()
    assert captures.MAX_CAPTURE_BYTES == 24 * 1024 * 1024
    assert captures.decode(samples.data_url(png), len(png) - 1) is None
    assert captures.decode(samples.data_url(png), len(png)) == png
    monkeypatch.setattr(captures, "MAX_CAPTURE_BYTES", 64)

    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(png)})

    assert (response.status_code, response.json()["detail"]["error"]) == (422, "invalid_request")
    assert media_store.saved == []


@pytest.fixture
def read_bodies(monkeypatch):
    from starlette.requests import Request

    calls = []
    original = Request.json

    async def json(self):
        calls.append(self.url.path)
        return await original(self)

    monkeypatch.setattr(Request, "json", json)
    return calls


def test_a_capture_over_the_body_limit_is_refused_before_its_body_is_read(client, project, samples, media_store, read_bodies, monkeypatch):
    monkeypatch.setattr(captures, "BODY_LIMIT", 100)

    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(samples.png())})

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "body_too_large"
    assert response.json()["detail"]["data"] == {"limit": 100}
    assert read_bodies == [] and media_store.saved == []


def test_a_capture_without_a_content_length_is_refused_before_its_body_is_read(client, project, read_bodies):
    headers = {"content-type": "application/json"}

    response = client.post(f"{BASE}/projects/{project['id']}/captures", content=iter([b'{"png": null}']), headers=headers)

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "body_too_large"
    assert read_bodies == []


def test_a_body_that_is_not_json_is_an_invalid_request(client, project):
    response = client.post(f"{BASE}/projects/{project['id']}/captures", content=b"png=1", headers={"content-type": "application/x-www-form-urlencoded"})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"


def test_a_capture_the_library_cannot_find_answers_store_failed(client, project, samples, monkeypatch):
    monkeypatch.setattr(core_bridge, "upload_item", lambda user_id, value: None)

    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(samples.png())})

    assert response.status_code == 502
    assert response.json()["detail"]["data"] == {"code": "store_failed"}


def test_the_render_routes_and_the_scene_file_upload_are_gone(client, project, samples):
    path = f"{BASE}/projects/{project['id']}"

    assert client.post(f"{path}/renders", json={"width": 64, "height": 36, "fps": 24, "frames": 3}).status_code in (404, 405)
    assert client.post(f"{path}/scene-files", content=b"x", headers={"content-length": "1"}).status_code in (404, 405)
