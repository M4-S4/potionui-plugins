import importlib
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

for _key in list(sys.modules):
    if _key.split(".", 1)[0] in ("backend", "hooks"):
        del sys.modules[_key]

if str(PLUGIN_ROOT) in sys.path:
    sys.path.remove(str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT))

importlib.invalidate_caches()
import backend  # noqa: E402,F401


@pytest.fixture
def scratch_db(tmp_path):
    from src.plugin_api.storage import db

    Database = type(db)

    Database._instance = None
    test_db = Database()
    test_db.db_path = tmp_path / "test.sqlite"
    test_db.db_path.parent.mkdir(parents=True, exist_ok=True)
    test_db._initialized = True
    yield test_db
    Database._instance = None


@pytest.fixture
def plugin_db(scratch_db, monkeypatch):
    monkeypatch.setattr("src.platform.database.database.db", scratch_db)
    return scratch_db


@pytest.fixture
def scheduled(monkeypatch):
    import concurrent.futures

    import src.plugin_api.hooks as plugin_hooks

    jobs = []

    def run_on_app_loop(coro):
        jobs.append(coro)
        return concurrent.futures.Future()

    monkeypatch.setattr(plugin_hooks, "run_on_app_loop", run_on_app_loop)
    yield jobs
    for job in jobs:
        job.close()


class SettingsStore(dict):
    def __init__(self):
        super().__init__()
        self.calls = []


@pytest.fixture
def store(monkeypatch):
    from backend import core_bridge

    values = SettingsStore()

    def get_plugin_setting(key, user_id=None):
        values.calls.append(("get", key, user_id))
        return values.get((key, user_id))

    def set_plugin_setting(key, value, user_id=None):
        values.calls.append(("set", key, value, user_id))
        values[(key, user_id)] = value

    monkeypatch.setattr(core_bridge, "get_plugin_setting", get_plugin_setting)
    monkeypatch.setattr(core_bridge, "set_plugin_setting", set_plugin_setting)
    return values


@pytest.fixture
def make_user():
    from src.plugin_api import AccountType, User

    def make(account_type=AccountType.USER, user_id="user-1"):
        return User(
            id=user_id,
            username=f"name-{user_id}",
            email=f"{user_id}@test.com",
            password_hash="hash",
            account_type=account_type,
        )

    return make


@pytest.fixture
def app(make_user):
    from fastapi import FastAPI

    from backend.api import router
    from src.plugin_api import get_current_active_user

    app = FastAPI(redirect_slashes=False)
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = make_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture
def no_container(monkeypatch):
    import src.plugin_api.limits as api_limits

    def limit_status(user_id, kind):
        raise RuntimeError("AppContainer not initialized yet")

    monkeypatch.setattr(api_limits, "limit_status", limit_status)
