"""HTTP routes of the model-browser plugin, mounted by PotionUI from manifest.yml (`api.module`).

Phase 0 only has `GET /health`. Every route requires a signed-in user; the
per-group capability checks (PLAN.md §4) arrive with the routes that need them.
"""

from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_active_user

from . import PLUGIN_ID, PLUGIN_VERSION

router = APIRouter(prefix="/api/plugins/model-browser", tags=["model-browser"])


@router.get("/health")
async def health(current_user: User = Depends(get_current_active_user)):
    """Answer when the plugin's routes are mounted: lets the page and the admin check the plugin is up."""
    return {
        "success": True,
        "data": {"status": "ok", "plugin": PLUGIN_ID, "version": PLUGIN_VERSION},
    }
