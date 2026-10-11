"""The `model_browser_requests` table (PLAN.md §4.4): models users asked an approver for.

Statuses:
- `open`: waiting for a decision. Its author may cancel it (`cancelled`); an approver may
  decline it (`rejected`) or approve it (`approved`);
- `approved`: the file was queued for the requester, or is being assigned to them when it
  was installed already. `sha256` links the request to the `model_browser_pending` row
  (`backend/pending.py`) that carries the file, `assign_to` says who will see the model
  (`user:<id>`, `group:<id>`, `none`). The download watcher closes it: `done` once the model
  is assigned and enriched, `failed` when the download fails.

One open request per requester and file: `find_open` finds it again, so asking twice for
the same file answers the same request; another user asking for it gets their own.

`snapshot` describes the file as it was when it was asked for, so the list shows it without
reading the source again (`build_snapshot`): `{name, type, mb_type, version_name,
base_model, file_name, size_bytes, nsfw, poi, license, thumbnail_url, source_url, sha256,
already_installed}`. `thumbnail_url` is the first image of the version that anyone may see
(never an NSFW image), https on a public host, or None.

Requests go out as `to_json()`, with the username of their author and of the approver
(None for a user who no longer exists); `for_viewer` also drops the thumbnail for a viewer
who does not see the model (NSFW in `hide` mode, or a real person with `hide_poi`).
"""

import ipaddress
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlsplit

from src.plugin_api import generate_ulid

from . import nsfw_filter, permissions
from .schema import File, ModelDetail, NsfwContext, Version

TABLE = "model_browser_requests"
OPEN = "open"
APPROVED = "approved"
REJECTED = "rejected"
CANCELLED = "cancelled"
DONE = "done"
FAILED = "failed"
STATUSES = (OPEN, APPROVED, REJECTED, CANCELLED, DONE, FAILED)
#: Longest note a requester or an approver may write.
MAX_NOTE_LENGTH = 1000

_COLUMNS = (
    "id", "user_id", "source", "source_model_id", "source_version_id", "file_id", "snapshot", "note",
    "status", "decided_by", "decision_note", "sha256", "assign_to", "created_at", "updated_at",
)
_UPDATABLE = frozenset({"status", "decided_by", "decision_note", "sha256", "assign_to"})


