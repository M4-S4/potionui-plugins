from typing import Any, Dict, NoReturn

from fastapi import HTTPException


def ok(data: Any) -> Dict[str, Any]:
    """A successful answer."""
    return {"success": True, "data": data}


def fail(status_code: int, error: str, message: str, **data: Any) -> NoReturn:
    """Raise an HTTP error carrying a stable error code and, when given, its data."""
    detail: Dict[str, Any] = {"success": False, "error": error, "message": message}
    if data:
        detail["data"] = data
    raise HTTPException(status_code=status_code, detail=detail)
