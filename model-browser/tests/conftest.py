"""Test fixtures for the model-browser plugin.

Mirrors `PluginLoader.load_plugin_module`'s runtime behavior (puts the plugin
dir on `sys.path`), and claims the top-level `backend` and `hooks` names for
this plugin, evicting any copy another plugin's tests already imported. Run
this directory in its own pytest process, as `tests/plugins/run_suites.py` and
`scripts/test-plugins.ps1` do: every plugin ships a `backend` package.

`PLUGIN_ROOT` comes from this file's resolved path, never from the PotionUI
checkout's layout: the folder under `content/plugins/local/` may be a copy, a
bind mount, a junction or a symlink, and `resolve()` follows a link.
"""

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
import backend  # noqa: E402,F401  (claims the namespace for this plugin)


@pytest.fixture
def scratch_db(tmp_path):
    """A throwaway sqlite file for exactly one test - never the real app DB.
    A fresh `Database` pointed at a temp file, no migration replay (this
    plugin's tables have no FOREIGN KEY on anything migration-owned)."""
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
    """`scratch_db`, as the database `from src.plugin_api import db` hands out."""
    monkeypatch.setattr("src.platform.database.database.db", scratch_db)
    return scratch_db


@pytest.fixture
def scheduled(monkeypatch):
    """`run_on_app_loop` replaced by a recorder: the coroutines handed over to the application
    loop (`watcher.schedule_step`), for the test to await. Those left unawaited are closed."""
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
