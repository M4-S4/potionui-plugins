from typing import Any, Dict

from fastapi import APIRouter, Depends

from . import PLUGIN_ID, PLUGIN_VERSION
from .core_bridge import User, get_current_active_user
from .responses import ok
from .routes_chain import router as chain_router
from .routes_exports import router as exports_router
from .routes_generation import router as generation_router
from .routes_keyframes import router as keyframes_router
from .routes_me import router as me_router
from .routes_media import router as media_router
from .routes_projects import router as projects_router
from .routes_prompts import router as prompts_router
from .routes_takes import router as takes_router

router = APIRouter(prefix="/api/plugins/video-producer", tags=["video-producer"])


@router.get("/health")
async def health(current_user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Liveness of the plugin's API for any signed-in user."""
    return ok({"status": "ok", "plugin": PLUGIN_ID, "version": PLUGIN_VERSION})


router.include_router(me_router)
router.include_router(projects_router)
router.include_router(media_router)
router.include_router(takes_router)
router.include_router(generation_router)
router.include_router(prompts_router)
router.include_router(exports_router)
router.include_router(chain_router)
router.include_router(keyframes_router)
