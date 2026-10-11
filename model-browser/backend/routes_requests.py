"""Model requests (PLAN.md §4.4, §7.3): `POST /requests`, `GET /requests`,
`POST /requests/{id}/approve`, `POST /requests/{id}/reject`, `DELETE /requests/{id}`.

Included by `backend/api.py` under `/api/plugins/model-browser`.
- `POST /requests` (`request`): body `{source, model_id, version_id, file_id, model_type?,
  note?}` (a note of at most 1000 characters). The file is checked for the requester as a
  download would be, against the request view of their grant
  (`downloads.prepare_download(..., purpose="request")`: source allowed and enabled, model
  visible to them, version and file found, type allowed, size within `max_file_gb`, download
  URL), without being queued. A file already installed and visible to them is a 409
  `already_available`; one installed but not visible to them is asked for all the same (its
  snapshot says `already_installed`: approving it only assigns it). Their open request for
  the same file is answered again (`already_requested: true`) rather than doubled. A new
  request notifies every approver but the requester (`model-browser.request_received`).
  Data: `{"request", "already_requested"}`.
- `GET /requests?status=&all=&limit=` (`request` or `approve`): the caller's requests, newest
  first; every user's for an approver (an admin, or a holder of `approve`) unless `all=false`.
  `status`: one or more statuses, repeated or comma-separated. `limit`: 1 to 200, 50 by
  default. Data: `{"requests": [...], "open_count": <the open requests the caller may decide
  on: all of them for an admin, the other users' for an `approve` holder, 0 otherwise>,
  "can_approve": bool}`.
- `POST /requests/{id}/approve` (`approve`): body `{note?, model_type?, assign_group_id?}`, an
  `open` request only (409 `not_open`), never one's own unless one is an admin (403
  `forbidden`). The request is checked again for the requester, with the request view of
  their own grant and their own NSFW context (`prepare_download(..., purpose="request",
  on_behalf=True)`: a model they may no longer see is a 403 `not_visible_to_requester`), and
  against their plan quota, then the file is queued for them (`downloads.queue_prepared`):
  the pending row is theirs (`requested_by`; `assign_to` from their request view, or
  `group:<id>` for one of their groups the approver picked when that view allows it), the
  core download is created by the approver. A file already
  on its way for someone else is not queued twice (`already_queued`: the download watcher
  assigns the requester when it arrives), an installed file is only assigned
  (`already_installed`). The request becomes `approved`, linked to the row by `sha256`, and
  the requester is notified (`model-browser.request_approved`). Data: `{"request", "pending",
  "download", "already_installed", "already_queued"}`. A refusal leaves the request `open`.
- `POST /requests/{id}/reject` (`approve`): body `{note?}`; an `open` request, not one's own
  unless one is an admin (403 `forbidden`), becomes `rejected`, and the requester is notified
  (`model-browser.request_rejected`). Data: `{"request"}`.
- `DELETE /requests/{id}` (any signed-in user): the author cancels their own `open` request
  (403 for anyone else, 409 `not_open`). Data: `{"request"}`.

Requests are sent with the usernames of their author and approver, and their snapshot as the
viewer may see it (`requests.for_viewer`). The download watcher (`watcher.py`) moves an
approved request on to `done` or `failed`.

Success: `{"success": true, "data": ...}`. Errors: `HTTPException` with `{"success": false,
"error": <code>, "message": ...}`: those of `POST /downloads` (`routes_downloads.py`:
`invalid_request`, `forbidden`, `limit_exceeded`, `not_found`, `unknown_source`, `blocked`, the
sources' errors, `internal_error`), and `already_available` (409), `not_open` (409),
`not_visible_to_requester` (403), `requester_gone` (409: the requester's account was deleted).
"""

import asyncio
import logging
from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, BeforeValidator, Field, ValidationError, field_validator

from src.plugin_api.models import MODEL_TYPES

from . import core_bridge, downloads, notifications, nsfw, permissions, requests
from .downloads import MAX_ID_LENGTH, DownloadError, DownloadRequest, FileRef, Prepared
from .http import SourceError
from .permissions import Principal, current_principal, require_any, require_approve, require_request
from .requests import MAX_NOTE_LENGTH, Request
from .routes_downloads import download_http_error
from .routes_sources import source_http_error
from .schema import NsfwContext

