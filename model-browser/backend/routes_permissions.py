"""Routes about who may do what: `GET /me`, `GET/PUT /permissions` (PLAN.md §4, §7.3).

Included by `backend/api.py` under `/api/plugins/model-browser`.
- `GET /me`, for any signed-in user: their capabilities, download parameters and NSFW
  context. The page shows or hides its actions from it; every route still checks.
- `GET /permissions` (admin): one entry per core user group, with its stored row or its
  default, and the values each field accepts.
- `PUT /permissions` (admin): replaces the whole table; a group left out of the body
  goes back to its default. Answers like `GET`.
Both `/permissions` routes delete the rows of groups the core no longer has.

Answers are `{"success": true, "data": ...}`; errors raise an `HTTPException` whose
`detail` is `{"success": false, "error": "<code>", "message": ...}`.
"""

import logging
from typing import Annotated, Any, Callable, Dict, List, Literal, NoReturn, Optional, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from src.plugin_api import User, get_current_admin_user
from src.plugin_api.models import MODEL_TYPES

from . import core_bridge, nsfw, permissions_store
from .permissions import CAPABILITIES, Principal, current_principal
from .permissions_store import DEFAULT_SOURCES, SOURCE_IDS, Row
from .settings import CORE_USER_NSFW_SETTING

logger = logging.getLogger("plugins.model-browser")

router = APIRouter()


def _only(allowed: Sequence[str], what: str) -> Callable[[List[str]], List[str]]:
    """A validator that rejects any value outside `allowed`."""

    def check(values: List[str]) -> List[str]:
        unknown = sorted(set(values) - set(allowed))
        if unknown:
            raise ValueError(f"unknown {what}: {', '.join(unknown)}")
        return values

    return check


class ParamsUpdate(BaseModel):
    """A group's download parameters (`Row.params_json()`); a key left out takes its default."""

    model_config = ConfigDict(extra="forbid")

    sources: Annotated[List[str], AfterValidator(_only(SOURCE_IDS, "source"))] = Field(
        default_factory=lambda: sorted(DEFAULT_SOURCES)
    )
    #: Empty allows every type.
    model_types: Annotated[List[str], AfterValidator(_only(MODEL_TYPES, "model type"))] = Field(
        default_factory=list
    )
    #: None: no size limit.
    max_file_gb: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False, strict=True)
    assign_to: Literal["user", "group"] = "user"
    allow_remote: bool = Field(default=False, strict=True)


class GroupUpdate(BaseModel):
    """One group's rights. Other keys, such as `name` and `is_system` sent back from `GET`, are ignored."""

    group_id: str
    capabilities: Annotated[List[str], AfterValidator(_only(CAPABILITIES, "capability"))]
    params: ParamsUpdate = Field(default_factory=ParamsUpdate)


class PermissionsUpdate(BaseModel):
    groups: List[GroupUpdate]


@router.get("/me")
def get_me(principal: Principal = Depends(current_principal)) -> Dict[str, Any]:
    """What the signed-in user may do, with which download parameters, and how NSFW media is shown to them."""
    user, grant = principal.user, principal.grant
    context = nsfw.resolve_nsfw(user)
    return _ok(
        {
            "user": {"id": user.id, "username": user.username, "is_admin": principal.is_admin},
            "capabilities": sorted(grant.capabilities),
            "params": {
                "sources": sorted(grant.sources),
                "model_types": sorted(grant.model_types),
                "max_file_gb": grant.max_file_gb,
                "assign_to": grant.assign_to,
                "allow_remote": grant.allow_remote,
                "unrestricted": grant.unrestricted,
            },
            "nsfw": {
                "ceiling": context.ceiling,
                "mode": context.mode,
                "allowed_modes": list(context.allowed_modes),
                "max_level": context.max_level,
                "hide_poi": context.hide_poi,
                "setting_key": CORE_USER_NSFW_SETTING,
            },
        }
    )


@router.get("/permissions")
def get_permissions(admin: User = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Every core user group with its rights (stored row or default), and the values each field accepts."""
    return _ok(_permissions(core_bridge.list_groups()))


@router.put("/permissions")
def put_permissions(
    body: Dict[str, Any] = Body(...),
    admin: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Replace every group's rights with `body["groups"]`; a group left out goes back to its default."""
    try:
        update = PermissionsUpdate.model_validate(body)
    except ValidationError as error:
        _fail(400, "invalid_request", _describe(error))

    groups = core_bridge.list_groups()
    known = {group["id"] for group in groups}
    rows: Dict[str, Row] = {}
    for entry in update.groups:
        if entry.group_id not in known:
            _fail(400, "unknown_group", f"There is no user group with the id '{entry.group_id}'")
        if entry.group_id in rows:
            _fail(400, "invalid_request", f"The user group '{entry.group_id}' is listed more than once")
        rows[entry.group_id] = Row.from_json(entry.model_dump())

    permissions_store.save_rows(rows.values())
    logger.info(
        "[MODEL-BROWSER] %s saved the permissions of %d user group(s); the other groups use their defaults",
        admin.username,
        len(rows),
    )
    return _ok(_permissions(groups))


def _permissions(groups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The `/permissions` payload for these core groups; deletes the rows of groups that are not among them."""
    rows = permissions_store.load_rows()
    gone = set(rows) - {group["id"] for group in groups}
    if gone:
        permissions_store.delete_rows(gone)
        logger.info(
            "[MODEL-BROWSER] Deleted the permissions of user groups that no longer exist: %s",
            ", ".join(sorted(gone)),
        )
    return {
        "capabilities": list(CAPABILITIES),
        "sources": list(SOURCE_IDS),
        "model_types": list(MODEL_TYPES),
        "groups": [_group_entry(group, permissions_store.row_or_default(rows, group["id"])) for group in groups],
    }


def _group_entry(group: Dict[str, Any], row: Row) -> Dict[str, Any]:
    return {
        "group_id": group["id"],
        "name": group["name"],
        "is_system": group["is_system"],
        "capabilities": sorted(row.capabilities),
        "params": row.params_json(),
    }


def _ok(data: Any) -> Dict[str, Any]:
    return {"success": True, "data": data}


def _fail(status_code: int, error: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"success": False, "error": error, "message": message})


def _describe(error: ValidationError) -> str:
    """A validation error on one line: `groups.0.capabilities: Value error, unknown capability: manage; ...`."""
    problems = []
    for item in error.errors(include_url=False):
        where = ".".join(str(part) for part in item["loc"])
        problems.append(f"{where}: {item['msg']}" if where else item["msg"])
    return "Invalid permissions: " + "; ".join(problems)
