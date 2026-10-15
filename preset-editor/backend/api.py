from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_admin_user

from . import PLUGIN_ID, PLUGIN_VERSION

router = APIRouter(prefix="/api/plugins/preset-editor", tags=["preset-editor"])


@router.get("/me")
async def me(current_user: User = Depends(get_current_admin_user)):
    return {
        "success": True,
        "data": {"is_admin": True, "user_id": current_user.id, "plugin": PLUGIN_ID, "version": PLUGIN_VERSION},
    }
