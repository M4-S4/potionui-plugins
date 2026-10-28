import logging
from typing import Any, Dict, Mapping, Optional

from . import core_bridge, formats, models, presets
from .core_bridge import User

logger = logging.getLogger("plugins.video-producer")

AUTO = "auto"
SEEDVR2 = "seedvr2"
RTX = "rtx"
ENGINE = "engine"

CHOICES = (AUTO, SEEDVR2, RTX, ENGINE)

PRESET_OF = {SEEDVR2: presets.SEEDVR2, RTX: presets.RTX_UPSCALE}

MODE = "video_upscale"

RTX_MODULE = "nvvfx"
RTX_TARGET_FIELD = "target_short_side"

UPSCALE_SHORT_SIDES = {"hd720": 720, "fhd1080": 1080, "qhd1440": 1440, "uhd2160": 2160}

NAMED_TARGETS = tuple(UPSCALE_SHORT_SIDES)

AUTO_TARGET = "auto"

TARGETS = (AUTO_TARGET, *NAMED_TARGETS)

DEFAULT_ASPECT = 16 / 9


def of_preset(preset_id: Any) -> str:
    """The upscaler an upscale take ran on, read from its preset: SeedVR2, RTX, else its engine's own mode."""
    for upscaler, owner in PRESET_OF.items():
        if preset_id == owner:
            return upscaler
    return ENGINE


def _runnable(user: User, preset_id: str) -> Optional[Any]:
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s", getattr(user, "id", None), exc_info=True)
        return None
    return next((item for item in descriptions if item.id == preset_id and MODE in (item.modes or {})), None)


def rtx_target_field(preset_id: str = presets.RTX_UPSCALE) -> bool:
    """Whether the RTX Upscale preset takes a target short side, which this plugin needs to ask for a size."""
    return RTX_TARGET_FIELD in models.form_fields(preset_id, MODE)


def ready(user: User) -> Dict[str, bool]:
    """The upscalers this user can run: SeedVR2 with its video mode; RTX with its video mode, a target short side and the nvidia-vfx module importable."""
    seedvr2 = _runnable(user, presets.SEEDVR2) is not None
    rtx = _runnable(user, presets.RTX_UPSCALE) is not None and rtx_target_field() and core_bridge.module_available(RTX_MODULE)
    return {SEEDVR2: seedvr2, RTX: bool(rtx)}


def _aspect(doc: Mapping[str, Any]) -> float:
    ratio = formats.ratio_of(doc.get("aspect"))
    return ratio if ratio else DEFAULT_ASPECT


def needed_short_side(doc: Mapping[str, Any], width: Any, height: Any) -> Optional[float]:
    """The short side a take of this size needs to fill the film's delivery frame as the export shows it: covering the frame when it is cropped or exact, inside it when it gets bars."""
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None
    frame_width, frame_height = formats.delivery_size(_aspect(doc), formats.resolution_value(doc.get("resolution")))
    shown = formats.fit(width / height, frame_width / frame_height, formats.framing_of(doc))
    pick = min if shown == formats.BARS else max
    return min(width, height) * pick(frame_width / width, frame_height / height)


def auto_target(doc: Mapping[str, Any], width: Any, height: Any) -> str:
    """The smallest named target whose short side gives the take what the export needs within the size tolerance of the formats table, never below the take's own short side, at most 2160."""
    needed = needed_short_side(doc, width, height)
    if needed is None:
        resolution = formats.resolution_value(doc.get("resolution"))
        needed = float(formats.RESOLUTIONS[resolution])
    else:
        needed = max(needed * (1 - formats.SIZES["tolerance"]), float(min(width, height)))
    for name, short in UPSCALE_SHORT_SIDES.items():
        if short >= needed - 0.5:
            return name
    return NAMED_TARGETS[-1]


def resolve_target(target: str, doc: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    """A named target: the one asked for, or the one Auto gives this take in this film."""
    if target in UPSCALE_SHORT_SIDES:
        return target
    return auto_target(doc, source.get("width"), source.get("height"))
