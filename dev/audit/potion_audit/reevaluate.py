import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .media import probe_image, probe_video
from .pack import Pack, cell_checks
from .plan import cell_folder
from .run import CHECKS_VERSION, IMAGE_SUFFIXES, VIDEO_SUFFIXES, derive_run_stats, evaluate, evaluate_run_report

REEVALUATED = "result.reevaluated.json"
CHECKED_VERDICTS = {"PASS", "FAIL"}


class ReevaluateError(ValueError):
    pass


def load_run_json(run_dir: Path) -> dict:
    path = run_dir / "run.json"
    if not path.is_file():
        raise ReevaluateError(f"{run_dir} holds no run.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _reprobe(folder: Path, stored: list[dict]) -> tuple[list[dict], list[str]]:
    outputs = []
    missing = []
    for output in stored:
        path = folder / output["file"]
        suffix = path.suffix.lower()
        if not path.is_file():
            missing.append(output["file"])
            outputs.append(output)
        elif suffix in VIDEO_SUFFIXES:
            outputs.append({"file": output["file"], "kind": "video", **probe_video(path)})
        elif suffix in IMAGE_SUFFIXES:
            outputs.append({"file": output["file"], "kind": "image", **probe_image(path)})
        else:
            outputs.append({"file": output["file"], "kind": "other", "size": path.stat().st_size})
    return outputs, missing


def rederive_stats(result: dict) -> dict:
    stored = result.get("generation_stats") or {}
    if (result.get("final_status") or {}).get("status") != "completed":
        return {**stored, "kept": "the generation did not complete: there is nothing to derive"}
    preset_stats = stored.get("preset_stats") or {}
    if "before" not in preset_stats or "after" not in preset_stats:
        return {**stored, "kept": "the run did not record the preset statistics read before and after it, so its derived values cannot be checked again"}
    return {**derive_run_stats(preset_stats["before"], preset_stats["after"]), "previous_peak_vram_mb": stored.get("peak_vram_mb")}


def reevaluate_cell(pack: Pack, entry: dict, folder: Path, result: dict) -> dict:
    previous = result.get("verdict")
    record = {
        "schema": 1,
        "cell": entry["cell"],
        "warm_repeat": entry.get("warm_repeat", False),
        "generation_id": result.get("generation_id"),
        "reevaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "potion_audit": __version__,
        "checks_version": CHECKS_VERSION,
        "previous": {"verdict": previous, "checks_version": result.get("checks_version", 1), "checks": result.get("checks")},
        "pack": {"id": pack.id, "sha256": pack.sha256, "same_as_run": pack.sha256 == (result.get("pack") or {}).get("sha256")},
        "generation_stats": rederive_stats(result),
    }
    completed = (result.get("final_status") or {}).get("status") == "completed"
    cell = next((item for item in pack.cells if item.id == entry["cell"]), None)
    if previous not in CHECKED_VERDICTS or not completed:
        return {**record, "verdict": previous, "changed": False, "checks": result.get("checks"), "kept": "the generation did not complete: there is nothing to check again"}
    if cell is None:
        return {**record, "verdict": previous, "changed": False, "checks": result.get("checks"), "kept": f"the pack {pack.id} has no cell {entry['cell']}"}
    checks = cell_checks(pack, cell)
    outputs, missing = _reprobe(folder, result.get("outputs") or [])
    report_path = folder / "run_report.json"
    run_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    rechecked = evaluate(checks, outputs) + evaluate_run_report(checks, run_report)
    verdict = "PASS" if all(check["ok"] for check in rechecked) else "FAIL"
    return {
        **record,
        "verdict": verdict,
        "changed": verdict != previous,
        "checks": rechecked,
        "outputs_missing": missing,
        "run_report_missing": not report_path.is_file(),
    }


def reevaluate_run(run_dir: Path, pack: Pack, log: Callable[[str], None] = print) -> list[dict]:
    run = load_run_json(run_dir)
    run_pack = run.get("pack") or {}
    if run_pack.get("id") != pack.id:
        raise ReevaluateError(f"{run_dir.name} ran the pack {run_pack.get('id')}, not {pack.id}")
    if run_pack.get("sha256") != pack.sha256:
        log(f"warning: {run_dir.name} ran another version of {pack.id} ({str(run_pack.get('sha256'))[:12]}), its checks are taken from {pack.sha256[:12]}")
    records = []
    for entry in run.get("cells") or ():
        if not entry.get("verdict"):
            continue
        folder = run_dir / "cells" / cell_folder(entry["cell"], entry.get("warm_repeat", False))
        result_path = folder / "result.json"
        if not result_path.is_file():
            log(f"{entry['cell']}: no result.json, skipped")
            continue
        record = reevaluate_cell(pack, entry, folder, json.loads(result_path.read_text(encoding="utf-8")))
        (folder / REEVALUATED).write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        records.append(record)
        if record["changed"]:
            log(f"{entry['cell']}{' warm' if record['warm_repeat'] else ''}: {record['previous']['verdict']} -> {record['verdict']}")
        stats = record["generation_stats"]
        if not stats.get("kept") and stats.get("peak_vram_mb") != stats.get("previous_peak_vram_mb"):
            log(f"{entry['cell']}{' warm' if record['warm_repeat'] else ''}: peak VRAM {stats.get('previous_peak_vram_mb')} -> {stats.get('peak_vram_mb')} MiB ({stats.get('peak_vram_source')})")
    changed = sum(1 for record in records if record["changed"])
    log(f"{run_dir.name}: {len(records)} cells checked again with checks version {CHECKS_VERSION}, {changed} changed")
    return records
