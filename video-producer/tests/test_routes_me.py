from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.plugin_api.limits as api_limits
from backend import core_bridge
from src.plugin_api import AccountType, get_current_active_user
from src.plugin_api.limits import LimitStatus

ME_URL = "/api/plugins/video-producer/me"

DEFAULT_SETTINGS = {"draft_resolution": "832x480", "max_parallel_jobs": 2, "export_dir_quota_mb": 2048}
UNLIMITED = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}


def _quota(monkeypatch, **status):
    asked = []

    def limit_status(user_id, kind):
        asked.append((user_id, kind))
        return LimitStatus(kind=kind, **status)

    monkeypatch.setattr(api_limits, "limit_status", limit_status)
    return asked


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def test_me_without_a_saved_locale_or_settings_reports_the_defaults(client, store, no_container):
    response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "locale": None,
            "is_admin": False,
            "limits": {"gpu_minutes": UNLIMITED},
            "settings": DEFAULT_SETTINGS,
            "plugin": {"id": "video-producer", "version": "0.1.0"},
        },
    }


@pytest.mark.parametrize("account_type, is_admin", [(AccountType.USER, False), (AccountType.ADMIN, True)])
def test_me_tells_whether_the_user_is_an_admin(app, client, make_user, store, no_container, account_type, is_admin):
    _as(app, make_user(account_type))

    assert client.get(ME_URL).json()["data"]["is_admin"] is is_admin


def test_me_names_the_plugin_and_its_version(client, store, no_container):
    assert client.get(ME_URL).json()["data"]["plugin"] == {"id": "video-producer", "version": "0.1.0"}


def test_me_asks_for_the_quota_of_the_signed_in_user(app, client, make_user, store, monkeypatch):
    asked = _quota(monkeypatch)
    _as(app, make_user(user_id="user-7"))

    client.get(ME_URL)

    assert asked == [("user-7", "video-producer.gpu_minutes")]


def test_me_reports_no_quota_for_a_user_without_a_limit(client, store, monkeypatch):
    _quota(monkeypatch)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == UNLIMITED


def test_me_reports_no_remaining_minutes_for_an_exempt_admin(app, client, make_user, store, monkeypatch):
    _quota(monkeypatch, limit=600, exempt=True)
    _as(app, make_user(AccountType.ADMIN))

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == {
        "limit": 600,
        "used": None,
        "remaining": None,
        "exempt": True,
        "resets_at": None,
    }


def test_me_reports_the_quota_used_remaining_and_reset_of_a_limited_user(client, store, monkeypatch):
    _quota(monkeypatch, limit=600, used=125.5, resets_at=datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == {
        "limit": 600,
        "used": 125.5,
        "remaining": 474.5,
        "exempt": False,
        "resets_at": "2026-11-01T00:00:00+00:00",
    }


def test_me_tells_the_reset_in_utc_whatever_the_offset(client, store, monkeypatch):
    local = datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=2)))
    _quota(monkeypatch, limit=10, used=1, resets_at=local)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"]["resets_at"] == "2026-10-31T22:00:00+00:00"


def test_me_reports_no_remaining_minutes_once_the_quota_is_used_up(client, store, monkeypatch):
    _quota(monkeypatch, limit=60, used=75)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"]["remaining"] == 0.0


def test_me_types_the_admin_settings_from_their_stored_strings(client, store, no_container):
    store.update(
        {
            ("draft_resolution", None): "1280x720",
            ("max_parallel_jobs", None): "4",
            ("export_dir_quota_mb", None): "512",
        }
    )

    assert client.get(ME_URL).json()["data"]["settings"] == {
        "draft_resolution": "1280x720",
        "max_parallel_jobs": 4,
        "export_dir_quota_mb": 512,
    }


def test_me_falls_back_to_the_default_of_a_setting_that_cannot_be_read(client, store, no_container):
    store.update(
        {
            ("draft_resolution", None): "640x480",
            ("max_parallel_jobs", None): "many",
            ("export_dir_quota_mb", None): "not a number",
        }
    )

    assert client.get(ME_URL).json()["data"]["settings"] == DEFAULT_SETTINGS


