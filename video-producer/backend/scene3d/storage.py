import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from .. import core_bridge

ULID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")

MIB = 1024 * 1024

GIB = 1024 * MIB

WORK = "work"

STALE_SECONDS = 3600


class SceneError(Exception):
    """A scene request the plugin refuses or cannot carry out, with its HTTP status, error code and data."""

    def __init__(self, status_code: int, error: str, message: str, **data: Any):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.data = data


def now() -> str:
    """The current time as the scene tables store it, ISO 8601 in UTC."""
    return datetime.now(timezone.utc).isoformat()


def is_id(value: object) -> bool:
    """True for an id the plugin generated, the only kind a scene path is built from."""
    return isinstance(value, str) and ULID.fullmatch(value) is not None


def scenes_base() -> Path:
    """The scene storage of every project."""
    return core_bridge.storage_directory() / "video_producer" / "scenes"


def project_folder(project_id: str) -> Path:
    """The scene storage of one project: its splat files and its work files."""
    return scenes_base() / project_id


def work_folder(project_id: str) -> Path:
    """The folder of the project's short-lived files: splats being copied and captures being stored."""
    return project_folder(project_id) / WORK


def folders(path: Path) -> List[Path]:
    """The folders inside a folder; none when it cannot be read."""
    try:
        return [entry for entry in path.iterdir() if entry.is_dir()]
    except OSError:
        return []


def drop(path: Path) -> None:
    """Delete a file or a folder, ignoring what is already gone."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def sweep_work(max_age: float = STALE_SECONDS, now: Optional[float] = None) -> int:
    """Delete the work files left without a write for more than an hour; returns how many it deleted."""
    limit = (time.time() if now is None else now) - max_age
    removed = 0
    for project in folders(scenes_base()):
        try:
            entries = list(work_folder(project.name).iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                idle = entry.stat().st_mtime < limit
            except OSError:
                continue
            if idle:
                drop(entry)
                removed += 1
    return removed
