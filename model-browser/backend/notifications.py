"""The plugin's notification types, and the helpers that send them (PLAN.md §4.4).

Five types, declared on the core's notification registry by the `notification_type.register`
hook (`hooks/notification_hooks.py`), so each one appears in every user's notification
preferences and can be turned off there:
- `model-browser.request_received`: someone asked for a model; sent to every user who may
  approve it (admins and holders of `approve`), never to the requester;
- `model-browser.request_approved`, `model-browser.request_rejected`: to the requester, when
  an approver decides;
- `model-browser.download_done`, `model-browser.download_failed`: to the user a download was
  for (a direct download, or an approved request), when it ends.

Every notification goes to one user through `core_bridge.notify` (never a broadcast), with
category "plugin" and source "model-browser". Sending never raises: a notification that
cannot be sent is logged, and whatever triggered it goes on. The request notifications carry
a `link` to the page's requests in their metadata, which the core's notification panel shows
as an "Open" link.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from . import core_bridge

logger = logging.getLogger("plugins.model-browser")

REQUEST_RECEIVED = "model-browser.request_received"
REQUEST_APPROVED = "model-browser.request_approved"
REQUEST_REJECTED = "model-browser.request_rejected"
DOWNLOAD_DONE = "model-browser.download_done"
DOWNLOAD_FAILED = "model-browser.download_failed"

#: The Model Browser page, and its requests (the core's notification panel opens `metadata.link`).
PAGE_LINK = "/plugins/model-browser"
REQUESTS_LINK = PAGE_LINK + "?tab=requests"
REQUESTS_LINK_LABEL = "Open requests"

#: Longest part of a note quoted in a notification.
NOTE_EXCERPT_LENGTH = 200


@dataclass(frozen=True)
class NotificationType:
    """What the core's `NotificationTypeSpec` needs to list a type in the preferences."""

    key: str
    label: str
    description: str
    category: str = "plugin"


TYPES = (
    NotificationType(
        key=REQUEST_RECEIVED,
        label="Model Browser: new model request",
        description="Someone asked for a model in the Model Browser and you can approve or decline it.",
    ),
    NotificationType(
        key=REQUEST_APPROVED,
        label="Model Browser: request approved",
        description="One of your model requests was approved and the model is on its way.",
    ),
    NotificationType(
        key=REQUEST_REJECTED,
        label="Model Browser: request declined",
        description="One of your model requests was declined.",
    ),
    NotificationType(
        key=DOWNLOAD_DONE,
        label="Model Browser: model ready",
        description="A model you downloaded or requested is downloaded and ready in your models.",
    ),
    NotificationType(
        key=DOWNLOAD_FAILED,
        label="Model Browser: download failed",
        description="A model you downloaded or requested could not be downloaded.",
    ),
)

#: Every key the plugin sends.
KEYS = tuple(item.key for item in TYPES)


def send(
    user_id: str,
    kind: str,
    *,
    title: str,
    message: str,
    level: str = "info",
    metadata: Optional[Mapping[str, Any]] = None,
) -> bool:
    """One notification of type `kind` to one user; False when it could not be sent. Never raises."""
    try:
        core_bridge.notify(
            user_id=user_id,
            notification_type=kind,
            title=title,
            message=message,
            level=level,
            metadata=metadata,
        )
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not send the %s notification to %s", kind, user_id, exc_info=True)
        return False
    return True


# Requests -------------------------------------------------------------------------


def _excerpt(text: Optional[str]) -> Optional[str]:
    """`text` on one line, cut to `NOTE_EXCERPT_LENGTH`; None when blank."""
    if not text or not text.strip():
        return None
    line = " ".join(text.split())
    if len(line) > NOTE_EXCERPT_LENGTH:
        line = line[: NOTE_EXCERPT_LENGTH - 3].rstrip() + "..."
    return line


def request_label(snapshot: Mapping[str, Any]) -> str:
    """How a request names its file: `Model name (file name)`, or whichever of the two is known."""
    name = snapshot.get("name") if isinstance(snapshot.get("name"), str) else None
    file_name = snapshot.get("file_name") if isinstance(snapshot.get("file_name"), str) else None
    name, file_name = (name or "").strip(), (file_name or "").strip()
    if name and file_name and name != file_name:
        return f"{name} ({file_name})"
    return name or file_name or "a model"


def request_metadata(request: Any) -> Dict[str, Any]:
    """What every request notification carries: the request and the file it names, and the link."""
    return {
        "request_id": request.id,
        "source": request.source,
        "source_model_id": request.source_model_id,
        "source_version_id": request.source_version_id,
        "file_id": request.file_id,
        "link": REQUESTS_LINK,
        "link_label": REQUESTS_LINK_LABEL,
    }


def request_received(recipient_ids: Iterable[str], request: Any, requester_name: str) -> int:
    """Tell everyone in `recipient_ids` but the requester that `request` waits for a decision;
    returns how many notifications were sent."""
    message = f"{requester_name} asked for {request_label(request.snapshot)}."
    note = _excerpt(request.note)
    if note:
        message += f' Note: "{note}"'
    sent = 0
    for user_id in sorted(set(recipient_ids)):
        if not user_id or user_id == request.user_id:
            continue
        sent += send(
            user_id,
            REQUEST_RECEIVED,
            title="New model request",
            message=message,
            level="info",
            metadata=request_metadata(request),
        )
    return sent


def request_approved(
    request: Any, approver_name: str, *, already_installed: bool = False, already_queued: bool = False
) -> bool:
    """Tell the requester their request was approved, and what happens next."""
    if already_installed:
        outcome = "the model is already installed and is being added to your models"
    elif already_queued:
        outcome = "the file is already being downloaded; you will be told when it is ready"
    else:
        outcome = "it is being downloaded for you"
    message = f"{approver_name} approved your request for {request_label(request.snapshot)}: {outcome}."
    note = _excerpt(request.decision_note)
    if note:
        message += f' Note: "{note}"'
    metadata = {**request_metadata(request), "sha256": request.sha256}
    return send(request.user_id, REQUEST_APPROVED, title="Model request approved", message=message, level="success", metadata=metadata)


def request_rejected(request: Any, approver_name: str) -> bool:
    """Tell the requester their request was declined, with the approver's note."""
    message = f"{approver_name} declined your request for {request_label(request.snapshot)}."
    note = _excerpt(request.decision_note)
    if note:
        message += f' Note: "{note}"'
    return send(
        request.user_id,
        REQUEST_REJECTED,
        title="Model request declined",
        message=message,
        level="warning",
        metadata=request_metadata(request),
    )


# Downloads ------------------------------------------------------------------------


def download_done(user_id: str, label: str, where: str, metadata: Mapping[str, Any]) -> bool:
    """`<label>: <where>.`, e.g. "Detail Tweaker XL (x.safetensors): it is now in your models."."""
    return send(
        user_id, DOWNLOAD_DONE, title="Model downloaded", message=f"{label}: {where}.", level="success", metadata=metadata
    )


def download_failed(user_id: str, label: str, reason: Optional[str], metadata: Mapping[str, Any]) -> bool:
    """`<label>: <reason>`."""
    return send(
        user_id,
        DOWNLOAD_FAILED,
        title="Model download failed",
        message=f"{label}: {reason or 'the download failed'}",
        level="error",
        metadata=metadata,
    )
