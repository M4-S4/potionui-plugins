import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from . import settings
from .core_bridge import generate_ulid

MAX_DOC_BYTES = 4 * 1024 * 1024

_REASON_LIMIT = 300

PROJECTS = "video_producer_projects"
VERSIONS = "video_producer_versions"
TAKES = "video_producer_takes"
JOBS = "video_producer_jobs"

ID = {"type": "string", "minLength": 1}
REF = {"type": ["string", "null"], "minLength": 1}
TEXT = {"type": "string"}
NUMBER = {"type": "number"}
INTEGER = {"type": "integer"}
FLAG = {"type": "boolean"}
NULLABLE_NUMBER = {"type": ["number", "null"]}
NULLABLE_INTEGER = {"type": ["integer", "null"]}
NULLABLE_TEXT = {"type": ["string", "null"]}
NULLABLE_FLAG = {"type": ["boolean", "null"]}
AUDIO_ROLES = ("Dialogue", "Musique", "Ambiance", "SFX")


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


HYBRID = _object({"continuite": NUMBER, "identite": NUMBER, "audio": NUMBER, "mouvement": NUMBER, "style": NUMBER})

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
    }
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
    }
)

TITLE = _object({"id": ID, "text": TEXT, "sub": TEXT, "start": NUMBER, "dur": NUMBER})

PROMPT = _object({"id": ID, "shotId": REF, "start": NUMBER, "dur": NUMBER, "strength": NUMBER, "text": TEXT})

FRAME = _object({"id": ID, "shotId": REF, "time": NUMBER, "assetId": REF, "role": TEXT, "strength": NUMBER})

CONTROL = _object(
    {
        "id": ID,
        "shotId": REF,
        "name": TEXT,
        "start": NUMBER,
        "dur": NUMBER,
        "guidance": NUMBER,
        "source": _enum("import", "scene3d"),
        "stale": FLAG,
    }
)

KEYFRAME = _object(
    {"id": ID, "t": NUMBER, "az": NUMBER, "el": NUMBER, "dist": NUMBER, "focal": NUMBER, "height": NUMBER}
)

PLAN3D = _object(
    {
        "id": ID,
        "shotId": REF,
        "sceneId": REF,
        "name": TEXT,
        "start": NUMBER,
        "dur": NUMBER,
        "keyframes": _array(KEYFRAME),
    }
)

MARKER = _object({"id": ID, "time": NUMBER, "label": TEXT, "kind": TEXT})

REFERENCE = _object(
    {
        "id": ID,
        "name": TEXT,
        "space": _enum("identite", "decors3d", "mouvement"),
        "type": TEXT,
        "assetId": REF,
        "role": TEXT,
        "scope": _tagged("type", {"global": {}, "shot": {"shotId": ID}}, nullable=True),
    }
)

SCENE = _tagged("kind", {"sample": {"id": ID, "name": TEXT}, "file": {"id": ID, "name": TEXT, "file": TEXT}})

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
    }
)

AUX = _object({"id": ID, "name": TEXT, "vol": NUMBER, "mute": FLAG})

RESULT = _object(
    {
        "id": ID,
        "clipId": ID,
        "quality": _enum("draft", "final"),
        "variant": TEXT,
        "assetId": REF,
        "look": TEXT,
        "status": _enum("new", "chosen", "redo"),
        "seed": INTEGER,
        "created": TEXT,
        "range": {"type": "array", "prefixItems": [NUMBER, NUMBER], "minItems": 2, "maxItems": 2},
        "local": TEXT,
        "parent": REF,
        "profile": TEXT,
        "mode": TEXT,
        "backend": TEXT,
    }
)

PROFILE = _object({"id": ID, "name": TEXT, "weights": HYBRID})

ENGINE = _object(
    {
        "seed": NULLABLE_INTEGER,
        "quality": TEXT,
        "resolution": TEXT,
        "steps": NULLABLE_NUMBER,
        "guidance": NULLABLE_NUMBER,
        "overlap": NUMBER,
        "windowLen": NUMBER,
        "loras": _array(_object({"name": TEXT, "weight": NUMBER})),
        "post": _object({"upscale": FLAG, "interpolation": FLAG, "denoise": FLAG}),
        "variants": NULLABLE_INTEGER,
        "backend": TEXT,
        "consistency": NUMBER,
        "lockIdentity": FLAG,
        "motionPriority": FLAG,
        "audioDriver": TEXT,
        "lipSync": FLAG,
        "offset": NUMBER,
        "followCut": FLAG,
        "naming": TEXT,
        "autoInsert": FLAG,
    },
    optional={"preset": NULLABLE_TEXT, "model": NULLABLE_TEXT},
)

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
    }
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
            "controls": _array(CONTROL),
            "plans3d": _array(PLAN3D),
            "markers": _array(MARKER),
            "references": _array(REFERENCE),
            "scenes": _array(SCENE),
            "lanes": _array(LANE),
            "aux": _array(AUX),
            "master": _object({"vol": NUMBER}),
            "results": _array(RESULT),
            "profiles": _array(PROFILE),
            "engine": ENGINE,
            "hybrid": HYBRID,
            "assets": _array(ASSET),
        }
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
        "doc": json.loads(row["doc"]),
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
        doc, current, at = json.loads(stored["doc"]), project["version"], _now()
        _advance(cursor, project_id, current, stored["doc"], doc["name"], at)
        _append_version(cursor, project_id, current + 1, stored["doc"], at, source_version=version, keep=keep)
    return {"id": project_id, "name": doc["name"], "version": current + 1, "doc": doc, "updated_at": at}
