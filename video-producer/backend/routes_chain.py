from typing import Any, Dict

from fastapi import APIRouter, Depends

from . import access, chain, core_bridge
from .chain import ChainError
from .core_bridge import LimitExceeded, MediaRefError, User, get_current_active_user
from .exports.media import basename
from .responses import fail, ok

router = APIRouter()


@router.post("/projects/{project_id}/shots/{shot_id}/end-frame")
async def end_frame(project_id: str, shot_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Store the last frame a shot shows, at the end of its cut (srcIn + dur) of its placed take or video, as an image of the project owner, with where it was taken."""
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    try:
        frame = await chain.end_frame(owner, project, shot_id)
    except ChainError as exc:
        fail(exc.status, exc.code, exc.message)
    except MediaRefError as exc:
        fail(502, "extract_failed", str(exc) or "The frame could not be stored.", code="store_failed")
    except LimitExceeded as exc:
        fail(502, "extract_failed", str(exc) or "The storage plan of the project owner is full.", code="limit_exceeded")
    item = core_bridge.upload_item(owner.id, frame["value"]) or {}
    if not item.get("item_id"):
        fail(502, "extract_failed", "The frame was stored but its library item cannot be found.", code="store_failed")
    filename = basename(frame["value"])
    return ok(
        {
            "media": {
                "kind": "library",
                "item_id": item["item_id"],
                "media_type": "image",
                "url": f"/api/media/uploads/{filename}",
                "filename": frame["filename"],
                "width": item.get("width"),
                "height": item.get("height"),
                "origin": {"kind": "library", "itemId": item["item_id"]},
            },
            "source": frame["source"],
        }
    )
