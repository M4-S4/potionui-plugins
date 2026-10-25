import asyncio

import pytest

from backend import core_bridge, limits, tracker
from backend.scene3d import files, formats, jobs, storage

BASE = "/api/plugins/video-producer"
SPLAT_ID = "01KX47GSP4TQ0000000000SP3D"
ASSETS = [
    {"id": "still", "kind": "image", "name": "Still", "origin": {"kind": "library", "itemId": "lib-still"}},
    {"id": "take", "kind": "video", "name": "Take", "origin": {"kind": "history", "generationId": "g-v", "fileId": "7"}},
    {"id": "voice", "kind": "audio", "name": "Voice", "origin": {"kind": "library", "itemId": "lib-voice"}},
    {"id": "loose", "kind": "image", "name": "Loose", "origin": None},
]


@pytest.fixture
def scene(core, make_project, export_storage, monkeypatch):
    core.use_splat()
    core.add_media({"kind": "library", "item_id": "lib-still"}, "uploads/still.png", "image")
    core.add_media({"kind": "library", "item_id": "lib-voice"}, "uploads/voice.wav", "audio")
    extracted = []

    async def extract_frame(user, ref, at="last"):
        extracted.append((user.id, ref, at))
        return {"value": f"uploads/take-frame-{at:g}s.png", "media_type": "image", "original_filename": "take-frame.png", "origin": None}

    monkeypatch.setattr(core_bridge, "extract_frame", extract_frame)
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 4}], assets=ASSETS)
    return project, extracted


def _start(client, project, asset_id="still", time=None, scene_id="sc-1"):
    return client.post(f"{BASE}/projects/{project['id']}/scenes/from-image", json={"sceneId": scene_id, "assetId": asset_id, "time": time, "name": "Ridge"})


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _ply_source(tmp_path, samples, monkeypatch, data=None, into_folder=False):
    source = tmp_path / "generated.ply"
    source.write_bytes(samples.ply(count=6) if data is None else data)
    asked = []

    def local_media_file(kind, value, folder):
        asked.append((kind, value))
        if into_folder:
            copy = folder / f"{core_bridge.SOURCE_PREFIX}{value.replace('/', '_')}"
            copy.write_bytes(source.read_bytes())
            return copy
        return source

    monkeypatch.setattr(core_bridge, "local_media_file", local_media_file)
    return source, asked


def test_an_image_asset_is_sent_as_it_is_to_the_splat_preset_with_its_models_and_one_reserved_minute(client, core, scene):
    project, extracted = scene

    response = _start(client, project)

    assert response.status_code == 202, response.text
    job = response.json()["data"]["job"]
    assert job == {
        "id": job["id"],
        "sceneId": "sc-1",
        "status": "queued",
        "progress": 0.0,
        "error": None,
        "errorCode": None,
        "fileId": None,
        "count": None,
        "view": None,
        "generationId": "gen-1",
        "createdAt": job["createdAt"],
        "finishedAt": None,
    }
    assert extracted == []
    assert core.submitted == [
        (
            "user-1",
            {
                "preset_id": SPLAT_ID,
                "mode": "img2splat",
                "prompts": [{"positive": "", "negative": ""}],
                "form_data": {"source_image": "uploads/still.png", "depth_model": "model:id-moge-sha", "seed": -1},
                "idempotency_key": f"vp-scene:{job['id']}",
            },
        )
    ]
    assert core.recorded == [("user-1", limits.GPU_MINUTES, 1.0, f"video-producer:scene:{job['id']}")]
    assert jobs.get_job(job["id"])["units_reserved"] == 1.0


def test_a_video_asset_gives_its_frame_at_the_time_asked_for(client, core, scene):
    project, extracted = scene

    job = _start(client, project, asset_id="take", time=2.5).json()["data"]["job"]

    assert extracted == [("user-1", {"kind": "history", "generation_id": "g-v", "file_id": "7"}, 2.5)]
    assert core.submitted[0][1]["form_data"]["source_image"] == "uploads/take-frame-2.5s.png"
    stored = jobs.get_job(job["id"])
    assert (stored["source_asset_id"], stored["source_time"], stored["source_value"]) == ("take", 2.5, "uploads/take-frame-2.5s.png")


