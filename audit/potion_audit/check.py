import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .cases import CaseSet
from .client import ApiClient, ApiError, ApiUnreachable, unwrap
from .config import Config
from .preflight_html import render

PREFLIGHT_SCHEMA = 1
LOW_DISK_PERCENT = 10.0
SETTINGS_KEPT = (
    "profiling_enabled",
    "profiling_census",
    "model_cache_scope",
    "models_dir",
    "output_directory",
    "temp_directory",
    "cache_dir",
)
LOCK_FILE = Path(__file__).resolve().parent.parent / "uv.lock"


def runner_info() -> dict:
    lock_sha = hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest() if LOCK_FILE.exists() else None
    return {
        "potion_audit": __version__,
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "uv_lock_sha256": lock_sha,
    }


def lookup_model(client: ApiClient, sha: str) -> dict | None:
    path = f"/api/models/hash/{sha}"
    payload = client.get_json(path, missing_ok=True)
    if payload is None:
        return None
    if isinstance(payload, dict) and payload.get("success") is False:
        if payload.get("error") == "model_not_found":
            return None
        raise ApiError("GET", path, 200, str(payload.get("message") or payload.get("error")))
    data = unwrap(payload) or {}
    model = data.get("model", data)
    if model.get("is_available") is False:
        return None
    return {
        "model_id": model.get("id"),
        "filename": model.get("filename"),
        "model_type": model.get("model_type"),
        "size_bytes": model.get("file_size"),
    }


def _disk(system_info: dict) -> dict:
    result = {}
    for name, usage in (system_info.get("disk_usage") or {}).items():
        total = usage.get("total") or 0
        free = usage.get("free") or 0
        result[name] = {
            "total": total,
            "used": usage.get("used"),
            "free": free,
            "free_percent": round(100.0 * free / total, 1) if total else None,
        }
    return result


def _tier(min_vram: float | None, vram: float | None) -> str:
    if min_vram is None or vram is None:
        return "unknown"
    return "beyond" if float(min_vram) > float(vram) + 0.25 else "within"


