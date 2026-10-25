import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from . import settings
from .bible import LAYOUTS, PARTS
from .catalog import PROFILES
from .core_bridge import generate_ulid

MAX_DOC_BYTES = 4 * 1024 * 1024

_REASON_LIMIT = 300

RETIRED_KEYS = ("results", "controls", "plans3d", "scenes")

CAPTURE_ROLE = "Capture 3D"

GUIDE_SOURCE = "scene3d"

SET_SPACE = "decors3d"

SET_ROLE = "Décor"

OLD_SET_ROLE = "Décor 3D"

MOTION_SPACE = "mouvement"

MOTION_TYPE = "Control video"

MOTION_ROLE = "Mouvement"

RETIRED_SET_TYPES = ("Scène d’essai", "Scène d'essai", "Gaussian Splat")

PROJECTS = "video_producer_projects"
VERSIONS = "video_producer_versions"
TAKES = "video_producer_takes"
JOBS = "video_producer_jobs"

ID = {"type": "string", "minLength": 1}
REF = {"type": ["string", "null"], "minLength": 1}
TEXT = {"type": "string"}
NUMBER = {"type": "number"}
FLAG = {"type": "boolean"}
NULLABLE_NUMBER = {"type": ["number", "null"]}
NULLABLE_INTEGER = {"type": ["integer", "null"]}
NULLABLE_TEXT = {"type": ["string", "null"]}
NULLABLE_FLAG = {"type": ["boolean", "null"]}
AUDIO_ROLES = ("Dialogue", "Musique", "Ambiance", "SFX")
REFERENCE_SPACES = ("identite", "decors3d", "mouvement", "son")
MAX_REFERENCE_MARGIN = 10
MAX_DRAFTS = 16
SEED_LIMIT = 2**31 - 1
MATCH_ANCHORS = ("keyframe", "reference", "previous")
MATCH_STATS = 6
LOUDNESS_TARGETS = ("web", "broadcast")
MAX_CROSSFADE = 2


def _enum(*values: Any) -> Dict[str, Any]:
    return {"enum": list(values)}


def _array(items: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "array", "items": items}


def _object(properties: Dict[str, Any], optional: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {**properties, **(optional or {})},
        "required": list(properties),
        "additionalProperties": False,
    }


def _tagged(tag: str, variants: Dict[str, Dict[str, Any]], nullable: bool = False) -> Dict[str, Any]:
    return {
        "type": ["object", "null"] if nullable else "object",
        "required": [tag],
        "properties": {tag: _enum(*variants)},
        "allOf": [
            {
                "if": {"type": "object", "properties": {tag: {"const": value}}, "required": [tag]},
                "then": _object({tag: {"const": value}, **fields}),
            }
            for value, fields in variants.items()
        ],
    }


REFERENCE_OVERRIDES = _object(
    {}, optional={"exclude": {**_array(ID), "uniqueItems": True}, "excludeLanes": {**_array(ID), "uniqueItems": True}}
)

STATS = {"type": "array", "items": NUMBER, "minItems": MATCH_STATS, "maxItems": MATCH_STATS}

COLOR_MATCH = _object(
    {
        "anchor": _enum(*MATCH_ANCHORS),
        "anchorId": REF,
        "assetId": REF,
        "strength": {"type": "number", "minimum": 0, "maximum": 100},
        "source": STATS,
        "target": STATS,
    }
)

SHOT_ENGINE = _object(
    {},
    optional={
        "preset": ID,
        "model": REF,
        "backend": TEXT,
        "profile": _enum(*PROFILES),
        "quality": _enum("draft", "final"),
        "seed": {"type": "integer", "minimum": 0, "maximum": SEED_LIMIT},
    },
)

HYBRID = _object({"continuite": NUMBER, "identite": NUMBER, "audio": NUMBER, "mouvement": NUMBER, "style": NUMBER})

IDS = {**_array(ID), "uniqueItems": True}

CAST = _object({}, optional={"characters": IDS, "place": REF})

CHARACTER = _object({"id": ID, "label": TEXT, "text": TEXT, "props": TEXT, "references": IDS})

PLACE = _object({"id": ID, "label": TEXT, "text": TEXT, "references": IDS})

BIBLE = _object({"characters": _array(CHARACTER), "places": _array(PLACE)})

