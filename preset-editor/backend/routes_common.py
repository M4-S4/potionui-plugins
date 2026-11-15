import logging
import re
from typing import Any, Dict

from fastapi import Depends, HTTPException, Request

from src.plugin_api import identity

from . import catalog, drafts

KEY_NAMES = ("ApiScope", "key_access", "key_scope")
KEY_QUERY = ("token", "access_token", "api_key", "key")
SESSION_TOKEN = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$")
STOPPED = "Preset Editor cannot keep API keys out of this PotionUI and refuses every request: update Preset Editor."

logger = logging.getLogger("plugins.preset-editor")


def _key_refused() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"success": False, "error": "key_not_allowed", "message": "Preset Editor accepts a signed-in session only, never an API key"},
    )


def refuse_api_keys(request: Request) -> None:
    for value in request.headers.getlist("authorization"):
        scheme, _, token = value.strip().partition(" ")
        if scheme.lower() != "bearer" or not SESSION_TOKEN.match(token.strip()):
            raise _key_refused()
    if "x-api-key" in request.headers or any(name in request.query_params for name in KEY_QUERY):
        raise _key_refused()


def refuse_everything() -> None:
    raise HTTPException(status_code=503, detail={"success": False, "error": "update_required", "message": STOPPED})


def keys_refused(names: Any) -> list:
    marker = getattr(names, "SESSION_ONLY", None)
    if marker is not None:
        return [marker]
    present = [name for name in KEY_NAMES if hasattr(names, name)]
    if present:
        logger.error("%s This PotionUI has API keys (%s) but no SESSION_ONLY marker.", STOPPED, ", ".join(present))
        return [Depends(refuse_everything)]
    logger.warning(
        "Preset Editor: this PotionUI has no SESSION_ONLY marker and no API key names; "
        "the plugin accepts a Bearer session token only and refuses any other credential itself"
    )
    return [Depends(refuse_api_keys)]


KEYS_REFUSED = keys_refused(identity)


def error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"success": False, "error": code, "message": message, **extra})


def ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def draft_payload(draft: drafts.Draft) -> Dict[str, Any]:
    return {**draft.to_dict(), "files": drafts.file_tree(draft.dir)}


def refuse_mirror(template: Any) -> None:
    source = catalog.mirror_source(template)
    if source is not None:
        raise error(
            409, "mirror",
            f"preset '{template.id}' is a mirror of '{source}': it has no files of its own, it uses the folder of '{source}'. "
            f"Manage the mirror in Admin → Presets, or open '{source}' to change its files",
            source_preset_id=source,
        )