class Usernames:
    """User id -> username (None for a user who no longer exists), each id looked up once."""

    def __init__(self, lookup: Optional[Callable[[str], Any]] = None) -> None:
        self._lookup = lookup or permissions.user_by_id
        self._known: Dict[str, Optional[str]] = {}

    def __call__(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        if user_id not in self._known:
            user = self._lookup(user_id)
            self._known[user_id] = getattr(user, "username", None) if user is not None else None
        return self._known[user_id]


@dataclass(frozen=True)
class Request:
    id: str
    user_id: str
    source: str
    source_model_id: str
    file_id: str
    snapshot: Dict[str, Any] = field(default_factory=dict)
    source_version_id: Optional[str] = None
    note: Optional[str] = None
    status: str = OPEN
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    #: The pending row's key once the request is approved.
    sha256: Optional[str] = None
    #: Who sees the model once approved: "user:<id>", "group:<id>" or "none".
    assign_to: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    def to_json(self, usernames: Optional[Usernames] = None) -> Dict[str, Any]:
        """The request as the routes send it: its columns (the snapshot as an object), and
        `username` / `decided_by_username`."""
        names = usernames or Usernames()
        data = {column: getattr(self, column) for column in _COLUMNS}
        data["snapshot"] = dict(self.snapshot)
        data["username"] = names(self.user_id)
        data["decided_by_username"] = names(self.decided_by)
        return data


def for_viewer(request: Request, ctx: NsfwContext, usernames: Optional[Usernames] = None) -> Dict[str, Any]:
    """`request.to_json()` with its snapshot as this viewer may see it (`snapshot_for_viewer`)."""
    data = request.to_json(usernames)
    data["snapshot"] = snapshot_for_viewer(request.snapshot, ctx)
    return data


def snapshot_for_viewer(snapshot: Mapping[str, Any], ctx: NsfwContext) -> Dict[str, Any]:
    """The snapshot without its thumbnail, marked `hidden`, for a viewer who may not see the
    model (NSFW while they hide NSFW, a real person while `hide_poi` is on); as it is otherwise.

    The thumbnail is never an NSFW image, but it shows a model this viewer is not shown
    anywhere else; its name and file stay, so an approver can still decide.
    """
    shown = dict(snapshot)
    hidden = (bool(shown.get("nsfw")) and nsfw_filter.display_mode(ctx) == "hide") or (
        ctx.hide_poi and bool(shown.get("poi"))
    )
    if hidden:
        shown["thumbnail_url"] = None
        shown["hidden"] = True
    return shown


# The snapshot ---------------------------------------------------------------------


def is_public_https_url(url: Any) -> bool:
    """https on the default port, no credentials, a host that is a public name (no IP, no local name)."""
    if not isinstance(url, str) or not url.isascii():
        return False
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char == "\\" for char in url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or port not in (None, 443) or "@" in parts.netloc:
        return False
    if not host or host.endswith(".") or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not host.rsplit(".", 1)[-1].isdigit()


def safe_thumbnail(version: Version) -> Optional[str]:
    """The url of the version's first image anyone may see: not NSFW, no real person, a still
    image, https on a public host. None when there is none."""
    for image in version.images:
        if image.nsfw or image.poi or image.kind != "image":
            continue
        if is_public_https_url(image.url):
            return image.url
    return None


def build_snapshot(
    detail: ModelDetail, version: Version, file: File, mb_type: str, *, already_installed: bool
) -> Dict[str, Any]:
    """What a request remembers of the file it asks for (see the module docstring).

    `detail` is the one filtered for the requester's NSFW context.
    """
    return {
        "name": detail.name,
        "type": detail.type,
        "mb_type": mb_type,
        "version_name": version.name,
        "base_model": version.base_model,
        "file_name": file.name,
        "size_bytes": file.size_bytes,
        "nsfw": bool(detail.nsfw or version.nsfw),
        "poi": bool(detail.poi),
        "license": detail.license.summary if detail.license is not None else None,
        "thumbnail_url": safe_thumbnail(version),
        "source_url": detail.source_url,
        "sha256": file.sha256.strip().lower() if file.sha256 else None,
        "already_installed": bool(already_installed),
    }


# The table ------------------------------------------------------------------------


def _from_record(record: Mapping[str, Any]) -> Request:
    try:
        snapshot = json.loads(record["snapshot"] or "{}")
    except (TypeError, ValueError):
        snapshot = {}
    values = {column: record[column] for column in _COLUMNS if column != "snapshot"}
    for stamp in ("created_at", "updated_at"):
        if values.get(stamp) is not None:
            values[stamp] = str(values[stamp])
    return Request(snapshot=snapshot if isinstance(snapshot, dict) else {}, **values)


def create(
    *,
    user_id: str,
    source: str,
    source_model_id: str,
    source_version_id: Optional[str],
    file_id: str,
    snapshot: Mapping[str, Any],
    note: Optional[str] = None,
) -> Request:
    """A new `open` request."""
    from src.plugin_api import db

    request_id = generate_ulid()
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABLE} (id, user_id, source, source_model_id, source_version_id, file_id, snapshot, "
            f"note, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, user_id, source, source_model_id, source_version_id, file_id, json.dumps(dict(snapshot)), note, OPEN),
        )
    return get(request_id)


def get(request_id: str) -> Optional[Request]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE id = ?", (request_id,))
        record = cursor.fetchone()
    return _from_record(record) if record else None


def list_rows(
    *,
    user_id: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
    limit: int = 200,
) -> List[Request]:
    """Requests newest first, optionally of one author and/or in some statuses."""
    from src.plugin_api import db

    clauses: List[str] = []
    params: List[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if statuses is not None:
        wanted = [status for status in statuses if status in STATUSES]
        if not wanted:
            return []
        clauses.append(f"status IN ({', '.join('?' * len(wanted))})")
        params.extend(wanted)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE}{where} ORDER BY created_at DESC, id DESC LIMIT ?",
            (*params, max(1, min(int(limit), 1000))),
        )
        records = cursor.fetchall()
    return [_from_record(record) for record in records]


