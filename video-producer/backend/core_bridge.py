import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

import yaml

from src.plugin_api import (
    AccountType,
    DirectorBindingError,
    GenerationNotFoundException,
    HookContext,
    IdempotencyKeyConflict,
    LimitEvents,
    MediaRefError,
    NotificationTypeSpec,
    PluginRepository,
    SetupCheck,
    SetupCheckContext,
    SetupCheckResult,
    User,
    generate_ulid,
    get_current_active_user,
)
from src.plugin_api import backends as api_backends
from src.plugin_api import cloud as api_cloud
from src.plugin_api import generation as api_generation
from src.plugin_api import hooks as api_hooks
from src.plugin_api import identity as api_identity
from src.plugin_api import limits as api_limits
from src.plugin_api import media as api_media
from src.plugin_api import models as api_models
from src.plugin_api import notifications as api_notifications
from src.plugin_api import presets as api_presets
from src.plugin_api.cloud import CLOUD_ENGINE

from . import PLUGIN_ID

__all__ = [
    "AccountType",
    "CLOUD_ENGINE",
    "DirectorBindingError",
    "GenerationNotFoundException",
    "HookContext",
    "IdempotencyKeyConflict",
    "LimitEvents",
    "MediaRefError",
    "NATIVE_DRIVERS",
    "NotificationTypeSpec",
    "PresetState",
    "SetupCheck",
    "SetupCheckContext",
    "SetupCheckResult",
    "User",
    "bind_director_media",
    "cancel_generation",
    "cloud_model",
    "cloud_video_models",
    "describe_preset",
    "enabled_backends",
    "enabled_cloud_video_models",
    "estimate_cloud_cost",
    "find_ffmpeg",
    "generate_ulid",
    "generation_state",
    "get_current_active_user",
    "get_plugin_setting",
    "get_user",
    "installed_model_for_file",
    "installed_model_id",
    "limit_status",
    "list_generation_files",
    "list_presets",
    "model_file_present",
    "notify",
    "preset_driver",
    "preset_form_fields",
    "preset_model_hashes",
    "preset_state",
    "preview_memory",
    "record_limit_event",
    "refund_limit_event",
    "register_notification_types",
    "resolve_media",
    "run_on_app_loop",
    "set_plugin_setting",
    "submit_generation",
]

logger = logging.getLogger("plugins.video-producer")

NATIVE_DRIVERS = ("native.local", "native.remote")

_FILE_UNAVAILABLE = "ModelFileUnavailable"

_PATH_VARIABLE = re.compile(r"\{\{\s*paths\.(preset|_shared)\s*\}\}")

_STORED_STATE_KEYS = ("backend_id", "started_at", "duration_ms", "error_code", "error_user_message", "error_message", "error_detail")


@dataclass(frozen=True)
class PresetState:
    id: str
    name: str
    loaded: bool
    installed: bool
    assigned: bool


def get_plugin_setting(key: str, user_id: Optional[str] = None) -> Optional[str]:
    """The stored value of a plugin setting (global, or the user's own), or None."""
    row = PluginRepository().get_plugin_setting(PLUGIN_ID, key, user_id=user_id)
    return None if row is None else row.setting_value


def set_plugin_setting(key: str, value: Optional[str], user_id: Optional[str] = None) -> None:
    """Store a plugin setting, global or for one user."""
    PluginRepository().set_plugin_setting(PLUGIN_ID, key, value, user_id=user_id)


def _utc_iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.astimezone(timezone.utc).isoformat() if moment is not None else None


def limit_status(user_id: str, kind: str) -> Dict[str, Any]:
    """Where the user stands against a limit kind; unlimited when it cannot be read."""
    try:
        status = api_limits.limit_status(user_id, kind)
    except Exception:
        logger.warning(
            "[VIDEO-PRODUCER] Could not read the %s limit of user %s; treating it as unlimited", kind, user_id, exc_info=True
        )
        return {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}
    return {
        "limit": status.limit,
        "used": status.used,
        "remaining": status.remaining,
        "exempt": status.exempt,
        "resets_at": _utc_iso(status.resets_at),
    }


