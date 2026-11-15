import logging
from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException

from src.plugin_api import identity

from . import catalog, drafts

KEY_PREFIX = "pui_"
KEY_NAMES = ("ApiScope", "key_access", "key_scope")

logger = logging.getLogger("plugins.preset-editor")


def refuse_api_keys(authorization: Optional[str] = Header(None)) -> None:
    scheme, _, token = (authorization or "").strip().partition(" ")
    if scheme.lower() == "bearer" and token.strip().startswith(KEY_PREFIX):
        raise HTTPException(
            status_code=403,
            detail={"success": False, "error": "key_not_allowed", "message": "Preset Editor accepts a signed-in session only, never an API key"},
        )


def keys_refused(names: Any) -> list:
    marker = getattr(names, "SESSION_ONLY", None)
    if marker is not None:
        return [marker]
    present = [name for name in KEY_NAMES if hasattr(names, name)]
    if present:
        raise RuntimeError(
            f"Preset Editor does not start: this PotionUI has API keys ({', '.join(present)}) but no SESSION_ONLY marker, "
            "so the plugin cannot keep its routes closed to API keys. Update Preset Editor."
        )
    logger.warning(
        "Preset Editor: this PotionUI has no SESSION_ONLY marker and no API key names; "
        "the plugin refuses every Bearer token that starts with %s itself", KEY_PREFIX,
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
