import dataclasses
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from src.features.presets.schema import PRESET_MEDIA_EXTENSIONS

PLUGIN_ID = "preset-editor"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / PLUGIN_ID
PACKAGE = "preset_editor"


@pytest.fixture(autouse=True)
def plugin_modules_removed_afterwards():
    modules, path = set(sys.modules), list(sys.path)
    try:
        yield
    finally:
        for name in set(sys.modules) - modules:
            if name.split(".")[0] in (PACKAGE, "preset_new"):
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


def _preset_new():
    spec = importlib.util.spec_from_file_location("preset_new", REPO_ROOT / "scripts" / "preset_new.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["preset_new"] = module
    spec.loader.exec_module(module)
    return module


def _tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*")) if path.is_file() and path.name != "description.md"
    }


CASES = [
    ("native", ["txt2img", "img2img"], None, None),
    ("comfyui", ["txt2img"], None, None),
    ("cloud", ["txt2img", "edit", "txt2video", "img2video"], "cloud.openrouter", None),
    ("native", ["txt2img", "img2img"], None, "z_image"),
]


@pytest.mark.parametrize("engine, modes, driver, family", CASES)
def test_the_plugin_skeleton_is_byte_identical_to_the_core_script(tmp_path, engine, modes, driver, family):
    preset_new = _preset_new()
    scaffold = _load("backend.scaffold")
    family_pipes = None
    if family:
        core_family = preset_new._load_family_pipes(family)
        family_pipes = scaffold.FamilyPipes(**{
            **dataclasses.asdict(core_family),
            "model_slots": tuple(core_family.model_slots),
            "sampler_choices": tuple(core_family.sampler_choices),
        })

    preset_new.scaffold(tmp_path / "core", "skeleton-test", "Skeleton", "image", engine, modes, False, family=family, driver=driver)
    scaffold.write_files(
        tmp_path / "plugin",
        scaffold.preset_files(preset_id="skeleton-test", name="Skeleton", category="image", engine=engine, modes=modes, driver=driver, family=family_pipes),
    )

    assert _tree(tmp_path / "plugin") == _tree(tmp_path / "core")
    assert (tmp_path / "plugin" / "description.md").is_file()


def test_the_plugin_media_extensions_are_the_cores():
    assert _load("backend.files").MEDIA_EXTENSIONS == PRESET_MEDIA_EXTENSIONS
