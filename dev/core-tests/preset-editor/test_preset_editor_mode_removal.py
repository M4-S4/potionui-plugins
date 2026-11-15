import importlib
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.plugin_api import AccountType, User, get_current_admin_user

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / PLUGIN_ID for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "preset_editor"
MARKETPLACE = REPO_ROOT / "content" / "presets" / "marketplace"
H3 = MARKETPLACE / "MiniMax-H3"
SDXL = MARKETPLACE / "SDXL"
PREFIX = "/api/plugins/preset-editor/drafts"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)

H3_SIMPLE = (H3 / "preset.yml").is_file() and "simple_modes" in (H3 / "preset.yml").read_text(encoding="utf-8")
needs_simple_modes = pytest.mark.skipif(not H3_SIMPLE, reason="the MiniMax-H3 preset of this core names no simple mode")


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
def copy_of(tmp_path, monkeypatch):
    paths = _load("backend.paths")
    drafts = _load("backend.drafts")
    roots = paths.Roots(
        drafts=tmp_path / "storage" / "drafts",
        history=tmp_path / "storage" / "history",
        staging=tmp_path / "content" / "presets" / ".preset-editor" / "staging",
        local_presets=tmp_path / "content" / "presets" / "local",
    )
    roots.ensure()
    monkeypatch.setattr(paths, "_current", roots)

    def make(source):
        name = source.name.lower()
        return drafts.create_copy(
            roots, source_dir=source, preset_id=f"pe-check-{name}", name=f"{source.name} check", target_dir=f"PECheck/{name}",
            created_by=ADMIN.id, source=f"copy_of:{name}",
        )

    return make


@pytest.fixture
def draft(copy_of):
    return copy_of(H3)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(_load("backend.api").router)
    app.dependency_overrides[get_current_admin_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client


def _tree(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


@needs_simple_modes
@pytest.mark.parametrize("mode, named", [("first_last", "vars.video_director.simple_modes.first_last"), ("loop", "prompt_syntax.loop")])
def test_the_removal_check_names_what_the_core_lint_reports_once_the_mode_is_gone(client, draft, mode, named):
    if mode not in (draft.dir / "preset.yml").read_text(encoding="utf-8"):
        pytest.skip(f"the MiniMax-H3 preset of this core has no {mode} mode")
    before = _tree(draft.dir)

    check = client.get(f"{PREFIX}/{draft.draft_id}/modes/{mode}/removal")

    assert check.status_code == 200, check.text
    data = check.json()["data"]
    assert data["allowed"] is True
    assert [error for error in data["errors"] if named in error], data["errors"]
    assert [issue for issue in data["errors"] + data["warnings"] if draft.draft_id in issue] == []
    assert _tree(draft.dir) == before


@needs_simple_modes
def test_the_removal_check_of_the_shared_video_mode_gives_the_refusal(client, draft):
    check = client.get(f"{PREFIX}/{draft.draft_id}/modes/video/removal")

    data = check.json()["data"]
    assert data["allowed"] is False
    assert data["message"].startswith(
        "The mode video cannot be removed: modes/first_last/pipeline.yml, modes/img2video/pipeline.yml and "
        "modes/txt2video/pipeline.yml take their pipeline from it, and "
    )
    assert data["message"].endswith(" load its files. Point them elsewhere, or remove those lines, first.")
    assert client.delete(f"{PREFIX}/{draft.draft_id}/modes/video").json()["detail"]["message"] == data["message"]


def test_the_removal_check_names_the_errors_of_the_lint_of_this_core_and_only_new_ones(client, copy_of):
    assert (SDXL / "modes" / "control").is_dir(), "the SDXL preset of this core has no control mode"
    draft = copy_of(SDXL)
    before = _tree(draft.dir)

    check = client.get(f"{PREFIX}/{draft.draft_id}/modes/control/removal")

    data = check.json()["data"]
    assert check.status_code == 200, check.text
    assert data["allowed"] is True
    assert [error for error in data["errors"] if "case 'sdxl-structure-pose-fast': mode 'control' is not declared" in error], data["errors"]
    assert [issue for issue in data["errors"] + data["warnings"] if draft.draft_id in issue or "preset-editor-removal-" in issue] == []
    assert _tree(draft.dir) == before
    removed = client.delete(f"{PREFIX}/{draft.draft_id}/modes/control")
    assert removed.status_code == 200, removed.text
    left = [issue for issue in removed.json()["data"]["lint"]["errors"] if "control" in issue]
    assert len(left) == len(data["errors"])