PROMPT_PARTS = _object({}, optional={name: TEXT for name in PARTS})

REFERENCE_PROMPT = _object({"layout": _enum(*LAYOUTS), "parts": PROMPT_PARTS, "base": PROMPT_PARTS})

OPTION_LORA = _object({"model": ID, "strength": NUMBER})

PRESET_OPTIONS = {
    "type": "object",
    "propertyNames": {"minLength": 1},
    "additionalProperties": {"anyOf": [{"type": ["string", "number", "boolean"]}, _array(OPTION_LORA)]},
}

ENGINE_OPTIONS = {"type": "object", "propertyNames": {"minLength": 1}, "additionalProperties": PRESET_OPTIONS}

CLIP = _object(
    {
        "id": ID,
        "assetId": REF,
        "start": NUMBER,
        "dur": NUMBER,
        "srcIn": NUMBER,
        "label": TEXT,
        "stage": _enum("source", "todo", "draft", "final"),
        "take": REF,
        "fadeIn": NUMBER,
        "fadeOut": NUMBER,
        "exposure": NUMBER,
        "contrast": NUMBER,
        "saturation": NUMBER,
        "temperature": NUMBER,
        "preset": TEXT,
        "flag": _enum("favori", "rejet", None),
    },
    optional={
        "mute": FLAG,
        "match": COLOR_MATCH,
        "deflicker": FLAG,
        "drafts": {"type": "integer", "minimum": 1, "maximum": MAX_DRAFTS},
        "revision": {"type": "integer", "minimum": 0},
        "referenceOverrides": REFERENCE_OVERRIDES,
        "engine": SHOT_ENGINE,
        "cast": CAST,
        "referencePrompt": REFERENCE_PROMPT,
    },
)

AUDIO = _object(
    {
        "id": ID,
        "assetId": REF,
        "lane": TEXT,
        "start": NUMBER,
        "dur": NUMBER,
        "srcIn": NUMBER,
        "fadeIn": NUMBER,
        "fadeOut": NUMBER,
        "gain": NUMBER,
    },
    optional={"reference": FLAG},
)

TITLE = _object({"id": ID, "text": TEXT, "sub": TEXT, "start": NUMBER, "dur": NUMBER})

PROMPT = _object({"id": ID, "shotId": REF, "start": NUMBER, "dur": NUMBER, "strength": NUMBER, "text": TEXT})

FRAME = _object(
    {"id": ID, "shotId": REF, "time": NUMBER, "assetId": REF, "role": TEXT, "strength": NUMBER}
)

MARKER = _object({"id": ID, "time": NUMBER, "label": TEXT, "kind": TEXT})

REFERENCE = _object(
    {
        "id": ID,
        "name": TEXT,
        "space": _enum(*REFERENCE_SPACES),
        "type": TEXT,
        "assetId": REF,
        "role": TEXT,
        "scope": _tagged("type", {"global": {}, "shot": {"shotId": ID}}, nullable=True),
    }
)

INSERT = _tagged(
    "type",
    {
        "eq": {"on": FLAG, "low": NUMBER, "mid": NUMBER, "high": NUMBER},
        "comp": {"on": FLAG, "threshold": NUMBER, "ratio": NUMBER, "attack": NUMBER, "release": NUMBER},
        "filter": {"on": FLAG, "cutoff": NUMBER},
    },
)

LANE = _object(
    {
        "id": ID,
        "name": TEXT,
        "role": _enum(*AUDIO_ROLES),
        "vol": NUMBER,
        "pan": NUMBER,
        "mute": FLAG,
        "solo": FLAG,
        "automation": _enum("off", "read", "write"),
        "sends": _object({"R1": NUMBER, "D1": NUMBER}),
        "inserts": _array(INSERT),
    },
    optional={"reference": FLAG},
)

VIDEO_TRACK = _object({"mute": FLAG, "solo": FLAG})

AUX = _object({"id": ID, "name": TEXT, "vol": NUMBER, "mute": FLAG})

PROFILE = _object({"id": ID, "name": TEXT, "weights": HYBRID})

