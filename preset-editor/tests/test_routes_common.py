import importlib
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import routes_common
from backend.api import router
from src.plugin_api import AccountType, User, get_current_admin_user, identity

PREFIX = "/api/plugins/preset-editor"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)
KEY = "pui_" + "a" * 46


def _guard_app():
    app = FastAPI()

    @app.get("/probe", dependencies=[Depends(routes_common.refuse_api_keys)])
    def probe():
        return {"ok": True}

    return app


def _router_app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_admin_user] = lambda: ADMIN
    return app


def _routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(PREFIX):
            for method in sorted(route.methods):
                yield method, re.sub(r"\{[^}]+\}", "x1", route.path)


def test_a_core_with_the_marker_gives_the_marker():
    marker = object()

    assert routes_common.keys_refused(SimpleNamespace(SESSION_ONLY=marker, ApiScope=object())) == [marker]


@pytest.mark.parametrize("name", routes_common.KEY_NAMES)
def test_a_core_with_api_keys_and_without_the_marker_stops_the_plugin(name):
    with pytest.raises(RuntimeError) as raised:
        routes_common.keys_refused(SimpleNamespace(**{name: object()}))

    assert str(raised.value) == (
        f"Preset Editor does not start: this PotionUI has API keys ({name}) but no SESSION_ONLY marker, "
        "so the plugin cannot keep its routes closed to API keys. Update Preset Editor."
    )


def test_a_core_without_keys_gets_the_plugin_guard_and_a_log_line(caplog):
    with caplog.at_level(logging.WARNING, logger="plugins.preset-editor"):
        refused = routes_common.keys_refused(SimpleNamespace())

    assert len(refused) == 1
    assert refused[0].dependency is routes_common.refuse_api_keys
    assert [record.getMessage() for record in caplog.records] == [
        "Preset Editor: this PotionUI has no SESSION_ONLY marker and no API key names; "
        "the plugin refuses every Bearer token that starts with pui_ itself"
    ]


@pytest.mark.parametrize("header", [f"Bearer {KEY}", f"bearer {KEY}", f"BEARER  {KEY}", f" Bearer {KEY} "])
def test_the_plugin_guard_refuses_an_api_key(header):
    with TestClient(_guard_app()) as client:
        response = client.get("/probe", headers={"Authorization": header})

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "key_not_allowed"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.x"}, {"Authorization": f"Basic {KEY}"}])
def test_the_plugin_guard_lets_a_session_through(headers):
    with TestClient(_guard_app()) as client:
        assert client.get("/probe", headers=headers).status_code == 200


def test_on_this_core_the_routes_are_closed_to_api_keys():
    marker = getattr(identity, "SESSION_ONLY", None)
    if marker is not None:
        assert routes_common.KEYS_REFUSED == [marker]
        return
    assert [name for name in routes_common.KEY_NAMES if hasattr(identity, name)] == []
    assert [item.dependency for item in routes_common.KEYS_REFUSED] == [routes_common.refuse_api_keys]
    app = _router_app()
    checked = 0
    with TestClient(app) as client:
        for method, url in _routes(app):
            response = client.request(method, url, headers={"Authorization": f"Bearer {KEY}"})
            assert response.status_code == 403, f"{method} {url}: {response.status_code}"
            assert response.json()["detail"]["error"] == "key_not_allowed", f"{method} {url}"
            checked += 1
        assert client.get(f"{PREFIX}/me").status_code == 200
    assert checked >= 25


def test_the_module_stops_when_this_core_loses_the_marker_but_keeps_api_keys(monkeypatch):
    monkeypatch.delattr(identity, "SESSION_ONLY", raising=False)
    monkeypatch.setattr(identity, "ApiScope", getattr(identity, "ApiScope", object()), raising=False)
    try:
        with pytest.raises(RuntimeError, match="does not start"):
            importlib.reload(routes_common)
    finally:
        monkeypatch.undo()
        importlib.reload(routes_common)
