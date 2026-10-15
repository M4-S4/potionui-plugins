import os
from pathlib import Path

from backend import paths


def test_default_roots_hang_off_the_storage_directory_and_the_core_preset_tree(monkeypatch):
    monkeypatch.setattr(paths, "storage_dir", lambda: Path("/srv/potionui/storage"))

    roots = paths.default_roots()

    assert roots.drafts == Path("/srv/potionui/storage/plugins/preset-editor/drafts")
    assert roots.history == Path("/srv/potionui/storage/plugins/preset-editor/history")
    assert roots.staging == Path("content/presets/.preset-editor/staging")
    assert roots.local_presets == Path("content/presets/local")


def test_roots_are_computed_once(monkeypatch):
    calls = []
    monkeypatch.setattr(paths, "_current", None)
    monkeypatch.setattr(paths, "storage_dir", lambda: calls.append(1) or Path("storage"))

    assert paths.roots() is paths.roots()
    assert calls == [1]


def test_ensure_creates_every_root(roots):
    roots.ensure()

    assert all(path.is_dir() for path in (roots.drafts, roots.history, roots.staging, roots.local_presets))


def test_clear_staging_removes_entries_but_keeps_the_folder(roots):
    roots.ensure()
    (roots.staging / "abandoned").mkdir()
    (roots.staging / "abandoned" / "preset.yml").write_text("schema: 1\n", encoding="utf-8")
    (roots.staging / "stray.tmp").write_text("", encoding="utf-8")

    assert paths.clear_staging(roots) == 2
    assert roots.staging.is_dir()
    assert list(roots.staging.iterdir()) == []


def test_clear_staging_unlinks_a_symlink_without_following_it(roots):
    roots.ensure()
    target = roots.drafts / "keep"
    target.mkdir(parents=True)
    (target / "preset.yml").write_text("schema: 1\n", encoding="utf-8")
    try:
        os.symlink(target, roots.staging / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return

    assert paths.clear_staging(roots) == 1
    assert (target / "preset.yml").exists()


def test_clear_staging_without_a_staging_folder_does_nothing(roots):
    assert paths.clear_staging(roots) == 0
