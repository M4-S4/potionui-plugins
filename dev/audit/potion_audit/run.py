import json
import re
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .cases import Case, CaseSet
from .check import lookup_model, runner_info
from .client import ApiClient, ApiError, unwrap
from .media import probe_image, probe_video

TERMINAL = {"completed", "failed", "cancelled"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_TIMEOUT = 1800.0
DEFAULT_DURATION = 5.0
OOM_CODES = {"cuda_oom", "gpu_restart_required"}
MEDIA_PROCESSING = re.compile(r"Processing <<NUMBER:(\d+) media files")
MEDIA_LOADED = re.compile(r"Loaded <<NUMBER:(\d+) files")
SOURCE_REFINED_STEPS = {"TXT2VID": "ENCODING SOURCE VIDEO"}
CHECKS_VERSION = 2
MAXIMUM_TOLERANCE_MB = 1.0
PRESET_STAT_KEYS = ("preset_id", "preset_name", "total_runs", "cold_runs", "warm_runs", "avg_cold_duration_ms", "avg_warm_duration_ms", "avg_model_load_ms", "peak_vram_mb", "avg_vram_mb", "peak_ram_mb", "avg_ram_mb", "avg_cpu_percent")


class RunRefused(RuntimeError):
    pass


def select_case(case_set: CaseSet, only: str) -> Case:
    preset_key, sep, mode = only.partition(":")
    if not sep or not preset_key or not mode:
        raise RunRefused(f"--only takes <preset>:<mode>, got {only!r}")
    preset = case_set.preset(preset_key)
    if preset is None:
        raise RunRefused(f"no preset {preset_key!r} in {case_set.path.name}")
    matches = [case for case in case_set.cases if case.preset_id == preset["id"] and case.mode == mode]
    if not matches:
        raise RunRefused(f"no case for {preset['key']}:{mode} in {case_set.path.name}")
    fast = [case for case in matches if "fast" in case.tags]
    return (fast or matches)[0]


def director_document(form: dict, prompt: str, negative: str, limits: dict) -> dict:
    settings = {"duration": float(form.get("duration") or limits.get("default_duration") or DEFAULT_DURATION)}
    fps = form.get("fps") or limits.get("default_fps")
    if fps:
        settings["fps"] = fps
    if isinstance(form.get("seed"), int):
        settings["seed"] = form["seed"]
    return {
        "schema_version": 1,
        "mode": "t2v",
        "settings": settings,
        "segments": [{"id": "shot-1", "prompt": prompt, "negative_prompt": negative}],
        "media": [],
    }


def build_request(case: Case, model_ids: dict[str, str], preset_detail: dict, run_id: str, prompt_override: str | None = None) -> dict:
    form = dict(case.form)
    case_prompt = str(form.pop("prompt", "") or "")
    prompt = case_prompt if prompt_override is None else prompt_override
    negative = str(form.pop("negative_prompt", "") or "")
    if case.seed is not None and "seed" not in form:
        form["seed"] = case.seed
    for field, model_id in model_ids.items():
        form[field] = f"model:{model_id}"
    director = (preset_detail.get("vars") or {}).get("video_director") or {}
    director_modes = director.get("preset_modes") or (["video"] if director else [])
    if director and case.mode in director_modes and "video_director" not in form:
        if not prompt:
            raise RunRefused(f"{case.preset_key}/{case.name} needs a prompt to build its Video Director document")
        form["video_director"] = director_document(form, prompt, negative, director.get("limits") or {})
    return {
        "preset_id": case.preset_id,
        "mode": case.mode,
        "prompts": [{"positive": prompt, "negative": negative}],
        "form_data": form,
        "idempotency_key": f"potion-audit-{run_id}-{case.preset_key}-{case.name}"[:200],
    }


def evaluate(checks: dict, outputs: list[dict]) -> list[dict]:
    results = []
    if "min_outputs" in checks:
        results.append({"check": "min_outputs", "expected": checks["min_outputs"], "actual": len(outputs), "ok": len(outputs) >= int(checks["min_outputs"])})
    if "resolution" in checks:
        expected = str(checks["resolution"])
        actual = [f"{item.get('width')}x{item.get('height')}" for item in outputs]
        results.append({"check": "resolution", "expected": expected, "actual": actual, "ok": bool(actual) and all(value == expected for value in actual)})
    if checks.get("not_black"):
        values = [item.get("not_black") for item in outputs]
        results.append({"check": "not_black", "expected": True, "actual": values, "ok": bool(values) and all(values)})
    return results


def _refines_source(before: list[str], step: str) -> bool:
    encoding = SOURCE_REFINED_STEPS.get(step.strip().upper())
    return encoding is not None and any(earlier.strip().upper() == encoding for earlier in before)


def evaluate_run_report(checks: dict, run_report: dict) -> list[dict]:
    steps = [str(entry.get("step") or "") for entry in run_report.get("status_history") or ()]
    asked = [int(found.group(1)) for found in (MEDIA_PROCESSING.search(step) for step in steps) if found]
    loaded = [int(found.group(1)) for found in (MEDIA_LOADED.search(step) for step in steps) if found]
    results = []
    if sum(asked):
        results.append({"check": "media_loaded", "expected": f"{sum(asked)} media files loaded", "actual": loaded, "ok": sum(loaded) >= sum(asked)})
    forbidden = {step.upper() for step in checks.get("forbidden_steps") or ()}
    if forbidden:
        seen = sorted({step.strip() for index, step in enumerate(steps) if step.strip().upper() in forbidden and not _refines_source(steps[:index], step)})
        results.append({"check": "generation_step", "expected": f"none of {', '.join(sorted(forbidden))}", "actual": seen, "ok": not seen})
    return results


def _status(client: ApiClient, generation_id: str) -> dict:
    return unwrap(client.get_json(f"/api/generations/{generation_id}/status")) or {}


def _sample_gpu(client: ApiClient) -> dict | None:
    stats = unwrap(client.get_json("/api/system/stats")) or {}
    gpu = stats.get("gpu") or {}
    ram = stats.get("ram") or {}
    if not gpu.get("available"):
        return None
    return {"vram_used_mb": gpu.get("vram_used"), "ram_used_mb": ram.get("used")}


def follow(client: ApiClient, generation_id: str, timeout: float, interval: float, clock: Callable[[], float], sleep: Callable[[float], None], log: Callable[[str], None]) -> tuple[dict, list[dict], bool]:
    started = clock()
    samples = []
    last_line = None
    while True:
        status = _status(client, generation_id)
        gpu = _sample_gpu(client)
        sample = {
            "t": round(clock() - started, 3),
            "status": status.get("status"),
            "progress": status.get("progress"),
            "step": status.get("current_step_num"),
            "total_steps": status.get("total_steps"),
            "current_step": status.get("current_step"),
        }
        if gpu:
            sample.update(gpu)
        samples.append(sample)
        line = f"{sample['status']} {sample['step']}/{sample['total_steps']} {sample['current_step'] or ''}".strip()
        if line != last_line:
            log(f"  {sample['t']:7.1f} s  {line}")
            last_line = line
        if status.get("status") in TERMINAL:
            return status, samples, False
        if clock() - started > timeout:
            return status, samples, True
        sleep(interval)


def step_seconds(samples: list[dict]) -> float | None:
    points = [(sample["t"], sample["step"]) for sample in samples if isinstance(sample.get("step"), int) and sample.get("status") == "running"]
    first = None
    for t, step in points:
        if step and step >= 1:
            first = (t, step)
            break
    if first is None:
        return None
    last = max(points, key=lambda point: (point[1], -point[0]))
    if last[1] <= first[1]:
        return None
    return round((last[0] - first[0]) / (last[1] - first[1]), 3)


def all_preset_stats(client: ApiClient) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for path in ("/api/stats/presets/timing", "/api/stats/presets/resources"):
        items = (unwrap(client.get_json(path, {"limit": 200})) or {}).get("items") or []
        for item in items:
            if item.get("preset_id"):
                merged.setdefault(str(item["preset_id"]), {}).update(item)
    return merged


def preset_stats(client: ApiClient, preset_id: str) -> dict:
    return all_preset_stats(client).get(preset_id, {})


def _added(before: dict, after: dict, average: str, count: str) -> float | None:
    old_n = before.get(count) or 0
    new_n = after.get(count) or 0
    if new_n != old_n + 1 or after.get(average) is None:
        return None
    return round(after[average] * new_n - (before.get(average) or 0) * old_n, 1)


def _mib(value: float | None) -> str:
    return "nothing" if value is None else f"{value:.1f} MiB"


def _bounded(before: dict, after: dict, average: str, maximum: str, label: str) -> tuple[float | None, str]:
    old_max = before.get(maximum)
    new_max = after.get(maximum)
    if after.get(average) is None or new_max is None:
        return None, f"the core recorded no {label} for this preset"
    if old_max is None:
        return round(new_max, 1), "the preset's maximum, which this run is the first to record"
    added = _added(before, after, average, "total_runs")
    if new_max > old_max + MAXIMUM_TOLERANCE_MB:
        if added is not None and abs(added - new_max) <= MAXIMUM_TOLERANCE_MB:
            return round(new_max, 1), "the preset's new maximum, which the averages confirm"
        return None, f"the preset's maximum rose to {new_max:.1f} MiB but the averages give {_mib(added)}: the preset holds runs with no {label} recorded"
    if added is None or added < 0 or added > new_max + MAXIMUM_TOLERANCE_MB:
        return None, f"the averages give {_mib(added)}, outside the preset's maximum of {new_max:.1f} MiB: the preset holds runs with no {label} recorded"
    return added, "the difference of the preset's averages, within its maximum"


def _resources_unrecorded(before: dict, after: dict) -> bool:
    if not before.get("total_runs"):
        return False
    keys = ("avg_vram_mb", "avg_ram_mb", "avg_cpu_percent")
    return any(before.get(key) is not None for key in keys) and all(before.get(key) == after.get(key) for key in keys)


def _kept(stats: dict) -> dict:
    return {key: stats[key] for key in PRESET_STAT_KEYS if key in stats}


def derive_run_stats(before: dict, after: dict) -> dict:
    preset_stats = {"before": _kept(before), "after": _kept(after)}
    if (after.get("total_runs") or 0) != (before.get("total_runs") or 0) + 1:
        return {"derived": False, "reason": "the preset's run count did not grow by exactly one", "preset_stats": preset_stats}
    cold = (after.get("cold_runs") or 0) == (before.get("cold_runs") or 0) + 1
    warm = (after.get("warm_runs") or 0) == (before.get("warm_runs") or 0) + 1
    if _resources_unrecorded(before, after):
        reason = "no resource average of the preset moved: the core recorded no resources for this run"
        peak_vram, vram_source = None, reason
        end_ram, ram_source = None, reason
        cpu = None
    else:
        peak_vram, vram_source = _bounded(before, after, "avg_vram_mb", "peak_vram_mb", "peak VRAM")
        end_ram, ram_source = _bounded(before, after, "avg_ram_mb", "peak_ram_mb", "RAM")
        cpu = _added(before, after, "avg_cpu_percent", "total_runs")
    return {
        "derived": True,
        "cold_start": True if cold else False if warm else None,
        "duration_ms": _added(before, after, "avg_cold_duration_ms", "cold_runs") if cold else _added(before, after, "avg_warm_duration_ms", "warm_runs") if warm else None,
        "model_load_ms": _added(before, after, "avg_model_load_ms", "cold_runs") if cold else 0.0 if warm else None,
        "peak_vram_mb": peak_vram,
        "peak_vram_source": vram_source,
        "end_ram_mb": end_ram,
        "end_ram_source": ram_source,
        "cpu_percent": cpu,
        "source": "difference of the per-preset averages of /api/stats/presets/timing and /resources before and after the run, checked against the preset's maximum",
        "preset_stats": preset_stats,
    }


def wait_for_stats(client: ApiClient, generation_id: str, preset_id: str, before: dict, attempts: int, interval: float, sleep: Callable[[float], None]) -> tuple[dict, dict]:
    admin = {}
    after = before
    for attempt in range(attempts):
        admin = unwrap(client.get_json(f"/api/admin/generations/{generation_id}")) or {}
        after = preset_stats(client, preset_id)
        if admin.get("run_report") is not None and (after.get("total_runs") or 0) > (before.get("total_runs") or 0):
            break
        if attempt + 1 < attempts:
            sleep(interval)
    return admin, after


def read_outputs(bundle: Path, out_dir: Path) -> list[dict]:
    outputs = []
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name.startswith("outputs/") or name.endswith("/"):
                continue
            target = out_dir / Path(name).name
            with archive.open(info) as source, open(target, "wb") as handle:
                handle.write(source.read())
            suffix = target.suffix.lower()
            if suffix in VIDEO_SUFFIXES:
                outputs.append({"file": target.name, "kind": "video", **probe_video(target)})
            elif suffix in IMAGE_SUFFIXES:
                outputs.append({"file": target.name, "kind": "image", **probe_image(target)})
            else:
                outputs.append({"file": target.name, "kind": "other", "size": target.stat().st_size})
    return outputs


def phases(run_report: dict) -> dict:
    timers = run_report.get("pipe_timers") or {}
    history = run_report.get("status_history") or []
    loads = [entry for entry in history if "Loading" in str(entry.get("message") or "") or str(entry.get("step") or "").startswith("Loading")]
    pipes = {}
    for pipe_id, timer in timers.items():
        start = timer.get("started_at")
        end = timer.get("ended_at")
        if start and end:
            pipes[pipe_id] = round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 3)
    return {"pipe_seconds": pipes, "load_events": [{"at": entry.get("at"), "step": entry.get("step")} for entry in loads]}


