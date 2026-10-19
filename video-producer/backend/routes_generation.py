from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from . import access, estimate, generation, settings, takes, tracker
from .core_bridge import User, get_current_active_user
from .estimate import OrderError
from .generation import Blocked
from .responses import fail, ok
from .routes_takes import blocked

router = APIRouter()


def _order(body: Any) -> estimate.Order:
    try:
        return estimate.parse_order(body)
    except OrderError as exc:
        fail(422, "invalid_request", str(exc))


@router.post("/projects/{project_id}/estimate")
async def estimate_takes(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """What the takes of some shots would need in memory, time, GPU minutes and money, and what blocks them."""
    order = _order(body)
    project = access.project_for(user, project_id)
    evaluation = await estimate.evaluate(user, access.owner_of(user, project), project["doc"], order)
    return ok(evaluation.payload)


@router.post("/projects/{project_id}/generate", status_code=202)
async def generate_takes(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Start one take per shot and variant, the ones past max_parallel_jobs waiting in the queue; in the 3D render mode, answer the rendered guides the shots take instead."""
    order = _order(body)
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    evaluation = await estimate.evaluate(user, owner, project["doc"], order)
    try:
        created = await generation.start(owner, project, evaluation)
    except Blocked as exc:
        blocked(exc)
    tracker.ensure_running()
    return ok({"takes": [takes.public(take) for take in created], "renders": evaluation.payload["renders"]})


@router.get("/projects/{project_id}/queue")
def project_queue(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The project's queued and running takes, and how many of its owner's generation slots are taken."""
    project = access.project_for(user, project_id)
    return ok(
        {
            "takes": [takes.public(take) for take in takes.list_active(project_id)],
            "slots": {"in_flight": takes.in_flight(project["user_id"]), "max": settings.get_setting("max_parallel_jobs")},
        }
    )
