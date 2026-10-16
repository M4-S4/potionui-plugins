from typing import Any, Dict, NoReturn, Optional

from fastapi import APIRouter, Body, Depends

from . import PLUGIN_ID, PLUGIN_VERSION, catalog, limits, projects, settings
from .core_bridge import AccountType, User, get_current_active_user
from .responses import fail, ok

router = APIRouter()

ME_KEYS = ("locale", "last_project_id")


def _last_project_id(user_id: str) -> Optional[str]:
    project_id = settings.last_project_id(user_id)
    if project_id is None or projects.project_owner(project_id) != user_id:
        return None
    return project_id


@router.get("/me")
def get_me(user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The signed-in user's locale, last project, role, quota, engines and video presets, and the plugin settings."""
    return ok(
        {
            "locale": settings.user_locale(user.id),
            "last_project_id": _last_project_id(user.id),
            "is_admin": user.account_type == AccountType.ADMIN,
            "limits": {"gpu_minutes": limits.gpu_minutes_status(user.id)},
            "settings": settings.all_settings(),
            "plugin": {"id": PLUGIN_ID, "version": PLUGIN_VERSION},
            "engines": catalog.video_engines(),
            "presets": catalog.video_presets(user),
        }
    )


def _invalid_locale() -> NoReturn:
    fail(422, "invalid_locale", f"The locale must be one of: {', '.join(settings.LOCALES)}.")


@router.put("/me")
def put_me(body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Save the signed-in user's Video Producer locale and last project; a key left out stays as it is."""
    if not isinstance(body, dict) or not any(key in body for key in ME_KEYS):
        _invalid_locale()
    locale = body.get("locale")
    if "locale" in body and (not isinstance(locale, str) or locale not in settings.LOCALES):
        _invalid_locale()
    project_id = body.get("last_project_id")
    if "last_project_id" in body:
        if project_id is not None and not isinstance(project_id, str):
            fail(422, "invalid_request", "last_project_id must be a project id or null.")
        if project_id is not None and projects.project_owner(project_id) != user.id:
            fail(404, "project_not_found", "The project does not exist.")
    if "locale" in body:
        settings.set_user_locale(user.id, locale)
    if "last_project_id" in body:
        settings.set_last_project_id(user.id, project_id)
    return ok(
        {
            "locale": locale if "locale" in body else settings.user_locale(user.id),
            "last_project_id": project_id if "last_project_id" in body else _last_project_id(user.id),
        }
    )
