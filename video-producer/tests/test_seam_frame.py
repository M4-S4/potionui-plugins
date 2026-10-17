import pytest

from backend import core_bridge, takes
from backend.core_bridge import MediaRefError
from src.plugin_api import AccountType, get_current_active_user

BASE = "/api/plugins/video-producer"
SHOTS = [
    {"id": "s1", "start": 0, "dur": 4},
    {"id": "s2", "start": 4, "dur": 4},
    {"id": "s3", "start": 8, "dur": 4},
]


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


class Frames:
    def __init__(self):
        self.asked = []
        self.error = None

    async def extract_frame(self, user, ref, at="last"):
        self.asked.append((user.id, dict(ref), at))
        if self.error is not None:
            raise self.error
        label = "last" if at == "last" else f"{at:g}s"
        return {"value": "uploads/7d1e.png", "media_type": "image", "original_filename": f"1-frame-{label}.png", "origin": None}

    def upload_item(self, user_id, value):
        return {"item_id": f"item-{user_id}", "filename": "1-frame-last.png", "width": 832, "height": 480}


@pytest.fixture
def frames(core, monkeypatch):
    found = Frames()
    monkeypatch.setattr(core_bridge, "extract_frame", found.extract_frame)
    monkeypatch.setattr(core_bridge, "upload_item", found.upload_item)
    return found


def _take(project_id, shot_id, generation_id, status="done", created_at=None, file_id=None):
    take = takes.create_take(
        {
            "project_id": project_id,
            "shot_id": shot_id,
            "user_id": "user-1",
            "quality": "draft",
            "kind": "render",
            "status": status,
            "generation_id": generation_id,
            "file_id": file_id or (f"f-{generation_id}" if status == "done" else None),
            "file_path": f"generations/2026-10-17/{generation_id}/1.mp4" if status == "done" else None,
        }
    )
    if created_at:
        from src.plugin_api import db

        with db.get_cursor() as cursor:
            cursor.execute("UPDATE video_producer_takes SET created_at = ? WHERE id = ?", (created_at, take["id"]))
    return take


@pytest.fixture
def project(core, make_project):
    return make_project(clips=SHOTS)


def _seam(client, project_id, shot_id="s2", body=None):
    return client.post(f"{BASE}/projects/{project_id}/shots/{shot_id}/seam-frame", json=body)


def _chosen(project, shot_id, take_id):
    from backend import projects

    doc = projects.get_project(project["id"])["doc"]
    doc["clips"] = [{**clip, "take": take_id} if clip["id"] == shot_id else clip for clip in doc["clips"]]
    projects.save_project(project["id"], doc, projects.get_project(project["id"])["version"])


def test_the_default_is_the_last_frame_of_the_take_chosen_for_the_previous_shot(client, project, frames):
    chosen = _take(project["id"], "s1", "g-chosen", created_at="2026-10-17T08:00:00+00:00")
    _take(project["id"], "s1", "g-later", created_at="2026-10-17T09:00:00+00:00")
    _chosen(project, "s1", chosen["id"])

    response = _seam(client, project["id"])

    assert response.status_code == 200
    assert frames.asked == [("user-1", {"kind": "history", "generation_id": "g-chosen", "file_id": "f-g-chosen"}, "last")]
    assert response.json()["data"]["media"] == {
        "kind": "library",
        "item_id": "item-user-1",
        "media_type": "image",
        "url": "/api/media/uploads/7d1e.png",
        "filename": "1-frame-last.png",
        "width": 832,
        "height": 480,
        "origin": {"kind": "library", "itemId": "item-user-1"},
    }


def test_without_a_usable_chosen_take_the_latest_finished_take_of_the_previous_shot_is_used(client, project, frames):
    _take(project["id"], "s1", "g-old", created_at="2026-10-17T08:00:00+00:00")
    _take(project["id"], "s1", "g-new", created_at="2026-10-17T09:00:00+00:00")
    failed = _take(project["id"], "s1", "g-failed", status="failed", created_at="2026-10-17T10:00:00+00:00")
    _take(project["id"], "s3", "g-other-shot", created_at="2026-10-17T11:00:00+00:00")
    _chosen(project, "s1", failed["id"])

    response = _seam(client, project["id"], body={"source": "previous_last"})

    assert response.status_code == 200
    assert frames.asked[0][1]["generation_id"] == "g-new"


