import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .core_bridge import generate_ulid

TAKES = "video_producer_takes"
JOBS = "video_producer_jobs"
CALIBRATION = "video_producer_calibration"
LOOKS = "video_producer_looks"

ACTIVE = ("queued", "running")

FLAGS = ("keep", "reject")

LABELS = ("draft", "rejected", "candidate", "final")

DRAFT, REJECTED, CANDIDATE, FINAL = LABELS

KEYFRAME = "keyframe"

_FLAG_OF = {CANDIDATE: "keep", REJECTED: "reject"}

CALIBRATION_ROWS = 20

COLUMNS = (
    "id",
    "project_id",
    "shot_id",
    "user_id",
    "generation_id",
    "quality",
    "kind",
    "parent_take_id",
    "preset_id",
    "mode",
    "director_mode",
    "backend_id",
    "model_id",
    "seed",
    "resolution",
    "status",
    "progress",
    "step",
    "variant",
    "chosen",
    "flag",
    "label",
    "shot_revision",
    "priority",
    "profile",
    "prompt_text",
    "file_path",
    "thumb_path",
    "file_id",
    "width",
    "height",
    "duration_s",
    "fps",
    "error_code",
    "error_message",
    "units_reserved",
    "request",
    "created_at",
    "started_at",
    "finished_at",
    "chain",
    "chain_wait",
    "frame_role",
)

PUBLIC = (
    "id",
    "project_id",
    "shot_id",
    "generation_id",
    "quality",
    "kind",
    "parent_take_id",
    "preset_id",
    "mode",
    "director_mode",
    "backend_id",
    "model_id",
    "seed",
    "resolution",
    "status",
    "progress",
    "step",
    "variant",
    "chosen",
    "flag",
    "label",
    "shot_revision",
    "priority",
    "profile",
    "prompt_text",
    "file_path",
    "url",
    "thumb_url",
    "file_id",
    "width",
    "height",
    "duration_s",
    "fps",
    "error_code",
    "error_message",
    "units_reserved",
    "created_at",
    "started_at",
    "finished_at",
    "chain",
    "frame_role",
)

_ACTIVE_SQL = "status IN ('queued', 'running')"

_WAITING_SQL = "status = 'queued' AND generation_id IS NULL AND chain_wait = 0"

_CHAIN_WAIT_SQL = "status = 'queued' AND generation_id IS NULL AND chain_wait = 1"

_VIDEO_SQL = f"COALESCE(kind, '') != '{KEYFRAME}'"

_QUEUE_ORDER = "priority DESC, created_at, id"

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {TAKES}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now() -> str:
    """The current time as the takes store it, ISO 8601 in UTC."""
    return _now()


def legacy_label(chosen: Any, flag: Any) -> str:
    """The label a take kept before labels: final when chosen, candidate when kept, rejected when rejected, else draft."""
    if chosen:
        return FINAL
    return {"keep": CANDIDATE, "reject": REJECTED}.get(flag, DRAFT)


def initial_label(quality: Any) -> str:
    """The label a new take starts with: candidate at final quality, draft otherwise."""
    return CANDIDATE if quality == "final" else DRAFT


def _marks(label: str) -> Dict[str, Any]:
    return {"label": label, "chosen": int(label == FINAL), "flag": _FLAG_OF.get(label)}


def _take(row: Any) -> Dict[str, Any]:
    take = {column: row[column] for column in COLUMNS}
    if take["label"] not in LABELS:
        take["label"] = legacy_label(take["chosen"], take["flag"])
    take["chosen"] = bool(take["chosen"])
    take["priority"] = int(take["priority"] or 0)
    take["units_reserved"] = float(take["units_reserved"] or 0)
    take["request"] = json.loads(take["request"]) if take["request"] else None
    take["chain"] = json.loads(take["chain"]) if take["chain"] else None
    take["chain_wait"] = bool(take["chain_wait"])
    return take


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def public(take: Dict[str, Any]) -> Dict[str, Any]:
    """A take as the API returns it, with the URL of its video and thumbnail."""
    url = None
    if take.get("generation_id") and take.get("file_path"):
        url = f"/api/media/generations/{take['generation_id']}/{_basename(take['file_path'])}"
    values = {**take, "url": url, "thumb_url": f"{url}?size=medium" if url and take.get("thumb_path") else None}
    return {key: values.get(key) for key in PUBLIC}