logger = logging.getLogger("plugins.model-browser")

router = APIRouter()

#: `GET /requests`: whoever may ask for a model or decide on requests.
require_requests_access = require_any("request", "approve")

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"success": False, "error": code, "message": message})


def _ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


# Bodies ---------------------------------------------------------------------------


def _blank_is_none(value: Any) -> Any:
    """A string trimmed, a blank one meaning "not given"; other values go on to validation."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


Note = Annotated[Optional[str], BeforeValidator(_blank_is_none)]


class RequestCreate(FileRef):
    """The body of `POST /requests`."""

    #: Why the requester wants the file, for the approvers.
    note: Note = Field(None, max_length=MAX_NOTE_LENGTH)


class Decision(BaseModel):
    """The body of `POST /requests/{id}/reject`: the approver's note to the requester."""

    note: Note = Field(None, max_length=MAX_NOTE_LENGTH)


class Approval(Decision):
    """The body of `POST /requests/{id}/approve`."""

    #: The PotionUI type to download the file as, instead of the one asked for.
    model_type: Annotated[Optional[str], BeforeValidator(_blank_is_none)] = None
    #: One of the requester's groups to assign the model to (their parameters must allow it).
    assign_group_id: Annotated[Optional[str], BeforeValidator(_blank_is_none)] = Field(None, max_length=MAX_ID_LENGTH)

    @field_validator("model_type")
    @classmethod
    def _model_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in MODEL_TYPES:
            raise ValueError(f"unknown model type '{value[:64]}'")
        return value

    @field_validator("assign_group_id")
    @classmethod
    def _group_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and any(ord(char) < 0x20 or ord(char) == 0x7F or char == "\\" for char in value):
            raise ValueError("must not contain a backslash or a control character")
        return value


def _validate(model: Any, body: Any, what: str) -> Any:
    try:
        return model.model_validate(body if body is not None else {})
    except ValidationError as error:
        raise _error(400, "invalid_request", downloads.describe_validation_error(error, what)) from None


def _statuses(values: Optional[List[str]]) -> Optional[List[str]]:
    """`?status=` values, repeated or comma-separated; None when none is given."""
    wanted = [part.strip() for value in values or [] for part in value.split(",") if part.strip()]
    unknown = [status for status in wanted if status not in requests.STATUSES]
    if unknown:
        raise _error(
            400,
            "invalid_request",
            f"Unknown request status '{unknown[0][:32]}': use one of {', '.join(requests.STATUSES)}",
        )
    return list(dict.fromkeys(wanted)) or None


def _get_request(request_id: str) -> Request:
    request = requests.get(request_id)
    if request is None:
        raise _error(404, "not_found", "Request not found")
    return request


def _not_open(request_id: str) -> HTTPException:
    current = requests.get(request_id)
    status = current.status if current is not None else "gone"
    return _error(409, "not_open", f"This request is no longer open (it is {status})")


#: The refusal of a non-admin approver deciding on their own request.
OWN_REQUEST_MESSAGE = "You cannot decide on your own request: cancel it instead"


def _refuse_own_request(request: Request, principal: Principal) -> None:
    """Only an admin decides on their own request; an `approve` holder cancels theirs."""
    if request.user_id == principal.user.id and not principal.is_admin:
        raise _error(403, "forbidden", OWN_REQUEST_MESSAGE)


# POST /requests -------------------------------------------------------------------


def _installed_for(prepared: Prepared) -> Tuple[bool, bool]:
    """`(installed, visible to the requester)` for the checked file; unknown without a SHA256."""
    sha256 = prepared.file.sha256
    if not sha256:
        return False, False
    model = core_bridge.find_model_by_sha256(sha256)
    if model is None or model.get("is_available", True) is False:
        return False, False
    if prepared.principal.is_admin:
        return True, True
    return True, model.get("id") in set(core_bridge.visible_model_ids(prepared.principal.user.id))


def _notify_approvers(request: Request, requester_name: str) -> None:
    try:
        recipients = permissions.approver_ids()
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not list who may approve request %s", request.id, exc_info=True)
        return
    notifications.request_received(recipients, request, requester_name)


