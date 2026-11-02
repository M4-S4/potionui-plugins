import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import core_bridge

logger = logging.getLogger("plugins.video-producer")

MODEL_REF = "model:"

MODEL_FIELD = "model"

LORA_FIELD = "lora_picker"

Fields = Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class ResolvedModels:
    values: Dict[str, Any] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)


def parse_size(value: Any) -> Optional[Tuple[int, int]]:
    """Width and height of a "WxH" value, or None."""
    if not isinstance(value, str) or value.count("x") != 1:
        return None
    width, height = value.split("x")
    if not (width.strip().isdigit() and height.strip().isdigit()):
        return None
    size = (int(width), int(height))
    return size if size[0] > 0 and size[1] > 0 else None


def form_fields(preset_id: str, mode: str) -> Fields:
    """The fields of a preset mode as the core declares them; empty when they cannot be read."""
    try:
        return core_bridge.preset_form_fields(preset_id, mode) or {}
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the fields of preset %s mode %s", preset_id, mode, exc_info=True)
        return {}


def resolution_options(fields: Fields) -> List[Dict[str, str]]:
    """The "WxH" options of a mode's resolution field."""
    options = (fields.get("resolution") or {}).get("options") or []
    return [dict(option) for option in options if parse_size(option.get("value"))]


def model_fields(fields: Fields, director_mode: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """The model fields a run needs, and the optional ones it takes when installed."""
    required = [name for name, spec in fields.items() if spec.get("type") == MODEL_FIELD and spec.get("required")]
    prefix = "i2v" if director_mode in ("i2v", "flf") else "t2v"
    high, low = f"{prefix}_high_noise_model", f"{prefix}_low_noise_model"
    if high in fields and high not in required:
        required.append(high)
    optional = [low] if low in fields and low not in required else []
    return required, optional


def _lookup(kind: str, value: str, cache: Dict[Tuple[str, str], Optional[str]]) -> Optional[str]:
    if (kind, value) not in cache:
        finder = core_bridge.installed_model_id if kind == "sha256" else core_bridge.installed_model_for_file
        try:
            cache[(kind, value)] = finder(value)
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not look up the model with %s %s", kind, value, exc_info=True)
            cache[(kind, value)] = None
    return cache[(kind, value)]


def _installed(recommendation: Dict[str, Any], cache: Dict[Tuple[str, str], Optional[str]]) -> Optional[str]:
    for kind in ("sha256", "filename"):
        value = recommendation.get(kind)
        found = _lookup(kind, value, cache) if value else None
        if found:
            return found
    return None


def _other_modes(preset_id: str, mode: str) -> List[str]:
    try:
        description = core_bridge.describe_preset(preset_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not describe preset %s", preset_id, exc_info=True)
        return []
    return [name for name in (description.modes if description is not None else {}) if name != mode]


def resolve_models(
    preset_id: str, mode: str, director_mode: Optional[str] = None, fields: Optional[Fields] = None, needed: Sequence[str] = ()
) -> ResolvedModels:
    """The first installed recommended file of each model field a run needs (with the named ones the mode has, such as the audio VAE of a run that carries sound), as model:<id>, the fields left without one, and the file name of each recommendation used."""
    fields = form_fields(preset_id, mode) if fields is None else fields
    required, optional = model_fields(fields, director_mode)
    required += [name for name in needed if name in fields and name not in required]
    optional = [name for name in optional if name not in required]
    cache: Dict[Tuple[str, str], Optional[str]] = {}
    others: List[Fields] = []
    loaded = False

    def recommended(name: str) -> Sequence[Dict[str, Any]]:
        nonlocal loaded
        own = (fields.get(name) or {}).get("recommendations") or []
        if own:
            return own
        if not loaded:
            others.extend(form_fields(preset_id, other) for other in _other_modes(preset_id, mode))
            loaded = True
        return next(
            (found for other in others if (found := (other.get(name) or {}).get("recommendations") or [])), []
        )

    values: Dict[str, Any] = {}
    missing: List[str] = []
    files: Dict[str, str] = {}
    for name in [*required, *optional]:
        chosen = next(((item, found) for item in recommended(name) if (found := _installed(item, cache))), None)
        if chosen is not None:
            values[name] = f"{MODEL_REF}{chosen[1]}"
            if chosen[0].get("filename"):
                files[name] = str(chosen[0]["filename"])
        elif name in required:
            missing.append(name)
    for name, rows in _default_loras(fields):
        resolved = _resolve_loras(rows, cache)
        if resolved is None:
            missing.append(name)
        else:
            values[name] = resolved
    return ResolvedModels(values=values, missing=missing, files=files)


def _default_loras(fields: Fields) -> List[Tuple[str, List[Dict[str, Any]]]]:
    found = []
    for name, spec in fields.items():
        rows = spec.get("default") if spec.get("type") == LORA_FIELD else None
        if isinstance(rows, list) and any(isinstance(row, dict) and row.get("model") for row in rows):
            found.append((name, [row for row in rows if isinstance(row, dict) and row.get("model")]))
    return found


def _resolve_loras(rows: List[Dict[str, Any]], cache: Dict[Tuple[str, str], Optional[str]]) -> Optional[List[Dict[str, Any]]]:
    resolved = []
    for row in rows:
        model = str(row["model"])
        if not model.startswith(MODEL_REF):
            model_id = _lookup("filename", model.replace("\\", "/").rsplit("/", 1)[-1], cache)
            if model_id is None:
                return None
            model = f"{MODEL_REF}{model_id}"
        resolved.append({**row, "model": model})
    return resolved