def _fetch_one(query: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    return None if row is None else _take(row)


def _fetch_all(query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [_take(row) for row in rows]


def create_take(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Store a new take; returns it as stored."""
    from src.plugin_api import db

    take = {column: None for column in COLUMNS}
    take.update(
        {"id": generate_ulid(), "status": "queued", "chosen": False, "priority": 0, "units_reserved": 0.0, "created_at": _now(), "chain_wait": False}
    )
    take.update({key: value for key, value in fields.items() if key in COLUMNS})
    if take["label"] not in LABELS:
        take["label"] = legacy_label(take["chosen"], take["flag"]) if take["chosen"] or take["flag"] else initial_label(take["quality"])
    take.update(_marks(take["label"]))
    values = {
        **take,
        "chosen": int(bool(take["chosen"])),
        "request": json.dumps(take["request"]) if take["request"] else None,
        "chain": json.dumps(take["chain"]) if take["chain"] else None,
        "chain_wait": int(bool(take["chain_wait"])),
    }
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TAKES} ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(values[column] for column in COLUMNS),
        )
    return get_take(take["id"])


def get_take(take_id: str) -> Optional[Dict[str, Any]]:
    """One take, or None."""
    return _fetch_one(f"{_SELECT} WHERE id = ?", (take_id,))


def take_for_generation(generation_id: str) -> Optional[Dict[str, Any]]:
    """The take a generation renders, or None."""
    if not generation_id:
        return None
    return _fetch_one(f"{_SELECT} WHERE generation_id = ? ORDER BY created_at DESC LIMIT 1", (generation_id,))


def list_takes(project_id: str, keyframes: bool = False) -> List[Dict[str, Any]]:
    """The video takes of a project, oldest first, with the start and end image candidates when keyframes is True."""
    kinds = "" if keyframes else f" AND {_VIDEO_SQL}"
    return _fetch_all(f"{_SELECT} WHERE project_id = ?{kinds} ORDER BY created_at, id", (project_id,))


def list_keyframes(project_id: str, shot_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """The start and end image candidates of a project, or of one of its shots, oldest first."""
    if shot_id is None:
        return _fetch_all(f"{_SELECT} WHERE project_id = ? AND kind = ? ORDER BY created_at, id", (project_id, KEYFRAME))
    return _fetch_all(
        f"{_SELECT} WHERE project_id = ? AND shot_id = ? AND kind = ? ORDER BY created_at, id", (project_id, shot_id, KEYFRAME)
    )


def list_active(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """The queued and running takes, of one project or of all, in queue order: those handed to the core first, then the waiting ones by priority, oldest first."""
    order = f"ORDER BY generation_id IS NULL, {_QUEUE_ORDER}"
    if project_id is None:
        return _fetch_all(f"{_SELECT} WHERE {_ACTIVE_SQL} {order}")
    return _fetch_all(f"{_SELECT} WHERE project_id = ? AND {_ACTIVE_SQL} {order}", (project_id,))


def list_user_active(user_id: str) -> List[Dict[str, Any]]:
    """The user's queued and running takes, of all their projects, in queue order."""
    return _fetch_all(f"{_SELECT} WHERE user_id = ? AND {_ACTIVE_SQL} ORDER BY generation_id IS NULL, {_QUEUE_ORDER}", (user_id,))


def waiting(user_id: str) -> List[Dict[str, Any]]:
    """The user's queued takes not yet handed to the core, in the order the pump hands them: highest priority first, then oldest first."""
    return _fetch_all(f"{_SELECT} WHERE user_id = ? AND {_WAITING_SQL} ORDER BY {_QUEUE_ORDER}", (user_id,))


def waiting_user_ids() -> List[str]:
    """The users with queued takes not yet handed to the core."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT user_id, MIN(created_at) AS first FROM {TAKES} "
            f"WHERE {_WAITING_SQL} AND user_id IS NOT NULL GROUP BY user_id ORDER BY first"
        )
        return [row["user_id"] for row in cursor.fetchall()]


def in_flight(user_id: str) -> int:
    """How many of the user's takes the core is generating or holds in its queue."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM {TAKES} WHERE user_id = ? AND generation_id IS NOT NULL AND {_ACTIVE_SQL}",
            (user_id,),
        )
        return int(cursor.fetchone()["count"])


def _update(take_id: str, fields: Dict[str, Any], condition: str) -> bool:
    from src.plugin_api import db

    names = [name for name in fields if name in COLUMNS and name != "id"]
    if not names:
        return False
    assignments = ", ".join(f"{name} = ?" for name in names)
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {TAKES} SET {assignments} WHERE id = ? AND {condition}",
            (*(fields[name] for name in names), take_id),
        )
        return cursor.rowcount == 1


def attach_generation(take_id: str, generation_id: str) -> bool:
    """Record the generation a queued take was handed to; False when the take left the queue meanwhile."""
    return _update(take_id, {"generation_id": generation_id}, "status = 'queued' AND generation_id IS NULL")


def update_active(take_id: str, **fields: Any) -> bool:
    """Update a take still queued or running; False when it has already ended."""
    return _update(take_id, fields, _ACTIVE_SQL)


def settle(take_id: str, status: str, **fields: Any) -> bool:
    """End a queued or running take; True only for the caller that ended it."""
    return _update(take_id, {**fields, "status": status}, _ACTIVE_SQL)


def prioritize(take: Dict[str, Any]) -> Dict[str, Any]:
    """Move a waiting take before every other waiting take of its user, its priority one above theirs; a take already first, handed to the core or ended is left alone."""
    queue = waiting(take["user_id"]) if take.get("user_id") else []
    if queue and queue[0]["id"] != take["id"] and any(item["id"] == take["id"] for item in queue):
        _update(take["id"], {"priority": queue[0]["priority"] + 1}, _WAITING_SQL)
    return get_take(take["id"]) or take


def set_label(take_id: str, label: str) -> Optional[Dict[str, Any]]:
    """Label a take; a final take becomes the only one of its shot, the previous final turning candidate."""
    from src.plugin_api import db

    take = get_take(take_id)
    if take is None:
        return None
    marks = _marks(label)
    with db.get_cursor() as cursor:
        if label == FINAL:
            demoted = _marks(CANDIDATE)
            cursor.execute(
                f"UPDATE {TAKES} SET label = ?, chosen = ?, flag = ? "
                "WHERE project_id = ? AND shot_id = ? AND id != ? AND (label = ? OR chosen = 1)",
                (demoted["label"], demoted["chosen"], demoted["flag"], take["project_id"], take["shot_id"], take_id, FINAL),
            )
        cursor.execute(
            f"UPDATE {TAKES} SET label = ?, chosen = ?, flag = ? WHERE id = ?",
            (marks["label"], marks["chosen"], marks["flag"], take_id),
        )
    return get_take(take_id)


def choose(take_id: str, chosen: bool) -> Optional[Dict[str, Any]]:
    """The former choose: final when chosen; unchoosing a final take makes it candidate and leaves the others alone."""
    take = get_take(take_id)
    if take is None:
        return None
    if chosen:
        return set_label(take_id, FINAL)
    return set_label(take_id, CANDIDATE) if take["label"] == FINAL else take


def set_flag(take_id: str, flag: Optional[str]) -> Optional[Dict[str, Any]]:
    """The former flag: keep makes a take candidate and reject rejected; clearing the flag of a candidate or rejected take makes it draft; a final take stays final unless rejected."""
    take = get_take(take_id)
    if take is None:
        return None
    if flag == "reject":
        return set_label(take_id, REJECTED)
    if take["label"] == FINAL:
        return take
    if flag == "keep":
        return set_label(take_id, CANDIDATE)
    return set_label(take_id, DRAFT) if take["label"] in (CANDIDATE, REJECTED) else take


def migrate_labels() -> int:
    """Label the takes stored before labels from their former marks; returns how many were labelled."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {TAKES} SET label = CASE WHEN chosen = 1 THEN ? WHEN flag = 'keep' THEN ? "
            "WHEN flag = 'reject' THEN ? ELSE ? END WHERE label IS NULL OR label NOT IN (?, ?, ?, ?)",
            (FINAL, CANDIDATE, REJECTED, DRAFT, *LABELS),
        )
        return cursor.rowcount


def delete_take(take_id: str) -> bool:
    """Delete a take, its jobs and its look; False when there was no such take."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {JOBS} WHERE take_id = ?", (take_id,))
        cursor.execute(f"DELETE FROM {LOOKS} WHERE key = ?", (f"take:{take_id}",))
        cursor.execute(f"DELETE FROM {TAKES} WHERE id = ?", (take_id,))
        return cursor.rowcount > 0


