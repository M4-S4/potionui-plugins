from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_admin_user

from . import PLUGIN_ID, PLUGIN_VERSION
from .routes_archive import router as archive_router
from .routes_drafts import router as drafts_router
from .routes_files import router as files_router
from .routes_media import router as media_router
from .routes_presets import router as presets_router

router = APIRouter(prefix="/api/plugins/preset-editor", tags=["preset-editor"])


@router.get("/me")
async def me(current_user: User = Depends(get_current_admin_user)):
    return {
        "success": True,
        "data": {"is_admin": True, "user_id": current_user.id, "plugin": PLUGIN_ID, "version": PLUGIN_VERSION},
    }


router.include_router(presets_router)
router.include_router(drafts_router)
router.include_router(files_router)
router.include_router(media_router)
router.include_router(archive_router)
