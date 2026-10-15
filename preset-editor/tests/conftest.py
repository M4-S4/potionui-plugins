import importlib
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PLUGIN_ROOT / "tests" / "fixtures" / "presets"

for _key in list(sys.modules):
    if _key.split(".", 1)[0] in ("backend", "hooks"):
        del sys.modules[_key]

if str(PLUGIN_ROOT) in sys.path:
    sys.path.remove(str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT))

importlib.invalidate_caches()
import backend  # noqa: E402,F401


@pytest.fixture
def roots(tmp_path, monkeypatch):
    from backend import paths

    current = paths.Roots(
        drafts=tmp_path / "storage" / "plugins" / "preset-editor" / "drafts",
        history=tmp_path / "storage" / "plugins" / "preset-editor" / "history",
        staging=tmp_path / "content" / "presets" / ".preset-editor" / "staging",
        local_presets=tmp_path / "content" / "presets" / "local",
    )
    monkeypatch.setattr(paths, "_current", current)
    return current
