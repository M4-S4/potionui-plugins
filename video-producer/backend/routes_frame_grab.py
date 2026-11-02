from typing import Any, Dict

from fastapi import APIRouter, Depends

from . import access, frame_grab
from .frame_grab import FrameError
from .core_bridge import LimitExceeded, MediaRefError, User, get_current_active_user
from .responses import fail, ok

router = APIRouter()


async def _frame(user: User, project_id: str, shot_id: str, first: bool) -> Dict[str, Any]:
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    try:
        frame = await (frame_grab.start_frame if first else frame_grab.end_frame)(owner, project, shot_id)
    except FrameError as exc:
        fail(exc.status, exc.code, exc.message)
    except MediaRefError as exc:
        fail(502, "extract_failed", str(exc) or "The frame could not be stored.", code="store_failed")
    except LimitExceeded as exc:
        fail(502, "extract_failed", str(exc) or "The storage plan of the project owner is full.", code="limit_exceeded")
    stored = frame_grab.media_of(owner.id, frame)
    if stored is None:
        fail(502, "extract_failed", "The frame was stored but its library item cannot be found.", code="store_failed")
    return ok({"media": stored, "source": frame["source"]})


@router.post("/projects/{project_id}/shots/{shot_id}/end-frame")
async def end_frame(project_id: str, shot_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Store the last frame a shot shows, at the end of its cut (srcIn + dur) of its placed take or video, as an image of the project owner, with where it was taken."""
    return await _frame(user, project_id, shot_id, False)


@router.post("/projects/{project_id}/shots/{shot_id}/start-frame")
async def start_frame(project_id: str, shot_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Store the first frame a shot shows, at the start of its cut (srcIn) of its placed take or video, as an image of the project owner, with where it was taken."""
    return await _frame(user, project_id, shot_id, True)
