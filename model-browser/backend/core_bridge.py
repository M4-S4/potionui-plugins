"""The one module of this plugin that reaches into PotionUI's internals (PLAN.md §3).

`src.plugin_api` exports `get_container()` but not the managers this plugin
drives: the download queue, model assignment, the provider fetch, the content
policy, user groups, notifications and plan limits. Until the phase 8 PR exports
them, every `AppContainer` attribute the plugin uses is read here and nowhere
else, so a core refactor breaks one file, and `check_container()` and
tests/test_core_bridge.py name the attribute that moved.

The functions take and return plain values (str, dict, list), never a core class,
so the rest of the plugin never depends on one. Each reaches the container through
`_container_attribute`, which names the attribute when the core moved it: a moved
attribute only breaks the features that use it.

This is also the only module allowed to import the core's internal exception
classes and operation modules (`src.features...`): each such import sits inside the
function that needs it, with a comment naming the core file. The core's refusals
come out as `CoreBridgeError(code, message)`.

`limit_status` stays a stub until phase 5 (plan limits).
"""

import logging
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, get_args

from src.plugin_api import User, get_container, model_for_path

logger = logging.getLogger("plugins.model-browser")

#: Every container attribute this module relies on, as a dotted path from the
#: `AppContainer` (`src/bootstrap/container.py`), down to the method called.
REQUIRED_ATTRIBUTES = (
    "download_queue.queue_model_download",
    "download_queue.get_download",
    "content_policy_resolver.resolve",
    "user_group_repository.get_user_groups",
    "user_group_repository.get_all_groups",
    "user_group_repository.get_group_by_id",
    "user_group_repository.assign_model_to_group",
    "model_repository.get_by_sha256",
    "model_repository.get_by_id",
    "model_repository.get_available_model_ids_for_user",
    "model_index_manager.assignments.assign_model_to_user",
    "model_index_manager.provider_info.run_provider_fetch",
    "model_index_manager.metadata.update_model_metadata",
    "plugin_registry",
    "notification_manager",
    # Phase 5 (plan limits, `limit_status`).
    "plans.guard",
    "plans.events",
)

#: The core's content policy modes, as `effective_policy()` returns them.
ContentPolicy = Literal["allowed", "blur", "blocked"]
CONTENT_POLICIES = get_args(ContentPolicy)

#: `source` of the notifications this plugin raises.
NOTIFICATION_SOURCE = "model-browser"

_PHASE_5 = "model-browser: implemented in phase 5"

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
    - "refused": the core declined an assignment (a hook, an unknown user).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _walk(node: Any, path: str) -> Any:
    """The object at dotted `path` from `node`, or None when a segment is absent or None."""
    for name in path.split("."):
        node = getattr(node, name, None)
        if node is None:
            return None
    return node


def _moved(paths: Sequence[str]) -> RuntimeError:
    return RuntimeError(
        "model-browser: PotionUI's AppContainer no longer provides "
        + ", ".join(paths)
        + ". The core renamed or removed attributes this plugin relies on: update "
        "REQUIRED_ATTRIBUTES and the functions that use them in backend/core_bridge.py."
    )


def missing_attributes(container: Any) -> List[str]:
    """The `REQUIRED_ATTRIBUTES` paths `container` does not provide, in declaration order.

    Works on any object, so tests can pass a stand-in. A path is missing when one
    of its segments is absent or None, and is reported in full: with `plans` gone,
    both "plans.guard" and "plans.events" are listed.
    """
    return [path for path in REQUIRED_ATTRIBUTES if _walk(container, path) is None]


def check_container() -> Any:
    """The live `AppContainer`, once checked against `REQUIRED_ATTRIBUTES`.

    Raises RuntimeError naming every missing path when the core renamed or removed
    an attribute this plugin relies on (and, before the application is composed,
    the RuntimeError of `get_container()` itself).
    """
    container = get_container()
    missing = missing_attributes(container)
    if missing:
        raise _moved(missing)
    return container


