import tempfile
from pathlib import Path
from typing import Optional

from . import core_bridge

ROOT = "video_producer"

EXPORTS = "exports"
FRAMES = "frames"
AUDIO = "audio"

PROBE = ".writable-"


class WorkdirError(Exception):
    """A work folder under the file storage directory that cannot be created or written to, with the code every caller answers it under."""

    code = "workdir_unwritable"

    def __init__(self, folder: Path, cause: OSError):
        super().__init__(f"Video Producer cannot write in {folder}: {cause.strerror or cause}. The file storage directory must be a local, writable folder on this server, even when the media are kept in object storage.")
        self.folder = folder
        self.cause = cause
        self.message = str(self)


def root() -> Path:
    """The folder of every work file of the plugin, under the application's file storage directory; not created."""
    return core_bridge.storage_directory() / ROOT


def area(name: str, owner_id: Optional[str] = None) -> Path:
    """The folder of one kind of work file, of one user when given; not created."""
    folder = root() / name
    return folder / owner_id if owner_id else folder


def make(folder: Path) -> Path:
    """The folder, created with its parents; WorkdirError when the file storage directory is missing, read-only or not a directory."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkdirError(folder, exc) from None
    return folder


def ensure(name: str, owner_id: Optional[str] = None) -> Path:
    """The folder of one kind of work file, of one user when given, created; WorkdirError as make."""
    return make(area(name, owner_id))


def scratch(name: str, owner_id: str) -> Path:
    """A new empty folder of a user under one kind of work file; WorkdirError as make."""
    base = ensure(name, owner_id)
    try:
        return Path(tempfile.mkdtemp(dir=base))
    except OSError as exc:
        raise WorkdirError(base, exc) from None


def check() -> Path:
    """The root work folder, created and written to once with a probe file that is deleted at once; WorkdirError when either fails."""
    folder = root()
    make(folder)
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=PROBE):
            pass
    except OSError as exc:
        raise WorkdirError(folder, exc) from None
    return folder
