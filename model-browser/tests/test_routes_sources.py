"""`GET /sources`, `/{source}/search`, `/{source}/models/{id}` and `.../nsfw-media` through the
plugin's real router.

`require_browse` is overridden with a signed-in user, `nsfw.resolve_nsfw` is replaced by the
context each test sets, the settings are faked, CivitAI is the fake transport serving the
recorded fixtures, and the raw cache lives in a scratch database.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import cache as cache_module
from backend import http as http_module
from backend import nsfw
from backend.api import router
from backend.cache import Cache
from backend.http import SourceHttp
from backend.permissions import require_browse
from backend.routes_sources import MAX_UPSTREAM_PAGES
from backend.tables import create_tables
from src.plugin_api import AccountType, User

from .civitai_fakes import ABSENT, FakeTransport, body, context, fake_settings, image_urls, item, page_body

BASE = "/api/plugins/model-browser"
PAGE_1_CURSOR = "409619|21294|82098"
PAGE_2_CURSOR = "287938|23768|12597"


def _user():
    return User(id="user-1", username="user", email="user@test.com", password_hash="hash", account_type=AccountType.USER)


@pytest.fixture
def state():
    return SimpleNamespace(ctx=context("allowed", "show"))


@pytest.fixture
def transport(plugin_db, monkeypatch, state):
    create_tables()
    fake_settings(monkeypatch)
    monkeypatch.setattr(nsfw, "resolve_nsfw", lambda user: state.ctx)
    monkeypatch.setattr(cache_module, "cache", Cache())
    fake = FakeTransport().add("/enums", "enums")
    monkeypatch.setattr(http_module, "http", SourceHttp(fetch=fake, limits={"civitai": (0.0, 4)}))
    return fake


@pytest.fixture
def client(transport):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_browse] = lambda: SimpleNamespace(user=_user())
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _lora_pages(transport):
    transport.add("/models", "models_lora_page1", cursor=ABSENT)
    transport.add("/models", "models_lora_page2", cursor=PAGE_1_CURSOR)
    transport.add("/models", (200, {}, page_body([])), cursor=PAGE_2_CURSOR)


def _ids(response):
    return [found["id"] for found in response.json()["data"]["items"]]


def _error(response):
    return response.json()["detail"]


# /sources ------------------------------------------------------------------------------


def test_sources_lists_civitai_with_its_filters(client):
    response = client.get(f"{BASE}/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    [civitai] = payload["data"]
    assert civitai["id"] == "civitai"
    assert [option["value"] for option in civitai["types"]] == body("enums")["ModelType"]
    assert [option["value"] for option in civitai["base_models"]] == body("enums")["ActiveBaseModel"]


def test_the_routes_need_a_signed_in_user(transport):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as anonymous:
        for path in ("/sources", "/civitai/search", "/civitai/models/122359", "/civitai/models/122359/nsfw-media"):
            assert anonymous.get(f"{BASE}{path}").status_code in (401, 403), path
    assert transport.calls == []


# Search --------------------------------------------------------------------------------


def test_search_for_a_blocked_user_asks_for_safe_content_and_fills_the_page(client, transport, state):
    _lora_pages(transport)
    state.ctx = context("blocked", "hide")

    response = client.get(f"{BASE}/civitai/search", params={"limit": 2})

    assert response.status_code == 200
    data = response.json()["data"]
    # Page 1 brings 58390 (264290 is NSFW), page 2 brings 82098 (200255 is NSFW).
    assert _ids(response) == ["58390", "82098"]
    assert all(found["nsfw"] is False for found in data["items"])
    assert data["next_cursor"] == PAGE_2_CURSOR
    calls = transport.calls_to("/models")
    assert [call["nsfw"] for call in calls] == ["false", "false"]
    assert [call.get("cursor") for call in calls] == [None, PAGE_1_CURSOR]
    assert all("civitai.red" not in found["source_url"] for found in data["items"])


def test_search_for_a_user_who_shows_nsfw(client, transport, state):
    _lora_pages(transport)
    state.ctx = context("allowed", "show")

    response = client.get(f"{BASE}/civitai/search", params={"limit": 2})

    assert _ids(response) == ["264290", "58390"]
    assert response.json()["data"]["next_cursor"] == PAGE_1_CURSOR
    assert [call["nsfw"] for call in transport.calls_to("/models")] == ["true"]
    items = response.json()["data"]["items"]
    assert items[0]["nsfw"] is True and items[0]["source_url"] == "https://civitai.red/models/264290"


@pytest.mark.parametrize(
    "ctx, nsfw_param",
    [
        (context("blocked", "hide"), "false"),
        (context("allowed", "hide"), "false"),
        (context("blur", "hide"), "false"),
        (context("blur", "blur"), "true"),
        (context("allowed", "blur"), "true"),
        (context("allowed", "show"), "true"),
    ],
)
def test_the_safe_hint_follows_the_ceiling_and_the_mode(client, transport, state, ctx, nsfw_param):
    transport.add("/models", "models_query")
    state.ctx = ctx

    client.get(f"{BASE}/civitai/search", params={"q": "detail tweaker", "limit": 1})

    assert transport.calls_to("/models")[0]["nsfw"] == nsfw_param


def test_search_in_blur_mode_sends_nsfw_thumbnails_without_their_url(client, transport, state):
    raw = body("models_query")
    nsfw_image = raw["items"][0]["modelVersions"][0]["images"][0]
    for version in raw["items"][0]["modelVersions"]:
        for image in version["images"]:
            image["nsfwLevel"] = 8
    transport.add("/models", (200, {}, raw))
    state.ctx = context("blur", "blur")

    response = client.get(f"{BASE}/civitai/search", params={"q": "detail tweaker", "limit": 2})

    first = response.json()["data"]["items"][0]
    assert first["nsfw"] is True
    assert first["thumbnail"]["url"] is None
    assert first["thumbnail"]["blurhash"] == nsfw_image["hash"]
    assert nsfw_image["url"] not in image_urls(response.json())


def test_search_passes_the_filters_through(client, transport):
    transport.add("/models", "models_flux_nsfwlevel")

    response = client.get(
        f"{BASE}/civitai/search",
        params=[
            ("q", "#flux"),
            ("types", "LORA"),
            ("types", "DoRA,LoCon"),
            ("base_models", "Flux.1 D"),
            ("sort", "most_downloaded"),
            ("period", "month"),
            ("limit", "10"),
        ],
    )

    assert response.status_code == 200
    assert transport.calls_to("/models")[0] == {
        "baseModels": "Flux.1 D",
        "limit": "30",
        "nsfw": "true",
        "period": "Month",
        "sort": "Most Downloaded",
        "tag": "flux",
        "types": ["DoRA", "LORA", "LoCon"],
    }


def test_an_ids_search_through_the_route(client, transport):
    transport.add("/models", "models_ids")
    transport.add("/models/58390", (200, {}, item("models_lora_page1", 58390)))

    response = client.get(f"{BASE}/civitai/search", params={"q": "$#122359,58390"})

    assert _ids(response) == ["122359", "58390"]
    assert response.json()["data"]["next_cursor"] is None


def test_page_filling_stops_after_ten_upstream_pages(client, transport, state):
    nsfw_only = item("models_flux_nsfwlevel", 667086)
    counter = {"n": 0}

    def endless(path, params):
        counter["n"] += 1
        return 200, {}, page_body([dict(nsfw_only, id=1000 + counter["n"])], f"cursor-{counter['n']}")

    transport.add("/models", endless)
    state.ctx = context("blocked", "hide")

    response = client.get(f"{BASE}/civitai/search", params={"limit": 5})

    assert response.status_code == 200
    assert _ids(response) == []
    assert counter["n"] == MAX_UPSTREAM_PAGES
    assert response.json()["data"]["next_cursor"] == f"cursor-{MAX_UPSTREAM_PAGES}"


def test_a_cursor_that_does_not_move_ends_the_search(client, transport, state):
    transport.add("/models", (200, {}, page_body([], "same")), cursor="same")
    state.ctx = context("blocked", "hide")

    response = client.get(f"{BASE}/civitai/search", params={"cursor": "same"})

    assert response.json()["data"] == {"source": "civitai", "items": [], "next_cursor": None}
    assert len(transport.calls_to("/models")) == 1


def test_a_failure_after_the_first_page_returns_what_was_found(client, transport, state):
    transport.add("/models", "models_lora_page1", cursor=ABSENT)
    transport.add("/models", (503, {}, {"error": "down"}), cursor=PAGE_1_CURSOR)
    state.ctx = context("blocked", "hide")

    response = client.get(f"{BASE}/civitai/search", params={"limit": 2})

    assert response.status_code == 200
    assert _ids(response) == ["58390"]
    assert response.json()["data"]["next_cursor"] == PAGE_1_CURSOR


def test_two_users_share_one_cached_upstream_page(client, transport, state):
    transport.add("/models", "models_query")

    state.ctx = context("blur", "blur")
    blurred = client.get(f"{BASE}/civitai/search", params={"q": "detail tweaker", "limit": 2})
    state.ctx = context("allowed", "show")
    shown = client.get(f"{BASE}/civitai/search", params={"q": "detail tweaker", "limit": 2})

    assert len(transport.calls_to("/models")) == 1
    assert _ids(blurred) == _ids(shown) == ["122359", "58390"]


# Errors --------------------------------------------------------------------------------


def test_an_unknown_source_is_404(client, transport):
    for path in ("/nope/search", "/nope/models/1", "/nope/models/1/nsfw-media", "/civarchive/search"):
        response = client.get(f"{BASE}{path}")
        assert response.status_code == 404, path
        assert _error(response) == {
            "success": False,
            "error": "unknown_source",
            "message": f"Unknown source '{path.split('/')[1]}'",
        }
    assert transport.calls == []


def test_an_upstream_429_is_a_429_with_retry_after(client, transport):
    transport.add("/models", (429, {"Retry-After": "17"}, {"error": "Too Many Requests"}))

    response = client.get(f"{BASE}/civitai/search")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "17"
    assert _error(response)["error"] == "rate_limited"


def test_a_429_without_retry_after_gets_a_default(client, transport):
    transport.add("/models/122359", (429, {}, b""))

    response = client.get(f"{BASE}/civitai/models/122359")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_an_upstream_outage_is_a_502(client, transport):
    transport.add("/models", (503, {}, b"<html>maintenance</html>"))

    response = client.get(f"{BASE}/civitai/search")

    assert response.status_code == 502
    assert _error(response) == {"success": False, "error": "source_unavailable", "message": "CivitAI answered HTTP 503"}


def test_an_upstream_refusal_is_a_400_with_its_message(client, transport):
    transport.add("/models", "error_400_limit")

    response = client.get(f"{BASE}/civitai/search")

    assert response.status_code == 400
    assert _error(response)["error"] == "invalid_request"
    assert "Too big: expected number to be <=100" in _error(response)["message"]


@pytest.mark.parametrize("params", [{"sort": "best"}, {"period": "forever"}, {"q": "$#none"}])
def test_bad_search_parameters_are_a_400(client, transport, params):
    response = client.get(f"{BASE}/civitai/search", params=params)

    assert response.status_code == 400
    assert _error(response)["error"] == "invalid_request"
    assert transport.calls_to("/models") == []


@pytest.mark.parametrize("limit", [0, 51])
def test_the_limit_is_bounded(client, limit):
    assert client.get(f"{BASE}/civitai/search", params={"limit": limit}).status_code == 422


# Detail --------------------------------------------------------------------------------


def test_detail_for_a_user_who_may_see_it(client, transport, state):
    transport.add("/models/122359", "model_122359")
    state.ctx = context("allowed", "show", max_level=4)

    response = client.get(f"{BASE}/civitai/models/122359")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == "122359"
    assert data["nsfw"] is False
    assert data["source_url"] == "https://civitai.com/models/122359"
    assert data["license"]["summary"].startswith("Credit required")
    assert [version["id"] for version in data["versions"]] == ["135867", "133241"]


def test_detail_of_an_nsfw_model_is_404_for_a_blocked_user(client, transport, state):
    transport.add("/models/122359", "model_122359")  # nsfwLevel 5: NSFW at PG-13
    state.ctx = context("blocked", "hide", max_level=2)

    response = client.get(f"{BASE}/civitai/models/122359")

    assert response.status_code == 404
    assert _error(response) == {"success": False, "error": "not_found", "message": "Model not found"}


def test_detail_in_blur_mode_keeps_the_model_without_nsfw_urls(client, transport, state):
    raw = body("model_122359")
    hidden = raw["modelVersions"][0]["images"][1]
    hidden["nsfwLevel"] = 16
    transport.add("/models/122359", (200, {}, raw))
    state.ctx = context("blur", "blur", max_level=2)

    response = client.get(f"{BASE}/civitai/models/122359")

    assert response.status_code == 200
    images = response.json()["data"]["versions"][0]["images"]
    assert [image["url"] is None for image in images] == [False, True, False]
    assert images[1]["blurhash"] == hidden["hash"]
    assert images[1]["id"] == "1917133"
    assert hidden["url"] not in image_urls(response.json())


def test_detail_of_an_unknown_model_is_404(client):
    response = client.get(f"{BASE}/civitai/models/999999")

    assert response.status_code == 404
    assert _error(response)["error"] == "not_found"


def test_detail_hides_a_real_person_model_when_the_admin_says_so(client, transport, state):
    raw = body("model_122359")
    raw["poi"] = True
    transport.add("/models/122359", (200, {}, raw))
    state.ctx = context("allowed", "show", max_level=4, hide_poi=True)

    assert client.get(f"{BASE}/civitai/models/122359").status_code == 404


# nsfw-media ------------------------------------------------------------------------------


def test_nsfw_media_is_404_for_a_blocked_user_without_asking_civitai(client, transport, state):
    transport.add("/models/122359", "model_122359")
    state.ctx = context("blocked", "hide", max_level=8)

    response = client.get(f"{BASE}/civitai/models/122359/nsfw-media")

    assert response.status_code == 404
    assert _error(response)["error"] == "not_found"
    assert transport.calls_to("/models/122359") == []


def test_nsfw_media_gives_the_urls_in_blur_mode(client, transport, state):
    raw = body("model_122359")
    hidden = [raw["modelVersions"][0]["images"][1], raw["modelVersions"][1]["images"][0]]
    for image in hidden:
        image["nsfwLevel"] = 8
    transport.add("/models/122359", (200, {}, raw))
    state.ctx = context("blur", "blur", max_level=2)

    response = client.get(f"{BASE}/civitai/models/122359/nsfw-media")

    assert response.status_code == 200
    images = response.json()["data"]["images"]
    assert [image["url"] for image in images] == [image["url"] for image in hidden]
    assert all(image["nsfw"] and image["blurhash"] for image in images)


def test_nsfw_media_is_404_when_the_model_itself_is_hidden(client, transport, state):
    transport.add("/models/122359", "model_122359")
    state.ctx = context("allowed", "hide", max_level=2)

    assert client.get(f"{BASE}/civitai/models/122359/nsfw-media").status_code == 404
