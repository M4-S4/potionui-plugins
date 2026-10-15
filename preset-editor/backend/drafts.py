import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.plugin_api.storage import generate_ulid

from . import paths
from .paths import Roots

META_FILE = ".preset-editor.json"
HISTORY_META_FILE = ".preset-editor-history.json"
IGNORED_NAMES = frozenset({META_FILE, HISTORY_META_FILE, "__pycache__", ".pytest_cache"})


class DraftError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Draft:
    draft_id: str
    preset_id: str
    name: str
    source: str
    target_dir: str
    created_by: str
    created_at: str
    updated_at: str
    published_at: Optional[str] = None
    last_lint: Optional[Dict[str, Any]] = None
    dir: Path = field(default=Path(), compare=False, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        del data["dir"]
        return data


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ignore_private(_directory: str, names: List[str]) -> List[str]:
    return [name for name in names if name in IGNORED_NAMES]


def read_header(preset_dir: Path) -> Dict[str, Any]:
    manifest = preset_dir / "preset.yml"
    if not manifest.is_file():
        raise DraftError("invalid_preset", f"{preset_dir} has no preset.yml")
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise DraftError("invalid_preset", f"preset.yml could not be parsed: {error}") from error
    if not isinstance(data, dict):
        raise DraftError("invalid_preset", "preset.yml is not a mapping")
    return data


def rewrite_top_level(text: str, values: Dict[str, str]) -> str:
    if text and not text.endswith("\n"):
        text += "\n"
    for key, value in values.items():
        line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
        pattern = re.compile(rf"^{re.escape(key)}:[ \t]*.*$", re.MULTILINE)
        text, count = pattern.subn(lambda _match: line, text, count=1)
        if count == 0:
            text += line + "\n"
    return text


def save(draft: Draft) -> Draft:
    draft.updated_at = now()
    (draft.dir / META_FILE).write_text(json.dumps(draft.to_dict(), indent=2) + "\n", encoding="utf-8")
    return draft


def load(roots: Roots, draft_id: str) -> Draft:
    try:
        directory = paths.draft_dir(roots, draft_id)
    except ValueError as error:
        raise DraftError("not_found", f"no draft {draft_id!r}") from error
    meta = directory / META_FILE
    if not meta.is_file():
        raise DraftError("not_found", f"no draft {draft_id!r}")
    data = json.loads(meta.read_text(encoding="utf-8"))
    return Draft(**data, dir=directory)


def list_drafts(roots: Roots) -> List[Draft]:
    found = []
    if roots.drafts.is_dir():
        for entry in roots.drafts.iterdir():
            if entry.is_dir() and (entry / META_FILE).is_file() and paths.DRAFT_ID_RE.match(entry.name):
                found.append(load(roots, entry.name))
    return sorted(found, key=lambda draft: (draft.created_at, draft.draft_id), reverse=True)


def delete(roots: Roots, draft_id: str) -> None:
    draft = load(roots, draft_id)
    shutil.rmtree(draft.dir)


def _create(roots: Roots, *, source_dir: Path, preset_id: str, name: str, target_dir: str, created_by: str,
            source: str, rewrite: bool) -> Draft:
    paths.check_preset_id(preset_id)
    target_dir = paths.check_target_dir(target_dir)
    read_header(source_dir)
    roots.drafts.mkdir(parents=True, exist_ok=True)
    draft_id = generate_ulid()
    directory = roots.drafts / draft_id
    shutil.copytree(source_dir, directory, ignore=ignore_private)
    if rewrite:
        manifest = directory / "preset.yml"
        manifest.write_text(
            rewrite_top_level(manifest.read_text(encoding="utf-8"), {"id": preset_id, "name": name}), encoding="utf-8"
        )
    stamp = now()
    draft = Draft(
        draft_id=draft_id, preset_id=preset_id, name=name, source=source, target_dir=target_dir,
        created_by=created_by, created_at=stamp, updated_at=stamp, dir=directory,
    )
    return save(draft)


def create_copy(roots: Roots, *, source_dir: Path, preset_id: str, name: str, target_dir: str, created_by: str,
                source: str) -> Draft:
    return _create(
        roots, source_dir=source_dir, preset_id=preset_id, name=name, target_dir=target_dir, created_by=created_by,
        source=source, rewrite=True,
    )


def create_blank(roots: Roots, *, files: Dict[str, str], preset_id: str, name: str, target_dir: str,
                 created_by: str) -> Draft:
    paths.check_preset_id(preset_id)
    target_dir = paths.check_target_dir(target_dir)
    roots.drafts.mkdir(parents=True, exist_ok=True)
    draft_id = generate_ulid()
    directory = roots.drafts / draft_id
    directory.mkdir()
    for relative, content in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    stamp = now()
    draft = Draft(
        draft_id=draft_id, preset_id=preset_id, name=name, source="blank", target_dir=target_dir,
        created_by=created_by, created_at=stamp, updated_at=stamp, dir=directory,
    )
    return save(draft)


def create_edit(roots: Roots, *, source_dir: Path, preset_id: str, name: str, target_dir: str,
                created_by: str) -> Draft:
    return _create(
        roots, source_dir=source_dir, preset_id=preset_id, name=name, target_dir=target_dir, created_by=created_by,
        source=f"edit_of:{preset_id}", rewrite=False,
    )


def file_tree(directory: Path) -> List[Dict[str, Any]]:
    files = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(part in IGNORED_NAMES for part in relative.parts) or not path.is_file():
            continue
        files.append({"path": relative.as_posix(), "size": path.stat().st_size})
    return files


def record_lint(draft: Draft, errors: List[str], warnings: List[str]) -> Draft:
    draft.last_lint = {"errors": list(errors), "warnings": list(warnings), "at": now()}
    return save(draft)


def mark_published(draft: Draft) -> Draft:
    draft.published_at = now()
    return save(draft)
