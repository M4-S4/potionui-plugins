import logging
from typing import Any, Dict, List, Optional

from . import core_bridge, presets
from .core_bridge import CLOUD_ENGINE, User

logger = logging.getLogger("plugins.video-producer")

VIDEO_DIRECTOR = "video_director"

NATIVE_KINDS = {"native.local": "local", "native.remote": "remote"}

ENGINE_KEYS = (
    "id",
    "name",
    "engine",
    "driver",
    "execution_device",
    "max_concurrent_runs",
    "vram_total_gb",
    "vram_free_gb",
    "is_default",
)


def engine_kind(backend: Dict[str, Any]) -> Optional[str]:
    """The kind of a backend takes can run on ("local", "remote" or "cloud"); None otherwise, ComfyUI included."""
    if backend.get("engine") == CLOUD_ENGINE:
        return "cloud"
    return NATIVE_KINDS.get(backend.get("driver") or "")


def video_engines() -> List[Dict[str, Any]]:
    """The enabled native and cloud backends, highest priority first; empty when they cannot be read."""
    try:
        backends = core_bridge.enabled_backends()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the backends; reporting none", exc_info=True)
        return []
    engines = []
    for backend in backends:
        kind = engine_kind(backend)
        if kind is not None:
            engines.append({**{key: backend.get(key) for key in ENGINE_KEYS}, "kind": kind})
    return engines


def is_video_preset(description: Any) -> bool:
    """True for a preset the Video Director drives."""
    return VIDEO_DIRECTOR in (description.vars or {})


def _fields(mode: Any) -> Dict[str, Any]:
    forms = mode.forms or {}
    fields = forms.get(mode.default_form)
    if fields is None:
        fields = next(iter(forms.values()), {})
    return {
        name: {"type": field.type, "required": field.required, "multi": field.multi} for name, field in fields.items()
    }


def _preset(description: Any, upscaler: bool) -> Dict[str, Any]:
    return {
        "id": description.id,
        "name": description.name,
        "engine": description.engine,
        "category": description.category,
        "requires": description.requires,
        "modes": {
            name: {"default_form": mode.default_form, "fields": _fields(mode)}
            for name, mode in (description.modes or {}).items()
        },
        VIDEO_DIRECTOR: (description.vars or {}).get(VIDEO_DIRECTOR),
        "upscaler": upscaler,
    }


def video_presets(user: User) -> List[Dict[str, Any]]:
    """The video and upscaler presets the user may run; empty when they cannot be read."""
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s; reporting none", user.id, exc_info=True)
        return []
    listed = []
    for description in descriptions:
        upscaler = description.id in presets.UPSCALER_PRESETS
        if upscaler or is_video_preset(description):
            listed.append(_preset(description, upscaler))
    return listed
