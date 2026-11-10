import importlib
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

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


@pytest.fixture
def marketplace(tmp_path):
    root = tmp_path / "content" / "presets" / "marketplace"
    shutil.copytree(FIXTURES / "minimal-native", root / "Fixture" / "native")
    return root


def template(preset_id, path, *, kind="marketplace", origin_path="Fixture/native", name="Minimal native", **extra):
    return SimpleNamespace(
        id=preset_id,
        name=name,
        version="1.0.0",
        path=str(path),
        engine="native",
        category="image",
        modes={"txt2img": None},
        origin={"kind": kind, "plugin_id": None, "path": origin_path},
        **extra,
    )


def read_header(preset_dir):
    import yaml

    return yaml.safe_load((Path(preset_dir) / "preset.yml").read_text(encoding="utf-8"))


def read_id(preset_dir):
    return read_header(preset_dir)["id"]


@pytest.fixture
def core(monkeypatch, roots, marketplace):
    from backend import core_bridge, settings

    state = SimpleNamespace(
        templates={"fixture-minimal-native": template("fixture-minimal-native", marketplace / "Fixture" / "native")},
        lint=([], ["[WARNING] preset.yml: no tests.yml"]),
        lint_calls=[],
        reloads=0,
        reload_registers=True,
        load_errors={},
        installed=set(),
        installs=[],
        uninstalls=[],
        settings={"history_depth": 10, "install_after_publish": True},
    )

    def catalog():
        return [
            {
                "id": item.id,
                "name": item.name,
                "version": item.version,
                "origin": dict(item.origin),
                "source": "custom" if item.origin["kind"] == "local" else "official",
            }
            for item in state.templates.values()
        ]

    def rescan_local():
        state.templates = {k: v for k, v in state.templates.items() if v.origin["kind"] != "local"}
        if not state.reload_registers:
            return
        for manifest in sorted(roots.local_presets.rglob("preset.yml")):
            relative = manifest.parent.relative_to(roots.local_presets).as_posix()
            header = read_header(manifest.parent)
            state.templates[header["id"]] = template(
                header["id"], manifest.parent, kind="local", origin_path=relative, name=header["name"]
            )

    async def lint_async(path):
        state.lint_calls.append(Path(path))
        return state.lint

    async def reload_presets_async():
        state.reloads += 1
        rescan_local()

    def install_preset(preset_id, user):
        state.installs.append((preset_id, user.id))
        state.installed.add(preset_id)
        return {"preset_id": preset_id}

    def uninstall_preset(preset_id, user):
        state.uninstalls.append((preset_id, user.id))
        state.installed.discard(preset_id)
        return {"message": f"Preset '{preset_id}' uninstalled successfully. Removed 0 user assignments.", "tombstone": None}

    monkeypatch.setattr(core_bridge, "find_preset", lambda preset_id: state.templates.get(preset_id))
    monkeypatch.setattr(core_bridge, "catalog", catalog)
    monkeypatch.setattr(core_bridge, "preset_roots", lambda: [marketplace, roots.local_presets])
    monkeypatch.setattr(core_bridge, "lint_async", lint_async)
    monkeypatch.setattr(core_bridge, "reload_presets_async", reload_presets_async)
    monkeypatch.setattr(core_bridge, "load_errors", lambda: {Path(key).resolve(): list(value) for key, value in state.load_errors.items()})
    monkeypatch.setattr(core_bridge, "is_installed", lambda preset_id: preset_id in state.installed)
    monkeypatch.setattr(core_bridge, "install_preset", install_preset)
    monkeypatch.setattr(core_bridge, "uninstall_preset", uninstall_preset)
    monkeypatch.setattr(settings, "get_setting", lambda key: state.settings[key])
    state.rescan_local = rescan_local
    return state
