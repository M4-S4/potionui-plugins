from typing import Any, Dict, NoReturn, Optional

from fastapi import APIRouter, Body, Depends

from . import core_bridge, generation, projects, renditions, takes
from .exports import jobs as export_jobs
from .core_bridge import AccountType, User, get_current_active_user
from .projects import DocError, ProjectNotFound, VersionConflict, VersionNotFound
from .responses import fail, ok

router = APIRouter()

TEXT_LIMIT = 200


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _not_found() -> NoReturn:
    fail(404, "project_not_found", "The project does not exist.")


def _object_body(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    if "doc" not in body:
        _invalid("The request body needs a doc.")
    return body


def _optional_text(body: Dict[str, Any], key: str) -> Optional[str]:
    value = body.get(key)
    if value is not None and not isinstance(value, str):
        _invalid(f"{key} must be a string.")
    if value is not None and len(value) > TEXT_LIMIT:
        _invalid(f"{key} must be at most {TEXT_LIMIT} characters.")
    return value


def _accessible(user: User, project_id: str) -> Dict[str, Any]:
    project = projects.get_project(project_id)
    if project is None or (project["user_id"] != user.id and user.account_type != AccountType.ADMIN):
        _not_found()
    return project


def _version_not_found(version: str) -> NoReturn:
    fail(404, "version_not_found", f"The project has no version {version}.")


def _doc_error(exc: DocError) -> NoReturn:
    fail(422, exc.code, str(exc))


def _conflict(exc: VersionConflict) -> NoReturn:
    fail(409, "version_conflict", str(exc), version=exc.current_version)


@router.get("/projects")
def list_projects(user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The signed-in user's projects, last updated first."""
    return ok({"projects": projects.list_projects(user.id)})


@router.post("/projects", status_code=201)
def create_project(body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Create a project from a document for the signed-in user."""
    body = _object_body(body)
    name = _optional_text(body, "name")
    try:
        project = projects.create_project(user.id, body["doc"], name=name)
    except DocError as exc:
        _doc_error(exc)
    return ok({"project": project})


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """One project with its document."""
    return ok({"project": _accessible(user, project_id)})


@router.put("/projects/{project_id}")
def save_project(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Save a new version of a project read at the given version."""
    body = _object_body(body)
    version = body.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        _invalid("version must be the integer version the document was read at.")
    label = _optional_text(body, "label")
    _accessible(user, project_id)
    try:
        saved = projects.save_project(project_id, body["doc"], version, label=label)
    except DocError as exc:
        _doc_error(exc)
    except VersionConflict as exc:
        _conflict(exc)
    except ProjectNotFound:
        _not_found()
    return ok({"project": saved})


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Delete a project with its versions, takes, versions at a frame rate, jobs and exports, cancelling and refunding its takes in flight first and cancelling its versions in flight."""
    project = _accessible(user, project_id)
    active = takes.list_active(project_id)
    flying = [item for item in renditions.list_for_project(project_id) if item["status"] in renditions.ACTIVE]
    owner = None
    if active or flying:
        owner = user if project["user_id"] == user.id else core_bridge.get_user(project["user_id"]) or user
    for take in active:
        await generation.cancel(owner, take)
    for rendition in flying:
        await renditions.cancel(owner, rendition)
    export_jobs.forget_project(project_id)
    if not projects.delete_project(project_id):
        _not_found()
    return ok({"deleted": project_id})


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The stored versions of a project, latest first."""
    _accessible(user, project_id)
    return ok({"versions": projects.list_versions(project_id)})


@router.post("/projects/{project_id}/versions/{version}/restore")
def restore_version(project_id: str, version: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Make a stored version the project's next version."""
    _accessible(user, project_id)
    try:
        number = int(version)
    except ValueError:
        _version_not_found(version)
    try:
        restored = projects.restore_version(project_id, number)
    except VersionNotFound:
        _version_not_found(version)
    except VersionConflict as exc:
        _conflict(exc)
    except ProjectNotFound:
        _not_found()
    return ok({"project": restored})