@router.post("/requests")
async def create_request(
    body: Any = Body(...),
    principal: Principal = Depends(require_request),
) -> Dict[str, Any]:
    """Ask the approvers for one file; their own open request for it is answered again.

    Body: `{source, model_id, version_id, file_id, model_type?, note?}`. Data: `{"request",
    "already_requested"}`.
    """
    asked = _validate(RequestCreate, body, "request")
    user = principal.user
    try:
        prepared = await downloads.prepare_download(
            principal, DownloadRequest.model_validate(asked.model_dump(exclude={"note"})), purpose="request"
        )
        installed, visible = await asyncio.to_thread(_installed_for, prepared)
    except DownloadError as exc:
        raise download_http_error(exc) from None
    except SourceError as exc:
        raise source_http_error(exc) from None
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not check the request of %s for %s %s", user.username, asked.source, asked.model_id)
        raise _error(500, "internal_error", "The request could not be made; the server log has the details") from None
    if visible:
        raise _error(409, "already_available", "This file is already installed and in your models")

    detail, version, file = prepared.detail, prepared.version, prepared.file
    existing = await asyncio.to_thread(requests.find_open, user.id, detail.source, detail.id, version.id, file.id)
    if existing is not None:
        return _ok({"request": requests.for_viewer(existing, prepared.ctx), "already_requested": True})

    snapshot = requests.build_snapshot(detail, version, file, prepared.model_type, already_installed=installed)
    created = await asyncio.to_thread(
        lambda: requests.create(
            user_id=user.id,
            source=detail.source,
            source_model_id=detail.id,
            source_version_id=version.id,
            file_id=file.id,
            snapshot=snapshot,
            note=asked.note,
        )
    )
    logger.info("[MODEL-BROWSER] %s requested %s (%s %s, request %s)", user.username, file.name, detail.source, detail.id, created.id)
    await asyncio.to_thread(_notify_approvers, created, user.username)
    return _ok({"request": requests.for_viewer(created, prepared.ctx), "already_requested": False})


# GET /requests --------------------------------------------------------------------


@router.get("/requests")
def list_requests(
    status: Optional[List[str]] = Query(None),
    all_users: Optional[bool] = Query(None, alias="all"),
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    principal: Principal = Depends(require_requests_access),
) -> Dict[str, Any]:
    """The caller's requests (every user's for an approver unless `all=false`), newest first.

    Data: `{"requests": [...], "open_count", "can_approve"}`.
    """
    statuses = _statuses(status)
    can_approve = permissions.can_approve(principal)
    everyone = can_approve and all_users is not False
    rows = requests.list_rows(user_id=None if everyone else principal.user.id, statuses=statuses, limit=limit)
    ctx = nsfw.resolve_nsfw(principal.user)
    names = requests.Usernames()
    return _ok(
        {
            "requests": [requests.for_viewer(row, ctx, names) for row in rows],
            "open_count": requests.open_count_for(principal),
            "can_approve": can_approve,
        }
    )


# POST /requests/{id}/approve ------------------------------------------------------


async def _queue_for_requester(
    request: Request, approval: Approval, principal: Principal
) -> Tuple[Dict[str, Any], str, NsfwContext]:
    """Check the request again for its requester and queue it for them; `(answer, assign_to,
    the approver's NSFW context)`. Raises the `HTTPException` the route answers."""
    approver = principal.user
    requester = await asyncio.to_thread(permissions.user_by_id, request.user_id)
    if requester is None:
        raise _error(409, "requester_gone", "The user who made this request no longer exists: decline it instead")
    model_type = approval.model_type or request.snapshot.get("mb_type")
    try:
        file_request = DownloadRequest(
            source=request.source,
            model_id=request.source_model_id,
            version_id=request.source_version_id or "",
            file_id=request.file_id,
            model_type=model_type,
            assign_group_id=approval.assign_group_id,
        )
    except ValidationError as error:
        raise _error(400, "invalid_request", downloads.describe_validation_error(error, "request")) from None
    try:
        requester_principal = await asyncio.to_thread(permissions.principal_for, requester)
        viewer_ctx = await asyncio.to_thread(nsfw.resolve_nsfw, approver)
        prepared = await downloads.prepare_download(
            requester_principal, file_request, purpose="request", on_behalf=True
        )
        answer = await downloads.queue_prepared(
            prepared,
            request_id=request.id,
            created_by=approver.id,
            viewer_ctx=viewer_ctx,
            viewer_admin=principal.is_admin,
        )
    except DownloadError as exc:
        raise download_http_error(exc) from None
    except SourceError as exc:
        raise source_http_error(exc) from None
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not queue request %s for %s", request.id, requester.username)
        raise _error(500, "internal_error", "The request could not be approved; the server log has the details") from None
    return answer, prepared.assign_to, viewer_ctx