@pytest.mark.parametrize(
    "asset_id, time, status, error",
    [
        ("take", None, 422, "invalid_request"),
        ("voice", None, 422, "invalid_source"),
        ("loose", None, 422, "invalid_source"),
        ("nowhere", None, 404, "asset_not_found"),
    ],
)
def test_a_source_that_is_not_an_image_or_a_timed_video_is_refused_before_anything_is_reserved(client, core, scene, asset_id, time, status, error):
    project, _ = scene

    response = _start(client, project, asset_id=asset_id, time=time)

    assert response.status_code == status
    assert response.json()["detail"]["error"] == error
    assert (core.submitted, core.recorded, jobs.list_project(project["id"])) == ([], [], [])


def test_an_image_that_is_gone_from_the_library_is_not_found(client, core, scene):
    project, _ = scene
    core.media.clear()

    assert _start(client, project).json()["detail"]["error"] == "media_not_found"


def test_a_frame_that_cannot_be_extracted_answers_502(client, core, scene, monkeypatch):
    project, _ = scene

    async def extract_frame(user, ref, at="last"):
        raise core_bridge.MediaRefError("extract_failed", "The video's frame rate could not be read")

    monkeypatch.setattr(core_bridge, "extract_frame", extract_frame)

    response = _start(client, project, asset_id="take", time=1)

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "extract_failed"
    assert core.submitted == []


@pytest.mark.parametrize("body", [{"assetId": "still"}, {"sceneId": "", "assetId": "still"}, {"sceneId": "s", "assetId": "still", "time": -1}, {"sceneId": "s", "assetId": "still", "time": "2"}, {"sceneId": "s", "assetId": "still", "name": 3}, []])
def test_a_malformed_from_image_body_is_an_invalid_request(client, core, scene, body):
    project, _ = scene

    response = client.post(f"{BASE}/projects/{project['id']}/scenes/from-image", json=body)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"


def test_without_the_splat_preset_the_scene_is_blocked(client, core, scene):
    project, extracted = scene
    del core.descriptions[SPLAT_ID]

    response = _start(client, project, asset_id="take", time=1)

    assert response.status_code == 409
    assert response.json()["detail"]["data"]["blocks"] == [
        {"code": "no_preset", "message": "The Image to Splat preset is not available to you.", "data": {"preset_id": SPLAT_ID}}
    ]
    assert (extracted, core.submitted, core.recorded) == ([], [], [])


def test_a_missing_model_of_the_splat_preset_blocks_with_its_field(client, core, scene):
    project, _ = scene
    core.missing = {"moge-sha"}

    blocks = _start(client, project).json()["detail"]["data"]["blocks"]

    assert blocks == [{"code": "missing_models", "message": "Install a recommended file for: depth_model.", "data": {"fields": ["depth_model"]}}]


def test_a_user_with_less_than_a_minute_left_is_blocked_and_an_exempt_user_reserves_nothing(client, core, scene):
    project, _ = scene
    core.quota = {"limit": 60, "used": 59.5, "remaining": 0.5, "exempt": False, "resets_at": None}

    blocked = _start(client, project).json()["detail"]["data"]["blocks"]

    assert [block["code"] for block in blocked] == ["quota_exceeded"]
    core.quota = {"limit": 60, "used": 60, "remaining": 0, "exempt": True, "resets_at": None}
    assert _start(client, project).status_code == 202
    assert core.recorded == []


def test_a_scene_is_refused_before_anything_is_reserved_when_the_owner_has_no_storage_left(client, core, scene):
    project, _ = scene
    core.quotas["storage_bytes"] = {"limit": 1000, "used": 1000, "remaining": 0, "exempt": False, "resets_at": None}

    response = _start(client, project)

    assert (response.status_code, response.json()["detail"]["error"]) == (413, "storage_full")
    assert (core.submitted, core.recorded, jobs.list_project(project["id"])) == ([], [], [])


def test_a_finished_splat_that_does_not_fit_the_storage_plan_fails_the_job_and_refunds_it(client, core, scene, tmp_path, samples, monkeypatch):
    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch)
    job = _start(client, project).json()["data"]["job"]
    core.quotas["storage_bytes"] = {"limit": 1000, "used": 990, "remaining": 10, "exempt": False, "resets_at": None}
    core.complete_splat("gen-1")

    _tick()

    failed = jobs.get_job(job["id"])
    assert (failed["status"], failed["error_code"]) == ("failed", "storage_full")
    assert core.refunded == [f"video-producer:scene:{job['id']}"]
    assert files.list_project(project["id"]) == []
    folder = storage.project_folder(project["id"])
    assert [path for path in folder.rglob("*") if path.is_file()] == []


