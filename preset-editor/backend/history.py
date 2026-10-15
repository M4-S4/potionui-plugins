import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import paths
from .drafts import HISTORY_META_FILE, DraftError, ignore_private, read_header
from .paths import Roots


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%f")


def archive(roots: Roots, preset_dir: Path, *, preset_id: str, target_dir: str, reason: str) -> str:
    header = read_header(preset_dir)
    root = paths.history_root(roots, preset_id)
    root.mkdir(parents=True, exist_ok=True)
    stamp = stamp_now()
    while (root / stamp).exists():
        stamp = stamp_now()
    entry = root / stamp
    shutil.copytree(preset_dir, entry, ignore=ignore_private)
    meta = {
        "preset_id": preset_id,
        "target_dir": target_dir,
        "reason": reason,
        "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "name": header.get("name"),
        "version": header.get("version"),
    }
    (entry / HISTORY_META_FILE).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return stamp


def _read_meta(entry: Path) -> Dict[str, Any]:
    meta = entry / HISTORY_META_FILE
    if not meta.is_file():
        return {}
    return json.loads(meta.read_text(encoding="utf-8"))


def list_entries(roots: Roots, preset_id: str) -> List[Dict[str, Any]]:
    root = paths.history_root(roots, preset_id)
    entries = []
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and paths.STAMP_RE.match(entry.name):
                entries.append({"stamp": entry.name, **_read_meta(entry)})
    return sorted(entries, key=lambda item: item["stamp"], reverse=True)


def entry_dir(roots: Roots, preset_id: str, stamp: str) -> Path:
    try:
        entry = paths.history_entry(roots, preset_id, stamp)
    except ValueError as error:
        raise DraftError("not_found", f"no history entry {stamp!r} for {preset_id!r}") from error
    if not (entry / "preset.yml").is_file():
        raise DraftError("not_found", f"no history entry {stamp!r} for {preset_id!r}")
    return entry


def rotate(roots: Roots, preset_id: str, depth: int) -> List[str]:
    removed = []
    for entry in list_entries(roots, preset_id)[max(depth, 1):]:
        shutil.rmtree(paths.history_entry(roots, preset_id, entry["stamp"]))
        removed.append(entry["stamp"])
    return removed
