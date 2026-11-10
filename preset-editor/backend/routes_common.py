from typing import Any, Dict

from fastapi import HTTPException

from . import catalog, drafts


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
