import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import projects
from src.plugin_api import AccountType, get_current_active_user

BASE = "/api/plugins/video-producer"
PROJECTS_URL = f"{BASE}/projects"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    return _fixture("starter_doc")


@pytest.fixture
def api(project_db, store, clock, client):
    return client


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _create(client, doc, **body):
    response = client.post(PROJECTS_URL, json={"doc": doc, **body})
    assert response.status_code == 201, response.text
    return response.json()["data"]["project"]


def _url(project_id, *parts):
    return "/".join([PROJECTS_URL, project_id, *[str(part) for part in parts]])


def _save(client, project_id, doc, version, **body):
    return client.put(_url(project_id), json={"doc": doc, "version": version, **body})


def _renamed(doc, name):
    return {**copy.deepcopy(doc), "name": name}


def _rows(db, table, project_id):
    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT * FROM {table} WHERE project_id = ? ORDER BY version", (project_id,))
        return [dict(row) for row in cursor.fetchall()]


def _count(db, sql, *args):
    with db.get_cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()[0]


def _detail(response):
    return response.json()["detail"]


def test_creating_a_project_answers_201_with_the_whole_project_at_version_one(api, starter, clock):
    response = api.post(PROJECTS_URL, json={"doc": starter})

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    project = body["data"]["project"]
    assert set(project) == {"id", "user_id", "name", "version", "doc", "created_at", "updated_at"}
    assert (project["user_id"], project["name"], project["version"]) == ("user-1", "[starter.name]", 1)
    assert project["doc"] == starter
    assert project["created_at"] == project["updated_at"] == clock[0].isoformat()
    assert len(project["id"]) == 26


def test_a_given_name_is_written_into_the_document(api, project_db, starter):
    project = _create(api, starter, name="Alpine trailer")

    assert project["name"] == "Alpine trailer"
    assert project["doc"]["name"] == "Alpine trailer"
    with project_db.get_cursor() as cursor:
        cursor.execute("SELECT name, doc FROM video_producer_projects")
        row = cursor.fetchone()
    assert row["name"] == "Alpine trailer"
    assert json.loads(row["doc"])["name"] == "Alpine trailer"


def test_creation_stores_the_canonical_document_and_a_first_version(api, project_db, starter):
    project = _create(api, starter)

    with project_db.get_cursor() as cursor:
        cursor.execute("SELECT doc FROM video_producer_projects WHERE id = ?", (project["id"],))
        stored = cursor.fetchone()["doc"]
    (version,) = _rows(project_db, "video_producer_versions", project["id"])
    assert stored == projects.canonical(starter)
    assert (version["version"], version["doc"], version["label"], version["source_version"]) == (1, stored, None, None)
    assert version["created_at"] == project["created_at"]


def test_timestamps_are_written_in_utc_iso_8601(project_db, store, client, starter):
    project = _create(client, starter)

    moment = datetime.fromisoformat(project["created_at"])
    assert moment.utcoffset() == timezone.utc.utcoffset(None)
    assert project["created_at"].endswith("+00:00")


@pytest.mark.parametrize(
    "body, code",
    [
        ([], "invalid_request"),
        ("doc", "invalid_request"),
        (None, "invalid_request"),
        ({}, "invalid_request"),
        ({"name": "Trailer"}, "invalid_request"),
        ({"doc": {}}, "invalid_doc"),
        ({"doc": []}, "invalid_doc"),
    ],
    ids=repr,
)
def test_creation_refuses_a_bad_body(api, project_db, body, code):
    response = api.post(PROJECTS_URL, json=body)

    assert response.status_code == 422
    assert _detail(response)["error"] == code
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 0


def test_creation_refuses_an_invalid_document_with_its_path(api, project_db, starter):
    starter["clips"][0]["extra"] = True

    response = api.post(PROJECTS_URL, json={"doc": starter})

    assert response.status_code == 422
    detail = _detail(response)
    assert (detail["success"], detail["error"]) == (False, "invalid_doc")
    assert detail["message"].startswith("$.clips[0]: ")
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 0


def test_creation_refuses_a_name_that_is_not_text(api, starter):
    response = api.post(PROJECTS_URL, json={"doc": starter, "name": 3})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"


