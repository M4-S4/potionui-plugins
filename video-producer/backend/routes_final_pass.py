from typing import Any, Dict, List, Mapping, Tuple

from fastapi import APIRouter, Body, Depends

from . import access, final_pass, takes, tracker
from .core_bridge import User, get_current_active_user
from .final_pass import PassError
from .generation import Blocked
from .responses import fail, ok
from .routes_takes import blocked

router = APIRouter()


def _order(body: Any) -> final_pass.Order:
    try:
        return final_pass.parse_order(body)
    except PassError as exc:
        fail(422, "invalid_request", str(exc))


def _sources(user: User, project_id: str, body: Any) -> Tuple[final_pass.Order, Dict[str, Any], User, List[Dict[str, Any]]]:
    order = _order(body)
    project = access.project_for(user, project_id)
    sources = [access.take_in(project, take_id) for take_id in order.takes]
    return order, project, access.owner_of(user, project), sources


async def _evaluate(user: User, project_id: str, body: Any) -> Tuple[Mapping[str, Any], User, final_pass.Evaluation]:
    order, project, owner, sources = _sources(user, project_id, body)
    return project, owner, await final_pass.evaluate(owner, project, order, sources)


@router.post("/projects/{project_id}/final-pass/estimate")
async def estimate_final_pass(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """What making some finished takes final in one go would need in memory, time and GPU minutes, and what blocks it."""
    _, _, evaluation = await _evaluate(user, project_id, body)
    return ok(evaluation.payload)


@router.post("/projects/{project_id}/final-pass", status_code=202)
async def start_final_pass(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Start the final take of each of some finished takes with one method and one target, the ones past max_parallel_jobs waiting in the queue; nothing starts when anything blocks."""
    project, owner, evaluation = await _evaluate(user, project_id, body)
    try:
        created = await final_pass.start(owner, project, evaluation)
    except Blocked as exc:
        blocked(exc)
    tracker.ensure_running()
    return ok({"takes": [takes.public(take) for take in created]})