ENGINE = _object(
    {"quality": TEXT, "variants": NULLABLE_INTEGER, "backend": TEXT},
    optional={
        "preset": NULLABLE_TEXT,
        "model": NULLABLE_TEXT,
        "seed": NULLABLE_INTEGER,
        "resolution": TEXT,
        "steps": NULLABLE_NUMBER,
        "guidance": NULLABLE_NUMBER,
        "overlap": NUMBER,
        "windowLen": NUMBER,
        "loras": _array(_object({"name": TEXT, "weight": NUMBER})),
        "post": _object({"upscale": FLAG, "interpolation": FLAG, "denoise": FLAG}),
        "consistency": NUMBER,
        "lockIdentity": FLAG,
        "motionPriority": FLAG,
        "audioDriver": TEXT,
        "lipSync": FLAG,
        "offset": NUMBER,
        "followCut": FLAG,
        "naming": TEXT,
        "autoInsert": FLAG,
        "referenceMargin": {"type": "number", "minimum": 0, "maximum": MAX_REFERENCE_MARGIN},
        "options": ENGINE_OPTIONS,
        "keyframes": _object({}, optional={"preset": ID, "model": REF}),
    },
)

FRAME_OF = _object({"shotId": ID, "takeId": REF, "assetId": ID, "at": NULLABLE_NUMBER})

ASSET = _object(
    {
        "id": ID,
        "kind": _enum("video", "image", "audio"),
        "name": TEXT,
        "src": NULLABLE_TEXT,
        "origin": _tagged(
            "kind",
            {"history": {"generationId": ID, "fileId": ID}, "library": {"itemId": ID}},
            nullable=True,
        ),
        "srcDur": NULLABLE_NUMBER,
        "width": NULLABLE_INTEGER,
        "height": NULLABLE_INTEGER,
        "fps": NULLABLE_NUMBER,
        "res": NULLABLE_TEXT,
        "generated": FLAG,
        "quality": _enum("draft", "final", None),
        "resultId": NULLABLE_TEXT,
        "role": _enum(*AUDIO_ROLES, None),
        "synth": _enum("wind", "steps", "pad", "voice", None),
        "transcript": NULLABLE_TEXT,
        "character": NULLABLE_TEXT,
        "lipSync": NULLABLE_FLAG,
    },
    optional={"frameOf": FRAME_OF},
)

DOC_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    **_object(
        {
            "name": TEXT,
            "fps": NUMBER,
            "aspect": TEXT,
            "resolution": TEXT,
            "promptLanguage": _enum("en", "fr"),
            "direction": _object(
                {
                    "univers": TEXT,
                    "personnages": TEXT,
                    "photographie": TEXT,
                    "palette": TEXT,
                    "rythme": TEXT,
                    "mode": TEXT,
                }
            ),
            "synopsis": TEXT,
            "clips": _array(CLIP),
            "audio": _array(AUDIO),
            "titles": _array(TITLE),
            "prompts": _array(PROMPT),
            "frames": _array(FRAME),
            "markers": _array(MARKER),
            "references": _array(REFERENCE),
            "lanes": _array(LANE),
            "aux": _array(AUX),
            "master": _object(
                {"vol": NUMBER},
                optional={
                    "loudness": _enum(*LOUDNESS_TARGETS),
                    "crossfade": {"type": "number", "minimum": 0, "maximum": MAX_CROSSFADE},
                },
            ),
            "engine": ENGINE,
            "assets": _array(ASSET),
        },
        optional={
            "video": VIDEO_TRACK,
            "profiles": _array(PROFILE),
            "hybrid": HYBRID,
            "firstFromPrevious": FLAG,
            "bible": BIBLE,
        },
    ),
}

_VALIDATOR = Draft202012Validator(DOC_SCHEMA)


