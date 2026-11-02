from typing import Any, Dict, NoReturn, Tuple

from . import core_bridge, projects, takes
from .core_bridge import AccountType, User
from .responses import fail


def project_not_found() -> NoReturn:
    """Answer 404 for a project the user may not reach."""
    fail(404, "project_not_found", "The project does not exist.")


def take_not_found() -> NoReturn:
    """Answer 404 for a take the user may not reach."""
    fail(404, "take_not_found", "The take does not exist.")


def can_reach(user: User, project: Dict[str, Any]) -> bool:
    """True for the owner of a project and for an administrator."""
    return project["user_id"] == user.id or user.account_type == AccountType.ADMIN


def project_for(user: User, project_id: str) -> Dict[str, Any]:
    """A project the user owns, or any project for an administrator; 404 otherwise."""
    project = projects.get_project(project_id)
    if project is None or not can_reach(user, project):
        project_not_found()
    return project


def owner_of(user: User, project: Dict[str, Any]) -> User:
    """The user generations of a project run as: its owner, even when an administrator asks."""
    if project["user_id"] == user.id:
        return user
    owner = core_bridge.get_user(project["user_id"])
    if owner is None:
        fail(409, "owner_not_found", "The owner of this project no longer exists.")
    return owner


def take_in(project: Dict[str, Any], take_id: str) -> Dict[str, Any]:
    """A take of the project; 404 otherwise."""
    take = takes.get_take(take_id)
    if take is None or take["project_id"] != project["id"]:
        take_not_found()
    return take


def take_for(user: User, take_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """A take the user may reach and its project; 404 otherwise."""
    take = takes.get_take(take_id)
    project = projects.get_project(take["project_id"]) if take is not None else None
    if take is None or project is None or not can_reach(user, project):
        take_not_found()
    return take, project
