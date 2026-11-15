import importlib
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import routes_common
from backend.api import router
from src.plugin_api import AccountType, User, get_current_admin_user, identity

PREFIX = "/api/plugins/preset-editor"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)
KEY = "pui_" + "a" * 46
SESSION = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJl"
REFUSED_REQUESTS = {
    "pui_ key": {"headers": {"Authorization": f"Bearer {KEY}"}},
    "lower-case bearer": {"headers": {"Authorization": f"bearer {KEY}"}},
    "other bearer shape": {"headers": {"Authorization": "Bearer pk_live_abcdef"}},
    "basic": {"headers": {"Authorization": "Basic YWRtaW46eA=="}},
    "x-api-key": {"headers": {"X-API-Key": KEY}},
    "token in the query": {"params": {"token": KEY}},
    "access_token in the query": {"params": {"access_token": KEY}},
}


def _guard_app():
    app = FastAPI()

    @app.get("/probe", dependencies=[Depends(routes_common.refuse_api_keys)])
    def probe():
        return {"ok": True}

    return app


def _router_app(dependencies):
    app = FastAPI()
    parent = APIRouter(dependencies=dependencies)
    parent.include_router(router)
    app.include_router(parent)
    app.dependency_overrides[get_current_admin_user] = lambda: ADMIN
    return app


def _routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(PREFIX):
            for method in sorted(route.methods):
                yield method, re.sub(r"\{[^}]+\}", "x1", route.path)


def _statuses(app, request):
    seen = []
    with TestClient(app) as client:
        for method, url in _routes(app):
            response = client.request(method, url, **request)
            detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else None
            seen.append((method, url, response.status_code, detail.get("error") if isinstance(detail, dict) else None))
    assert len(seen) >= 27
    return seen


def test_a_core_with_the_marker_gives_the_marker():
    marker = object()

    assert routes_common.keys_refused(SimpleNamespace(SESSION_ONLY=marker, ApiScope=object())) == [marker]


@pytest.mark.parametrize("name", routes_common.KEY_NAMES)
def test_a_core_with_api_keys_and_without_the_marker_gets_a_router_that_refuses_everything(name, caplog):
    with caplog.at_level(logging.ERROR, logger="plugins.preset-editor"):
        refused = routes_common.keys_refused(SimpleNamespace(**{name: object()}))

    assert [item.dependency for item in refused] == [routes_common.refuse_everything]
    assert [record.getMessage() for record in caplog.records] == [
        f"{routes_common.STOPPED} This PotionUI has API keys ({name}) but no SESSION_ONLY marker."
    ]


def test_every_route_answers_update_required_when_the_plugin_stops():
    app = _router_app(routes_common.keys_refused(SimpleNamespace(ApiScope=object())))

    for method, url, status, code in _statuses(app, {"headers": {"Authorization": f"Bearer {SESSION}"}}):
        assert (status, code) == (503, "update_required"), f"{method} {url}"


def test_a_core_without_keys_gets_the_strict_guard_and_a_log_line(caplog):
    with caplog.at_level(logging.WARNING, logger="plugins.preset-editor"):
        refused = routes_common.keys_refused(SimpleNamespace())

    assert [item.dependency for item in refused] == [routes_common.refuse_api_keys]
    assert [record.getMessage() for record in caplog.records] == [
        "Preset Editor: this PotionUI has no SESSION_ONLY marker and no API key names; "
        "the plugin accepts a Bearer session token only and refuses any other credential itself"
    ]


@pytest.mark.parametrize("name", sorted(REFUSED_REQUESTS))
def test_the_strict_guard_refuses_every_credential_but_a_session_on_every_route(name):
    app = _router_app(routes_common.keys_refused(SimpleNamespace()))

    for method, url, status, code in _statuses(app, REFUSED_REQUESTS[name]):
        assert (status, code) == (403, "key_not_allowed"), f"{name}: {method} {url}"


@pytest.mark.parametrize("headers", [{}, {"Authorization": f"Bearer {SESSION}"}, {"Authorization": f" bearer  {SESSION} "}])
def test_the_strict_guard_lets_a_session_or_no_credential_through_on_every_route(headers, core):
    app = _router_app(routes_common.keys_refused(SimpleNamespace()))

    for method, url, status, code in _statuses(app, {"headers": headers}):
        assert code not in ("key_not_allowed", "update_required"), f"{method} {url}: {status} {code}"


def test_a_second_authorization_header_is_checked_too():
    with TestClient(_guard_app()) as client:
        response = client.get("/probe", headers=[("Authorization", f"Bearer {SESSION}"), ("Authorization", f"Bearer {KEY}")])

    assert response.status_code == 403


def test_on_this_core_the_routes_are_closed_to_api_keys():
    marker = getattr(identity, "SESSION_ONLY", None)
    if marker is not None:
        assert routes_common.KEYS_REFUSED == [marker]
        return
    assert [name for name in routes_common.KEY_NAMES if hasattr(identity, name)] == []
    assert [item.dependency for item in routes_common.KEYS_REFUSED] == [routes_common.refuse_api_keys]
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_admin_user] = lambda: ADMIN
    for name, request in REFUSED_REQUESTS.items():
        for method, url, status, code in _statuses(app, request):
            assert (status, code) == (403, "key_not_allowed"), f"{name}: {method} {url}"
    with TestClient(app) as client:
        assert client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {SESSION}"}).status_code == 200


def test_the_module_refuses_everything_when_this_core_loses_the_marker_but_keeps_api_keys(monkeypatch):
    monkeypatch.delattr(identity, "SESSION_ONLY", raising=False)
    monkeypatch.setattr(identity, "ApiScope", getattr(identity, "ApiScope", object()), raising=False)
    try:
        importlib.reload(routes_common)
        assert [item.dependency for item in routes_common.KEYS_REFUSED] == [routes_common.refuse_everything]
    finally:
        monkeypatch.undo()
        importlib.reload(routes_common)
