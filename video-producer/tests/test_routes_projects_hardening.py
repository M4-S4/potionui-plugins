import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import core_bridge, projects
from src.plugin_api import AccountType, get_current_active_user

BASE = "/api/plugins/video-producer"
PROJECTS_URL = f"{BASE}/projects"
ME_URL = f"{BASE}/me"
RESOLVE_URL = f"{BASE}/media/resolve"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

ASSET = {
    "id": "01HARDENING0ASSET00000000",
    "kind": "video",
    "name": "ridge.mp4",
    "src": "/api/media/uploads/ridge.mp4",
    "origin": {"kind": "library", "itemId": "01HARDENING0UPLOAD0000000"},
    "srcDur": 6.0,
    "width": 1280,
    "height": 720,
    "fps": None,
    "res": "1280x720",
    "generated": False,
    "quality": None,
    "resultId": None,
    "role": None,
}


def _starter():
    return json.loads((FIXTURES / "starter_doc.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    doc = _starter()
    doc["assets"] = [copy.deepcopy(ASSET)]
    return doc


@pytest.fixture(autouse=True)
def empty_catalog(monkeypatch):
    monkeypatch.setattr(core_bridge, "api_backends", SimpleNamespace(list_backends=lambda: []))
    monkeypatch.setattr(core_bridge, "api_presets", SimpleNamespace(list_presets=lambda user: []))


@pytest.fixture
def api(project_db, store, clock, no_container, client):
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


def _named(doc, name):
    return {**copy.deepcopy(doc), "name": name}


def _detail(response):
    return response.json()["detail"]


def _version_numbers(client, project_id):
    return [item["version"] for item in client.get(_url(project_id, "versions")).json()["data"]["versions"]]


def _count(db, sql, *args):
    with db.get_cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()[0]


def _objects(node, path="$"):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _objects(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _objects(value, f"{path}[{index}]")


def _at(doc, path):
    node = doc
    for part in path.removeprefix("$").replace("]", "").replace("[", ".").split("."):
        if part:
            node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def test_each_user_lists_only_their_own_projects(app, api, make_user, starter):
    users = (
        ("user-1", AccountType.USER, ["A1", "A2"]),
        ("user-2", AccountType.USER, ["B1"]),
        ("admin-1", AccountType.ADMIN, ["C1"]),
    )
    ids = {}
    for user_id, account_type, names in users:
        _as(app, make_user(account_type, user_id=user_id))
        ids[user_id] = {_create(api, starter, name=name)["id"] for name in names}

    for user_id, account_type, _ in users:
        _as(app, make_user(account_type, user_id=user_id))
        listed = api.get(PROJECTS_URL).json()["data"]["projects"]
        assert {item["id"] for item in listed} == ids[user_id], user_id

    _as(app, make_user(user_id="user-2"))
    for foreign in ids["user-1"] | ids["admin-1"]:
        assert api.get(_url(foreign)).status_code == 404
        assert api.get(_url(foreign, "versions")).status_code == 404


def test_an_admin_reads_saves_and_deletes_the_project_of_another_user(app, api, project_db, make_user, starter):
    created = _create(api, starter, name="Owned by user-1")
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    read = api.get(_url(created["id"]))
    saved = _save(api, created["id"], _named(starter, "Edited by the admin"), 1, label="Admin pass")
    versions = api.get(_url(created["id"], "versions"))

    assert read.json()["data"]["project"]["user_id"] == "user-1"
    assert saved.status_code == 200
    assert saved.json()["data"]["project"]["version"] == 2
    listed = versions.json()["data"]["versions"]
    assert [(item["version"], item["label"]) for item in listed] == [(2, "Admin pass"), (1, None)]
    assert api.get(PROJECTS_URL).json()["data"]["projects"] == []

    _as(app, make_user(user_id="user-1"))
    owned = api.get(_url(created["id"])).json()["data"]["project"]
    assert (owned["user_id"], owned["name"], owned["version"]) == ("user-1", "Edited by the admin", 2)
    assert [item["id"] for item in api.get(PROJECTS_URL).json()["data"]["projects"]] == [created["id"]]

    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))
    assert api.delete(_url(created["id"])).json()["data"] == {"deleted": created["id"]}
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 0
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 0
    _as(app, make_user(user_id="user-1"))
    assert api.get(PROJECTS_URL).json()["data"]["projects"] == []


@pytest.mark.parametrize("path", ["$", "$.clips[0]", "$.assets[0]", "$.lanes[0].inserts[0]"])
@pytest.mark.parametrize("verb", ["create", "save"])
def test_an_unknown_field_is_refused_with_its_path_at_every_level(api, project_db, starter, path, verb):
    created = _create(api, starter)
    broken = copy.deepcopy(starter)
    _at(broken, path)["unexpected"] = 1

    if verb == "create":
        response = api.post(PROJECTS_URL, json={"doc": broken})
    else:
        response = _save(api, created["id"], broken, 1)

    assert response.status_code == 422
    detail = _detail(response)
    assert (detail["success"], detail["error"]) == (False, "invalid_doc")
    assert detail["message"].startswith(f"{path}: "), detail["message"]
    assert "unexpected" in detail["message"]
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 1
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 1
    assert api.get(_url(created["id"])).json()["data"]["project"]["version"] == 1


def test_an_unknown_field_is_refused_on_every_object_the_document_holds(api, starter):
    swept = 0
    for path, _ in _objects(starter):
        broken = copy.deepcopy(starter)
        _at(broken, path)["unexpected"] = 1

        response = api.post(PROJECTS_URL, json={"doc": broken})

        assert response.status_code == 422, path
        assert _detail(response)["error"] == "invalid_doc", path
        assert _detail(response)["message"].startswith(f"{path}: "), (path, _detail(response)["message"])
        swept += 1
    assert swept > 30


def test_a_missing_required_field_is_refused_at_every_level(api, starter):
    paths = (
        "$.clips[0].dur",
        "$.assets[0].kind",
        "$.lanes[0].inserts[0].type",
        "$.engine.quality",
        "$.hybrid.style",
    )
    for path in paths:
        broken = copy.deepcopy(starter)
        parent, _, key = path.rpartition(".")
        del _at(broken, parent)[key]

        response = api.post(PROJECTS_URL, json={"doc": broken})

        assert response.status_code == 422, path
        assert _detail(response)["error"] == "invalid_doc", path


def test_a_document_over_four_mebibytes_is_too_large_to_create_or_save(api, project_db, starter):
    created = _create(api, starter)
    huge = _named(starter, "Huge")
    huge["synopsis"] = "x" * projects.MAX_DOC_BYTES

    refused = [api.post(PROJECTS_URL, json={"doc": huge}), _save(api, created["id"], huge, 1)]

    for response in refused:
        assert response.status_code == 422
        assert _detail(response)["error"] == "doc_too_large"
        assert _detail(response)["message"].startswith("$: the document is ")
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 1
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 1


def test_the_size_limit_counts_bytes_not_characters(api, starter):
    accented = _named(starter, "Accents")
    accented["synopsis"] = "é" * (projects.MAX_DOC_BYTES // 2)

    response = api.post(PROJECTS_URL, json={"doc": accented})

    assert response.status_code == 422
    assert _detail(response)["error"] == "doc_too_large"


def test_a_document_of_exactly_the_limit_is_stored_and_one_byte_more_is_not(api, starter):
    padded = _named(starter, "Boundary")
    padded["synopsis"] = ""
    room = projects.MAX_DOC_BYTES - len(projects.canonical(padded).encode("utf-8"))
    padded["synopsis"] = "x" * room
    assert len(projects.canonical(padded).encode("utf-8")) == projects.MAX_DOC_BYTES

    accepted = api.post(PROJECTS_URL, json={"doc": padded})
    padded["synopsis"] += "x"
    refused = api.post(PROJECTS_URL, json={"doc": padded})

    assert accepted.status_code == 201
    assert refused.status_code == 422
    assert _detail(refused)["error"] == "doc_too_large"


NOT_INTEGERS = ["1", "2", "one", "", "1.0", 1.0, 1.5, -0.5, True, False, None, [1], {"v": 1}]


@pytest.mark.parametrize("version", NOT_INTEGERS, ids=repr)
def test_saving_with_a_version_that_is_not_an_integer_is_refused_and_writes_nothing(api, project_db, starter, version):
    created = _create(api, starter)

    response = api.put(_url(created["id"]), json={"doc": _named(starter, "Edited"), "version": version})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["name"]) == (1, starter["name"])
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 1


def test_a_label_of_a_mebibyte_is_refused(api, project_db, starter):
    created = _create(api, starter)

    response = _save(api, created["id"], _named(starter, "Edited"), 1, label="x" * 1024 * 1024)

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 1


@pytest.mark.parametrize("length, status", [(200, 200), (201, 422)])
def test_a_label_is_limited_to_two_hundred_characters(api, starter, length, status):
    created = _create(api, starter)

    response = _save(api, created["id"], _named(starter, "Edited"), 1, label="é" * length)

    assert response.status_code == status
    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]
    assert len(versions) == (2 if status == 200 else 1)
    if status == 200:
        assert versions[0]["label"] == "é" * length
    else:
        assert _detail(response)["error"] == "invalid_request"


