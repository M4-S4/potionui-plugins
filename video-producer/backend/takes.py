import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .core_bridge import generate_ulid

TAKES = "video_producer_takes"
JOBS = "video_producer_jobs"
CALIBRATION = "video_producer_calibration"

ACTIVE = ("queued", "running")

FLAGS = ("keep", "reject")

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
)

_ACTIVE_SQL = "status IN ('queued', 'running')"

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {TAKES}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now() -> str:
    """The current time as the takes store it, ISO 8601 in UTC."""
    return _now()


def _take(row: Any) -> Dict[str, Any]:
    take = {column: row[column] for column in COLUMNS}
    take["chosen"] = bool(take["chosen"])
    take["units_reserved"] = float(take["units_reserved"] or 0)
    take["request"] = json.loads(take["request"]) if take["request"] else None
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
    take.update({"id": generate_ulid(), "status": "queued", "chosen": False, "units_reserved": 0.0, "created_at": _now()})
    take.update({key: value for key, value in fields.items() if key in COLUMNS})
    values = {**take, "chosen": int(bool(take["chosen"])), "request": json.dumps(take["request"]) if take["request"] else None}
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


def list_takes(project_id: str) -> List[Dict[str, Any]]:
    """The takes of a project, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE project_id = ? ORDER BY created_at, id", (project_id,))


def list_active(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """The queued and running takes, of one project or of all, oldest first."""
    if project_id is None:
        return _fetch_all(f"{_SELECT} WHERE {_ACTIVE_SQL} ORDER BY created_at, id")
    return _fetch_all(f"{_SELECT} WHERE project_id = ? AND {_ACTIVE_SQL} ORDER BY created_at, id", (project_id,))


def waiting(user_id: str) -> List[Dict[str, Any]]:
    """The user's queued takes not yet handed to the core, oldest first."""
    return _fetch_all(
        f"{_SELECT} WHERE user_id = ? AND status = 'queued' AND generation_id IS NULL ORDER BY created_at, id", (user_id,)
    )


def waiting_user_ids() -> List[str]:
    """The users with queued takes not yet handed to the core."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT user_id, MIN(created_at) AS first FROM {TAKES} "
            "WHERE status = 'queued' AND generation_id IS NULL AND user_id IS NOT NULL GROUP BY user_id ORDER BY first"
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


def choose(take_id: str, chosen: bool) -> Optional[Dict[str, Any]]:
    """Mark a take as the one kept for its shot, unmarking the others, or unmark it."""
    from src.plugin_api import db

    take = get_take(take_id)
    if take is None:
        return None
    with db.get_cursor() as cursor:
        if chosen:
            cursor.execute(
                f"UPDATE {TAKES} SET chosen = 0 WHERE project_id = ? AND shot_id = ? AND id != ?",
                (take["project_id"], take["shot_id"], take_id),
            )
        cursor.execute(f"UPDATE {TAKES} SET chosen = ? WHERE id = ?", (int(chosen), take_id))
    return get_take(take_id)


def set_flag(take_id: str, flag: Optional[str]) -> Optional[Dict[str, Any]]:
    """Flag a take as kept or rejected, or clear its flag."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"UPDATE {TAKES} SET flag = ? WHERE id = ?", (flag, take_id))
    return get_take(take_id)


def delete_take(take_id: str) -> bool:
    """Delete a take and its jobs; False when there was no such take."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {JOBS} WHERE take_id = ?", (take_id,))
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
    """The latest measures of a preset at a resolution, on one backend or on any, newest first."""
    from src.plugin_api import db

    query = f"SELECT seconds, duration_ms FROM {CALIBRATION} WHERE preset_id = ? AND resolution = ?"
    params: Tuple[Any, ...] = (preset_id, resolution)
    if backend_id:
        query += " AND backend_id = ?"
        params += (backend_id,)
    with db.get_cursor() as cursor:
        cursor.execute(query + " ORDER BY created_at DESC, rowid DESC LIMIT ?", (*params, limit))
        return [(float(row["seconds"]), int(row["duration_ms"])) for row in cursor.fetchall()]
