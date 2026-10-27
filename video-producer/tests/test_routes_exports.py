import json
from pathlib import Path

import pytest

from backend import core_bridge, takes
from backend.exports import jobs, video
from src.plugin_api import AccountType, get_current_active_user

BASE = "/api/plugins/video-producer"
FOLDER = Path(__file__).resolve().parent / "fixtures" / "exports"
STORAGE = "/srv/storage"
TYPES = {
    "fcpxml": "application/xml",
    "otio": "application/json",
    "edl": "text/plain; charset=utf-8",
    "srt": "application/x-subrip",
}
TAKE_FIELDS = ("shot_id", "generation_id", "file_id", "file_path", "status", "quality", "kind", "chosen")


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


@pytest.fixture
def reference():
    return json.loads((FOLDER / "reference-project.json").read_text(encoding="utf-8"))


@pytest.fixture
def host(core, export_storage, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(core_bridge, "media_file_path", lambda kind, value: f"{STORAGE}/{value}")
    return core


@pytest.fixture
def project(host, make_project, reference):
    created = make_project(doc=reference["doc"])
    for take in reference["takes"]:
        takes.create_take({**{key: take[key] for key in TAKE_FIELDS}, "project_id": created["id"], "user_id": "user-1"})
    for upload in reference["uploads"]:
        host.add_media({"kind": "library", "item_id": upload["item_id"]}, upload["value"], media_type=upload["media_type"])
    return created


@pytest.mark.parametrize("fmt", ["fcpxml", "otio", "edl", "srt"])
def test_an_exchange_export_by_name_is_the_golden_file_as_an_attachment(client, project, fmt):
    response = client.get(f"{BASE}/projects/{project['id']}/exports/{fmt}", params={"media": "name"})

    assert response.status_code == 200
    assert response.headers["content-type"] == TYPES[fmt]
    assert response.headers["content-disposition"] == (
        f"attachment; filename=\"Aube_maree.{fmt}\"; filename*=UTF-8''Aube_%26_mar%C3%A9e.{fmt}"
    )
    assert response.content == (FOLDER / f"reference.{fmt}").read_bytes()


def test_an_exchange_export_names_the_real_paths_on_the_server_by_default(client, project, reference):
    response = client.get(f"{BASE}/projects/{project['id']}/exports/edl")

    sources = [line for line in response.text.split("\r\n") if line.startswith("* SOURCE FILE: ")]
    assert sources == [
        f"* SOURCE FILE: {STORAGE}/{reference['takes'][1]['file_path']}",
        f"* SOURCE FILE: {STORAGE}/{reference['takes'][2]['file_path']}",
        f"* SOURCE FILE: {STORAGE}/{reference['uploads'][0]['value']}",
    ]
    xml = client.get(f"{BASE}/projects/{project['id']}/exports/fcpxml", params={"media": "path"}).text
    assert f'src="file://{STORAGE}/uploads/03927418-58f2-440f-9a15-456093037531.mp4"' in xml


@pytest.mark.parametrize("fmt, media", [("video", "path"), ("mov", "path"), ("edl", "url"), ("FCPXML", "name")])
def test_an_unknown_format_or_media_mode_is_an_invalid_request(client, project, fmt, media):
    response = client.get(f"{BASE}/projects/{project['id']}/exports/{fmt}", params={"media": media})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"


def test_the_exchange_exports_of_another_users_project_are_not_found(app, client, project, make_user):
    _as(app, make_user(user_id="user-2"))

    response = client.get(f"{BASE}/projects/{project['id']}/exports/edl")

    assert response.status_code == 404 and response.json()["detail"]["error"] == "project_not_found"
    assert client.get(f"{BASE}/projects/nope/exports/srt").status_code == 404


def test_an_administrator_exports_another_users_project_with_the_owners_media(app, client, project, host, make_user, monkeypatch):
    asked = []
    resolve = host.resolve_media
    monkeypatch.setattr(core_bridge, "resolve_media", lambda user, ref: asked.append(user.id) or resolve(user, ref))
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    response = client.get(f"{BASE}/projects/{project['id']}/exports/otio", params={"media": "name"})

    assert response.status_code == 200 and set(asked) == {"user-1"}


def test_the_srt_holds_the_titles_alone_whatever_the_users_locale(client, project, store):
    store[("locale", "user-1")] = "fr"

    response = client.get(f"{BASE}/projects/{project['id']}/exports/srt")

    assert response.status_code == 200
    assert "Fin" in response.text and "Marin" not in response.text


def _start(client, project_id, **body):
    return client.post(f"{BASE}/projects/{project_id}/exports/video", json={"format": "web", **body})


def test_a_video_export_is_queued_and_answers_202_with_its_job(client, project, host):
    response = _start(client, project["id"])

    assert response.status_code == 202
    job = response.json()["data"]["job"]
    assert {key: job[key] for key in ("project_id", "format", "resolution", "status", "progress", "step", "file", "media", "error")} == {
        "project_id": project["id"],
        "format": "web",
        "resolution": "1080p",
        "status": "queued",
        "progress": 0,
        "step": None,
        "file": None,
        "media": None,
        "error": None,
    }
    assert [coroutine.__qualname__ for coroutine in host.scheduled] == ["Runner.run"]
    assert jobs.get_job(job["id"])["user_id"] == "user-1"


def test_a_social_export_takes_the_resolution_asked_for(client, project):
    job = _start(client, project["id"], format="social", resolution="720p").json()["data"]["job"]

    assert (job["format"], job["resolution"]) == ("social", "720p")


@pytest.mark.parametrize(
    "body",
    [{"format": "master"}, {"format": "archive"}, {"format": "web", "resolution": "8K"}, {"resolution": "720p"}, ["web"]],
)
def test_a_format_other_than_web_or_social_is_an_invalid_request(client, project, body):
    response = client.post(f"{BASE}/projects/{project['id']}/exports/video", json=body)

    assert response.status_code == 422 and response.json()["detail"]["error"] == "invalid_request"


@pytest.mark.parametrize("fmt", ["fcpxml", "otio", "edl", "video"])
def test_a_document_whose_times_cannot_be_counted_is_an_invalid_doc_and_queues_nothing(client, host, make_project, reference, fmt):
    broken = make_project(doc={**reference["doc"], "fps": 0})

    if fmt == "video":
        response = _start(client, broken["id"])
    else:
        response = client.get(f"{BASE}/projects/{broken['id']}/exports/{fmt}")

    assert response.status_code == 422
    assert response.json()["detail"] == {"success": False, "error": "invalid_doc", "message": "$.fps: must be a positive number of frames per second"}
    assert jobs.list_project(broken["id"]) == []


def test_the_subtitles_of_a_document_without_a_frame_rate_still_export(client, host, make_project, reference):
    broken = make_project(doc={**reference["doc"], "fps": 0})

    response = client.get(f"{BASE}/projects/{broken['id']}/exports/srt")

    assert response.status_code == 200 and response.content == (FOLDER / "reference.srt").read_bytes()


def test_a_video_export_without_ffmpeg_is_refused(client, project, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    response = _start(client, project["id"])

    assert response.status_code == 409 and response.json()["detail"]["error"] == "ffmpeg_unavailable"


def test_a_video_export_of_a_sequence_without_any_file_is_refused(client, host, make_project, make_doc):
    empty = make_project(doc=make_doc(clips=[{"id": "c1"}]))

    response = _start(client, empty["id"])

    assert response.status_code == 409 and response.json()["detail"]["error"] == "nothing_to_export"


def test_a_second_export_of_the_same_project_is_refused_while_the_first_runs(client, project):
    first = _start(client, project["id"])

    second = _start(client, project["id"], format="social")

    assert first.status_code == 202
    assert second.status_code == 409 and second.json()["detail"]["error"] == "export_running"


def test_a_video_export_is_refused_when_the_cache_cannot_get_under_the_quota(client, project, store, make_project, reference):
    store[("export_dir_quota_mb", None)] = "1"
    other = make_project(doc=reference["doc"])
    running = jobs.create_job(other["id"], "user-1", "web", "720p")
    folder = video.job_folder(running)
    folder.mkdir(parents=True)
    (folder / "mezzanine.mp4").write_bytes(b"\0" * (2 * 1024 * 1024))

    response = _start(client, project["id"])

    assert response.status_code == 429
    assert response.json()["detail"]["error"] == "export_quota"
    assert response.json()["detail"]["data"] == {"quota_mb": 1}


def test_finished_exports_are_evicted_to_make_room_for_a_new_one(client, project, store, make_project, reference):
    store[("export_dir_quota_mb", None)] = "1"
    other = make_project(doc=reference["doc"])
    old = jobs.create_job(other["id"], "user-1", "web", "720p")
    jobs.settle(old["id"], "done", file_name="old.mp4", file_size=1)
    video.job_folder(old).mkdir(parents=True)
    (video.job_folder(old) / "old.mp4").write_bytes(b"\0" * (2 * 1024 * 1024))

    response = _start(client, project["id"])

    assert response.status_code == 202
    assert jobs.get_job(old["id"]) is None and not video.job_folder(old).exists()


def _done(job_id, size=11):
    job = jobs.get_job(job_id)
    folder = video.job_folder(job)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Aube_maree_1080p.mp4").write_bytes(b"x" * size)
    jobs.claim_next()
    jobs.settle(job_id, "done", progress=100.0, step=None, file_name="Aube_maree_1080p.mp4", file_size=size, media_item_id="item-1", media_url="/api/media/uploads/u.mp4")


def test_a_job_is_read_by_its_owner_and_an_administrator_only(app, client, project, make_user):
    job = _start(client, project["id"]).json()["data"]["job"]

    mine = client.get(f"{BASE}/exports/{job['id']}")
    _as(app, make_user(user_id="user-2"))
    foreign = client.get(f"{BASE}/exports/{job['id']}")
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))
    admin = client.get(f"{BASE}/exports/{job['id']}")

    assert mine.status_code == 200 and mine.json()["data"]["job"]["id"] == job["id"]
    assert foreign.status_code == 404 and foreign.json()["detail"]["error"] == "job_not_found"
    assert admin.status_code == 200
    assert client.get(f"{BASE}/exports/nope").status_code == 404


