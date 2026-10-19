import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, BinaryIO, Dict, List, Optional, Tuple

try:
    from python_multipart.multipart import MultipartParser, parse_options_header
except ImportError:
    from multipart.multipart import MultipartParser, parse_options_header

from .. import limits, projects
from ..core_bridge import generate_ulid
from . import formats, storage
from .formats import Probe
from .storage import GIB, MIB, SceneError

FILES = "video_producer_scene_files"

MAX_BYTES = 1024 * MIB

PROJECT_MAX_BYTES = 20 * GIB

ORPHAN_SECONDS = 24 * 3600

MULTIPART_MARGIN = 64 * 1024

FIELD_LIMIT = 1024

FIELD_COUNT = 8

FILE_FIELD = "file"

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


def _bytes(column: str, value: str) -> int:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT COALESCE(SUM(size), 0) AS total FROM {FILES} WHERE {column} = ?", (value,))
        return int(cursor.fetchone()["total"] or 0)


def ensure_room(project_id: str, owner_id: str, incoming: int, upload: bool = False) -> None:
    """Refuse a scene file of incoming bytes that would take the project past its cap or its owner past the storage plan, counting the owner's scene files on top of what the core measures; an upload also meets the plan's largest file. SceneError 413 otherwise."""
    used = _bytes("project_id", project_id)
    if used + incoming > PROJECT_MAX_BYTES:
        raise SceneError(
            413, "storage_full", f"The scene files of a project take at most {PROJECT_MAX_BYTES // GIB} GiB.", limit=PROJECT_MAX_BYTES, used=used, needed=incoming
        )
    largest = limits.upload_size_status(owner_id)["remaining"] if upload else None
    if largest is not None and incoming > largest:
        raise SceneError(413, "file_too_large", "The file is larger than the storage plan allows for one upload.", limit=int(largest))
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


def accepted_format(kind: str, filename: str) -> str:
    """The format of an upload of a kind, from its file name; SceneError when the kind does not take it."""
    fmt = formats.format_of(filename)
    allowed = formats.KINDS[kind]
    if fmt not in allowed:
        raise SceneError(422, "unsupported_format", f"A {kind} upload must be a {', '.join('.' + name for name in allowed)} file.")
    return fmt


def _invalid(message: str) -> SceneError:
    return SceneError(422, "invalid_request", message)


class UploadForm:
    """A multipart form read as it arrives: its few small fields kept in memory, its one file written straight into the work folder."""

    def __init__(self, folder: Path, file_id: str):
        self.folder = folder
        self.file_id = file_id
        self.fields: Dict[str, str] = {}
        self.filename: Optional[str] = None
        self.path: Optional[Path] = None
        self.size = 0
        self.pending: List[bytes] = []
        self.handle: Optional[BinaryIO] = None
        self.created: List[Path] = []
        self.open_part = False
        self._header = b""
        self._value = b""
        self._disposition = b""
        self._name: Optional[str] = None
        self._file = False
        self._data = bytearray()

    def callbacks(self) -> Dict[str, Any]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }

    def on_part_begin(self) -> None:
        self.open_part = True
        self._disposition, self._name, self._file, self._data = b"", None, False, bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def on_header_end(self) -> None:
        if self._header.strip().lower() == b"content-disposition":
            self._disposition = self._value
        self._header, self._value = b"", b""

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._disposition)
        if b"name" not in options:
            raise _invalid("Each part of the form needs a name.")
        self._name = options[b"name"].decode("utf-8", "replace")
        if b"filename" not in options:
            if len(self.fields) >= FIELD_COUNT:
                raise _invalid("The form has too many fields.")
            return
        if self._name != FILE_FIELD or self.filename is not None:
            raise _invalid(f"The form takes one file, in the field {FILE_FIELD}.")
        self.filename = options[b"filename"].decode("utf-8", "replace")
        fmt = formats.format_of(self.filename)
        if fmt is None:
            raise SceneError(422, "unsupported_format", "A scene file must be a .ply, .spz, .splat or .glb file.")
        self.created = [folder for folder in (self.folder.parent, self.folder) if not folder.exists()]
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / f"upload-{self.file_id}.{fmt}"
        self.handle = self.path.open("wb")
        self._file = True

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._file:
            self.size += end - start
            if self.size > MAX_BYTES:
                raise SceneError(413, "file_too_large", f"A scene file is at most {MAX_BYTES // MIB} MiB.")
            self.pending.append(bytes(data[start:end]))
            return
        self._data += data[start:end]
        if len(self._data) > FIELD_LIMIT:
            raise _invalid(f"A field of the form is longer than {FIELD_LIMIT} bytes.")

    def on_part_end(self) -> None:
        self.open_part = False
        if not self._file and self._name is not None:
            self.fields[self._name] = self._data.decode("utf-8", "replace")
        self._file = False

    def write(self, chunks: List[bytes]) -> None:
        if self.handle is not None:
            self.handle.writelines(chunks)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None

    def drop(self, stored: bool) -> None:
        self.close()
        if self.path is not None:
            self.path.unlink(missing_ok=True)
        for folder in [] if stored else reversed(self.created):
            try:
                folder.rmdir()
            except OSError:
                pass


async def read_form(form: UploadForm, content_type: str, stream: AsyncIterator[bytes]) -> None:
    """Feed a multipart body to the form as it arrives, writing the file off the event loop; SceneError for a body that is not such a form."""
    mime, options = parse_options_header(content_type)
    if mime != b"multipart/form-data" or not options.get(b"boundary"):
        raise _invalid("The request needs a file, sent as multipart/form-data.")
    parser = MultipartParser(options[b"boundary"], form.callbacks())
    try:
        async for chunk in stream:
            if chunk:
                parser.write(chunk)
            if form.pending:
                chunks, form.pending = form.pending, []
                await asyncio.to_thread(form.write, chunks)
        parser.finalize()
    except ValueError:
        raise _invalid("The request body is not a valid multipart form.") from None
    if form.open_part:
        raise _invalid("The form ends before its last part.")
    await asyncio.to_thread(form.close)


async def receive_upload(project_id: str, user_id: str, content_type: str, stream: AsyncIterator[bytes]) -> Dict[str, Any]:
    """Store the splat or glb file of a multipart form (fields file and kind) of at most 1 GiB, written once into the work folder as it arrives, checked against the storage room and its format, then moved into place; SceneError otherwise."""
    file_id = generate_ulid()
    form = UploadForm(storage.work_folder(project_id), file_id)
    stored = False
    try:
        await read_form(form, content_type, stream)
        kind = form.fields.get("kind")
        if kind not in formats.KINDS:
            raise _invalid(f"kind must be one of: {', '.join(formats.KINDS)}.")
        if form.path is None or not form.filename:
            raise _invalid("The request needs a file.")
        fmt = accepted_format(kind, form.filename)
        ensure_room(project_id, user_id, form.size, upload=True)
        try:
            probe = await asyncio.to_thread(formats.probe, fmt, form.path)
        except formats.FormatError as exc:
            raise SceneError(422, "invalid_file", str(exc)) from None
        target = storage.project_folder(project_id) / stored_name(file_id, fmt)
        form.path.replace(target)
        stored = True
    finally:
        form.drop(stored)
    return add_file(file_id, project_id, user_id, kind, Path(form.filename.replace("\\", "/")).name, form.size, probe)
