"""Who may do what (PLAN.md §4): capabilities granted per user group, merged per user.

An admin (`account_type == ADMIN`) may do everything, with no parameter limiting them.
Anyone else gets the merge of their groups (`core_bridge.user_groups`), each group
contributing its row of `model_browser_group_permissions`, or its default without one
(`permissions_store.default_row`). A row holds one parameter set; it is merged per
capability, into two views of the grant:
- a capability is granted when at least one group grants it;
- the download view (`Grant.sources`, `model_types`, `max_file_gb`, `assign_to`,
  `allow_remote`, also `Grant.download_params`) binds direct downloads and comes only from
  the groups that grant `download`;
- the request view (`Grant.request_params`) binds requests, when they are made and again,
  for the requester, when they are approved; it comes only from the groups that grant
  `request`, and has no `allow_remote` (a request names no destination).
In each view, sources are united; model types too, but a group that lists none allows every
type, so the merge then allows every type; the largest `max_file_gb` wins and no limit
beats any limit; `assign_to` is "group" as soon as one group says so; `allow_remote` (downloads
only) when one group allows it. A user without `download` thus has an empty download view,
one without `request` an empty request view; the default `all_users` row (`browse` +
`request`) gives wide request parameters and leaves every download view as it is. Approval
is the control for requests.

Rows of groups the core has deleted are never read here (a user's groups come from the
core); the `/permissions` routes delete them.

Routes hang on the `require_*` dependencies, or on `current_principal` for `GET /me`, and
receive a `Principal`. `approver_ids` lists who holds `approve` (the recipients of a new
request's notification), `principal_for` builds the principal of a user who is not the
caller (the requester, when an approver acts on their request), and `acting_admin` names
the admin in whose name a model is assigned to a group, since the core's group operation
needs one: the requester or the request's decider when they are admins, else the admin who
last saved the group's permissions.
"""

import logging
from dataclasses import dataclass
from typing import Callable, FrozenSet, Iterable, Optional, Set

from fastapi import Depends, HTTPException

from src.plugin_api import AccountType, User, get_current_active_user, get_user, list_user_ids

from . import core_bridge, permissions_store
from .permissions_store import (  # noqa: F401  (re-exported: the vocabulary is defined with the table)
    CAPABILITIES,
    DEFAULT_CAPABILITIES,
    DEFAULT_SOURCES,
    Row,
)

logger = logging.getLogger("plugins.model-browser")

#: What a grant's parameters are checked for, each named after the capability whose groups
#: give them: a direct download, or a request.
PURPOSES = ("download", "request")


@dataclass(frozen=True)
class Params:
    """The parameters of one view of a grant (downloads or requests), merged over the
    user's groups that grant that capability. Empty for a user without it."""

    #: Sources the user may download (request) from.
    sources: FrozenSet[str] = frozenset()
    #: PotionUI model types; empty means every type.
    model_types: FrozenSet[str] = frozenset()
    #: Largest file in GB; None means no size limit.
    max_file_gb: Optional[float] = None
    #: "user": the model is assigned to the user; "group": to one of their groups, picked.
    assign_to: str = "user"
    #: Downloads only: whether a remote backend may be the destination. Always False for requests.
    allow_remote: bool = False

    def __post_init__(self) -> None:
        for name in ("sources", "model_types"):
            object.__setattr__(self, name, frozenset(getattr(self, name)))


#: An empty view: no source, so nothing may be downloaded or requested.
NO_PARAMS = Params()


@dataclass(frozen=True)
class Grant:
    """The effective rights of one user, after merging their groups (PLAN.md §4.1, §4.2).

    The download view is kept in the grant's own fields (`sources` ... `allow_remote`);
    `request_params` is the request view. `params(purpose)` gives either as `Params`, and the
    `allows_*` helpers check either, the download view by default.
    """

    capabilities: FrozenSet[str]
    #: Sources and PotionUI model types the user may download; ignored when `unrestricted`.
    #: Both are empty for a user without `download`.
    sources: FrozenSet[str]
    #: Empty means every type.
    model_types: FrozenSet[str]
    #: None means no size limit.
    max_file_gb: Optional[float]
    #: "user": the model is assigned to the downloader; "group": they pick one of their groups.
    assign_to: str
    allow_remote: bool
    #: Admins: every capability, no parameter applies (in either view).
    unrestricted: bool
    #: The request view, from the groups that grant `request`; `NO_PARAMS` without `request`.
    request_params: Params = NO_PARAMS

    @property
    def download_params(self) -> Params:
        """The download view as `Params`."""
        return Params(
            sources=self.sources,
            model_types=self.model_types,
            max_file_gb=self.max_file_gb,
            assign_to=self.assign_to,
            allow_remote=self.allow_remote,
        )

    def params(self, purpose: str = "download") -> Params:
        """The view that binds `purpose`: "download" or "request"."""
        if purpose == "download":
            return self.download_params
        if purpose == "request":
            return self.request_params
        raise ValueError(f"unknown purpose {purpose!r}")

    def has(self, capability: str) -> bool:
        return self.unrestricted or capability in self.capabilities

    def allows_source(self, source: str, purpose: str = "download") -> bool:
        """Whether the view of `purpose` allows this source (the capability is checked apart)."""
        return self.unrestricted or source in self.params(purpose).sources

    def allows_type(self, model_type: str, purpose: str = "download") -> bool:
        """Whether the view of `purpose` allows this PotionUI model type; no type listed allows every type."""
        if self.unrestricted:
            return True
        model_types = self.params(purpose).model_types
        return not model_types or model_type in model_types


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


