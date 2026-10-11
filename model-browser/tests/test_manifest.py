"""manifest.yml, read and loaded by PotionUI's own `PluginLoader`, the way the app does it.

Catches what would otherwise only show up as a plugin in the ERROR state in
Admin -> Plugins: a manifest key the schema rejects, a handler path that does
not resolve, or a relative import that only works in the test layout.
"""

import sys
from pathlib import Path

import pytest

from backend import PLUGIN_ID, PLUGIN_VERSION

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def loader(monkeypatch, tmp_path):
    from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader

    monkeypatch.delenv(EXTRA_PLUGIN_DIRS_ENV, raising=False)
    return PluginLoader(marketplace_dir=str(tmp_path / "marketplace"), local_dir=str(PLUGIN_ROOT.parent))


@pytest.fixture
def manifest(loader):
    found = [m for m in loader.discover_plugins() if Path(m.plugin_dir).resolve() == PLUGIN_ROOT]
    assert len(found) == 1, f"PluginLoader did not discover {PLUGIN_ROOT}"
    assert found[0].validation_error is None, found[0].validation_error
    return found[0]


def test_manifest_identity_matches_the_backend(manifest):
    assert (manifest.id, manifest.version) == (PLUGIN_ID, PLUGIN_VERSION)


def test_every_backend_hook_handler_loads_inside_the_plugin_package(loader, manifest):
    assert set(manifest.hooks) == {"plugin.lifecycle.boot", "plugin.lifecycle.ready", "plugin.lifecycle.disable"}
    for hook, handler_path in manifest.hooks.items():
        handler = loader.load_hook_handler(manifest, handler_path)

        assert callable(handler), f"{hook}: {handler_path} did not load (see the log above)"
        assert handler.__module__ == "model_browser.hooks.lifecycle_hooks"

    # The handlers reach the backend through the plugin's package, never a top-level `backend`.
    lifecycle = sys.modules["model_browser.hooks.lifecycle_hooks"]
    assert lifecycle.tables.__name__ == "model_browser.backend.tables"


def test_api_module_loads_and_exposes_the_router(loader, manifest):
    module_path = manifest.api_routes["module"].replace(".py", "").replace("/", ".")

    api = loader.load_plugin_module(manifest, module_path)

    assert api is not None, f"{manifest.api_routes['module']} did not load (see the log above)"
    assert api.router.prefix == f"/api/plugins/{PLUGIN_ID}"


def test_sidebar_entry_opens_the_page_for_every_user(manifest):
    assert [item["route"] for item in manifest.sidebar_items] == [page["route"] for page in manifest.pages]
    assert all(item.get("require_role") is None for item in manifest.sidebar_items)


def test_docs_files_exist(manifest):
    for doc in manifest.docs:
        assert (PLUGIN_ROOT / doc["path"]).is_file(), doc["path"]