def _container_attribute(path: str) -> Any:
    """The object at `path`, one of `REQUIRED_ATTRIBUTES`, on the live container.

    Raises RuntimeError naming `path` when the core renamed or removed it (and,
    before the application is composed, the RuntimeError of `get_container()`).
    """
    if path not in REQUIRED_ATTRIBUTES:
        raise ValueError(f"{path!r} is missing from REQUIRED_ATTRIBUTES")
    node = _walk(get_container(), path)
    if node is None:
        raise _moved([path])
    return node


def _container_owner(path: str) -> Any:
    """The object holding the last segment of `path` (a repository, for a method path), checked like `_container_attribute`."""
    _container_attribute(path)
    return _walk(get_container(), path.rsplit(".", 1)[0])


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

    Uses `download_queue.queue_model_download(...)` (async). `model_type` picks the
    type's write folder, `subdir` a folder under it; `provider_id` ("civitai",
    "huggingface") makes the core add that provider's credentials; `checksum_sha256`
    makes the worker verify the file. Raises `CoreBridgeError`: "invalid" when the core
    refuses the file name, the sub-folder or the remote backend, "blocked" when a
    `download.before_queue` hook refuses the download (its `block_reason` is the
    message) or the depot cannot be written to.
    """
    # Internal exceptions, src/features/downloads/exceptions.py (`UnsafeFilenameException`
    # is a `DownloadQueueException`).
    from src.features.downloads.exceptions import DownloadQueueException, UnsafeFilenameException

    queue = _container_attribute("download_queue.queue_model_download")
    try:
        download = await queue(
            url,
            filename=filename,
            tags=list(tags) if tags is not None else None,
            checksum_sha256=checksum_sha256,
            provider_id=provider_id,
            created_by=created_by,
            model_type=model_type,
            subdir=subdir,
            destination_backend_id=destination_backend_id,
        )
    except UnsafeFilenameException as exc:
        raise CoreBridgeError("invalid", str(exc)) from exc
    except DownloadQueueException as exc:
        raise CoreBridgeError(_queue_refusal_code(str(exc)), str(exc)) from exc
    return download.to_dict()


def get_download(download_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """A queued download's current state (`Download.to_dict()`: status, progress, destination path,
    error message ...), or None once the core no longer has it.

    Uses `download_queue.get_download(download_id)`, which raises for an unknown id.
    """
    # Internal exception, src/features/downloads/exceptions.py.
    from src.features.downloads.exceptions import DownloadNotFoundException

    if not download_id:
        return None
    try:
        download = _container_attribute("download_queue.get_download")(download_id)
    except DownloadNotFoundException:
        return None
    return download.to_dict()


# Models ---------------------------------------------------------------------


def _model_dict(model: Any) -> Dict[str, Any]:
    """A core `Model` as the plain dict `model_for_path` also returns (`id`, `sha256`,
    `model_type`, `filename`, `model_metadata`, `is_available` ...)."""
    return model.to_dict(include_providers=False, include_tags=False)


def find_model_by_sha256(sha256: str) -> Optional[Dict[str, Any]]:
    """The indexed model with this SHA256 (any case), or None.

    Uses `model_repository.get_by_sha256(sha256)`. No visibility filter: check
    `visible_model_ids()` before showing the model to a non-admin. A model whose file
    has gone has `is_available: False`.
    """
    if not sha256:
        return None
    model = _container_attribute("model_repository.get_by_sha256")(sha256.strip().lower(), include_providers=False)
    return _model_dict(model) if model is not None else None


def find_model_by_path(path: str) -> Optional[Dict[str, Any]]:
    """The model indexed at this file path (a download's `destination_path`), or None.

    Uses `model_for_path`, exported by `src.plugin_api`: the same dict as
    `find_model_by_sha256`. A file the indexer refused as the duplicate of another
    model is not indexed at its own path.
    """
    if not path:
        return None
    return model_for_path(path)


def visible_model_ids(user_id: str) -> List[str]:
    """Ids of the models `user_id` can see: assigned to them directly or through one of their groups.

    Uses `model_repository.get_available_model_ids_for_user(user_id)`.
    """
    return list(_container_attribute("model_repository.get_available_model_ids_for_user")(user_id))


def assign_to_user(model_id: str, user_id: str) -> bool:
    """Make a model visible to one user; True when newly assigned, False when it already was.

    Uses `model_index_manager.assignments.assign_model_to_user(model_id, user_id)`, which
    fires `model_index.before_assign` / `model_index.after_assign`. Raises
    `CoreBridgeError("refused")` when a hook blocks it or the model or the user is unknown.
    """
    # Internal exceptions, src/features/models/exceptions.py.
    from src.features.models.exceptions import ModelAlreadyAssignedException, ModelAssignmentException

    assign = _container_attribute("model_index_manager.assignments.assign_model_to_user")
    try:
        assign(model_id, user_id)
    except ModelAlreadyAssignedException:
        return False
    except ModelAssignmentException as exc:
        raise CoreBridgeError("refused", str(exc)) from exc
    return True


def assign_to_group(group_id: str, model_ids: Sequence[str], acting_admin: Optional[User] = None) -> List[str]:
    """Make models visible to every member of a group; returns the ids newly assigned.

    Two paths, which differ in the hooks they fire:
    - with `acting_admin` (an admin `User` acting through the plugin, e.g. approving a
      request): the core's own group operation,
      `user_groups/operations/resources.py::assign_models(repository, plugin_registry,
      group_id, model_ids, acting_admin)`, which fires `user_groups.before_assign_resource`
      (a hook may skip a model) and `after_assign_resource` with that admin's id;
    - without (the plugin's own automated assignment, from the download watcher):
      `user_group_repository.assign_model_to_group(group_id, model_id)` for each id,
      which fires no hook, since there is no admin to name.
    A model already in the group is skipped on both paths. Raises
    `CoreBridgeError("not_found")` when the group does not exist,
    `CoreBridgeError("refused")` when the core declines `acting_admin`.
    """
    if _container_attribute("user_group_repository.get_group_by_id")(group_id) is None:
        raise CoreBridgeError("not_found", f"There is no user group with the id '{group_id}'")
    model_ids = [model_id for model_id in model_ids if model_id]
    if not model_ids:
        return []
    if acting_admin is not None:
        # Internal operation module, src/features/user_groups/operations/resources.py.
        from src.features.user_groups.operations.resources import assign_models

        repository = _container_owner("user_group_repository.assign_model_to_group")
        try:
            assigned = assign_models(
                repository, _container_attribute("plugin_registry"), group_id, list(model_ids), acting_admin
            )
        except ValueError as exc:  # not an admin, or the group vanished in between
            raise CoreBridgeError("refused", str(exc)) from exc
        return [assignment.model_id for assignment in assigned]
    assign = _container_attribute("user_group_repository.assign_model_to_group")
    # None: already in the group, or a model id the core does not know.
    return [model_id for model_id in model_ids if assign(group_id, model_id) is not None]


async def run_provider_fetch(provider: str, model_ids: Sequence[str]) -> Dict[str, Any]:
    """Fill models' description, trigger words, tags and previews from a provider; returns the core's
    summary, `{"successful": n, "failed": n, "errors"?: [{"model_id", "reason"}]}`.

    Uses `model_index_manager.provider_info.run_provider_fetch(provider, model_ids)` (async),
    which never raises and only fills fields that are empty. An empty `model_ids` fetches
    nothing (the core would read it as "every model without provider info").
    """
    model_ids = [model_id for model_id in model_ids if model_id]
    if not model_ids:
        return {"successful": 0, "failed": 0}
    fetch = _container_attribute("model_index_manager.provider_info.run_provider_fetch")
    summary = await fetch(provider, model_ids=model_ids)
    return dict(summary) if isinstance(summary, Mapping) else {"successful": 0, "failed": len(model_ids)}


def read_attributes(model_id: str) -> Dict[str, Any]:
    """A model's shared attribute values (`model_metadata`); `CoreBridgeError("not_found")` for an unknown model.

    Uses `model_repository.get_by_id(model_id)`.
    """
    model = _container_attribute("model_repository.get_by_id")(model_id, include_providers=False, include_tags=False)
    if model is None:
        raise CoreBridgeError("not_found", f"No model with id '{model_id}'")
    return dict(model.model_metadata or {})


def write_attributes(model_id: str, values: Mapping[str, Any]) -> None:
    """Set some model attributes (`mb_base_model`, `mb_license`), keeping the model's other values.

    Uses `model_index_manager.metadata.update_model_metadata(model_id, values)`, which
    replaces the whole map and validates every key against the attribute definitions of
    the model's type: the current values are merged first. Raises
    `CoreBridgeError("invalid")` when the core refuses a key (an attribute it does not
    declare for this type, e.g. the plugin's definitions not registered yet), and
    `CoreBridgeError("not_found")` for an unknown model.
    """
    # Internal exceptions, src/features/models/exceptions.py.
    from src.features.models.exceptions import InvalidModelMetadataException, ModelNotFoundException

    current = read_attributes(model_id)
    merged = {**current, **dict(values)}
    if merged == current:
        return
    update = _container_attribute("model_index_manager.metadata.update_model_metadata")
    try:
        update(model_id, merged)
    except InvalidModelMetadataException as exc:
        logger.warning("[MODEL-BROWSER] The core refused the attributes of model %s: %s", model_id, exc)
        raise CoreBridgeError("invalid", str(exc)) from exc
    except ModelNotFoundException as exc:
        raise CoreBridgeError("not_found", str(exc)) from exc


# Users, groups and content policy ------------------------------------------


def effective_policy(user_id: str) -> ContentPolicy:
    """The content policy that applies to `user_id`: the instance setting, made stricter by their groups.

    Uses `content_policy_resolver.resolve(user_id).mode`; a mode this plugin does not
    know counts as "blocked".
    """
    policy = _container_attribute("content_policy_resolver.resolve")(user_id)
    mode = getattr(policy, "mode", None)
    return mode if mode in CONTENT_POLICIES else "blocked"


def user_groups(user_id: str) -> List[Dict[str, Any]]:
    """The groups `user_id` belongs to, as `{"id", "name", "is_system", "content_policy"}` dicts.

    Uses `user_group_repository.get_user_groups(user_id)`.
    """
    return [_group(group) for group in _container_attribute("user_group_repository.get_user_groups")(user_id)]


def list_groups() -> List[Dict[str, Any]]:
    """Every user group, as `{"id", "name", "is_system", "content_policy"}` dicts, in the core's order (by name).

    Uses `user_group_repository.get_all_groups()`.
    """
    return [_group(group) for group in _container_attribute("user_group_repository.get_all_groups")()]


def _group(group: Any) -> Dict[str, Any]:
    """A core `UserGroup` record as a plain dict."""
    return {
        "id": group.id,
        "name": group.name,
        "is_system": bool(getattr(group, "is_system", False)),
        "content_policy": getattr(group, "content_policy", None),
    }


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

    Uses `notification_manager(...)`, the core's `notify` already bound to its
    collaborators, with `source="model-browser"` and `category="plugin"`; `level` is
    "info", "success", "warning" or "error". Never raises: a notification that cannot be
    sent is logged. Never broadcasts: without a `user_id` nothing is sent.
    """
    if not user_id:
        logger.warning("[MODEL-BROWSER] Not sending %r: no user to notify", notification_type)
        return
    try:
        _container_attribute("notification_manager")(
            level=level,
            title=title,
            message=message,
            category="plugin",
            user_id=user_id,
            source=NOTIFICATION_SOURCE,
            metadata=dict(metadata) if metadata else None,
            type=notification_type,
        )
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not send the %r notification to %s", notification_type, user_id, exc_info=True)


def limit_status(user_id: str, kind: str) -> Dict[str, Any]:
    """Where `user_id` stands against the plan limit `kind`: exempt or not, the limit, the usage so far.

    Will use `plans.guard` (`resolution(user_id)`, `is_exempt(subject, settings)`,
    `measure(kind: LimitKind, user_id, tz_name)`) and `plans.events`, the ledger behind
    `LimitEvents`.
    """
    raise NotImplementedError(_PHASE_5)
