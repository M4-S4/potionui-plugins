import asyncio
import base64
import binascii
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .. import core_bridge
from ..core_bridge import LimitExceeded, MediaRefError, User, generate_ulid
from ..exports import slug
from ..exports.media import basename
from . import storage
from .storage import SceneError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

MAX_CAPTURE_BYTES = 24 * storage.MIB

BODY_LIMIT = MAX_CAPTURE_BYTES * 4 // 3 + 64 * 1024

NAME_LIMIT = 80

PREFIX = "data:image/png;base64,"


def decode(data_url: Any, limit: int) -> Optional[bytes]:
    """The bytes of a base64 data URL of a PNG image, or None when it is not one or is over limit bytes."""
    if not isinstance(data_url, str) or not data_url.startswith(PREFIX) or (len(data_url) - len(PREFIX)) * 3 // 4 > limit + 3:
        return None
    try:
        raw = base64.b64decode(data_url[len(PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if raw.startswith(PNG_SIGNATURE) and len(raw) <= limit else None


def file_stem(name: Any, fallback: str) -> str:
    """A safe file name for a capture, without its extension, that never starts with a dash or a dot."""
    stem = slug(str(name or "").strip() or fallback)[:NAME_LIMIT]
    while stem.startswith(("-", ".")):
        stem = slug(stem.lstrip("-.") or fallback)[:NAME_LIMIT]
    return stem.rstrip("._") or fallback


async def store_media(owner: User, path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Store a file the plugin wrote in the owner's library; returns the stored media and its library item, SceneError otherwise."""
    try:
        stored = await core_bridge.save_user_media(owner, path)
    except MediaRefError as exc:
        raise SceneError(502, "store_failed", str(exc) or "The file could not be stored in the library.", code=exc.code) from None
    except LimitExceeded as exc:
        raise SceneError(502, "store_failed", str(exc) or "The storage plan of the project owner is full.", code="limit_exceeded") from None
    item = core_bridge.upload_item(owner.id, stored["value"]) or {}
    if not item.get("item_id"):
        raise SceneError(502, "store_failed", "The file was stored but its library item cannot be found.", code="store_failed")
    return stored, item


def media(stored: Dict[str, Any], item: Dict[str, Any], media_type: str) -> Dict[str, Any]:
    """A stored library file as the routes return it, in the shape the seam frame uses."""
    filename = basename(stored["value"])
    return {
        "kind": "library",
        "item_id": item["item_id"],
        "media_type": media_type,
        "url": f"/api/media/uploads/{filename}",
        "filename": stored.get("original_filename") or item.get("filename") or filename,
        "width": item.get("width"),
        "height": item.get("height"),
        "origin": {"kind": "library", "itemId": item["item_id"]},
    }


async def capture(owner: User, project_id: str, png: bytes, name: Any) -> Dict[str, Any]:
    """Store a PNG capture of a scene as an image of the project owner's library."""
    folder = storage.work_folder(project_id) / generate_ulid()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        path = folder / f"{file_stem(name, 'capture')}.png"
        await asyncio.to_thread(path.write_bytes, png)
        stored, item = await store_media(owner, path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return media(stored, item, "image")