def notify(
    *,
    user_id: str,
    notification_type: str,
    title: str,
    message: str = "",
    level: str = "info",
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    """Send one plugin notification to a user; never raises."""
    if not user_id:
        logger.warning("[VIDEO-PRODUCER] Not sending %r: no user to notify", notification_type)
        return
    try:
        api_notifications.notify(
            source=PLUGIN_ID,
            title=title,
            message=message,
            user_id=user_id,
            type=notification_type,
            level=level,
            category="plugin",
            metadata=dict(metadata) if metadata else None,
        )
    except Exception:
        logger.warning(
            "[VIDEO-PRODUCER] Could not send the %r notification to %s", notification_type, user_id, exc_info=True
        )


def register_notification_types(registry: Any, specs: Iterable[NotificationTypeSpec]) -> List[str]:
    """Declare the plugin's notification types on the core registry; returns the keys added."""
    return api_notifications.register_notification_types(registry, list(specs))


def run_on_app_loop(coro: Any) -> Any:
    """Schedule a coroutine on the application's event loop."""
    return api_hooks.run_on_app_loop(coro)


def resolve_media(user: User, ref: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve a history or library media reference the user may read; raises MediaRefError."""
    return dict(api_generation.resolve_media_ref(user, dict(ref)))


def find_ffmpeg() -> Optional[str]:
    """The ffmpeg executable the host would use, or None."""
    return api_media.find_ffmpeg()


def enabled_backends() -> List[Dict[str, Any]]:
    """Every enabled backend as list_backends describes it, highest priority first."""
    return api_backends.list_backends()


def list_presets(user: User) -> List[api_presets.PresetDescription]:
    """The installed presets the user may run, each described like describe_preset."""
    return api_presets.list_presets(user)


def enabled_cloud_video_models(backend_id: str) -> int:
    """How many video models are turned on in a cloud backend's catalog. Temporary: reads the container."""
    repository = api_hooks.get_container().cloud_catalog.repository
    return sum(1 for entry in repository.list_enabled(backend_id) if "video" in (entry.outputs or []))


def preset_state(preset_id: str) -> PresetState:
    """Whether a preset is loaded, installed and assigned to anyone. Temporary: reads the container for install state."""
    description = api_presets.describe_preset(preset_id)
    if description is None:
        return PresetState(id=preset_id, name=preset_id, loaded=False, installed=False, assigned=False)
    collaborators = api_hooks.get_container().preset_collaborators
    installed = bool(collaborators.db_repo.is_preset_installed(preset_id))
    assigned = False
    if installed:
        summary = collaborators.db_repo.get_preset_assignment_summary(preset_id) or {}
        groups = collaborators.group_repo.get_group_count_for_preset(preset_id) or 0
        assigned = int(summary.get("total_assignments") or 0) + int(groups) > 0
    return PresetState(id=preset_id, name=description.name, loaded=True, installed=installed, assigned=assigned)


def preset_model_hashes(
    preset_id: str, field_names: Sequence[str], modes: Optional[Sequence[str]] = None
) -> Dict[str, Set[str]]:
    """SHA-256 of the files a preset recommends for each named model field, in every mode or only in the named ones. Temporary: reads the container."""
    hashes: Dict[str, Set[str]] = {name: set() for name in field_names}
    template = api_hooks.get_container().file_preset_repository.find_preset_by_id(preset_id)
    if template is None:
        return hashes
    for name, mode in (template.modes or {}).items():
        if modes is not None and name not in modes:
            continue
        for form in mode.forms or []:
            _collect_hashes(form.fields, hashes)
    return hashes


def _collect_hashes(fields: Any, hashes: Dict[str, Set[str]]) -> None:
    for form_field in fields or []:
        if form_field.name in hashes and form_field.type == "model":
            for item in (form_field.configuration or {}).get("recommendations") or []:
                sha256 = str(item.get("sha256") or "").strip().lower() if isinstance(item, Mapping) else ""
                if sha256:
                    hashes[form_field.name].add(sha256)
        if isinstance(form_field.children, list):
            _collect_hashes(form_field.children, hashes)


def _reachable(model: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not model or not model.get("id"):
        return None
    try:
        api_models.resolve_model_file(model["id"])
    except Exception as exc:
        if type(exc).__name__ != _FILE_UNAVAILABLE:
            raise
        return None
    return str(model["id"])


def installed_model_id(sha256: str) -> Optional[str]:
    """The id of the catalog model with this SHA-256 when its file is reachable, else None."""
    return _reachable(api_models.model_for_sha256(sha256))


def installed_model_for_file(filename: str) -> Optional[str]:
    """The id of the one catalog model with this file name when its file is reachable, else None."""
    return _reachable(api_models.model_for_path(filename))


def model_file_present(sha256: str) -> bool:
    """True when the catalog holds a model with this SHA-256 and its file is reachable."""
    return installed_model_id(sha256) is not None


def get_user(user_id: str) -> Optional[User]:
    """The user with this id, or None when there is none."""
    return api_identity.get_user(user_id)


def describe_preset(preset_id: str) -> Optional[api_presets.PresetDescription]:
    """One preset's modes, fields, engine and vars, or None when it is not loaded."""
    return api_presets.describe_preset(preset_id)


def bind_director_media(
    request: Mapping[str, Any], role: str, media: Mapping[str, Any], promote: bool = False
) -> Dict[str, Any]:
    """Bind a resolved image as the first or last frame of a request's Video Director document."""
    return api_presets.bind_director_media(dict(request), role, dict(media), promote=promote)


async def submit_generation(user: User, request: Mapping[str, Any]) -> Dict[str, Any]:
    """Start a generation as the user; returns its id, status and queue position."""
    return dict(await api_generation.submit_generation(user, dict(request)))


async def preview_memory(user: User, request: Mapping[str, Any]) -> Dict[str, Any]:
    """The memory estimate, device, budget and backend a request would get, without starting it."""
    return dict(await api_generation.preview_memory(user, dict(request)))


async def cancel_generation(user: User, generation_id: str) -> bool:
    """Cancel one generation of the user; True when something was cancelled."""
    return bool(await api_generation.cancel_generation(user, generation_id))


def generation_state(user: User, generation_id: str) -> Dict[str, Any]:
    """The status of a generation the user may read, with its backend, start, duration and failure details. Temporary: reads the container for the stored row."""
    payload = dict(api_generation.generation_state(user, generation_id))
    missing = [key for key in _STORED_STATE_KEYS if key not in payload]
    if not missing:
        return payload
    try:
        row = api_hooks.get_container().generation_repository.get_by_id(generation_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the stored row of generation %s", generation_id, exc_info=True)
        row = None
    stored = {**row.to_dict(), "error_detail": getattr(row, "error_detail", None)} if row is not None else {}
    for key in missing:
        payload[key] = stored.get(key)
    return payload


def list_generation_files(user: User, generation_id: str) -> List[Dict[str, Any]]:
    """The final files of a generation the user may read, in canonical order."""
    return [dict(item) for item in api_generation.list_generation_files(user, generation_id)]


def record_limit_event(user_id: str, kind: str, units: float, ref_id: str) -> bool:
    """Record usage against a limit kind; False, logged, when the core cannot record it."""
    try:
        LimitEvents.record(user_id, kind, units=units, ref_id=ref_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not record %s units of %s under %s", units, kind, ref_id, exc_info=True)
        return False
    return True


def refund_limit_event(ref_id: str) -> int:
    """Refund the usage recorded under a reference; 0, logged, when the core cannot refund it."""
    try:
        return int(LimitEvents.refund(ref_id) or 0)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not refund the usage recorded under %s", ref_id, exc_info=True)
        return 0


def estimate_cloud_cost(user: User, model_id: str, shots: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """What a run of shots on a cloud model would cost; PermissionError for anyone but an administrator."""
    return dict(api_cloud.estimate_cloud_cost(user, model_id, list(shots)))


def _cloud_summary(model_id: str, entry: Any) -> Dict[str, Any]:
    spec = entry.spec
    return {
        "id": model_id,
        "name": entry.label,
        "provider_model_id": entry.provider_model_id,
        "tasks": sorted(entry.tasks or []),
        "typical_seconds": spec.typical_seconds,
        "max_seconds": spec.max_seconds,
    }


def cloud_video_models(backend_id: str) -> List[Dict[str, Any]]:
    """The video models turned on in a cloud backend's catalog. Temporary: reads the container."""
    repository = api_hooks.get_container().cloud_catalog.repository
    return [
        _cloud_summary(entry.model_id, entry)
        for entry in repository.list_enabled(backend_id)
        if "video" in (entry.outputs or []) and entry.model_id
    ]


def cloud_model(model_id: str) -> Optional[Dict[str, Any]]:
    """An enabled cloud video model with its parameters and media inputs, or None. Temporary: reads the container."""
    resolved = api_hooks.get_container().cloud_capabilities.resolve(model_id)
    if resolved is None or "video" not in (resolved.entry.outputs or []):
        return None
    spec = resolved.spec
    return {
        **_cloud_summary(model_id, resolved.entry),
        "backend_id": resolved.backend_id,
        "params": [
            {
                "name": param.name,
                "kind": param.kind,
                "values": list(param.values),
                "minimum": param.minimum,
                "maximum": param.maximum,
                "step": param.step,
                "default": param.default,
                "tasks": sorted(param.tasks),
            }
            for param in spec.params
        ],
        "inputs": [{"role": media.role, "tasks": sorted(media.tasks)} for media in spec.inputs],
    }


def _option(item: Any) -> Optional[Dict[str, str]]:
    if isinstance(item, Mapping):
        if item.get("value") is None:
            return None
        value = str(item["value"])
        return {"value": value, "label": str(item.get("label") or item.get("description") or value)}
    if item is None:
        return None
    return {"value": str(item), "label": str(item)}


def _option_file(path: str, roots: Mapping[str, str]) -> List[Any]:
    resolved = Path(_PATH_VARIABLE.sub(lambda match: roots[match.group(1)], path))
    try:
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        logger.warning("[VIDEO-PRODUCER] Could not read the option file %s", resolved, exc_info=True)
        return []
    if isinstance(data, Mapping):
        data = data.get("options")
    return list(data) if isinstance(data, list) else []


def _options(configuration: Mapping[str, Any], roots: Mapping[str, str]) -> List[Dict[str, str]]:
    items = list(configuration.get("options") or [])
    single = configuration.get("file")
    if isinstance(single, Mapping) and single.get("path"):
        items.extend(_option_file(str(single["path"]), roots))
    for entry in configuration.get("files") or []:
        if isinstance(entry, Mapping) and entry.get("path"):
            items.extend(_option_file(str(entry["path"]), roots))
    options: List[Dict[str, str]] = []
    for option in (_option(item) for item in items):
        if option is not None and all(seen["value"] != option["value"] for seen in options):
            options.append(option)
    return options


def _file_name(item: Mapping[str, Any]) -> Optional[str]:
    link = str(item.get("link") or "").split("?", 1)[0].rstrip("/")
    name = link.rsplit("/", 1)[-1] if link else str(item.get("name") or "")
    return name if "." in name and " " not in name else None


def _recommendations(configuration: Mapping[str, Any]) -> List[Dict[str, Optional[str]]]:
    found: List[Dict[str, Optional[str]]] = []
    for item in configuration.get("recommendations") or []:
        if not isinstance(item, Mapping):
            continue
        sha256 = str(item.get("sha256") or "").strip().lower() or None
        recommendation = {"sha256": sha256, "filename": _file_name(item)}
        if (sha256 or recommendation["filename"]) and recommendation not in found:
            found.append(recommendation)
    return found


def _describe_fields(fields: Any, roots: Mapping[str, str], out: Dict[str, Dict[str, Any]]) -> None:
    for form_field in fields or []:
        if form_field.name and form_field.name not in out:
            configuration = form_field.configuration or {}
            out[form_field.name] = {
                "type": form_field.type,
                "required": bool(form_field.required),
                "default": form_field.default,
                "options": _options(configuration, roots),
                "recommendations": _recommendations(configuration),
            }
        if isinstance(form_field.children, list):
            _describe_fields(form_field.children, roots, out)


def preset_driver(preset_id: str) -> Optional[str]:
    """The backend driver a preset declares, such as cloud.openrouter, or None. Temporary: reads the container."""
    template = api_hooks.get_container().file_preset_repository.find_preset_by_id(preset_id)
    driver = getattr(template, "driver", None) if template is not None else None
    return str(driver) if driver else None


def preset_form_fields(preset_id: str, mode: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Type, required flag, default, options and recommended files (SHA-256, file name) of each field of a preset mode, or None. Temporary: reads the container."""
    repository = api_hooks.get_container().file_preset_repository
    template = repository.find_preset_by_id(preset_id)
    if template is None or mode not in (template.modes or {}):
        return None
    roots = {"preset": str(template.path), "_shared": str(repository.preset_loader.shared_path)}
    forms = sorted(template.modes[mode].forms or [], key=lambda form: (not form.default, form.order, form.name))
    fields: Dict[str, Dict[str, Any]] = {}
    for form in forms:
        _describe_fields(form.fields, roots, fields)
    return fields