def test_the_file_of_a_job_is_not_ready_until_it_is_done_then_downloads_as_an_attachment(client, project):
    job = _start(client, project["id"]).json()["data"]["job"]

    early = client.get(f"{BASE}/exports/{job['id']}/file")
    _done(job["id"])
    response = client.get(f"{BASE}/exports/{job['id']}/file")

    assert early.status_code == 409 and early.json()["detail"]["error"] == "not_ready"
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"] == (
        "attachment; filename=\"Aube_maree_1080p.mp4\"; filename*=UTF-8''Aube_%26_mar%C3%A9e_1080p.mp4"
    )
    assert response.content == b"x" * 11
    done = client.get(f"{BASE}/exports/{job['id']}").json()["data"]["job"]
    assert done["file"] == {"name": "Aube_maree_1080p.mp4", "size": 11, "url": f"{BASE}/exports/{job['id']}/file"}
    assert done["media"] == {"kind": "library", "item_id": "item-1", "url": "/api/media/uploads/u.mp4"}


def test_deleting_a_queued_job_cancels_it_and_deleting_it_again_removes_it(client, project):
    job = _start(client, project["id"]).json()["data"]["job"]

    cancelled = client.delete(f"{BASE}/exports/{job['id']}")
    deleted = client.delete(f"{BASE}/exports/{job['id']}")

    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["job"]["status"] == "cancelled"
    assert cancelled.json()["data"]["job"]["error"]["code"] == "cancelled"
    assert deleted.json() == {"success": True, "data": {"deleted": job["id"]}}
    assert client.get(f"{BASE}/exports/{job['id']}").status_code == 404
    assert _start(client, project["id"]).status_code == 202