def collect(client: ApiClient, config: Config, case_set: CaseSet, username: str, password: str) -> dict:
    preflight = {
        "schema": PREFLIGHT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": config.machine,
        "target": {"url": config.target.url, "mode": config.target.mode},
        "runner": runner_info(),
        "cases_source": {**case_set.source, "file": case_set.path.name, "sha256": case_set.sha256},
        "blocking": [],
        "warnings": [],
    }
    try:
        client.login(username, password)
    except ApiUnreachable as error:
        preflight["blocking"].append(f"api_unreachable: {error}")
        return preflight
    except ApiError as error:
        preflight["blocking"].append(f"login_failed: HTTP {error.status}")
        return preflight

    me = unwrap(client.get_json("/api/auth/me"))
    preflight["user"] = {"username": me.get("username"), "account_type": me.get("account_type")}
    if str(me.get("account_type", "")).upper() != "ADMIN":
        preflight["blocking"].append("not_admin: the audit account must be an admin")
        return preflight

    openapi = client.get_json("/openapi.json") or {}
    plugins = unwrap(client.get_json("/api/plugins")) or []
    settings = unwrap(client.get_json("/api/settings")) or {}
    preflight["instance"] = {
        "app_version": (openapi.get("info") or {}).get("version"),
        "plugins": [
            {key: plugin.get(key) for key in ("id", "version", "enabled", "state", "source")}
            for plugin in sorted(plugins, key=lambda item: item.get("id") or "")
        ],
        "settings": {key: settings.get(key) for key in SETTINGS_KEPT if key in settings},
    }

    gpu_profile = client.get_json("/api/system/gpu-profile") or {}
    stats = unwrap(client.get_json("/api/system/stats")) or {}
    backends = unwrap(client.get_json("/api/system/backends")) or []
    local = []
    for backend in backends:
        if backend.get("kind") != "local":
            continue
        entry = {key: backend.get(key) for key in ("id", "name", "engine", "status", "hardware", "jobs")}
        entry["system_info"] = unwrap(client.get_json(f"/api/backends/{backend['id']}/system-info"))
        entry["optimizations"] = unwrap(client.get_json(f"/api/backends/{backend['id']}/optimizations"))
        local.append(entry)
    preflight["hardware"] = {
        "gpu_profile": gpu_profile,
        "stats": stats,
        "backends": [{key: backend.get(key) for key in ("id", "name", "engine", "kind", "status")} for backend in backends],
        "local_backends": local,
    }
    vram = gpu_profile.get("vram_gb")

    disk = {}
    for entry in local:
        for name, usage in _disk(entry.get("system_info") or {}).items():
            disk[f"{entry['id']}:{name}"] = usage
            if usage["free_percent"] is not None and usage["free_percent"] < LOW_DISK_PERCENT:
                preflight["warnings"].append(f"low_disk: {entry['id']}:{name} has {usage['free_percent']} % free")
    preflight["disk"] = disk

    queue = unwrap(client.get_json("/api/admin/generations/queue")) or {}
    pending = len(queue.get("pending") or ())
    running = len(queue.get("running") or ())
    preflight["queue"] = {"pending": pending, "running": running}
    if pending or running:
        preflight["blocking"].append(f"queue_busy: {running} running, {pending} pending")

    installed = {preset["id"]: preset for preset in unwrap(client.get_json("/api/presets", {"include_uninstalled": "true"})) or []}
    mine = {preset["id"] for preset in unwrap(client.get_json("/api/presets")) or []}
    presets = []
    for expected in case_set.presets:
        live = installed.get(expected["id"])
        live_requires = (live or {}).get("requires") or {}
        min_vram = live_requires.get("min_vram_gb", expected.get("min_vram_gb")) if live else expected.get("min_vram_gb")
        presets.append(
            {
                "key": expected["key"],
                "id": expected["id"],
                "name": expected["name"],
                "origin": expected["origin"],
                "engine": expected["engine"],
                "category": expected["category"],
                "expected_version": expected["version"],
                "installed": bool(live and live.get("installed")),
                "installed_version": live.get("version") if live else None,
                "version_match": bool(live) and live.get("version") == expected["version"],
                "assignment_count": live.get("assignment_count") if live else None,
                "group_count": live.get("group_count") if live else None,
                "assigned_to_me": expected["id"] in mine,
                "min_vram_gb": min_vram,
                "tier": _tier(min_vram, vram),
                "case_count": expected["case_count"],
                "modes": expected["modes"],
            }
        )
    known = {preset["id"] for preset in case_set.presets}
    preflight["presets"] = presets
    preflight["presets_not_in_cases"] = [
        {key: preset.get(key) for key in ("id", "name", "version", "engine", "origin")}
        for preset_id, preset in sorted(installed.items())
        if preset_id not in known
    ]
    for preset in presets:
        if preset["installed"] and not preset["version_match"]:
            preflight["warnings"].append(
                f"version_mismatch: {preset['key']} is {preset['installed_version']} on the instance, "
                f"{preset['expected_version']} in the cases"
            )

    models = {}
    keys = {}
    for case in case_set.cases:
        for ref in case.models:
            key = ref.sha256 if ref.resolved else f"unresolved:{case.preset_key}:{ref.field}:{ref.filename or ''}"
            keys[(case.preset_key, case.name, ref.field)] = key
            entry = models.setdefault(
                key,
                {
                    "sha256": ref.sha256 if ref.resolved else None,
                    "filename": ref.filename,
                    "expected_size_bytes": ref.size_bytes,
                    "source": ref.source,
                    "fields": set(),
                    "used_by": [],
                    "alternatives": list(ref.alternatives),
                },
            )
            entry["fields"].add(ref.field)
            entry["used_by"].append(f"{case.preset_key}/{case.name}")
            if entry["expected_size_bytes"] is None and ref.size_bytes is not None:
                entry["expected_size_bytes"] = ref.size_bytes
    for entry in models.values():
        entry["fields"] = sorted(entry["fields"])
        entry["found"] = lookup_model(client, entry["sha256"]) if entry["sha256"] else None
        for sha in entry["alternatives"] if entry["found"] is None else ():
            found = lookup_model(client, sha)
            if found:
                entry["found"] = {**found, "alternative_sha256": sha}
                break
        entry["present"] = None if entry["sha256"] is None else entry["found"] is not None
    preflight["models"] = sorted(
        models.values(),
        key=lambda item: ({False: 0, None: 1, True: 2}[item["present"]], item["filename"] or item["sha256"] or ""),
    )

    by_id = {preset["id"]: preset for preset in presets}
    cases = []
    for case in case_set.cases:
        refs = [models[keys[(case.preset_key, case.name, ref.field)]] for ref in case.models]
        missing = [ref for ref in refs if ref["present"] is False]
        preset = by_id.get(case.preset_id, {})
        unresolved = [ref.field for ref in case.models if not ref.resolved]
        if preset.get("engine") == "cloud":
            verdict = "cloud_excluded"
        elif not preset.get("installed"):
            verdict = "preset_not_installed"
        elif unresolved:
            verdict = "model_unresolved"
        elif missing:
            verdict = "model_missing"
        elif preset.get("tier") == "beyond":
            verdict = "beyond_tier"
        else:
            verdict = "ready"
        cases.append(
            {
                "preset_key": case.preset_key,
                "name": case.name,
                "mode": case.mode,
                "kind": case.kind,
                "tags": list(case.tags),
                "models_total": len(refs),
                "models_present": sum(1 for ref in refs if ref["present"] is True),
                "missing_bytes": sum(ref["expected_size_bytes"] or 0 for ref in missing),
                "missing_unknown_size": sum(1 for ref in missing if ref["expected_size_bytes"] is None),
                "unresolved_fields": unresolved,
                "verdict": verdict,
            }
        )
    preflight["cases"] = cases
    missing_models = [model for model in preflight["models"] if model["present"] is False]
    unresolved_models = [model for model in preflight["models"] if model["present"] is None]
    verdicts = {}
    for case in cases:
        verdicts[case["verdict"]] = verdicts.get(case["verdict"], 0) + 1
    preflight["summary"] = {
        "presets": len(presets),
        "presets_without_cases": sum(1 for preset in presets if preset["case_count"] == 0),
        "cases": len(cases),
        "cases_ready": verdicts.get("ready", 0),
        "verdicts": verdicts,
        "models": len(preflight["models"]),
        "models_present": sum(1 for model in preflight["models"] if model["present"] is True),
        "models_missing": len(missing_models),
        "missing_bytes": sum(model["expected_size_bytes"] or 0 for model in missing_models),
        "missing_unknown_size": sum(1 for model in missing_models if model["expected_size_bytes"] is None),
        "models_unresolved": len(unresolved_models),
        "unresolved_known_bytes": sum(model["expected_size_bytes"] or 0 for model in unresolved_models),
    }
    return preflight


def write_preflight(preflight: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "preflight.json"
    html_path = out_dir / "preflight.html"
    json_path.write_text(json.dumps(preflight, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    html_path.write_text(render(preflight), encoding="utf-8", newline="\n")
    return json_path, html_path