def test_an_explicit_take_and_time_extract_that_frame(client, project, frames):
    take = _take(project["id"], "s3", "g-3")

    seconds = _seam(client, project["id"], body={"source": {"take_id": take["id"], "at": 2.5}})
    last = _seam(client, project["id"], shot_id="s1", body={"source": {"take_id": take["id"], "at": "last"}})

    assert seconds.status_code == 200 and last.status_code == 200
    assert [(ref["generation_id"], at) for _, ref, at in frames.asked] == [("g-3", 2.5), ("g-3", "last")]
    assert seconds.json()["data"]["media"]["filename"] == "1-frame-2.5s.png"


def test_the_first_shot_has_no_previous_take(client, project, frames):
    response = _seam(client, project["id"], shot_id="s1")

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_previous_take"
    assert frames.asked == []


def test_a_previous_shot_without_a_finished_take_has_no_previous_take(client, project, frames):
    _take(project["id"], "s1", "g-running", status="running")

    response = _seam(client, project["id"])

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_previous_take"


def test_an_explicit_take_without_file_is_refused(client, project, frames):
    take = _take(project["id"], "s1", "g-q", status="queued")

    response = _seam(client, project["id"], body={"source": {"take_id": take["id"], "at": "last"}})

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_previous_take"


def test_an_unknown_shot_is_not_found(client, project, frames):
    response = _seam(client, project["id"], shot_id="nope")

    assert response.status_code == 404 and response.json()["detail"]["error"] == "shot_not_found"


def test_a_take_of_another_project_is_not_found(client, project, make_project, frames):
    other = make_project(clips=SHOTS)
    take = _take(other["id"], "s1", "g-x")

    response = _seam(client, project["id"], body={"source": {"take_id": take["id"], "at": "last"}})

    assert response.status_code == 404 and response.json()["detail"]["error"] == "take_not_found"


@pytest.mark.parametrize(
    "body",
    [
        {"source": "next_first"},
        {"source": {"take_id": "t"}},
        {"source": {"take_id": "t", "at": -1}},
        {"source": {"take_id": "t", "at": True}},
        {"source": {"take_id": "t", "at": "first"}},
        {"source": {"take_id": 3, "at": "last"}},
        {"source": {"take_id": "t", "at": "last", "extra": 1}},
        ["previous_last"],
    ],
)
def test_a_malformed_source_is_an_invalid_request(client, project, frames, body):
    response = _seam(client, project["id"], body=body)

    assert response.status_code == 422 and response.json()["detail"]["error"] == "invalid_request"


def test_a_frame_the_core_cannot_extract_answers_502_with_the_core_code(client, project, frames):
    _take(project["id"], "s1", "g-1")
    frames.error = MediaRefError("not_found", "The referenced media is not available")

    response = _seam(client, project["id"])

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert (detail["error"], detail["data"]) == ("extract_failed", {"code": "not_found"})


@pytest.mark.parametrize("item", [None, {}, {"item_id": None, "filename": "x.png"}])
def test_a_frame_whose_library_item_cannot_be_found_answers_502_store_failed(client, project, frames, monkeypatch, item):
    _take(project["id"], "s1", "g-1")
    monkeypatch.setattr(core_bridge, "upload_item", lambda user_id, value: item)

    response = _seam(client, project["id"])

    detail = response.json()["detail"]
    assert response.status_code == 502 and (detail["error"], detail["data"]) == ("extract_failed", {"code": "store_failed"})


def test_another_users_project_is_not_found(app, client, project, frames, make_user):
    _take(project["id"], "s1", "g-1")
    _as(app, make_user(user_id="user-2"))

    assert _seam(client, project["id"]).status_code == 404


def test_an_administrator_stores_the_frame_for_the_project_owner(app, client, project, frames, make_user):
    _take(project["id"], "s1", "g-1")
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    response = _seam(client, project["id"])

    assert response.status_code == 200
    assert frames.asked[0][0] == "user-1"
    assert response.json()["data"]["media"]["item_id"] == "item-user-1"


def test_the_seam_frame_leaves_the_document_alone(client, project, frames):
    from backend import projects

    _take(project["id"], "s1", "g-1")
    before = projects.get_project(project["id"])

    _seam(client, project["id"])

    after = projects.get_project(project["id"])
    assert (after["version"], after["doc"]) == (before["version"], before["doc"])