def ensure_idle(client: ApiClient) -> None:
    queue = unwrap(client.get_json("/api/admin/generations/queue")) or {}
    if queue.get("pending") or queue.get("running"):
        raise RunRefused(f"the global queue is busy: {len(queue.get('running') or ())} running, {len(queue.get('pending') or ())} pending")


def execute(client: ApiClient, case_set: CaseSet, case: Case, out_root: Path, run_id: str, *, dry_run: bool = False, prompt: str | None = None, timeout: float | None = None, interval: float = 2.0, keep_bundle: bool = False, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    ensure_idle(client)
    model_ids = {}
    for ref in case.models:
        if not ref.resolved:
            raise RunRefused(f"model field {ref.field} has no sha256 to look up")
        found = next((hit for hit in (lookup_model(client, sha) for sha in (ref.sha256, *ref.alternatives)) if hit), None)
        if not found:
            raise RunRefused(f"model {ref.filename or ref.sha256} ({ref.field}) is not on the instance")
        model_ids[ref.field] = found["model_id"]
    preset_detail = unwrap(client.get_json(f"/api/presets/{case.preset_id}")) or {}
    request = build_request(case, model_ids, preset_detail, run_id, prompt)
    case_dir = out_root / run_id / "cases" / f"{case.preset_key}--{case.mode}--{case.name}"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if dry_run:
        log(f"{case.preset_key}:{case.mode} {case.name}: dry run, request written to {case_dir / 'request.json'}")
        return {"verdict": "DRY_RUN", "request": request, "case_dir": str(case_dir)}
    head = {
        "schema": 1,
        "run_id": run_id,
        "case": {"preset_key": case.preset_key, "preset_id": case.preset_id, "name": case.name, "mode": case.mode, "tags": list(case.tags)},
        "cases_source": {**case_set.source, "file": case_set.path.name, "sha256": case_set.sha256},
        "runner": runner_info(),
    }
    limit = timeout or float(case.checks.get("max_seconds") or DEFAULT_TIMEOUT)
    return submit_and_collect(client, request, case.preset_id, case.checks, case_dir, head, f"{case.preset_key}:{case.mode} {case.name}", limit, interval, clock, sleep, log, keep_bundle=keep_bundle)


def submit_and_collect(client: ApiClient, request: dict, preset_id: str, checks: dict, case_dir: Path, head: dict, label: str, timeout: float, interval: float, clock: Callable[[], float], sleep: Callable[[float], None], log: Callable[[str], None], *, keep_bundle: bool = False) -> dict:
    stats_before = preset_stats(client, preset_id)
    log(f"{label}: submitting")
    submitted_at = datetime.now(UTC).isoformat(timespec="seconds")
    started = unwrap(client.post_json("/api/generations/start", request)) or {}
    generation_id = started.get("generation_id") or (started.get("status") or {}).get("id")
    if not generation_id:
        raise ApiError("POST", "/api/generations/start", 200, "the answer holds no generation_id")
    result = {**head, "checks_version": CHECKS_VERSION, "generation_id": generation_id, "submitted_at": submitted_at}
    try:
        status, samples, timed_out = follow(client, generation_id, timeout, interval, clock, sleep, log)
    except KeyboardInterrupt:
        client.post_json(f"/api/generations/{generation_id}/cancel", {})
        result["verdict"] = "STOPPED"
        _write(case_dir, result)
        raise
    if timed_out:
        client.post_json(f"/api/generations/{generation_id}/cancel", {})
    result["samples"] = samples
    result["final_status"] = status
    admin, stats_after = wait_for_stats(client, generation_id, preset_id, stats_before, 10, interval, sleep)
    record = unwrap(client.get_json(f"/api/generations/history/{generation_id}")) or {}
    run_report = admin.get("run_report") or {}
    result["generation_stats"] = derive_run_stats(stats_before, stats_after) if status.get("status") == "completed" else {"derived": False, "reason": "the run did not complete"}
    result["timing"] = {
        "run_seconds": record.get("run_seconds"),
        "queued_seconds": record.get("queued_seconds"),
        "duration_ms": record.get("duration_ms"),
        "seconds_per_step_polled": step_seconds(samples),
        **phases(run_report),
    }
    vram = [sample["vram_used_mb"] for sample in samples if sample.get("vram_used_mb") is not None]
    ram = [sample["ram_used_mb"] for sample in samples if sample.get("ram_used_mb") is not None]
    result["memory"] = {
        "peak_vram_used_mb_sampled": max(vram) if vram else None,
        "peak_ram_used_mb_sampled": max(ram) if ram else None,
        "source": "GET /api/system/stats at each poll, whole device",
    }
    result["has_profile"] = bool(record.get("has_profile"))
    (case_dir / "run_report.json").write_text(json.dumps(run_report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if status.get("status") == "completed":
        bundle = client.download(f"/api/generations/history/{generation_id}/export-bundle", case_dir / "bundle.zip")
        outputs = read_outputs(bundle.path, case_dir)
        if not keep_bundle:
            bundle.path.unlink()
        result["bundle"] = {"file": bundle.path.name if keep_bundle else None, "size": bundle.size, "kept": keep_bundle}
        result["outputs"] = outputs
        result["checks"] = evaluate(checks, outputs) + evaluate_run_report(checks, run_report)
        result["verdict"] = "PASS" if all(check["ok"] for check in result["checks"]) else "FAIL"
    else:
        failure = client.get_json(f"/api/generations/{generation_id}/failure", missing_ok=True)
        detail = unwrap(failure) if failure else {}
        result["failure"] = {key: detail.get(key) for key in ("error_code", "message", "failed_pipe_name", "failed_at_step")} if detail else None
        if timed_out:
            result["verdict"] = "TIMEOUT"
        elif detail and detail.get("error_code") in OOM_CODES:
            result["verdict"] = "OOM"
        else:
            result["verdict"] = "FAIL"
    _write(case_dir, result)
    log(f"{label}: {result['verdict']} in {result['timing']['run_seconds']} s")
    return result


def _write(case_dir: Path, result: dict) -> None:
    (case_dir / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