def test_a_request_the_core_refuses_gives_a_failed_job_and_refunds_its_minute(client, core, scene):
    project, _ = scene
    core.refusal = PermissionError("not assigned")

    job = _start(client, project).json()["data"]["job"]

    assert (job["status"], job["errorCode"], job["error"]) == ("failed", "preset_not_available", "The preset is not available to you.")
    assert core.refunded == [f"video-producer:scene:{job['id']}"]


def test_the_tracker_reports_the_progress_of_a_running_splat(client, core, scene):
    project, _ = scene
    job = _start(client, project).json()["data"]["job"]
    core.states["gen-1"].update(status="running", progress=0.42, backend_id="b-local")

    assert _tick() is True

    listed = client.get(f"{BASE}/projects/{project['id']}/scenes/jobs").json()["data"]["jobs"]
    assert [(item["id"], item["status"], item["progress"]) for item in listed] == [(job["id"], "running", 42.0)]
    assert jobs.get_job(job["id"])["backend_id"] == "b-local"


def test_a_finished_splat_is_copied_to_the_scene_storage_with_its_count_and_view_and_its_minutes_adjusted(client, core, scene, tmp_path, samples, monkeypatch, export_storage):
    project, _ = scene
    source, asked = _ply_source(tmp_path, samples, monkeypatch)
    job = _start(client, project).json()["data"]["job"]
    core.complete_splat("gen-1", duration_ms=30000)

    assert _tick() is False

    done = client.get(f"{BASE}/projects/{project['id']}/scenes/jobs").json()["data"]["jobs"][0]
    assert (done["status"], done["progress"], done["count"], done["error"]) == ("done", 100.0, 6, None)
    assert done["view"] == {"fov": 48.5, "aspect": 1.7778, "depth": 4.0}
    assert asked == [("history", "generations/2026-10-19/gen-1/scene.ply")]
    stored = files.get_file(done["fileId"])
    assert (stored["kind"], stored["format"], stored["job_id"], stored["user_id"], stored["splat_count"]) == ("splat", "ply", job["id"], "user-1", 6)
    path = export_storage / "video_producer" / "scenes" / project["id"] / f"{done['fileId']}.ply"
    assert path.read_bytes() == source.read_bytes() and source.exists()
    assert client.get(f"{BASE}/projects/{project['id']}/scene-files/{done['fileId']}").content == source.read_bytes()
    ref = f"video-producer:scene:{job['id']}"
    assert core.refunded == [ref]
    assert core.recorded[-1] == ("user-1", limits.GPU_MINUTES, 0.5, f"{ref}:actual")


def test_a_splat_longer_than_its_reservation_records_the_extra_minutes(client, core, scene, tmp_path, samples, monkeypatch):
    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch)
    job = _start(client, project).json()["data"]["job"]
    core.complete_splat("gen-1", duration_ms=90000, splat_count=1234)

    _tick()

    assert jobs.get_job(job["id"])["splat_count"] == 1234
    assert core.recorded[-1] == ("user-1", limits.GPU_MINUTES, 0.5, f"video-producer:scene:{job['id']}:adjust")
    assert core.refunded == []


def test_a_splat_streamed_from_object_storage_is_moved_into_place(client, core, scene, tmp_path, samples, monkeypatch):
    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch, into_folder=True)
    _start(client, project)
    core.complete_splat("gen-1")

    _tick()

    folder = storage.project_folder(project["id"])
    (job,) = jobs.list_project(project["id"])
    assert sorted(path.name for path in folder.rglob("*") if path.is_file()) == [f"{job['file_id']}.ply"]