def test_me_reads_the_settings_of_the_admin_and_the_locale_of_the_user(client, store, no_container):
    store.update({("locale", "user-1"): "fr", ("locale", None): "en", ("max_parallel_jobs", "user-1"): "9"})

    data = client.get(ME_URL).json()["data"]

    assert data["locale"] == "fr"
    assert data["settings"]["max_parallel_jobs"] == 2


def test_me_ignores_a_stored_locale_it_does_not_support(client, store, no_container):
    store[("locale", "user-1")] = "de"

    assert client.get(ME_URL).json()["data"]["locale"] is None


@pytest.mark.parametrize("locale", ["en", "fr"])
def test_put_me_saves_the_locale_for_the_user_only(client, store, no_container, locale):
    response = client.put(ME_URL, json={"locale": locale})

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"locale": locale}}
    assert store == {("locale", "user-1"): locale}
    assert client.get(ME_URL).json()["data"]["locale"] == locale


def test_put_me_keeps_the_last_locale_and_ignores_other_keys(client, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})
    response = client.put(ME_URL, json={"locale": "en", "theme": "dark"})

    assert response.json() == {"success": True, "data": {"locale": "en"}}
    assert store == {("locale", "user-1"): "en"}


def test_the_locale_of_a_user_is_not_seen_by_another_one(app, client, make_user, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})
    _as(app, make_user(user_id="user-2"))

    assert client.get(ME_URL).json()["data"]["locale"] is None
    assert client.put(ME_URL, json={"locale": "en"}).status_code == 200
    assert store == {("locale", "user-1"): "fr", ("locale", "user-2"): "en"}


@pytest.mark.parametrize(
    "body",
    [
        {"locale": "de"},
        {"locale": "FR"},
        {"locale": " fr"},
        {"locale": ""},
        {"locale": None},
        {"locale": 0},
        {"locale": 3},
        {"locale": True},
        {"locale": ["fr"]},
        {"locale": {"code": "fr"}},
        {},
        {"language": "fr"},
        ["fr"],
        "fr",
        3,
        None,
    ],
    ids=repr,
)
def test_put_me_refuses_an_unsupported_locale(client, store, body):
    response = client.put(ME_URL, json=body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["success"] is False
    assert detail["error"] == "invalid_locale"
    assert "en" in detail["message"] and "fr" in detail["message"]
    assert store == {}


def test_put_me_refuses_a_body_that_is_not_json(client, store):
    response = client.put(ME_URL, content="locale=fr", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert store == {}


def test_a_refused_locale_leaves_the_saved_one_alone(client, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})

    assert client.put(ME_URL, json={"locale": "de"}).status_code == 422
    assert client.get(ME_URL).json()["data"]["locale"] == "fr"


@pytest.mark.parametrize("method", ["get", "put"])
def test_me_needs_a_signed_in_user(app, store, method):
    app.dependency_overrides.clear()
    options = {"json": {"locale": "fr"}} if method == "put" else {}

    with TestClient(app) as anonymous:
        response = getattr(anonymous, method)(ME_URL, **options)

    assert response.status_code == 401
    assert store == {}


def test_the_locale_goes_through_the_plugin_repository_with_the_user_id(client, no_container, monkeypatch):
    calls = []

    class Repository:
        def get_plugin_setting(self, plugin_id, setting_key, user_id=None):
            calls.append(("get", plugin_id, setting_key, user_id))
            return SimpleNamespace(setting_value="fr") if setting_key == "locale" else None

        def set_plugin_setting(self, plugin_id, setting_key, setting_value, user_id=None, is_secret=False):
            calls.append(("set", plugin_id, setting_key, setting_value, user_id))

    monkeypatch.setattr(core_bridge, "PluginRepository", Repository)

    assert client.put(ME_URL, json={"locale": "en"}).status_code == 200
    assert client.get(ME_URL).json()["data"]["locale"] == "fr"

    assert calls[0] == ("set", "video-producer", "locale", "en", "user-1")
    assert ("get", "video-producer", "locale", "user-1") in calls
    assert ("get", "video-producer", "draft_resolution", None) in calls
