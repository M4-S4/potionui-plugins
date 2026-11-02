import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import bible, formats
from ..core_bridge import generate_ulid
from ..director import FIRST_ROLES, LAST_ROLES, shot_revision

GRID = 0.04
PROMPT_STRENGTH = 75
FRAME_STRENGTH = 100
MIN_SHOT_S = 0.4
SHOT_CAP_S = 60.0
TAKE_SLACK = 0.05
FIRST, LAST = "first", "last"
LINKED = ("prompts", "frames")

SPACES = {"identity": "identite", "set": "decors3d", "motion": "mouvement", "sound": "son"}
SPACE_ROLES = {"identite": "Identité", "decors3d": "Décor", "mouvement": "Mouvement", "son": "Son"}
SPACE_TYPES = {
    "identite": (("Personnage", "image"), ("Décor", "image"), ("Objet", "image"), ("Style", "image")),
    "decors3d": (("Capture 3D", "image"),),
    "mouvement": (("Control video", "video"), ("Trajectoire", "video")),
    "son": (("Voix", "audio"), ("Musique", "audio"), ("Ambiance", "audio")),
}

TAKE_NAMES = {
    "en": {"final": "{shot} · Final {variant}", "draft": "{shot} · Draft {variant}"},
    "fr": {"final": "{shot} · Final {variant}", "draft": "{shot} · Brouillon {variant}"},
}
SHOT_NAMES = {"en": "Shot", "fr": "Plan"}


class EditError(ValueError):
    """A change the document refuses, with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def snap(value: float, step: float = GRID) -> float:
    """A time on the page's grid, rounded the way the page rounds it."""
    return float(f"{math.floor(value / step + 0.5) * step:.3f}")


def dicts(value: Any) -> List[Dict[str, Any]]:
    """The objects of a list, or an empty list."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def number(value: Any) -> float:
    """A JSON number as a float, 0 for anything else."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def clips_of(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The shots of the document, in timeline order."""
    return dicts(doc.get("clips"))


def new_clip(label: str, duration: float) -> Dict[str, Any]:
    """A shot to generate, shaped like the page's new shots."""
    return {
        "id": generate_ulid(),
        "assetId": None,
        "start": 0,
        "dur": duration,
        "srcIn": 0,
        "label": label,
        "stage": "todo",
        "take": None,
        "fadeIn": 0,
        "fadeOut": 0,
        "exposure": 0,
        "contrast": 100,
        "saturation": 100,
        "temperature": 0,
        "preset": "Original",
        "flag": None,
        "mute": False,
    }


def new_prompt(clip: Mapping[str, Any], text: str) -> Dict[str, Any]:
    """The prompt of a shot, covering it."""
    return {"id": generate_ulid(), "shotId": clip["id"], "start": clip["start"], "dur": clip["dur"], "strength": PROMPT_STRENGTH, "text": text}


def touch(clip: Dict[str, Any], doc: Mapping[str, Any]) -> None:
    """Count one more edit of the shot's inputs, so its takes read as made from an older shot."""
    clip["revision"] = shot_revision(doc, clip["id"]) + 1


def _linked(doc: Mapping[str, Any], shot_id: Any) -> List[Dict[str, Any]]:
    return [item for key in LINKED for item in dicts(doc.get(key)) if item.get("shotId") == shot_id]


def relayout(doc: Dict[str, Any]) -> None:
    """Lay the shots end to end from zero, moving the prompts and frames linked to each shot with it."""
    clips = clips_of(doc)
    before = {clip["id"]: number(clip.get("start")) for clip in clips}
    at = 0.0
    for clip in clips:
        clip["start"] = snap(at)
        at += number(clip.get("dur"))
    for clip in clips:
        delta = clip["start"] - before.get(clip["id"], clip["start"])
        if abs(delta) <= 1e-6:
            continue
        for item in _linked(doc, clip["id"]):
            key = "time" if "time" in item else "start"
            item[key] = snap(number(item.get(key)) + delta)