@pytest.mark.parametrize(
    "files_of, data, code",
    [
        (lambda core: core.files.update({"gen-1": [{"id": "f", "file_type": "IMAGE", "file_path": "generations/x/0.png"}]}), None, "no_output"),
        (lambda core: None, b"ply\nformat ascii 1.0\nend_header\n", "invalid_output"),
    ],
)
def test_a_generation_without_a_readable_splat_fails_the_job_and_refunds_it(client, core, scene, tmp_path, samples, monkeypatch, files_of, data, code):
    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch, data=data)
    job = _start(client, project).json()["data"]["job"]
    core.complete_splat("gen-1")
    files_of(core)

    _tick()

    failed = jobs.get_job(job["id"])
    assert (failed["status"], failed["error_code"]) == ("failed", code)
    assert core.refunded == [f"video-producer:scene:{job['id']}"]
    assert files.list_project(project["id"]) == []
    folder = storage.project_folder(project["id"])
    assert not folder.exists() or [path.name for path in folder.rglob("*") if path.is_file()] == []


def test_the_splat_is_checked_in_the_work_folder_and_appears_in_place_only_once_whole(client, core, scene, tmp_path, samples, monkeypatch):
    from backend.scene3d import formats

    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch)
    _start(client, project)
    core.complete_splat("gen-1")
    probed = []
    probe = formats.probe

    def spy(fmt, path):
        probed.append((path.parent.name, path.name, sorted(entry.name for entry in storage.project_folder(project["id"]).iterdir() if entry.is_file())))
        return probe(fmt, path)

    monkeypatch.setattr(formats, "probe", spy)

    _tick()

    (job,) = jobs.list_project(project["id"])
    assert probed == [("work", f"copy-{job['file_id']}.ply", [])]
    assert files.path_of(files.get_file(job["file_id"])).is_file()
    assert list(storage.work_folder(project["id"]).iterdir()) == []


def test_a_finish_that_keeps_failing_ends_the_job_failed_and_refunded_after_three_rounds(client, core, scene, tmp_path, samples, monkeypatch, caplog):
    project, _ = scene
    _ply_source(tmp_path, samples, monkeypatch)
    job = _start(client, project).json()["data"]["job"]
    core.complete_splat("gen-1")
    rounds = []

    def add_file(*args, **kwargs):
        rounds.append(args[0])
        raise RuntimeError("database is locked")

    monkeypatch.setattr(files, "add_file", add_file)

    assert _tick() is True
    assert _tick() is True
    assert jobs.get_job(job["id"])["status"] == "queued" and core.refunded == []
    assert _tick() is False

    failed = jobs.get_job(job["id"])
    assert (failed["status"], failed["error_code"]) == ("failed", "finish_failed")
    assert len(rounds) == jobs.FINISH_ATTEMPTS == 3
    assert core.refunded == [f"video-producer:scene:{job['id']}"]
    assert [path for path in storage.project_folder(project["id"]).rglob("*") if path.is_file()] == []
    assert jobs._FINISH_FAILURES == {}
    assert "could not be finished in 3 attempts" in caplog.text


def test_a_user_builds_at_most_two_scenes_at_once(client, core, scene, make_project):
    project, _ = scene
    first = _start(client, project).json()["data"]["job"]
    _start(client, make_project(assets=ASSETS), scene_id="sc-2")

    refused = _start(client, project, scene_id="sc-3")

    assert (refused.status_code, refused.json()["detail"]["error"]) == (409, "scene_jobs_busy")
    assert refused.json()["detail"]["data"] == {"limit": 2}
    assert len(core.submitted) == 2 and len(core.recorded) == 2
    client.post(f"{BASE}/projects/{project['id']}/scenes/jobs/{first['id']}/cancel")
    assert _start(client, project, scene_id="sc-3").status_code == 202


def test_a_splat_file_the_server_cannot_reach_fails_the_job(client, core, scene, monkeypatch):
    project, _ = scene
    monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, folder: None)
    job = _start(client, project).json()["data"]["job"]
    core.complete_splat("gen-1")

    _tick()

    assert jobs.get_job(job["id"])["error_code"] == "output_missing"


def test_a_failed_splat_generation_fails_the_job_with_the_core_message_and_refunds_it(client, core, scene):
    project, _ = scene
    job = _start(client, project).json()["data"]["job"]
    core.fail("gen-1", code="cuda_oom", message="The GPU ran out of memory.")

    _tick()

    listed = client.get(f"{BASE}/projects/{project['id']}/scenes/jobs").json()["data"]["jobs"][0]
    assert (listed["status"], listed["errorCode"], listed["error"]) == ("failed", "cuda_oom", "The GPU ran out of memory.")
    assert core.refunded == [f"video-producer:scene:{job['id']}"]