def add_job(take_id: str, generation_id: str, limit_ref_id: Optional[str], units: float) -> str:
    """Record that a take was handed to the core with the minutes it reserves."""
    from src.plugin_api import db

    job_id = generate_ulid()
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {JOBS} (id, take_id, generation_id, limit_ref_id, units_reserved, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, take_id, generation_id, limit_ref_id, units, _now()),
        )
    return job_id


def close_jobs(take_id: str) -> None:
    """Mark the open jobs of a take finished."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"UPDATE {JOBS} SET finished_at = ? WHERE take_id = ? AND finished_at IS NULL", (_now(), take_id))


def list_jobs(take_id: str) -> List[Dict[str, Any]]:
    """The jobs of a take, oldest first."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT id, take_id, generation_id, limit_ref_id, units_reserved, started_at, finished_at FROM {JOBS} "
            "WHERE take_id = ? ORDER BY started_at, id",
            (take_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def add_calibration(preset_id: str, backend_id: str, resolution: str, seconds: float, duration_ms: int) -> None:
    """Record how long a take of this many seconds took on a backend at a resolution."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {CALIBRATION} (preset_id, backend_id, resolution, seconds, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (preset_id, backend_id, resolution, seconds, duration_ms, _now()),
        )


def calibration(
    preset_id: str, backend_id: Optional[str], resolution: str, limit: int = CALIBRATION_ROWS
) -> List[Tuple[float, int]]:
    """The latest measures of a preset at a resolution on the backend that rendered them, newest first; none without a backend."""
    from src.plugin_api import db

    if not backend_id:
        return []
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT seconds, duration_ms FROM {CALIBRATION} WHERE preset_id = ? AND backend_id = ? AND resolution = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (preset_id, backend_id, resolution, limit),
        )
        return [(float(row["seconds"]), int(row["duration_ms"])) for row in cursor.fetchall()]


def chain_waiting() -> List[Dict[str, Any]]:
    """The queued takes that wait for the last image of the previous shot before the queue may hand them over, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE {_CHAIN_WAIT_SQL} ORDER BY created_at, id")


def take_frame(take_id: str, chain: Dict[str, Any], request: Dict[str, Any]) -> bool:
    """Record the first image a waiting take got and the request that carries it, the take joining the queue; False when it no longer waits."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {TAKES} SET chain = ?, request = ?, chain_wait = 0 WHERE id = ? AND {_CHAIN_WAIT_SQL}",
            (json.dumps(chain), json.dumps(request), take_id),
        )
        return cursor.rowcount == 1
