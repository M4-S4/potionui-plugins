from backend import paths
from hooks import lifecycle_hooks
from src.plugin_api import HookContext


def _context():
    return HookContext(hook_name="plugin.lifecycle.boot", plugin_id="preset-editor", data={"plugin_id": "preset-editor"})


def test_on_boot_creates_the_folders_and_empties_the_staging_area(roots):
    roots.staging.mkdir(parents=True)
    (roots.staging / "left-over").mkdir()
    context = _context()

    assert lifecycle_hooks.on_boot(context) is context
    assert all(path.is_dir() for path in (roots.drafts, roots.history, roots.staging, roots.local_presets))
    assert list(roots.staging.iterdir()) == []


def test_on_boot_returns_the_context_when_the_folders_cannot_be_prepared(monkeypatch):
    def broken():
        raise OSError("read-only file system")

    monkeypatch.setattr(paths, "roots", broken)
    context = _context()

    assert lifecycle_hooks.on_boot(context) is context
