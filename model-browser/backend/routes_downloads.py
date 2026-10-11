"""Routes that download and tell what is installed: `POST /downloads`, `GET /downloads`,
`POST /installed` (PLAN.md §7.3, §7.4).

Included by `backend/api.py` under `/api/plugins/model-browser`.
- `POST /downloads` (`download`): checks the request for the caller and puts the file on
  the core download queue (`downloads.start_download`). The download watcher
  (`watcher.py`) then follows it to the indexed, assigned and enriched model.
- `GET /downloads` (`download` or `request`): the caller's downloads, newest first; every
  user's for an admin or an `approve` holder (`?all=false`: their own only). `?limit=`
  1 to 200, 50 by default.
- `POST /installed` (`browse`): which of up to 200 SHA256 are installed; for a non-admin,
  installed **and** visible to them (assigned directly or through a group). Answered by
  `installed.installed_map`, the rule `GET /{source}/search` also uses for its `installed` badge.

Pending rows are sent with their `info` filtered for the viewer's NSFW context and without
the model's description (`downloads.row_for_viewer`), and the core's download record with
only its public fields to a non-admin (`downloads.PUBLIC_DOWNLOAD_FIELDS`).

Success: `{"success": true, "data": ...}`. Errors: `HTTPException` with
`{"success": false, "error": <code>, "message": ...}`: `invalid_request` and `invalid` (400),
`forbidden` (403), `not_found` and `unknown_source` (404), `blocked` (409, the core or
another plugin refused to queue the file), the sources' errors as in `routes_sources.py`
(429, 502), `internal_error` (500).
"""

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, field_validator

from . import core_bridge, downloads, nsfw, pending
from .downloads import DownloadError, DownloadRequest
from .http import SourceError
from .installed import installed_map
from .permissions import Principal, require_any, require_browse, require_download
from .routes_sources import source_http_error

logger = logging.getLogger("plugins.model-browser")

router = APIRouter()

#: `GET /downloads`: whoever may download or request a model.
require_downloads_access = require_any("download", "request")

MAX_INSTALLED_HASHES = 200
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"success": False, "error": code, "message": message})


@router.post("/downloads")
async def post_download(
    body: Any = Body(...),
    principal: Principal = Depends(require_download),
) -> Dict[str, Any]:
    """Queue one file for the caller, or reuse what is already there.

    Body: `{source, model_id, version_id, file_id, model_type?, subdir?, filename?,
    destination_backend_id?, assign_group_id?}`. Data: `{"pending", "download",
    "already_installed", "already_queued"}`.
    """
    try:
        request = DownloadRequest.model_validate(body)
    except ValidationError as error:
        raise _error(400, "invalid_request", downloads.describe_validation_error(error)) from None
    try:
        data = await downloads.start_download(principal, request)
    except DownloadError as exc:
        raise _error(exc.status, exc.code, exc.message) from None
    except SourceError as exc:
        raise source_http_error(exc) from None
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not start the download of %s %s", request.source, request.model_id)
        raise _error(500, "internal_error", "The download could not be started; the server log has the details") from None
    return {"success": True, "data": data}


@router.get("/downloads")
def list_downloads(
    all_users: Optional[bool] = Query(None, alias="all"),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    principal: Principal = Depends(require_downloads_access),
) -> Dict[str, Any]:
    """The caller's downloads (every user's for an admin or an `approve` holder unless `all=false`), newest first.

    Data: a list of `{"pending": <row>, "download": <core download or None>}`.
    """
    user = principal.user
    everyone = (principal.is_admin or principal.grant.has("approve")) and all_users is not False
    rows = pending.list_rows(requested_by=None if everyone else user.id, limit=limit)
    ctx = nsfw.resolve_nsfw(user)
    return {
        "success": True,
        "data": [
            {
                "pending": downloads.row_for_viewer(row, ctx),
                "download": downloads.public_download(_download(row), admin=principal.is_admin),
            }
            for row in rows
        ],
    }


def _download(row: pending.PendingRow) -> Optional[Dict[str, Any]]:
    if not row.download_id:
        return None
    try:
        return core_bridge.get_download(row.download_id)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not read download %s", row.download_id, exc_info=True)
        return None


class InstalledRequest(BaseModel):
    """The body of `POST /installed`."""

    sha256s: List[str] = Field(max_length=MAX_INSTALLED_HASHES)

    @field_validator("sha256s")
    @classmethod
    def _hashes(cls, values: List[str]) -> List[str]:
        hashes: Dict[str, None] = {}
        for value in values:
            sha256 = value.strip().lower()
            if not _SHA256.fullmatch(sha256):
                raise ValueError(f"'{value[:80]}' is not a SHA256 (64 hexadecimal characters)")
            hashes[sha256] = None
        return list(hashes)


@router.post("/installed")
async def installed(
    body: Any = Body(...),
    principal: Principal = Depends(require_browse),
) -> Dict[str, Any]:
    """Which of these SHA256 are installed: for a non-admin, installed and visible to them.

    Body: `{"sha256s": [...]}` (at most 200; any case). Data: `{"installed": {<lower-case
    sha256>: bool}}`. A model whose file has gone from the disk does not count.
    """
    try:
        request = InstalledRequest.model_validate(body)
    except ValidationError as error:
        raise _error(400, "invalid_request", downloads.describe_validation_error(error, "hash list")) from None
    return {"success": True, "data": {"installed": await installed_map(request.sha256s, principal)}}