class DocError(ValueError):
    """A project document the plugin refuses to store."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProjectNotFound(LookupError):
    """No project has this id."""


class VersionNotFound(LookupError):
    """The project has no stored version with this number."""


class VersionConflict(Exception):
    """The project moved on since the version the caller read."""

    def __init__(self, current_version: int):
        super().__init__(f"The project is at version {current_version}")
        self.current_version = current_version


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _empty_capture(frame: Any) -> bool:
    return isinstance(frame, dict) and frame.get("role") == CAPTURE_ROLE and not frame.get("assetId")


def _captured_frame(frame: Any) -> bool:
    return isinstance(frame, dict) and "sceneId" in frame


def _plain_frame(frame: Any) -> Any:
    return {key: value for key, value in frame.items() if key != "sceneId"} if _captured_frame(frame) else frame


def _retired_set(reference: Any) -> bool:
    return isinstance(reference, dict) and reference.get("space") == SET_SPACE and reference.get("type") in RETIRED_SET_TYPES


def _old_role(reference: Any) -> bool:
    return isinstance(reference, dict) and reference.get("role") == OLD_SET_ROLE


def _current_reference(reference: Any) -> Any:
    if not isinstance(reference, dict):
        return reference
    changes = {"type": CAPTURE_ROLE} if _retired_set(reference) else {}
    if _old_role(reference):
        changes["role"] = SET_ROLE
    return {**reference, **changes} if changes else reference


def _span(item: Dict[str, Any]) -> Tuple[float, float]:
    start = float(item["start"]) if _number(item.get("start")) else 0.0
    return start, start + (float(item["dur"]) if _number(item.get("dur")) else 0.0)


def _guided_shot(control: Dict[str, Any], clips: Any) -> Optional[str]:
    shots = [clip for clip in clips if isinstance(clip, dict) and isinstance(clip.get("id"), str) and clip["id"]] if isinstance(clips, list) else []
    if control.get("shotId"):
        return control["shotId"] if any(clip["id"] == control["shotId"] for clip in shots) else None
    start, end = _span(control)
    covered = [(min(end, last) - max(start, first), clip["id"]) for clip in shots for first, last in [_span(clip)]]
    best = max(covered, key=lambda pair: pair[0], default=None)
    return best[1] if best is not None and best[0] > 0 else None


def _motion_references(doc: Dict[str, Any], references: List[Any]) -> List[Dict[str, Any]]:
    controls = doc.get("controls") if isinstance(doc.get("controls"), list) else []
    assets = doc.get("assets") if isinstance(doc.get("assets"), list) else []
    videos = {asset.get("id") for asset in assets if isinstance(asset, dict) and asset.get("kind") == "video"}
    known = {reference.get("id") for reference in references if isinstance(reference, dict)}
    added: List[Dict[str, Any]] = []
    for control in controls:
        if not isinstance(control, dict) or control.get("source") != GUIDE_SOURCE or control.get("assetId") not in videos:
            continue
        if not isinstance(control.get("id"), str) or not control["id"] or control["id"] in known:
            continue
        shot_id = _guided_shot(control, doc.get("clips"))
        if shot_id is None:
            continue
        added.append(
            {
                "id": control["id"],
                "name": control["name"] if isinstance(control.get("name"), str) else "",
                "space": MOTION_SPACE,
                "type": MOTION_TYPE,
                "assetId": control["assetId"],
                "role": MOTION_ROLE,
                "scope": {"type": "shot", "shotId": shot_id},
            }
        )
        known.add(control["id"])
    return added


def _card_ids(doc: Dict[str, Any], kind: str) -> Set[Any]:
    bible = doc.get("bible")
    cards = bible.get(kind) if isinstance(bible, dict) else None
    return {card.get("id") for card in cards if isinstance(card, dict)} if isinstance(cards, list) else set()


def _cast(clip: Any, characters: Set[Any], places: Set[Any]) -> Any:
    cast = clip.get("cast") if isinstance(clip, dict) else None
    if not isinstance(cast, dict):
        return clip
    kept = dict(cast)
    listed = cast.get("characters")
    if isinstance(listed, list):
        known = [item for item in listed if item in characters]
        if known != listed:
            kept["characters"] = known
        if not known:
            kept.pop("characters")
    if cast.get("place") is not None and cast["place"] not in places:
        kept.pop("place")
    if kept == cast:
        return clip
    return {**clip, "cast": kept} if kept else {key: value for key, value in clip.items() if key != "cast"}


def migrate(doc: Any) -> Any:
    """A document in the current schema: the video of each 3D guide added once as a Mouvement reference of the shot it covers, then the keys earlier versions of the page wrote dropped (the simulated takes, the 3D shots, the Control videos and the 3D scenes), the empty 3D captures dropped and the scene of the other frames forgotten, the retired 3D set references turned into 3D captures when they have an image and dropped otherwise, the 3D set role of a reference turned into the set role, and the cast of each shot cleared of the bible cards that no longer exist; the same object when nothing changes."""
    if not isinstance(doc, dict):
        return doc
    changes: Dict[str, Any] = {}
    frames = doc.get("frames")
    if isinstance(frames, list) and any(_empty_capture(frame) or _captured_frame(frame) for frame in frames):
        changes["frames"] = [_plain_frame(frame) for frame in frames if not _empty_capture(frame)]
    references = doc.get("references")
    if isinstance(references, list) and any(_retired_set(reference) or _old_role(reference) for reference in references):
        changes["references"] = [_current_reference(reference) for reference in references if not _retired_set(reference) or reference.get("assetId")]
    kept = changes.get("references", references)
    motions = _motion_references(doc, kept) if isinstance(kept, list) else []
    if motions:
        changes["references"] = [*kept, *motions]
    clips = doc.get("clips")
    if isinstance(clips, list):
        cast = [_cast(clip, _card_ids(doc, "characters"), _card_ids(doc, "places")) for clip in clips]
        if any(new is not old for new, old in zip(cast, clips)):
            changes["clips"] = cast
    if not changes and not any(key in doc for key in RETIRED_KEYS):
        return doc
    return {**{key: value for key, value in doc.items() if key not in RETIRED_KEYS}, **changes}


def canonical(doc: Any) -> str:
    """The stable JSON text a document is stored and compared as."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _reason(text: str) -> str:
    return text if len(text) <= _REASON_LIMIT else text[: _REASON_LIMIT - 1] + "…"