def _folded(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def find_shot(doc: Mapping[str, Any], ref: Any) -> Dict[str, Any]:
    """The shot a reference names: its id, its position from 1, or its exact label."""
    clips = clips_of(doc)
    if isinstance(ref, bool) or not isinstance(ref, (str, int)):
        raise EditError("shot_not_found", "Name a shot by its id from the context, its number or its label.")
    text = str(ref).strip()
    found = next((clip for clip in clips if clip.get("id") == text), None)
    if found is None and text.isdigit() and 1 <= int(text) <= len(clips):
        found = clips[int(text) - 1]
    if found is None:
        named = [clip for clip in clips if text and _folded(clip.get("label")) == _folded(text)]
        found = named[0] if len(named) == 1 else None
    if found is None:
        raise EditError("shot_not_found", f"The project has no shot {text!r}.")
    return found


def index_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> int:
    """The position of a shot in the timeline, from 0."""
    return next(index for index, item in enumerate(clips_of(doc)) if item.get("id") == clip.get("id"))


def find_card(doc: Mapping[str, Any], kind: str, ref: Any) -> bible.Card:
    """The bible card of a kind that a reference names: its id or its label."""
    text = str(ref).strip() if isinstance(ref, str) else ""
    found = next((card for card in bible.cards(doc, kind) if card.id == text or _folded(card.label) == _folded(text)), None)
    if found is None:
        what = "character" if kind == bible.CHARACTERS else "place"
        raise EditError("card_not_found", f"The bible has no {what} {text!r}.")
    return found


def find_asset(doc: Mapping[str, Any], ref: Any) -> Dict[str, Any]:
    """The media of the project a reference names: its id or its exact name."""
    text = str(ref).strip() if isinstance(ref, str) else ""
    assets = dicts(doc.get("assets"))
    found = next((item for item in assets if item.get("id") == text), None)
    if found is None:
        named = [item for item in assets if text and _folded(item.get("name")) == _folded(text)]
        found = named[0] if len(named) == 1 else None
    if found is None:
        raise EditError("media_not_found", f"The project has no media {text!r}.")
    return found


def add_shots(doc: Dict[str, Any], shots: Sequence[Mapping[str, Any]], index: int) -> List[Dict[str, Any]]:
    """Insert new shots at a position of the timeline, each with its prompt and cast, and lay the timeline out again."""
    added = []
    for offset, shot in enumerate(shots):
        clip = new_clip(shot["label"], shot["duration"])
        if shot.get("cast"):
            clip["cast"] = shot["cast"]
        doc.setdefault("clips", []).insert(index + offset, clip)
        added.append((clip, shot.get("prompt") or ""))
    relayout(doc)
    for clip, text in added:
        if text:
            doc.setdefault("prompts", []).append(new_prompt(clip, text))
    return [clip for clip, _ in added]


def move_shot(doc: Dict[str, Any], clip: Mapping[str, Any], position: int) -> bool:
    """Move a shot to a position of the timeline, from 0; False when it is already there."""
    clips = doc["clips"]
    current = index_of(doc, clip)
    target = max(0, min(len(clips) - 1, position))
    if current == target:
        return False
    clips.insert(target, clips.pop(current))
    relayout(doc)
    return True


def delete_shots(doc: Dict[str, Any], shot_ids: Sequence[str]) -> None:
    """Remove shots with their own prompts, frames and references, and lay the timeline out again."""
    gone = set(shot_ids)
    doc["clips"] = [clip for clip in dicts(doc.get("clips")) if clip.get("id") not in gone]
    for key in LINKED:
        doc[key] = [item for item in dicts(doc.get(key)) if item.get("shotId") not in gone]
    doc["references"] = [
        reference
        for reference in dicts(doc.get("references"))
        if not (isinstance(reference.get("scope"), dict) and reference["scope"].get("type") == "shot" and reference["scope"].get("shotId") in gone)
    ]
    relayout(doc)


def _prompt_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    return next((prompt for prompt in dicts(doc.get("prompts")) if prompt.get("shotId") == clip.get("id")), None)


def role_kind(role: Any) -> Optional[str]:
    """Whether a frame's role makes it the first or the last frame of its shot."""
    value = str(role or "").strip().lower()
    return FIRST if value in FIRST_ROLES else LAST if value in LAST_ROLES else None


def frames_of(doc: Mapping[str, Any], clip: Mapping[str, Any], kind: str) -> List[Dict[str, Any]]:
    """The frames of a shot that act as its first or its last frame."""
    return [frame for frame in dicts(doc.get("frames")) if frame.get("shotId") == clip.get("id") and role_kind(frame.get("role")) == kind]


def frame_time(clip: Mapping[str, Any], kind: str) -> float:
    """Where the first or last frame of a shot sits on the timeline."""
    start = number(clip.get("start"))
    return snap(start + max(0.0, number(clip.get("dur")) - GRID)) if kind == LAST else snap(start)


def frame_asset(doc: Mapping[str, Any], clip: Mapping[str, Any], kind: str) -> Optional[str]:
    """The media of a shot's first or last frame, or None."""
    return next((frame["assetId"] for frame in frames_of(doc, clip, kind) if frame.get("assetId")), None)


def place_frame(doc: Dict[str, Any], clip: Mapping[str, Any], kind: str, asset_id: Optional[str]) -> None:
    """Make a media the first or last frame of a shot, or remove that frame when the media is None."""
    existing = frames_of(doc, clip, kind)
    frames = doc.setdefault("frames", [])
    if not asset_id:
        doc["frames"] = [frame for frame in frames if not any(frame is item for item in existing)]
        return
    fields = {"shotId": clip["id"], "time": frame_time(clip, kind), "assetId": asset_id, "role": kind, "strength": existing[0].get("strength", FRAME_STRENGTH) if existing else FRAME_STRENGTH}
    if existing:
        existing[0].update(fields)
        doc["frames"] = [frame for frame in frames if not any(frame is item for item in existing[1:])]
    else:
        frames.append({"id": generate_ulid(), **fields})


def _media_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    return next((item for item in dicts(doc.get("assets")) if item.get("id") == clip.get("assetId")), None)


def _source_length(media: Optional[Mapping[str, Any]]) -> Optional[float]:
    length = media.get("srcDur") if media else None
    return float(length) if isinstance(length, (int, float)) and not isinstance(length, bool) else None


def take_length(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[float]:
    """How long the generated take placed on a shot lasts on the timeline from its in point, slowed by the shot's speed, or None."""
    media = _media_of(doc, clip)
    if not media or not media.get("generated") or _source_length(media) is None:
        return None
    return (number(media["srcDur"]) - number(clip.get("srcIn"))) / formats.speed_of(clip)


def duration_limit(doc: Mapping[str, Any], clip: Mapping[str, Any], engine_max: Optional[float] = None) -> Tuple[float, Optional[str]]:
    """The longest a shot may last and what sets it, as the page's durationLimit: its engine over a generated take, else what its source media has left from its in point, slowed by the shot's speed."""
    media = _media_of(doc, clip)
    if media and media.get("generated"):
        return (engine_max, "engine") if engine_max and engine_max > 0 else (SHOT_CAP_S, None)
    length = _source_length(media)
    return ((length if length is not None else SHOT_CAP_S) - number(clip.get("srcIn"))) / formats.speed_of(clip), "source" if length else None


def release(clip: Dict[str, Any]) -> Optional[str]:
    """Take the placed take off a shot, which goes back to generate; returns the take it held."""
    held = clip.get("take")
    clip.update({"assetId": None, "take": None, "srcIn": 0, "stage": "todo"})
    return held


def resize(doc: Dict[str, Any], clip: Dict[str, Any], duration: float, maximum: float = SHOT_CAP_S) -> Tuple[bool, Optional[str]]:
    """Change a shot's length as the shot editor does, within its maximum: its covering prompt and its frames follow, and a take too short for it is released; returns whether it changed and the take released."""
    duration = snap(min(max(MIN_SHOT_S, duration), max(MIN_SHOT_S, maximum)))
    was = number(clip.get("dur"))
    if abs(duration - was) <= 1e-6:
        return False, None
    prompt = _prompt_of(doc, clip)
    covered = prompt is not None and abs(number(prompt.get("start")) - number(clip.get("start"))) < 1e-6 and abs(number(prompt.get("dur")) - was) < 1e-6
    clip["dur"] = duration
    if covered:
        prompt["dur"] = duration
    for kind in (FIRST, LAST):
        place_frame(doc, clip, kind, frame_asset(doc, clip, kind))
    length = take_length(doc, clip)
    released = release(clip) if length is not None and duration > was + 1e-6 and duration > length + TAKE_SLACK else None
    return True, released


def set_cast(clip: Dict[str, Any], characters: Optional[List[str]], place: Any) -> None:
    """Store the cast of a shot, or drop it when it is empty."""
    cast = dict(clip["cast"]) if isinstance(clip.get("cast"), dict) else {}
    if characters is not None:
        if characters:
            cast["characters"] = characters
        else:
            cast.pop("characters", None)
    if place is not ...:
        if place:
            cast["place"] = place
        else:
            cast.pop("place", None)
    if cast:
        clip["cast"] = cast
    else:
        clip.pop("cast", None)


def chain_frames(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The first frames of a shot taken from the last image of the previous shot, as the page's chainFrames."""
    if index_of(doc, clip) == 0:
        return []
    stills = {item.get("id") for item in dicts(doc.get("assets")) if isinstance(item.get("frameOf"), dict)}
    return [frame for frame in frames_of(doc, clip, FIRST) if frame.get("assetId") in stills]


def set_chain(doc: Dict[str, Any], clip: Dict[str, Any], on: bool) -> bool:
    """Make a shot start from the last image of the previous shot or not, as the page's setShotChain; False for the first shot or when its own choice is already that."""
    if index_of(doc, clip) == 0 or clip.get("firstFromPrevious") is on:
        return False
    dropped = [] if on else chain_frames(doc, clip)
    clip["firstFromPrevious"] = on
    if dropped:
        doc["frames"] = [frame for frame in dicts(doc.get("frames")) if not any(frame is item for item in dropped)]
    return True


def reference_type(space: str, kind: Any) -> Optional[str]:
    """The first reference type of a space that takes media of this kind."""
    return next((name for name, media in SPACE_TYPES.get(space, ()) if media == kind), None)


def add_reference(doc: Dict[str, Any], clip: Mapping[str, Any], media: Mapping[str, Any], space: str) -> Dict[str, Any]:
    """Attach a media of the project to one shot as its own reference."""
    kind = reference_type(space, media.get("kind"))
    if kind is None:
        raise EditError("invalid_arguments", f"A {media.get('kind')} cannot be a reference of the {space} space.")
    reference = {
        "id": generate_ulid(),
        "name": str(media.get("name") or kind),
        "space": space,
        "type": kind,
        "assetId": media["id"],
        "role": SPACE_ROLES[space],
        "scope": {"type": "shot", "shotId": clip["id"]},
    }
    doc.setdefault("references", []).append(reference)
    return reference


def own_references(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The references attached to one shot only."""
    return [
        reference
        for reference in dicts(doc.get("references"))
        if isinstance(reference.get("scope"), dict) and reference["scope"].get("type") == "shot" and reference["scope"].get("shotId") == clip.get("id")
    ]


def global_references(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The references every shot inherits."""
    return [reference for reference in dicts(doc.get("references")) if not (isinstance(reference.get("scope"), dict) and reference["scope"].get("type") == "shot")]


def excluded(clip: Mapping[str, Any]) -> List[str]:
    """The inherited references a shot leaves out."""
    overrides = clip.get("referenceOverrides")
    listed = overrides.get("exclude") if isinstance(overrides, dict) else None
    return [item for item in listed if isinstance(item, str) and item] if isinstance(listed, list) else []


def set_excluded(clip: Dict[str, Any], ids: Sequence[str]) -> None:
    """Store the inherited references a shot leaves out, dropping the override when none is left."""
    overrides = dict(clip["referenceOverrides"]) if isinstance(clip.get("referenceOverrides"), dict) else {}
    unique = list(dict.fromkeys(ids))
    if unique:
        overrides["exclude"] = unique
    else:
        overrides.pop("exclude", None)
    if overrides:
        clip["referenceOverrides"] = overrides
    else:
        clip.pop("referenceOverrides", None)


def take_asset(take: Mapping[str, Any], name: str) -> Dict[str, Any]:
    """The media of a finished take, shaped like the page's."""
    width = take.get("width") if isinstance(take.get("width"), int) else None
    height = take.get("height") if isinstance(take.get("height"), int) else None
    origin = {"kind": "history", "generationId": take["generation_id"], "fileId": take["file_id"]} if take.get("generation_id") and take.get("file_id") else None
    return {
        "id": f"gen-{take['id']}",
        "kind": "video",
        "name": name,
        "src": take.get("url"),
        "origin": origin,
        "srcDur": take.get("duration_s"),
        "width": width,
        "height": height,
        "fps": take.get("fps"),
        "res": f"{width}×{height}" if width and height else None,
        "generated": True,
        "quality": take.get("quality"),
        "resultId": take["id"],
        "role": None,
    }


def shot_name(doc: Mapping[str, Any], clip: Mapping[str, Any], language: str) -> str:
    """The name the page gives a shot: its label, else its media's name, else the word for shot."""
    if clip.get("label"):
        return str(clip["label"])
    media = next((item for item in dicts(doc.get("assets")) if clip.get("assetId") and item.get("id") == clip.get("assetId")), None)
    return str(media["name"]) if media and media.get("name") else SHOT_NAMES.get(language, SHOT_NAMES["en"])


def place_take(doc: Dict[str, Any], clip: Dict[str, Any], take: Mapping[str, Any], language: str) -> bool:
    """Put a finished take on its shot as the page does, adding its media when the project has none; False when nothing changed."""
    asset_id = f"gen-{take['id']}"
    assets = doc.setdefault("assets", [])
    changed = False
    if not any(item.get("id") == asset_id for item in dicts(assets)):
        names = TAKE_NAMES.get(language, TAKE_NAMES["en"])
        pattern = names["final"] if take.get("quality") == "final" else names["draft"]
        assets.append(take_asset(take, pattern.format(shot=shot_name(doc, clip, language), variant=take.get("variant") or "")))
        changed = True
    removed = doc.get("removedTakes")
    if isinstance(removed, list) and take["id"] in removed:
        kept = [item for item in removed if item != take["id"]]
        if kept:
            doc["removedTakes"] = kept
        else:
            doc.pop("removedTakes", None)
        changed = True
    placed = {"assetId": asset_id, "take": take["id"], "srcIn": 0, "stage": take.get("quality") or "draft"}
    changed = changed or any(clip.get(key) != value for key, value in placed.items())
    clip.update(placed)
    return changed
