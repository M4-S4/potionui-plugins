import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from src.plugin_api import (
    AccountType,
    HookContext,
    LimitEvents,
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
from src.plugin_api import hooks as api_hooks
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
    "HookContext",
    "LimitEvents",
    "NATIVE_DRIVERS",
    "NotificationTypeSpec",
    "PresetState",
    "SetupCheck",
    "SetupCheckContext",
    "SetupCheckResult",
    "User",
    "enabled_backends",
    "enabled_cloud_video_models",
    "find_ffmpeg",
    "generate_ulid",
    "get_current_active_user",
    "get_plugin_setting",
    "limit_status",
    "list_presets",
    "model_file_present",
    "notify",
    "preset_model_hashes",
    "preset_state",
    "register_notification_types",
    "run_on_app_loop",
    "set_plugin_setting",
]

logger = logging.getLogger("plugins.video-producer")

NATIVE_DRIVERS = ("native.local", "native.remote")

_FILE_UNAVAILABLE = "ModelFileUnavailable"


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


def set_plugin_setting(key: str, value: str, user_id: Optional[str] = None) -> None:
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


def preset_model_hashes(preset_id: str, field_names: Sequence[str]) -> Dict[str, Set[str]]:
    """SHA-256 of the files a preset recommends for each named model field. Temporary: reads the container."""
    hashes: Dict[str, Set[str]] = {name: set() for name in field_names}
    template = api_hooks.get_container().file_preset_repository.find_preset_by_id(preset_id)
    if template is None:
        return hashes
    for mode in (template.modes or {}).values():
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


def model_file_present(sha256: str) -> bool:
    """True when the catalog holds a model with this SHA-256 and its file is reachable."""
    model = api_models.model_for_sha256(sha256)
    if not model or not model.get("id"):
        return False
    try:
        api_models.resolve_model_file(model["id"])
    except Exception as exc:
        if type(exc).__name__ != _FILE_UNAVAILABLE:
            raise
        return False
    return True