def test_deleting_a_done_job_removes_its_folder(client, project):
    job = _start(client, project["id"]).json()["data"]["job"]
    _done(job["id"])
    folder = video.job_folder(jobs.get_job(job["id"]))

    response = client.delete(f"{BASE}/exports/{job['id']}")

    assert response.json()["data"] == {"deleted": job["id"]} and not folder.exists()


def test_the_exports_of_a_project_are_listed_newest_first(client, project):
    first = _start(client, project["id"]).json()["data"]["job"]
    client.delete(f"{BASE}/exports/{first['id']}")
    second = _start(client, project["id"], format="social").json()["data"]["job"]

    response = client.get(f"{BASE}/projects/{project['id']}/exports")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()["data"]["jobs"]] == [second["id"], first["id"]]
    assert client.get(f"{BASE}/projects/nope/exports").status_code == 404


def test_deleting_a_project_deletes_its_exports(client, project):
    job = _start(client, project["id"]).json()["data"]["job"]
    _done(job["id"])
    folder = video.job_folder(jobs.get_job(job["id"]))

    assert client.delete(f"{BASE}/projects/{project['id']}").status_code == 200

    assert jobs.get_job(job["id"]) is None and not folder.exists()


@pytest.mark.parametrize("found, expected", [("/usr/bin/ffmpeg", True), (None, False)])
def test_me_tells_whether_ffmpeg_is_on_the_server(client, store, no_container, monkeypatch, found, expected):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: found)

    assert client.get(f"{BASE}/me").json()["data"]["ffmpeg"] is expected


def test_me_says_no_ffmpeg_when_it_cannot_look_for_it(client, store, no_container, monkeypatch):
    def broken():
        raise RuntimeError("which failed")

    monkeypatch.setattr(core_bridge, "find_ffmpeg", broken)

    assert client.get(f"{BASE}/me").json()["data"]["ffmpeg"] is False
