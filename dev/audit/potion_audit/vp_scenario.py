import json
import os
import re
import sys
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import av
import numpy as np
from PIL import Image

from .check import runner_info
from .client import ApiClient, ApiError, unwrap
from .config import load_config, credentials
from .inputs import Uploads
from .matrix import HEALTHY, instance_health
from .media import probe_video
from .pack import DEFAULT_PACK, Pack, estimate, expand, load_pack
from .plan import timing_by_preset
from .run import DEFAULT_TIMEOUT, OOM_CODES, RunRefused, all_preset_stats, derive_run_stats, ensure_idle, evaluate, evaluate_run_report, phases, read_outputs, step_seconds, wait_for_stats

VP = "/api/plugins/video-producer"
PLUGIN_ID = "video-producer"
MARK = "potion-audit"
ENGINES = (
    "plugin:video-producer/Wan2.1-T2V-1.3B-8GB",
    "plugin:video-producer/Wan2.2-TI2V-5B-8GB",
    "plugin:video-producer/Wan2.2-14B-Lightning-12GB",
    "plugin:video-producer/MiniMax-H3-12GB",
    "plugin:video-producer/MiniMax-H3-Fast-12GB",
)
UPSCALERS = {"seedvr2": "core/SeedVR2:video_upscale", "rtx": "plugin:nvidia-rtx-upscale/RTX-Upscale:video_upscale"}
TARGETS = ("auto", "hd720", "fhd1080", "qhd1440", "uhd2160")
QUALITIES = ("draft", "final")
FL2VA = "FL2VA"
REF2VA = "Ref2VA"
REFS_MODE = "refs"
TAKE_TERMINAL = {"done", "failed", "cancelled"}
EXPORT_TERMINAL = {"done", "failed", "cancelled"}
IMAGE_START = {"i2v", "flf"}
FPS = 24
SHOT_SECONDS = 5.0
DURATION_SLACK = 0.1
LOOKS_ATTEMPTS = 30
STOP_AFTER = {"OOM": "stopped after an OOM: the instance needs a restart, with the operator's consent"}
SAFE = re.compile(r"[^A-Za-z0-9._-]+")
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 2
EXIT_STOPPED = 3
LUMI_CARD = "card-lumi"
WORKSHOP_CARD = "place-workshop"
REFERENCES = (("ref-lumi", "lumi", "Lumi", "Personnage", LUMI_CARD), ("ref-bottle", "bottle", "PotionUI bottle", "Objet", None))
FRAME_ROLES = ("first", "last")
FRAME_STRENGTH = 100
FRAME_STEP = 0.04
LIGHTNING_I2V_ID = "01M57QPEMDPKHHW83YSEYBN0X2"
CHAIN_IMAGE = "image"
CHAIN_TEXT = "text"
CHAIN_TEXT_WARNING = "chain_text_only"
EXPECTATIONS = {
    "Wan2.1-T2V-1.3B-8GB": {"chain": CHAIN_TEXT, "flf_reason": "Wan 2.1 T2V 1.3B is a text-to-video model: it takes neither a first nor a last image", "image_preset": None},
    "Wan2.2-TI2V-5B-8GB": {"chain": CHAIN_IMAGE, "flf_reason": "Wan 2.2 TI2V 5B starts from a first image only: the model knows no last image", "image_preset": None},
    "Wan2.2-14B-Lightning-12GB": {"chain": CHAIN_IMAGE, "flf_reason": None, "image_preset": {"id": LIGHTNING_I2V_ID, "key": "Wan2.2-14B-Lightning-I2V-12GB"}},
    "MiniMax-H3-12GB": {"chain": CHAIN_IMAGE, "flf_reason": None, "image_preset": None},
    "MiniMax-H3-Fast-12GB": {"chain": CHAIN_IMAGE, "flf_reason": None, "image_preset": None},
}
SHOTS = (
    {
        "id": "s1-workshop",
        "label": "1 Workshop",
        "chain": False,
        "frames": None,
        "profile": FL2VA,
        "characters": [],
        "place": WORKSHOP_CARD,
        "prompt": "wide establishing shot of {workshop}, a small glowing violet potion bottle on the oak workbench in the middle, the camera slowly pushing in towards the bench, {motion}",
    },
    {
        "id": "s2-bottle",
        "label": "2 Bottle",
        "chain": True,
        "frames": None,
        "profile": FL2VA,
        "characters": [],
        "place": WORKSHOP_CARD,
        "prompt": "close-up of {bottle}, the violet liquid swirling with glowing golden particles, a thin mist rising from the neck, the camera still slowly pushing in, {motion}",
    },
    {
        "id": "s3-lumi",
        "label": "3 Lumi",
        "chain": False,
        "frames": None,
        "profile": REF2VA,
        "characters": [LUMI_CARD],
        "place": WORKSHOP_CARD,
        "prompt": "{lumi}, standing at the oak workbench of {workshop}, lifts the potion bottle, looks at it and smiles without a word, medium close-up, {motion}",
    },
    {
        "id": "s4-gold",
        "label": "4 Gold",
        "chain": False,
        "frames": ("bottle", "bottle-gold"),
        "profile": FL2VA,
        "characters": [],
        "place": WORKSHOP_CARD,
        "prompt": "close-up of {bottle}, the glowing violet liquid slowly turns to molten gold, golden sparks swirl around the neck, {motion}",
    },
)
UPLOADED = tuple(dict.fromkeys([reference[1] for reference in REFERENCES] + [input_id for shot in SHOTS for input_id in shot["frames"] or ()]))
LANES = (("A1", "Dialogue", "Dialogue", 0, 0), ("A2", "Music", "Musique", -2, 0), ("A3", "Ambience", "Ambiance", -6, -0.2), ("A4", "Foley", "SFX", -4, 0.3))


