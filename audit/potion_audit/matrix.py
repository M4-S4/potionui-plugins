import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .client import ApiClient, ApiError
from .coverage import ModelResolver, assess, live_state
from .inputs import Uploads
from .pack import Pack, PackError, build_cell_request, cell_checks, estimate, run_order
from .plan import cell_folder, select_cells, timing_by_preset
from .run import DEFAULT_TIMEOUT, RunRefused, ensure_idle, runner_info, submit_and_collect

HEALTHY = {"healthy", "ok"}
RUNNABLE = {"ready", "ready_beyond_tier"}
STOP_AFTER = {"OOM": "stopped after an OOM: the instance needs a restart, with the operator's consent"}


def instance_health(client: ApiClient) -> str:
    try:
        payload = client.get_json("/health")
    except ApiError as error:
        return f"HTTP {error.status}"
    return str((payload or {}).get("status") or "unknown") if isinstance(payload, dict) else "unknown"


def _summary(entries: list[dict]) -> dict:
    statuses = {}
    verdicts = {}
    for entry in entries:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
        if entry.get("verdict"):
            verdicts[entry["verdict"]] = verdicts.get(entry["verdict"], 0) + 1
    ran = [entry for entry in entries if entry.get("verdict")]
    measured = [entry["run_seconds"] for entry in ran if entry.get("run_seconds") is not None]
    estimated = [entry["estimate_seconds"] for entry in ran if entry.get("estimate_seconds") is not None]
    return {
        "cells": len(entries),
        "run": len(ran),
        "statuses": statuses,
        "verdicts": verdicts,
        "measured_seconds": round(sum(measured), 1),
        "estimated_seconds": round(sum(estimated), 1),
    }


def run_profile(client: ApiClient, pack: Pack, profile: str, out_root: Path, run_id: str, *, beyond_tier: bool = False, only: str | None = None, machine: str | None = None, timeout: float | None = None, interval: float = 2.0, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    health = instance_health(client)
    if health not in HEALTHY:
        raise RunRefused(f"the instance is not healthy: {health}")
    ensure_idle(client)
    live = live_state(client)
    resolver = ModelResolver(client)
    timing = timing_by_preset(client)
    app_version = ((client.get_json("/openapi.json") or {}).get("info") or {}).get("version")
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    uploads = Uploads(client, run_dir / "uploads.json")
    run = {
        "schema": 1,
        "run_id": run_id,
        "profile": profile,
        "dry_run": False,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ended_at": None,
        "machine": machine,
        "app_version": app_version,
        "pack": {"id": pack.id, "version": pack.version, "file": pack.path.name, "sha256": pack.sha256},
        "cases": {"file": pack.case_set.path.name, "sha256": pack.case_set.sha256},
        "runner": runner_info(),
        "stopped": None,
        "summary": {},
        "cells": [],
    }
    entries = run["cells"]
    seen = set()
    current = None
    try:
        for index, (cell, warm) in enumerate(run_order(select_cells(pack, profile, only), profile), start=1):
            entry = {
                "order": index,
                "cell": cell.id,
                "preset": cell.preset_ref,
                "mode": cell.mode,
                "variant": cell.variant,
                "source": cell.status,
                "case": cell.case,
                "warm_repeat": warm,
                "status": None,
                "reason": None,
                "estimate_seconds": None,
                "verdict": None,
            }
            entries.append(entry)
            if run["stopped"]:
                entry.update(status="not_run", reason=run["stopped"])
                continue
            assessed = assess(pack, cell, resolver, live)
            status = assessed["status"]
            if status == "beyond_tier" and beyond_tier:
                status = "ready_beyond_tier"
            entry.update(status=status, reason=assessed["reason"])
            if status not in RUNNABLE:
                continue
            cold = cell.preset_id not in seen
            seen.add(cell.preset_id)
            entry["estimate_seconds"] = estimate(timing.get(cell.preset_id), warm or not cold)
            health = instance_health(client)
            if health not in HEALTHY:
                run["stopped"] = f"stopped: the instance is {health}"
                entry.update(status="not_run", reason=run["stopped"])
                continue
            try:
                ensure_idle(client)
            except RunRefused as error:
                run["stopped"] = f"stopped: {error}"
                entry.update(status="not_run", reason=run["stopped"])
                continue
            model_ids = {model["field"]: model["model_id"] for model in assessed["models"]}
            try:
                request = build_cell_request(pack, cell, model_ids, live.presets.get(cell.preset_id) or {}, run_id + ("-warm" if warm else ""), lambda input_id, as_path: uploads.media(pack, input_id, as_path))
            except (PackError, RunRefused) as error:
                entry.update(status="request_error", reason=str(error))
                continue
            folder = run_dir / "cells" / cell_folder(cell.id, warm)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            checks = cell_checks(pack, cell)
            head = {
                "schema": 1,
                "run_id": run_id,
                "cell": cell.id,
                "warm_repeat": warm,
                "pack": run["pack"],
                "cases": run["cases"],
                "app_version": app_version,
                "runner": run["runner"],
            }
            current = entry
            try:
                result = submit_and_collect(client, request, cell.preset_id, checks, folder, head, f"{index:3d}  {cell.id}{' warm' if warm else ''}", timeout or float(checks.get("max_seconds") or DEFAULT_TIMEOUT), interval, clock, sleep, log)
            except ApiError as error:
                current = None
                entry.update(verdict="REJECTED", reason=str(error))
                log(f"{cell.id}: REJECTED, {error}")
                continue
            current = None
            stats = result.get("generation_stats") or {}
            entry.update(
                verdict=result["verdict"],
                generation_id=result.get("generation_id"),
                run_seconds=(result.get("timing") or {}).get("run_seconds"),
                peak_vram_mb=stats.get("peak_vram_mb"),
                result=str(folder / "result.json"),
            )
            if result["verdict"] in STOP_AFTER:
                run["stopped"] = STOP_AFTER[result["verdict"]]
    except KeyboardInterrupt:
        run["stopped"] = "stopped with Ctrl+C: the running generation was cancelled"
        if current is not None:
            current["verdict"] = "STOPPED"
        raise
    finally:
        run["ended_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        run["summary"] = _summary(entries)
        (run_dir / "run.json").write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    summary = run["summary"]
    verdicts = ", ".join(f"{name} {count}" for name, count in sorted(summary["verdicts"].items())) or "none"
    log(f"{summary['run']} of {summary['cells']} cells run ({verdicts}), {summary['measured_seconds'] / 60:.1f} min measured for {summary['estimated_seconds'] / 60:.1f} min estimated")
    if run["stopped"]:
        log(run["stopped"])
    log(f"run: {run_dir / 'run.json'}")
    return run


def run_passed(run: dict) -> bool:
    return not run["stopped"] and all(entry["verdict"] == "PASS" for entry in run["cells"] if entry.get("verdict"))
