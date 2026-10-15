import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader
from src.plugin_api import HookContext

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / PLUGIN_ID
PACKAGE = "preset_editor"
SLOT = "admin.presets.header-actions"
PRESETS_TAB = REPO_ROOT / "frontend" / "src" / "routes" / "admin" / "components" / "PresetsTab.svelte"
SETTING_TYPES_THE_ADMIN_PAGE_RENDERS = {"number", "boolean", "info"}


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


@pytest.fixture
def loader(monkeypatch, tmp_path):
    monkeypatch.delenv(EXTRA_PLUGIN_DIRS_ENV, raising=False)
    return PluginLoader(marketplace_dir=str(PLUGIN_ROOT.parent), local_dir=str(tmp_path / "local"))


@pytest.fixture
def manifest(loader):
    found = [m for m in loader.discover_plugins() if Path(m.plugin_dir).resolve() == PLUGIN_ROOT]
    assert len(found) == 1, f"PluginLoader did not discover {PLUGIN_ROOT}"
    assert found[0].validation_error is None, found[0].validation_error
    return found[0]


def test_manifest_identity_matches_the_backend(manifest):
    backend = _load("backend")

    assert (manifest.id, manifest.version) == (backend.PLUGIN_ID, backend.PLUGIN_VERSION)


def test_the_boot_hook_loads_inside_the_plugin_package(loader, manifest):
    assert set(manifest.hooks) == {"plugin.lifecycle.boot"}
    handler = loader.load_hook_handler(manifest, manifest.hooks["plugin.lifecycle.boot"])

    assert callable(handler), f"{manifest.hooks['plugin.lifecycle.boot']} did not load (see the log above)"
    assert handler.__module__ == f"{PACKAGE}.hooks.lifecycle_hooks"
    assert sys.modules[f"{PACKAGE}.hooks.lifecycle_hooks"].paths.__name__ == f"{PACKAGE}.backend.paths"


def test_the_boot_hook_prepares_the_folders(loader, manifest, monkeypatch, tmp_path):
    handler = loader.load_hook_handler(manifest, manifest.hooks["plugin.lifecycle.boot"])
    paths = _load("backend.paths")
    roots = paths.Roots(
        drafts=tmp_path / "drafts", history=tmp_path / "history", staging=tmp_path / "staging", local_presets=tmp_path / "local"
    )
    monkeypatch.setattr(paths, "_current", roots)
    context = HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={"plugin_id": PLUGIN_ID})

    assert handler(context) is context
    assert all(path.is_dir() for path in (roots.drafts, roots.history, roots.staging, roots.local_presets))


def test_api_module_loads_and_exposes_the_router(loader, manifest):
    module_path = manifest.api_routes["module"].replace(".py", "").replace("/", ".")

    api = loader.load_plugin_module(manifest, module_path)

    assert api is not None, f"{manifest.api_routes['module']} did not load (see the log above)"
    assert api.router.prefix == f"/api/plugins/{PLUGIN_ID}"
    assert sorted({route.path for route in api.router.routes}) == [
        f"/api/plugins/{PLUGIN_ID}/{suffix}"
        for suffix in (
            "drafts",
            "drafts/{draft_id}",
            "drafts/{draft_id}/files/{path:path}",
            "drafts/{draft_id}/lint",
            "drafts/{draft_id}/modes",
            "drafts/{draft_id}/modes/{mode}",
            "drafts/{draft_id}/publish",
            "me",
            "presets/{preset_id}",
            "presets/{preset_id}/edit",
            "presets/{preset_id}/history",
            "presets/{preset_id}/history/{stamp}/restore",
            "reference/shared",
        )
    ]


def test_the_page_is_reached_through_an_admin_only_sidebar_entry(manifest):
    assert [page["route"] for page in manifest.pages] == [PLUGIN_ID]
    assert [(item["route"], item["require_role"]) for item in manifest.sidebar_items] == [(PLUGIN_ID, "ADMIN")]


def test_the_header_contribution_targets_the_slot_the_presets_tab_mounts(manifest):
    assert [(c["slot"], c["require_role"]) for c in manifest.contributions] == [(SLOT, "ADMIN")]
    source = PRESETS_TAB.read_text(encoding="utf-8")
    assert f'hookName="{SLOT}"' in source
    assert "selectPreset" in source and "refreshPresets" in source


def test_every_component_the_manifest_cites_is_built(manifest):
    components = [page["component"] for page in manifest.pages] + [c["component"] for c in manifest.contributions]

    assert components == ["PresetEditorPage.js", "PresetsHeaderActions.js"]
    for component in components:
        assert (PLUGIN_ROOT / "frontend" / "dist" / component).is_file(), component


def test_docs_files_exist(manifest):
    for doc in manifest.docs:
        assert (PLUGIN_ROOT / doc["path"]).is_file(), doc["path"]


def test_settings_use_types_the_admin_page_renders(manifest):
    assert {setting["type"] for setting in manifest.settings} <= SETTING_TYPES_THE_ADMIN_PAGE_RENDERS
    assert [setting["name"] for setting in manifest.settings] == ["history_depth", "install_after_publish", "storage_notice"]
