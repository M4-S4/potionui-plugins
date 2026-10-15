import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.plugin_api.storage import SettingRepository, Settings

from . import PLUGIN_ID

LOCAL_PRESETS_DIR = Path("content/presets/local")
STAGING_DIR = Path("content/presets/.preset-editor/staging")


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
