import json

import pytest

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.run import RunRefused, build_request, derive_run_stats, execute, select_case, step_seconds

from conftest import PASSWORD, SDXL_ID, USER, WAN_ID, png_bytes


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


def run_case(fake_api, case_set, tmp_path, only="SDXL:txt2img", **kwargs):
    clock = FakeClock()
    lines = []
    result = execute(logged_in(fake_api), case_set, select_case(case_set, only), tmp_path, "run-1", clock=clock, sleep=clock.sleep, log=lines.append, **kwargs)
    return result, lines


def test_run_without_confirm_gpu_is_refused_before_any_request(fake_api, config_file, credentials_env, capsys):
    code = main(["run", "--config", str(config_file), "--only", "SDXL:txt2img"])
    assert code == 2
    assert fake_api.requests == []
    assert "--confirm-gpu" in capsys.readouterr().err


def test_a_dry_run_writes_the_request_and_submits_nothing(fake_api, config_file, credentials_env, tmp_path):
    code = main(["run", "--config", str(config_file), "--only", "SDXL:txt2img", "--dry-run", "--run-id", "dry"])
    assert code == 0
    assert fake_api.started == []
    assert all(method == "GET" for method, _ in fake_api.methods()[1:])
    request = json.loads((tmp_path / "out" / "dry" / "cases" / "SDXL--txt2img--sdxl-fast" / "request.json").read_text(encoding="utf-8"))
    assert request["form_data"]["model"] == "model:M-SDXL"


def test_select_case_prefers_the_fast_case_of_the_mode(case_set):
    assert select_case(case_set, "SDXL:txt2img").name == "sdxl-fast"
    assert select_case(case_set, f"{WAN_ID}:video").name == "wan-t2v"


@pytest.mark.parametrize("only", ["SDXL", "Nope:txt2img", "SDXL:video"])
def test_select_case_refuses_an_unknown_preset_or_mode(case_set, only):
    with pytest.raises(RunRefused):
        select_case(case_set, only)


def test_the_request_carries_model_ids_seed_and_the_prompt(case_set):
    case = select_case(case_set, "SDXL:txt2img")
    request = build_request(case, {"model": "M-SDXL"}, {"vars": {}}, "run-1")
    assert request["preset_id"] == SDXL_ID
    assert request["prompts"] == [{"positive": "a purple potion", "negative": ""}]
    assert request["form_data"] == {"steps": 4, "resolution": "64x64", "seed": 999, "model": "model:M-SDXL"}
    assert "video_director" not in request["form_data"]
    assert request["idempotency_key"] == "potion-audit-run-1-SDXL-sdxl-fast"


def test_a_director_mode_gets_a_minimal_t2v_document(case_set):
    case = select_case(case_set, "Wan:video")
    detail = {"vars": {"video_director": {"preset_modes": ["video"], "limits": {"default_duration": 5, "default_fps": 16}}}}
    request = build_request(case, {}, detail, "run-1", "a violet potion")
    assert request["form_data"]["video_director"] == {
        "schema_version": 1,
        "mode": "t2v",
        "settings": {"duration": 5.0, "fps": 16, "seed": 12345},
        "segments": [{"id": "shot-1", "prompt": "a violet potion", "negative_prompt": ""}],
        "media": [],
    }


def test_a_full_run_submits_follows_downloads_and_checks(fake_api, case_set, tmp_path):
    fake_api.statuses = [
        {"id": "G1", "status": "pending"},
        {"id": "G1", "status": "running", "current_step_num": 1, "total_steps": 4},
        {"id": "G1", "status": "running", "current_step_num": 3, "total_steps": 4},
    ]
    result, lines = run_case(fake_api, case_set, tmp_path)
    assert result["verdict"] == "PASS"
    assert fake_api.started[0]["form_data"]["model"] == "model:M-SDXL"
    assert result["outputs"][0]["width"] == 64
    assert all(check["ok"] for check in result["checks"])
    assert result["timing"]["run_seconds"] == 12
    assert result["timing"]["seconds_per_step_polled"] == 1.0
    assert result["timing"]["pipe_seconds"] == {"0": 2.5}
    assert result["generation_stats"]["peak_vram_mb"] == 7400.0
    assert result["generation_stats"]["model_load_ms"] == 11000.0
    assert result["generation_stats"]["cold_start"] is True
    assert result["memory"]["peak_vram_used_mb_sampled"] == 2100
    case_dir = tmp_path / "run-1" / "cases" / "SDXL--txt2img--sdxl-fast"
    assert json.loads((case_dir / "result.json").read_text(encoding="utf-8"))["verdict"] == "PASS"
    assert (case_dir / "bundle.zip").exists()
    assert (case_dir / "0.png").exists()
    assert lines[-1].endswith("PASS in 12 s")


