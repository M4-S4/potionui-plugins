import json

import pytest

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.matrix import run_passed, run_profile
from potion_audit.pack import load_pack
from potion_audit.run import RunRefused

from conftest import PASSWORD, USER
from packs import write_pack


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def logged_in(fake_api) -> ApiClient:
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def quiet(line: str) -> None:
    return None


def test_a_profile_run_submits_each_ready_cell_and_goes_on_after_a_failure(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    fake_api.outcomes = [("completed", None), ("failed", {"error_code": "pipe_error", "message": "boom"})]
    code = main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "smoke", "--beyond-tier", "--confirm-gpu", "--run-id", "matrix-1", "--interval", "0.01"])
    assert code == 1
    run = json.loads((tmp_path / "out" / "matrix-1" / "run.json").read_text(encoding="utf-8"))
    assert [(entry["cell"], entry["status"], entry["verdict"]) for entry in run["cells"]] == [("core/SDXL:txt2img", "ready", "PASS"), ("core/Wan:video", "ready_beyond_tier", "FAIL")]
    assert run["summary"]["verdicts"] == {"FAIL": 1, "PASS": 1}
    assert run["stopped"] is None
    assert run["app_version"] == "9.9.9"
    assert run["pack"]["sha256"] == load_pack(path).sha256
    assert len(fake_api.started) == 2
    result = json.loads((tmp_path / "out" / "matrix-1" / "cells" / "core-Wan--video" / "result.json").read_text(encoding="utf-8"))
    assert (result["cell"], result["verdict"]) == ("core/Wan:video", "FAIL")


def test_an_oom_stops_the_run_and_leaves_the_next_cells_not_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.outcomes = [("failed", {"error_code": "cuda_oom", "message": "out of memory"})]
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", "matrix-2", beyond_tier=True, clock=clock, sleep=clock.sleep, log=quiet)
    rows = [(entry["cell"], entry["warm_repeat"], entry["status"], entry["verdict"]) for entry in run["cells"]]
    assert rows == [
        ("core/SDXL:txt2img", False, "ready", "OOM"),
        ("core/SDXL:txt2img/edit", False, "not_run", None),
        ("core/Wan:video", False, "not_run", None),
        ("core/Wan:video", True, "not_run", None),
    ]
    assert "OOM" in run["stopped"]
    assert len(fake_api.started) == 1
    assert not run_passed(run)


def test_a_generation_that_left_the_gpu_unusable_counts_as_an_oom_and_stops_the_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.outcomes = [("failed", {"error_code": "gpu_restart_required", "message": "This process can no longer use the GPU"})]
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "smoke", tmp_path / "out", "matrix-8", beyond_tier=True, clock=clock, sleep=clock.sleep, log=quiet)
    assert [(entry["cell"], entry["status"], entry["verdict"]) for entry in run["cells"]] == [("core/SDXL:txt2img", "ready", "OOM"), ("core/Wan:video", "not_run", None)]
    assert "OOM" in run["stopped"]


def test_a_run_uploads_each_input_once_and_gives_every_submission_its_own_key(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    assert main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")]) == 0
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), load_pack(path), "full", tmp_path / "out", "matrix-3", beyond_tier=True, clock=clock, sleep=clock.sleep, log=quiet)
    assert [(entry["cell"], entry["warm_repeat"], entry["verdict"]) for entry in run["cells"]] == [
        ("core/SDXL:txt2img", False, "PASS"),
        ("core/SDXL:txt2img/edit", False, "PASS"),
        ("core/Wan:video", False, "PASS"),
        ("core/Wan:video", True, "PASS"),
    ]
    assert run_passed(run)
    assert fake_api.uploads == ["bottle.png", "mask.png"]
    keys = [request["idempotency_key"] for request in fake_api.started]
    assert len(set(keys)) == 4
    edit = fake_api.started[1]["form_data"]
    assert edit["source_image"] == "storage/uploads/1-bottle.png"
    assert edit["source_image_inpaint_mask"] == "storage/uploads/2-mask.png"
    assert edit["references"][0]["path"] == "storage/uploads/1-bottle.png"


def test_a_cell_whose_media_did_not_load_fails_even_with_a_good_output(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    assert main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")]) == 0
    fake_api.history = [
        {"at": "2026-01-01T00:00:00+00:00", "step": "Processing <<NUMBER:2 media files:folder>>"},
        {"at": "2026-01-01T00:00:01+00:00", "step": "Loaded <<NUMBER:0 files:check-circle>> (<<NUMBER:0 images:image>>)"},
        {"at": "2026-01-01T00:00:02+00:00", "step": "TXT2IMG"},
    ]
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), load_pack(path), "full", tmp_path / "out", "matrix-7", only="core/SDXL:txt2img/edit", clock=clock, sleep=clock.sleep, log=quiet)
    assert [(entry["cell"], entry["verdict"]) for entry in run["cells"]] == [("core/SDXL:txt2img/edit", "FAIL")]
    result = json.loads((tmp_path / "out" / "matrix-7" / "cells" / "core-SDXL--txt2img-edit" / "result.json").read_text(encoding="utf-8"))
    media = next(check for check in result["checks"] if check["check"] == "media_loaded")
    assert (media["ok"], media["actual"]) == (False, [0])


def test_a_run_report_check_catches_a_text_only_step_on_a_source_cell():
    from potion_audit.run import evaluate_run_report

    report = {"status_history": [{"step": "Processing <<NUMBER:1 media files:folder>>"}, {"step": "Loaded <<NUMBER:1 files:check-circle>>"}, {"step": "TXT2IMG"}]}
    checks = evaluate_run_report({"forbidden_steps": ["TXT2IMG"]}, report)
    assert [(check["check"], check["ok"]) for check in checks] == [("media_loaded", True), ("generation_step", False)]
    good = {"status_history": [{"step": "Processing <<NUMBER:1 media files:folder>>"}, {"step": "Loaded <<NUMBER:1 files:check-circle>>"}, {"step": "IMG2IMG"}]}
    assert all(check["ok"] for check in evaluate_run_report({"forbidden_steps": ["TXT2IMG"]}, good))
    assert evaluate_run_report({}, {"status_history": [{"step": "TXT2IMG"}]}) == []


def test_a_cell_waiting_for_an_input_is_listed_and_not_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    clock = FakeClock()
    run = run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", "matrix-4", clock=clock, sleep=clock.sleep, log=quiet)
    rows = [(entry["cell"], entry["warm_repeat"], entry["status"], entry["verdict"]) for entry in run["cells"]]
    assert rows == [
        ("core/SDXL:txt2img", False, "ready", "PASS"),
        ("core/SDXL:txt2img/edit", False, "input_pending", None),
        ("core/Wan:video", False, "beyond_tier", None),
        ("core/Wan:video", True, "beyond_tier", None),
    ]
    assert run_passed(run)
    assert len(fake_api.started) == 1


def test_a_degraded_instance_refuses_the_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.health = "degraded"
    with pytest.raises(RunRefused, match="degraded"):
        run_profile(logged_in(fake_api), pack, "smoke", tmp_path / "out", "matrix-5", log=quiet)
    assert fake_api.started == []


def test_a_busy_queue_before_a_cell_stops_the_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    fake_api.queue = {"pending": [], "running": [{"id": "X"}]}
    with pytest.raises(RunRefused, match="queue is busy"):
        run_profile(logged_in(fake_api), pack, "smoke", tmp_path / "out", "matrix-6", log=quiet)
    assert fake_api.started == []
