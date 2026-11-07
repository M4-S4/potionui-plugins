import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .client import ApiClient, unwrap
from .coverage import ModelResolver, assess, live_state
from .pack import Pack, PackError, build_cell_request, dry_media, estimate, included, run_order
from .run import ensure_idle, runner_info

RUNNABLE = {"ready", "input_pending"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def timing_by_preset(client: ApiClient) -> dict:
    items = (unwrap(client.get_json("/api/stats/presets/timing", {"limit": 200})) or {}).get("items") or []
    return {item.get("preset_id"): item for item in items}


def cell_folder(cell_id: str, warm: bool) -> str:
    name = SAFE_NAME.sub("_", cell_id.replace(":", "--").replace("/", "-")).strip("_")
    return name + ("--warm" if warm else "")


def dry_run(client: ApiClient, pack: Pack, profile: str, out_root: Path, run_id: str, *, beyond_tier: bool = False, only: str | None = None, log: Callable[[str], None] = print) -> dict:
    ensure_idle(client)
    live = live_state(client)
    resolver = ModelResolver(client)
    timing = timing_by_preset(client)
    cells = included(pack.cells, profile)
    if only:
        cells = [cell for cell in cells if cell.id == only or cell.id.startswith(only + ":") or cell.preset_ref == only]
    run_dir = out_root / run_id
    entries = []
    seen_presets = set()
    for index, (cell, warm) in enumerate(run_order(cells, profile), start=1):
        assessed = assess(pack, cell, resolver, live)
        status = assessed["status"]
        if status == "beyond_tier" and beyond_tier:
            status = "ready_beyond_tier"
        runnable = status in RUNNABLE or status == "ready_beyond_tier"
        cold = cell.preset_id not in seen_presets
        if runnable:
            seen_presets.add(cell.preset_id)
        entry = {
            "order": index,
            "cell": cell.id,
            "preset": cell.preset_ref,
            "mode": cell.mode,
            "variant": cell.variant,
            "source": cell.status,
            "case": cell.case,
            "warm_repeat": warm,
            "status": status,
            "reason": assessed["reason"],
            "inputs": assessed["inputs"],
            "estimate_seconds": None,
            "estimate_basis": None,
        }
        if runnable:
            seconds = estimate(timing.get(cell.preset_id), warm or not cold)
            entry["estimate_seconds"] = seconds
            entry["estimate_basis"] = None if seconds is None else ("warm average of the preset" if warm or not cold else "cold average of the preset")
            model_ids = {model["field"]: model["model_id"] for model in assessed["models"]}
            try:
                request = build_cell_request(pack, cell, model_ids, live.presets.get(cell.preset_id) or {}, run_id + ("-warm" if warm else ""), dry_media)
            except PackError as error:
                entry.update(status="request_error", reason=str(error))
            else:
                folder = run_dir / "cells" / cell_folder(cell.id, warm)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
                entry["request"] = str(folder / "request.json")
        entries.append(entry)
    planned = [entry for entry in entries if entry.get("request")]
    known = [entry["estimate_seconds"] for entry in planned if entry["estimate_seconds"] is not None]
    counts = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    plan = {
        "schema": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": run_id,
        "profile": profile,
        "dry_run": True,
        "pack": {"id": pack.id, "version": pack.version, "file": pack.path.name, "sha256": pack.sha256},
        "cases": {"file": pack.case_set.path.name, "sha256": pack.case_set.sha256},
        "runner": runner_info(),
        "summary": {
            "cells": len(entries),
            "planned": len(planned),
            "statuses": counts,
            "estimated_seconds": round(sum(known), 1),
            "planned_without_estimate": len(planned) - len(known),
        },
        "cells": entries,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for entry in entries:
        seconds = "" if entry["estimate_seconds"] is None else f"{entry['estimate_seconds']:8.1f} s"
        reason = f"  ({entry['reason']})" if entry["reason"] and not entry.get("request") else ""
        warm = " warm" if entry["warm_repeat"] else ""
        log(f"{entry['order']:3d}  {entry['cell']}{warm}  {entry['status']}  {seconds}{reason}")
    summary = plan["summary"]
    log(f"{summary['planned']} of {summary['cells']} cells planned, {summary['estimated_seconds'] / 60:.1f} min estimated, {summary['planned_without_estimate']} without an estimate")
    log(f"plan: {run_dir / 'plan.json'}")
    return plan