@pytest.mark.parametrize("length, status", [(200, 201), (201, 422)])
def test_a_given_project_name_is_limited_to_two_hundred_characters(api, project_db, starter, length, status):
    response = api.post(PROJECTS_URL, json={"doc": starter, "name": "n" * length})

    assert response.status_code == status
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == (1 if status == 201 else 0)
    if status == 422:
        assert _detail(response)["error"] == "invalid_request"


def test_saving_without_a_version_key_is_refused(api, starter):
    created = _create(api, starter)

    response = api.put(_url(created["id"]), json={"doc": _named(starter, "Edited")})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"


def test_a_pruned_version_can_no_longer_be_restored(api, store, starter):
    store[("versions_kept", None)] = "5"
    created = _create(api, starter)
    for version in range(1, 8):
        assert _save(api, created["id"], _named(starter, f"Cut {version}"), version).status_code == 200
    assert _version_numbers(api, created["id"]) == [8, 7, 6, 5, 4]

    for pruned in (1, 2, 3):
        response = api.post(_url(created["id"], "versions", pruned, "restore"))
        assert response.status_code == 404, pruned
        assert _detail(response)["error"] == "version_not_found"

    assert api.get(_url(created["id"])).json()["data"]["project"]["version"] == 8
    assert api.post(_url(created["id"], "versions", 4, "restore")).status_code == 200
    assert _version_numbers(api, created["id"]) == [9, 8, 7, 6, 5]
    assert api.post(_url(created["id"], "versions", 4, "restore")).status_code == 404


