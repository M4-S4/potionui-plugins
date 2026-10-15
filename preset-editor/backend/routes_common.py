from typing import Any, Dict

from fastapi import HTTPException

from . import drafts


def error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"success": False, "error": code, "message": message, **extra})


def ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def draft_payload(draft: drafts.Draft) -> Dict[str, Any]:
    return {**draft.to_dict(), "files": drafts.file_tree(draft.dir)}