def find_open(
    user_id: str, source: str, source_model_id: str, source_version_id: Optional[str], file_id: str
) -> Optional[Request]:
    """`user_id`'s open request for this file, if they have one (the oldest)."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE user_id = ? AND source = ? AND source_model_id = ? "
            f"AND source_version_id IS ? AND file_id = ? AND status = ? ORDER BY created_at, id LIMIT 1",
            (user_id, source, source_model_id, source_version_id, file_id, OPEN),
        )
        record = cursor.fetchone()
    return _from_record(record) if record else None


def update(request_id: str, *, only_from: Optional[Iterable[str]] = None, **fields: Any) -> Optional[Request]:
    """Set some of `status`, `decided_by`, `decision_note`, `sha256`, `assign_to` (None clears one).

    With `only_from`, only while the request is in one of those statuses: the change and the
    check are one statement, so two approvers never both win. Returns the request as stored
    after the change, or None when it does not exist or was not in `only_from`.
    """
    from src.plugin_api import db

    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise ValueError(f"cannot update {sorted(unknown)} on a request")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"unknown request status {fields['status']!r}")
    if not fields:
        return get(request_id)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    query = f"UPDATE {TABLE} SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    params: List[Any] = [*fields.values(), request_id]
    if only_from is not None:
        allowed = [status for status in only_from if status in STATUSES]
        if not allowed:
            return None
        query += f" AND status IN ({', '.join('?' * len(allowed))})"
        params.extend(allowed)
    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        changed = cursor.rowcount > 0
    return get(request_id) if changed else None


def set_status(
    request_id: str,
    status: str,
    *,
    decided_by: Optional[str] = None,
    decision_note: Optional[str] = None,
    sha256: Optional[str] = None,
    assign_to: Optional[str] = None,
    only_from: Optional[Iterable[str]] = None,
) -> Optional[Request]:
    """Move a request to `status`, setting the other values given (None leaves one as it is).

    See `update` for `only_from` and the answer.
    """
    fields: Dict[str, Any] = {"status": status}
    for name, value in (
        ("decided_by", decided_by),
        ("decision_note", decision_note),
        ("sha256", sha256),
        ("assign_to", assign_to),
    ):
        if value is not None:
            fields[name] = value
    return update(request_id, only_from=only_from, **fields)


def list_approved_for_sha256(sha256: str) -> List[Request]:
    """The approved requests linked to the pending row `sha256` (oldest first)."""
    from src.plugin_api import db

    if not sha256:
        return []
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE sha256 = ? AND status = ? ORDER BY created_at, id",
            (sha256, APPROVED),
        )
        records = cursor.fetchall()
    return [_from_record(record) for record in records]


def relink(old_sha256: str, new_sha256: str) -> int:
    """Point the requests linked to the pending row `old_sha256` at `new_sha256` (the row was
    moved to its model's real hash); returns how many."""
    from src.plugin_api import db

    if not old_sha256 or not new_sha256 or old_sha256 == new_sha256:
        return 0
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {TABLE} SET sha256 = ?, updated_at = CURRENT_TIMESTAMP WHERE sha256 = ?",
            (new_sha256, old_sha256),
        )
        return cursor.rowcount


def open_count(exclude_user_id: Optional[str] = None) -> int:
    """How many requests wait for a decision, those of `exclude_user_id` left out."""
    from src.plugin_api import db

    query = f"SELECT COUNT(*) AS count FROM {TABLE} WHERE status = ?"
    params: List[Any] = [OPEN]
    if exclude_user_id is not None:
        query += " AND user_id != ?"
        params.append(exclude_user_id)
    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        record = cursor.fetchone()
    return int(record["count"]) if record else 0


def open_count_for(principal: "permissions.Principal") -> int:
    """The open requests `principal` may decide on (`GET /me`, `GET /requests`): every one for
    an admin, the other users' for a holder of `approve` (who may not decide on their own),
    0 for anyone else."""
    if principal.is_admin:
        return open_count()
    if permissions.can_approve(principal):
        return open_count(exclude_user_id=principal.user.id)
    return 0
