import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from .. import core_bridge

ULID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")

MIB = 1024 * 1024

RENDERS = "renders"

WORK = "work"


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
    """The scene storage of one project: its splat and glb files, its renders and its work files."""
    return scenes_base() / project_id


def renders_folder(project_id: str) -> Path:
    """The folders of the project's renders in progress."""
    return project_folder(project_id) / RENDERS


def work_folder(project_id: str) -> Path:
    """The folder of the project's short-lived files: uploads being checked and captures being stored."""
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
