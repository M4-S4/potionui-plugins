"""Plan quotas on downloads (PLAN.md §4.5): checked before a file is queued, recorded once it
is queued, refunded when it fails.

Two kinds (manifest `limit_kinds:`), each counted per month, which an admin adds to the
core's plans like any other limit:
- `model-browser.downloads` (count): one per file queued for a user;
- `model-browser.download_bytes` (bytes): the size of that file, when the source gives it.

The core never enforces them (`limit_handlers.never_applies`): it only checks limits when a
user submits or uploads. Before queueing a file for a user (a direct download, or an approved
request, for the requester), `check_quota` asks `core_bridge.limit_status` where that user
stands for both kinds, and raises `QuotaExceeded` (403 `limit_exceeded`) when one more file
would go over: one more download over the count, or the file's size over the volume (a file
of unknown size only once the volume is used up). `limit_status` answers "unlimited" when the
plans cannot be read: a broken quota never blocks a download.

Once the file is on the core queue, `record` adds one event per kind to the core's limit
ledger (`LimitEvents.record(user_id, kind, units, ref_id)`). Their `ref_id` (`new_ref_id`,
unique per queued file, kept as the pending row's `limit_ref_id`) lets `refund` cancel both
when the download fails or is cancelled. A file already installed is only assigned, and a
file already on its way is not queued twice: neither counts. Recording and refunding never
raise.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.plugin_api import LimitEvents, generate_ulid

from . import PLUGIN_ID, core_bridge

logger = logging.getLogger("plugins.model-browser")

DOWNLOADS = "model-browser.downloads"
DOWNLOAD_BYTES = "model-browser.download_bytes"
#: The plugin's kinds, in the order they are checked.
KINDS = (DOWNLOADS, DOWNLOAD_BYTES)
#: Same as `label:` in manifest.yml (tests/test_manifest.py checks it).
LABELS = {DOWNLOADS: "Model downloads per month", DOWNLOAD_BYTES: "Downloaded model bytes per month"}

_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB")


class QuotaExceeded(Exception):
    """Queueing one more file would take the user over one of the plugin's plan limits."""

    def __init__(
        self,
        kind: str,
        used: float,
        limit: float,
        incoming: Optional[float],
        resets_at: Optional[str],
        message: str,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.used = used
        self.limit = limit
        self.incoming = incoming
        self.resets_at = resets_at
        self.message = message

    def payload(self) -> Dict[str, Any]:
        """The fields the routes add to their `limit_exceeded` error."""
        return {
            "kind": self.kind,
            "label": LABELS.get(self.kind, self.kind),
            "used": _number(self.used),
            "limit": _number(self.limit),
            "incoming": None if self.incoming is None else _number(self.incoming),
            "resets_at": self.resets_at,
        }


def _number(value: float) -> float:
    value = float(value)
    return int(value) if value.is_integer() else value


def _trim(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def format_amount(kind: str, value: float) -> str:
    """`3`, or `4.2 GB` for the volume."""
    if kind != DOWNLOAD_BYTES:
        return _trim(float(value))
    value = float(value)
    index = 0
    while index < len(_BYTE_UNITS) - 1 and value >= 1024 ** (index + 1):
        index += 1
    return f"{_trim(value / 1024 ** index)} {_BYTE_UNITS[index]}"


def exceeded(limit: float, used: float, incoming: Optional[float]) -> bool:
    """The core's rule: without a known amount, refuse once the limit is reached; with one, when it would go over."""
    if incoming is None:
        return used >= limit
    return used + incoming > limit


def _resets(resets_at: Optional[str]) -> str:
    """` It resets on Nov 1.` for an ISO date in the plans' time zone; empty when unknown."""
    if not resets_at:
        return ""
    try:
        moment = datetime.fromisoformat(resets_at)
    except ValueError:
        return ""
    return f" It resets on {moment.strftime('%b')} {moment.day}."


def refusal_message(
    kind: str,
    used: float,
    limit: float,
    incoming: Optional[float],
    resets_at: Optional[str] = None,
    contact_line: str = "",
    requester_name: Optional[str] = None,
) -> str:
    """The refusal, to the user themselves, or to an approver when `requester_name` is given."""
    label = LABELS.get(kind, kind).lower()
    usage = f"{format_amount(kind, used)} of {format_amount(kind, limit)}"
    file_goes_over = kind == DOWNLOAD_BYTES and incoming is not None and used < limit
    size = format_amount(kind, incoming) if incoming is not None else ""
    if requester_name is None:
        if file_goes_over:
            text = f"This file ({size}) would go over your {label} limit: you have used {usage}."
        else:
            text = f"You have reached your {label} limit: {usage} used."
    elif file_goes_over:
        text = f"This file ({size}) would go over the {label} limit of {requester_name}: they have used {usage}."
    else:
        text = f"{requester_name} has reached their {label} limit: {usage} used."
    text += _resets(resets_at)
    if requester_name is None and contact_line.strip():
        text += f" {contact_line.strip()}"
    return text


def check_quota(user_id: str, size_bytes: Optional[int], *, requester_name: Optional[str] = None) -> None:
    """Raise `QuotaExceeded` when one more file of `size_bytes` (None: unknown) queued for
    `user_id` would go over one of the plugin's plan limits.

    `requester_name`: an approver is queueing the file on that user's request; the message
    then speaks of the requester. An exempt admin, a user without a plan or without these
    limits, and plans that cannot be read all pass.
    """
    for kind in KINDS:
        try:
            status = core_bridge.limit_status(user_id, kind)
        except Exception:
            logger.warning("[MODEL-BROWSER] Could not read the %s limit of %s; not enforcing it", kind, user_id, exc_info=True)
            continue
        limit, used = status.get("limit"), status.get("used")
        if limit is None or used is None or status.get("exempt"):
            continue
        if kind == DOWNLOADS:
            incoming: Optional[float] = 1
        else:
            incoming = size_bytes if isinstance(size_bytes, int) and size_bytes > 0 else None
        if exceeded(float(limit), float(used), incoming):
            message = refusal_message(
                kind,
                float(used),
                float(limit),
                incoming,
                status.get("resets_at"),
                str(status.get("contact_line") or ""),
                requester_name,
            )
            raise QuotaExceeded(kind, float(used), float(limit), incoming, status.get("resets_at"), message)


def new_ref_id() -> str:
    """A `ref_id` for the events of one queued file: unique, so refunding a failed download
    never refunds an earlier download of the same file."""
    return f"{PLUGIN_ID}:{generate_ulid()}"


def record(user_id: str, size_bytes: Optional[int], ref_id: str) -> None:
    """Count one file queued for `user_id`: one download, and its size when known. Never raises."""
    events = [(DOWNLOADS, 1)]
    if isinstance(size_bytes, int) and size_bytes > 0:
        events.append((DOWNLOAD_BYTES, size_bytes))
    for kind, units in events:
        try:
            LimitEvents.record(user_id, kind, units, ref_id)
        except Exception:
            logger.warning("[MODEL-BROWSER] Could not record a %s event for %s", kind, user_id, exc_info=True)


def refund(ref_id: Optional[str]) -> int:
    """Cancel the events recorded under `ref_id` (a download that failed); how many. Never raises."""
    if not ref_id:
        return 0
    try:
        return int(LimitEvents.refund(ref_id) or 0)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not refund the limit events of %s", ref_id, exc_info=True)
        return 0
