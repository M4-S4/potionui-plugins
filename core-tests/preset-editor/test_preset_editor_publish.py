import importlib
import importlib.util
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.features.presets.file_repository import FilePresetRepository
from src.features.presets.loader import PresetTemplateLoader
from src.features.presets.repository import DatabasePresetRepository
from src.features.presets.schema import PRESET_ID_RE
from src.features.users.repository import UserRepository
from src.plugin_api import AccountType, User

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / PLUGIN_ID
PACKAGE = "preset_editor"
NATIVE = PLUGIN_ROOT / "tests" / "fixtures" / "presets" / "minimal-native"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


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
    marketplace = tmp_path / "content" / "presets" / "marketplace"
    shutil.copytree(NATIVE, marketplace / "Fixture" / "native")
    loader = PresetTemplateLoader([str(marketplace), str(roots.local_presets)])
    loader.reload()
    file_repo = FilePresetRepository(loader)
    db_repo = DatabasePresetRepository()
    collaborators = SimpleNamespace(preset_loader=loader, file_repo=file_repo, db_repo=db_repo, plugins=_Plugins())
    container = SimpleNamespace(
        preset_template_loader=loader, file_preset_repository=file_repo, preset_collaborators=collaborators
    )
    core_bridge = _load("backend.core_bridge")
    monkeypatch.setattr(core_bridge, "get_container", lambda: container)
    return SimpleNamespace(bridge=core_bridge, loader=loader, db_repo=db_repo, marketplace=marketplace)


def _publish_copy(core, roots, *, preset_id="copy-one", name="Copy one", target="MyModel/v1"):
    drafts, publish = _load("backend.drafts"), _load("backend.publish")
    source = core.bridge.find_preset("fixture-minimal-native")
    draft = drafts.create_copy(
        roots, source_dir=Path(source.path), preset_id=preset_id, name=name, target_dir=target, created_by="admin-1",
        source="copy_of:fixture-minimal-native",
    )
    errors, _warnings = core.bridge.lint(draft.dir)
    assert errors == []
    publish.check_collisions(
        roots, preset_id=preset_id, target_dir=target, catalog=core.bridge.catalog(), disk_roots=core.bridge.preset_roots()
    )
    result = publish.publish_draft(roots, draft, history_depth=3)
    core.bridge.reload_presets()
    return draft, result


def test_the_plugin_preset_id_rule_is_the_cores():
    assert _load("backend.paths").PRESET_ID_RE.pattern == PRESET_ID_RE.pattern


def test_a_published_copy_is_loaded_by_the_core_and_can_be_installed(core, roots):
    draft, result = _publish_copy(core, roots)

    assert result == {"preset_id": "copy-one", "target_dir": "MyModel/v1", "archived": None}
    template = core.bridge.find_preset("copy-one")
    assert Path(template.path).resolve() == (roots.local_presets / "MyModel" / "v1").resolve()
    assert template.origin == {"kind": "local", "plugin_id": None, "path": "MyModel/v1"}
    assert (template.name, template.id, list(template.modes)) == ("Copy one", "copy-one", ["txt2img"])
    info = next(item for item in core.bridge.catalog() if item["id"] == "copy-one")
    assert (info["source"], info["origin"]["kind"], info["origin"]["path"]) == ("custom", "local", "MyModel/v1")
    assert core.loader.load_errors == {}

    assert core.bridge.is_installed("copy-one") is False
    core.bridge.install_preset("copy-one", ADMIN)
    assert core.bridge.is_installed("copy-one") is True


def test_a_duplicate_id_is_refused_before_anything_is_written(core, roots):
    drafts, publish = _load("backend.drafts"), _load("backend.publish")
    source = core.bridge.find_preset("fixture-minimal-native")
    draft = drafts.create_copy(
        roots, source_dir=Path(source.path), preset_id="fixture-minimal-native", name="Clash", target_dir="MyModel/v1",
        created_by="admin-1", source="copy_of:fixture-minimal-native",
    )

    with pytest.raises(publish.PublishError) as failure:
        publish.check_collisions(
            roots, preset_id=draft.preset_id, target_dir=draft.target_dir, catalog=core.bridge.catalog(),
            disk_roots=core.bridge.preset_roots(),
        )

    assert failure.value.code == "id_in_use"
    assert list(roots.local_presets.iterdir()) == []


def test_republishing_keeps_the_installation_and_the_assignments(core, roots):
    drafts, publish, history = _load("backend.drafts"), _load("backend.publish"), _load("backend.history")
    _publish_copy(core, roots)
    core.bridge.install_preset("copy-one", ADMIN)
    user = UserRepository().create(username="alice", email="alice@test.com", password_hash="x", account_type=AccountType.USER)
    assert core.db_repo.assign_preset_to_user("copy-one", user.id) is not None

    template = core.bridge.find_preset("copy-one")
    edit = drafts.create_edit(
        roots, source_dir=Path(template.path), preset_id="copy-one", name="Copy one", target_dir="MyModel/v1", created_by="admin-1"
    )
    manifest = edit.dir / "preset.yml"
    manifest.write_text(drafts.rewrite_top_level(manifest.read_text(encoding="utf-8"), {"name": "Copy one, edited"}), encoding="utf-8")
    assert core.bridge.lint(edit.dir)[0] == []
    publish.check_collisions(
        roots, preset_id="copy-one", target_dir="MyModel/v1", catalog=core.bridge.catalog(), disk_roots=core.bridge.preset_roots()
    )
    result = publish.publish_draft(roots, edit, history_depth=3)
    core.bridge.reload_presets()

    assert result["archived"] is not None
    assert core.bridge.find_preset("copy-one").name == "Copy one, edited"
    assert core.bridge.is_installed("copy-one") is True
    assert core.db_repo.get_preset_assignment_summary("copy-one")["total_assignments"] == 1
    assert [(e["reason"], e["name"]) for e in history.list_entries(roots, "copy-one")] == [("publish", "Copy one")]


def test_deleting_a_local_preset_uninstalls_it_and_archives_it(core, roots):
    publish, history = _load("backend.publish"), _load("backend.history")
    _publish_copy(core, roots)
    core.bridge.install_preset("copy-one", ADMIN)
    template = core.bridge.find_preset("copy-one")

    core.bridge.uninstall_preset("copy-one", ADMIN)
    stamp = publish.delete_local_preset(
        roots, preset_dir=Path(template.path), preset_id="copy-one", target_dir="MyModel/v1", history_depth=3
    )
    core.bridge.reload_presets()

    assert core.bridge.find_preset("copy-one") is None
    assert core.bridge.is_installed("copy-one") is False
    assert not (roots.local_presets / "MyModel").exists()
    assert [(e["stamp"], e["reason"]) for e in history.list_entries(roots, "copy-one")] == [(stamp, "delete")]
    assert [item["id"] for item in core.bridge.catalog()] == ["fixture-minimal-native"]
