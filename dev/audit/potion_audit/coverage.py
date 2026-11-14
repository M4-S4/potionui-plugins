from dataclasses import dataclass
from pathlib import PurePosixPath

from .cases import ModelRef
from .check import lookup_model
from .client import ApiClient, ApiError, unwrap
from .pack import Cell, Pack, PackError, cell_models, merged_form, preset_ref

STATUS_ORDER = (
    "ready",
    "input_pending",
    "beyond_tier",
    "model_missing",
    "model_unresolved",
    "preset_not_installed",
    "mode_missing",
    "plugin_inactive",
    "excluded",
)
TIER_MARGIN_GB = 0.25
PASSTHROUGH_KEYS = {"video_director", "music_director", "llm", "prompt_timeline", "timeline"}
MASK_SUFFIX = "_inpaint_mask"
ORIGIN_SUFFIX = "__origin"
FORM_CHECKED = {"ready", "input_pending", "beyond_tier", "model_missing", "model_unresolved"}


class ModelResolver:
    def __init__(self, client: ApiClient):
        self.client = client
        self._by_sha = {}
        self._by_name = {}

    def by_sha(self, sha: str) -> dict | None:
        if sha not in self._by_sha:
            self._by_sha[sha] = lookup_model(self.client, sha)
        return self._by_sha[sha]

    def by_filename(self, preset_id: str, filename: str) -> dict | None:
        key = (preset_id, filename)
        if key not in self._by_name:
            stem = PurePosixPath(filename).stem
            data = unwrap(self.client.get_json(f"/api/presets/{preset_id}/models", {"search": stem, "limit": 50})) or {}
            found = None
            for model in data.get("models") or ():
                if model.get("filename") == filename and model.get("is_available") is not False:
                    found = {
                        "model_id": model.get("id"),
                        "filename": model.get("filename"),
                        "model_type": model.get("model_type"),
                        "size_bytes": model.get("file_size"),
                        "sha256": model.get("sha256"),
                    }
                    break
            self._by_name[key] = found
        return self._by_name[key]

    def resolve(self, ref: ModelRef, preset_id: str) -> dict:
        if ref.resolved:
            for rank, sha in enumerate((ref.sha256, *ref.alternatives)):
                found = self.by_sha(sha)
                if found:
                    return {"field": ref.field, "sha256": sha, "filename": found.get("filename") or ref.filename, "by": "sha256" if rank == 0 else f"sha256, alternative {rank}", "found": found, "present": True}
            return {"field": ref.field, "sha256": ref.sha256, "filename": ref.filename, "by": "sha256", "found": None, "present": False}
        if ref.filename:
            found = self.by_filename(preset_id, ref.filename)
            return {"field": ref.field, "sha256": None, "filename": ref.filename, "by": "filename", "found": found, "present": found is not None}
        return {"field": ref.field, "sha256": None, "filename": None, "by": "none", "found": None, "present": None}


@dataclass(frozen=True)
class Live:
    presets: dict
    enabled_plugins: frozenset
    vram_gb: float | None


def live_state(client: ApiClient) -> Live:
    presets = {preset["id"]: preset for preset in unwrap(client.get_json("/api/presets", {"include_uninstalled": "true"})) or []}
    plugins = unwrap(client.get_json("/api/plugins")) or []
    gpu = client.get_json("/api/system/gpu-profile") or {}
    return Live(
        presets=presets,
        enabled_plugins=frozenset(plugin.get("id") for plugin in plugins if plugin.get("enabled")),
        vram_gb=gpu.get("vram_gb"),
    )


def mode_names(live_preset: dict) -> list[str] | None:
    modes = live_preset.get("modes")
    if not isinstance(modes, list):
        return None
    names = [mode if isinstance(mode, str) else (mode.get("id") or mode.get("name") or "") for mode in modes if isinstance(mode, (str, dict))]
    return [name for name in names if name] or None


def missing_mode_reason(live_preset: dict, mode: str) -> str | None:
    names = mode_names(live_preset)
    if names is None or mode in names:
        return None
    retired = ((live_preset.get("vars") or {}).get("retired_modes") or {}).get(mode)
    replaced = f", which replaced it with {retired!r}" if retired else ""
    return f"the instance offers no mode {mode!r} for this preset{replaced}; its modes: {', '.join(names)}"


def _beyond(live_preset: dict, vram: float | None) -> bool:
    need = (live_preset.get("requires") or {}).get("min_vram_gb")
    return need is not None and vram is not None and float(need) > float(vram) + TIER_MARGIN_GB


