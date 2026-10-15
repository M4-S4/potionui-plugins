import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from src.plugin_api.storage import SettingRepository, Settings

from . import PLUGIN_ID

LOCAL_PRESETS_DIR = Path("content/presets/local")
STAGING_DIR = Path("content/presets/.preset-editor/staging")

PRESET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
DRAFT_ID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
STAMP_RE = re.compile(r"^\d{8}T\d{6}\.\d{6}$")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_TARGET_SEGMENTS = 2


@dataclass(frozen=True)
class Roots:
    drafts: Path
    history: Path
    staging: Path
    local_presets: Path

    def ensure(self) -> None:
        for path in (self.drafts, self.history, self.staging, self.local_presets):
            path.mkdir(parents=True, exist_ok=True)


_current: Optional[Roots] = None


def storage_dir() -> Path:
    return Path(Settings(SettingRepository()).get_file_storage_directory())


def default_roots() -> Roots:
    plugin_storage = storage_dir() / "plugins" / PLUGIN_ID
    return Roots(
        drafts=plugin_storage / "drafts",
        history=plugin_storage / "history",
        staging=STAGING_DIR,
        local_presets=LOCAL_PRESETS_DIR,
    )


def roots() -> Roots:
    global _current
    if _current is None:
        _current = default_roots()
    return _current


def clear_staging(roots: Roots) -> int:
    removed = 0
    if not roots.staging.is_dir():
        return removed
    for entry in roots.staging.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed += 1
    return removed


def check_preset_id(value: str) -> str:
    if not isinstance(value, str) or not PRESET_ID_RE.match(value):
        raise ValueError("a preset id is 3 to 64 letters, digits, '_' or '-'")
    return value


def check_draft_id(value: str) -> str:
    if not isinstance(value, str) or not DRAFT_ID_RE.match(value):
        raise ValueError("not a draft id")
    return value


def check_stamp(value: str) -> str:
    if not isinstance(value, str) or not STAMP_RE.match(value):
        raise ValueError("not a history stamp")
    return value


def check_target_dir(value: str) -> str:
    segments = value.split("/") if isinstance(value, str) else []
    if not 1 <= len(segments) <= MAX_TARGET_SEGMENTS or not all(SEGMENT_RE.match(segment) for segment in segments):
        raise ValueError(
            "the target folder is '<Model>' or '<Model>/<variant>', each name made of letters, digits, '.', '_' or '-' "
            "and starting with a letter or a digit"
        )
    return "/".join(segments)


def target_dir(model_dir: str, variant_dir: Optional[str] = None) -> str:
    parts = [model_dir] + ([variant_dir] if variant_dir else [])
    return check_target_dir("/".join(str(part).strip() for part in parts))


def draft_dir(roots: Roots, draft_id: str) -> Path:
    return roots.drafts / check_draft_id(draft_id)


def local_preset_dir(roots: Roots, target: str) -> Path:
    return roots.local_presets / PurePosixPath(check_target_dir(target))


def history_root(roots: Roots, preset_id: str) -> Path:
    return roots.history / check_preset_id(preset_id)


def history_entry(roots: Roots, preset_id: str, stamp: str) -> Path:
    return history_root(roots, preset_id) / check_stamp(stamp)