def test_creation_refuses_a_document_over_the_size_limit(api, project_db, starter):
    starter["synopsis"] = "x" * projects.MAX_DOC_BYTES

    response = api.post(PROJECTS_URL, json={"doc": starter})

    assert response.status_code == 422
    assert _detail(response)["error"] == "doc_too_large"
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 0


def test_the_list_holds_the_callers_projects_last_updated_first(app, api, make_user, starter):
    first = _create(api, starter, name="First")
    second = _create(api, _fixture("empty_doc"), name="Second")
    _as(app, make_user(user_id="user-2"))
    _create(api, starter, name="Someone else's")
    _as(app, make_user(user_id="user-1"))
    assert _save(api, first["id"], _renamed(starter, "First, edited"), 1).status_code == 200

    response = api.get(PROJECTS_URL)

    assert response.status_code == 200
    listed = response.json()["data"]["projects"]
    assert [item["id"] for item in listed] == [first["id"], second["id"]]
    assert listed[0] == {
        "id": first["id"],
        "name": "First, edited",
        "version": 2,
        "created_at": first["created_at"],
        "updated_at": listed[0]["updated_at"],
        "shots": 5,
        "duration_s": 25,
    }
    assert listed[0]["updated_at"] > first["updated_at"]
    assert (listed[1]["shots"], listed[1]["duration_s"]) == (0, 0)


def test_the_list_is_empty_for_a_user_without_projects(api):
    assert api.get(PROJECTS_URL).json() == {"success": True, "data": {"projects": []}}


def test_an_admin_lists_only_their_own_projects(app, api, make_user, starter):
    _create(api, starter)
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    assert api.get(PROJECTS_URL).json()["data"]["projects"] == []


def test_reading_a_project_gives_its_document_and_owner(api, starter):
    created = _create(api, starter)

    response = api.get(_url(created["id"]))

    assert response.status_code == 200
    assert response.json()["data"]["project"] == created


def test_an_unknown_project_is_not_found(api):
    response = api.get(_url("01UNKNOWNPROJECT0000000000"))

    assert response.status_code == 404
    assert _detail(response)["error"] == "project_not_found"


def test_saving_a_changed_document_moves_to_the_next_version(api, project_db, starter, clock):
    created = _create(api, starter)
    edited = _renamed(starter, "Alpine trailer")
    edited["clips"][0]["label"] = "Opening"

    response = _save(api, created["id"], edited, 1, label="Before the review")

    assert response.status_code == 200
    assert response.json()["data"]["project"] == {
        "id": created["id"],
        "name": "Alpine trailer",
        "version": 2,
        "updated_at": clock[-1].isoformat(),
        "unchanged": False,
    }
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["name"], project["doc"]) == (2, "Alpine trailer", edited)
    assert project["created_at"] == created["created_at"]
    versions = _rows(project_db, "video_producer_versions", created["id"])
    assert [(row["version"], row["label"]) for row in versions] == [(1, None), (2, "Before the review")]
    assert versions[1]["doc"] == projects.canonical(edited)


def test_saving_the_same_document_writes_nothing(api, project_db, starter):
    created = _create(api, starter)
    edited = _renamed(starter, "Edited")
    _save(api, created["id"], edited, 1)
    reordered = dict(reversed(list(copy.deepcopy(edited).items())))

    response = _save(api, created["id"], reordered, 2, label="Ignored")

    assert response.status_code == 200
    saved = response.json()["data"]["project"]
    assert (saved["version"], saved["unchanged"], saved["name"]) == (2, True, "Edited")
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 2
    assert api.get(_url(created["id"])).json()["data"]["project"]["updated_at"] == saved["updated_at"]


def test_saving_from_a_stale_version_is_a_conflict_carrying_the_current_version(api, project_db, starter):
    created = _create(api, starter)
    _save(api, created["id"], _renamed(starter, "Edited"), 1)

    response = _save(api, created["id"], _renamed(starter, "Concurrent"), 1)

    assert response.status_code == 409
    detail = _detail(response)
    assert detail == {
        "success": False,
        "error": "version_conflict",
        "message": "The project is at version 2",
        "data": {"version": 2},
    }
    assert api.get(_url(created["id"])).json()["data"]["project"]["name"] == "Edited"
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 2


def test_saving_ahead_of_the_current_version_is_a_conflict_too(api, starter):
    created = _create(api, starter)

    response = _save(api, created["id"], _renamed(starter, "Edited"), 5)

    assert response.status_code == 409
    assert _detail(response)["data"] == {"version": 1}