def engine_key(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def project_prefix(run_id: str) -> str:
    return f"{MARK} {run_id} "


def project_name(run_id: str, ref: str) -> str:
    return (project_prefix(run_id) + engine_key(ref))[:200]


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def matrix_files(paths: list[Path]) -> list[Path]:
    found = []
    for path in paths:
        if path.is_file():
            found.append(path)
            continue
        night = path / "night.json"
        if night.is_file():
            segments = json.loads(night.read_text(encoding="utf-8")).get("segments") or []
            found.extend(path.parent / str(segment["run_id"]) / "run.json" for segment in segments)
            continue
        named = [path / name for name in ("run.json", "results.json") if (path / name).is_file()]
        if not named:
            raise RunRefused(f"{path.name}: no run.json, results.json or night.json in this folder")
        found.append(named[0])
    for path in found:
        if not path.is_file():
            raise RunRefused(f"the matrix file {path.parent.name}/{path.name} does not exist")
    return found


def load_matrix(paths: list[Path]) -> dict:
    cells = {}
    files = matrix_files(paths)
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("cells") if isinstance(data.get("cells"), list) else data.get("results") or []
        for entry in entries:
            verdict = entry.get("verdict")
            if not verdict or not entry.get("cell"):
                continue
            cell = cells.setdefault(entry["cell"], {"verdicts": [], "cold_seconds": None, "warm_seconds": None})
            cell["verdicts"].append(verdict)
            if verdict == "PASS" and entry.get("run_seconds") is not None:
                cell["warm_seconds" if entry.get("warm_repeat") else "cold_seconds"] = float(entry["run_seconds"])
    return {"files": [f"{path.parent.name}/{path.name}" for path in files], "cells": cells}


def passed(matrix: dict | None, cell: str) -> bool:
    if matrix is None:
        return True
    found = matrix["cells"].get(cell)
    return bool(found) and all(verdict == "PASS" for verdict in found["verdicts"])


def _not_passed(matrix: dict, cell: str) -> str:
    found = matrix["cells"].get(cell)
    if not found:
        return f"the matrix did not run {cell}"
    return f"{cell} did not pass the matrix ({', '.join(found['verdicts'])})"


def _named(names: list[str]) -> list[str]:
    chosen = []
    for name in names:
        hits = [ref for ref in ENGINES if name.lower() in (ref.lower(), engine_key(ref).lower())]
        if not hits:
            raise RunRefused(f"--engines: {name!r} is none of {', '.join(engine_key(ref) for ref in ENGINES)}")
        chosen.extend(hit for hit in hits if hit not in chosen)
    return chosen


def select_engines(pack: Pack, matrix: dict | None, names: list[str] | None) -> list[dict]:
    if matrix is None and not names:
        raise RunRefused("vp run needs a matrix (--matrix <run.json or run folder>) or --engines")
    wanted = _named(names) if names else list(ENGINES)
    engines = []
    for ref in ENGINES:
        preset = pack.preset(ref)
        if preset is None:
            raise RunRefused(f"the case file of the pack has no preset {ref}")
        expected = EXPECTATIONS[engine_key(ref)]
        entry = {
            "engine": ref,
            "key": engine_key(ref),
            "preset_id": preset["id"],
            "selected": True,
            "reason": None,
            "ref2va": False,
            "ref2va_reason": None,
            "chain": expected["chain"],
            "flf": expected["flf_reason"] is None,
            "flf_reason": expected["flf_reason"],
            "image_preset": expected["image_preset"],
        }
        if ref not in wanted:
            entry.update(selected=False, reason="left out by --engines")
        elif not passed(matrix, f"{ref}:video"):
            entry.update(selected=False, reason=_not_passed(matrix, f"{ref}:video"))
        if REFS_MODE not in preset.get("modes", ()):
            entry["ref2va_reason"] = f"{entry['key']} has no {REFS_MODE} mode, so the plugin offers no {REF2VA} profile"
        elif not passed(matrix, f"{ref}:{REFS_MODE}"):
            entry["ref2va_reason"] = _not_passed(matrix, f"{ref}:{REFS_MODE}")
        else:
            entry["ref2va"] = True
        engines.append(entry)
    return engines


def upscaler_state(pack: Pack, matrix: dict | None, upscaler: str) -> dict:
    cell = UPSCALERS[upscaler]
    preset = pack.preset(cell.rsplit(":", 1)[0]) or {}
    state = {"upscaler": upscaler, "cell": cell, "preset_id": preset.get("id"), "allowed": True, "reason": None}
    if not passed(matrix, cell):
        others = [name for name, other in UPSCALERS.items() if name != upscaler and passed(matrix, other)]
        hint = f": pass --upscaler {others[0]}" if others else ""
        state.update(allowed=False, reason=_not_passed(matrix, cell) + hint)
    return state


def shot_prompt(pack: Pack, shot: dict) -> str:
    return expand(pack, shot["prompt"])


def _asset(asset_id: str, name: str, kind: str, src, origin, width, height, generated: bool = False, quality=None, result_id=None, seconds=None, fps=None) -> dict:
    return {
        "id": asset_id,
        "kind": kind,
        "name": name,
        "src": src,
        "origin": origin,
        "srcDur": seconds,
        "width": width,
        "height": height,
        "fps": fps,
        "res": f"{width}x{height}" if width and height else None,
        "generated": generated,
        "quality": quality,
        "resultId": result_id,
        "role": None,
    }


def _lane(lane_id: str, name: str, role: str, vol: float, pan: float) -> dict:
    return {
        "id": lane_id,
        "name": name,
        "role": role,
        "vol": vol,
        "pan": pan,
        "mute": False,
        "solo": False,
        "sends": {"R1": -12, "D1": -60},
        "inserts": [{"type": "eq", "on": True, "low": 0, "mid": 0, "high": 0}, {"type": "comp", "on": False, "threshold": -18, "ratio": 3, "attack": 10, "release": 120}],
    }


def _frame_time(start: float, role: str) -> float:
    return round(start + SHOT_SECONDS - FRAME_STEP, 3) if role == "last" else start


def companion_options(engine: dict, companion_steps: int | None) -> dict:
    if not companion_steps or not engine.get("image_preset"):
        return {}
    return {engine["image_preset"]["id"]: {"speed_profile": "custom", "steps": companion_steps, "cfg": 1.0}}


def build_doc(pack: Pack, engine: dict, run_id: str, media: dict, companion_steps: int | None = None) -> dict:
    preset_id = engine["preset_id"]
    clips = []
    prompts = []
    frames = []
    start = 0.0
    for index, shot in enumerate(SHOTS):
        clip = {
            "id": shot["id"],
            "assetId": None,
            "start": start,
            "dur": SHOT_SECONDS,
            "srcIn": 0,
            "label": shot["label"],
            "stage": "todo",
            "take": None,
            "fadeIn": 0,
            "fadeOut": 0,
            "exposure": 0,
            "contrast": 100,
            "saturation": 100,
            "temperature": 0,
            "preset": "Original",
            "flag": None,
            "cast": {"characters": list(shot["characters"]), "place": shot["place"]},
            "firstFromPrevious": shot["chain"],
            "engine": {"preset": preset_id, "model": None, "profile": shot["profile"], "seed": pack.seed + index},
        }
        clips.append(clip)
        prompts.append({"id": f"p-{shot['id']}", "shotId": shot["id"], "start": start, "dur": SHOT_SECONDS, "strength": 75, "text": shot_prompt(pack, shot)})
        for role, input_id in zip(FRAME_ROLES, shot["frames"] or ()):
            frames.append({"id": f"f-{shot['id']}-{role}", "shotId": shot["id"], "time": _frame_time(start, role), "assetId": f"frame-{input_id}", "role": role, "strength": FRAME_STRENGTH})
        start += SHOT_SECONDS
    assets = []
    references = []
    for reference_id, input_id, name, kind, _ in REFERENCES:
        spec = pack.inputs[input_id]
        src, origin = media.get(input_id, (f"input:{input_id}", None))
        assets.append(_asset(f"asset-{input_id}", Path(spec.file).name, "image", src, origin, spec.width, spec.height))
        references.append({"id": reference_id, "name": name, "space": "identite", "type": kind, "assetId": f"asset-{input_id}", "role": "Identité", "scope": {"type": "global"}})
    for input_id in dict.fromkeys(input_id for shot in SHOTS for input_id in shot["frames"] or ()):
        spec = pack.inputs[input_id]
        src, origin = media.get(input_id, (f"input:{input_id}", None))
        assets.append(_asset(f"frame-{input_id}", Path(spec.file).name, "image", src, origin, spec.width, spec.height))
    engine_settings = {"quality": "Standard", "variants": 1, "backend": "native", "preset": preset_id, "model": None, "seed": pack.seed, "loras": []}
    options = companion_options(engine, companion_steps)
    if options:
        engine_settings["options"] = options
    return {
        "name": project_name(run_id, engine["engine"]),
        "fps": FPS,
        "aspect": "16:9",
        "resolution": "1080p",
        "promptLanguage": "en",
        "direction": {
            "univers": "A witch's cottage workshop at night, where a glowing violet potion is brewed.",
            "personnages": "",
            "photographie": "Each shot is one continuous take; motivated light from the hearth and the candles.",
            "palette": "Midnight blue, copper and cream, the violet of the potion as the constant colour, gold for the magic.",
            "rythme": "Calm and slow.",
            "mode": FL2VA,
        },
        "synopsis": f"{MARK} {run_id}: a wide shot of the workshop, a close-up of the potion bottle chained on it, Lumi lifting the bottle, then the potion turning to gold between a first and a last image.",
        "clips": clips,
        "audio": [],
        "titles": [],
        "prompts": prompts,
        "frames": frames,
        "markers": [{"id": "m-run", "time": 0, "label": f"{MARK} {run_id}", "kind": "marker"}],
        "references": references,
        "lanes": [_lane(*lane) for lane in LANES],
        "aux": [{"id": "R1", "name": "Reverb", "vol": -6, "mute": False}, {"id": "D1", "name": "Delay", "vol": -10, "mute": False}],
        "master": {"vol": 0},
        "engine": engine_settings,
        "assets": assets,
        "firstFromPrevious": False,
        "bible": {
            "characters": [{"id": LUMI_CARD, "label": "Lumi", "text": expand(pack, "{lumi}"), "props": "a small glowing violet potion bottle", "references": ["ref-lumi"]}],
            "places": [{"id": WORKSHOP_CARD, "label": "Workshop", "text": expand(pack, "{workshop}"), "references": []}],
        },
        "dialogueLanguage": "English",
    }


def take_order(engine: dict, shot: dict, quality: str, run_id: str) -> dict:
    return {"shots": [shot["id"]], "quality": quality, "variants": 1, "preset_id": engine["preset_id"], "model_id": None, "label": f"{MARK} {run_id} {shot['id']}"[:200]}


def final_order(take_id: str, upscaler: str, target: str) -> dict:
    return {"takes": [take_id], "method": "upscale", "target": target, "upscaler": upscaler}


def export_order() -> dict:
    return {"format": "web"}


def _measure(matrix: dict | None, cell: str, warm: bool) -> float | None:
    if matrix is None or not passed(matrix, cell):
        return None
    found = matrix["cells"][cell]
    return found["warm_seconds"] if warm and found["warm_seconds"] is not None else found["cold_seconds"]


def _estimate(matrix: dict | None, timing: dict, cell: str, preset_id: str | None, warm: bool) -> tuple[float | None, str | None]:
    seconds = _measure(matrix, cell, warm)
    if seconds is not None:
        return seconds, f"run seconds of {cell}{' (warm)' if warm else ''} in the matrix"
    seconds = estimate(timing.get(preset_id), warm)
    if seconds is not None:
        return seconds, f"{'warm' if warm else 'cold'} average of the preset in /api/stats/presets/timing"
    return None, None


def not_offered(engine: dict, shot: dict) -> str | None:
    if shot["profile"] == REF2VA and not engine["ref2va"]:
        return engine["ref2va_reason"]
    if shot["frames"] and not engine["flf"]:
        return engine["flf_reason"]
    return None


def text_chain(engine: dict | None, shot: dict) -> bool:
    return bool(shot["chain"] and engine and engine.get("chain") == CHAIN_TEXT)


def image_shot(engine: dict | None, shot: dict) -> bool:
    return bool(shot["frames"] or (shot["chain"] and not text_chain(engine, shot)))


def expected_checks(engine: dict, shot: dict) -> tuple[list[str], list[str]]:
    checks = ["profile"]
    skipped = []
    if text_chain(engine, shot):
        checks += ["chain_mode", "chain_warning"]
        skipped += ["chain_frame", "chain_start"]
    elif shot["chain"]:
        checks += ["chain_frame", "chain_start"]
    if shot["frames"]:
        checks.append("flf_start")
    if image_shot(engine, shot) and engine.get("image_preset"):
        checks.append("image_preset")
    return checks, skipped


def plan_engine(pack: Pack, engine: dict, matrix: dict | None, timing: dict, final: dict, quality: str, target: str, run_id: str) -> list[dict]:
    steps = []
    for index, shot in enumerate(SHOTS):
        step = {"step": "take", "shot": shot["id"], "profile": shot["profile"], "chained_on": SHOTS[index - 1]["id"] if shot["chain"] else None, "frames": list(shot["frames"] or ()), "status": "planned", "reason": None, "order": take_order(engine, shot, quality, run_id)}
        step["checks"], step["not_offered"] = expected_checks(engine, shot)
        reason = not_offered(engine, shot)
        if reason:
            step.update(status="skipped", reason=reason, order=None, checks=[], not_offered=[])
        cell = f"{engine['engine']}:{REFS_MODE if shot['profile'] == REF2VA else 'video'}"
        if step["status"] == "planned":
            step["estimate_seconds"], step["estimate_basis"] = _estimate(matrix, timing, cell, engine["preset_id"], index > 0)
        steps.append(step)
    step = {"step": "final_pass", "shot": SHOTS[0]["id"], "upscaler": final["upscaler"], "status": "planned", "reason": None, "order": final_order(f"<take of {SHOTS[0]['id']}>", final["upscaler"], target)}
    if not final["allowed"]:
        step.update(status="not_run", reason=final["reason"], order=None)
    else:
        step["estimate_seconds"], step["estimate_basis"] = _estimate(matrix, timing, final["cell"], final["preset_id"], False)
    steps.append(step)
    steps.append({"step": "export", "status": "planned", "reason": None, "order": export_order(), "estimate_seconds": None, "estimate_basis": None})
    return steps


def _check_plugin(client: ApiClient) -> str | None:
    plugins = unwrap(client.get_json("/api/plugins")) or []
    found = next((item for item in plugins if isinstance(item, dict) and item.get("id") == PLUGIN_ID), None)
    if not found or not found.get("enabled"):
        raise RunRefused(f"the {PLUGIN_ID} plugin is not enabled on the instance")
    unwrap(client.get_json(f"{VP}/health"))
    return found.get("version")


def _head(client: ApiClient, pack: Pack, run_id: str, dry_run: bool, machine: str | None, matrix: dict | None, quality: str, final: dict, target: str, companion_steps: int | None = None) -> dict:
    health = instance_health(client)
    if health not in HEALTHY:
        raise RunRefused(f"the instance is not healthy: {health}")
    ensure_idle(client)
    plugin_version = _check_plugin(client)
    return {
        "schema": 1,
        "kind": "vp-scenario",
        "run_id": run_id,
        "dry_run": dry_run,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ended_at": None,
        "machine": machine,
        "app_version": ((client.get_json("/openapi.json") or {}).get("info") or {}).get("version"),
        "plugin": {"id": PLUGIN_ID, "version": plugin_version},
        "pack": {"id": pack.id, "version": pack.version, "file": pack.path.name, "sha256": pack.sha256},
        "cases": {"file": pack.case_set.path.name, "sha256": pack.case_set.sha256},
        "matrix": matrix["files"] if matrix else None,
        "settings": {"quality": quality, "upscaler": final["upscaler"], "target": target, "shot_seconds": SHOT_SECONDS, "fps": FPS, "companion_steps": companion_steps},
        "final_pass": final,
        "runner": runner_info(),
        "stopped": None,
        "summary": {},
        "engines": [],
    }


def dry_run(client: ApiClient, pack: Pack, out_root: Path, run_id: str, engines: list[dict], matrix: dict | None, *, quality: str = "draft", upscaler: str = "seedvr2", target: str = "fhd1080", companion_steps: int | None = None, machine: str | None = None, log: Callable[[str], None] = print) -> dict:
    final = upscaler_state(pack, matrix, upscaler)
    plan = _head(client, pack, run_id, True, machine, matrix, quality, final, target, companion_steps)
    timing = timing_by_preset(client)
    run_dir = out_root / run_id
    for engine in engines:
        entry = {**engine, "project": None, "steps": [], "estimate_seconds": None}
        if engine["selected"]:
            doc = build_doc(pack, engine, run_id, {}, companion_steps)
            _write_json(run_dir / "projects" / f"{engine['key']}.json", doc)
            entry["project"] = {"name": doc["name"], "doc": f"projects/{engine['key']}.json", "shots": [clip["id"] for clip in doc["clips"]], "options": doc["engine"].get("options")}
            entry["steps"] = plan_engine(pack, engine, matrix, timing, final, quality, target, run_id)
            known = [step["estimate_seconds"] for step in entry["steps"] if step.get("estimate_seconds") is not None]
            entry["estimate_seconds"] = round(sum(known), 1)
        plan["engines"].append(entry)
    planned = [step for entry in plan["engines"] for step in entry["steps"] if step["status"] == "planned"]
    plan["summary"] = {
        "engines": len([entry for entry in plan["engines"] if entry["selected"]]),
        "generations": len([step for step in planned if step["step"] != "export"]),
        "exports": len([step for step in planned if step["step"] == "export"]),
        "estimated_seconds": round(sum(entry["estimate_seconds"] or 0 for entry in plan["engines"]), 1),
        "planned_without_estimate": len([step for step in planned if step.get("estimate_seconds") is None]),
    }
    plan["ended_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    _write_json(run_dir / "plan.json", plan)
    for entry in plan["engines"]:
        if not entry["selected"]:
            log(f"{entry['key']}: left out, {entry['reason']}")
            continue
        log(f"{entry['key']}: {entry['estimate_seconds'] / 60:.1f} min estimated")
        for step in entry["steps"]:
            seconds = "" if step.get("estimate_seconds") is None else f"{step['estimate_seconds']:7.1f} s"
            what = step["step"] + (f" {step['shot']}" if step["step"] == "take" else "")
            reason = f"  ({step['reason']})" if step["reason"] else ""
            log(f"  {what:22s} {step['status']:8s} {seconds}{reason}")
    summary = plan["summary"]
    log(f"{summary['engines']} engines, {summary['generations']} generations and {summary['exports']} exports planned, {summary['estimated_seconds'] / 60:.1f} min estimated, {summary['planned_without_estimate']} steps without an estimate")
    log(f"plan: {run_dir / 'plan.json'}")
    return plan


def _sample_gpu(client: ApiClient) -> dict:
    stats = unwrap(client.get_json("/api/system/stats")) or {}
    gpu = stats.get("gpu") or {}
    if not gpu.get("available"):
        return {}
    return {"vram_used_mb": gpu.get("vram_used"), "ram_used_mb": (stats.get("ram") or {}).get("used")}


def _take(client: ApiClient, project_id: str, take_id: str) -> dict:
    found = (unwrap(client.get_json(f"{VP}/projects/{project_id}/takes")) or {}).get("takes") or []
    return next((take for take in found if take.get("id") == take_id), {})


def follow_take(client: ApiClient, project_id: str, take_id: str, timeout: float, interval: float, clock: Callable[[], float], sleep: Callable[[float], None], log: Callable[[str], None]) -> tuple[dict, list[dict], bool]:
    started = clock()
    samples = []
    last_line = None
    while True:
        take = _take(client, project_id, take_id)
        status = {}
        if take.get("generation_id"):
            status = unwrap(client.get_json(f"/api/generations/{take['generation_id']}/status")) or {}
        sample = {
            "t": round(clock() - started, 3),
            "take_status": take.get("status"),
            "status": status.get("status") or take.get("status"),
            "progress": status.get("progress", take.get("progress")),
            "step": status.get("current_step_num"),
            "total_steps": status.get("total_steps"),
            "current_step": status.get("current_step") or take.get("step"),
            **_sample_gpu(client),
        }
        samples.append(sample)
        line = f"{sample['take_status']} {sample['status']} {sample['step']}/{sample['total_steps']} {sample['current_step'] or ''}".strip()
        if line != last_line:
            log(f"  {sample['t']:7.1f} s  {line}")
            last_line = line
        if take.get("status") in TAKE_TERMINAL:
            return take, samples, False
        if clock() - started > timeout:
            return take, samples, True
        sleep(interval)


def _failure(client: ApiClient, take: dict) -> dict | None:
    detail = {}
    if take.get("generation_id"):
        found = client.get_json(f"/api/generations/{take['generation_id']}/failure", missing_ok=True)
        detail = unwrap(found) if found else {}
    code = (detail or {}).get("error_code") or take.get("error_code")
    if not detail and not take.get("error_code"):
        return None
    return {
        "error_code": code,
        "message": (detail or {}).get("message") or take.get("error_message"),
        "failed_pipe_name": (detail or {}).get("failed_pipe_name"),
        "failed_at_step": (detail or {}).get("failed_at_step"),
        "take_error_code": take.get("error_code"),
    }


def estimate_warnings(estimate: dict | None, shot_id: str) -> list[str] | None:
    if not isinstance(estimate, dict) or "warnings" not in estimate:
        return None
    codes = []
    for warning in estimate.get("warnings") or ():
        about = (warning.get("data") or {}).get("shot_id")
        if warning.get("code") and about in (None, shot_id) and warning["code"] not in codes:
            codes.append(warning["code"])
    return codes


def take_checks(shot: dict | None, take: dict, previous: dict | None, engine: dict | None = None, estimate: dict | None = None) -> tuple[dict, list[dict], list[dict]]:
    checks = {"min_outputs": 1, "not_black": True}
    extra = []
    skipped = []
    mode = take.get("director_mode")
    if mode in IMAGE_START:
        checks["forbidden_steps"] = ["TXT2VID"]
    if shot is None:
        return checks, extra, skipped
    extra.append({"check": "profile", "expected": shot["profile"], "actual": take.get("profile"), "ok": take.get("profile") == shot["profile"]})
    if text_chain(engine, shot):
        reason = f"{engine['key']} generates from text only: the plugin starts the chained shot from its text and warns with {CHAIN_TEXT_WARNING}"
        skipped += [{"check": "chain_frame", "reason": reason}, {"check": "chain_start", "reason": reason}]
        codes = estimate_warnings(estimate, shot["id"])
        extra.append({"check": "chain_mode", "expected": "t2v", "actual": mode, "ok": mode == "t2v"})
        extra.append({"check": "chain_warning", "expected": f"{CHAIN_TEXT_WARNING} among the warnings of the estimate", "actual": codes, "ok": bool(codes) and CHAIN_TEXT_WARNING in codes})
    elif shot["chain"]:
        chain = take.get("chain") or {}
        source = chain.get("source") or {}
        expected = previous.get("id") if previous else None
        extra.append({"check": "chain_frame", "expected": f"the last image of {SHOTS[0]['id']} ({expected})", "actual": {"state": chain.get("state"), "source": source}, "ok": chain.get("state") == "taken" and source.get("shotId") == SHOTS[0]["id"]})
        extra.append({"check": "chain_start", "expected": f"a director mode that starts from an image ({', '.join(sorted(IMAGE_START))})", "actual": mode, "ok": mode in IMAGE_START})
    if shot["frames"]:
        extra.append({"check": "flf_start", "expected": f"flf, from the first and the last image of the shot ({' and '.join(shot['frames'])})", "actual": mode, "ok": mode == "flf"})
    if image_shot(engine, shot) and engine and engine.get("image_preset"):
        wanted = engine["image_preset"]
        extra.append({"check": "image_preset", "expected": f"{wanted['key']} ({wanted['id']})", "actual": take.get("preset_id"), "ok": take.get("preset_id") == wanted["id"]})
    return checks, extra, skipped


def stats_preset_of(record: dict, take: dict, ordered: str) -> dict:
    found = {"preset_id": ordered, "source": "the preset the audit ordered"}
    for source, value in (("the generation record", record.get("preset_id")), ("the take", take.get("preset_id"))):
        if value:
            found = {"preset_id": str(value), "source": source}
            break
    return {
        **found,
        "name": None,
        "ordered_preset_id": ordered,
        "record_preset_id": record.get("preset_id"),
        "take_preset_id": take.get("preset_id"),
        "differs": found["preset_id"] != ordered,
    }


def collect_take(client: ApiClient, take: dict, samples: list[dict], timed_out: bool, preset_id: str, stats_before: dict[str, dict], shot: dict | None, previous: dict | None, folder: Path, head: dict, interval: float, sleep: Callable[[float], None], engine: dict | None = None) -> dict:
    generation_id = take.get("generation_id")
    result = {**head, "generation_id": generation_id, "take": take, "samples": samples, "final_status": {"take": take.get("status")}}
    checks, extra, skipped = take_checks(shot, take, previous, engine, head.get("estimate"))
    if skipped:
        result["not_offered"] = skipped
    run_report = {}
    record = {}
    if generation_id:
        result["final_status"]["generation"] = unwrap(client.get_json(f"/api/generations/{generation_id}/status")) or {}
        record = unwrap(client.get_json(f"/api/generations/history/{generation_id}")) or {}
        chosen = stats_preset_of(record, take, preset_id)
        before = stats_before.get(chosen["preset_id"], {})
        admin, stats_after = wait_for_stats(client, generation_id, chosen["preset_id"], before, 10, interval, sleep)
        chosen["name"] = stats_after.get("preset_name") or before.get("preset_name")
        result["stats_preset"] = chosen
        run_report = admin.get("run_report") or {}
        result["generation_stats"] = derive_run_stats(before, stats_after) if take.get("status") == "done" else {"derived": False, "reason": "the take did not finish"}
    else:
        result["generation_stats"] = {"derived": False, "reason": "the take has no generation"}
    result["timing"] = {
        "run_seconds": record.get("run_seconds"),
        "queued_seconds": record.get("queued_seconds"),
        "duration_ms": record.get("duration_ms"),
        "seconds_per_step_polled": step_seconds(samples),
        "total_steps_polled": max((sample["total_steps"] for sample in samples if isinstance(sample.get("total_steps"), int)), default=None),
        "take_started_at": take.get("started_at"),
        "take_finished_at": take.get("finished_at"),
        **phases(run_report),
    }
    vram = [sample["vram_used_mb"] for sample in samples if sample.get("vram_used_mb") is not None]
    ram = [sample["ram_used_mb"] for sample in samples if sample.get("ram_used_mb") is not None]
    result["memory"] = {"peak_vram_used_mb_sampled": max(vram) if vram else None, "peak_ram_used_mb_sampled": max(ram) if ram else None, "source": "GET /api/system/stats at each poll, whole device"}
    result["has_profile"] = bool(record.get("has_profile"))
    _write_json(folder / "run_report.json", run_report)
    if take.get("status") == "done" and generation_id:
        bundle = client.download(f"/api/generations/history/{generation_id}/export-bundle", folder / "bundle.zip")
        result["bundle"] = {"file": bundle.path.name, "size": bundle.size}
        result["outputs"] = read_outputs(bundle.path, folder)
        result["checks"] = evaluate(checks, result["outputs"]) + evaluate_run_report(checks, run_report) + extra
        result["verdict"] = "PASS" if all(check["ok"] for check in result["checks"]) else "FAIL"
    else:
        result["failure"] = _failure(client, take)
        codes = {(result["failure"] or {}).get("error_code"), take.get("error_code")}
        if timed_out:
            result["verdict"] = "TIMEOUT"
        elif codes & OOM_CODES:
            result["verdict"] = "OOM"
        else:
            result["verdict"] = "FAIL"
    _write_json(folder / "result.json", result)
    return result


def _video(result: dict) -> Path | None:
    for output in result.get("outputs") or ():
        if output.get("kind") == "video":
            return Path(result["folder"]) / output["file"]
    return None


def edge_frame(path: Path, last: bool) -> np.ndarray | None:
    found = None
    with av.open(str(path)) as container:
        for frame in container.decode(container.streams.video[0]):
            found = frame.to_ndarray(format="rgb24")
            if not last:
                break
    return found


def frame_gap(before: Path, after: Path) -> dict:
    a = edge_frame(before, True)
    b = edge_frame(after, False)
    if a is None or b is None:
        return {"measured": False, "reason": "a video has no frame"}
    height = min(a.shape[0], b.shape[0])
    width = min(a.shape[1], b.shape[1])
    a = np.asarray(Image.fromarray(a).resize((width, height), Image.Resampling.LANCZOS), dtype=np.float64)
    b = np.asarray(Image.fromarray(b).resize((width, height), Image.Resampling.LANCZOS), dtype=np.float64)
    mse = float(np.mean((a - b) ** 2))
    return {
        "measured": True,
        "size": f"{width}x{height}",
        "mean_abs_diff": round(float(np.mean(np.abs(a - b))), 3),
        "psnr_db": None if mse == 0 else round(10 * np.log10(255.0**2 / mse), 2),
        "source": "last decoded frame of the first shot's take against the first decoded frame of the second shot's take, RGB 0-255, both scaled to the smaller size",
    }


def _versioned(client: ApiClient, project_id: str) -> tuple[dict, int]:
    project = unwrap(client.get_json(f"{VP}/projects/{project_id}"))["project"]
    return project["doc"], project["version"]


def place_take(client: ApiClient, project_id: str, take: dict, label: str) -> int:
    doc, version = _versioned(client, project_id)
    clip = next(clip for clip in doc["clips"] if clip["id"] == take["shot_id"])
    asset_id = f"take-{take['id']}"
    origin = {"kind": "history", "generationId": take["generation_id"], "fileId": str(take["file_id"])}
    asset = _asset(asset_id, f"{clip['label']} {take.get('quality') or ''} {take.get('variant') or ''}".strip(), "video", take.get("url"), origin, take.get("width"), take.get("height"), True, take.get("quality") if take.get("quality") in QUALITIES else None, take["id"], take.get("duration_s"), take.get("fps"))
    doc["assets"] = [item for item in doc["assets"] if item["id"] != asset_id] + [asset]
    clip.update({"assetId": asset_id, "take": take["id"], "srcIn": 0, "stage": take.get("quality") if take.get("quality") in QUALITIES else "draft"})
    saved = unwrap(client.put_json(f"{VP}/projects/{project_id}", {"doc": doc, "version": version, "label": label}))
    return saved["project"]["version"]


def _folder(run_dir: Path, *parts: str) -> Path:
    folder = run_dir.joinpath(*(SAFE.sub("_", part) for part in parts))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def read_estimate(client: ApiClient, project_id: str, order: dict) -> dict:
    try:
        payload = unwrap(client.post_json(f"{VP}/projects/{project_id}/estimate", order)) or {}
    except ApiError as error:
        return {"error": str(error)}
    return {"shots": payload.get("shots") or [], "blocks": payload.get("blocks") or [], "warnings": payload.get("warnings") or []}


def run_take(client: ApiClient, project_id: str, engine: dict, shot: dict | None, order: dict, path: str, previous: dict | None, folder: Path, head: dict, timeout: float, interval: float, clock, sleep, log, stats_preset: str) -> dict:
    ensure_idle(client)
    estimate = read_estimate(client, project_id, order) if shot is not None else None
    stats_before = all_preset_stats(client)
    log(f"{engine['key']} {head['step']}: ordering")
    head = {**head, "submitted_at": datetime.now(UTC).isoformat(timespec="seconds"), "order": order}
    if estimate is not None:
        head["estimate"] = estimate
    try:
        created = (unwrap(client.post_json(path, order)) or {}).get("takes") or []
    except ApiError as error:
        result = {**head, "verdict": "BLOCKED", "reason": str(error), "blocked": {"status": error.status, "detail": error.detail}}
        _write_json(folder / "result.json", result)
        log(f"{engine['key']} {head['step']}: BLOCKED, {error}")
        return result
    wanted = [take for take in created if shot is None or take.get("shot_id") == shot["id"]]
    if not wanted:
        result = {**head, "verdict": "REJECTED", "reason": "the plugin answered no take"}
        _write_json(folder / "result.json", result)
        return result
    take_id = wanted[0]["id"]
    try:
        take, samples, timed_out = follow_take(client, project_id, take_id, timeout, interval, clock, sleep, log)
    except KeyboardInterrupt:
        client.post_json(f"{VP}/takes/{take_id}/cancel", {})
        _write_json(folder / "result.json", {**head, "take": {"id": take_id}, "verdict": "STOPPED"})
        raise
    if timed_out:
        client.post_json(f"{VP}/takes/{take_id}/cancel", {})
    result = collect_take(client, take, samples, timed_out, stats_preset, stats_before, shot, previous, folder, {**head, "folder": str(folder)}, interval, sleep, engine)
    log(f"{engine['key']} {head['step']}: {result['verdict']} in {result['timing']['run_seconds']} s")
    return result


def run_export(client: ApiClient, project_id: str, folder: Path, head: dict, timeout: float, interval: float, clock, sleep, log, expected_seconds: float) -> dict:
    result = {**head, "order": export_order()}
    try:
        job = (unwrap(client.post_json(f"{VP}/projects/{project_id}/exports/video", export_order())) or {}).get("job") or {}
    except ApiError as error:
        result.update(verdict="BLOCKED", reason=str(error))
        _write_json(folder / "result.json", result)
        return result
    started = clock()
    while job.get("status") not in EXPORT_TERMINAL and clock() - started <= timeout:
        sleep(interval)
        job = (unwrap(client.get_json(f"{VP}/exports/{job['id']}")) or {}).get("job") or job
    result["job"] = job
    result["timing"] = {"polled_seconds": round(clock() - started, 3)}
    if job.get("status") != "done":
        result["verdict"] = "TIMEOUT" if job.get("status") not in EXPORT_TERMINAL else "FAIL"
        _write_json(folder / "result.json", result)
        return result
    download = client.download(f"{VP}/exports/{job['id']}/file", folder / "export.mp4")
    info = probe_video(download.path)
    result["outputs"] = [{"file": download.path.name, "kind": "video", "size": download.size, **info}]
    frames = round(expected_seconds * FPS)
    duration = info.get("duration_seconds")
    result["checks"] = [
        {"check": "duration", "expected": f"{expected_seconds} s within {DURATION_SLACK} s", "actual": duration, "ok": duration is not None and abs(duration - expected_seconds) <= DURATION_SLACK},
        {"check": "fps", "expected": FPS, "actual": info.get("fps"), "ok": info.get("fps") is not None and abs(info["fps"] - FPS) < 0.01},
        {"check": "frames", "expected": f"{frames} within 1", "actual": info.get("decoded_frames"), "ok": abs((info.get("decoded_frames") or 0) - frames) <= 1},
        {"check": "not_black", "expected": True, "actual": info.get("not_black"), "ok": bool(info.get("not_black"))},
    ]
    result["verdict"] = "PASS" if all(check["ok"] for check in result["checks"]) else "FAIL"
    _write_json(folder / "result.json", result)
    log(f"export: {result['verdict']}, {duration} s, {info.get('decoded_frames')} frames at {info.get('fps')} fps")
    return result


def read_looks(client: ApiClient, project_id: str, folder: Path, interval: float, sleep) -> dict:
    report = unwrap(client.post_json(f"{VP}/projects/{project_id}/looks", {})) or {}
    for _ in range(LOOKS_ATTEMPTS):
        if not report.get("queued"):
            break
        sleep(max(interval, 1.0))
        report = unwrap(client.get_json(f"{VP}/projects/{project_id}/looks")) or {}
    _write_json(folder / "looks.json", report)
    lumi = [item for item in report.get("takes") or () if item.get("shot_id") == SHOTS[2]["id"]]
    return {
        "file": "looks.json",
        "queued_left": report.get("queued"),
        "available": {name: (report.get(name) or {}).get("available") for name in ("embedder", "faces", "identity")},
        "thresholds": report.get("thresholds"),
        "seams": report.get("seams"),
        "chains": report.get("chains"),
        "lumi": [{"take_id": item.get("take_id"), "status": item.get("status"), "identity": item.get("identity"), "cards": item.get("cards")} for item in lumi],
    }


def _engine_summary(entry: dict) -> list[str]:
    return [step.get("verdict") for step in entry["steps"] if step.get("verdict")]


def summarize(scenario: dict) -> dict:
    verdicts = {}
    measured = []
    for entry in scenario["engines"]:
        for step in entry["steps"]:
            if step.get("verdict"):
                verdicts[step["verdict"]] = verdicts.get(step["verdict"], 0) + 1
            if step.get("run_seconds") is not None:
                measured.append(step["run_seconds"])
    return {"engines": len([entry for entry in scenario["engines"] if entry["selected"]]), "verdicts": verdicts, "measured_seconds": round(sum(measured), 1)}


def run_engine(client: ApiClient, pack: Pack, engine: dict, run_id: str, run_dir: Path, media: dict, final: dict, quality: str, target: str, timeout: float, interval: float, clock, sleep, log, base: dict, entry: dict, scenario: dict, companion_steps: int | None = None) -> None:
    doc = build_doc(pack, engine, run_id, media, companion_steps)
    _write_json(run_dir / "projects" / f"{engine['key']}.json", doc)
    project = (unwrap(client.post_json(f"{VP}/projects", {"name": doc["name"], "doc": doc})) or {})["project"]
    project_id = project["id"]
    entry["project"] = {"id": project_id, "name": doc["name"], "doc": f"projects/{engine['key']}.json"}

    def write() -> None:
        _write_json(run_dir / "scenario.json", scenario)

    write()
    done = {}
    for index, shot in enumerate(SHOTS):
        step = {"step": "take", "shot": shot["id"], "profile": shot["profile"], "status": None, "reason": None, "verdict": None}
        entry["steps"].append(step)
        if scenario["stopped"]:
            step.update(status="not_run", reason=scenario["stopped"])
            continue
        reason = not_offered(engine, shot)
        if reason:
            step.update(status="skipped", reason=reason)
            continue
        previous = done.get(SHOTS[index - 1]["id"]) if shot["chain"] else None
        if shot["chain"] and previous is None:
            step.update(status="not_run", reason=f"{SHOTS[index - 1]['id']} has no finished take to chain on")
            continue
        folder = _folder(run_dir, "takes", f"{engine['key']}--{shot['id']}")
        head = {**base, "cell": f"vp:{engine['engine']}:{shot['id']}", "step": f"take {shot['id']}", "engine": engine["engine"], "project_id": project_id, "shot": shot["id"]}
        result = run_take(client, project_id, engine, shot, take_order(engine, shot, quality, run_id), f"{VP}/projects/{project_id}/generate", previous, folder, head, timeout, interval, clock, sleep, log, engine["preset_id"])
        step.update(_step_of(result, folder, run_dir))
        if result.get("take", {}).get("status") == "done":
            done[shot["id"]] = result["take"]
            place_take(client, project_id, result["take"], f"{MARK} {shot['id']}")
        if result["verdict"] in STOP_AFTER:
            scenario["stopped"] = STOP_AFTER[result["verdict"]]
        write()
    first = done.get(SHOTS[0]["id"])
    step = {"step": "final_pass", "shot": SHOTS[0]["id"], "upscaler": final["upscaler"], "status": None, "reason": None, "verdict": None}
    entry["steps"].append(step)
    if scenario["stopped"]:
        step.update(status="not_run", reason=scenario["stopped"])
    elif not final["allowed"]:
        step.update(status="not_run", reason=final["reason"])
    elif first is None:
        step.update(status="not_run", reason=f"{SHOTS[0]['id']} has no finished take")
    else:
        folder = _folder(run_dir, "final", engine["key"])
        head = {**base, "cell": f"vp:{engine['engine']}:final-pass", "step": "final pass", "engine": engine["engine"], "project_id": project_id, "shot": SHOTS[0]["id"], "parent_take_id": first["id"]}
        result = run_take(client, project_id, engine, None, final_order(first["id"], final["upscaler"], target), f"{VP}/projects/{project_id}/final-pass", None, folder, head, timeout, interval, clock, sleep, log, final["preset_id"])
        step.update(_step_of(result, folder, run_dir))
        if result.get("take", {}).get("status") == "done":
            place_take(client, project_id, result["take"], f"{MARK} final pass")
        if result["verdict"] in STOP_AFTER:
            scenario["stopped"] = STOP_AFTER[result["verdict"]]
    write()
    step = {"step": "export", "status": None, "reason": None, "verdict": None}
    entry["steps"].append(step)
    if scenario["stopped"]:
        step.update(status="not_run", reason=scenario["stopped"])
    elif not done:
        step.update(status="not_run", reason="no shot has a finished take")
    else:
        folder = _folder(run_dir, "exports", engine["key"])
        result = run_export(client, project_id, folder, {**base, "cell": f"vp:{engine['engine']}:export", "engine": engine["engine"], "project_id": project_id}, timeout, interval, clock, sleep, log, SHOT_SECONDS * len(SHOTS))
        step.update(status="ran", verdict=result["verdict"], reason=result.get("reason"), result=str((folder / "result.json").relative_to(run_dir)))
    measures = {"seam": None, "looks": None}
    first_result = next((item for item in entry["steps"] if item.get("shot") == SHOTS[0]["id"] and item["step"] == "take"), {})
    second_result = next((item for item in entry["steps"] if item.get("shot") == SHOTS[1]["id"]), {})
    if first_result.get("video") and second_result.get("video"):
        measures["seam"] = frame_gap(run_dir / first_result["video"], run_dir / second_result["video"])
    if done and not scenario["stopped"]:
        try:
            measures["looks"] = read_looks(client, project_id, _folder(run_dir, "projects", engine["key"]), interval, sleep)
        except ApiError as error:
            measures["looks"] = {"error": str(error)}
    entry["measures"] = measures
    write()


def _step_of(result: dict, folder: Path, run_dir: Path) -> dict:
    take = result.get("take") or {}
    stats = result.get("generation_stats") or {}
    chosen = result.get("stats_preset") or {}
    video = _video(result)
    return {
        "status": "ran",
        "verdict": result["verdict"],
        "reason": result.get("reason"),
        "take_id": take.get("id"),
        "generation_id": take.get("generation_id"),
        "director_mode": take.get("director_mode"),
        "preset_id": take.get("preset_id"),
        "stats_preset": {key: chosen.get(key) for key in ("preset_id", "name", "source", "differs")} if chosen else None,
        "run_seconds": (result.get("timing") or {}).get("run_seconds"),
        "seconds_per_step": (result.get("timing") or {}).get("seconds_per_step_polled"),
        "peak_vram_mb": stats.get("peak_vram_mb"),
        "result": str((folder / "result.json").relative_to(run_dir)),
        "video": str(video.relative_to(run_dir)) if video else None,
    }


def run_scenario(client: ApiClient, pack: Pack, out_root: Path, run_id: str, engines: list[dict], matrix: dict | None, *, quality: str = "draft", upscaler: str = "seedvr2", target: str = "fhd1080", companion_steps: int | None = None, timeout: float | None = None, interval: float = 2.0, machine: str | None = None, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> dict:
    final = upscaler_state(pack, matrix, upscaler)
    scenario = _head(client, pack, run_id, False, machine, matrix, quality, final, target, companion_steps)
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    base = {"schema": 1, "run_id": run_id, "kind": "vp-scenario", "pack": scenario["pack"], "cases": scenario["cases"], "app_version": scenario["app_version"], "plugin": scenario["plugin"], "runner": scenario["runner"]}
    limit = timeout or DEFAULT_TIMEOUT
    try:
        media = {}
        if any(engine["selected"] for engine in engines):
            uploads = Uploads(client, run_dir / "uploads.json")
            for input_id in UPLOADED:
                uploads.media(pack, input_id, False)
                stored = uploads.done[pack.inputs[input_id].sha256]
                if not stored.get("id"):
                    raise RunRefused(f"the upload of {pack.inputs[input_id].file} gave no id: start the scenario under a new run id")
                found = (unwrap(client.post_json(f"{VP}/media/uploaded", {"id": stored["id"], "filename": stored["filename"]})) or {}).get("media") or {}
                if not found.get("origin"):
                    raise RunRefused(f"the plugin gave no library origin for {pack.inputs[input_id].file}")
                media[input_id] = (found.get("url"), found["origin"])
        for engine in engines:
            entry = {**engine, "project": None, "steps": [], "measures": None}
            scenario["engines"].append(entry)
            if not engine["selected"]:
                continue
            if scenario["stopped"]:
                entry["reason"] = scenario["stopped"]
                continue
            health = instance_health(client)
            if health not in HEALTHY:
                scenario["stopped"] = f"stopped: the instance is {health}"
                continue
            run_engine(client, pack, engine, run_id, run_dir, media, final, quality, target, limit, interval, clock, sleep, log, base, entry, scenario, companion_steps)
    except KeyboardInterrupt:
        scenario["stopped"] = "stopped with Ctrl+C: the running take was cancelled"
        raise
    finally:
        scenario["ended_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        scenario["summary"] = summarize(scenario)
        _write_json(run_dir / "scenario.json", scenario)
    verdicts = ", ".join(f"{name} {count}" for name, count in sorted(scenario["summary"]["verdicts"].items())) or "none"
    log(f"{scenario['summary']['engines']} engines ({verdicts}), {scenario['summary']['measured_seconds'] / 60:.1f} min measured")
    if scenario["stopped"]:
        log(scenario["stopped"])
    log(f"scenario: {run_dir / 'scenario.json'}")
    return scenario


def scenario_passed(scenario: dict) -> bool:
    return not scenario["stopped"] and all(verdict == "PASS" for entry in scenario["engines"] for verdict in _engine_summary(entry))


UPLOAD_GONE = {400, 404}


def recorded_uploads(run_dir: Path) -> list[str]:
    record = run_dir / "uploads.json"
    if not record.is_file():
        return []
    found = []
    for item in (json.loads(record.read_text(encoding="utf-8")) or {}).values():
        filename = str((item or {}).get("filename") or "")
        if filename and filename not in found and "/" not in filename and "\\" not in filename and not filename.startswith("."):
            found.append(filename)
    return found


def upload_exists(client: ApiClient, filename: str) -> bool:
    try:
        client.get_json(f"/api/media/uploads/{urllib.parse.quote(filename, safe='')}/info")
    except ApiError as error:
        if error.status in UPLOAD_GONE:
            return False
        raise
    return True


def cleanup(client: ApiClient, run_dir: Path, confirm: bool, log: Callable[[str], None] = print) -> dict:
    record = run_dir / "scenario.json"
    if not record.is_file():
        raise RunRefused(f"{run_dir.name} holds no scenario.json")
    scenario = json.loads(record.read_text(encoding="utf-8"))
    run_id = scenario["run_id"]
    projects = {entry["project"]["id"] for entry in scenario.get("engines") or () if entry.get("project") and entry["project"].get("id")}
    listed = (unwrap(client.get_json(f"{VP}/projects")) or {}).get("projects") or []
    projects |= {item["id"] for item in listed if str(item.get("name") or "").startswith(project_prefix(run_id))}
    generations = []
    for entry in scenario.get("engines") or ():
        for step in entry.get("steps") or ():
            if step.get("generation_id") and step["generation_id"] not in generations:
                generations.append(step["generation_id"])
    for project_id in sorted(projects):
        found = client.get_json(f"{VP}/projects/{project_id}/takes", missing_ok=True)
        for take in (unwrap(found) or {}).get("takes") or () if found else ():
            if take.get("generation_id") and take["generation_id"] not in generations:
                generations.append(take["generation_id"])
    plan = {"run_id": run_id, "confirmed": confirm, "projects": [{"id": project_id} for project_id in sorted(projects)], "generations": [{"id": generation_id} for generation_id in generations], "uploads": [{"filename": filename} for filename in recorded_uploads(run_dir)]}
    for item in plan["projects"]:
        log(f"project {item['id']}")
    for item in plan["generations"]:
        log(f"generation {item['id']}")
    for item in plan["uploads"]:
        log(f"upload {item['filename']}")
    if not confirm:
        log(f"{len(plan['projects'])} projects, {len(plan['generations'])} generations and {len(plan['uploads'])} uploads of {run_id}: pass --confirm to delete them")
        return plan
    for item in plan["projects"]:
        answer = client.delete_json(f"{VP}/projects/{item['id']}", missing_ok=True)
        item["deleted"] = answer is not None
    for item in plan["generations"]:
        existed = client.get_json(f"/api/generations/history/{item['id']}", missing_ok=True) is not None
        answer = client.delete_json(f"/api/generations/history/{item['id']}", missing_ok=True) if existed else None
        item.update(existed=existed, message=(answer or {}).get("message") if isinstance(answer, dict) else None, exists_after=client.get_json(f"/api/generations/history/{item['id']}", missing_ok=True) is not None)
    for item in plan["uploads"]:
        existed = upload_exists(client, item["filename"])
        answer = client.delete_json(f"/api/media/uploads/{urllib.parse.quote(item['filename'], safe='')}", missing_ok=True) if existed else None
        item.update(existed=existed, deleted=answer is not None, exists_after=upload_exists(client, item["filename"]))
    _write_json(run_dir / "cleanup.json", plan)
    left = [item["id"] for item in plan["generations"] if item["exists_after"]]
    uploads_left = [item["filename"] for item in plan["uploads"] if item["exists_after"]]
    log(f"{len(plan['projects'])} projects, {len(plan['generations'])} generations and {len(plan['uploads'])} uploads deleted, {len(left)} generations and {len(uploads_left)} uploads still there")
    return plan


def add_vp_parser(commands) -> None:
    vp = commands.add_parser("vp", help="the Video Producer scenario: a project of four shots, a final pass and an export")
    vp_commands = vp.add_subparsers(dest="vp_command", required=True)
    run = vp_commands.add_parser("run", help="plan the scenario with --dry-run, run it with --confirm-gpu")
    run.add_argument("--config", type=Path, default=Path("audit.toml"))
    run.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    run.add_argument("--matrix", type=Path, action="append", help="a run.json or results.json of a matrix, a run folder, or a folder with night.json; repeatable")
    run.add_argument("--engines", help="comma-separated presets of the plugin; with --matrix, only those that passed it")
    run.add_argument("--quality", choices=QUALITIES, default="draft")
    run.add_argument("--upscaler", choices=sorted(UPSCALERS), default="seedvr2")
    run.add_argument("--target", choices=TARGETS, default="fhd1080")
    run.add_argument("--companion-steps", type=int, help="steps of the image-to-video companion an engine hands its image shots to (Wan2.2-14B-Lightning-12GB), set in the engine options of the project")
    run.add_argument("--timeout", type=float, help="seconds before a take is cancelled")
    run.add_argument("--interval", type=float, default=2.0)
    run.add_argument("--run-id", help="name of the run folder (default: <date>-<machine>-vp)")
    run.add_argument("--dry-run", action="store_true", help="build the documents and the list of generations in memory, write nothing on the instance")
    run.add_argument("--confirm-gpu", action="store_true", help="required unless --dry-run: the operator agreed to use the GPU")
    clean = vp_commands.add_parser("cleanup", help="list the projects, generations and uploads of a scenario run, delete them with --confirm")
    clean.add_argument("run_dir", type=Path)
    clean.add_argument("--config", type=Path, default=Path("audit.toml"))
    clean.add_argument("--confirm", action="store_true")


def vp_command(args) -> int:
    if args.vp_command == "run" and args.companion_steps is not None and args.companion_steps < 1:
        print("--companion-steps takes a whole number of steps from 1", file=sys.stderr)
        return EXIT_BLOCKED
    if args.vp_command == "run" and not args.confirm_gpu and not args.dry_run:
        print("vp run uses the GPU of the instance: pass --confirm-gpu once the operator has agreed", file=sys.stderr)
        return EXIT_BLOCKED
    config = load_config(args.config)
    username, password = credentials(config.target, os.environ)
    client = ApiClient(config.target.url, config.target.timeout_seconds)
    if args.vp_command == "cleanup":
        client.login(username, password)
        cleanup(client, args.run_dir, args.confirm)
        return EXIT_OK
    pack = load_pack(args.pack)
    matrix = load_matrix(args.matrix) if args.matrix else None
    names = [name.strip() for name in args.engines.split(",") if name.strip()] if args.engines else None
    engines = select_engines(pack, matrix, names)
    if not any(engine["selected"] for engine in engines):
        for engine in engines:
            print(f"{engine['key']}: {engine['reason']}", file=sys.stderr)
        print("no engine of the plugin is left to run", file=sys.stderr)
        return EXIT_BLOCKED
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{config.machine}-vp"
    client.login(username, password)
    if args.dry_run:
        dry_run(client, pack, config.output_dir, run_id, engines, matrix, quality=args.quality, upscaler=args.upscaler, target=args.target, companion_steps=args.companion_steps, machine=config.machine)
        return EXIT_OK
    try:
        scenario = run_scenario(client, pack, config.output_dir, run_id, engines, matrix, quality=args.quality, upscaler=args.upscaler, target=args.target, companion_steps=args.companion_steps, timeout=args.timeout, interval=args.interval, machine=config.machine)
    except KeyboardInterrupt:
        print("stopped: the running take was cancelled, see scenario.json", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK if scenario_passed(scenario) else EXIT_FAIL