def merge_params(rows: Iterable[Row], *, remote: bool = True) -> Params:
    """One view: the parameters of these rows merged (see the module docstring).

    `remote=False` (requests) leaves `allow_remote` False whatever the rows say.
    """
    rows = list(rows)
    sizes = [row.max_file_gb for row in rows]
    every_type = any(not row.model_types for row in rows)
    return Params(
        sources=frozenset().union(*(row.sources for row in rows)),
        model_types=frozenset() if every_type else frozenset().union(*(row.model_types for row in rows)),
        max_file_gb=None if not sizes or None in sizes else max(sizes),
        assign_to="group" if any(row.assign_to == "group" for row in rows) else "user",
        allow_remote=remote and any(row.allow_remote for row in rows),
    )


def merge_rows(rows: Iterable[Row]) -> Grant:
    """The grant of a non-admin whose groups have these rows (stored or default).

    The download view comes from the rows that grant `download`, the request view from the
    rows that grant `request`.
    """
    rows = list(rows)
    downloads = merge_params(row for row in rows if "download" in row.capabilities)
    requests = merge_params((row for row in rows if "request" in row.capabilities), remote=False)
    return Grant(
        capabilities=frozenset().union(*(row.capabilities for row in rows)),
        sources=downloads.sources,
        model_types=downloads.model_types,
        max_file_gb=downloads.max_file_gb,
        assign_to=downloads.assign_to,
        allow_remote=downloads.allow_remote,
        unrestricted=False,
        request_params=requests,
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


def require_any(*capabilities: str) -> Callable[..., Principal]:
    """A FastAPI dependency: the signed-in user must hold at least one of `capabilities`; yields their `Principal`.

    Like `require`, bind it once at module level in the routes so tests can override it.
    """
    if not capabilities:
        raise ValueError("require_any needs at least one capability")
    unknown = [capability for capability in capabilities if capability not in CAPABILITIES]
    if unknown:
        raise ValueError(f"unknown capabilities {unknown!r}")

    def dependency(user: User = Depends(get_current_active_user)) -> Principal:
        grant = resolve_grant(user)
        if not any(grant.has(capability) for capability in capabilities):
            names = ", ".join(f"'{capability}'" for capability in capabilities)
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "forbidden",
                    "message": f"This action needs one of these permissions: {names}",
                },
            )
        return Principal(user=user, grant=grant)

    dependency.__name__ = "require_any_" + "_".join(capabilities)
    return dependency


require_browse = require("browse")
require_request = require("request")
require_download = require("download")
require_approve = require("approve")


def current_principal(user: User = Depends(get_current_active_user)) -> Principal:
    """The signed-in user with their grant, no capability needed (for `GET /me`)."""
    return Principal(user=user, grant=resolve_grant(user))


def principal_for(user: User) -> Principal:
    """`user` with their grant: the principal of someone who is not the caller (a requester)."""
    return Principal(user=user, grant=resolve_grant(user))


def can_approve(principal: Principal) -> bool:
    """Whether `principal` may approve or decline requests (an admin, or a holder of `approve`)."""
    return principal.grant.has("approve")


def user_by_id(user_id: Optional[str]) -> Optional[User]:
    """The user with this id, or None when there is none or the core cannot tell. Never raises."""
    if not user_id:
        return None
    try:
        return get_user(user_id)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not look user %s up", user_id, exc_info=True)
        return None


def admin_by_id(user_id: Optional[str]) -> Optional[User]:
    """The user with this id when they are an admin (an acting admin for the core's group
    operations), else None. Never raises."""
    user = user_by_id(user_id)
    return user if user is not None and is_admin(user) else None


def acting_admin(requested_by: Optional[str], decided_by: Optional[str], group_id: str) -> Optional[User]:
    """The admin in whose name a model is assigned to the group `group_id`: the requester when
    they are an admin, else the decider when they are one, else the admin who last saved that
    group's stored permission row (`Row.updated_by`; nobody for a group on its default row),
    else None. Never raises.
    """
    for user_id in (requested_by, decided_by):
        admin = admin_by_id(user_id)
        if admin is not None:
            return admin
    try:
        row = permissions_store.load_rows().get(group_id)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not read the permissions of user group %s", group_id, exc_info=True)
        return None
    return admin_by_id(row.updated_by) if row is not None else None


def approver_ids() -> Set[str]:
    """Ids of every user who holds `approve`: every admin, and every member of a group whose
    row (stored or default) grants it.

    Admins are found with `list_user_ids` and `get_user`, group members with
    `core_bridge.group_member_ids`.
    """
    rows = permissions_store.load_rows()
    ids: Set[str] = set()
    for group in core_bridge.list_groups():
        if "approve" in permissions_store.row_or_default(rows, group["id"]).capabilities:
            ids.update(core_bridge.group_member_ids(group["id"]))
    for user_id in list_user_ids():
        if user_id in ids:
            continue
        user = user_by_id(user_id)
        if user is not None and is_admin(user):
            ids.add(user_id)
    return ids
