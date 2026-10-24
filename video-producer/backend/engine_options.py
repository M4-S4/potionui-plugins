import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from . import models

NUMBER_TYPES = ("slider", "number", "stepper", "integer")
FLAG_TYPES = ("checkbox", "boolean", "gate")
CHOICE_TYPES = ("select", "sampler", "schedule")
TEXT_TYPES = ("textbox", "string")
SEED_TYPE = "seed"
MODEL_TYPE = "model"
LORA_TYPE = "lora_picker"

EDITABLE_TYPES = (*NUMBER_TYPES, *FLAG_TYPES, *CHOICE_TYPES, *TEXT_TYPES, SEED_TYPE, MODEL_TYPE, LORA_TYPE)

MANAGED = ("video_director", "references", "quantity", "resolution", "fps", "prompt", "negative_prompt", "aspect_ratio")
CLOUD_MANAGED = ("model",)

SEED = "seed"
STEPS = "steps"

SEED_RANGE = 2**31
TEXT_LIMIT = 2000
LORA_LIMIT = 32
REACTION_PASSES = 8

DESCRIBED = ("type", "label", "group", "audience", "gate", "default", "required", "limits", "reactions")


@dataclass
class Chosen:
    values: Dict[str, Any] = field(default_factory=dict)
    invalid: List[str] = field(default_factory=list)
    seed: Optional[int] = None


def editable(name: str, spec: Mapping[str, Any], cloud: bool = False) -> bool:
    """True for a field of a preset mode the project may set: a type the Edit Engine window can show, shown by the form, not bound to a cloud model's capabilities, and not one the plugin fills itself."""
    if spec.get("type") not in EDITABLE_TYPES or spec.get("hidden") or spec.get("bound"):
        return False
    return name not in MANAGED and not (cloud and name in CLOUD_MANAGED)


def describe(name: str, spec: Mapping[str, Any]) -> Dict[str, Any]:
    """What the Edit Engine window needs of a field: its name, type, label, groups, audience, gate, default, limits, reactions, the options of a choice and the recommended files of a model."""
    described: Dict[str, Any] = {"name": name, **{key: spec.get(key) for key in DESCRIBED}}
    described["group"] = list(spec.get("group") or [])
    described["limits"] = dict(spec.get("limits") or {})
    described["reactions"] = list(spec.get("reactions") or [])
    described["required"] = bool(spec.get("required"))
    if spec.get("type") in CHOICE_TYPES:
        described["options"] = [dict(option) for option in spec.get("options") or []]
    if spec.get("type") == MODEL_TYPE:
        described["recommended"] = [item["filename"] for item in spec.get("recommendations") or [] if item.get("filename")]
    return described


def editable_fields(fields: models.Fields, cloud: bool = False) -> List[Dict[str, Any]]:
    """The fields of a preset mode the project may set, in the order of the form."""
    return [describe(name, spec) for name, spec in fields.items() if editable(name, spec, cloud)]


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _whole(value: Any) -> bool:
    return _number(value) and float(value).is_integer()


def _within(value: float, low: Any, high: Any) -> bool:
    return (not _number(low) or value >= low) and (not _number(high) or value <= high)


def _integral(spec: Mapping[str, Any]) -> bool:
    limits = spec.get("limits") or {}
    step, low = limits.get("step"), limits.get("min")
    return spec.get("type") == "integer" or (_whole(step) and step >= 1 and (low is None or _whole(low)))


def _lora(row: Any, limits: Mapping[str, Any]) -> bool:
    if not isinstance(row, Mapping) or set(row) != {"model", "strength"}:
        return False
    model, strength = row["model"], row["strength"]
    return _model_ref(model) and _number(strength) and _within(strength, limits.get("strength_min"), limits.get("strength_max"))


def _model_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(models.MODEL_REF) and len(value) > len(models.MODEL_REF)


def valid(spec: Mapping[str, Any], value: Any) -> bool:
    """True when a value fits its field: a number within its limits (whole when its step is), a seed from -1 to 2³¹ - 1, a boolean, one of the options of a choice, a short text, a model:<id> reference, or a list of LoRAs with their strength within its limits."""
    kind = spec.get("type")
    limits = spec.get("limits") or {}
    if kind in NUMBER_TYPES:
        return _number(value) and _within(value, limits.get("min"), limits.get("max")) and (not _integral(spec) or _whole(value))
    if kind == SEED_TYPE:
        return isinstance(value, int) and not isinstance(value, bool) and -1 <= value < SEED_RANGE
    if kind in FLAG_TYPES:
        return isinstance(value, bool)
    if kind in CHOICE_TYPES:
        options = [option.get("value") for option in spec.get("options") or []]
        return isinstance(value, str) and (value in options if options else 0 < len(value) <= TEXT_LIMIT)
    if kind in TEXT_TYPES:
        limit = limits.get("max_length")
        return isinstance(value, str) and len(value) <= (limit if _whole(limit) else TEXT_LIMIT)
    if kind == MODEL_TYPE:
        return _model_ref(value)
    if kind == LORA_TYPE:
        most = limits.get("max_items")
        return isinstance(value, list) and len(value) <= (most if _whole(most) else LORA_LIMIT) and all(_lora(row, limits) for row in value)
    return False