@pytest.mark.parametrize("version", [None, "1", 1.5, True, [1]], ids=repr)
def test_saving_needs_an_integer_version(api, starter, version):
    created = _create(api, starter)

    response = api.put(_url(created["id"]), json={"doc": _renamed(starter, "Edited"), "version": version})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"


@pytest.mark.parametrize("body", [{"version": 1}, [], "doc", {"doc": {}, "version": 1, "label": 3}], ids=repr)
def test_saving_refuses_a_bad_body(api, starter, body):
    created = _create(api, starter)

    response = api.put(_url(created["id"]), json=body)

    assert response.status_code == 422
    assert _detail(response)["error"] in {"invalid_request", "invalid_doc"}


def test_saving_an_invalid_document_writes_nothing(api, project_db, starter):
    created = _create(api, starter)
    broken = _renamed(starter, "Broken")
    del broken["assets"]

    response = _save(api, created["id"], broken, 1)

    assert response.status_code == 422
    detail = _detail(response)
    assert (detail["error"], detail["message"]) == ("invalid_doc", "$: 'assets' is a required property")
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["doc"]) == (1, starter)
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 1


def test_saving_an_unknown_project_is_not_found(api, starter):
    response = _save(api, "01UNKNOWNPROJECT0000000000", starter, 1)

    assert response.status_code == 404
    assert _detail(response)["error"] == "project_not_found"


def test_the_versions_are_listed_latest_first_without_their_documents(api, starter, clock):
    created = _create(api, starter)
    two_shots = _renamed(starter, "Two shots")
    two_shots["clips"] = two_shots["clips"][:2]
    _save(api, created["id"], two_shots, 1, label="Cut down")
    _save(api, created["id"], two_shots, 2)

    response = api.get(_url(created["id"], "versions"))

    assert response.status_code == 200
    versions = response.json()["data"]["versions"]
    assert [set(item) for item in versions] == [{"id", "version", "label", "source_version", "created_at", "shots"}] * 2
    assert [(item["version"], item["label"], item["source_version"], item["shots"]) for item in versions] == [
        (2, "Cut down", None, 2),
        (1, None, None, 5),
    ]
    assert versions[0]["created_at"] > versions[1]["created_at"]


def test_the_label_a_save_sends_is_the_label_its_version_is_listed_with(api, starter):
    created = _create(api, starter)
    _save(api, created["id"], _renamed(starter, "By the assistant"), 1, label="Assistant")
    _save(api, created["id"], _renamed(starter, "Saved by hand"), 2, label="Saved from the History menu")
    _save(api, created["id"], _renamed(starter, "Autosaved"), 3)
    api.post(_url(created["id"], "versions", 2, "restore"))

    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]

    assert [(item["version"], item["label"], item["source_version"]) for item in versions] == [
        (5, None, 2),
        (4, None, None),
        (3, "Saved from the History menu", None),
        (2, "Assistant", None),
        (1, None, None),
    ]


def test_only_the_versions_kept_latest_versions_remain(api, project_db, store, starter):
    store[("versions_kept", None)] = "5"
    created = _create(api, starter)
    for version in range(1, 8):
        assert _save(api, created["id"], _renamed(starter, f"Cut {version}"), version).status_code == 200

    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]

    assert [item["version"] for item in versions] == [8, 7, 6, 5, 4]
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 5
    assert api.get(_url(created["id"])).json()["data"]["project"]["version"] == 8


def test_pruning_leaves_the_versions_of_other_projects_alone(api, project_db, store, starter):
    store[("versions_kept", None)] = "5"
    kept = _create(api, starter)
    _save(api, kept["id"], _renamed(starter, "Kept"), 1)
    pruned = _create(api, starter)
    for version in range(1, 8):
        _save(api, pruned["id"], _renamed(starter, f"Cut {version}"), version)

    assert [row["version"] for row in _rows(project_db, "video_producer_versions", kept["id"])] == [1, 2]