@pytest.mark.parametrize("raw", ["5", "1", "-10", " 3 "])
def test_the_lower_bound_of_versions_kept_is_five_after_twenty_distinct_saves(api, project_db, store, starter, raw):
    store[("versions_kept", None)] = raw
    created = _create(api, starter)
    for version in range(1, 21):
        assert _save(api, created["id"], _named(starter, f"Cut {version}"), version).status_code == 200

    assert _version_numbers(api, created["id"]) == [21, 20, 19, 18, 17]
    project = api.get(_url(created["id"])).json()["data"]["project"]
    assert (project["version"], project["name"]) == (21, "Cut 20")
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_versions") == 5


@pytest.mark.parametrize("raw", ["many", "1e999", None])
def test_an_unreadable_versions_kept_falls_back_to_the_default_not_to_the_bound(api, store, starter, raw):
    store[("versions_kept", None)] = raw
    created = _create(api, starter)
    for version in range(1, 9):
        _save(api, created["id"], _named(starter, f"Cut {version}"), version)

    assert len(_version_numbers(api, created["id"])) == 9


def test_the_upper_bound_of_versions_kept_is_five_hundred(api, store, starter):
    store[("versions_kept", None)] = "100000"

    assert api.get(ME_URL).json()["data"]["settings"]["versions_kept"] == 500


def test_pruning_keeps_the_latest_versions_not_the_labelled_ones(api, store, starter):
    store[("versions_kept", None)] = "5"
    created = _create(api, starter)
    assert _save(api, created["id"], _named(starter, "Milestone"), 1, label="Milestone").status_code == 200
    for version in range(2, 9):
        _save(api, created["id"], _named(starter, f"Cut {version}"), version)

    versions = api.get(_url(created["id"], "versions")).json()["data"]["versions"]

    assert [item["version"] for item in versions] == [9, 8, 7, 6, 5]
    assert all(item["label"] is None for item in versions)


def test_the_last_project_of_a_deleted_project_becomes_null_in_me(api, store, starter):
    created = _create(api, starter)
    assert api.put(ME_URL, json={"last_project_id": created["id"]}).status_code == 200
    assert api.get(ME_URL).json()["data"]["last_project_id"] == created["id"]

    assert api.delete(_url(created["id"])).status_code == 200

    me = api.get(ME_URL).json()["data"]
    assert me["last_project_id"] is None
    fresh = _create(api, starter)
    assert api.get(ME_URL).json()["data"]["last_project_id"] is None
    assert fresh["id"] != created["id"]


