import logging
from typing import Any, Dict, List, Mapping, Optional

from . import core_bridge, engine_options, models, presets, reception
from .core_bridge import CLOUD_ENGINE, User

logger = logging.getLogger("plugins.video-producer")

VIDEO_DIRECTOR = "video_director"

VIDEO_PRODUCER = "video_producer"

NATIVE_KINDS = {"native.local": "local", "native.remote": "remote"}

READY = "ready"
REMOTE = "remote"
NO_GPU = "no_gpu"
UNREAD = "unread"
UNESTABLISHED = "unestablished"

FL2VA = "FL2VA"
REF2VA = "Ref2VA"
HYBRID_AV = "Hybrid AV"

PROFILES = (FL2VA, REF2VA, HYBRID_AV)

REFS_MODE = "refs"

CLOUD_MODES = ("txt2video", "img2video")

DEFAULT_FPS = 24

UPSCALE_TARGETS = ("hd720", "fhd1080", "qhd1440", "uhd2160")

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


def gpu_state(backend: Mapping[str, Any]) -> str:
    """Where a native backend would run a take: ready, remote, no_gpu, unread or unestablished."""
    device = backend.get("execution_device")
    if device in (REMOTE, NO_GPU):
        return device
    if device == "this_host_gpu":
        return READY if _positive(backend.get("vram_total_gb")) else UNREAD
    return UNESTABLISHED