def test_restoring_a_version_makes_it_the_next_version(api, project_db, starter, clock):
    created = _create(api, starter)
    _save(api, created["id"], _renamed(starter, "Second"), 1)
    _save(api, created["id"], _renamed(starter, "Third"), 2)

    response = api.post(_url(created["id"], "versions", 1, "restore"))

    assert response.status_code == 200
    assert response.json()["data"]["project"] == {
        "id": created["id"],
        "name": "[starter.name]",
        "version": 4,
        "doc": starter,
        "updated_at": clock[-1].isoformat(),
    }
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["name"], project["doc"]) == (4, "[starter.name]", starter)
    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]
    assert [(item["version"], item["source_version"]) for item in versions] == [(4, 1), (3, None), (2, None), (1, None)]
    assert _save(api, created["id"], _renamed(starter, "Fourth"), 4).status_code == 200


def test_restoring_is_pruned_like_saving(api, store, starter):
    store[("versions_kept", None)] = "5"
    created = _create(api, starter)
    for version in range(1, 5):
        _save(api, created["id"], _renamed(starter, f"Cut {version}"), version)

    api.post(_url(created["id"], "versions", 2, "restore"))

    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]
    assert [(item["version"], item["source_version"]) for item in versions] == [
        (6, 2),
        (5, None),
        (4, None),
        (3, None),
        (2, None),
    ]


@pytest.mark.parametrize("version", [7, 0, -1, "latest", "1.5"])
def test_restoring_an_unknown_version_is_not_found(api, project_db, starter, version):
    created = _create(api, starter)

    response = api.post(_url(created["id"], "versions", version, "restore"))

    assert response.status_code == 404
    assert _detail(response)["error"] == "version_not_found"
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 1


LEGACY_RESULT = {"id": "r1", "clipId": "c1", "quality": "draft", "variant": "A", "status": "chosen", "range": [0, 4]}


def _with_results(doc):
    return {**copy.deepcopy(doc), "results": [LEGACY_RESULT]}


def _store_legacy(db, project_id, doc, version=1):
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE video_producer_versions SET doc = ? WHERE project_id = ? AND version = ?", (text, project_id, version))
        cursor.execute("UPDATE video_producer_projects SET doc = ? WHERE id = ? AND version = ?", (text, project_id, version))


def _stored_doc(db, project_id):
    return _count(db, "SELECT doc FROM video_producer_projects WHERE id = ?", project_id)


def test_a_document_stored_with_simulated_takes_is_read_without_them(api, project_db, starter):
    created = _create(api, starter)
    _store_legacy(project_db, created["id"], _with_results(starter))

    project = api.get(_url(created["id"])).json()["data"]["project"]
    listed = api.get(PROJECTS_URL).json()["data"]["projects"]
    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]

    assert project["doc"] == starter
    assert [(item["id"], item["shots"]) for item in listed] == [(created["id"], 5)]
    assert [(item["version"], item["shots"]) for item in versions] == [(1, 5)]


def test_a_document_read_without_its_simulated_takes_is_saved_without_them(api, project_db, starter):
    created = _create(api, starter)
    _store_legacy(project_db, created["id"], _with_results(starter))
    read = api.get(_url(created["id"])).json()["data"]["project"]

    response = _save(api, created["id"], read["doc"], 1)

    assert response.status_code == 200
    assert (response.json()["data"]["project"]["version"], response.json()["data"]["project"]["unchanged"]) == (2, False)
    assert _stored_doc(project_db, created["id"]) == projects.canonical(starter)
    assert _rows(project_db, "video_producer_versions", created["id"])[-1]["doc"] == projects.canonical(starter)


def test_a_page_that_still_sends_simulated_takes_is_saved_without_them(api, project_db, starter):
    created = _create(api, _with_results(starter))
    edited = _renamed(starter, "Edited")

    unchanged = _save(api, created["id"], _with_results(starter), 1)
    saved = _save(api, created["id"], _with_results(edited), 1)

    assert created["doc"] == starter
    assert unchanged.status_code == 200 and unchanged.json()["data"]["project"]["unchanged"] is True
    assert saved.status_code == 200 and saved.json()["data"]["project"]["version"] == 2
    assert [json.loads(row["doc"]) for row in _rows(project_db, "video_producer_versions", created["id"])] == [starter, edited]
    assert api.get(_url(created["id"])).json()["data"]["project"]["doc"] == edited


