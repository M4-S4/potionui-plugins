import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import limits, projects
from . import storage
from .formats import Probe
from .storage import GIB, SceneError

FILES = "video_producer_scene_files"

PROJECT_MAX_BYTES = 20 * GIB

ORPHAN_SECONDS = 24 * 3600

NAME_LIMIT = 200

COLUMNS = (
    "id",
    "project_id",
    "user_id",
    "kind",
    "format",
    "name",
    "stored_name",
    "size",
    "splat_count",
    "view",
    "cameras",
    "job_id",
    "created_at",
)

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {FILES}"


def _file(row: Any) -> Dict[str, Any]:
    found = {column: row[column] for column in COLUMNS}
    found["view"] = json.loads(found["view"]) if found["view"] else None
    found["cameras"] = json.loads(found["cameras"]) if found["cameras"] else None
    return found


def _fetch(query: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        return [_file(row) for row in cursor.fetchall()]


def get_file(file_id: str) -> Optional[Dict[str, Any]]:
    """One scene file, or None."""
    found = _fetch(f"{_SELECT} WHERE id = ?", (file_id,))
    return found[0] if found else None


def list_project(project_id: str) -> List[Dict[str, Any]]:
    """The scene files of a project, oldest first."""
    return _fetch(f"{_SELECT} WHERE project_id = ? ORDER BY created_at, id", (project_id,))


def path_of(found: Dict[str, Any]) -> Path:
    """Where a scene file is stored."""
    return storage.project_folder(found["project_id"]) / found["stored_name"]


def stored_name(file_id: str, fmt: str) -> str:
    """The name a scene file is stored under: its id and its format."""
    return f"{file_id}.{fmt}"


def add_file(
    file_id: str,
    project_id: str,
    user_id: str,
    kind: str,
    name: str,
    size: int,
    probe: Probe,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a scene file already stored under its id."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {FILES} ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
            (
                file_id,
                project_id,
                user_id,
                kind,
                probe.format,
                name[:NAME_LIMIT],
                stored_name(file_id, probe.format),
                size,
                probe.count,
                json.dumps(probe.view) if probe.view else None,
                None,
                job_id,
                storage.now(),
            ),
        )
    return get_file(file_id)


def delete_file(found: Dict[str, Any]) -> None:
    """Delete a scene file and its row."""
    from src.plugin_api import db

    path_of(found).unlink(missing_ok=True)
    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {FILES} WHERE id = ?", (found["id"],))


def forget_project(project_id: str) -> None:
    """Delete the rows of a deleted project's scene files; its folder goes with the rest of its scene storage."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {FILES} WHERE project_id = ?", (project_id,))


def _bytes(column: str, value: str) -> int:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT COALESCE(SUM(size), 0) AS total FROM {FILES} WHERE {column} = ?", (value,))
        return int(cursor.fetchone()["total"] or 0)


def ensure_room(project_id: str, owner_id: str, incoming: int) -> None:
    """Refuse a scene file of incoming bytes that would take the project past its cap or its owner past the storage plan, counting the owner's scene files on top of what the core measures. SceneError 413 otherwise."""
    used = _bytes("project_id", project_id)
    if used + incoming > PROJECT_MAX_BYTES:
        raise SceneError(
            413, "storage_full", f"The scene files of a project take at most {PROJECT_MAX_BYTES // GIB} GiB.", limit=PROJECT_MAX_BYTES, used=used, needed=incoming
        )
    remaining = limits.storage_status(owner_id)["remaining"]
    if remaining is None:
        return
    left = max(0, int(remaining) - _bytes("user_id", owner_id))
    if incoming > left:
        raise SceneError(413, "storage_full", "The storage plan of the project owner is full.", remaining=left, needed=incoming)


def _cited(found: Dict[str, Any]) -> bool:
    from src.plugin_api import db

    marker = f'"fileId":"{found["id"]}"'
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT 1 FROM {projects.PROJECTS} WHERE id = ? AND instr(doc, ?) > 0 "
            f"UNION ALL SELECT 1 FROM {projects.VERSIONS} WHERE project_id = ? AND instr(doc, ?) > 0 LIMIT 1",
            (found["project_id"], marker, found["project_id"], marker),
        )
        return cursor.fetchone() is not None


def _created(found: Dict[str, Any]) -> float:
    try:
        return datetime.fromisoformat(found["created_at"]).timestamp()
    except (TypeError, ValueError):
        return time.time()


def _strays(project: Path, limit: float) -> int:
    kept = {found["stored_name"] for found in list_project(project.name)}
    removed = 0
    for entry in project.iterdir():
        try:
            stray = entry.is_file() and entry.name not in kept and entry.stat().st_mtime < limit
        except OSError:
            continue
        if stray:
            entry.unlink(missing_ok=True)
            removed += 1
    return removed


def collect_orphans(min_age: float = ORPHAN_SECONDS, now: Optional[float] = None) -> int:
    """Delete the scene files that neither the current document of their project nor any of its stored versions cites by fileId, and the files of a project folder no row knows, never one younger than a day; returns how many it deleted."""
    limit = (time.time() if now is None else now) - min_age
    removed = 0
    for found in _fetch(_SELECT, ()):
        if _created(found) < limit and not _cited(found):
            delete_file(found)
            removed += 1
    for project in storage.folders(storage.scenes_base()):
        try:
            removed += _strays(project, limit)
        except OSError:
            continue
    return removed
