from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from . import access, director, keyframes, takes, tracker
from .core_bridge import User, get_current_active_user
from .generation import Blocked
from .keyframes import OrderError
from .responses import fail, ok
from .routes_takes import blocked

router = APIRouter()


def _order(body: Any) -> keyframes.Order:
    try:
        return keyframes.parse_order(body)
    except OrderError as exc:
        fail(422, "invalid_request", str(exc))


def _shot(project: Dict[str, Any], shot_id: str) -> None:
    if director.clip_of(project["doc"], shot_id) is None:
        fail(404, "shot_not_found", "The shot does not exist.")


@router.get("/projects/{project_id}/shots/{shot_id}/keyframes")
def list_keyframes(project_id: str, shot_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The start and end image candidates of a shot, oldest first."""
    access.project_for(user, project_id)
    return ok({"takes": [takes.public(take) for take in takes.list_keyframes(project_id, shot_id)]})


@router.post("/projects/{project_id}/shots/{shot_id}/keyframes/estimate")
async def estimate_keyframes(
    project_id: str, shot_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """What the start or end image candidates of a shot would need in memory, time, GPU minutes and money, the pictures they send, and what blocks them."""
    order = _order(body)
    project = access.project_for(user, project_id)
    _shot(project, shot_id)
    evaluation = await keyframes.evaluate(user, access.owner_of(user, project), project, shot_id, order)
    return ok(evaluation.payload)


@router.post("/projects/{project_id}/shots/{shot_id}/keyframes", status_code=202)
async def generate_keyframes(
    project_id: str, shot_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Start two to four start or end image candidates of a shot by editing its reference pictures, the ones past max_parallel_jobs waiting in the queue."""
    order = _order(body)
    project = access.project_for(user, project_id)
    _shot(project, shot_id)
    owner = access.owner_of(user, project)
    evaluation = await keyframes.evaluate(user, owner, project, shot_id, order)
    try:
        created = await keyframes.start(owner, project, evaluation)
    except Blocked as exc:
        blocked(exc)
    tracker.ensure_running()
    return ok({"takes": [takes.public(take) for take in created]})
