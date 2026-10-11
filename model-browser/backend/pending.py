"""The `model_browser_pending` table (PLAN.md §7.3, §7.4): one row per file the plugin
downloads, from the moment it is queued until it is assigned and enriched.

The key is the file's SHA256 (lower-case hex) when the source gives one: that is what
the core indexer computes and what the `model-browser` provider is asked for
(`get_model_by_hash`). A file without a known hash (some Hugging Face files, every file of
a gated repo read anonymously) is keyed `nohash:<download url>` until the watcher finds the
indexed model and `rekey()`s the row to the real hash.

Statuses: `queued` (on the core queue) -> `indexed` (model id known) -> `assigned` ->
`enriched` (done); `failed` at any point, with `error`. `info` holds the normalised
detail cut down to the chosen version and file (`backend/schema.py` shapes, as JSON), which
is what the provider turns into a `ProviderModelInfo`.
"""

import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional

TABLE = "model_browser_pending"
STATUSES = ("queued", "indexed", "assigned", "enriched", "failed")
UNFINISHED = ("queued", "indexed", "assigned")
NOHASH_PREFIX = "nohash:"

_COLUMNS = (
    "sha256", "source", "source_model_id", "source_version_id", "file_name", "info",
    "requested_by", "assign_to", "request_id", "download_id", "limit_ref_id", "model_id",
    "status", "error", "created_at", "updated_at",
)
_UPDATABLE = frozenset({"download_id", "limit_ref_id", "model_id", "status", "error", "assign_to", "request_id"})


def key_for(sha256: Optional[str], download_url: str) -> str:
    """The row key: the lower-case hash, or `nohash:<url>` while the hash is unknown."""
    if sha256:
        return sha256.strip().lower()
    return NOHASH_PREFIX + download_url


def is_nohash(key: str) -> bool:
    return key.startswith(NOHASH_PREFIX)


@dataclass(frozen=True)
class PendingRow:
    sha256: str
    source: str
    source_model_id: str
    file_name: str
    requested_by: str
    #: "user:<id>" | "group:<id>" | "none" (an admin downloading for the whole instance).
    assign_to: str
    info: Dict[str, Any] = field(default_factory=dict)
    source_version_id: Optional[str] = None
    request_id: Optional[str] = None
    download_id: Optional[str] = None
    limit_ref_id: Optional[str] = None
    model_id: Optional[str] = None
    status: str = "queued"
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def nohash(self) -> bool:
        return is_nohash(self.sha256)

    @property
    def finished(self) -> bool:
        return self.status not in UNFINISHED

    def to_json(self) -> Dict[str, Any]:
        """The row as the `GET /downloads` route sends it (the `info` JSON included)."""
        return {column: getattr(self, column) for column in _COLUMNS}


def _row_from_record(record: Mapping[str, Any]) -> PendingRow:
    try:
        info = json.loads(record["info"] or "{}")
    except (TypeError, ValueError):
        info = {}
    values = {column: record[column] for column in _COLUMNS if column != "info"}
    for stamp in ("created_at", "updated_at"):
        if values.get(stamp) is not None:
            values[stamp] = str(values[stamp])
    return PendingRow(info=info if isinstance(info, dict) else {}, **values)


def get(key: str) -> Optional[PendingRow]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM {TABLE} WHERE sha256 = ?", (key,))
        record = cursor.fetchone()
    return _row_from_record(record) if record else None


def insert(row: PendingRow) -> PendingRow:
    """Insert a new row; raises `sqlite3.IntegrityError` when the key already exists."""
    from src.plugin_api import db

    if row.status not in STATUSES:
        raise ValueError(f"unknown pending status {row.status!r}")
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABLE} (sha256, source, source_model_id, source_version_id, file_name, info, "
            f"requested_by, assign_to, request_id, download_id, limit_ref_id, model_id, status, error) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.sha256, row.source, row.source_model_id, row.source_version_id, row.file_name,
                json.dumps(row.info), row.requested_by, row.assign_to, row.request_id, row.download_id,
                row.limit_ref_id, row.model_id, row.status, row.error,
            ),
        )
    return get(row.sha256) or row


def update(key: str, **fields: Any) -> Optional[PendingRow]:
    """Set some of `download_id`, `limit_ref_id`, `model_id`, `status`, `error`, `assign_to`, `request_id`."""
    from src.plugin_api import db

    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise ValueError(f"cannot update {sorted(unknown)} on a pending row")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"unknown pending status {fields['status']!r}")
    if not fields:
        return get(key)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {TABLE} SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE sha256 = ?",
            (*fields.values(), key),
        )
    return get(key)


def rekey(old_key: str, sha256: str) -> Optional[PendingRow]:
    """Move a `nohash:` row to the real hash once the indexed model revealed it.

    When a row with the real hash already exists (the same file was queued twice), the
    old row is dropped and the existing one is returned.
    """
    from src.plugin_api import db

    new_key = sha256.strip().lower()
    existing = get(new_key)
    with db.get_cursor() as cursor:
        if existing is not None:
            cursor.execute(f"DELETE FROM {TABLE} WHERE sha256 = ?", (old_key,))
        else:
            cursor.execute(
                f"UPDATE {TABLE} SET sha256 = ?, updated_at = CURRENT_TIMESTAMP WHERE sha256 = ?",
                (new_key, old_key),
            )
    return get(new_key)


def delete(key: str) -> bool:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE} WHERE sha256 = ?", (key,))
        return cursor.rowcount > 0


def list_rows(
    *,
    requested_by: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
    limit: int = 200,
) -> List[PendingRow]:
    """Rows newest first, optionally for one requester and/or some statuses."""
    from src.plugin_api import db

    clauses, params = [], []
    if requested_by is not None:
        clauses.append("requested_by = ?")
        params.append(requested_by)
    if statuses is not None:
        wanted = [status for status in statuses if status in STATUSES]
        if not wanted:
            return []
        clauses.append(f"status IN ({', '.join('?' * len(wanted))})")
        params.extend(wanted)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM {TABLE}{where} ORDER BY created_at DESC, sha256 LIMIT ?",
            (*params, max(1, min(int(limit), 1000))),
        )
        records = cursor.fetchall()
    return [_row_from_record(record) for record in records]


def list_unfinished() -> List[PendingRow]:
    """Every row the watcher still has to move on (oldest first)."""
    rows = list_rows(statuses=UNFINISHED, limit=1000)
    return list(reversed(rows))


def with_status(row: PendingRow, status: str, error: Optional[str] = None) -> PendingRow:
    """A copy of `row` with a new status, for callers that keep the row in memory."""
    return replace(row, status=status, error=error)
