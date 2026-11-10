import functools
import importlib
import importlib.util
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.features.presets.file_repository import FilePresetRepository
from src.features.presets.loader import PresetTemplateLoader
from src.features.presets.repository import DatabasePresetRepository
from src.features.user_groups.repository import UserGroupRepository
from src.plugin_api import AccountType, User, get_current_active_user
from src.plugin_api import presets as plugin_api_presets

pytestmark = pytest.mark.skipif(
    not hasattr(plugin_api_presets, "files_preset_id"), reason="this core has no preset mirrors"
)

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / PLUGIN_ID for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "preset_editor"
NATIVE = PLUGIN_ROOT / "tests" / "fixtures" / "presets" / "minimal-native"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)
PRESETS_URL = "/api/plugins/preset-editor/presets"
DRAFTS_URL = "/api/plugins/preset-editor/drafts"
ORIGIN = "local-one"
MIRROR = "local-one-mirror"


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


class _Plugins:
    def execute_hook(self, hook, context=None, initial_data=None):
        return SimpleNamespace(data=dict(initial_data or {})), True


@pytest.fixture
def roots(tmp_path, monkeypatch):
    paths = _load("backend.paths")
    roots = paths.Roots(
        drafts=tmp_path / "storage" / "drafts",
        history=tmp_path / "storage" / "history",
        staging=tmp_path / "content" / "presets" / ".preset-editor" / "staging",
        local_presets=tmp_path / "content" / "presets" / "local",
    )
    roots.ensure()
    monkeypatch.setattr(paths, "_current", roots)
    return roots


@pytest.fixture
def core(roots, tmp_path, monkeypatch, mock_db):
    from src.features.presets.mappers import read_overlays

    marketplace = tmp_path / "content" / "presets" / "marketplace"
    shutil.copytree(NATIVE, marketplace / "Fixture" / "native")
    drafts = _load("backend.drafts")
    origin_dir = roots.local_presets / "Local" / "v1"
    shutil.copytree(NATIVE, origin_dir)
    manifest = origin_dir / "preset.yml"
    manifest.write_text(
        drafts.rewrite_top_level(manifest.read_text(encoding="utf-8"), {"id": ORIGIN, "name": "Local one"}), encoding="utf-8"
    )
    db_repo = DatabasePresetRepository()
    loader = PresetTemplateLoader(
        [str(marketplace), str(roots.local_presets)], overlay_source=functools.partial(read_overlays, db_repo)
    )
    loader.reload()
    file_repo = FilePresetRepository(loader)
    collaborators = SimpleNamespace(
        preset_loader=loader, file_repo=file_repo, db_repo=db_repo, group_repo=UserGroupRepository(), plugins=_Plugins(),
        cover_store=None,
    )
    container = SimpleNamespace(
        preset_template_loader=loader, file_preset_repository=file_repo, preset_collaborators=collaborators,
        requirement_checker_registry=None,
    )
    core_bridge = _load("backend.core_bridge")
    monkeypatch.setattr(core_bridge, "get_container", lambda: container)
    monkeypatch.setattr(plugin_api_presets, "get_container", lambda: container)
    core_bridge.install_preset(ORIGIN, ADMIN)
    db_repo.create_mirror(
        preset_id=MIRROR, source_preset_id=ORIGIN, display_name="Local one, mirrored", display_description=None,
        display_cover=None, offered_modes=None, first_mode=None, configuration={}, form_overrides={},
    )
    loader.refresh_overlays()
    app = FastAPI()
    app.include_router(_load("backend.api").router)
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield SimpleNamespace(
            bridge=core_bridge, loader=loader, db_repo=db_repo, client=client, origin_dir=origin_dir,
            collaborators=collaborators,
        )


def _tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_the_core_shows_the_mirror_as_a_local_preset_living_in_the_folder_of_its_source(core):
    mirror = core.bridge.find_preset(MIRROR)

    assert (mirror.source_preset_id, mirror.name) == (ORIGIN, "Local one, mirrored")
    assert Path(mirror.path).resolve() == core.origin_dir.resolve()
    assert mirror.origin == core.bridge.find_preset(ORIGIN).origin == {"kind": "local", "plugin_id": None, "path": "Local/v1"}
    assert core.bridge.is_installed(MIRROR) and core.bridge.is_installed(ORIGIN)


def test_deleting_a_mirror_is_refused_before_anything_is_uninstalled_or_removed(core, roots):
    history = _load("backend.history")
    before = _tree(core.origin_dir)

    response = core.client.delete(f"{PRESETS_URL}/{MIRROR}")

    assert (response.status_code, core.origin_dir.is_dir()) == (409, True), response.text
    detail = response.json()["detail"]
    assert detail["error"] == "mirror"
    assert ORIGIN in detail["message"] and "Admin" in detail["message"]
    assert _tree(core.origin_dir) == before
    assert core.bridge.is_installed(MIRROR) and core.bridge.is_installed(ORIGIN)
    assert core.bridge.find_preset(ORIGIN) is not None and core.bridge.find_preset(MIRROR) is not None
    assert history.list_entries(roots, MIRROR) == [] and history.list_entries(roots, ORIGIN) == []


def test_deleting_the_source_of_a_mirror_is_refused_by_the_core_before_its_folder_is_removed(core, roots):
    history = _load("backend.history")
    before = _tree(core.origin_dir)

    with pytest.raises(Exception) as failure:
        core.client.delete(f"{PRESETS_URL}/{ORIGIN}")

    assert type(failure.value).__name__ == "PresetHasMirrorsError"
    assert _tree(core.origin_dir) == before
    assert core.bridge.is_installed(ORIGIN) and core.bridge.is_installed(MIRROR)
    assert history.list_entries(roots, ORIGIN) == []