def _reopen(request_id: str) -> None:
    """Undo a claimed approval that could not go through: the request is `open` again."""
    try:
        requests.update(
            request_id, only_from=(requests.APPROVED,), status=requests.OPEN, decided_by=None, decision_note=None
        )
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not reopen request %s after a failed approval", request_id)


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    body: Any = Body(None),
    principal: Principal = Depends(require_approve),
) -> Dict[str, Any]:
    """Queue the requested file for its requester (see the module docstring).

    Body: `{note?, model_type?, assign_group_id?}`. Data: `{"request", "pending", "download",
    "already_installed", "already_queued"}`.
    """
    approval = _validate(Approval, body, "approval")
    approver = principal.user
    request = await asyncio.to_thread(_get_request, request_id)
    _refuse_own_request(request, principal)
    if not request.is_open:
        raise await asyncio.to_thread(_not_open, request.id)
    # Claimed first, in one statement: a second approver, a rejection or a cancellation
    # arriving meanwhile finds the request no longer open.
    claimed = await asyncio.to_thread(
        lambda: requests.set_status(
            request.id,
            requests.APPROVED,
            decided_by=approver.id,
            decision_note=approval.note,
            only_from=(requests.OPEN,),
        )
    )
    if claimed is None:
        raise await asyncio.to_thread(_not_open, request.id)
    try:
        answer, assign_to, viewer_ctx = await _queue_for_requester(claimed, approval, principal)
    except BaseException:
        await asyncio.to_thread(_reopen, claimed.id)
        raise
    approved = (
        await asyncio.to_thread(
            lambda: requests.update(claimed.id, sha256=answer["pending"]["sha256"], assign_to=assign_to)
        )
        or claimed
    )
    logger.info(
        "[MODEL-BROWSER] %s approved request %s of %s (%s)",
        approver.username,
        approved.id,
        approved.user_id,
        "already installed" if answer["already_installed"] else "already queued" if answer["already_queued"] else "queued",
    )
    await asyncio.to_thread(
        lambda: notifications.request_approved(
            approved,
            approver.username,
            already_installed=answer["already_installed"],
            already_queued=answer["already_queued"],
        )
    )
    return _ok({"request": requests.for_viewer(approved, viewer_ctx), **answer})


# POST /requests/{id}/reject -------------------------------------------------------


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: str,
    body: Any = Body(None),
    principal: Principal = Depends(require_approve),
) -> Dict[str, Any]:
    """Decline an open request. Body: `{note?}`. Data: `{"request"}`."""
    decision = _validate(Decision, body, "decision")
    approver = principal.user
    request = _get_request(request_id)
    _refuse_own_request(request, principal)
    rejected = requests.set_status(
        request.id,
        requests.REJECTED,
        decided_by=approver.id,
        decision_note=decision.note,
        only_from=(requests.OPEN,),
    )
    if rejected is None:
        raise _not_open(request.id)
    logger.info("[MODEL-BROWSER] %s declined request %s of %s", approver.username, rejected.id, rejected.user_id)
    notifications.request_rejected(rejected, approver.username)
    return _ok({"request": requests.for_viewer(rejected, nsfw.resolve_nsfw(approver))})


# DELETE /requests/{id} ------------------------------------------------------------


@router.delete("/requests/{request_id}")
def cancel_request(request_id: str, principal: Principal = Depends(current_principal)) -> Dict[str, Any]:
    """The author cancels their own open request. Data: `{"request"}`."""
    user = principal.user
    request = _get_request(request_id)
    if request.user_id != user.id:
        raise _error(403, "forbidden", "Only the user who made a request can cancel it")
    cancelled = requests.set_status(request.id, requests.CANCELLED, only_from=(requests.OPEN,))
    if cancelled is None:
        raise _not_open(request.id)
    logger.info("[MODEL-BROWSER] %s cancelled request %s", user.username, cancelled.id)
    return _ok({"request": requests.for_viewer(cancelled, nsfw.resolve_nsfw(user))})
