"""HTTP routes of the model-browser plugin, mounted by PotionUI from manifest.yml (`api.module`).

`router` carries the plugin prefix and `GET /health`; the feature routers are
included below, each in its own module:
- `routes_permissions.py`: `GET /me`, `GET/PUT /permissions` (PLAN.md §4);
- `routes_sources.py`: `GET /sources`, search, detail, `nsfw-media` (§7.3).

Every route requires a signed-in user; the per-group capability checks are the
`require_*` dependencies of `permissions.py`.
"""

from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_active_user

from . import PLUGIN_ID, PLUGIN_VERSION
from .routes_permissions import router as permissions_router
from .routes_sources import router as sources_router

router = APIRouter(prefix="/api/plugins/model-browser", tags=["model-browser"])


@router.get("/health")
async def health(current_user: User = Depends(get_current_active_user)):
    """Answer when the plugin's routes are mounted: lets the page and the admin check the plugin is up."""
    return {
        "success": True,
        "data": {"status": "ok", "plugin": PLUGIN_ID, "version": PLUGIN_VERSION},
    }


router.include_router(permissions_router)
router.include_router(sources_router)
