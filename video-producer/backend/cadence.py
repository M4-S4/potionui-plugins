import logging
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import core_bridge, director, estimate, formats, models, presets, upscalers
from .core_bridge import User

logger = logging.getLogger("plugins.video-producer")

CHOICES = upscalers.INTERPOLATORS

AUTO, RIFE, RTX = CHOICES

PRESET_OF = {RIFE: presets.VIDEO_TOOLS, RTX: presets.RTX_UPSCALE}

MODE = "interpolate"

TARGET_FIELD = "target_fps"

RTX_MODEL_FIELD = "mode"

RTX_MODEL = "medium"

RTX_PACKAGE = "nvidia-vfx"

RTX_LEAST = (0, 2)

HALF_FLOW_SHORT_SIDE = 1440


def _positive(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def project_fps(doc: Mapping[str, Any]) -> float:
    """The frame rate of the film, the table's default when the document has none."""
    return _positive(doc.get("fps")) or float(formats.DEFAULT_CADENCE)


def target_of(doc: Mapping[str, Any]) -> Optional[int]:
    """The frame rate a take is conformed to in this film: the film's, when it is one of the table's cadences."""
    fps = project_fps(doc)
    return int(fps) if fps.is_integer() and int(fps) in formats.CADENCES else None


def needs_conform(take_fps: Any, fps: Any) -> bool:
    """Whether a take at this frame rate is slower than the film's by the table's share or more, so that the export would repeat its frames."""
    source, target = _positive(take_fps), _positive(fps)
    return source is not None and target is not None and source < target * (1 - formats.SLOWER) - 1e-9


def choice_of(doc: Mapping[str, Any]) -> str:
    """The interpolator the film asks for: Auto unless its final pass choices name one."""
    chosen = (doc.get("finalPass") or {}).get("interpolator")
    return chosen if chosen in CHOICES else AUTO


def _version(text: Optional[str]) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])


def _runnable(user: User, preset_id: str) -> bool:
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s", getattr(user, "id", None), exc_info=True)
        return False
    return any(item.id == preset_id and MODE in (item.modes or {}) for item in descriptions)


def frame_generation_installed() -> bool:
    """Whether nvidia-vfx 0.2 or later, which brings NVIDIA Frame Generation, is installed on the server."""
    return core_bridge.module_available(upscalers.RTX_MODULE) and _version(core_bridge.package_version(RTX_PACKAGE)) >= RTX_LEAST


def ready(user: User) -> Dict[str, bool]:
    """The interpolators this user can run: RIFE through Video Tools with a target frame rate; NVIDIA Frame Generation through RTX Upscale with a target frame rate and a model choice, nvidia-vfx 0.2 or later installed."""
    rife = _runnable(user, presets.VIDEO_TOOLS) and TARGET_FIELD in models.form_fields(presets.VIDEO_TOOLS, MODE)
    rtx = False
    if _runnable(user, presets.RTX_UPSCALE) and frame_generation_installed():
        fields = models.form_fields(presets.RTX_UPSCALE, MODE)
        rtx = TARGET_FIELD in fields and RTX_MODEL_FIELD in fields
    return {RIFE: bool(rife), RTX: bool(rtx)}


def pick(choice: str, found: Mapping[str, bool]) -> Optional[str]:
    """The interpolator a choice runs on: Auto takes Frame Generation when it is ready, RIFE otherwise; a named one only when it is ready."""
    if choice == AUTO:
        return RTX if found.get(RTX) else RIFE if found.get(RIFE) else None
    return choice if found.get(choice) else None


def missing_note(choice: str) -> Dict[str, Any]:
    """The block of a conform no interpolator can run."""
    if choice == RTX:
        return director.note(
            "interpolator_missing",
            "NVIDIA Frame Generation needs the RTX Upscale plugin with its Interpolate mode and nvidia-vfx 0.2 or later on the server.",
            interpolator=RTX,
        )
    return director.note(
        "interpolator_missing",
        "No interpolator is available: install the Video Tools preset with RIFE 4.25, or NVIDIA Frame Generation.",
        interpolator=choice,
    )


def _short_side(take: Mapping[str, Any]) -> int:
    sizes = [value for value in (take.get("width"), take.get("height")) if isinstance(value, int) and value > 0]
    return min(sizes) if sizes else 0


def build_request(user: User, take: Mapping[str, Any], fps: int, interpolator: str) -> Tuple[Dict[str, Any], List[str]]:
    """The request that brings a finished take to a frame rate, duration and sound kept, and the models it misses: RIFE 4.25 with cuts detected and half flow from 1440 up, or Frame Generation Medium; DirectorError when the take's video is gone."""
    preset_id = PRESET_OF[interpolator]
    media = director.source_video(user, take)
    form: Dict[str, Any] = {"input_video": media["value"], TARGET_FIELD: int(fps), "keep_audio": True, "scene_detection": True}
    if media.get("origin"):
        form["input_video__origin"] = media["origin"]
    if interpolator == RTX:
        form[RTX_MODEL_FIELD] = RTX_MODEL
        return _request(preset_id, form), []
    form["flow_scale"] = 0.5 if _short_side(take) >= HALF_FLOW_SHORT_SIDE else 1.0
    resolved = models.resolve_models(preset_id, MODE)
    form.update(resolved.values)
    return _request(preset_id, form), list(resolved.missing)


def _request(preset_id: str, form: Dict[str, Any]) -> Dict[str, Any]:
    return {"preset_id": preset_id, "mode": MODE, "prompts": [{"positive": "", "negative": ""}], "form_data": form}


def seconds_for(interpolator: Optional[str], backend_id: Optional[str], resolution: Optional[str], duration_s: Any) -> Optional[float]:
    """How long bringing a take of this size and length to the film's frame rate takes, from the measures of the interpolator; None when it was never measured near this size."""
    length = _positive(duration_s)
    if interpolator is None or length is None:
        return None
    ratio, _ = estimate.calibrated_ratio(PRESET_OF[interpolator], backend_id, resolution)
    return None if ratio is None else ratio * length
