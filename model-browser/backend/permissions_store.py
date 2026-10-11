"""The `model_browser_group_permissions` table (PLAN.md §4.3): what each user group may do.

One row per group the admin edited: `capabilities` holds a JSON list, `params` a JSON
object (`sources`, `model_types`, `max_file_gb`, `assign_to`, `allow_remote`). A group
without a row gets its install-time default (`default_row`). `permissions.py` merges the
rows of a user's groups into their grant; `routes_permissions.py` lists and replaces
them for the admin, and deletes the rows of groups the core no longer has.

Reading is tolerant: a missing or malformed value takes its default, so a row written by
another version of the plugin, or edited by hand, never breaks a request.

The vocabulary (capabilities, sources, defaults) is defined here, at the bottom of the
import chain, and re-exported by `permissions.py`.
"""

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional

TABLE = "model_browser_group_permissions"

#: What a group can be granted (PLAN.md §4.1).
CAPABILITIES = ("browse", "request", "download", "approve")

#: Every source the plugin knows, in display order (the values of `schema.SourceId`).
SOURCE_IDS = ("civitai", "huggingface", "openmodeldb", "civarchive")

#: Who a downloaded model is assigned to: the user, or one of their groups (chosen at download).
ASSIGN_TO = ("user", "group")

#: What a group gets when the admin never edited its row (PLAN.md §4.2); any other group gets nothing.
DEFAULT_CAPABILITIES = {
    "all_users": frozenset({"browse", "request"}),
    "all_admins": frozenset(CAPABILITIES),
}

#: Sources a group may download from unless the admin says otherwise: CivArchive is opt-in (§8.5).
DEFAULT_SOURCES = frozenset({"civitai", "huggingface", "openmodeldb"})


@dataclass(frozen=True)
class Row:
    """One group's rights, with one parameter set. It counts in a user's download view when
    `capabilities` includes `download`, and in their request view when it includes `request`
    (`allow_remote` only ever counts for downloads); otherwise it is ignored."""

    group_id: str
    capabilities: FrozenSet[str] = frozenset()
    sources: FrozenSet[str] = DEFAULT_SOURCES
    #: PotionUI model types the group may download or request; empty means every type.
    model_types: FrozenSet[str] = frozenset()
    #: Largest file the group may download or request, in GB; None means no limit.
    max_file_gb: Optional[float] = None
    assign_to: str = "user"
    allow_remote: bool = False

    def __post_init__(self) -> None:
        for name in ("capabilities", "sources", "model_types"):
            object.__setattr__(self, name, frozenset(getattr(self, name)))

    def params_json(self) -> Dict[str, Any]:
        """The `params` object, lists sorted."""
        return {
            "sources": sorted(self.sources),
            "model_types": sorted(self.model_types),
            "max_file_gb": self.max_file_gb,
            "assign_to": self.assign_to,
            "allow_remote": self.allow_remote,
        }

    def to_json(self) -> Dict[str, Any]:
        """`{"group_id", "capabilities", "params"}`: the shape stored, sent by the routes and accepted back."""
        return {"group_id": self.group_id, "capabilities": sorted(self.capabilities), "params": self.params_json()}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Row":
        """The row `to_json()` describes; only `group_id` is required.

        A missing or malformed value takes its default (`params` keys included).
        Unknown capabilities and sources are dropped; model types are kept as they
        are, since dropping them could empty the set, which would allow every type.
        """
        params = data.get("params")
        if not isinstance(params, Mapping):
            params = {}
        assign_to = params.get("assign_to")
        return cls(
            group_id=str(data["group_id"]),
            capabilities=_strings(data.get("capabilities"), frozenset()) & frozenset(CAPABILITIES),
            sources=_strings(params.get("sources"), DEFAULT_SOURCES) & frozenset(SOURCE_IDS),
            model_types=_strings(params.get("model_types"), frozenset()),
            max_file_gb=_size_gb(params.get("max_file_gb")),
            assign_to=assign_to if assign_to in ASSIGN_TO else "user",
            allow_remote=params.get("allow_remote") is True,
        )


def default_row(group_id: str) -> Row:
    """A group's rights while it has no row: `all_users` browse and request, `all_admins` everything, others nothing."""
    return Row(group_id=group_id, capabilities=DEFAULT_CAPABILITIES.get(group_id, frozenset()))


def row_or_default(rows: Mapping[str, Row], group_id: str) -> Row:
    """The group's stored row from `load_rows()`, or its default."""
    row = rows.get(group_id)
    return row if row is not None else default_row(group_id)


def load_rows() -> Dict[str, Row]:
    """Every stored row, by group id, including rows of groups the core has deleted since."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT group_id, capabilities, params FROM {TABLE}")
        records = cursor.fetchall()
    return {
        record["group_id"]: Row.from_json(
            {
                "group_id": record["group_id"],
                "capabilities": _loads(record["capabilities"]),
                "params": _loads(record["params"]),
            }
        )
        for record in records
    }


def save_rows(rows: Iterable[Row]) -> None:
    """Make the table hold exactly `rows`, in one transaction: every other group's row is deleted.

    A group listed twice keeps its last row.
    """
    from src.plugin_api import db

    by_group = {row.group_id: row for row in rows}
    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE}")
        cursor.executemany(
            f"INSERT INTO {TABLE} (group_id, capabilities, params, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            [
                (row.group_id, json.dumps(sorted(row.capabilities)), json.dumps(row.params_json()))
                for row in by_group.values()
            ],
        )


def delete_rows(group_ids: Iterable[str]) -> int:
    """Delete these groups' rows (they go back to their defaults); returns how many rows it deleted."""
    from src.plugin_api import db

    ids = sorted(set(group_ids))
    if not ids:
        return 0
    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE} WHERE group_id IN ({', '.join('?' * len(ids))})", ids)
        return cursor.rowcount


def _loads(text: Any) -> Any:
    """Parsed JSON, or None when `text` is not JSON."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _strings(value: Any, default: FrozenSet[str]) -> FrozenSet[str]:
    """A JSON list as a set of strings; anything else is `default`."""
    if not isinstance(value, list):
        return default
    return frozenset(str(item) for item in value)


def _size_gb(value: Any) -> Optional[float]:
    """A positive, finite number of GB; anything else means no limit."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None
