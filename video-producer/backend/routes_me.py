from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from . import PLUGIN_ID, PLUGIN_VERSION, catalog, limits, settings
from .core_bridge import AccountType, User, get_current_active_user
from .responses import fail, ok

router = APIRouter()


@router.get("/me")
def get_me(user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The signed-in user's locale, role, quota, engines and video presets, and the plugin settings the page needs."""
    return ok(
        {
            "locale": settings.user_locale(user.id),
            "is_admin": user.account_type == AccountType.ADMIN,
            "limits": {"gpu_minutes": limits.gpu_minutes_status(user.id)},
            "settings": settings.all_settings(),
            "plugin": {"id": PLUGIN_ID, "version": PLUGIN_VERSION},
            "engines": catalog.video_engines(),
            "presets": catalog.video_presets(user),
        }
    )


@router.put("/me")
def put_me(body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Save the signed-in user's Video Producer locale."""
    locale = body.get("locale") if isinstance(body, dict) else None
    try:
        saved = settings.set_user_locale(user.id, locale)
    except ValueError:
        fail(422, "invalid_locale", f"The locale must be one of: {', '.join(settings.LOCALES)}.")
    return ok({"locale": saved})