def validate_doc(doc: Any) -> str:
    """Check a document against DOC_SCHEMA and the size limit; returns its canonical text."""
    try:
        text = canonical(doc)
    except ValueError as exc:
        raise DocError("invalid_doc", f"$: {_reason(str(exc))}") from None
    size = len(text.encode("utf-8"))
    if size > MAX_DOC_BYTES:
        raise DocError("doc_too_large", f"$: the document is {size} bytes, over the {MAX_DOC_BYTES}-byte limit")
    error = best_match(_VALIDATOR.iter_errors(doc))
    if error is not None:
        raise DocError("invalid_doc", f"{error.json_path}: {_reason(error.message)}")
    return text


def summary(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The shot count and the running time of a document."""
    ends = [item["start"] + item["dur"] for key in ("clips", "audio", "titles") for item in doc.get(key) or []]
    return {"shots": len(doc.get("clips") or []), "duration_s": max(ends, default=0)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "version": row["version"],
        "doc": migrate(json.loads(row["doc"])),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _versions_kept() -> int:
    return int(settings.get_setting("versions_kept"))


def _append_version(
    cursor: Any,
    project_id: str,
    version: int,
    text: str,
    at: str,
    label: Optional[str] = None,
    source_version: Optional[int] = None,
    keep: Optional[int] = None,
) -> None:
    cursor.execute(
        f"INSERT INTO {VERSIONS} (id, project_id, version, doc, label, source_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (generate_ulid(), project_id, version, text, label, source_version, at),
    )
    if keep is not None:
        cursor.execute(
            f"DELETE FROM {VERSIONS} WHERE project_id = ? AND id NOT IN "
            f"(SELECT id FROM {VERSIONS} WHERE project_id = ? ORDER BY version DESC LIMIT ?)",
            (project_id, project_id, keep),
        )


def _advance(cursor: Any, project_id: str, version: int, text: str, name: str, at: str) -> None:
    cursor.execute(
        f"UPDATE {PROJECTS} SET doc = ?, name = ?, version = ?, updated_at = ? WHERE id = ? AND version = ?",
        (text, name, version + 1, at, project_id, version),
    )
    if cursor.rowcount != 1:
        cursor.execute(f"SELECT version FROM {PROJECTS} WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if row is None:
            raise ProjectNotFound(project_id)
        raise VersionConflict(row["version"])


def list_projects(user_id: str) -> List[Dict[str, Any]]:
    """The user's own projects with their shot count and running time, last updated first."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT id, name, version, doc, created_at, updated_at FROM {PROJECTS} "
            "WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user_id,),
        )
        rows = cursor.fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            **summary(json.loads(row["doc"])),
        }
        for row in rows
    ]


