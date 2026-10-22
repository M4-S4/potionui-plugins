import pytest
from fastapi.testclient import TestClient

from backend import core_bridge
from src.plugin_api import MediaRefError, get_current_active_user

RESOLVE_URL = "/api/plugins/video-producer/media/resolve"

HISTORY = {"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": "01M535FILE00000000000000"}
LIBRARY = {"kind": "library", "itemId": "01M535UPLOAD0000000000000"}


class Resolver:
    def __init__(self):
        self.asked = []
        self.answer = None
        self.error = None

    def __call__(self, user, ref):
        self.asked.append((user.id, ref))
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture
def resolver(monkeypatch):
    resolver = Resolver()
    monkeypatch.setattr(core_bridge, "resolve_media", resolver)
    return resolver


def _detail(response):
    return response.json()["detail"]


def test_a_history_origin_resolves_to_its_generation_url(client, resolver):
    resolver.answer = {
        "value": "generations/2026/10/01M535GENERATION000000000/take_0001.mp4",
        "media_type": "VIDEO",
        "original_filename": "take_0001.mp4",
        "origin": {"generation_id": HISTORY["generationId"], "file_index": 0},
    }

    response = client.post(RESOLVE_URL, json={"origin": HISTORY})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "media": {
                "kind": "history",
                "media_type": "video",
                "url": "/api/media/generations/01M535GENERATION000000000/take_0001.mp4",
                "filename": "take_0001.mp4",
                "origin": HISTORY,
            }
        },
    }
    assert resolver.asked == [
        ("user-1", {"kind": "history", "generation_id": HISTORY["generationId"], "file_id": HISTORY["fileId"]})
    ]


def test_a_library_origin_resolves_to_its_upload_url_and_keeps_the_original_name(client, resolver):
    resolver.answer = {
        "value": "uploads/7f3a9c.png",
        "media_type": "image",
        "original_filename": "Hiker portrait.png",
        "origin": None,
    }

    response = client.post(RESOLVE_URL, json={"origin": LIBRARY})

    assert response.status_code == 200
    assert response.json()["data"]["media"] == {
        "kind": "library",
        "media_type": "image",
        "url": "/api/media/uploads/7f3a9c.png",
        "filename": "Hiker portrait.png",
        "origin": LIBRARY,
    }
    assert resolver.asked == [("user-1", {"kind": "library", "item_id": LIBRARY["itemId"]})]


def test_a_media_without_an_original_name_is_named_after_its_file(client, resolver):
    resolver.answer = {"value": "uploads\\ridge.wav", "media_type": "audio", "original_filename": None, "origin": None}

    media = client.post(RESOLVE_URL, json={"origin": LIBRARY}).json()["data"]["media"]

    assert (media["url"], media["filename"], media["media_type"]) == ("/api/media/uploads/ridge.wav", "ridge.wav", "audio")


@pytest.mark.parametrize(
    "core_type, media_type",
    [("VIDEO", "video"), ("IMAGE", "image"), ("AUDIO", "audio"), ("video/mp4", "video"), ("MESH", "mesh"), (None, None)],
)
def test_the_media_type_is_the_lowercase_category_the_core_reports(client, resolver, core_type, media_type):
    resolver.answer = {"value": "generations/g/out.bin", "media_type": core_type, "original_filename": "out.bin", "origin": None}

    media = client.post(RESOLVE_URL, json={"origin": HISTORY}).json()["data"]["media"]

    assert (media["kind"], media["media_type"]) == ("history", media_type)


def test_the_media_is_resolved_as_the_signed_in_user(app, client, make_user, resolver):
    resolver.answer = {"value": "uploads/a.png", "media_type": "image", "original_filename": None, "origin": None}
    app.dependency_overrides[get_current_active_user] = lambda: make_user(user_id="user-9")

    client.post(RESOLVE_URL, json={"origin": LIBRARY})

    assert resolver.asked[0][0] == "user-9"


def test_a_reference_the_core_finds_invalid_is_refused(client, resolver):
    resolver.error = MediaRefError("invalid_ref", "A history reference needs generation_id and file_id")

    response = client.post(RESOLVE_URL, json={"origin": {**HISTORY, "fileId": ""}})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_ref"


def test_a_media_the_user_cannot_reach_is_not_found(client, resolver):
    resolver.error = MediaRefError("not_found", "The referenced media is not available")

    response = client.post(RESOLVE_URL, json={"origin": LIBRARY})

    assert response.status_code == 404
    detail = _detail(response)
    assert (detail["success"], detail["error"]) == (False, "media_not_found")


@pytest.mark.parametrize(
    "origin",
    [
        {"kind": "url", "href": "https://example.com/a.mp4"},
        {"kind": "history", "generation_id": "g", "file_id": "f"},
        {"kind": "library", "item_id": "i"},
        {**LIBRARY, "extra": 1},
        {"kind": "history", "generationId": "g"},
        {"itemId": "i"},
    ],
    ids=repr,
)
def test_an_origin_outside_the_picker_shapes_is_an_invalid_ref(client, resolver, origin):
    response = client.post(RESOLVE_URL, json={"origin": origin})

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_ref"
    assert resolver.asked == []