def assess(pack: Pack, cell: Cell, resolver: ModelResolver, live: Live) -> dict:
    entry = {
        "id": cell.id,
        "preset": cell.preset_ref,
        "preset_id": cell.preset_id,
        "mode": cell.mode,
        "variant": cell.variant,
        "source": cell.status,
        "case": cell.case,
        "profiles": list(cell.profiles),
        "repeat_warm": cell.repeat_warm,
        "models": [],
        "inputs": sorted({binding.input_id for binding in cell.bind.values()}),
        "reason": None,
    }
    if cell.exclude:
        entry.update(status="excluded", reason=cell.exclude)
        return entry
    if cell.requires_plugin and cell.requires_plugin not in live.enabled_plugins:
        entry.update(status="plugin_inactive", reason=f"plugin {cell.requires_plugin} is not enabled")
        return entry
    live_preset = live.presets.get(cell.preset_id)
    if not live_preset or not live_preset.get("installed"):
        entry.update(status="preset_not_installed", reason="the instance does not have this preset installed")
        return entry
    gone = missing_mode_reason(live_preset, cell.mode)
    if gone:
        entry.update(status="mode_missing", reason=gone)
        return entry
    try:
        refs = cell_models(pack, cell)
    except PackError as error:
        entry.update(status="model_unresolved", reason=str(error))
        return entry
    models = [resolver.resolve(ref, cell.preset_id) for ref in refs]
    entry["models"] = [{key: model[key] for key in ("field", "sha256", "filename", "by", "present")} | {"model_id": (model["found"] or {}).get("model_id")} for model in models]
    pending = [input_id for input_id in entry["inputs"] if pack.inputs[input_id].pending]
    if any(model["present"] is None for model in models):
        entry.update(status="model_unresolved", reason="no sha256 and no file name: " + ", ".join(model["field"] for model in models if model["present"] is None))
    elif any(model["present"] is False for model in models):
        entry.update(status="model_missing", reason="not on the instance: " + ", ".join(f"{model['field']} ({model['filename'] or model['sha256'][:12]})" for model in models if model["present"] is False))
    elif _beyond(live_preset, live.vram_gb):
        entry.update(status="beyond_tier", reason=f"needs {live_preset['requires']['min_vram_gb']} GB, the GPU has {live.vram_gb} GB")
    elif pending:
        entry.update(status="input_pending", reason="inputs not made yet: " + ", ".join(pending))
    else:
        entry["status"] = "ready"
    return entry


def uncovered(pack: Pack, live: Live) -> list[dict]:
    covered = {(cell.preset_id, cell.mode) for cell in pack.cells}
    whole = {cell.preset_id for cell in pack.cells if cell.mode == "*"}
    missing = []
    for preset_id, preset in sorted(live.presets.items()):
        if not preset.get("installed") or preset_id in whole:
            continue
        known = pack.case_set.preset(preset_id)
        modes = preset.get("modes") or (known or {}).get("modes") or ()
        for mode in modes:
            if (preset_id, mode) not in covered:
                cloud = preset.get("engine") == "cloud"
                missing.append({"preset_id": preset_id, "name": preset.get("name"), "mode": mode, "engine": preset.get("engine"), "status": "excluded" if cloud else "no_case", "reason": "cloud preset" if cloud else "no cell in the pack"})
    return missing


class FormReader:
    def __init__(self, client: ApiClient):
        self.client = client
        self._forms = {}

    def fields(self, preset_id: str, mode: str) -> set[str]:
        key = (preset_id, mode)
        if key not in self._forms:
            form = unwrap(self.client.get_json(f"/api/presets/{preset_id}/form", {"mode": mode})) or {}
            self._forms[key] = form_field_names(form.get("form_schema"))
        return self._forms[key]


def form_field_names(node, found: set[str] | None = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(node, dict):
        if isinstance(node.get("name"), str) and node["name"] and "type" in node:
            found.add(node["name"])
        for value in node.values():
            form_field_names(value, found)
    elif isinstance(node, list):
        for value in node:
            form_field_names(value, found)
    return found


def sent_fields(pack: Pack, cell: Cell) -> set[str]:
    form, _, _ = merged_form(pack, cell)
    sent = set(form)
    sent.update(path.split(".")[0].split("[")[0] for path in cell.bind)
    sent.update(ref.field for ref in cell_models(pack, cell))
    return sent


def undeclared(sent: set[str], declared: set[str]) -> list[str]:
    found = []
    for key in sorted(sent):
        if key in declared or key in PASSTHROUGH_KEYS:
            continue
        if key.endswith(MASK_SUFFIX) and key[: -len(MASK_SUFFIX)] in declared:
            continue
        if key.endswith(ORIGIN_SUFFIX) and key[: -len(ORIGIN_SUFFIX)] in declared:
            continue
        found.append(key)
    return found


def check_forms(pack: Pack, entries: list[dict], forms: FormReader) -> None:
    cells = {cell.id: cell for cell in pack.cells}
    for entry in entries:
        if entry["status"] not in FORM_CHECKED:
            continue
        cell = cells[entry["id"]]
        try:
            declared = forms.fields(cell.preset_id, cell.mode)
            entry["undeclared_fields"] = undeclared(sent_fields(pack, cell), declared)
        except (ApiError, ValueError) as error:
            entry["form_error"] = str(error)


def coverage(pack: Pack, resolver: ModelResolver, live: Live, forms: FormReader | None = None) -> dict:
    cells = [assess(pack, cell, resolver, live) for cell in pack.cells]
    if forms is not None:
        check_forms(pack, cells, forms)
    counts = {}
    for cell in cells:
        counts[cell["status"]] = counts.get(cell["status"], 0) + 1
    extra = uncovered(pack, live)
    for cell in extra:
        counts[cell["status"]] = counts.get(cell["status"], 0) + 1
    return {
        "id": pack.id,
        "version": pack.version,
        "file": pack.path.name,
        "sha256": pack.sha256,
        "cases": {"file": pack.case_set.path.name, "sha256": pack.case_set.sha256, **pack.case_set.source},
        "cells": cells,
        "uncovered": extra,
        "summary": counts,
    }


def preset_refs(pack: Pack) -> dict[str, str]:
    return {preset["id"]: preset_ref(preset) for preset in pack.case_set.presets}
