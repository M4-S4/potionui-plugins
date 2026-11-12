import inspect
from pathlib import Path

import pytest
import yaml

from .conftest import H3_12GB_ID, H3_FAST_12GB_ID, FakeCore

PLUGIN = Path(__file__).resolve().parents[1]
SHARED = PLUGIN.parents[2] / "presets" / "_shared"
MEANINGFUL = ("speed_profile", "resolution", "frames", "steps", "source_video")
TWELVE_GB = {H3_12GB_ID: "MiniMax-H3-12GB", H3_FAST_12GB_ID: "MiniMax-H3-Fast-12GB"}
USES = sorted(name for name, method in inspect.getmembers(FakeCore, inspect.isfunction) if name.startswith("use_") and len(inspect.signature(method).parameters) == 1)


def _path(text, preset):
    return Path(text.replace("{{ paths.preset }}", str(preset)).replace("{{ paths._shared }}", str(SHARED)))


def _walk(items, preset, found):
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if "name" in item:
            found[item["name"]] = item
        children = item.get("children")
        if isinstance(children, str):
            _walk(yaml.safe_load(_path(children, preset).read_text(encoding="utf-8")).get("fields"), preset, found)
        elif isinstance(children, list):
            _walk(children, preset, found)
    return found


def real_fields(folder, mode):
    preset = PLUGIN / "presets" / folder
    form = yaml.safe_load((preset / "modes" / mode / "form.yml").read_text(encoding="utf-8"))
    return preset, _walk(form["fields"], preset, {})


def real_sizes(field, preset):
    values = [entry["value"] for item in field["configuration"]["files"] for entry in yaml.safe_load(_path(item["path"], preset).read_text(encoding="utf-8"))]
    return list(dict.fromkeys(values))


def test_the_check_reaches_every_double_of_a_12_gb_preset(core):
    reached = set()
    for use in USES:
        getattr(core, use)()
        reached |= {key for key in core.fields if key[0] in TWELVE_GB}

    assert reached == {(H3_12GB_ID, "video"), (H3_12GB_ID, "refs"), (H3_12GB_ID, "extend"), (H3_FAST_12GB_ID, "video"), (H3_FAST_12GB_ID, "extend")}


@pytest.mark.parametrize("use", USES)
def test_the_fields_the_tests_give_a_12_gb_preset_are_those_of_its_real_form(core, use):
    getattr(core, use)()

    for (preset_id, mode), fixture in core.fields.items():
        if preset_id not in TWELVE_GB:
            continue
        folder = TWELVE_GB[preset_id]
        preset, real = real_fields(folder, mode)
        for name, spec in fixture.items():
            assert name in real, (folder, mode, name)
            field = real[name]
            assert spec["type"] == field["type"], (folder, mode, name)
            assert spec["default"] == field.get("default"), (folder, mode, name)
            if spec["type"] == "select":
                assert [option["value"] for option in spec["options"]] == [option["value"] for option in field["configuration"]["options"]], (folder, mode, name)
            if spec["type"] == "resolution":
                assert [option["value"] for option in spec["options"]] == real_sizes(field, preset), (folder, mode, name)
        assert [name for name in MEANINGFUL if name in real] == [name for name in MEANINGFUL if name in fixture], (folder, mode)
