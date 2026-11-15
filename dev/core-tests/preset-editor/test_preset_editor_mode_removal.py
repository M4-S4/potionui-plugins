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
H3 = REPO_ROOT / "content" / "presets" / "marketplace" / "MiniMax-H3"
PREFIX = "/api/plugins/preset-editor/drafts"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)

if not (H3 / "preset.yml").is_file() or "simple_modes" not in (H3 / "preset.yml").read_text(encoding="utf-8"):
    pytest.skip("the MiniMax-H3 preset of this core names no simple mode", allow_module_level=True)


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
def draft(tmp_path, monkeypatch):
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
    return drafts.create_copy(
        roots, source_dir=H3, preset_id="pe-check-h3", name="H3 check", target_dir="PECheck/h3",
        created_by=ADMIN.id, source="copy_of:minimax-h3",
    )


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(_load("backend.api").router)
    app.dependency_overrides[get_current_admin_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client


def _tree(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


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
    assert _tree(draft.dir) == before


def test_the_removal_check_of_the_shared_video_mode_gives_the_refusal(client, draft):
    check = client.get(f"{PREFIX}/{draft.draft_id}/modes/video/removal")

    data = check.json()["data"]
    assert data["allowed"] is False
    assert data["message"].startswith(
        "The mode video cannot be removed: modes/first_last/pipeline.yml, modes/img2video/pipeline.yml and "
        "modes/txt2video/pipeline.yml take their pipeline from it, and "
    )
    assert data["message"].endswith(" load its files. Point them elsewhere first.")
    assert client.delete(f"{PREFIX}/{draft.draft_id}/modes/video").json()["detail"]["message"] == data["message"]
