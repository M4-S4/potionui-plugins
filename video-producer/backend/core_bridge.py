import logging
import re
import shutil
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
from src.plugin_api.limits import LimitExceeded
from src.plugin_api.media import FfmpegUnavailableError, TranscodeSpec, VideoProbe, VideoTranscodeError
from src.plugin_api.storage import SettingRepository, Settings

from . import PLUGIN_ID

__all__ = [
    "AccountType",
    "CLOUD_ENGINE",
    "DirectorBindingError",
    "FfmpegUnavailableError",
    "GenerationNotFoundException",
    "HookContext",
    "IdempotencyKeyConflict",
    "LimitEvents",
    "LimitExceeded",
    "MediaRefError",
    "NATIVE_DRIVERS",
    "NotificationTypeSpec",
    "PresetState",
    "SOURCE_PREFIX",
    "SetupCheck",
    "SetupCheckContext",
    "SetupCheckResult",
    "TranscodeSpec",
    "User",
    "VideoProbe",
    "VideoTranscodeError",
    "bind_director_media",
    "cancel_generation",
    "cloud_edit_models",
    "cloud_model",
    "cloud_video_models",
    "describe_preset",
    "enabled_backends",
    "enabled_cloud_video_models",
    "estimate_cloud_cost",
    "extract_frame",
    "find_ffmpeg",
    "find_ffprobe",
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
    "local_media_file",
    "media_file_path",
    "model_file_present",
    "notify",
    "preset_driver",
    "preset_form_fields",
    "preset_model_hashes",
    "preset_state",
    "preview_memory",
    "probe_video",
    "record_limit_event",
    "refund_limit_event",
    "register_notification_types",
    "resolve_media",
    "run_on_app_loop",
    "save_user_media",
    "set_plugin_setting",
    "storage_directory",
    "submit_generation",
    "transcode_video",
    "upload_item",
]

logger = logging.getLogger("plugins.video-producer")

NATIVE_DRIVERS = ("native.local", "native.remote")

SOURCE_PREFIX = "source-"

_COPY_CHUNK = 1 << 20

_FILE_UNAVAILABLE = "ModelFileUnavailable"

_PATH_VARIABLE = re.compile(r"\{\{\s*paths\.(preset|_shared)\s*\}\}")

EDIT_TASK = "img_edit"

REFERENCE_ROLE = "reference"

_STORED_STATE_KEYS = ("backend_id", "started_at", "duration_ms", "error_code", "error_user_message", "error_message", "error_detail")

GATE_FIELD = "gate"

REGISTRY_FIELDS = ("sampler", "schedule")

FIELD_LIMITS = ("min", "max", "step", "strength_min", "strength_max", "strength_step", "strength_default", "max_items", "max_length")

REACTION_ACTIONS = ("set_value", "set_visibility", "set_disabled")


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


def find_ffprobe() -> Optional[str]:
    """The ffprobe executable next to ffmpeg or on the PATH, or None."""
    ffmpeg = find_ffmpeg()
    sibling = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix) if ffmpeg else None
    if sibling is not None and sibling.is_file():
        return str(sibling)
    return shutil.which("ffprobe")


def probe_video(path: Path) -> Optional[VideoProbe]:
    """What ffprobe reads of a video file, or None."""
    return api_media.probe_video(Path(path))


def transcode_video(src: Path, dest: Path, spec: TranscodeSpec) -> Any:
    """Re-encode a video with the host's converter; raises VideoTranscodeError."""
    return api_media.transcode_video(Path(src), Path(dest), spec)


async def extract_frame(user: User, ref: Mapping[str, Any], at: Any = "last") -> Dict[str, Any]:
    """Store one frame of a video the user may read as their PNG upload; raises MediaRefError."""
    return dict(await api_media.extract_frame(user, dict(ref), at=at))


async def save_user_media(user: User, path: Path) -> Dict[str, Any]:
    """Store a file the plugin wrote as the user's upload; raises MediaRefError."""
    return dict(await api_media.save_user_media(user, Path(path)))


