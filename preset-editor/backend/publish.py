import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.plugin_api.storage import generate_ulid

from . import history, paths
from .drafts import Draft, DraftError, ignore_private, read_header
from .paths import Roots

_lock = threading.Lock()


class PublishError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ids_on_disk(roots: Iterable[Path]) -> Dict[str, List[Path]]:
    found: Dict[str, List[Path]] = {}
    for root in roots:
        if not Path(root).is_dir():
            continue
        for manifest in Path(root).rglob("preset.yml"):
            try:
                preset_id = read_header(manifest.parent).get("id")
            except DraftError:
                continue
            if isinstance(preset_id, str):
                found.setdefault(preset_id, []).append(manifest.parent.resolve())
    return found


def check_collisions(roots: Roots, *, preset_id: str, target_dir: str, catalog: Iterable[Dict[str, Any]],
                     disk_roots: Iterable[Path]) -> None:
    destination = paths.local_preset_dir(roots, target_dir).resolve()
    for info in catalog:
        if info.get("id") != preset_id:
            continue
        origin = info.get("origin") or {}
        if origin.get("kind") != "local" or origin.get("path") != target_dir:
            where = f"plugin '{origin.get('plugin_id')}'" if origin.get("kind") == "plugin" else f"the {origin.get('kind')} presets"
            raise PublishError("id_in_use", f"preset id '{preset_id}' is already used by {where} ({origin.get('path')})")
    for location in ids_on_disk(disk_roots).get(preset_id, []):
        if location != destination:
            raise PublishError("id_in_use", f"preset id '{preset_id}' is already used by the preset at {location}")
    if destination.exists():
        try:
            existing = read_header(destination).get("id")
        except DraftError:
            existing = None
        if existing != preset_id:
            raise PublishError("target_in_use", f"the folder {target_dir} already holds another preset")


def stage(roots: Roots, draft_dir: Path) -> Path:
    roots.staging.mkdir(parents=True, exist_ok=True)
    staging = roots.staging / generate_ulid()
    shutil.copytree(draft_dir, staging, ignore=ignore_private)
    return staging


def swap(target: Path, staging: Path, backup_root: Path) -> Optional[Path]:
    backup: Optional[Path] = None
    try:
        if target.exists():
            backup = backup_root / f"backup-{generate_ulid()}"
            os.replace(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
    except OSError as error:
        if backup is not None and backup.exists() and not target.exists():
            try:
                os.replace(backup, target)
            except OSError as restore_error:
                raise PublishError(
                    "swap_failed",
                    f"could not put the preset in place ({error}) nor restore the previous version ({restore_error}); "
                    f"the previous version is preserved at {backup}",
                ) from restore_error
        shutil.rmtree(staging, ignore_errors=True)
        raise PublishError("swap_failed", f"could not put the preset in place: {error}") from error
    return backup


def publish_draft(roots: Roots, draft: Draft) -> Dict[str, Any]:
    with _lock:
        target = paths.local_preset_dir(roots, draft.target_dir)
        staging = stage(roots, draft.dir)
        backup = swap(target, staging, roots.staging)
    return {"preset_id": draft.preset_id, "target_dir": draft.target_dir, "target": target, "backup": backup}


def commit_publish(roots: Roots, draft: Draft, backup: Optional[Path], *, history_depth: int) -> Optional[str]:
    if backup is None:
        return None
    with _lock:
        archived = history.archive(roots, backup, preset_id=draft.preset_id, target_dir=draft.target_dir, reason="publish")
        shutil.rmtree(backup, ignore_errors=True)
        history.rotate(roots, draft.preset_id, history_depth)
    return archived


def rollback_publish(roots: Roots, target: Path, backup: Optional[Path]) -> None:
    with _lock:
        if target.exists():
            shutil.rmtree(target)
        if backup is not None and backup.exists():
            os.replace(backup, target)
        else:
            _prune_empty_parents(target, roots.local_presets)


def _prune_empty_parents(path: Path, stop: Path) -> None:
    stop = stop.resolve()
    current = path.resolve().parent
    while current != stop and stop in current.parents and current.is_dir() and not any(current.iterdir()):
        current.rmdir()
        current = current.parent


def delete_local_preset(roots: Roots, *, preset_dir: Path, preset_id: str, target_dir: str, history_depth: int) -> str:
    with _lock:
        stamp = history.archive(roots, preset_dir, preset_id=preset_id, target_dir=target_dir, reason="delete")
        shutil.rmtree(preset_dir)
        _prune_empty_parents(preset_dir, roots.local_presets)
        history.rotate(roots, preset_id, history_depth)
    return stamp
