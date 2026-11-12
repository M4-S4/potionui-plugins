from pathlib import Path
from typing import Any, Dict

from . import core_bridge
from .core_bridge import LimitExceeded, MediaRefError, User

FOLDER = Path(__file__).resolve().parents[1] / "starter"

IMAGES = ("lumi", "bottle", "bottle-gold")


class StarterError(Exception):
    def __init__(self, code: str, image: str, message: str):
        super().__init__(message)
        self.code = code
        self.image = image
        self.message = message


def image_path(name: str) -> Path:
    return FOLDER / f"{name}.jpg"


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1]


async def _store(user: User, name: str) -> Dict[str, Any]:
    path = image_path(name)
    if not path.is_file():
        raise StarterError("missing", name, f"The plugin ships no {path.name}.")
    try:
        stored = await core_bridge.save_user_media(user, path)
    except MediaRefError as exc:
        raise StarterError(exc.code or "store_failed", name, str(exc) or f"{path.name} could not be stored.") from None
    except LimitExceeded as exc:
        raise StarterError("limit_exceeded", name, str(exc) or "The storage plan is full.") from None
    item = (stored.get("ref") or {}).get("item_id")
    if not item:
        raise StarterError("store_failed", name, f"{path.name} was stored but its library item cannot be found.")
    return {
        "kind": "library",
        "item_id": item,
        "media_type": "image",
        "url": f"/api/media/uploads/{_basename(str(stored['value']))}",
        "filename": path.name,
        "width": stored.get("width"),
        "height": stored.get("height"),
        "origin": {"kind": "library", "itemId": item},
    }


async def store_images(user: User) -> Dict[str, Dict[str, Any]]:
    return {name: await _store(user, name) for name in IMAGES}
