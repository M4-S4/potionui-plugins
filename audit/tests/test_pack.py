import json
import tomllib

import pytest

from potion_audit.cli import main
from potion_audit.pack import (
    PackError,
    build_cell_request,
    cell_models,
    dry_media,
    estimate,
    included,
    load_pack,
    run_order,
    set_input_facts,
    toml_value,
    verify,
)

from conftest import MISSING_SHA, SDXL_ID, SDXL_SHA, WAN_DIT_SHA, WAN_ID, WAN_VAE_SHA
from packs import write_pack


def cell(pack, cell_id):
    return next(item for item in pack.cells if item.id == cell_id)


def errors(problems):
    return [problem for problem in problems if problem.severity == "error"]


def messages(problems):
    return " | ".join(f"{problem.where}: {problem.message}" for problem in problems)


@pytest.fixture
def pack(tmp_path, case_file):
    return load_pack(write_pack(tmp_path, case_file))


def test_the_pack_reads_its_cells_with_their_kind(pack):
    assert pack.id == "potion-test"
    assert [item.id for item in pack.cells] == ["core/SDXL:txt2img", "core/Wan:video", "core/SDXL:txt2img/edit", "core/ModelTools:*"]
    assert [item.status for item in pack.cells] == ["case", "corrected", "new", "excluded"]
    assert cell(pack, "core/SDXL:txt2img").preset_id == SDXL_ID


def test_a_correct_pack_verifies_with_pending_inputs_allowed(pack):
    problems = verify(pack, allow_pending=True)
    assert errors(problems) == [], messages(problems)
    assert [problem.where for problem in problems if problem.severity == "pending"] == ["input mask"]


def test_a_pending_input_is_an_error_unless_allowed(pack):
    assert [problem.where for problem in errors(verify(pack))] == ["input mask"]


def test_pack_verify_exits_with_one_on_an_error_and_zero_when_clean(tmp_path, case_file, capsys):
    path = write_pack(tmp_path, case_file)
    assert main(["pack", "verify", "--pack", str(path)]) == 1
    assert "input mask" in capsys.readouterr().out
    assert main(["pack", "verify", "--pack", str(path), "--allow-pending"]) == 0


@pytest.mark.parametrize(
    "replace, expected",
    [
        ({'size_bytes = ': 'size_bytes = 1'}, "bytes, the pack says"),
        ({'sha256 = "': 'sha256 = "0'}, "is not 64 lowercase hex digits"),
        ({'prompt = "t2v"': 'prompt = "nope"'}, "no prompt 'nope'"),
        ({'positive = "slow push-in on {bottle}"': 'positive = "slow push-in on {cauldron}"'}, "the bible does not define"),
        ({'source_image = "bottle"': 'source_image = "ghost"'}, "names no input 'ghost'"),
        ({'case = "wan-t2v"': 'case = "wan-missing"'}, "no case 'wan-missing'"),
        ({'profiles = ["full"]\nsources': 'profiles = ["smoke"]\nsources'}, "more than one smoke cell"),
        ({'alternatives = [': 'alternatives = ["xyz", '}, "is not a sha256"),
        ({'repeat_warm = true': 'repeat_warm = true\ncolour = "red"'}, "unknown keys: colour"),
    ],
)
def test_verify_reports_each_kind_of_error(tmp_path, case_file, replace, expected):
    try:
        pack = load_pack(write_pack(tmp_path, case_file, replace=replace))
    except PackError as error:
        assert expected in str(error)
        return
    assert expected in messages(errors(verify(pack, allow_pending=True)))


def test_a_missing_input_file_is_an_error(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    pack.input_path("bottle").unlink()
    assert "inputs/bottle.png is missing" in messages(errors(verify(pack, allow_pending=True)))


def test_a_mode_without_a_cell_is_an_error(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file, replace={'[[cells]]\npreset = "core/ModelTools"\nmode = "*"\nexclude = "writes into the model store"\n': ''}))
    assert "mode convert has no cell" in messages(errors(verify(pack, allow_pending=True)))