def test_the_last_project_becomes_null_when_an_admin_deletes_it(app, api, make_user, store, starter):
    created = _create(api, starter)
    api.put(ME_URL, json={"last_project_id": created["id"]})
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))
    assert api.delete(_url(created["id"])).status_code == 200
    _as(app, make_user(user_id="user-1"))

    assert api.get(ME_URL).json()["data"]["last_project_id"] is None


def test_put_me_refuses_the_project_of_another_user_even_for_an_admin(app, api, make_user, store, starter):
    created = _create(api, starter)
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    put = api.put(ME_URL, json={"last_project_id": created["id"]})
    both = api.put(ME_URL, json={"locale": "fr", "last_project_id": created["id"]})

    for response in (put, both):
        assert response.status_code == 404
        assert _detail(response)["error"] == "project_not_found"
    assert store.get(("last_project_id", "admin-1")) is None
    assert store.get(("locale", "admin-1")) is None
    assert api.get(ME_URL).json()["data"]["last_project_id"] is None
    assert api.get(_url(created["id"])).status_code == 200


def test_put_me_cannot_probe_for_projects_of_others_by_telling_them_apart(app, api, make_user, store, starter):
    created = _create(api, starter)
    _as(app, make_user(user_id="user-2"))

    foreign = api.put(ME_URL, json={"last_project_id": created["id"]})
    unknown = api.put(ME_URL, json={"last_project_id": "01UNKNOWNPROJECT0000000000"})

    assert foreign.status_code == unknown.status_code == 404
    assert _detail(foreign) == _detail(unknown)


@pytest.fixture
def core_without_media(monkeypatch):
    def refuse(user, ref):
        raise AssertionError(f"the route asked the core to resolve a ref it should have refused: {ref!r}")

    monkeypatch.setattr(core_bridge, "resolve_media", refuse)


@pytest.mark.parametrize(
    "origin",
    [
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": 7},
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": 7.5},
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": True},
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": None},
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": ""},
        {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": ["a"]},
        {"kind": "history", "generationId": 12, "fileId": "01M535FILE00000000000000"},
        {"kind": "library", "itemId": 3},
        {"kind": "library", "itemId": ""},
        {"kind": "library", "itemId": None},
    ],
    ids=repr,
)
def test_a_media_origin_whose_ids_are_not_text_is_an_invalid_ref(api, core_without_media, origin):
    response = api.post(RESOLVE_URL, json={"origin": origin})

    assert response.status_code == 422
    detail = _detail(response)
    assert (detail["success"], detail["error"]) == (False, "invalid_ref")


def test_two_concurrent_saves_from_the_same_version_cannot_both_win(app, project_db, store, clock, make_user, starter):
    store[("versions_kept", None)] = "5"
    with TestClient(app) as writer:
        created = _create(writer, starter)
        outcomes = []
        barrier = threading.Barrier(6)

        def attempt(index):
            barrier.wait()
            outcomes.append(_save(writer, created["id"], _named(starter, f"Racer {index}"), 1).status_code)

        threads = [threading.Thread(target=attempt, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(outcomes) == [200, 409, 409, 409, 409, 409]
        project = writer.get(_url(created["id"])).json()["data"]["project"]
        assert project["version"] == 2
        assert _version_numbers(writer, created["id"]) == [2, 1]


CALLS = (("get", ()), ("put", ()), ("delete", ()), ("get", ("versions",)), ("post", ("versions", 1, "restore")))


def test_an_id_that_looks_like_sql_or_a_path_is_just_unknown(api, starter):
    _create(api, starter)

    for project_id in ("' OR 1=1 --", "%", "..%2f..%2fetc", "a b", "0" * 300):
        for method, suffix in CALLS:
            options = {"json": {"doc": starter, "version": 1}} if method == "put" else {}
            response = getattr(api, method)(_url(project_id, *suffix), **options)
            assert response.status_code in {404, 405}, (project_id, method, suffix)
    assert len(api.get(PROJECTS_URL).json()["data"]["projects"]) == 1


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_a_number_json_cannot_store_is_refused_not_stored(api, project_db, starter, literal):
    body = json.dumps({"doc": starter}).replace('"fps": 25', f'"fps": {literal}')
    assert literal in body

    response = api.post(PROJECTS_URL, content=body, headers={"content-type": "application/json"})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_doc"
    assert _count(project_db, "SELECT COUNT(*) FROM video_producer_projects") == 0