def test_restoring_a_version_stored_with_simulated_takes_restores_it_without_them(api, project_db, starter):
    created = _create(api, starter)
    _save(api, created["id"], _renamed(starter, "Second"), 1)
    _store_legacy(project_db, created["id"], _with_results(starter), version=1)

    response = api.post(_url(created["id"], "versions", 1, "restore"))

    assert response.status_code == 200
    assert response.json()["data"]["project"]["doc"] == starter
    assert _stored_doc(project_db, created["id"]) == projects.canonical(starter)
    assert _rows(project_db, "video_producer_versions", created["id"])[-1]["doc"] == projects.canonical(starter)


def _seed_takes(db, project_id, prefix):
    with db.get_cursor() as cursor:
        for index in range(2):
            take_id = f"{prefix}-take-{index}"
            cursor.execute(
                "INSERT INTO video_producer_takes (id, project_id, shot_id, quality, kind, status) "
                "VALUES (?, ?, 'shot', 'draft', 'video', 'done')",
                (take_id, project_id),
            )
            cursor.execute("INSERT INTO video_producer_jobs (id, take_id) VALUES (?, ?)", (f"{prefix}-job-{index}", take_id))


def test_deleting_a_project_removes_its_versions_takes_and_jobs(api, project_db, starter):
    doomed = _create(api, starter)
    _save(api, doomed["id"], _renamed(starter, "Second"), 1)
    kept = _create(api, starter)
    _seed_takes(project_db, doomed["id"], "doomed")
    _seed_takes(project_db, kept["id"], "kept")

    response = api.delete(_url(doomed["id"]))

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"deleted": doomed["id"]}}
    assert api.get(_url(doomed["id"])).status_code == 404
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions WHERE project_id = ?", doomed["id"]) == 0
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_takes WHERE project_id = ?", doomed["id"]) == 0
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_jobs WHERE id LIKE 'doomed-%'") == 0
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_takes WHERE project_id = ?", kept["id"]) == 2
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_jobs WHERE id LIKE 'kept-%'") == 2
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions WHERE project_id = ?", kept["id"]) == 1
    assert [item["id"] for item in api.get(PROJECTS_URL).json()["data"]["projects"]] == [kept["id"]]


def test_deleting_an_unknown_project_is_not_found(api):
    response = api.delete(_url("01UNKNOWNPROJECT0000000000"))

    assert response.status_code == 404
    assert _detail(response)["error"] == "project_not_found"


def _requests(project_id, doc):
    return [
        ("get", _url(project_id), {}),
        ("put", _url(project_id), {"json": {"doc": _renamed(doc, "Taken over"), "version": 1}}),
        ("get", _url(project_id, "versions"), {}),
        ("post", _url(project_id, "versions", 1, "restore"), {}),
        ("delete", _url(project_id), {}),
    ]


def test_another_users_project_is_not_found_whatever_the_request(app, api, project_db, make_user, starter):
    created = _create(api, starter)
    _as(app, make_user(user_id="user-2"))

    for method, url, options in _requests(created["id"], starter):
        response = getattr(api, method)(url, **options)
        assert response.status_code == 404, (method, url)
        assert _detail(response)["error"] == "project_not_found", (method, url)

    _as(app, make_user(user_id="user-1"))
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["doc"]) == (1, starter)
    assert len(_rows(project_db, "video_producer_versions", created["id"])) == 1


def test_an_admin_reaches_every_project(app, api, make_user, starter):
    created = _create(api, starter)
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    responses = [getattr(api, method)(url, **options) for method, url, options in _requests(created["id"], starter)]

    assert [response.status_code for response in responses] == [200] * 5
    assert responses[0].json()["data"]["project"]["user_id"] == "user-1"
    assert responses[1].json()["data"]["project"]["version"] == 2
    assert responses[3].json()["data"]["project"]["version"] == 3
    assert responses[4].json()["data"] == {"deleted": created["id"]}


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/projects"),
        ("post", "/projects"),
        ("get", "/projects/p-1"),
        ("put", "/projects/p-1"),
        ("delete", "/projects/p-1"),
        ("get", "/projects/p-1/versions"),
        ("post", "/projects/p-1/versions/1/restore"),
    ],
)
def test_the_project_routes_need_a_signed_in_user(app, project_db, store, method, path):
    app.dependency_overrides.clear()

    with TestClient(app) as anonymous:
        response = getattr(anonymous, method)(f"{BASE}{path}")

    assert response.status_code == 401