def _cloud_models(backend_id: str) -> List[Dict[str, Any]]:
    try:
        return core_bridge.cloud_video_models(backend_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the video models of cloud backend %s", backend_id, exc_info=True)
        return []


def video_engines() -> List[Dict[str, Any]]:
    """The enabled native and cloud backends takes can run on, highest priority first, a cloud one with its video models, a native one configured with no GPU left out; empty when they cannot be read."""
    try:
        backends = core_bridge.enabled_backends()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the backends; reporting none", exc_info=True)
        return []
    engines = []
    for backend in backends:
        kind = engine_kind(backend)
        if kind is None or (kind != "cloud" and gpu_state(backend) == NO_GPU):
            continue
        engine = {**{key: backend.get(key) for key in ENGINE_KEYS}, "kind": kind}
        if kind == "cloud":
            engine["models"] = _cloud_models(backend.get("id"))
        engines.append(engine)
    return engines


def native_engine(engines: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """The native backend the takes of native presets run on: the first of the engines, listed when not given, that is this machine's or a remote worker; None without any, when only cloud backends are enabled."""
    found = video_engines() if engines is None else engines
    return next((engine for engine in found if engine.get("kind") in NATIVE_KINDS.values()), None)


def is_video_preset(description: Any) -> bool:
    """True for a preset the Video Director drives."""
    return VIDEO_DIRECTOR in (description.vars or {})


def director_of(variables: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The Video Director capabilities a preset declares, or an empty mapping."""
    director = (variables or {}).get(VIDEO_DIRECTOR)
    return dict(director) if isinstance(director, Mapping) else {}


def main_mode(variables: Optional[Mapping[str, Any]], modes: List[str]) -> Optional[str]:
    """The preset mode the Video Director opens on: the first of its preset modes, else the first mode."""
    for mode in director_of(variables).get("preset_modes") or []:
        if mode in modes:
            return mode
    return modes[0] if modes else None


def memory_profile(variables: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The memory profile a preset is set up for, such as "12 GB", read from its vars.video_producer.profile; None otherwise."""
    own = (variables or {}).get(VIDEO_PRODUCER)
    profile = own.get("profile") if isinstance(own, Mapping) else None
    return profile.strip() if isinstance(profile, str) and profile.strip() else None


def preset_limits(variables: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The Video Director limits of a preset: default and maximum duration, default fps."""
    limits = director_of(variables).get("limits")
    return dict(limits) if isinstance(limits, Mapping) else {}


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def preset_fps(variables: Optional[Mapping[str, Any]]) -> float:
    """The frame rate a preset renders at by default."""
    variables = variables or {}
    for value in (preset_limits(variables).get("default_fps"), variables.get("default_fps"), variables.get("fps")):
        if _positive(value):
            return value
    return DEFAULT_FPS


def fps_locked(variables: Optional[Mapping[str, Any]], fields: Mapping[str, Any]) -> bool:
    """True when the preset fixes its frame rate: a director mode says so, or its form has no fps field."""
    composition = director_of(variables).get("modes") or {}
    declared = any(isinstance(mode, Mapping) and mode.get("fps_locked") for mode in composition.values())
    return declared or (bool(fields) and "fps" not in fields)


def audio_mux(variables: Optional[Mapping[str, Any]]) -> bool:
    """True when a preset's director mode takes an audio track, which the plugin lays onto the finished video."""
    composition = director_of(variables).get("modes") or {}
    director = composition.get("director") if isinstance(composition, Mapping) else None
    return isinstance(director, Mapping) and director.get("audio") is True


def director_modes(variables: Optional[Mapping[str, Any]]) -> List[str]:
    """The composition modes a preset offers in any of its preset modes."""
    director = director_of(variables)
    layers = [director.get("modes") or {}]
    for override in (director.get("preset_mode_overrides") or {}).values():
        if isinstance(override, Mapping):
            layers.append(override.get("modes") or {})
    found: List[str] = []
    for layer in layers:
        for name, capability in layer.items():
            if capability is not None and name not in found:
                found.append(name)
    return found


def profiles(preset_id: str, variables: Optional[Mapping[str, Any]], modes: List[str]) -> List[str]:
    """The generation profiles a preset can run: Ref2VA for MiniMax-H3 when it has a References mode, and for the presets that make it from a reference sheet when their director mode takes an IC-LoRA."""
    if not director_of(variables):
        return []
    if preset_id in reception.SHEET["presets"]:
        director = (director_of(variables).get("modes") or {}).get("director")
        return [FL2VA, *([REF2VA] if isinstance(director, Mapping) and director.get("ic_lora") else [])]
    if preset_id not in presets.MINIMAX_H3_PRESETS:
        return [FL2VA]
    return [FL2VA, *([REF2VA] if REFS_MODE in modes else []), HYBRID_AV]


def run_modes(preset_id: str, variables: Optional[Mapping[str, Any]], modes: List[str], engine: Optional[str]) -> List[str]:
    """The preset modes the Video Director runs a preset in: its main mode, its References mode when it runs Ref2VA, and the text and image modes of a cloud preset."""
    if not director_of(variables):
        return []
    wanted = [main_mode(variables, modes)]
    if REF2VA in profiles(preset_id, variables, modes):
        wanted.append(REFS_MODE)
    if engine == CLOUD_ENGINE:
        wanted.extend(CLOUD_MODES)
    return [mode for mode in dict.fromkeys(wanted) if mode in modes]


def _fields(mode: Any) -> Dict[str, Any]:
    forms = mode.forms or {}
    fields = forms.get(mode.default_form)
    if fields is None:
        fields = next(iter(forms.values()), {})
    return {
        name: {"type": field.type, "required": field.required, "multi": field.multi} for name, field in fields.items()
    }


def _driver(preset_id: str) -> Optional[str]:
    try:
        return core_bridge.preset_driver(preset_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the driver of preset %s", preset_id, exc_info=True)
        return None


def _cloud_backends() -> List[Dict[str, Any]]:
    try:
        return [backend for backend in core_bridge.enabled_backends() if backend.get("engine") == CLOUD_ENGINE]
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the backends; no cloud preset is tied to one", exc_info=True)
        return []


def preset_backend_id(description: Any, driver: Optional[str], cloud_backends: List[Dict[str, Any]]) -> Optional[str]:
    """The cloud backend a cloud preset runs on, the first enabled one with its driver; None for a native preset."""
    if description.engine != CLOUD_ENGINE or not driver:
        return None
    return next((backend.get("id") for backend in cloud_backends if backend.get("driver") == driver), None)


def _preset(description: Any, upscaler: bool, cloud_backends: List[Dict[str, Any]]) -> Dict[str, Any]:
    variables = description.vars or {}
    modes = list(description.modes or {})
    director = director_of(variables)
    main = main_mode(variables, modes) if director else None
    fields = models.form_fields(description.id, main) if main else {}
    run = run_modes(description.id, variables, modes, description.engine)
    cloud = description.engine == CLOUD_ENGINE
    driver = _driver(description.id)
    return {
        "id": description.id,
        "name": description.name,
        "engine": description.engine,
        "category": description.category,
        "requires": description.requires,
        "profile": memory_profile(variables),
        "modes": {
            name: {
                "default_form": mode.default_form,
                "fields": _fields(mode),
                **(
                    {"options": engine_options.editable_fields(fields if name == main else models.form_fields(description.id, name), cloud)}
                    if name in run
                    else {}
                ),
            }
            for name, mode in (description.modes or {}).items()
        },
        VIDEO_DIRECTOR: variables.get(VIDEO_DIRECTOR),
        "upscaler": upscaler,
        "resolutions": [
            {"value": option["value"], "label": option.get("label") or option["value"]}
            for option in models.resolution_options(fields)
        ],
        "fps": preset_fps(variables) if director else None,
        "fps_locked": fps_locked(variables, fields) if director else False,
        "limits": preset_limits(variables),
        "director_modes": director_modes(variables),
        "audio_mux": audio_mux(variables),
        "profiles": profiles(description.id, variables, modes),
        "driver": driver,
        "backend_id": preset_backend_id(description, driver, cloud_backends),
    }


def video_presets(user: User) -> List[Dict[str, Any]]:
    """The video and upscaler presets the user may run, with their driver and cloud backend; empty when they cannot be read."""
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s; reporting none", user.id, exc_info=True)
        return []
    wanted = [
        (description, description.id in presets.UPSCALER_PRESETS)
        for description in descriptions
        if description.id in presets.UPSCALER_PRESETS or is_video_preset(description)
    ]
    cloud_backends = _cloud_backends() if any(description.engine == CLOUD_ENGINE for description, _ in wanted) else []
    return [_preset(description, upscaler, cloud_backends) for description, upscaler in wanted]
