import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from fastapi import HTTPException

from src.plugin_api.chat import ToolApprovalPreview, ToolContext, ToolResult

from .. import bible, core_bridge, director, estimate, generation, limits, projects, settings, takes, tracker
from ..exports import jobs, video
from ..generation import Blocked
from ..routes_exports import queue_video
from . import cards, edits
from .edits import EditError
from .tools import (
    MAX_DURATION_S,
    MAX_LABEL_CHARS,
    MAX_SHOTS,
    MAX_TEXT_CHARS,
    MIN_DURATION_S,
    INVALID_ARGUMENTS,
    PROJECT_NOT_FOUND,
    ToolFailure,
    _VideoProducerTool,
    commit,
    instruction_of,
    load_project,
    page_context,
)

PRODUCTION = "vp_production"
CARD_EXPIRED = "card_expired"
CARD_OUT_OF_DATE = "card_out_of_date"
MAX_TAKES_PER_SHOT = 8
MAX_READ_CHARS = 9000
MAX_READ_PROMPT_CHARS = 1200
MAX_SHOT_TAKES = 6
MAX_MEDIA = 30
MAX_EXPORTS = 3
PREVIEW_CHARS = 80
LABELS = takes.LABELS
QUALITIES = estimate.QUALITIES
SPACE_NAMES = {value: key for key, value in edits.SPACES.items()}

REF_SCHEMA = {"type": "string", "description": "A shot: its id from the context, its number, or its exact label"}
SHOTS_SCHEMA = {"type": "array", "items": REF_SCHEMA, "minItems": 1, "maxItems": MAX_SHOTS}
LABEL_SCHEMA = {"type": "string", "maxLength": MAX_LABEL_CHARS}
DURATION_SCHEMA = {"type": "number", "minimum": MIN_DURATION_S, "maximum": MAX_DURATION_S}
CHARACTERS_SCHEMA = {"type": "array", "items": {"type": "string"}, "description": "Bible character labels; [] clears"}
PLACE_SCHEMA = {"type": "string", "description": "Bible place label; empty clears"}


def _ok(payload: Mapping[str, Any], preview: Optional[ToolApprovalPreview] = None) -> ToolResult:
    return ToolResult(success=True, data=json.dumps(payload, ensure_ascii=False), preview=preview)


def _invalid(message: str) -> ToolFailure:
    return ToolFailure(INVALID_ARGUMENTS, message)


def _edit(error: EditError) -> ToolFailure:
    return ToolFailure(error.code, error.message)


def _http(error: HTTPException) -> ToolFailure:
    detail = error.detail if isinstance(error.detail, dict) else {}
    return ToolFailure(str(detail.get("error") or "failed"), str(detail.get("message") or "The action failed."))


def _list(value: Any, name: str, limit: int = MAX_SHOTS) -> List[Any]:
    items = [value] if isinstance(value, (str, int)) and not isinstance(value, bool) else value
    if not isinstance(items, list) or not items:
        raise _invalid(f"{name} must be a non-empty list.")
    if len(items) > limit:
        raise _invalid(f"{name} lists more than {limit} items.")
    return items


def _optional_list(value: Any, name: str) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = [value] if value.strip() else []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _invalid(f"{name} must be a list of strings.")
    return [item for item in value if item.strip()]


