"""The one module of this plugin that reaches into PotionUI's internals (PLAN.md §3).

`src.plugin_api` exports `get_container()` but not the managers this plugin
drives: the download queue, model assignment, the provider fetch, the content
policy, user groups, notifications and plan limits. Until the phase 8 PR exports
them, every `AppContainer` attribute the plugin uses is read here and nowhere
else, so a core refactor breaks one file, and `check_container()` and
tests/test_core_bridge.py name the attribute that moved.

Phase 1 implements the content policy and the user groups; the other functions
are typed stubs that phase 3 implements. The functions take and return plain
values (str, dict, list), never a core class, so the rest of the plugin never
depends on one. Each reaches the container through `_container_attribute`, which
names the attribute when the core moved it: a moved attribute only breaks the
features that use it.
"""

from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, get_args

from src.plugin_api import User, get_container

#: Every container attribute this module relies on, as a dotted path from the
#: `AppContainer` (`src/bootstrap/container.py`). The implemented functions list
#: the methods they call; phase 3 narrows the other entries the same way.
REQUIRED_ATTRIBUTES = (
    "download_queue",
    "download_repository",
    "content_policy_resolver.resolve",
    "user_group_repository.get_user_groups",
    "user_group_repository.get_all_groups",
    "model_repository.get_available_model_ids_for_user",
    "model_index_manager.assignments.assign_model_to_user",
    "model_index_manager.provider_info.run_provider_fetch",
    "model_index_manager.access",
    "model_index_manager.metadata",
    "plans.guard",
    "plans.events",
    "notification_manager",
    "notification_repository",
    "user_repository",
)

#: The core's content policy modes, as `effective_policy()` returns them.
ContentPolicy = Literal["allowed", "blur", "blocked"]
CONTENT_POLICIES = get_args(ContentPolicy)

_PHASE_3 = "model-browser: implemented in phase 3"


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


# Downloads ------------------------------------------------------------------


async def queue_model_download(
    url: str,
    *,
    destination_dir: Optional[str] = None,
    filename: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
    checksum_sha256: Optional[str] = None,
    provider_id: Optional[str] = None,
    created_by: Optional[str] = None,
    model_type: Optional[str] = None,
    subdir: Optional[str] = None,
    destination_backend_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queue one model file on the core download queue; returns the queued download.

    Will use `download_queue.queue_model_download(...)` (async). It fires
    `download.before_queue`, where another plugin can block the download with a
    `block_reason`; `provider_id` ("civitai", "huggingface") makes the core add
    that provider's credentials.
    """
    raise NotImplementedError(_PHASE_3)


def get_download(download_id: str) -> Optional[Dict[str, Any]]:
    """A queued download's current state (status, destination path, error), or None once the core has dropped it.

    Will use `download_queue.get_download(download_id)`, which raises for an unknown
    id; `download_repository` stores the same rows.
    """
    raise NotImplementedError(_PHASE_3)


# Models ---------------------------------------------------------------------


def find_model_by_sha256(sha256: str) -> Optional[Dict[str, Any]]:
    """The indexed model with this SHA256, or None.

    Will use `model_repository.get_by_sha256(sha256)`. No visibility filter: check
    `visible_model_ids()` before showing the model to a non-admin.
    """
    raise NotImplementedError(_PHASE_3)


def visible_model_ids(user_id: str) -> List[str]:
    """Ids of the models `user_id` can see: assigned to them directly or through one of their groups.

    Will use `model_repository.get_available_model_ids_for_user(user_id)`.
    """
    raise NotImplementedError(_PHASE_3)


def assign_to_user(model_id: str, user_id: str) -> None:
    """Make a model visible to one user.

    Will use `model_index_manager.assignments.assign_model_to_user(model_id, user_id)`,
    which fires `model_index.before_assign` / `model_index.after_assign`.
    """
    raise NotImplementedError(_PHASE_3)


def assign_to_group(group_id: str, model_ids: Sequence[str], acting_admin: User) -> List[str]:
    """Make models visible to every member of a group; returns the ids newly assigned.

    Will use `user_group_repository.assign_model_to_group(group_id, model_id)`. The
    core's own group assignment is done as an admin and fires the user-group
    assignment hooks: `acting_admin` is that admin.
    """
    raise NotImplementedError(_PHASE_3)


async def run_provider_fetch(provider: str, model_ids: Sequence[str]) -> Dict[str, Any]:
    """Fill models' description, trigger words and previews from a provider; returns the core's summary.

    Will use `model_index_manager.provider_info.run_provider_fetch(provider,
    model_ids, force_refresh)` (async). The core only fills fields that are empty.
    """
    raise NotImplementedError(_PHASE_3)


def write_attributes(model_id: str, values: Mapping[str, Any]) -> None:
    """Set the plugin's model attributes (`mb_base_model`, `mb_license`), keeping the model's other values.

    Will use `model_index_manager.metadata.update_model_metadata(model_id, values)`,
    which replaces the whole map: merge with the current values first.
    """
    raise NotImplementedError(_PHASE_3)


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
) -> None:
    """Notify one user; `notification_type` is one the plugin registered ("model-browser.download_done", ...).

    Will use `notification_manager(...)`, the core's `notify` already bound to its
    collaborators (`notification_repository` is its store), with
    `source="model-browser"`.
    """
    raise NotImplementedError(_PHASE_3)


def limit_status(user_id: str, kind: str) -> Dict[str, Any]:
    """Where `user_id` stands against the plan limit `kind`: exempt or not, the limit, the usage so far.

    Will use `plans.guard` (`resolution(user_id)`, `is_exempt(...)`,
    `measure(kind, user_id)`) and `plans.events`, the ledger behind `LimitEvents`.
    """
    raise NotImplementedError(_PHASE_3)