def test_a_black_output_fails_the_not_black_check(fake_api, case_set, tmp_path):
    fake_api.outputs = {"0.png": png_bytes((0, 0, 0))}
    result, _ = run_case(fake_api, case_set, tmp_path)
    assert result["verdict"] == "FAIL"
    assert [check["check"] for check in result["checks"] if not check["ok"]] == ["not_black"]


def test_a_cuda_oom_failure_is_reported_as_oom(fake_api, case_set, tmp_path):
    fake_api.final = "failed"
    fake_api.failure = {"error_code": "cuda_oom", "message": "Ran out of GPU memory", "failed_pipe_name": "generator", "failed_at_step": "x"}
    result, _ = run_case(fake_api, case_set, tmp_path)
    assert result["verdict"] == "OOM"
    assert result["failure"]["error_code"] == "cuda_oom"
    assert "outputs" not in result


def test_a_run_past_its_timeout_is_cancelled(fake_api, case_set, tmp_path):
    fake_api.statuses = [{"id": "G1", "status": "running", "current_step_num": 1, "total_steps": 4}] * 10
    fake_api.final = "cancelled"
    result, _ = run_case(fake_api, case_set, tmp_path, timeout=5)
    assert result["verdict"] == "TIMEOUT"
    assert ("POST", "/api/generations/G1/cancel") in fake_api.methods()


def test_a_busy_queue_refuses_the_run_before_submitting(fake_api, case_set, tmp_path):
    fake_api.queue = {"pending": [], "running": [{"id": "other"}]}
    with pytest.raises(RunRefused, match="busy"):
        run_case(fake_api, case_set, tmp_path)
    assert fake_api.started == []


def test_a_missing_model_refuses_the_run_before_submitting(fake_api, case_set, tmp_path):
    with pytest.raises(RunRefused, match="not on the instance"):
        run_case(fake_api, case_set, tmp_path, only="Wan:video")
    assert fake_api.started == []


def test_run_stats_are_recovered_from_the_preset_averages():
    before = {"total_runs": 2, "cold_runs": 1, "warm_runs": 1, "avg_warm_duration_ms": 10000.0, "avg_vram_mb": 5000.0, "avg_ram_mb": 100.0, "avg_cpu_percent": 50.0}
    after = {"total_runs": 3, "cold_runs": 1, "warm_runs": 2, "avg_warm_duration_ms": 11000.0, "avg_vram_mb": 6000.0, "avg_ram_mb": 100.0, "avg_cpu_percent": 50.0}
    stats = derive_run_stats(before, after)
    assert stats["cold_start"] is False
    assert stats["duration_ms"] == 12000.0
    assert stats["model_load_ms"] == 0.0
    assert stats["peak_vram_mb"] == 8000.0


def test_run_stats_are_not_derived_when_another_run_slipped_in():
    stats = derive_run_stats({"total_runs": 2}, {"total_runs": 4})
    assert stats["derived"] is False


def test_seconds_per_step_come_from_running_samples_only():
    samples = [
        {"t": 0.0, "status": "pending", "step": None},
        {"t": 10.0, "status": "running", "step": 1},
        {"t": 14.0, "status": "running", "step": 3},
        {"t": 30.0, "status": "completed", "step": 30},
    ]
    assert step_seconds(samples) == 2.0
    assert step_seconds([{"t": 1.0, "status": "running", "step": 1}]) is None
