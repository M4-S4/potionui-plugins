import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from backend import core_bridge
from backend.exports import video
from backend.scene3d import captures, renders, storage

BASE = "/api/plugins/video-producer"
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture
def project(core, make_project, export_storage, media_store, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    return make_project()


def _open(client, project, **fields):
    body = {"width": 64, "height": 36, "fps": 24, "frames": 3, "name": "Orbit guide", **fields}
    return client.post(f"{BASE}/projects/{project['id']}/renders", json=body)


def _send(client, project, render_id, start, images):
    return client.post(f"{BASE}/projects/{project['id']}/renders/{render_id}/frames", json={"start": start, "images": images})


def _frames(samples, count):
    return [samples.data_url(samples.jpeg(color=(40 * index, 80, 120)), "jpeg") for index in range(count)]


@pytest.fixture
def fake_encode(monkeypatch):
    runs = []

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        runs.append({"command": list(command), "total": total, "cwd": cwd, "code": code, "frames": sorted(path.name for path in Path(cwd).glob("*.jpg"))})
        (Path(cwd) / command[-1]).write_bytes(b"mp4 bytes")

    monkeypatch.setattr(video, "assemble", assemble)
    return runs


def test_a_render_opens_a_folder_that_receives_its_frames_in_batches(client, project, samples):
    response = _open(client, project)

    assert response.status_code == 201, response.text
    render = response.json()["data"]["render"]
    assert render == {"id": render["id"], "width": 64, "height": 36, "fps": 24.0, "frames": 3}
    folder = storage.renders_folder(project["id"]) / render["id"]
    assert json.loads((folder / "render.json").read_text(encoding="utf-8"))["user_id"] == "user-1"
    first = _send(client, project, render["id"], 0, _frames(samples, 2))
    assert first.json()["data"] == {"received": 2}
    assert _send(client, project, render["id"], 1, _frames(samples, 2)).json()["data"] == {"received": 3}
    assert sorted(path.name for path in folder.glob("*.jpg")) == ["000000.jpg", "000001.jpg", "000002.jpg"]
    assert list(folder.glob("*.part")) == []


def test_a_finished_render_is_encoded_into_an_h264_mp4_and_stored_in_the_owner_library(client, project, samples, media_store, fake_encode):
    render = _open(client, project).json()["data"]["render"]
    _send(client, project, render["id"], 0, _frames(samples, 3))

    response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish")

    assert response.status_code == 200, response.text
    media = response.json()["data"]["media"]
    assert media == {
        "kind": "library",
        "item_id": "item-1",
        "media_type": "video",
        "url": "/api/media/uploads/0001-Orbit_guide.mp4",
        "filename": "Orbit_guide.mp4",
        "width": 832,
        "height": 468,
        "fps": 24.0,
        "duration": 0.125,
        "origin": {"kind": "library", "itemId": "item-1"},
    }
    assert [(saved["user_id"], saved["name"], saved["data"]) for saved in media_store.saved] == [("user-1", "Orbit_guide.mp4", b"mp4 bytes")]
    (run,) = fake_encode
    assert run["command"] == [
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-f", "image2", "-framerate", "24", "-start_number", "0", "-i", "%06d.jpg",
        "-frames:v", "3", "-vf", "scale=64:36:flags=lanczos", "-r", "24",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", "Orbit_guide.mp4",
    ]
    assert (run["total"], run["code"], run["frames"]) == (0.125, "encode_failed", ["000000.jpg", "000001.jpg", "000002.jpg"])
    assert not (storage.renders_folder(project["id"]) / render["id"]).exists()
    assert client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish").json()["detail"]["error"] == "render_not_found"


def test_a_render_with_frames_still_missing_is_not_encoded(client, project, samples, fake_encode):
    render = _open(client, project, frames=4).json()["data"]["render"]
    _send(client, project, render["id"], 1, _frames(samples, 2))

    response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish")

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "frames_missing"
    assert response.json()["detail"]["data"] == {"missing": 2}
    assert fake_encode == []


def test_a_render_without_ffmpeg_or_whose_encoding_fails_answers_its_error_and_keeps_its_frames(client, project, samples, monkeypatch):
    render = _open(client, project, frames=1).json()["data"]["render"]
    _send(client, project, render["id"], 0, _frames(samples, 1))
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    assert client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish").json()["detail"]["error"] == "ffmpeg_unavailable"

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        raise video.ExportError(code, "Invalid data found when processing input")

    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(video, "assemble", assemble)
    response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish")
    assert response.status_code == 502
    assert response.json()["detail"] == {"success": False, "error": "encode_failed", "message": "Invalid data found when processing input"}
    assert (storage.renders_folder(project["id"]) / render["id"] / "000000.jpg").is_file()


def test_a_render_the_library_refuses_answers_store_failed(client, project, samples, fake_encode, monkeypatch):
    render = _open(client, project, frames=1).json()["data"]["render"]
    _send(client, project, render["id"], 0, _frames(samples, 1))

    async def save_user_media(user, path):
        raise core_bridge.MediaRefError("upload_rejected", "The file is too large")

    monkeypatch.setattr(core_bridge, "save_user_media", save_user_media)

    response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish")

    assert response.status_code == 502
    assert response.json()["detail"] == {"success": False, "error": "store_failed", "message": "The file is too large", "data": {"code": "upload_rejected"}}


@pytest.mark.parametrize(
    "fields",
    [{"width": 63}, {"height": 8}, {"width": 4098}, {"fps": 0}, {"fps": "24"}, {"fps": 121}, {"frames": 0}, {"frames": 7201}, {"frames": 2.5}, {"name": 4}, {"width": True}],
)
def test_a_render_outside_the_limits_is_an_invalid_request(client, project, fields):
    response = _open(client, project, **fields)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"
    assert storage.folders(storage.renders_folder(project["id"])) == []


def test_frames_that_are_not_jpeg_data_urls_or_end_past_the_render_are_refused(client, project, samples):
    render = _open(client, project).json()["data"]["render"]
    png = samples.data_url(samples.png(), "png")
    fake = "data:image/jpeg;base64," + "aGVsbG8="
    cases = [
        ({"start": 0, "images": [png]}, "images[0]"),
        ({"start": 0, "images": [_frames(samples, 1)[0], fake]}, "images[1]"),
        ({"start": 0, "images": ["data:image/jpeg;base64,***"]}, "images[0]"),
        ({"start": 2, "images": _frames(samples, 2)}, "ends past them"),
        ({"start": -1, "images": _frames(samples, 1)}, "start"),
        ({"start": 0, "images": []}, "images must be"),
        ({"start": 0}, "images must be"),
    ]
    for body, message in cases:
        response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/frames", json=body)
        assert response.status_code == 422, body
        assert message in response.json()["detail"]["message"], body
    assert list((storage.renders_folder(project["id"]) / render["id"]).glob("*.jpg")) == []


def test_a_render_is_reached_only_through_its_own_project_and_by_its_id(client, project, make_project, samples):
    other = make_project()
    render = _open(client, project).json()["data"]["render"]

    for path in (f"/projects/{other['id']}/renders/{render['id']}/finish", f"/projects/{project['id']}/renders/..%2Fwork/finish"):
        response = client.post(f"{BASE}{path}")
        assert response.status_code == 404
    assert _send(client, other, render["id"], 0, _frames(samples, 1)).json()["detail"]["error"] == "render_not_found"
    assert client.delete(f"{BASE}/projects/{other['id']}/renders/{render['id']}").status_code == 404


def test_deleting_a_render_stops_its_encoding_and_drops_its_frames(client, project, samples, monkeypatch):
    render = _open(client, project).json()["data"]["render"]
    _send(client, project, render["id"], 0, _frames(samples, 2))
    killed = []
    monkeypatch.setattr(renders, "kill", lambda render_id: killed.append(render_id) or False)

    response = client.delete(f"{BASE}/projects/{project['id']}/renders/{render['id']}")

    assert (response.status_code, response.json()["data"]) == (200, {})
    assert killed == [render["id"]]
    assert not (storage.renders_folder(project["id"]) / render["id"]).exists()
    assert client.delete(f"{BASE}/projects/{project['id']}/renders/{render['id']}").json()["detail"]["error"] == "render_not_found"


def test_the_startup_sweep_deletes_the_renders_and_work_files_left_for_more_than_a_day(client, project, make_project, samples):
    old = _open(client, project).json()["data"]["render"]
    fresh = _open(client, project).json()["data"]["render"]
    work = storage.work_folder(project["id"])
    work.mkdir(parents=True)
    (work / "upload-01M5OLDUPLOAD0000000000000").write_bytes(b"x")
    day_ago = time.time() - 25 * 3600
    for path in (storage.renders_folder(project["id"]) / old["id"], work / "upload-01M5OLDUPLOAD0000000000000"):
        os.utime(path, (day_ago, day_ago))
    scene_file = storage.project_folder(project["id"]) / "01M5SCENEFILE0000000000000.ply"
    scene_file.write_bytes(samples.ply())
    os.utime(scene_file, (day_ago, day_ago))

    assert renders.sweep() == 2

    assert [folder.name for folder in storage.folders(storage.renders_folder(project["id"]))] == [fresh["id"]]
    assert list(work.iterdir()) == [] and scene_file.is_file()


def test_the_sweep_ignores_a_storage_without_scenes(export_storage):
    assert renders.sweep() == 0


def test_on_ready_fails_the_splat_jobs_a_stop_left_and_sweeps_the_old_renders(core, client, project, scheduled, caplog):
    from hooks import lifecycle_hooks
    from backend.scene3d import jobs
    from src.plugin_api import HookContext

    jobs._insert({"id": "01M5JOBNEVERSTARTED0000000", "project_id": project["id"], "scene_id": "s", "user_id": "user-1", "status": "queued", "progress": 0, "units_reserved": 0, "created_at": storage.now()})
    old = _open(client, project).json()["data"]["render"]
    day_ago = time.time() - 25 * 3600
    os.utime(storage.renders_folder(project["id"]) / old["id"], (day_ago, day_ago))
    caplog.set_level("INFO", logger="plugins.video-producer")

    lifecycle_hooks.on_ready(HookContext(hook_name="plugin.lifecycle.ready", plugin_id="video-producer", data={}))

    assert jobs.get_job("01M5JOBNEVERSTARTED0000000")["status"] == "failed"
    assert storage.folders(storage.renders_folder(project["id"])) == []
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


def test_a_capture_over_40_mib_is_refused(project, samples, monkeypatch):
    monkeypatch.setattr(captures, "MAX_IMAGE_BYTES", 64)

    assert captures.decode(samples.data_url(samples.png()), "png") is None


def test_a_capture_the_library_cannot_find_answers_store_failed(client, project, samples, monkeypatch):
    monkeypatch.setattr(core_bridge, "upload_item", lambda user_id, value: None)

    response = client.post(f"{BASE}/projects/{project['id']}/captures", json={"png": samples.data_url(samples.png())})

    assert response.status_code == 502
    assert response.json()["detail"]["data"] == {"code": "store_failed"}


@pytest.mark.requires_ffmpeg
@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
def test_ffmpeg_encodes_the_frames_of_a_render_into_an_h264_yuv420p_mp4(client, project, samples, media_store, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: shutil.which("ffmpeg"))
    render = _open(client, project, width=64, height=36, frames=12).json()["data"]["render"]
    _send(client, project, render["id"], 0, _frames(samples, 12))

    response = client.post(f"{BASE}/projects/{project['id']}/renders/{render['id']}/finish")

    assert response.status_code == 200, response.text
    (saved,) = media_store.saved
    probe_dir = Path(storage.scenes_base()) / "probe"
    probe_dir.mkdir()
    out = probe_dir / saved["name"]
    out.write_bytes(saved["data"])
    probed = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
             "stream=codec_name,pix_fmt,width,height,nb_read_frames,r_frame_rate", "-of", "json", str(out)],
            capture_output=True, check=True, text=True,
        ).stdout
    )["streams"][0]
    assert probed == {"codec_name": "h264", "width": 64, "height": 36, "pix_fmt": "yuv420p", "r_frame_rate": "24/1", "nb_read_frames": "12"}
