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

JPEG_SIGNATURE = b"\xff\xd8\xff"

MAX_IMAGE_BYTES = 40 * 1024 * 1024

NAME_LIMIT = 80

PREFIXES = {"png": ("data:image/png;base64,",), "jpeg": ("data:image/jpeg;base64,", "data:image/jpg;base64,")}

SIGNATURES = {"png": PNG_SIGNATURE, "jpeg": JPEG_SIGNATURE}


def decode(data_url: Any, kind: str) -> Optional[bytes]:
    """The bytes of a base64 data URL of a PNG or a JPEG image, or None when it is not one or is over 40 MiB."""
    if not isinstance(data_url, str):
        return None
    prefix = next((prefix for prefix in PREFIXES[kind] if data_url.startswith(prefix)), None)
    if prefix is None or (len(data_url) - len(prefix)) * 3 // 4 > MAX_IMAGE_BYTES + 3:
        return None
    try:
        raw = base64.b64decode(data_url[len(prefix):], validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if raw.startswith(SIGNATURES[kind]) and len(raw) <= MAX_IMAGE_BYTES else None


def file_stem(name: Any, fallback: str) -> str:
    """A safe file name for a capture or a render, without its extension."""
    stem = slug(str(name or "").strip() or fallback)[:NAME_LIMIT].strip("._")
    return stem or fallback


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


def media(stored: Dict[str, Any], item: Dict[str, Any], media_type: str, **extra: Any) -> Dict[str, Any]:
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
        **extra,
        "origin": {"kind": "library", "itemId": item["item_id"]},
    }


async def capture(owner: User, project_id: str, png: bytes, name: Any) -> Dict[str, Any]:
    """Store a PNG capture of a scene as an image of the project owner's library."""
    folder = storage.work_folder(project_id) / generate_ulid()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        path = folder / f"{file_stem(name, 'capture')}.png"
        path.write_bytes(png)
        stored, item = await store_media(owner, path)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return media(stored, item, "image")