def storage_directory() -> Path:
    """The application's file storage directory, absolute."""
    return Path(Settings(SettingRepository()).get_file_storage_directory()).resolve()


def _media_driver(kind: str) -> Any:
    container = api_hooks.get_container()
    return container.file_service.storage_driver if kind == "history" else container.media_store.storage_driver


def media_file_path(kind: str, value: str) -> Optional[str]:
    """The absolute path on this server of a history or library media key, or None on object storage. Temporary: reads the container."""
    path = _media_driver(kind).local_path(value)
    return None if path is None else str(Path(path).resolve())


def local_media_file(kind: str, value: str, folder: Path) -> Optional[Path]:
    """A local file holding a history or library media key, streamed into the folder as source-<key> on object storage; None when missing. Temporary: reads the container."""
    driver = _media_driver(kind)
    path = driver.local_path(value)
    if path is not None:
        return Path(path) if Path(path).is_file() else None
    if not driver.exists(value):
        return None
    target = Path(folder) / f"{SOURCE_PREFIX}{value.replace('/', '_')}"
    try:
        with target.open("wb") as handle:
            for chunk in driver.get_stream(value, _COPY_CHUNK):
                handle.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def upload_item(user_id: str, value: str) -> Optional[Dict[str, Any]]:
    """The library item an uploads/ key of the user is: its id, file name and size, or None. Temporary: reads the container."""
    filename = value.replace("\\", "/").rsplit("/", 1)[-1]
    upload = api_hooks.get_container().media_store.upload_repo.get_by_filename(filename, user_id)
    if upload is None:
        return None
    return {
        "item_id": upload.id,
        "filename": upload.original_filename or filename,
        "width": upload.width,
        "height": upload.height,
    }


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
    request: Mapping[str, Any],
    role: str,
    media: Mapping[str, Any],
    promote: bool = False,
    segment_id: Optional[str] = None,
    capabilities: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Bind a resolved image as the first or last frame of a request's Video Director document, on segment_id in a director document, against capabilities when given."""
    return api_presets.bind_director_media(
        dict(request), role, dict(media), segment_id=segment_id, promote=promote, capabilities=capabilities
    )


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
        "inputs": [{"role": media.role, "tasks": sorted(media.tasks)} for media in spec.inputs or ()],
    }


def cloud_video_models(backend_id: str) -> List[Dict[str, Any]]:
    """The video models turned on in a cloud backend's catalog. Temporary: reads the container."""
    repository = api_hooks.get_container().cloud_catalog.repository
    return [
        _cloud_summary(entry.model_id, entry)
        for entry in repository.list_enabled(backend_id)
        if "video" in (entry.outputs or []) and entry.model_id
    ]


def _params(spec: Any) -> List[Dict[str, Any]]:
    return [
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
        "params": _params(spec),
    }


def _reference_limit(spec: Any) -> int:
    limits = [
        int(getattr(media, "max_items", 0) or 0)
        for media in spec.inputs
        if media.role == REFERENCE_ROLE and (not media.tasks or EDIT_TASK in media.tasks)
    ]
    return max(limits, default=0)


def cloud_edit_models(backend_id: str) -> List[Dict[str, Any]]:
    """The models turned on in a cloud backend's catalog that edit a picture from reference pictures, with their parameters and the most references they take. Temporary: reads the container."""
    repository = api_hooks.get_container().cloud_catalog.repository
    return [
        {
            "id": entry.model_id,
            "name": entry.label,
            "provider_model_id": entry.provider_model_id,
            "params": _params(entry.spec),
            "max_images": _reference_limit(entry.spec),
        }
        for entry in repository.list_enabled(backend_id)
        if entry.model_id and EDIT_TASK in (entry.tasks or [])
    ]


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


@dataclass(frozen=True)
class _Scope:
    group: Sequence[str] = ()
    advanced: bool = False
    hidden: bool = False
    gate: Optional[str] = None


