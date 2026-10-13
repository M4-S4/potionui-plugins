"""The plugin's single seam to PotionUI's operations (PLAN.md §3): the download queue, the
model catalog, user groups and the content policy, notifications and plan limits.

It only uses what `src.plugin_api` exports, never the core's internals: `.downloads`,
`.models` (lookups, assignment to a user, attributes, the provider fetch), `.groups`,
`.notifications` and `.limits`, all exported since PotionUI 0.0.16 (an older core fails at
import). The rest of the plugin calls the functions below for these operations, not the
exports, so the tests replace a function here (`tests/download_fakes.py::FakeCore`) and a
change of the exports is absorbed in one file. Other exports (users, storage, `LimitEvents`,
providers) are imported where they are used.

The functions take and return plain values (str, dict, list; `assign_to_group` also takes
the exported `User` it acts as), never a core record, so the rest of the plugin never depends
on one. The core's refusals come out as `CoreBridgeError(code, message)`.

The model lookups ask the core for its admin payload, the one that carries the hash and the
availability flag, and hand on only `MODEL_KEYS`: nothing else of that payload (location,
file size, copies, prompting guidance ...) leaves this module, so none of it can reach a user.

Plan limits are read here (`limit_status`); the events behind them are recorded and refunded
with `LimitEvents` (`backend/limits.py`).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, get_args

from src.plugin_api import (
    DownloadQueueException,
    InvalidModelMetadataException,
    ModelAssignmentException,
    ModelNotFoundException,
    UnsafeFilenameException,
    User,
)
from src.plugin_api import downloads as api_downloads
from src.plugin_api import groups as api_groups
from src.plugin_api import limits as api_limits
from src.plugin_api import models as api_models
from src.plugin_api import notifications as api_notifications

logger = logging.getLogger("plugins.model-browser")

#: The core's content policy modes, as `effective_policy()` returns them.
ContentPolicy = Literal["allowed", "blur", "blocked"]
CONTENT_POLICIES = get_args(ContentPolicy)

#: `source` of the notifications this plugin raises.
NOTIFICATION_SOURCE = "model-browser"

#: The keys of the model dicts the `find_model_by_*` functions return, and the only ones.
MODEL_KEYS = ("id", "sha256", "is_available", "created_at", "filename", "model_type")

#: The class name of what `resolve_model_file` raises for a model without a present file, or
#: one it does not know (`src/features/models/locator.py`); docs/plugin-api.md says to catch
#: it by name, since `src.plugin_api` does not export it.
_FILE_UNAVAILABLE = "ModelFileUnavailable"

#: Parts of the core's own `DownloadQueueException` messages that refuse a parameter
#: (`src/features/downloads/queue.py`): a sub-folder or destination outside the depot,
#: an unusable remote backend. Any other refusal is a `download.before_queue` hook's
#: `block_reason`, or a depot the core cannot write to.
_INVALID_QUEUE_MESSAGES = (
    "must be a relative path",
    "escapes the configured directory",
    "No backend configured with id",
    "is not a native.remote backend",
    "is not fully configured",
    "Remote destinations are not available",
)


class CoreBridgeError(Exception):
    """The core refused or failed an operation, for a reason the caller can act on.

    `code`:
    - "blocked": another plugin's hook refused it, or the core cannot do it now
      (download queue: `download.before_queue`, a depot it cannot write to);
    - "invalid": the core refused a parameter (unsafe file name, sub-folder, remote backend,
      a model attribute the core does not declare for the model's type);
    - "not_found": the model or the user group does not exist (any more);
    - "refused": the core declined an assignment (a hook, an unknown user, an acting user
      who is missing or not an admin).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Downloads ------------------------------------------------------------------


def _queue_refusal_code(message: str) -> str:
    return "invalid" if any(part in message for part in _INVALID_QUEUE_MESSAGES) else "blocked"


async def queue_model_download(
    url: str,
    *,
    filename: Optional[str] = None,
    model_type: Optional[str] = None,
    subdir: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    checksum_sha256: Optional[str] = None,
    provider_id: Optional[str] = None,
    created_by: Optional[str] = None,
    destination_backend_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue one model file on the core download queue; returns the queued download (`Download.to_dict()`).

    `model_type` picks the type's write folder, `subdir` a folder under it; `provider_id`
    ("civitai", "huggingface") makes the core add that provider's credentials;
    `checksum_sha256` makes the worker verify the file. Raises `CoreBridgeError`: "invalid"
    when the core refuses the file name, the sub-folder or the remote backend, "blocked" when
    a `download.before_queue` hook refuses the download (its `block_reason` is the message) or
    the depot cannot be written to.
    """
    try:
        return await api_downloads.queue_model_download(
            url,
            filename=filename,
            model_type=model_type,
            subdir=subdir,
            tags=list(tags) if tags is not None else None,
            checksum_sha256=checksum_sha256,
            provider_id=provider_id,
            created_by=created_by,
            destination_backend_id=destination_backend_id,
        )
    except UnsafeFilenameException as exc:
        raise CoreBridgeError("invalid", str(exc)) from exc
    except DownloadQueueException as exc:
        raise CoreBridgeError(_queue_refusal_code(str(exc)), str(exc)) from exc


def get_download(download_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """A queued download's current state (`Download.to_dict()`: status, progress, destination path,
    error message ...), or None once the core no longer has it."""
    if not download_id:
        return None
    return api_downloads.get_download(download_id)


# Models ---------------------------------------------------------------------


def _trimmed(model: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The `MODEL_KEYS` of a core model dict, or None."""
    if model is None:
        return None
    return {key: model.get(key) for key in MODEL_KEYS}


def find_model_by_sha256(sha256: str) -> Optional[Dict[str, Any]]:
    """The indexed model with this SHA256 (any case), as `MODEL_KEYS`, or None.

    No visibility filter: check `visible_model_ids()` before showing the model to a
    non-admin. A model whose file has gone has `is_available: False`.
    """
    if not sha256:
        return None
    return _trimmed(api_models.model_for_sha256(sha256, admin=True))


def find_model_by_path(path: str) -> Optional[Dict[str, Any]]:
    """The model indexed at this file path (a download's `destination_path`), as `MODEL_KEYS`, or None.

    A file the indexer refused as the duplicate of another model is not indexed at its own path.
    """
    if not path:
        return None
    return _trimmed(api_models.model_for_path(path, admin=True))


def find_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    """The catalog model `model_id`, as `MODEL_KEYS`, or None for a model the core does not
    know or whose file is not present on an online root.

    Resolves the model's file (`resolve_model_file`), then reads the model at that path.
    """
    if not model_id:
        return None
    try:
        path = api_models.resolve_model_file(model_id)
    except Exception as exc:
        if type(exc).__name__ != _FILE_UNAVAILABLE:
            raise
        return None
    return _trimmed(api_models.model_for_path(str(path), admin=True))


def visible_model_ids(user_id: str) -> List[str]:
    """Ids of the models `user_id` can see: assigned to them directly or through one of their groups."""
    return api_models.visible_model_ids(user_id)


def assign_to_user(model_id: str, user_id: str) -> bool:
    """Make a model visible to one user; True when newly assigned, False when it already was.

    The core fires `model_index.before_assign` / `model_index.after_assign`. Raises
    `CoreBridgeError("refused")` when a hook blocks it or the model or the user is unknown.
    """
    try:
        return api_models.assign_model_to_user(model_id, user_id)
    except ModelAssignmentException as exc:
        raise CoreBridgeError("refused", str(exc)) from exc


def assign_to_group(group_id: str, model_ids: Sequence[str], acting_user: User) -> List[str]:
    """Make models visible to every member of a group, in `acting_user`'s name; returns the ids newly assigned.

    Goes through the core's group operation, which requires an admin and fires
    `user_groups.before_assign_resource` (a hook may skip a model) and `after_assign_resource`
    with that admin's id; a model already in the group is skipped. Raises
    `CoreBridgeError("not_found")` when the group does not exist (checked first), and
    `CoreBridgeError("refused")` without an acting `User`, or when the core declines them
    (not an admin) or the group vanished in between. Without a model id, nothing is asked of
    the core.
    """
    if group_id not in {group["id"] for group in api_groups.list_groups()}:
        raise CoreBridgeError("not_found", f"There is no user group with the id '{group_id}'")
    if not isinstance(acting_user, User):
        raise CoreBridgeError("refused", f"Assigning models to the group '{group_id}' needs an acting admin")
    model_ids = [model_id for model_id in model_ids if model_id]
    if not model_ids:
        return []
    try:
        return api_groups.assign_models_to_group(group_id, model_ids, acting_user)
    except ValueError as exc:
        raise CoreBridgeError("refused", str(exc)) from exc


async def run_provider_fetch(provider: str, model_ids: Sequence[str]) -> Dict[str, Any]:
    """Fill models' description, trigger words, tags and previews from a provider; returns the core's
    summary, `{"successful": n, "failed": n, "errors"?: [{"model_id", "reason"}]}`.

    Only fields that are empty are filled. An empty `model_ids` fetches nothing. The core's
    `ProviderFetchException` (a provider it does not know or has not initialised, or a
    `model_index.before_fetch_info` veto) is not translated: it reaches the caller.
    """
    model_ids = [model_id for model_id in model_ids if model_id]
    if not model_ids:
        return {"successful": 0, "failed": 0}
    return await api_models.run_provider_fetch(provider, model_ids)


def write_attributes(model_id: str, values: Mapping[str, Any]) -> None:
    """Set some model attributes (`mb_base_model`, `mb_license`), keeping the model's other values.

    The core merges `values` into the model's current values and validates every key against
    the attribute definitions of the model's type. Raises `CoreBridgeError("invalid")` when the
    core refuses a key (an attribute it does not declare for this type, e.g. the plugin's
    definitions not registered yet), and `CoreBridgeError("not_found")` for an unknown model.
    """
    try:
        api_models.update_model_metadata(model_id, dict(values))
    except InvalidModelMetadataException as exc:
        logger.warning("[MODEL-BROWSER] The core refused the attributes of model %s: %s", model_id, exc)
        raise CoreBridgeError("invalid", str(exc)) from exc
    except ModelNotFoundException as exc:
        raise CoreBridgeError("not_found", str(exc)) from exc


# Users, groups and content policy ------------------------------------------


def effective_policy(user_id: str) -> ContentPolicy:
    """The content policy that applies to `user_id`: the instance setting, made stricter by their groups.

    A mode this plugin does not know counts as "blocked".
    """
    mode = api_groups.effective_content_policy(user_id)
    return mode if mode in CONTENT_POLICIES else "blocked"


def user_groups(user_id: str) -> List[Dict[str, Any]]:
    """The groups `user_id` belongs to, as `{"id", "name", "is_system", "content_policy"}` dicts."""
    return api_groups.get_user_groups(user_id)


def list_groups() -> List[Dict[str, Any]]:
    """Every user group, as `{"id", "name", "is_system", "content_policy"}` dicts, in the core's order (by name)."""
    return api_groups.list_groups()


def group_member_ids(group_id: str) -> List[str]:
    """Ids of the members of a user group, without duplicates; none for a group that does not exist."""
    return api_groups.group_member_ids(group_id)


# Notifications and plan limits ---------------------------------------------


def notify(
    *,
    user_id: str,
    notification_type: str,
    title: str,
    message: str = "",
    level: str = "info",
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    """Notify one user; `notification_type` is one the plugin registers ("model-browser.download_done", ...).

    Sent with `source="model-browser"` and `category="plugin"`; `level` is "info", "success",
    "warning" or "error". Never raises: a notification that cannot be sent is logged. Never
    broadcasts: without a `user_id` nothing is sent (the core would send it to everyone).
    """
    if not user_id:
        logger.warning("[MODEL-BROWSER] Not sending %r: no user to notify", notification_type)
        return
    try:
        api_notifications.notify(
            source=NOTIFICATION_SOURCE,
            title=title,
            message=message,
            user_id=user_id,
            type=notification_type,
            level=level,
            category="plugin",
            metadata=dict(metadata) if metadata else None,
        )
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not send the %r notification to %s", notification_type, user_id, exc_info=True)


def register_notification_types(registry: Any, types: Sequence[Any]) -> List[str]:
    """Declare notification types on the registry `notification_type.register` hands its
    handlers (`context.data["registry"]`); returns the keys it added.

    Each item has `key`, `label`, `description` and `category`, and becomes a
    `NotificationTypeSpec`, which shows it in every user's notification preferences. A key
    already registered is left as it is, so registering twice is harmless.
    """
    specs = [
        api_notifications.NotificationTypeSpec(
            key=item.key, label=item.label, description=item.description, category=item.category
        )
        for item in types
    ]
    return api_notifications.register_notification_types(registry, specs)


def _unlimited(kind: str) -> Dict[str, Any]:
    return {"kind": kind, "limit": None, "used": None, "exempt": False, "resets_at": None, "contact_line": ""}


def _utc_iso(moment: Optional[datetime]) -> Optional[str]:
    """`moment` as ISO 8601 in UTC."""
    return moment.astimezone(timezone.utc).isoformat() if moment is not None else None


def limit_status(user_id: str, kind: str) -> Dict[str, Any]:
    """Where `user_id` stands against the plan limit `kind` in its current window.

    Returns `{"kind", "limit", "used", "exempt", "resets_at", "contact_line"}`:
    - `limit` None: unlimited. The user has no plan, the plan that applies to them sets no
      limit for `kind`, or the kind is not registered (the plugin's `limit_kinds` did not load);
    - `exempt` True: an admin while the plan settings exempt admins (`limit` is kept, `used`
      is not measured);
    - otherwise `used` is the usage measured in the current window, `resets_at` the end of
      that window (ISO 8601 in UTC: the plans' day time zone is not exported), `contact_line`
      the admin's line for refusals.
    Never raises: when the plans cannot be read, the failure is logged and the answer is
    "unlimited", so a broken quota never blocks a download.
    """
    try:
        status = api_limits.limit_status(user_id, kind)
        return {
            "kind": status.kind,
            "limit": status.limit,
            "used": status.used,
            "exempt": status.exempt,
            "resets_at": _utc_iso(status.resets_at),
            "contact_line": status.contact_line,
        }
    except Exception:
        logger.warning(
            "[MODEL-BROWSER] Could not read the %s limit of user %s; treating it as unlimited", kind, user_id, exc_info=True
        )
        return _unlimited(kind)