def test_a_cell_defined_twice_is_an_error(tmp_path, case_file):
    extra = '\n[[cells]]\npreset = "core/Wan"\nmode = "video"\ncase = "wan-t2v"\nprompt = "t2v"\nprofiles = ["full"]\n'
    pack = load_pack(write_pack(tmp_path, case_file, extra=extra))
    assert "defined twice" in messages(errors(verify(pack, allow_pending=True)))


def test_a_case_negative_prompt_needs_a_pack_negative(tmp_path, case_file):
    data = json.loads(case_file.read_text(encoding="utf-8"))
    for case in data["cases"]:
        if case["name"] == "sdxl-fast":
            case["form"]["negative_prompt"] = "ugly"
    case_file.write_text(json.dumps(data), encoding="utf-8")
    pack = load_pack(write_pack(tmp_path, case_file, replace={'negative = "plain"\n': ''}))
    assert "has a negative prompt" in messages(errors(verify(pack, allow_pending=True)))


def test_an_unbound_placeholder_is_an_error(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file, replace={'form = {steps = 4}': 'form = {steps = 4, pictures = ["PLACEHOLDER/a.png"]}'}))
    assert "pictures[0] still hold a PLACEHOLDER value" in messages(errors(verify(pack, allow_pending=True)))


def test_a_changed_case_file_no_longer_matches_the_pack(tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    case_file.write_text(case_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert "the pack says" in messages(errors(verify(load_pack(path), allow_pending=True)))


def test_a_case_cell_takes_the_pack_prompt_negative_and_seed(pack):
    request = build_cell_request(pack, cell(pack, "core/SDXL:txt2img"), {"model": "M-SDXL"}, {}, "r1", dry_media)
    assert request["prompts"] == [{"positive": "a violet potion bottle, candlelight", "negative": "blurry"}]
    assert request["form_data"] == {"steps": 4, "resolution": "64x64", "seed": 12345, "model": "model:M-SDXL"}
    assert request["idempotency_key"] == "potion-audit-r1-core_SDXL_txt2img"


def test_a_corrected_cell_drops_overrides_and_builds_the_director_document(pack):
    target = cell(pack, "core/Wan:video")
    refs = {ref.field: ref for ref in cell_models(pack, target)}
    assert refs["t2v_high_noise_model"].sha256 == WAN_DIT_SHA
    assert refs["text_encoder"].sha256 == MISSING_SHA
    assert refs["text_encoder"].alternatives == (WAN_VAE_SHA,)
    detail = {"vars": {"video_director": {"preset_modes": ["video"], "limits": {"default_duration": 5, "default_fps": 16}}}}
    request = build_cell_request(pack, target, {"vae": "M-VAE"}, detail, "r1", dry_media)
    form = request["form_data"]
    assert "resolution" not in form
    assert form["expert_boundary_preset"] == "0.875"
    assert form["video_director"]["segments"][0]["prompt"] == "slow push-in on a violet potion bottle"
    assert form["video_director"]["settings"] == {"duration": 5.0, "fps": 16, "seed": 12345}


def test_a_new_cell_copies_models_and_binds_inputs(pack):
    target = cell(pack, "core/SDXL:txt2img/edit")
    assert [ref.sha256 for ref in cell_models(pack, target)] == [SDXL_SHA]
    request = build_cell_request(pack, target, {"model": "M-SDXL"}, {}, "r1", dry_media)
    form = request["form_data"]
    assert form["seed"] == 7
    assert form["steps"] == 4
    assert form["source_image"] == "input:bottle"
    assert form["source_image_inpaint_mask"] == "input:mask"
    assert form["references"] == ["input:bottle"]


def test_a_real_binding_places_the_media_item_or_its_path(pack):
    item = {"path": "storage/uploads/1-bottle.png", "relative_path": "uploads/1-bottle.png", "url": "/u", "name": "bottle.png", "type": "image", "metadata": {}}
    request = build_cell_request(pack, cell(pack, "core/SDXL:txt2img/edit"), {}, {}, "r1", lambda input_id, as_path: item)
    form = request["form_data"]
    assert form["source_image"] == item
    assert form["source_image_inpaint_mask"] == "storage/uploads/1-bottle.png"
    assert form["references"] == [item]


def test_a_binding_into_a_director_document_keeps_its_media_shape(tmp_path, case_file):
    document = '{schema_version = 1, mode = "flf", settings = {fps = 24, duration = 5.0, seed = -1}, segments = [{id = "s1", prompt = "old"}], media = [{id = "m1", role = "first", media = {path = "PLACEHOLDER/first.png", type = "image"}}]}'
    pack = load_pack(write_pack(tmp_path, case_file, replace={'form = {steps = 4}': f"form = {{steps = 4, video_director = {document}}}", '"references[0]" = "bottle"': '"video_director.media[0].media" = "bottle"'}))
    item = {"path": "storage/uploads/1-bottle.png", "relative_path": "uploads/1-bottle.png", "url": "/u", "name": "bottle.png", "type": "image", "metadata": {}}
    request = build_cell_request(pack, cell(pack, "core/SDXL:txt2img/edit"), {}, {}, "r1", lambda input_id, as_path: item)
    document = request["form_data"]["video_director"]
    assert document["media"][0]["media"] == {"path": "storage/uploads/1-bottle.png", "type": "image", "relative_path": "uploads/1-bottle.png"}
    assert document["segments"][0]["prompt"] == "a violet potion bottle, candlelight"


def test_a_prompt_can_set_extra_form_fields(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file, replace={'prompt = "image"\nseed = 7': 'prompt = "song"\nseed = 7'}))
    request = build_cell_request(pack, cell(pack, "core/SDXL:txt2img/edit"), {}, {}, "r1", dry_media)
    assert request["prompts"][0]["positive"] == "[Verse]\nla la"
    assert request["form_data"]["style"] == "folk, candlelight"


def test_excluded_cells_belong_to_no_profile(pack):
    assert [item.id for item in included(pack.cells, "smoke")] == ["core/SDXL:txt2img", "core/Wan:video"]
    assert "core/ModelTools:*" not in [item.id for item in included(pack.cells, "full")]


def test_the_run_order_groups_a_preset_and_repeats_video_warm_in_full_only(pack):
    full = [(item.id, warm) for item, warm in run_order(included(pack.cells, "full"), "full")]
    assert full == [("core/SDXL:txt2img", False), ("core/SDXL:txt2img/edit", False), ("core/Wan:video", False), ("core/Wan:video", True)]
    smoke = [(item.id, warm) for item, warm in run_order(included(pack.cells, "smoke"), "smoke")]
    assert smoke == [("core/SDXL:txt2img", False), ("core/Wan:video", False)]


def test_estimates_take_the_cold_or_warm_average_and_fall_back(pack):
    timing = {"avg_cold_duration_ms": 30000.0, "avg_warm_duration_ms": 10000.0}
    assert estimate(timing, warm=False) == 30.0
    assert estimate(timing, warm=True) == 10.0
    assert estimate({"avg_cold_duration_ms": 30000.0, "avg_warm_duration_ms": None}, warm=True) == 30.0
    assert estimate(None, warm=False) is None


def test_input_facts_are_written_back_into_the_pack(tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    text = set_input_facts(path.read_text(encoding="utf-8"), "mask", {"sha256": "f" * 64, "size_bytes": 42, "origin": {"method": "transform", "op": "rect_mask"}})
    data = tomllib.loads(text)
    assert data["inputs"]["mask"]["sha256"] == "f" * 64
    assert data["inputs"]["mask"]["size_bytes"] == 42
    assert data["inputs"]["mask"]["origin"] == {"method": "transform", "op": "rect_mask"}
    assert data["inputs"]["mask"]["make"]["op"] == "rect_mask"
    assert data["inputs"]["bottle"] == tomllib.loads(path.read_text(encoding="utf-8"))["inputs"]["bottle"]


def test_toml_values_round_trip():
    value = {"plain": "a \"quoted\"\nline", "n": 3, "f": 0.5, "flag": True, "list": ["x", 1], "video_director.media[0]": "y"}
    assert tomllib.loads(f"v = {toml_value(value)}")["v"] == value


def test_the_shipped_pack_verifies_with_its_inputs_pending():
    from potion_audit.pack import DEFAULT_PACK

    pack = load_pack(DEFAULT_PACK)
    problems = verify(pack, allow_pending=True)
    assert errors(problems) == [], messages(errors(problems))
    assert pack.case_set.source["ref"].startswith("02cce6fdd")
    assert all(cell.profiles or cell.exclude for cell in pack.cells)


def test_the_check_adds_the_pack_coverage(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    fake_api.models[WAN_DIT_SHA] = "M-WAN-DIT"
    code = main(["check", "--config", str(config_file), "--pack", str(path)])
    assert code == 0
    preflight = json.loads((tmp_path / "out" / "preflight" / "preflight.json").read_text(encoding="utf-8"))
    statuses = {item["id"]: item["status"] for item in preflight["pack"]["cells"]}
    assert statuses == {"core/SDXL:txt2img": "ready", "core/Wan:video": "beyond_tier", "core/SDXL:txt2img/edit": "input_pending", "core/ModelTools:*": "excluded"}
    wan = next(item for item in preflight["pack"]["cells"] if item["id"] == "core/Wan:video")
    text_encoder = next(model for model in wan["models"] if model["field"] == "text_encoder")
    assert text_encoder["by"] == "sha256, alternative 1"
    assert "Pack potion-test" in (tmp_path / "out" / "preflight" / "preflight.html").read_text(encoding="utf-8")
    assert all(method == "GET" for method, path in fake_api.methods() if path != "/api/auth/login")


def test_the_coverage_marks_missing_models_inactive_plugins_and_uninstalled_presets(fake_api, tmp_path, case_file):
    from potion_audit.client import ApiClient
    from potion_audit.coverage import ModelResolver, assess, live_state
    from conftest import PASSWORD, USER

    extra = '\n[[cells]]\npreset = "core/Wan"\nmode = "video"\nvariant = "rtx"\ncase = "wan-t2v"\nprompt = "t2v"\nprofiles = ["full"]\nrequires_plugin = "nvidia-rtx-upscale"\n'
    pack = load_pack(write_pack(tmp_path, case_file, extra=extra))
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    fake_api.vram_gb = 24.0
    live = live_state(client)
    del fake_api.models[WAN_DIT_SHA]
    resolver = ModelResolver(client)
    assert assess(pack, cell(pack, "core/Wan:video"), resolver, live)["status"] == "model_missing"
    fake_api.models[WAN_DIT_SHA] = "M-WAN-DIT"
    assert assess(pack, cell(pack, "core/Wan:video"), ModelResolver(client), live)["status"] == "ready"
    assert assess(pack, cell(pack, "core/Wan:video/rtx"), resolver, live)["status"] == "plugin_inactive"
    del live.presets[WAN_ID]
    assert assess(pack, cell(pack, "core/Wan:video"), resolver, live)["status"] == "preset_not_installed"


def test_a_model_without_sha256_is_found_by_its_file_name(fake_api, tmp_path, case_file):
    from potion_audit.client import ApiClient
    from potion_audit.coverage import ModelResolver, assess, live_state
    from conftest import PASSWORD, USER

    pack = load_pack(write_pack(tmp_path, case_file, replace={'models_from = "sdxl-fast"': 'models_from = "sdxl-fast"\nmodels = {style_lora = {filename = "potion-style.safetensors"}}'}))
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    live = live_state(client)
    first = assess(pack, cell(pack, "core/SDXL:txt2img/edit"), ModelResolver(client), live)
    assert first["status"] == "model_missing"
    fake_api.named_models["potion-style.safetensors"] = "M-STYLE"
    second = assess(pack, cell(pack, "core/SDXL:txt2img/edit"), ModelResolver(client), live)
    lora = next(model for model in second["models"] if model["field"] == "style_lora")
    assert (lora["by"], lora["model_id"]) == ("filename", "M-STYLE")
