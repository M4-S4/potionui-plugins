from typing import Any, Dict

from fastapi import APIRouter, Depends

from . import access, looks, tracker
from .core_bridge import User, get_current_active_user
from .responses import ok

router = APIRouter()


@router.get("/projects/{project_id}/looks")
def project_looks(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The looks the server measured for the project's finished takes: the score of each seam between two placed takes and of each take against the bible cards of its shot's cast, with the thresholds under which the page warns."""
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    return ok(looks.report(owner, project))


@router.post("/projects/{project_id}/looks")
def measure_looks(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Ask for every look the project's finished takes and cast pictures miss; they are computed in the background while no generation runs."""
    project = access.project_for(user, project_id)
    owner = access.owner_of(user, project)
    found = looks.report(owner, project, enqueue=True)
    tracker.ensure_running()
    return ok(found)
