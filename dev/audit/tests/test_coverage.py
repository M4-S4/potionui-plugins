import json

import pytest

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.coverage import Live, ModelResolver, assess, form_field_names, live_state, uncovered, undeclared
from potion_audit.pack import PackError, load_pack, verify

from conftest import PASSWORD, SDXL_ID, USER, WAN_DIT_SHA
from packs import write_pack

CATALOG = '\n[[cells]]\npreset = "field-catalog-all-fields"\nmode = "catalog"\nexclude = "an inert development preset"\n'
SDXL_FORM = {"fields": [{"type": "tabs", "children": [{"type": "tab", "children": [
    {"name": "steps", "type": "slider", "default": 20},
    {"name": "resolution", "type": "resolution", "options": [{"value": "64x64", "label": "64"}]},
    {"name": "model", "type": "model", "configuration": {"recommendations": [{"name": "sdxl.safetensors"}]}},
    {"name": "source_image", "type": "image"},
]}]}]}


def logged_in(fake_api):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def cell(pack, cell_id):
    return next(item for item in pack.cells if item.id == cell_id)


def test_a_cell_whose_mode_the_instance_no_longer_offers_is_mode_missing(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.sdxl_modes = ["img2img"]
    fake_api.sdxl_vars = {"retired_modes": {"txt2img": "img2img"}}
    client = logged_in(fake_api)
    entry = assess(pack, cell(pack, "core/SDXL:txt2img"), ModelResolver(client), live_state(client))
    assert entry["status"] == "mode_missing"
    assert entry["reason"] == "the instance offers no mode 'txt2img' for this preset, which replaced it with 'img2img'; its modes: img2img"


def test_a_cell_whose_mode_the_instance_offers_is_assessed_as_before(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    client = logged_in(fake_api)
    assert assess(pack, cell(pack, "core/SDXL:txt2img"), ModelResolver(client), live_state(client))["status"] == "ready"


def test_check_and_dry_run_give_a_retired_mode_its_own_status_and_no_request(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    fake_api.sdxl_modes = ["img2img"]
    fake_api.models[WAN_DIT_SHA] = "M-WAN-DIT"
    assert main(["check", "--config", str(config_file), "--pack", str(path)]) == 0
    preflight = json.loads((tmp_path / "out" / "preflight" / "preflight.json").read_text(encoding="utf-8"))
    statuses = {item["id"]: item["status"] for item in preflight["pack"]["cells"]}
    assert statuses["core/SDXL:txt2img"] == "mode_missing"
    assert statuses["core/SDXL:txt2img/edit"] == "mode_missing"
    assert "mode_missing" in (tmp_path / "out" / "preflight" / "preflight.html").read_text(encoding="utf-8")
    assert main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "full", "--dry-run", "--run-id", "plan-gone"]) == 0
    plan = json.loads((tmp_path / "out" / "plan-gone" / "plan.json").read_text(encoding="utf-8"))
    sdxl = [entry for entry in plan["cells"] if entry["preset"] == "core/SDXL"]
    assert [(entry["status"], "request" in entry) for entry in sdxl] == [("mode_missing", False), ("mode_missing", False)]
    assert "no mode 'txt2img'" in sdxl[0]["reason"]
    assert not (tmp_path / "out" / "plan-gone" / "cells" / "core-SDXL--txt2img").exists()


def test_an_exclusion_can_name_by_id_a_preset_the_case_file_does_not_hold(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file, extra=CATALOG))
    excluded = cell(pack, "field-catalog-all-fields:catalog")
    assert (excluded.preset_id, excluded.status) == ("field-catalog-all-fields", "excluded")
    assert [problem for problem in verify(pack, allow_pending=True) if problem.severity == "error"] == []
    live = Live(presets={"field-catalog-all-fields": {"installed": True, "modes": ["catalog", "other"], "engine": "native", "name": "Catalog"}}, enabled_plugins=frozenset(), vram_gb=12.0)
    assert [(item["mode"], item["status"]) for item in uncovered(pack, live)] == [("other", "no_case")]


@pytest.mark.parametrize("extra", [
    '\n[[cells]]\npreset = "field-catalog-all-fields"\nmode = "catalog"\nprofiles = ["full"]\n',
    '\n[[cells]]\npreset = "core/FieldCatalog"\nmode = "catalog"\nexclude = "unknown"\n',
])
def test_only_an_exclusion_named_by_id_may_lie_outside_the_case_file(tmp_path, case_file, extra):
    with pytest.raises(PackError, match="no preset"):
        load_pack(write_pack(tmp_path, case_file, extra=extra))


def test_form_field_names_take_named_fields_only():
    assert form_field_names(SDXL_FORM) == {"steps", "resolution", "model", "source_image"}


def test_undeclared_keeps_what_the_server_would_strip():
    declared = {"steps", "source_image"}
    sent = {"steps", "seed", "source_image_inpaint_mask", "source_image__origin", "video_director", "music_director", "frames_inpaint_mask", "audio_vae"}
    assert undeclared(sent, declared) == ["audio_vae", "frames_inpaint_mask", "seed"]


def test_check_lists_the_fields_a_cell_sends_that_its_form_does_not_declare(fake_api, config_file, credentials_env, tmp_path, case_file, capsys):
    path = write_pack(tmp_path, case_file)
    fake_api.forms[(SDXL_ID, "txt2img")] = SDXL_FORM
    assert main(["check", "--config", str(config_file), "--pack", str(path)]) == 0
    preflight = json.loads((tmp_path / "out" / "preflight" / "preflight.json").read_text(encoding="utf-8"))
    cells = {item["id"]: item for item in preflight["pack"]["cells"]}
    assert cells["core/SDXL:txt2img"]["undeclared_fields"] == ["seed"]
    assert cells["core/SDXL:txt2img/edit"]["undeclared_fields"] == ["references", "seed"]
    assert "core/Wan:video" in cells and "undeclared_fields" not in cells["core/Wan:video"]
    assert "Mode 'video' not found" in cells["core/Wan:video"]["form_error"]
    assert "undeclared_fields" not in cells["core/ModelTools:*"]
    assert cells["core/SDXL:txt2img"]["status"] == "ready"
    out = capsys.readouterr().out
    assert "warning: core/SDXL:txt2img/edit sends fields its form on the instance does not declare: references, seed" in out
    assert "fields the form does not declare: seed" in (tmp_path / "out" / "preflight" / "preflight.html").read_text(encoding="utf-8")
    assert all(method == "GET" for method, route in fake_api.methods() if route != "/api/auth/login")