def _registry_options(kind: str, configuration: Mapping[str, Any]) -> List[Dict[str, str]]:
    try:
        from src.plugin_api import sampling as api_sampling

        registry = api_sampling.sampler_registry if kind == "sampler" else api_sampling.schedule_registry
        found = registry.select(
            family=configuration.get("family") or None,
            include=configuration.get("include") or None,
            exclude=configuration.get("exclude") or None,
        )
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the %s options", kind, exc_info=True)
        return []
    return [{"value": str(entry.key), "label": str(entry.label or entry.key)} for entry in found]


def _number_or_none(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _limits(configuration: Mapping[str, Any]) -> Dict[str, Any]:
    limits = {key: _number_or_none(configuration.get(key)) for key in FIELD_LIMITS}
    found: Dict[str, Any] = {key: value for key, value in limits.items() if value is not None}
    if isinstance(configuration.get("model_type"), str):
        found["model_type"] = configuration["model_type"]
    return found


def _reactions(reactions: Any) -> List[Dict[str, Any]]:
    found = []
    for reaction in reactions or []:
        reaction = _plain(reaction)
        when, then = (reaction.get("when"), reaction.get("then")) if isinstance(reaction, Mapping) else (None, None)
        if isinstance(then, Mapping) and when is not None:
            kept = {key: then[key] for key in REACTION_ACTIONS if key in then and then[key] is not None}
            if kept:
                found.append({"when": _plain(when), "then": _plain(kept)})
    return found


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def _describe_fields(fields: Any, roots: Mapping[str, str], out: Dict[str, Dict[str, Any]], scope: _Scope = _Scope()) -> None:
    for form_field in fields or []:
        configuration = getattr(form_field, "configuration", None) or {}
        label = getattr(form_field, "label", None)
        inner = _Scope(
            group=scope.group,
            advanced=scope.advanced or getattr(form_field, "audience", None) == "advanced",
            hidden=scope.hidden
            or getattr(form_field, "visible", None) is False
            or getattr(form_field, "hidden_when_video_director", False) is True,
            gate=scope.gate,
        )
        if form_field.name and form_field.name not in out:
            kind = form_field.type
            options = _registry_options(kind, configuration) if kind in REGISTRY_FIELDS else _options(configuration, roots)
            out[form_field.name] = {
                "type": kind,
                "required": bool(form_field.required),
                "default": form_field.default,
                "options": options,
                "recommendations": _recommendations(configuration),
                "label": str(label) if label else None,
                "group": list(scope.group),
                "audience": "advanced" if inner.advanced else "simple",
                "hidden": inner.hidden,
                "gate": scope.gate,
                "limits": _limits(configuration),
                "reactions": _reactions(getattr(form_field, "reactions", None)),
                "bound": bool(getattr(form_field, "capability", None)),
                **({"multi": True, "max_items": configuration.get("max_items")} if configuration.get("multi") else {}),
            }
        if isinstance(form_field.children, list):
            if form_field.name and form_field.type == GATE_FIELD:
                child = _Scope(group=inner.group, advanced=inner.advanced, hidden=inner.hidden, gate=form_field.name)
            elif not form_field.name and label:
                child = _Scope(group=[*inner.group, str(label)], advanced=inner.advanced, hidden=inner.hidden, gate=inner.gate)
            else:
                child = inner
            _describe_fields(form_field.children, roots, out, child)


def preset_driver(preset_id: str) -> Optional[str]:
    """The backend driver a preset declares, such as cloud.openrouter, or None. Temporary: reads the container."""
    template = api_hooks.get_container().file_preset_repository.find_preset_by_id(preset_id)
    driver = getattr(template, "driver", None) if template is not None else None
    return str(driver) if driver else None


def preset_form_fields(preset_id: str, mode: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Type, required flag, default, options and recommended files (SHA-256, file name) of each field of a preset mode, with its label, the labels of the tabs and sections around it, its audience, whether the form hides it, the gate it sits in, its limits, its reactions and the most items a multiple field takes; or None. Temporary: reads the container."""
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
