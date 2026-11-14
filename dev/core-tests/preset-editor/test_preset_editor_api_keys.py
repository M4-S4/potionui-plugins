import importlib
import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

api_scopes = pytest.importorskip("src.platform.security.api_scopes", reason="this core has no API keys")

from src.platform.security import current_user
from src.platform.security.principal import KeyGrant, ResolvedKey
from src.plugin_api import AccountType, User

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / PLUGIN_ID for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "preset_editor"
PREFIX = "/api/plugins/preset-editor"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)
SESSION = "session-token"
KEYS = {scope: f"pui_{scope.value:a<40}ZZZZZZ" for scope in api_scopes.ApiScope}


@pytest.fixture(autouse=True)
def plugin_modules_removed_afterwards():
    modules, path = set(sys.modules), list(sys.path)
    try:
        yield
    finally:
        for name in set(sys.modules) - modules:
            if name.split(".")[0] == PACKAGE:
                del sys.modules[name]
        sys.path[:] = path


def _load(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


class _Resolver:
    def __init__(self):
        self.keys = {
            secret: ResolvedKey(
                user=ADMIN,
                grant=KeyGrant(key_id=f"key-{scope.value}", user_id=ADMIN.id, scopes=frozenset({scope}), display_prefix=secret[:12]),
            )
            for scope, secret in KEYS.items()
        }

    def resolve(self, plaintext):
        return self.keys.get(plaintext)

    def mcp_gate(self, grant):
        return None

    def record_use(self, grant, via):
        return None


@pytest.fixture
def app():
    manager = Mock()
    manager.get_user_from_token.side_effect = lambda token: ADMIN if token == SESSION else None
    previous_auth, previous_resolver = current_user._auth, current_user._key_resolver
    current_user.set_auth(manager)
    current_user.set_key_resolver(_Resolver())
    current_user._key_failures.reset("testclient")
    app = FastAPI()
    app.include_router(_load("backend.api").router)
    try:
        yield app
    finally:
        current_user._auth = previous_auth
        current_user.set_key_resolver(previous_resolver)
        current_user._key_failures.reset("testclient")


def _routes(app):
    found = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(PREFIX):
            for method in sorted(route.methods):
                found.append((method, route))
    return found


def _url(path):
    return re.sub(r"\{[^}]+\}", "x1", path)


def test_the_plugin_has_routes_that_write_delete_export_and_publish(app):
    paths = {(method, route.path) for method, route in _routes(app)}

    assert ("POST", f"{PREFIX}/drafts/{{draft_id}}/publish") in paths
    assert ("PUT", f"{PREFIX}/drafts/{{draft_id}}/files/{{path:path}}") in paths
    assert ("DELETE", f"{PREFIX}/presets/{{preset_id}}") in paths
    assert ("GET", f"{PREFIX}/presets/{{preset_id}}/export") in paths
    assert len(paths) >= 25


def test_every_route_of_the_plugin_is_for_a_signed_in_session_only(app):
    for method, route in _routes(app):
        assert api_scopes.required_scopes(route, method) is None, f"{method} {route.path}"
        assert api_scopes.policy_source(route, method) == api_scopes.SOURCE_SESSION_ONLY, f"{method} {route.path}"


@pytest.mark.parametrize("scope", list(api_scopes.ApiScope), ids=lambda scope: scope.value)
def test_no_api_key_reaches_a_route_of_the_plugin_whatever_its_scope(app, scope):
    with TestClient(app) as client:
        for method, route in _routes(app):
            current_user._key_failures.reset("testclient")
            response = client.request(method, _url(route.path), headers={"Authorization": f"Bearer {KEYS[scope]}"})

            assert response.status_code == 403, f"{method} {route.path}: {response.status_code} {response.text[:200]}"
            assert response.json()["detail"]["error"] == "key_not_allowed", f"{method} {route.path}"


def test_a_signed_in_admin_still_reaches_the_plugin(app):
    with TestClient(app) as client:
        response = client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {SESSION}"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_admin"] is True