def _label(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_LABEL_CHARS:
        raise _invalid(f"{name} must be 1 to {MAX_LABEL_CHARS} characters.")
    return value.strip()


def _duration(value: Any, name: str) -> float:
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            value = None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_DURATION_S <= value <= MAX_DURATION_S:
        raise _invalid(f"{name} must be a number of seconds from {MIN_DURATION_S} to {MAX_DURATION_S}.")
    return float(value)


def _count(value: Any, name: str, top: int = MAX_TAKES_PER_SHOT) -> int:
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
        raise _invalid(f"{name} must be a whole number from 1 to {top}.")
    return value


def _text(value: Any, name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _invalid(f"{name} must be a string.")
    if len(value) > MAX_TEXT_CHARS:
        raise _invalid(f"{name} is longer than {MAX_TEXT_CHARS} characters.")
    return value.strip()


def _seconds(value: Any) -> float:
    return round(edits.number(value), 2)


def _head(text: Any, limit: int = PREVIEW_CHARS) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


def _user(user_id: str) -> core_bridge.User:
    user = core_bridge.get_user(user_id)
    if user is None:
        raise ToolFailure("user_not_found", "The user of this chat no longer exists.")
    return user


def _owner(context: ToolContext, project: Mapping[str, Any]) -> Tuple[core_bridge.User, core_bridge.User]:
    caller = _user(context.user_id)
    if project["user_id"] == caller.id:
        return caller, caller
    owner = core_bridge.get_user(project["user_id"])
    if owner is None:
        raise ToolFailure("owner_not_found", "The owner of this project no longer exists.")
    return caller, owner


def _language(context: ToolContext) -> str:
    shown = page_context(context).get("locale")
    return shown if shown in edits.TAKE_NAMES else settings.user_locale(context.user_id) or "en"


def _changed(context: ToolContext, change: Callable[[Dict[str, Any]], Any]) -> Tuple[Dict[str, Any], Any, int]:
    def apply(doc: Dict[str, Any]) -> Any:
        try:
            return change(doc)
        except EditError as error:
            raise _edit(error) from None

    return commit(context, apply)


def _shot_entry(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": clip["id"],
        "n": edits.index_of(doc, clip) + 1,
        "label": edits.shot_name(doc, clip, "en"),
        "start_s": _seconds(clip.get("start")),
        "duration_s": _seconds(clip.get("dur")),
    }


def _cast_ids(doc: Mapping[str, Any], characters: Optional[List[str]], place: Any) -> Tuple[Optional[List[str]], Any]:
    ids = None if characters is None else list(dict.fromkeys(edits.find_card(doc, bible.CHARACTERS, item).id for item in characters))
    if place is ...:
        return ids, ...
    if place is None or (isinstance(place, str) and not place.strip()):
        return ids, None
    if not isinstance(place, str):
        raise EditError(INVALID_ARGUMENTS, "place must be the label of a bible place.")
    return ids, edits.find_card(doc, bible.PLACES, place).id


def _take_entry(take: Mapping[str, Any]) -> Dict[str, Any]:
    entry = {"id": take["id"], "variant": take.get("variant"), "quality": take.get("quality"), "status": take.get("status"), "label": take.get("label")}
    if take.get("status") in takes.ACTIVE and take.get("progress") is not None:
        entry["progress"] = round(edits.number(take["progress"]))
    if take.get("status") == "failed" and take.get("error_message"):
        entry["error"] = _head(take["error_message"], 120)
    return entry


def _reference_entries(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    skipped = set(edits.excluded(clip))
    entries = [{"id": ref["id"], "name": ref.get("name"), "space": SPACE_NAMES.get(ref.get("space"), ref.get("space")), "own": True} for ref in edits.own_references(doc, clip)]
    entries += [
        {"id": ref["id"], "name": ref.get("name"), "space": SPACE_NAMES.get(ref.get("space"), ref.get("space")), "own": False, **({"excluded": True} if ref["id"] in skipped else {})}
        for ref in edits.global_references(doc)
    ]
    return entries


def _media_name(doc: Mapping[str, Any], asset_id: Optional[str]) -> Optional[str]:
    media = next((item for item in edits.dicts(doc.get("assets")) if asset_id and item.get("id") == asset_id), None)
    return str(media.get("name") or media["id"]) if media else None


def _shot_details(doc: Mapping[str, Any], clip: Mapping[str, Any], shot_takes: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    characters, place = bible.cast_of(doc, clip)
    placed = next((take for take in shot_takes if take["id"] == clip.get("take")), None)
    entry = {
        **_shot_entry(doc, clip),
        "stage": clip.get("stage"),
        "prompt": _head(instruction_of(doc, clip), MAX_READ_PROMPT_CHARS),
        "cast": [card.label for card in characters] + ([place.label] if place else []),
        "first_frame": _media_name(doc, edits.frame_asset(doc, clip, edits.FIRST)),
        "last_frame": _media_name(doc, edits.frame_asset(doc, clip, edits.LAST)),
        "references": _reference_entries(doc, clip),
        "takes": [_take_entry(take) for take in shot_takes[-MAX_SHOT_TAKES:]],
        "placed_take": placed["id"] if placed else None,
    }
    if isinstance(clip.get("drafts"), int):
        entry["takes_per_run"] = clip["drafts"]
    if isinstance(clip.get("firstFromPrevious"), bool):
        entry["chain"] = clip["firstFromPrevious"]
    return entry


def read_project(context: ToolContext, refs: Optional[List[Any]]) -> Dict[str, Any]:
    """What the assistant reads of the open project: its engine, its shots in detail with their takes, its media and its bible, within a size budget."""
    project = load_project(context)
    doc = project["doc"]
    clips = edits.clips_of(doc) if refs is None else [edits.find_shot(doc, ref) for ref in refs]
    by_shot: Dict[str, List[Dict[str, Any]]] = {}
    for take in takes.list_takes(project["id"]):
        by_shot.setdefault(take["shot_id"], []).append(take)
    engine = doc.get("engine") if isinstance(doc.get("engine"), dict) else {}
    payload: Dict[str, Any] = {
        "project_id": project["id"],
        "version": project["version"],
        "name": doc.get("name"),
        "engine": {"preset": engine.get("preset"), "model": engine.get("model"), "quality": engine.get("quality") or "draft", "takes_per_run": engine.get("variants") or 1},
        "bible": {kind: [{"id": card.id, "label": card.label} for card in bible.cards(doc, kind)] for kind in (bible.CHARACTERS, bible.PLACES)},
        "media": [
            {"id": item["id"], "name": item.get("name"), "kind": item.get("kind")}
            for item in edits.dicts(doc.get("assets"))
            if not item.get("generated")
        ][:MAX_MEDIA],
        "shots": [],
    }
    used = len(json.dumps(payload, ensure_ascii=False))
    for index, clip in enumerate(clips):
        entry = _shot_details(doc, clip, by_shot.get(clip["id"], []))
        size = len(json.dumps(entry, ensure_ascii=False)) + 2
        if payload["shots"] and used + size > MAX_READ_CHARS:
            payload["more_shots"] = len(clips) - index
            break
        payload["shots"].append(entry)
        used += size
    return payload


def _add_arguments(arguments: Mapping[str, Any]) -> List[Dict[str, Any]]:
    shots = _list(arguments.get("shots"), "shots")
    parsed = []
    for index, item in enumerate(shots):
        if not isinstance(item, dict):
            raise _invalid(f"shots[{index}] must be an object with label and duration_s.")
        parsed.append(
            {
                "label": _label(item.get("label"), f"shots[{index}].label"),
                "duration": _duration(item.get("duration_s", 4), f"shots[{index}].duration_s"),
                "prompt": _text(item.get("prompt"), f"shots[{index}].prompt"),
                "characters": _optional_list(item.get("characters"), f"shots[{index}].characters"),
                "place": item.get("place", ...),
            }
        )
    return parsed


def _insert_index(doc: Mapping[str, Any], after: Any) -> int:
    if after is None or (isinstance(after, str) and not after.strip()):
        return len(edits.clips_of(doc))
    if isinstance(after, str) and after.strip().lower() == "start":
        return 0
    return edits.index_of(doc, edits.find_shot(doc, after)) + 1


def add_shots(doc: Dict[str, Any], shots: Sequence[Mapping[str, Any]], after: Any) -> List[Dict[str, Any]]:
    """Insert the asked shots after a shot, at the start or at the end, with their bible cast resolved from labels."""
    index = _insert_index(doc, after)
    ready = []
    for shot in shots:
        characters, place = _cast_ids(doc, shot["characters"], shot["place"])
        cast = {**({"characters": characters} if characters else {}), **({"place": place} if place not in (None, ...) else {})}
        ready.append({"label": shot["label"], "duration": edits.snap(shot["duration"]), "prompt": shot["prompt"], "cast": cast})
    return [_shot_entry(doc, clip) for clip in edits.add_shots(doc, ready, index)]


UPDATE_FIELDS = ("label", "duration_s", "position", "characters", "place", "first_frame", "last_frame", "add_references", "remove_references", "exclude_references", "include_references", "takes_per_run", "chain")


def _update_arguments(arguments: Mapping[str, Any]) -> List[Dict[str, Any]]:
    updates = _list(arguments.get("updates"), "updates")
    parsed = []
    for index, item in enumerate(updates):
        if not isinstance(item, dict) or "shot" not in item:
            raise _invalid(f"updates[{index}] must be an object with shot and the fields to change.")
        where = f"updates[{index}]"
        unknown = sorted(set(item) - {"shot", *UPDATE_FIELDS})
        if unknown:
            raise _invalid(f"{where} has unknown fields: {', '.join(unknown)}. Prompts are written with vp_write_shot_prompt.")
        fields: Dict[str, Any] = {"shot": item["shot"]}
        if "label" in item:
            fields["label"] = _label(item["label"], f"{where}.label")
        if "duration_s" in item:
            fields["duration_s"] = _duration(item["duration_s"], f"{where}.duration_s")
        if "position" in item:
            fields["position"] = _count(item["position"], f"{where}.position", 10_000)
        if "characters" in item:
            fields["characters"] = _optional_list(item["characters"], f"{where}.characters") or []
        if "place" in item:
            fields["place"] = item["place"]
        for kind in ("first_frame", "last_frame"):
            if kind in item:
                if item[kind] is not None and not isinstance(item[kind], str):
                    raise _invalid(f"{where}.{kind} must be the id or name of a media, or empty.")
                fields[kind] = (item[kind] or "").strip()
        if "add_references" in item:
            added = item["add_references"] if isinstance(item["add_references"], list) else None
            if added is None or not all(isinstance(ref, dict) and isinstance(ref.get("media"), str) for ref in added):
                raise _invalid(f"{where}.add_references must list objects with media and space.")
            for ref in added:
                if ref.get("space", "identity") not in edits.SPACES:
                    raise _invalid(f"{where}.add_references space must be one of: {', '.join(edits.SPACES)}.")
            fields["add_references"] = [(ref["media"], edits.SPACES[ref.get("space", "identity")]) for ref in added]
        for key in ("remove_references", "exclude_references", "include_references"):
            if key in item:
                fields[key] = _optional_list(item[key], f"{where}.{key}") or []
        if "takes_per_run" in item:
            fields["takes_per_run"] = _count(item["takes_per_run"], f"{where}.takes_per_run")
        if "chain" in item:
            if not isinstance(item["chain"], bool):
                raise _invalid(f"{where}.chain must be true or false.")
            fields["chain"] = item["chain"]
        if len(fields) == 1:
            raise _invalid(f"{where} changes nothing.")
        parsed.append(fields)
    return parsed


def _references(doc: Dict[str, Any], clip: Dict[str, Any], fields: Mapping[str, Any], changed: List[str]) -> bool:
    inputs = False
    own = {ref["id"] for ref in edits.own_references(doc, clip)}
    inherited = {ref["id"] for ref in edits.global_references(doc)}
    for media, space in fields.get("add_references", []):
        edits.add_reference(doc, clip, edits.find_asset(doc, media), space)
        inputs = True
    removed = fields.get("remove_references", [])
    for ref in removed:
        if ref not in own:
            raise EditError("reference_not_found", f"The shot has no reference {ref!r} of its own.")
    if removed:
        doc["references"] = [ref for ref in edits.dicts(doc.get("references")) if ref.get("id") not in set(removed)]
        inputs = True
    leave, use = fields.get("exclude_references", []), fields.get("include_references", [])
    for ref in [*leave, *use]:
        if ref not in inherited:
            raise EditError("reference_not_found", f"The project has no reference {ref!r} every shot inherits.")
    if leave or use:
        before = edits.excluded(clip)
        after = [ref for ref in before if ref not in use] + [ref for ref in leave if ref not in before]
        if sorted(after) != sorted(before):
            edits.set_excluded(clip, after)
            inputs = True
    if inputs:
        changed.append("references")
    return inputs


EngineMax = Callable[[Mapping[str, Any], Mapping[str, Any]], Optional[float]]


def _no_engine_max(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[float]:
    return None


def engine_max(context: ToolContext) -> EngineMax:
    """The longest take the engine of a shot makes, read once per preset from the presets the caller may run."""
    user = core_bridge.get_user(context.user_id)
    found: Dict[str, Optional[float]] = {}

    def maximum(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[float]:
        engine = doc.get("engine") if isinstance(doc.get("engine"), dict) else {}
        preset_id = director.shot_engine(doc, clip["id"]).get("preset") or engine.get("preset")
        if user is None or not isinstance(preset_id, str) or not preset_id:
            return None
        if preset_id not in found:
            preset = director.find_preset(user, preset_id)
            value = preset.limits.get("max_duration") if preset else None
            found[preset_id] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None
        return found[preset_id]

    return maximum


def update_shot(doc: Dict[str, Any], fields: Mapping[str, Any], longest: EngineMax = _no_engine_max) -> Dict[str, Any]:
    """Apply one shot's update as the page does, counting an edit of its inputs when its length, frames, references or cast change, and keeping its length within what its media and its engine allow."""
    clip = edits.find_shot(doc, fields["shot"])
    changed: List[str] = []
    inputs = False
    released = None
    limited = None
    if "label" in fields and fields["label"] != clip.get("label"):
        clip["label"] = fields["label"]
        changed.append("label")
    if "duration_s" in fields:
        maximum, by = edits.duration_limit(doc, clip, longest(doc, clip))
        if fields["duration_s"] > max(edits.MIN_SHOT_S, maximum) + 1e-6:
            limited = {"max_s": round(max(edits.MIN_SHOT_S, maximum), 2), "by": by}
        resized, released = edits.resize(doc, clip, fields["duration_s"], maximum)
        if resized:
            edits.relayout(doc)
            changed.append("duration_s")
            inputs = True
    if "characters" in fields or "place" in fields:
        characters, place = _cast_ids(doc, fields.get("characters"), fields.get("place", ...))
        before = json.dumps(clip.get("cast"), sort_keys=True)
        edits.set_cast(clip, characters, place)
        if json.dumps(clip.get("cast"), sort_keys=True) != before:
            changed.append("cast")
            inputs = True
    for kind, name in ((edits.FIRST, "first_frame"), (edits.LAST, "last_frame")):
        if name not in fields:
            continue
        asset_id = edits.find_asset(doc, fields[name])["id"] if fields[name] else None
        if asset_id != edits.frame_asset(doc, clip, kind):
            edits.place_frame(doc, clip, kind, asset_id)
            changed.append(name)
            inputs = True
    inputs = _references(doc, clip, fields, changed) or inputs
    if "takes_per_run" in fields and clip.get("drafts") != fields["takes_per_run"]:
        clip["drafts"] = fields["takes_per_run"]
        changed.append("takes_per_run")
    if "position" in fields and edits.move_shot(doc, clip, fields["position"] - 1):
        changed.append("position")
    if "chain" in fields and edits.set_chain(doc, clip, fields["chain"]):
        changed.append("chain")
    if inputs:
        edits.touch(clip, doc)
    return {"shot_id": clip["id"], "changed": changed, **({"released_take": released} if released else {}), **({"duration_limit": limited} if limited else {})}


def _release_labels(released: Sequence[str]) -> None:
    for take_id in released:
        take = takes.get_take(take_id)
        if take is not None and take.get("label") in (takes.FINAL, takes.CANDIDATE):
            takes.set_label(take_id, takes.DRAFT)


def _order(doc: Mapping[str, Any], shot_ids: List[str], quality: Optional[str], per_shot: Optional[int]) -> estimate.Order:
    engine = doc.get("engine") if isinstance(doc.get("engine"), dict) else {}
    preset_id = engine.get("preset")
    if not isinstance(preset_id, str) or not preset_id:
        raise ToolFailure("no_engine", "The project has no engine: choose one in the Production bar first.")
    variants = per_shot or (engine["variants"] if isinstance(engine.get("variants"), int) and 1 <= engine["variants"] <= MAX_TAKES_PER_SHOT else 1)
    counts = {}
    if per_shot is None:
        for clip in edits.clips_of(doc):
            drafts = clip.get("drafts")
            if clip["id"] in shot_ids and isinstance(drafts, int) and drafts != variants:
                counts[clip["id"]] = min(max(drafts, 1), MAX_TAKES_PER_SHOT)
    model_id = engine.get("model") if isinstance(engine.get("model"), str) and engine.get("model") else None
    return estimate.Order(
        shots=shot_ids,
        quality=quality or (engine.get("quality") if engine.get("quality") in QUALITIES else "draft"),
        variants=variants,
        preset_id=preset_id,
        model_id=model_id,
        shot_variants=counts,
    )


def _generate_arguments(doc: Mapping[str, Any], arguments: Mapping[str, Any]) -> Tuple[List[str], Optional[str], Optional[int]]:
    try:
        shot_ids = list(dict.fromkeys(edits.find_shot(doc, ref)["id"] for ref in _list(arguments.get("shots"), "shots")))
    except EditError as error:
        raise _edit(error) from None
    quality = arguments.get("quality")
    if quality is not None and quality not in QUALITIES:
        raise _invalid(f"quality must be one of: {', '.join(QUALITIES)}.")
    per_shot = arguments.get("takes_per_shot")
    return shot_ids, quality, None if per_shot is None else _count(per_shot, "takes_per_shot")


async def evaluate_order(context: ToolContext, arguments: Mapping[str, Any]) -> Tuple[Dict[str, Any], core_bridge.User, estimate.Order, estimate.Evaluation]:
    """The project, its owner, the order and its estimate for a vp_generate call; blocked when anything would stop the takes."""
    project = load_project(context)
    caller, owner = _owner(context, project)
    order = _order(project["doc"], *_generate_arguments(project["doc"], arguments))
    evaluation = await estimate.evaluate(caller, owner, project["doc"], order, project["id"])
    if evaluation.blocked:
        raise ToolFailure("blocked", " ".join(block["message"] for block in evaluation.payload["blocks"]))
    return project, owner, order, evaluation


def _cost_usd(evaluation: estimate.Evaluation) -> Optional[float]:
    total = (evaluation.payload.get("cost") or {}).get("total_usd")
    return float(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else None


def _take_count(evaluation: estimate.Evaluation) -> int:
    return sum(evaluation.count(plan.shot_id) for plan in evaluation.plans.shots)


def _generation_card(doc: Mapping[str, Any], order: estimate.Order, evaluation: estimate.Evaluation) -> Dict[str, Any]:
    return {
        "shots": list(order.shots),
        "names": [edits.shot_name(doc, edits.find_shot(doc, shot_id), "en") for shot_id in order.shots],
        "quality": order.quality,
        "variants": order.variants,
        "shot_variants": dict(order.shot_variants),
        "preset_id": order.preset_id,
        "model_id": order.model_id,
        "presets": {plan.shot_id: plan.preset_id for plan in evaluation.plans.shots},
        "takes": _take_count(evaluation),
        "gpu_minutes": evaluation.payload["quota"]["needed_minutes"],
        "cost_usd": _cost_usd(evaluation),
    }


def _generation_shown(doc: Mapping[str, Any], card: Mapping[str, Any], evaluation: estimate.Evaluation) -> Dict[str, Any]:
    durations = {clip["id"]: _seconds(clip.get("dur")) for clip in edits.clips_of(doc)}
    return {
        "shots": [{"id": shot_id, "duration_s": durations.get(shot_id), "takes": evaluation.count(shot_id)} for shot_id in card["shots"]],
        "quality": card["quality"],
        "engine": card["preset_id"],
        "model": card["model_id"],
        "presets": card["presets"],
    }


def _generation_preview(doc: Mapping[str, Any], order: estimate.Order, evaluation: estimate.Evaluation) -> Tuple[ToolApprovalPreview, Dict[str, Any], Dict[str, Any]]:
    payload = evaluation.payload
    card = _generation_card(doc, order, evaluation)
    names = card["names"]
    count = card["takes"]
    quota = payload["quota"]
    minutes = f"{quota['needed_minutes']:g}"
    if quota.get("limit") is not None and not quota.get("exempt") and quota.get("remaining") is not None:
        minutes += f" of {float(quota['remaining']):g} left this month"
    seconds = payload["time"]["seconds"]
    fields = [
        {"label": "Shots", "value": ", ".join(names)},
        {"label": "Takes", "value": str(count)},
        {"label": "Quality", "value": order.quality},
        {"label": "Engine", "value": order.preset_id + (f" · {order.model_id}" if order.model_id else ""), "mono": True},
        {"label": "GPU minutes", "value": minutes},
        {"label": "Time", "value": f"about {round(seconds / 60, 1):g} min" if seconds else "not measured yet"},
    ]
    cost = payload.get("cost")
    if cost and cost.get("total_usd") is not None:
        fields.append({"label": "Cost", "value": f"${cost['total_usd']}"})
    warnings = [warning["message"] for warning in payload["warnings"] if warning.get("message")]
    summary = f"Generate {_plural(count, 'take')} for {_plural(len(names), 'shot')}"
    preview = ToolApprovalPreview(
        action="Generate takes",
        target=_plural(len(names), "shot"),
        kind="generation",
        summary=summary,
        fields=fields,
        note=" ".join(warnings) or None,
        changes=[{"op": "generate", "summary": summary, "before": _generation_shown(doc, card, evaluation), "after": None}],
    )
    data = {"shots": order.shots, "takes": count, "quality": order.quality, "gpu_minutes": quota["needed_minutes"], "warnings": warnings}
    return preview, data, card


def _unknown_card() -> ToolFailure:
    return ToolFailure(
        CARD_EXPIRED,
        f"The server no longer has the card that was approved: it restarted, the card is more than a week old, or more than {cards.MAX_CARDS_PER_USER} newer cards of yours were shown since. Nothing ran; ask again to show a new card.",
    )


def approved_card(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
    """The card an approval runs: the one its turn showed, the refusal it already met, or card_expired when the server no longer has it."""
    card = cards.shown(context, tool, arguments)
    if card is None:
        raise _unknown_card()
    refused = card.get(cards.REFUSED)
    if refused:
        raise ToolFailure(refused["code"], refused["message"])
    return card


def _refused(context: ToolContext, tool: str, arguments: Mapping[str, Any], failure: ToolFailure) -> ToolResult:
    if failure.code == CARD_OUT_OF_DATE:
        cards.refuse(context, tool, arguments, failure)
    return failure.result()


def _out_of_date(what: str) -> ToolFailure:
    return ToolFailure(CARD_OUT_OF_DATE, f"{what} since the card was shown, so nothing ran. Read the project and ask again to show a new card.")


def _missing(names: Sequence[str]) -> str:
    return f"{', '.join(names)} no longer exist{'s' if len(names) == 1 else ''}"


def _within_card(card: Mapping[str, Any], evaluation: estimate.Evaluation) -> None:
    if {plan.shot_id: plan.preset_id for plan in evaluation.plans.shots} != card["presets"]:
        raise _out_of_date("The engine of a shot changed")
    count = _take_count(evaluation)
    minutes = evaluation.payload["quota"]["needed_minutes"]
    cost = _cost_usd(evaluation)
    dearer = cost is not None and (card["cost_usd"] is None or cost > card["cost_usd"] + 1e-9)
    if count > card["takes"] or minutes > card["gpu_minutes"] + 1e-9 or dearer:
        shown = f"{_plural(card['takes'], 'take')} and {card['gpu_minutes']:g} GPU minutes"
        raise _out_of_date(f"The estimate rose to {_plural(count, 'take')} and {minutes:g} GPU minutes from the {shown} on the card")


async def generate_shown(context: ToolContext, card: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Start the takes an approved card showed: the same shots by id, quality, numbers of takes and engine, refused when a shot is gone or the estimate rose."""
    project = load_project(context)
    caller, owner = _owner(context, project)
    doc = project["doc"]
    present = {clip["id"] for clip in edits.clips_of(doc)}
    gone = [name for shot_id, name in zip(card["shots"], card["names"]) if shot_id not in present]
    if gone:
        raise _out_of_date(_missing(gone))
    order = estimate.Order(
        shots=list(card["shots"]),
        quality=card["quality"],
        variants=card["variants"],
        preset_id=card["preset_id"],
        model_id=card["model_id"],
        shot_variants=dict(card["shot_variants"]),
    )
    evaluation = await estimate.evaluate(caller, owner, doc, order, project["id"])
    if evaluation.blocked:
        raise ToolFailure("blocked", " ".join(block["message"] for block in evaluation.payload["blocks"]))
    _within_card(card, evaluation)
    try:
        created = await generation.start(owner, project, evaluation)
    except Blocked as exc:
        raise ToolFailure("blocked", str(exc) or "The takes cannot start.") from None
    return project, created


def _find_take(project: Mapping[str, Any], arguments: Mapping[str, Any]) -> Dict[str, Any]:
    take_id = arguments.get("take_id")
    if isinstance(take_id, str) and take_id.strip():
        take = takes.get_take(take_id.strip())
        if take is None or take["project_id"] != project["id"] or take.get("kind") == takes.KEYFRAME:
            raise ToolFailure("take_not_found", f"The project has no take {take_id.strip()!r}.")
        return take
    shot, variant = arguments.get("shot"), arguments.get("variant")
    if not isinstance(variant, str) or not variant.strip():
        raise _invalid("Pass take_id, or shot and variant.")
    try:
        clip = edits.find_shot(project["doc"], shot)
    except EditError as error:
        raise _edit(error) from None
    found = [take for take in takes.list_takes(project["id"]) if take["shot_id"] == clip["id"] and str(take.get("variant") or "").upper() == variant.strip().upper()]
    if not found:
        raise ToolFailure("take_not_found", f"The shot has no take {variant.strip().upper()}.")
    if len(found) > 1:
        listed = ", ".join(f"{take['id']} ({take.get('quality')})" for take in found)
        raise ToolFailure("ambiguous_take", f"Several takes of the shot are {variant.strip().upper()}: {listed}. Pass take_id.")
    return found[0]


def label_take(context: ToolContext, arguments: Mapping[str, Any]) -> Dict[str, Any]:
    """Label a take; a final take is also placed on its shot, as the page does."""
    label = arguments.get("label")
    if label not in LABELS:
        raise _invalid(f"label must be one of: {', '.join(LABELS)}.")
    project = load_project(context)
    take = _find_take(project, arguments)
    shown = takes.public(take)
    result: Dict[str, Any] = {"project_id": project["id"], "take_id": take["id"], "shot_id": take["shot_id"], "variant": take.get("variant"), "label": label}
    if label != takes.FINAL:
        if take.get("label") == takes.FINAL and label != takes.FINAL:
            raise ToolFailure("take_is_final", "A final take stays final until another take of its shot is made final.")
        takes.set_label(take["id"], label)
        return result
    if take.get("status") != "done" or not shown.get("url"):
        raise ToolFailure("take_not_done", "Only a finished take can be final.")
    language = _language(context)

    def place(doc: Dict[str, Any]) -> bool:
        clip = next((item for item in edits.clips_of(doc) if item.get("id") == take["shot_id"]), None)
        return clip is not None and edits.place_take(doc, clip, shown, language)

    placed_project, placed, version = _changed(context, place)
    takes.set_label(take["id"], takes.FINAL)
    return {**result, "placed": placed, "version": version}


def assemble(context: ToolContext) -> Dict[str, Any]:
    """Put every final take on its shot, as the page's Assemble does."""
    project = load_project(context)
    finals = [takes.public(take) for take in takes.list_takes(project["id"]) if take.get("label") == takes.FINAL and take.get("status") == "done"]
    language = _language(context)

    def place(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        placed = []
        for take in finals:
            clip = next((item for item in edits.clips_of(doc) if item.get("id") == take["shot_id"]), None)
            if clip is not None and take.get("url"):
                edits.place_take(doc, clip, take, language)
                placed.append({"shot_id": clip["id"], "variant": take.get("variant")})
        return placed

    _, placed, version = _changed(context, place)
    project = load_project(context)
    covered = {item["shot_id"] for item in placed}
    missing = [_shot_entry(project["doc"], clip)["label"] for clip in edits.clips_of(project["doc"]) if clip["id"] not in covered and clip.get("stage") != "source"]
    return {"project_id": project["id"], "version": version, "placed": placed, "without_final": missing}


def production_status(context: ToolContext) -> Dict[str, Any]:
    """The takes in flight with their place in the queue, the generation slots, the GPU minutes left and the latest exports."""
    project = load_project(context)
    owner_id = project["user_id"]
    waiting = [take["id"] for take in takes.waiting(owner_id)]
    places = {take_id: index + 1 for index, take_id in enumerate(waiting)}
    names = {clip["id"]: edits.shot_name(project["doc"], clip, "en") for clip in edits.clips_of(project["doc"])}
    queue = []
    for take in takes.list_active(project["id"]):
        if take.get("kind") == takes.KEYFRAME:
            continue
        entry = {**_take_entry(take), "shot": names.get(take["shot_id"], take["shot_id"])}
        if take.get("chain_wait"):
            entry["waits_for_previous_shot"] = True
        elif places.get(take["id"]):
            entry["queue_position"] = places[take["id"]]
        queue.append(entry)
    quota = limits.gpu_minutes_status(owner_id)
    exports = [jobs.public(job) for job in jobs.list_project(project["id"])[:MAX_EXPORTS]]
    return {
        "project_id": project["id"],
        "queue": queue,
        "slots": {"in_flight": takes.in_flight(owner_id), "max": settings.get_setting("max_parallel_jobs")},
        "gpu_minutes": {key: quota.get(key) for key in ("used", "limit", "remaining")},
        "exports": [{key: job[key] for key in ("id", "status", "format", "resolution", "progress")} | ({"error": job["error"]["message"]} if job.get("error") else {}) for job in exports],
    }


class _ProductionTool(_VideoProducerTool):
    context_group = PRODUCTION


class ReadProjectTool(_VideoProducerTool):
    """Read the open project in detail: shots, prompts, cast, references, frames and takes."""

    icon = "file-search"

    @property
    def name(self) -> str:
        return "vp_get_project"

    @property
    def label(self) -> str:
        return "Read project"

    @property
    def user_description(self) -> str:
        return "Reads your Video Producer project in detail, with the takes of each shot."

    @property
    def hint(self) -> str:
        return "Read the full prompts, takes, references, frames and media before you change or generate them."

    @property
    def description(self) -> str:
        return (
            "Read the Video Producer project open on the page: engine, bible cards, media you can use as frames or "
            "references, and for each shot its id, number, label, timing, stage, full prompt, cast, first and last "
            "frame, references (own or inherited, excluded or not) and latest takes (id, variant, quality, status, "
            "label). Read-only."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"shots": {"type": "array", "items": REF_SCHEMA, "description": "Shots to detail; omit for every shot"}},
            "required": [],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            refs = None if kwargs.get("shots") in (None, [], "") else _list(kwargs.get("shots"), "shots", 200)
            return _ok(read_project(context, refs))
        except EditError as error:
            return _edit(error).result()
        except ToolFailure as failure:
            return failure.result()


class AddShotsTool(_VideoProducerTool):
    """Add shots to the open project at once; the page shows them and Ctrl+Z takes them back."""

    icon = "list-plus"

    @property
    def name(self) -> str:
        return "vp_add_shots"

    @property
    def label(self) -> str:
        return "Add shots"

    @property
    def user_description(self) -> str:
        return "Adds shots to your Video Producer project, with their prompt and cast."

    @property
    def hint(self) -> str:
        return "Add shots now when the user asks for them; vp_split_synopsis only proposes a cut to review."

    @property
    def description(self) -> str:
        return (
            f"Add 1 to {MAX_SHOTS} shots to the project open on the page, in order, after a shot, at the start or at the "
            f"end. Each shot has a label (at most {MAX_LABEL_CHARS} characters), a duration ({MIN_DURATION_S} to "
            f"{MAX_DURATION_S} s), a prompt in the project's prompt language, and optionally the bible characters and "
            "place it casts, by label. Saved at once: the page shows the shots and the user can undo with Ctrl+Z."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shots": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_SHOTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": LABEL_SCHEMA,
                            "duration_s": DURATION_SCHEMA,
                            "prompt": {"type": "string"},
                            "characters": CHARACTERS_SCHEMA,
                            "place": PLACE_SCHEMA,
                        },
                        "required": ["label", "duration_s", "prompt"],
                    },
                },
                "after": {"type": "string", "description": "Shot to insert after, or \"start\"; omit to add at the end"},
            },
            "required": ["shots"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            shots = _add_arguments(kwargs)
            project, added, version = _changed(context, lambda doc: add_shots(doc, shots, kwargs.get("after")))
        except ToolFailure as failure:
            return failure.result()
        return _ok({"project_id": project["id"], "version": version, "added": added})


class UpdateShotsTool(_VideoProducerTool):
    """Change shots of the open project at once; the page shows the change and Ctrl+Z takes it back."""

    icon = "pencil"

    @property
    def name(self) -> str:
        return "vp_update_shots"

    @property
    def label(self) -> str:
        return "Update shots"

    @property
    def user_description(self) -> str:
        return "Changes the label, length, order, cast, frames or references of shots of your Video Producer project."

    @property
    def hint(self) -> str:
        return "Change, reorder, cast or attach media to shots; give only the fields that change."

    @property
    def description(self) -> str:
        return (
            "Change one or more shots of the project open on the page. Per shot, give only what changes: label, "
            "duration_s, position (1 = first; moves the shot), characters and place (bible labels), first_frame and "
            "last_frame (media id or name, empty removes), add_references ({media, space: identity|set|motion|sound}), "
            "remove_references (ids of the shot's own references), exclude_references / include_references (ids of "
            "inherited references), takes_per_run (1 to 8), chain (start from the previous shot's last image). Prompts "
            "are written with vp_write_shot_prompt. Saved at once; Ctrl+Z on the page undoes it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        ids = {"type": "array", "items": {"type": "string"}}
        return {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_SHOTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "shot": REF_SCHEMA,
                            "label": LABEL_SCHEMA,
                            "duration_s": DURATION_SCHEMA,
                            "position": {"type": "integer", "minimum": 1},
                            "characters": CHARACTERS_SCHEMA,
                            "place": PLACE_SCHEMA,
                            "first_frame": {"type": "string"},
                            "last_frame": {"type": "string"},
                            "add_references": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"media": {"type": "string"}, "space": {"type": "string", "enum": list(edits.SPACES)}},
                                    "required": ["media"],
                                },
                            },
                            "remove_references": ids,
                            "exclude_references": ids,
                            "include_references": ids,
                            "takes_per_run": {"type": "integer", "minimum": 1, "maximum": MAX_TAKES_PER_SHOT},
                            "chain": {"type": "boolean"},
                        },
                        "required": ["shot"],
                    },
                }
            },
            "required": ["updates"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            updates = _update_arguments(kwargs)
            longest = engine_max(context)
            project, changes, version = _changed(context, lambda doc: [update_shot(doc, fields, longest) for fields in updates])
        except ToolFailure as failure:
            return failure.result()
        _release_labels([change["released_take"] for change in changes if change.get("released_take")])
        return _ok({"project_id": project["id"], "version": version, "updated": changes})


class DeleteShotsTool(_VideoProducerTool):
    """Delete shots of the open project, after the user approves it."""

    icon = "trash-2"

    @property
    def name(self) -> str:
        return "vp_delete_shots"

    @property
    def label(self) -> str:
        return "Delete shots"

    @property
    def user_description(self) -> str:
        return "Deletes shots of your Video Producer project, with their prompts and frames, once you approve."

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "Delete shots only when the user asks; they approve the list first."

    @property
    def description(self) -> str:
        return (
            "Delete shots of the project open on the page with their prompts, frames and own references; the shots "
            "after them move up. Their takes stay in the project. The user sees the list and nothing is deleted until "
            "they approve; Ctrl+Z on the page brings the shots back."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"shots": SHOTS_SCHEMA}, "required": ["shots"]}

    @staticmethod
    def _targets(doc: Mapping[str, Any], kwargs: Mapping[str, Any]) -> List[Dict[str, Any]]:
        try:
            found = [edits.find_shot(doc, ref) for ref in _list(kwargs.get("shots"), "shots", 200)]
        except EditError as error:
            raise _edit(error) from None
        return list({clip["id"]: clip for clip in found}.values())

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            cards.turn_of(context)
            project = load_project(context)
            targets = self._targets(project["doc"], kwargs)
        except ToolFailure as failure:
            return failure.result()
        doc = project["doc"]
        rows = [
            {
                "range": f"{_seconds(clip.get('start')):g}–{_seconds(edits.number(clip.get('start')) + edits.number(clip.get('dur'))):g} s",
                "text": f"{edits.shot_name(doc, clip, 'en')}: {_head(instruction_of(doc, clip)) or 'no prompt'}",
                "op": "remove",
            }
            for clip in targets
        ]
        count = _plural(len(targets), "shot")
        preview = ToolApprovalPreview(
            action="Delete shots",
            target=count,
            kind="timeline",
            summary=f"Delete {count}",
            rows=rows,
            note="Their prompts, frames and own references go with them; their takes stay in the project. Ctrl+Z on the page brings them back.",
            changes=[
                {"op": "remove", "summary": edits.shot_name(doc, clip, "en"), "before": {**_shot_entry(doc, clip), "prompt": _head(instruction_of(doc, clip))}, "after": None}
                for clip in targets
            ],
        )
        shown = [{"id": clip["id"], "name": edits.shot_name(doc, clip, "en")} for clip in targets]
        cards.keep(context, self.name, kwargs, {"project_id": project["id"], "shots": shown})
        return _ok({"status": "pending_approval", "project_id": project["id"], "shots": [clip["id"] for clip in targets]}, preview)

    async def execute_confirmed(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            card = approved_card(context, self.name, kwargs)
        except ToolFailure as failure:
            return failure.result()

        def delete(doc: Dict[str, Any]) -> List[str]:
            present = {clip["id"] for clip in edits.clips_of(doc)}
            gone = [shot["name"] for shot in card["shots"] if shot["id"] not in present]
            if gone:
                raise _out_of_date(_missing(gone))
            ids = [shot["id"] for shot in card["shots"]]
            edits.delete_shots(doc, ids)
            return ids

        try:
            project, deleted, version = _changed(context, delete)
        except ToolFailure as failure:
            return _refused(context, self.name, kwargs, failure)
        cards.forget(context, self.name, kwargs)
        return _ok({"project_id": project["id"], "version": version, "deleted": deleted})


class GenerateTool(_ProductionTool):
    """Start takes of shots on the project's engine, after the user approves the estimate."""

    icon = "clapperboard"

    @property
    def name(self) -> str:
        return "vp_generate"

    @property
    def label(self) -> str:
        return "Generate takes"

    @property
    def user_description(self) -> str:
        return "Starts takes of shots of your Video Producer project once you approve the GPU minutes they cost."

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return "Generate takes of shots on the project's engine; the user approves the GPU minutes first."

    @property
    def description(self) -> str:
        return (
            "Start takes of one or more shots on the engine chosen in the Production bar, in draft or final quality, "
            f"with each shot's own number of takes unless takes_per_shot (1 to {MAX_TAKES_PER_SHOT}) is given. The user "
            "sees the estimate (takes, GPU minutes, time) and nothing starts until they approve. Answers blocked with "
            "the reason when the takes cannot start. Follow them with vp_status."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shots": SHOTS_SCHEMA,
                "quality": {"type": "string", "enum": list(QUALITIES)},
                "takes_per_shot": {"type": "integer", "minimum": 1, "maximum": MAX_TAKES_PER_SHOT},
            },
            "required": ["shots"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            cards.turn_of(context)
            project, _, order, evaluation = await evaluate_order(context, kwargs)
        except ToolFailure as failure:
            return failure.result()
        preview, data, card = _generation_preview(project["doc"], order, evaluation)
        cards.keep(context, self.name, kwargs, card)
        return _ok({"status": "pending_approval", "project_id": project["id"], **data}, preview)

    async def execute_confirmed(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            card = approved_card(context, self.name, kwargs)
        except ToolFailure as failure:
            return failure.result()
        try:
            project, created = await generate_shown(context, card)
        except ToolFailure as failure:
            return _refused(context, self.name, kwargs, failure)
        cards.forget(context, self.name, kwargs)
        tracker.ensure_running()
        return _ok({"project_id": project["id"], "takes": [{**_take_entry(take), "shot_id": take["shot_id"]} for take in created]})


class StatusTool(_ProductionTool):
    """Report the queue, the GPU minutes left and the latest exports. Read-only."""

    icon = "list-checks"

    @property
    def name(self) -> str:
        return "vp_status"

    @property
    def label(self) -> str:
        return "Production status"

    @property
    def user_description(self) -> str:
        return "Reports the takes in progress, the GPU minutes left and the latest exports of your Video Producer project."

    @property
    def hint(self) -> str:
        return "Check the takes in flight and the exports."

    @property
    def description(self) -> str:
        return (
            "Report the production of the project open on the page: the takes queued or running (shot, variant, "
            "progress, place in the queue, or waiting for the previous shot), the generation slots in use, the GPU "
            "minutes used and left this month, and the latest video exports. Read-only; finished takes are in "
            "vp_get_project."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            return _ok(production_status(context))
        except ToolFailure as failure:
            return failure.result()


class LabelTakeTool(_ProductionTool):
    """Label a take; Final also puts it on its shot."""

    icon = "tag"

    @property
    def name(self) -> str:
        return "vp_label_take"

    @property
    def label(self) -> str:
        return "Label take"

    @property
    def user_description(self) -> str:
        return "Labels a take of your Video Producer project draft, rejected, candidate or final."

    @property
    def hint(self) -> str:
        return "Label a take; final puts it on its shot."

    @property
    def description(self) -> str:
        return (
            "Label one take draft, rejected, candidate or final. Name it by take_id, or by shot and variant (the letter "
            "of the take). Final needs a finished take: it becomes the only final take of its shot and is put on the "
            "shot in the edit; Ctrl+Z on the page takes it off. A final take stays final until another take of its "
            "shot is made final."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "take_id": {"type": "string"},
                "shot": REF_SCHEMA,
                "variant": {"type": "string", "description": "The take's letter, such as A"},
                "label": {"type": "string", "enum": list(LABELS)},
            },
            "required": ["label"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            return _ok(label_take(context, kwargs))
        except ToolFailure as failure:
            return failure.result()


class AssembleTool(_ProductionTool):
    """Put every final take on its shot."""

    icon = "layers"

    @property
    def name(self) -> str:
        return "vp_assemble"

    @property
    def label(self) -> str:
        return "Assemble"

    @property
    def user_description(self) -> str:
        return "Puts the final take of every shot of your Video Producer project in the edit."

    @property
    def hint(self) -> str:
        return "Put every final take in the edit before an export."

    @property
    def description(self) -> str:
        return (
            "Put the final take of every shot that has one on that shot in the edit, as the page's Assemble does, and "
            "list the shots without a final take. Saved at once; Ctrl+Z on the page undoes it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            return _ok(assemble(context))
        except ToolFailure as failure:
            return failure.result()


class ExportVideoTool(_ProductionTool):
    """Queue the MP4 export of the edit."""

    icon = "download"

    @property
    def name(self) -> str:
        return "vp_export_video"

    @property
    def label(self) -> str:
        return "Export video"

    @property
    def user_description(self) -> str:
        return "Starts the MP4 export of your Video Producer edit."

    @property
    def hint(self) -> str:
        return "Export the edit to an MP4 once its shots have takes."

    @property
    def description(self) -> str:
        return (
            "Queue the assembly of the edit open on the page into a video: web (H.264 MP4) keeps the project's aspect, "
            "social (H.264 MP4) is 9:16, master is ProRes 422 HQ in a MOV and archive H.265 in an MP4, both in the "
            "project's aspect. stems also writes one WAV per role and one for the shots' sound, packed with the video "
            "in a ZIP. The resolution defaults to the project's. It runs on the server's CPU, not the GPU; follow it "
            "with vp_status and download it from the page's Export window."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": list(video.FORMATS)},
                "resolution": {"type": "string", "enum": list(video.RESOLUTIONS)},
                "stems": {"type": "boolean"},
            },
            "required": [],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            project = load_project(context)
            job = queue_video(
                _user(context.user_id), project["id"], kwargs.get("format") or video.FORMATS[0], kwargs.get("resolution") or None, kwargs.get("stems") is True
            )
        except ToolFailure as failure:
            return failure.result()
        except HTTPException as error:
            return _http(error).result()
        shown = jobs.public(job)
        return _ok(
            {"project_id": project["id"], "job_id": shown["id"], "status": shown["status"], "format": shown["format"], "resolution": shown["resolution"], "stems": shown["stems"]}
        )
