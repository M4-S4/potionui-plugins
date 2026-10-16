from typing import Any, Dict, NoReturn, Optional

from fastapi import APIRouter, Body, Depends

from . import core_bridge
from .core_bridge import MediaRefError, User, get_current_active_user
from .responses import fail, ok

router = APIRouter()

ORIGIN_KEYS = {
    "history": {"generationId": "generation_id", "fileId": "file_id"},
    "library": {"itemId": "item_id"},
}


def _invalid_ref() -> NoReturn:
    fail(422, "invalid_ref", "Unsupported media reference.")


def _core_ref(origin: Dict[str, Any]) -> Dict[str, Any]:
    keys = ORIGIN_KEYS.get(origin.get("kind"))
    if keys is None or set(origin) != {"kind", *keys}:
        _invalid_ref()
    return {"kind": origin["kind"], **{core: origin[key] for key, core in keys.items()}}


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def _url(ref: Dict[str, Any], value: str) -> str:
    if ref["kind"] == "history":
        return f"/api/media/generations/{ref['generation_id']}/{_basename(value)}"
    return f"/api/media/uploads/{_basename(value)}"


def _media_type(media_type: Any) -> Optional[str]:
    category = str(media_type or "").split("/", 1)[0].lower()
    return category or None


@router.post("/media/resolve")
def resolve_media(body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Resolve a media origin the host pickers emit into the URL and file name the editor plays."""
    origin = body.get("origin") if isinstance(body, dict) else None
    if not isinstance(origin, dict):
        fail(422, "invalid_request", "The request body needs an origin object.")
    ref = _core_ref(origin)
    try:
        resolved = core_bridge.resolve_media(user, ref)
    except MediaRefError as exc:
        if exc.code == "not_found":
            fail(404, "media_not_found", "The media is not available.")
        _invalid_ref()
    value = resolved["value"]
    return ok(
        {
            "media": {
                "kind": ref["kind"],
                "media_type": _media_type(resolved.get("media_type")),
                "url": _url(ref, value),
                "filename": resolved.get("original_filename") or _basename(value),
                "origin": origin,
            }
        }
    )