def test_a_splat_generation_the_core_lost_or_whose_owner_is_gone_fails_the_job(client, core, scene):
    project, _ = scene
    first = _start(client, project).json()["data"]["job"]
    del core.states["gen-1"]

    _tick()

    assert jobs.get_job(first["id"])["error_code"] == "generation_not_found"
    second = _start(client, project).json()["data"]["job"]
    del core.users["user-1"]
    _tick()
    assert jobs.get_job(second["id"])["error_code"] == "user_not_found"


def test_cancelling_a_splat_job_cancels_its_generation_and_refunds_it(client, core, scene):
    project, _ = scene
    job = _start(client, project).json()["data"]["job"]

    response = client.post(f"{BASE}/projects/{project['id']}/scenes/jobs/{job['id']}/cancel")

    cancelled = response.json()["data"]["job"]
    assert (cancelled["status"], cancelled["errorCode"]) == ("cancelled", "cancelled")
    assert core.cancelled == [("user-1", "gen-1")]
    assert core.refunded == [f"video-producer:scene:{job['id']}"]
    again = client.post(f"{BASE}/projects/{project['id']}/scenes/jobs/{job['id']}/cancel").json()["data"]["job"]
    assert again["status"] == "cancelled" and core.refunded == [f"video-producer:scene:{job['id']}"]


def test_a_splat_job_is_cancelled_only_through_its_own_project(client, core, scene, make_project):
    project, _ = scene
    other = make_project()
    job = _start(client, project).json()["data"]["job"]

    response = client.post(f"{BASE}/projects/{other['id']}/scenes/jobs/{job['id']}/cancel")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "job_not_found"
    assert jobs.get_job(job["id"])["status"] == "queued"


def test_an_admin_starts_a_splat_as_the_owner_of_the_project(app, client, core, scene, make_user):
    from src.plugin_api import AccountType, get_current_active_user

    project, _ = scene
    app.dependency_overrides[get_current_active_user] = lambda: make_user(AccountType.ADMIN, user_id="admin-1")

    job = _start(client, project).json()["data"]["job"]

    assert core.submitted[0][0] == "user-1"
    assert jobs.get_job(job["id"])["user_id"] == "user-1"


def test_at_startup_a_job_the_core_never_took_fails_and_is_refunded(core, scene):
    project, _ = scene
    jobs._insert({"id": "01M5JOBNEVERSTARTED0000000", "project_id": project["id"], "scene_id": "s", "user_id": "user-1", "status": "queued", "progress": 0, "units_reserved": 1.0, "created_at": storage.now()})

    assert jobs.recover() == 1

    assert jobs.get_job("01M5JOBNEVERSTARTED0000000")["error_code"] == "submit_failed"
    assert core.refunded == ["video-producer:scene:01M5JOBNEVERSTARTED0000000"]


def test_deleting_a_project_cancels_its_splat_jobs_and_deletes_its_scene_files_and_folder(client, core, scene, samples, export_storage):
    project, _ = scene
    job = _start(client, project).json()["data"]["job"]
    folder = storage.project_folder(project["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / files.stored_name("01M5STOREDFILE000000000000", "ply")).write_bytes(samples.ply())
    files.add_file("01M5STOREDFILE000000000000", project["id"], "user-1", "splat", "a.ply", len(samples.ply()), formats.Probe(format="ply", count=2))

    assert client.delete(f"{BASE}/projects/{project['id']}").status_code == 200

    assert core.cancelled == [("user-1", "gen-1")]
    assert core.refunded == [f"video-producer:scene:{job['id']}"]
    assert jobs.get_job(job["id"]) is None and jobs.list_project(project["id"]) == []
    assert files.list_project(project["id"]) == []
    assert not (export_storage / "video_producer" / "scenes" / project["id"]).exists()


def test_an_admin_deleting_a_project_cancels_its_splat_jobs_as_the_owner(app, client, core, scene, make_user):
    from src.plugin_api import AccountType, get_current_active_user

    project, _ = scene
    job = _start(client, project).json()["data"]["job"]
    app.dependency_overrides[get_current_active_user] = lambda: make_user(AccountType.ADMIN, user_id="admin-1")

    assert client.delete(f"{BASE}/projects/{project['id']}").status_code == 200

    assert core.cancelled == [("user-1", "gen-1")]
    assert jobs.get_job(job["id"]) is None
