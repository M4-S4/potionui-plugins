import logging
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import catalog, core_bridge, director, estimate, formats, models, presets, upscalers
from .core_bridge import User

logger = logging.getLogger("plugins.video-producer")

CHOICES = upscalers.INTERPOLATORS

AUTO, RIFE, RTX = CHOICES

RTX_CHECKED = upscalers.RTX_CHECKED

PRESET_OF = {RIFE: presets.VIDEO_TOOLS, RTX: presets.RTX_UPSCALE}

MODE = "interpolate"

TARGET_FIELD = "target_fps"

RTX_MODEL_FIELD = "mode"

RTX_MODEL = "medium"

RTX_PACKAGE = "nvidia-vfx"

RTX_LEAST = (0, 2)

HALF_FLOW_SHORT_SIDE = 1440

FACTORS = (2, 4)

speed_of = formats.speed_of


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


def needed_fps(doc: Mapping[str, Any], clip: Optional[Mapping[str, Any]], take_fps: Any) -> Optional[float]:
    """The frame rate a take needs on a shot: the film's divided by the shot's speed, when the take is slower than that by the table's share or more; None when it needs no version."""
    film = target_of(doc)
    if film is None:
        return None
    fps = film / speed_of(clip)
    return fps if needs_conform(take_fps, fps) else None


def passes(take_fps: Any, fps: float, film: int) -> List[Tuple[float, Optional[int]]]:
    """How a take reaches a frame rate, as (frame rate, multiplier) steps: one step to a frame rate the interpolators take, else a multiplier of the film's rate, from the take when it already runs at it and from its version at the film's rate otherwise."""
    if float(fps).is_integer() and int(fps) in formats.CADENCES:
        return [(float(fps), None)]
    factor = round(fps / film)
    if factor not in FACTORS or abs(factor * film - fps) > 1e-6:
        raise ValueError(f"{fps} fps is not a multiple of the film's {film} fps that an interpolator makes")
    source = _positive(take_fps)
    if source is not None and abs(source - film) < 1e-6:
        return [(float(fps), factor)]
    return [(float(film), None), (float(fps), factor)]


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


def frame_generation_installed(engine: Optional[Mapping[str, Any]]) -> Optional[bool]:
    """Whether nvidia-vfx 0.2 or later, which brings NVIDIA Frame Generation, is installed where the RTX pipes run; None when that is a remote worker, whose packages this server cannot see."""
    module = upscalers.nvvfx(engine)
    if module is None:
        return None
    return module and _version(core_bridge.package_version(RTX_PACKAGE)) >= RTX_LEAST


def ready(user: User, engines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, bool]:
    """The interpolators this user can run, both on the native engine, none without one: RIFE through Video Tools with a target frame rate; NVIDIA Frame Generation through RTX Upscale with a target frame rate and a model choice, nvidia-vfx 0.2 or later installed where it runs, which rtx_checked says was looked up here rather than left to a remote worker."""
    engine = catalog.native_engine(engines)
    if engine is None:
        return {RIFE: False, RTX: False, RTX_CHECKED: True}
    installed = frame_generation_installed(engine)
    rife = _runnable(user, presets.VIDEO_TOOLS) and TARGET_FIELD in models.form_fields(presets.VIDEO_TOOLS, MODE)
    rtx = False
    if _runnable(user, presets.RTX_UPSCALE) and installed is not False:
        fields = models.form_fields(presets.RTX_UPSCALE, MODE)
        rtx = TARGET_FIELD in fields and RTX_MODEL_FIELD in fields
    return {RIFE: bool(rife), RTX: bool(rtx), RTX_CHECKED: installed is not None}


def pick(choice: str, found: Mapping[str, bool]) -> Optional[str]:
    """The interpolator a choice runs on: Auto takes Frame Generation when it is ready and was checked here, else RIFE when it is ready, else Frame Generation left to a remote worker to check; a named one only when it is ready."""
    if choice == AUTO:
        if found.get(RTX) and found.get(RTX_CHECKED, True):
            return RTX
        return RIFE if found.get(RIFE) else RTX if found.get(RTX) else None
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


def build_request(user: User, take: Mapping[str, Any], fps: float, interpolator: str, factor: Optional[int] = None) -> Tuple[Dict[str, Any], List[str]]:
    """The request that brings a finished take, or a finished version of it, to a frame rate, or multiplies its rate, duration and sound kept, and the models it misses: RIFE 4.25 with cuts detected and half flow from 1440 up, or Frame Generation Medium; DirectorError when the video is gone."""
    preset_id = PRESET_OF[interpolator]
    media = director.source_video(user, take)
    rate = {TARGET_FIELD: 0, "factor": int(factor)} if factor else {TARGET_FIELD: int(fps)}
    form: Dict[str, Any] = {"input_video": media["value"], **rate, "keep_audio": True, "scene_detection": True}
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
