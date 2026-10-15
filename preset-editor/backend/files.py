import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

TEXT_EXTENSIONS = frozenset({".yml", ".yaml", ".md", ".json", ".txt"})
MEDIA_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm"})
MAX_TEXT_BYTES = 1024 * 1024
PUBLIC_DIR = "public"
MANIFEST = "preset.yml"
MODE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class FilesError(Exception):
    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def etag_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or "\x00" in value:
        raise FilesError("invalid_path", "a file path is relative, with '/' between its folders")
    parts = value.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        raise FilesError("invalid_path", "a file path has no '.', '..', empty or hidden segment")
    return PurePosixPath(*parts)


def resolve(draft_dir: Path, value: str) -> Tuple[Path, PurePosixPath]:
    relative = relative_path(value)
    base = draft_dir.resolve()
    target = base
    for part in relative.parts:
        target = target / part
        if target.is_symlink():
            raise FilesError("invalid_path", "a file path never goes through a link")
    resolved = target.resolve()
    if resolved != target or base not in resolved.parents:
        raise FilesError("invalid_path", "a file path stays inside the draft")
    return target, relative


def is_text(relative: PurePosixPath) -> bool:
    return relative.suffix.lower() in TEXT_EXTENSIONS and relative.parts[0] != PUBLIC_DIR


def is_media(relative: PurePosixPath) -> bool:
    return relative.suffix.lower() in MEDIA_EXTENSIONS and relative.parts[0] == PUBLIC_DIR and len(relative.parts) > 1


def read_text(draft_dir: Path, value: str) -> Dict[str, Any]:
    target, relative = resolve(draft_dir, value)
    if not is_text(relative):
        raise FilesError("not_text", "only the YAML, Markdown, JSON and text files outside public/ are read as text")
    if not target.is_file():
        raise FilesError("not_found", f"no file {relative}")
    data = target.read_bytes()
    if len(data) > MAX_TEXT_BYTES:
        raise FilesError("too_large", f"{relative} is larger than {MAX_TEXT_BYTES // 1024} KiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FilesError("not_text", f"{relative} is not UTF-8 text") from error
    return {"path": str(relative), "content": text, "etag": etag_of(data), "size": len(data)}


def write_text(draft_dir: Path, value: str, content: str, if_match: Optional[str]) -> Dict[str, Any]:
    target, relative = resolve(draft_dir, value)
    if not is_text(relative):
        raise FilesError("not_text", "only YAML, Markdown, JSON and text files outside public/ are written here")
    if not isinstance(content, str):
        raise FilesError("invalid_request", "content must be text")
    data = content.encode("utf-8")
    if len(data) > MAX_TEXT_BYTES:
        raise FilesError("too_large", f"the content is larger than {MAX_TEXT_BYTES // 1024} KiB")
    if target.exists():
        if not target.is_file():
            raise FilesError("invalid_path", f"{relative} is not a file")
        current = target.read_bytes()
        if if_match is None:
            raise FilesError("precondition_required", f"{relative} exists: send its etag in If-Match", etag=etag_of(current))
        if if_match != etag_of(current):
            raise FilesError(
                "precondition_failed", f"{relative} changed since it was read", etag=etag_of(current),
                content=current.decode("utf-8", errors="replace"),
            )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.writing")
    temporary.write_bytes(data)
    os.replace(temporary, target)
    return {"path": str(relative), "etag": etag_of(data), "size": len(data)}


def delete_file(draft_dir: Path, value: str) -> Dict[str, Any]:
    target, relative = resolve(draft_dir, value)
    if str(relative) == MANIFEST:
        raise FilesError("invalid_request", "preset.yml cannot be deleted")
    if not target.is_file():
        raise FilesError("not_found", f"no file {relative}")
    target.unlink()
    parent = target.parent
    while parent != draft_dir.resolve() and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    return {"path": str(relative)}


def check_mode_name(value: str) -> str:
    if not isinstance(value, str) or not MODE_NAME_RE.match(value):
        raise FilesError("invalid_request", "a mode name is lowercase letters, digits and '_', starting with a letter")
    return value


def manifest_modes(text: str) -> List[str]:
    block = re.search(r"^modes:[ \t]*$((?:\n[ \t]+-[^\n]*)+)", text, re.MULTILINE)
    if block:
        return [re.sub(r"^[ \t]+-[ \t]*", "", line).strip().strip("\"'") for line in block.group(1).strip("\n").splitlines()]
    flow = re.search(r"^modes:[ \t]*\[([^\]]*)\][ \t]*$", text, re.MULTILINE)
    if flow:
        return [item.strip().strip("\"'") for item in flow.group(1).split(",") if item.strip()]
    return []


def add_mode_to_manifest(text: str, mode: str) -> str:
    if mode in manifest_modes(text):
        return text
    block = re.search(r"^modes:[ \t]*$((?:\n[ \t]+-[^\n]*)+)", text, re.MULTILINE)
    if block:
        lines = block.group(1).strip("\n").splitlines()
        indent = re.match(r"^[ \t]+", lines[-1]).group(0)
        insertion = f"\n{indent}- {mode}"
        return text[: block.end()] + insertion + text[block.end():]
    flow = re.search(r"^modes:[ \t]*\[([^\]]*)\][ \t]*$", text, re.MULTILINE)
    if flow:
        items = [item.strip() for item in flow.group(1).split(",") if item.strip()] + [mode]
        return text[: flow.start()] + f"modes: [{', '.join(items)}]" + text[flow.end():]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + f"modes:\n  - {mode}\n"


def remove_mode_from_manifest(text: str, mode: str) -> str:
    block = re.search(r"^modes:[ \t]*$((?:\n[ \t]+-[^\n]*)+)", text, re.MULTILINE)
    if block:
        kept = [line for line in block.group(1).strip("\n").splitlines() if re.sub(r"^[ \t]+-[ \t]*", "", line).strip().strip("\"'") != mode]
        replacement = ("\n" + "\n".join(kept)) if kept else ""
        return text[: block.start(1)] + replacement + text[block.end(1):]
    flow = re.search(r"^modes:[ \t]*\[([^\]]*)\][ \t]*$", text, re.MULTILINE)
    if flow:
        items = [item.strip() for item in flow.group(1).split(",") if item.strip() and item.strip().strip("\"'") != mode]
        return text[: flow.start()] + f"modes: [{', '.join(items)}]" + text[flow.end():]
    return text