@pytest.mark.parametrize("body", [{}, {"origin": None}, {"origin": "library"}, {"origin": [LIBRARY]}, [LIBRARY], "x", None], ids=repr)
def test_a_body_without_an_origin_object_is_an_invalid_request(client, resolver, body):
    response = client.post(RESOLVE_URL, json=body)

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"
    assert resolver.asked == []


def test_resolving_needs_a_signed_in_user(app, resolver):
    app.dependency_overrides.clear()

    with TestClient(app) as anonymous:
        response = anonymous.post(RESOLVE_URL, json={"origin": LIBRARY})

    assert response.status_code == 401
    assert resolver.asked == []


UPLOADED_URL = "/api/plugins/video-producer/media/uploaded"


class Uploads:
    def __init__(self):
        self.asked = []
        self.items = {}

    def __call__(self, user_id, value):
        self.asked.append((user_id, value))
        return self.items.get((user_id, value))


@pytest.fixture
def uploads(monkeypatch):
    uploads = Uploads()
    monkeypatch.setattr(core_bridge, "upload_item", uploads)
    return uploads


def test_an_uploaded_file_resolves_to_its_library_item_and_the_media_the_editor_plays(client, resolver, uploads):
    uploads.items[("user-1", "9b1c.mp4")] = {"item_id": "01M535UPLOAD0000000000000", "filename": "Harbour at dawn.mp4"}
    resolver.answer = {"value": "uploads/9b1c.mp4", "media_type": "video/mp4", "original_filename": "Harbour at dawn.mp4", "origin": None}

    response = client.post(UPLOADED_URL, json={"filename": "9b1c.mp4"})

    assert response.status_code == 200
    assert response.json()["data"]["media"] == {
        "kind": "library",
        "media_type": "video",
        "url": "/api/media/uploads/9b1c.mp4",
        "filename": "Harbour at dawn.mp4",
        "origin": LIBRARY,
    }
    assert uploads.asked == [("user-1", "9b1c.mp4")]
    assert resolver.asked == [("user-1", {"kind": "library", "item_id": LIBRARY["itemId"]})]


def test_the_same_file_uploaded_twice_gives_the_same_origin(client, resolver, uploads):
    uploads.items[("user-1", "a.wav")] = {"item_id": "01M535UPLOAD0000000000000", "filename": "a.wav"}
    resolver.answer = {"value": "uploads/a.wav", "media_type": "audio", "original_filename": "a.wav", "origin": None}

    first, second = (client.post(UPLOADED_URL, json={"filename": "a.wav"}).json()["data"]["media"] for _ in range(2))

    assert first["origin"] == second["origin"] == LIBRARY


def test_an_upload_of_another_user_or_an_unknown_file_is_not_found(app, client, make_user, resolver, uploads):
    uploads.items[("user-1", "mine.png")] = {"item_id": "01M535UPLOAD0000000000000", "filename": "mine.png"}
    app.dependency_overrides[get_current_active_user] = lambda: make_user(user_id="user-2")

    response = client.post(UPLOADED_URL, json={"filename": "mine.png"})

    assert response.status_code == 404
    assert _detail(response)["error"] == "media_not_found"
    assert uploads.asked == [("user-2", "mine.png")]
    assert resolver.asked == []


@pytest.mark.parametrize("core_type", ["model/gltf-binary", "application/octet-stream", "MESH", None])
def test_an_uploaded_file_that_is_not_an_image_a_video_or_audio_is_refused(client, resolver, uploads, core_type):
    uploads.items[("user-1", "scene.glb")] = {"item_id": "01M535UPLOAD0000000000000", "filename": "scene.glb"}
    resolver.answer = {"value": "uploads/scene.glb", "media_type": core_type, "original_filename": "scene.glb", "origin": None}

    response = client.post(UPLOADED_URL, json={"filename": "scene.glb"})

    assert response.status_code == 415
    assert _detail(response)["error"] == "unsupported_media"


@pytest.mark.parametrize(
    "body",
    [{}, {"filename": ""}, {"filename": "  "}, {"filename": 3}, {"filename": "uploads/a.png"}, {"filename": "..\a.png"}, {"filename": ".env"}, ["a.png"], None],
    ids=repr,
)
def test_a_body_without_a_bare_file_name_is_an_invalid_request(client, resolver, uploads, body):
    response = client.post(UPLOADED_URL, json=body)

    assert response.status_code == 422
    assert _detail(response)["error"] == "invalid_request"
    assert uploads.asked == []
    assert resolver.asked == []


def test_resolving_an_upload_needs_a_signed_in_user(app, resolver, uploads):
    app.dependency_overrides.clear()

    with TestClient(app) as anonymous:
        response = anonymous.post(UPLOADED_URL, json={"filename": "a.png"})

    assert response.status_code == 401
    assert uploads.asked == []