def create_project(user_id: str, doc: Any, name: Optional[str] = None) -> Dict[str, Any]:
    """Store a new project at version 1, naming its document when a name is given."""
    from src.plugin_api import db

    doc = migrate(doc)
    if name is not None and isinstance(doc, dict):
        doc = {**doc, "name": name}
    text = validate_doc(doc)
    project_id, at = generate_ulid(), _now()
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {PROJECTS} (id, user_id, name, doc, version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (project_id, user_id, doc["name"], text, at, at),
        )
        _append_version(cursor, project_id, 1, text, at)
    return {
        "id": project_id,
        "user_id": user_id,
        "name": doc["name"],
        "version": 1,
        "doc": json.loads(text),
        "created_at": at,
        "updated_at": at,
    }


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """A project with its owner and document, or None."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT id, user_id, name, version, doc, created_at, updated_at FROM {PROJECTS} WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
    return None if row is None else _project(row)


def project_owner(project_id: str) -> Optional[str]:
    """The id of the user who owns a project, or None when there is no such project."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT user_id FROM {PROJECTS} WHERE id = ?", (project_id,))
        row = cursor.fetchone()
    return None if row is None else row["user_id"]


def save_project(project_id: str, doc: Any, expected_version: int, label: Optional[str] = None) -> Dict[str, Any]:
    """Store a new version of a project, or nothing when the document did not change."""
    from src.plugin_api import db

    doc = migrate(doc)
    text = validate_doc(doc)
    keep = _versions_kept()
    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT name, version, doc, updated_at FROM {PROJECTS} WHERE id = ?", (project_id,))
        project = cursor.fetchone()
        if project is None:
            raise ProjectNotFound(project_id)
        if project["version"] != expected_version:
            raise VersionConflict(project["version"])
        cursor.execute(
            f"SELECT doc FROM {VERSIONS} WHERE project_id = ? ORDER BY version DESC LIMIT 1", (project_id,)
        )
        latest = cursor.fetchone()
        if (latest["doc"] if latest is not None else project["doc"]) == text:
            return {
                "id": project_id,
                "name": project["name"],
                "version": project["version"],
                "updated_at": project["updated_at"],
                "unchanged": True,
            }
        at = _now()
        _advance(cursor, project_id, expected_version, text, doc["name"], at)
        _append_version(cursor, project_id, expected_version + 1, text, at, label=label, keep=keep)
    return {"id": project_id, "name": doc["name"], "version": expected_version + 1, "updated_at": at, "unchanged": False}


def delete_project(project_id: str) -> bool:
    """Delete a project with its versions, takes and jobs; False when there was no such project."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {JOBS} WHERE take_id IN (SELECT id FROM {TAKES} WHERE project_id = ?)", (project_id,))
        cursor.execute(f"DELETE FROM {TAKES} WHERE project_id = ?", (project_id,))
        cursor.execute(f"DELETE FROM {VERSIONS} WHERE project_id = ?", (project_id,))
        cursor.execute(f"DELETE FROM {PROJECTS} WHERE id = ?", (project_id,))
        return cursor.rowcount > 0


def list_versions(project_id: str) -> List[Dict[str, Any]]:
    """The stored versions of a project without their documents, latest first."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT id, version, label, source_version, created_at, doc FROM {VERSIONS} "
            "WHERE project_id = ? ORDER BY version DESC",
            (project_id,),
        )
        rows = cursor.fetchall()
    return [
        {
            "id": row["id"],
            "version": row["version"],
            "label": row["label"],
            "source_version": row["source_version"],
            "created_at": row["created_at"],
            "shots": summary(json.loads(row["doc"]))["shots"],
        }
        for row in rows
    ]


def restore_version(project_id: str, version: int) -> Dict[str, Any]:
    """Make a stored version the project's next version."""
    from src.plugin_api import db

    keep = _versions_kept()
    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT version FROM {PROJECTS} WHERE id = ?", (project_id,))
        project = cursor.fetchone()
        if project is None:
            raise ProjectNotFound(project_id)
        cursor.execute(f"SELECT doc FROM {VERSIONS} WHERE project_id = ? AND version = ?", (project_id, version))
        stored = cursor.fetchone()
        if stored is None:
            raise VersionNotFound(version)
        doc, current, at = migrate(json.loads(stored["doc"])), project["version"], _now()
        text = canonical(doc)
        _advance(cursor, project_id, current, text, doc["name"], at)
        _append_version(cursor, project_id, current + 1, text, at, source_version=version, keep=keep)
    return {"id": project_id, "name": doc["name"], "version": current + 1, "doc": doc, "updated_at": at}
