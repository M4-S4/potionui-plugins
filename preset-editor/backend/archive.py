import io
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List

from . import files
from .drafts import IGNORED_NAMES
from .files import MANIFEST, MEDIA_EXTENSIONS, TEXT_EXTENSIONS, FilesError

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_RATIO = 200
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | MEDIA_EXTENSIONS
SKIPPED_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"}) | IGNORED_NAMES
SKIPPED_FOLDERS = frozenset({"__MACOSX"})
CHUNK = 1024 * 1024


def _exportable(relative: PurePosixPath) -> bool:
    return not any(part in SKIPPED_NAMES or part.startswith(".") for part in relative.parts)


def export_dir(directory: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            relative = PurePosixPath(path.relative_to(directory).as_posix())
            if path.is_symlink() or not path.is_file() or not _exportable(relative):
                continue
            archive.write(path, str(relative))
    return buffer.getvalue()


def _skipped(name: str) -> bool:
    parts = name.split("/")
    return parts[0] in SKIPPED_FOLDERS or parts[-1] in SKIPPED_NAMES


def _members(archive: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise FilesError("too_large", f"the archive has more than {MAX_ENTRIES} entries")
    members = []
    total = 0
    for info in entries:
        if info.is_dir() or _skipped(info.filename):
            continue
        kind = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
        if kind == stat.S_IFLNK:
            raise FilesError("invalid_request", f"{info.filename} is a link")
        if kind not in (0, stat.S_IFREG):
            raise FilesError("invalid_request", f"{info.filename} is not a regular file")
        total += info.file_size
        if total > MAX_EXTRACTED_BYTES:
            raise FilesError("too_large", f"the archive unpacks to more than {MAX_EXTRACTED_BYTES // (1024 * 1024)} MiB")
        if info.file_size > CHUNK and info.file_size > MAX_RATIO * max(info.compress_size, 1):
            raise FilesError("invalid_request", f"{info.filename} inflates more than {MAX_RATIO} times")
        members.append(info)
    if not members:
        raise FilesError("invalid_request", "the archive holds no file")
    return members


def _strip_prefix(names: List[str]) -> str:
    if MANIFEST in names:
        return ""
    first = names[0].split("/", 1)
    if len(first) == 2 and first[0] and all(name.startswith(f"{first[0]}/") for name in names):
        return f"{first[0]}/"
    return ""


def plan(data: bytes) -> Dict[zipfile.ZipInfo, PurePosixPath]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise FilesError("too_large", f"the archive is larger than {MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as failure:
        raise FilesError("invalid_request", "the file is not a zip archive") from failure
    members = _members(archive)
    prefix = _strip_prefix([info.filename for info in members])
    relative: Dict[zipfile.ZipInfo, PurePosixPath] = {}
    seen = set()
    for info in members:
        name = info.filename[len(prefix):]
        try:
            path = files.relative_path(name)
        except FilesError as failure:
            raise FilesError("invalid_request", f"{info.filename}: {failure.message}") from failure
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise FilesError("invalid_request", f"{info.filename}: only {', '.join(sorted(ALLOWED_EXTENSIONS))} files")
        if str(path) in seen:
            raise FilesError("invalid_request", f"{info.filename} appears twice")
        seen.add(str(path))
        relative[info] = path
    if MANIFEST not in seen:
        raise FilesError("invalid_request", f"{MANIFEST} is missing at the root of the archive")
    return relative


def extract(data: bytes, destination: Path) -> List[str]:
    relative = plan(data)
    destination.mkdir(parents=True, exist_ok=False)
    written: List[str] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info, path in relative.items():
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, "wb") as sink:
                    while True:
                        chunk = source.read(CHUNK)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_EXTRACTED_BYTES:
                            raise FilesError("too_large", f"the archive unpacks to more than {MAX_EXTRACTED_BYTES // (1024 * 1024)} MiB")
                        sink.write(chunk)
                written.append(str(path))
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return written
