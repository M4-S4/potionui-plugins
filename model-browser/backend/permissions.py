"""Who may do what (PLAN.md §4): capabilities granted per user group, merged per user.

An admin (`account_type == ADMIN`) may do everything, with no parameter limiting them.
Anyone else gets the merge of their groups (`core_bridge.user_groups`), each group
contributing its row of `model_browser_group_permissions`, or its default without one
(`permissions_store.default_row`):
- a capability is granted when at least one group grants it;
- the download parameters come only from the groups that grant `download`: sources are
  united; model types too, but a group that lists none allows every type, so the merge
  then allows every type; the largest `max_file_gb` wins and no limit beats any limit;
  `assign_to` is "group" as soon as one group says so; `allow_remote` when one group allows it.

Rows of groups the core has deleted are never read here (a user's groups come from the
core); the `/permissions` routes delete them.

Routes hang on the `require_*` dependencies, or on `current_principal` for `GET /me`, and
receive a `Principal`.
"""

from dataclasses import dataclass
from typing import Callable, FrozenSet, Iterable, Optional

from fastapi import Depends, HTTPException

from src.plugin_api import AccountType, User, get_current_active_user

from . import core_bridge, permissions_store
from .permissions_store import (  # noqa: F401  (re-exported: the vocabulary is defined with the table)
    CAPABILITIES,
    DEFAULT_CAPABILITIES,
    DEFAULT_SOURCES,
    Row,
)


@dataclass(frozen=True)
class Grant:
    """The effective rights of one user, after merging their groups (PLAN.md §4.1, §4.2)."""

    capabilities: FrozenSet[str]
    #: Sources and PotionUI model types the user may download; ignored when `unrestricted`.
    #: Both are empty for a user without `download`.
    sources: FrozenSet[str]
    #: Empty means every type.
    model_types: FrozenSet[str]
    #: None means no size limit.
    max_file_gb: Optional[float]
    #: "user": the model is assigned to the requester; "group": they pick one of their groups.
    assign_to: str
    allow_remote: bool
    #: Admins: every capability, no parameter applies.
    unrestricted: bool

    def has(self, capability: str) -> bool:
        return self.unrestricted or capability in self.capabilities

    def allows_source(self, source: str) -> bool:
        """Whether the download parameters allow this source (the capability is checked apart)."""
        return self.unrestricted or source in self.sources

    def allows_type(self, model_type: str) -> bool:
        """Whether the download parameters allow this PotionUI model type; no type listed allows every type."""
        return self.unrestricted or not self.model_types or model_type in self.model_types


@dataclass(frozen=True)
class Principal:
    """The signed-in user and their grant, as the routes receive them."""

    user: User
    grant: Grant

    @property
    def is_admin(self) -> bool:
        return self.grant.unrestricted


ADMIN_GRANT = Grant(
    capabilities=frozenset(CAPABILITIES),
    sources=frozenset(),
    model_types=frozenset(),
    max_file_gb=None,
    assign_to="user",
    allow_remote=True,
    unrestricted=True,
)


def is_admin(user: User) -> bool:
    return user.account_type == AccountType.ADMIN


def merge_rows(rows: Iterable[Row]) -> Grant:
    """The grant of a non-admin whose groups have these rows (stored or default)."""
    rows = list(rows)
    downloading = [row for row in rows if "download" in row.capabilities]
    sizes = [row.max_file_gb for row in downloading]
    every_type = any(not row.model_types for row in downloading)
    return Grant(
        capabilities=frozenset().union(*(row.capabilities for row in rows)),
        sources=frozenset().union(*(row.sources for row in downloading)),
        model_types=frozenset() if every_type else frozenset().union(*(row.model_types for row in downloading)),
        max_file_gb=None if not sizes or None in sizes else max(sizes),
        assign_to="group" if any(row.assign_to == "group" for row in downloading) else "user",
        allow_remote=any(row.allow_remote for row in downloading),
        unrestricted=False,
    )


def resolve_grant(user: User) -> Grant:
    """The user's effective grant: everything for an admin, the merge of their groups otherwise."""
    if is_admin(user):
        return ADMIN_GRANT
    groups = core_bridge.user_groups(user.id)
    rows = permissions_store.load_rows()
    return merge_rows(permissions_store.row_or_default(rows, group["id"]) for group in groups)


def forbidden(capability: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"success": False, "error": "forbidden", "message": f"This action needs the '{capability}' permission"},
    )


def require(capability: str) -> Callable[..., Principal]:
    """A FastAPI dependency: the signed-in user must hold `capability`; yields their `Principal`.

    Use the module-level instances (`require_browse`, ...) in routes so tests can
    override one callable with `app.dependency_overrides`.
    """
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability {capability!r}")

    def dependency(user: User = Depends(get_current_active_user)) -> Principal:
        grant = resolve_grant(user)
        if not grant.has(capability):
            raise forbidden(capability)
        return Principal(user=user, grant=grant)

    dependency.__name__ = f"require_{capability}"
    return dependency


require_browse = require("browse")
require_request = require("request")
require_download = require("download")
require_approve = require("approve")


def current_principal(user: User = Depends(get_current_active_user)) -> Principal:
    """The signed-in user with their grant, no capability needed (for `GET /me`)."""
    return Principal(user=user, grant=resolve_grant(user))