def stored(doc: Mapping[str, Any], preset_id: Optional[str]) -> Dict[str, Any]:
    """The options the project keeps for a preset; empty when it keeps none."""
    options = (doc.get("engine") or {}).get("options")
    chosen = options.get(preset_id) if isinstance(options, Mapping) and preset_id else None
    return dict(chosen) if isinstance(chosen, Mapping) else {}


def chosen(doc: Mapping[str, Any], preset_id: str, fields: models.Fields, cloud: bool = False) -> Chosen:
    """The project's options for a preset that apply to a mode: the form values, the fields whose value does not fit, and a fixed seed, which the takes get instead of the form."""
    result = Chosen()
    for name, value in stored(doc, preset_id).items():
        spec = fields.get(name)
        if spec is None or not editable(name, spec, cloud):
            continue
        if not valid(spec, value):
            result.invalid.append(name)
        elif name == SEED:
            result.seed = value if value >= 0 else None
        else:
            result.values[name] = value
    return result


def _same(a: Any, b: Any) -> bool:
    if _number(a) and _number(b):
        return a == b
    return type(a) is type(b) and a == b


def _compare(a: Any, b: Any, test: Any) -> bool:
    try:
        return test(float(a), float(b))
    except (TypeError, ValueError):
        return False


def _empty(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, (list, dict)) and not value)


OPERATORS = {
    "equals": _same,
    "not_equals": lambda a, b: not _same(a, b),
    "in": lambda a, b: isinstance(b, list) and any(_same(a, item) for item in b),
    "not_in": lambda a, b: isinstance(b, list) and not any(_same(a, item) for item in b),
    "greater_than": lambda a, b: _compare(a, b, lambda x, y: x > y),
    "less_than": lambda a, b: _compare(a, b, lambda x, y: x < y),
    "greater_than_or_equals": lambda a, b: _compare(a, b, lambda x, y: x >= y),
    "less_than_or_equals": lambda a, b: _compare(a, b, lambda x, y: x <= y),
    "contains": lambda a, b: str(b) in str(a),
    "not_contains": lambda a, b: str(b) not in str(a),
    "is_empty": lambda a, b: _empty(a),
    "is_not_empty": lambda a, b: not _empty(a),
}


def matches(when: Any, values: Mapping[str, Any]) -> bool:
    """True when the values meet a reaction's condition: a list of conditions all met, AND or OR over conditions, or one field compared with an operator, written out or as its shorthand."""
    if isinstance(when, list):
        return all(matches(item, values) for item in when)
    if not isinstance(when, Mapping):
        return False
    if "logic" in when:
        conditions = when.get("conditions") if isinstance(when.get("conditions"), list) else []
        if when["logic"] == "OR":
            return any(matches(item, values) for item in conditions) if conditions else True
        return when["logic"] == "AND" and all(matches(item, values) for item in conditions)
    operator = when.get("operator") or next((key for key in OPERATORS if key in when), None)
    test = OPERATORS.get(operator)
    if test is None or not isinstance(when.get("field"), str):
        return False
    expected = when.get("value") if "operator" in when else when.get(operator)
    return bool(test(values.get(when["field"]), expected))


def resolved(fields: models.Fields, values: Mapping[str, Any]) -> Dict[str, Any]:
    """The value of every field once the form fills in its defaults and the reactions of the fields left out, as the core binds a request."""
    given = {name: value for name, value in values.items() if name in fields}
    current = {name: spec.get("default") for name, spec in fields.items()}
    current.update(given)
    for _ in range(REACTION_PASSES):
        snapshot = dict(current)
        for name, spec in fields.items():
            if name in given:
                continue
            for reaction in spec.get("reactions") or []:
                then = reaction.get("then") or {}
                if "set_value" in then and matches(reaction.get("when"), snapshot):
                    current[name] = then["set_value"]
        if current == snapshot:
            break
    return current


def steps(fields: models.Fields, values: Mapping[str, Any]) -> Optional[float]:
    """The number of steps a request runs, or None when the mode has no step count."""
    spec = fields.get(STEPS)
    if spec is None or spec.get("type") not in NUMBER_TYPES:
        return None
    value = resolved(fields, values).get(STEPS)
    return float(value) if _number(value) and value > 0 else None


def work_scale(fields: models.Fields, values: Mapping[str, Any]) -> float:
    """How much longer than at the mode's defaults a request runs, the time of a take being taken as proportional to its steps; 1 when either count is unknown."""
    asked, default = steps(fields, values), steps(fields, {})
    return asked / default if asked is not None and default is not None else 1.0


def take_scale(take: Mapping[str, Any]) -> float:
    """The work scale of a take's request against its mode's defaults, so that its measure counts as one made at those defaults; 1 when it cannot be told."""
    request = take.get("request") if isinstance(take.get("request"), Mapping) else {}
    form = request.get("form_data") if isinstance(request.get("form_data"), Mapping) else {}
    preset_id, mode = take.get("preset_id"), take.get("mode")
    if not form or not isinstance(preset_id, str) or not isinstance(mode, str):
        return 1.0
    scale = work_scale(models.form_fields(preset_id, mode), form)
    return scale if scale > 0 else 1.0
