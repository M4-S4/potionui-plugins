from typing import Any, Dict, NoReturn

from fastapi import APIRouter, Body, Depends

from . import access, catalog, generation, takes, tracker
from .core_bridge import User, get_current_active_user
from .generation import Blocked, TakeError
from .responses import fail, ok

router = APIRouter()


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _object(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    return body


def blocked(exc: Blocked) -> NoReturn:
    """Answer 409 with what blocks the takes."""
    fail(409, "blocked", str(exc) or "The takes cannot start.", blocks=exc.blocks)


def take_error(exc: TakeError) -> NoReturn:
    """Answer the status and code of a take in the wrong state."""
    fail(exc.status_code, exc.code, exc.message)


@router.get("/projects/{project_id}/takes")
def list_takes(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The takes of a project, oldest first."""
    access.project_for(user, project_id)
    return ok({"takes": [takes.public(take) for take in takes.list_takes(project_id)]})


@router.post("/projects/{project_id}/takes/{take_id}/label")
def label_take(
    project_id: str, take_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Label a take draft, rejected, candidate or final; a final take is the only one of its shot."""
    label = _object(body).get("label")
    if label not in takes.LABELS:
        _invalid(f"label must be one of: {', '.join(takes.LABELS)}.")
    project = access.project_for(user, project_id)
    take = access.take_in(project, take_id)
    if label == takes.FINAL and take["status"] != "done":
        fail(409, "take_not_done", "Only a finished take can be final.")
    return ok({"take": takes.public(takes.set_label(take_id, label))})


@router.post("/projects/{project_id}/takes/{take_id}/choose")
def choose_take(
    project_id: str, take_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Former route: label a take final, the previous final turning candidate, or a final take candidate."""
    chosen = _object(body).get("chosen")
    if not isinstance(chosen, bool):
        _invalid("chosen must be true or false.")
    project = access.project_for(user, project_id)
    take = access.take_in(project, take_id)
    if chosen and take["status"] != "done":
        fail(409, "take_not_done", "Only a finished take can be kept.")
    return ok({"take": takes.public(takes.choose(take_id, chosen))})


@router.post("/projects/{project_id}/takes/{take_id}/flag")
def flag_take(
    project_id: str, take_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Former route: keep labels a take candidate, reject rejected, and null takes a candidate or rejected take back to draft."""
    body = _object(body)
    if "flag" not in body or (body["flag"] is not None and body["flag"] not in takes.FLAGS):
        _invalid(f"flag must be one of: {', '.join(takes.FLAGS)}, or null.")
    project = access.project_for(user, project_id)
    access.take_in(project, take_id)
    return ok({"take": takes.public(takes.set_flag(take_id, body["flag"]))})


@router.post("/projects/{project_id}/takes/{take_id}/prioritize")
def prioritize_take(project_id: str, take_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Move a waiting take to the head of its owner's queue; a take already handed to the core is left as it is."""
    project = access.project_for(user, project_id)
    take = access.take_in(project, take_id)
    if take["status"] not in takes.ACTIVE:
        fail(409, "take_not_queued", "Only a queued take can move to the head of the queue.")
    return ok({"take": takes.public(takes.prioritize(take))})


@router.delete("/projects/{project_id}/takes/{take_id}")
async def delete_take(project_id: str, take_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Delete a take, cancelling it first while it is in flight; the host generation is kept."""
    project = access.project_for(user, project_id)
    take = access.take_in(project, take_id)
    await generation.delete(access.owner_of(user, project), take)
    return ok({"deleted": take_id})


@router.post("/projects/{project_id}/takes/{take_id}/final", status_code=202)
async def final_take(
    project_id: str, take_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Start the final take of a finished take, by upscale or by a new render at the largest size."""
    body = _object(body)
    method, target = body.get("method"), body.get("target")
    if method not in generation.METHODS:
        _invalid(f"method must be one of: {', '.join(generation.METHODS)}.")
    if target not in catalog.UPSCALE_TARGETS:
        _invalid(f"target must be one of: {', '.join(catalog.UPSCALE_TARGETS)}.")
    project = access.project_for(user, project_id)
    source = access.take_in(project, take_id)
    try:
        take = await generation.final(access.owner_of(user, project), project, source, method, target)
    except Blocked as exc:
        blocked(exc)
    except TakeError as exc:
        take_error(exc)
    tracker.ensure_running()
    return ok({"take": takes.public(take)})


@router.post("/takes/{take_id}/cancel")
async def cancel_take(take_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Cancel a queued or running take and refund its minutes."""
    take, project = access.take_for(user, take_id)
    return ok({"take": takes.public(await generation.cancel(access.owner_of(user, project), take))})


@router.post("/takes/{take_id}/retry", status_code=202)
async def retry_take(take_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Start a new take like a failed or cancelled one, with the same shot, seed, quality and preset."""
    source, project = access.take_for(user, take_id)
    try:
        take = await generation.retry(access.owner_of(user, project), project, source)
    except Blocked as exc:
        blocked(exc)
    except TakeError as exc:
        take_error(exc)
    tracker.ensure_running()
    return ok({"take": takes.public(take)})
