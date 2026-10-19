import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core_bridge import generate_ulid
from . import formats, storage
from .formats import Probe
from .storage import SceneError

FILES = "video_producer_scene_files"

MAX_BYTES = 1024 * 1024 * 1024

CHUNK = 1024 * 1024

NAME_LIMIT = 200

FILE_URL = "/api/plugins/video-producer/projects/{project_id}/scene-files/{file_id}"

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


def public(found: Dict[str, Any]) -> Dict[str, Any]:
    """A scene file as the API returns it."""
    return {
        "id": found["id"],
        "kind": found["kind"],
        "format": found["format"],
        "name": found["name"],
        "size": found["size"],
        "count": found["splat_count"],
        "view": found["view"],
        "cameras": found["cameras"],
        "url": FILE_URL.format(project_id=found["project_id"], file_id=found["id"]),
        "created_at": found["created_at"],
    }


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
                json.dumps(probe.cameras) if probe.cameras is not None else None,
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


def accepted_format(kind: str, filename: str) -> str:
    """The format of an upload of a kind, from its file name; SceneError when the kind does not take it."""
    fmt = formats.format_of(filename)
    allowed = formats.KINDS[kind]
    if fmt not in allowed:
        raise SceneError(422, "unsupported_format", f"A {kind} upload must be a {', '.join('.' + name for name in allowed)} file.")
    return fmt


async def store_upload(project_id: str, user_id: str, kind: str, upload: Any) -> Dict[str, Any]:
    """Store an uploaded splat or glb file of at most 1 GiB after checking its format; SceneError otherwise."""
    filename = str(getattr(upload, "filename", "") or "")
    fmt = accepted_format(kind, filename)
    folder = storage.work_folder(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    file_id = generate_ulid()
    work = folder / f"upload-{file_id}.{fmt}"
    size = 0
    try:
        with work.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise SceneError(413, "file_too_large", "A scene file is at most 1 GiB.")
                handle.write(chunk)
        try:
            probe = await asyncio.to_thread(formats.probe, fmt, work)
        except formats.FormatError as exc:
            raise SceneError(422, "invalid_file", str(exc)) from None
        target = storage.project_folder(project_id) / stored_name(file_id, fmt)
        work.replace(target)
    finally:
        work.unlink(missing_ok=True)
    return add_file(file_id, project_id, user_id, kind, Path(filename.replace("\\", "/")).name, size, probe)
