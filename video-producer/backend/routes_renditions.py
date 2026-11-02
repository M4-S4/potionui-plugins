from typing import Any, Dict, List, NoReturn, Optional, Tuple

from fastapi import APIRouter, Body, Depends

from . import access, cadence, generation, projects, renditions, takes, tracker
from .core_bridge import User, get_current_active_user
from .responses import fail, ok

router = APIRouter()

MAX_TAKES = 200


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _order(body: Any) -> Tuple[List[str], Optional[str]]:
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    ids = body.get("takes")
    if not isinstance(ids, list) or not ids or not all(isinstance(take_id, str) and take_id for take_id in ids):
        _invalid("takes must be a non-empty list of take ids.")
    if len(set(ids)) > MAX_TAKES:
        _invalid(f"takes holds at most {MAX_TAKES} take ids.")
    choice = body.get("interpolator")
    if choice is not None and choice not in cadence.CHOICES:
        _invalid(f"interpolator must be one of: {', '.join(cadence.CHOICES)}.")
    return list(dict.fromkeys(ids)), choice


def _not_found() -> NoReturn:
    fail(404, "rendition_not_found", "The version at a frame rate does not exist.")


@router.get("/projects/{project_id}/renditions")
def list_renditions(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The versions at a frame rate of a project's takes, oldest first."""
    access.project_for(user, project_id)
    return ok({"renditions": [renditions.public(item) for item in renditions.list_for_project(project_id)]})


@router.post("/projects/{project_id}/renditions/estimate")
def estimate_renditions(project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Which of some takes are slower than their shot needs (the film's frame rate divided by the shot's speed), which interpolator would bring them to it and how long it would take; None when it was never measured."""
    ids, choice = _order(body)
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    doc = project.get("doc") or {}
    fps = cadence.target_of(doc)
    chosen = cadence.choice_of(doc) if choice is None else choice
    found = cadence.ready(owner)
    interpolator = cadence.pick(chosen, found)
    slow: List[str] = []
    work: Optional[float] = 0.0
    for take_id in ids:
        take = access.take_in(project, take_id)
        needed = cadence.needed_fps(doc, renditions.shot_of(project, take.get("shot_id")), take.get("fps"))
        if needed is None or take.get("kind") == takes.KEYFRAME or renditions.current_for(take_id, needed) is not None:
            continue
        slow.append(take_id)
        part = cadence.seconds_for(interpolator, take.get("backend_id"), renditions.size_of(take), take.get("duration_s"))
        work = None if part is None or work is None else work + part
    seconds = round(work, 1) if slow and work is not None and interpolator is not None else None
    return ok({"fps": fps, "choice": chosen, "interpolator": interpolator, "ready": found, "takes": slow, "seconds": seconds})


@router.post("/projects/{project_id}/renditions", status_code=202)
async def order_renditions(project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Bring some takes to the film's frame rate: each gets its version already finished or on its way, else a new one; the takes that cannot have one are listed with the reason."""
    ids, choice = _order(body)
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    sources = [access.take_in(project, take_id) for take_id in ids]
    ordered: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    for take in sources:
        try:
            ordered.append(renditions.order(owner, project, take, choice, renditions.shot_of(project, take.get("shot_id"))))
        except renditions.Refused as exc:
            refused.append({"take_id": take["id"], **exc.block})
    if ordered:
        await generation.pump(owner)
        tracker.ensure_running()
    return ok(
        {
            "renditions": [renditions.public(renditions.get(item["id"]) or item) for item in ordered],
            "refused": refused,
        }
    )


@router.post("/renditions/{rendition_id}/cancel")
async def cancel_rendition(rendition_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Cancel a version at a frame rate still waiting, queued or running."""
    rendition = renditions.get(rendition_id)
    project = projects.get_project(rendition["project_id"]) if rendition is not None else None
    if rendition is None or project is None or not access.can_reach(user, project):
        _not_found()
    cancelled = await renditions.cancel(access.owner_of(user, project), rendition)
    return ok({"rendition": renditions.public(cancelled or rendition)})
