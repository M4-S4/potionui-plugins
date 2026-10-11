"""`backend.core_bridge`: the container attribute check, the phase 1 functions, and the phase 3 stubs."""

import dataclasses
import inspect
from types import SimpleNamespace

import pytest

from backend import core_bridge
from backend.core_bridge import REQUIRED_ATTRIBUTES, check_container, missing_attributes
from src.features.user_groups.records import UserGroup
from src.plugin_api import AccountType, User


def test_a_complete_container_misses_nothing(fake_container):
    assert missing_attributes(fake_container) == []


def test_a_missing_leaf_and_a_missing_parent_are_reported_in_full(fake_container):
    del fake_container.model_index_manager.assignments.assign_model_to_user
    del fake_container.plans

    assert missing_attributes(fake_container) == [
        "model_index_manager.assignments.assign_model_to_user",
        "plans.guard",
        "plans.events",
    ]


def test_an_attribute_set_to_none_counts_as_missing(fake_container):
    fake_container.notification_manager = None

    assert missing_attributes(fake_container) == ["notification_manager"]


def test_check_container_names_each_missing_path(monkeypatch, fake_container):
    del fake_container.content_policy_resolver
    del fake_container.model_repository.get_available_model_ids_for_user
    monkeypatch.setattr(core_bridge, "get_container", lambda: fake_container)

    with pytest.raises(RuntimeError) as raised:
        check_container()

    message = str(raised.value)
    assert "content_policy_resolver" in message
    assert "model_repository.get_available_model_ids_for_user" in message
    assert "core_bridge.py" in message


def test_check_container_returns_a_complete_container(monkeypatch, fake_container):
    monkeypatch.setattr(core_bridge, "get_container", lambda: fake_container)

    assert check_container() is fake_container


def test_the_core_container_still_declares_every_attribute_core_bridge_uses():
    """Fails when PotionUI renames or removes an AppContainer attribute (PLAN.md §3)."""
    from src.bootstrap.container import AppContainer

    declared = set(getattr(AppContainer, "__annotations__", {}))
    if dataclasses.is_dataclass(AppContainer):
        declared |= {field.name for field in dataclasses.fields(AppContainer)}
    gone = sorted({path.split(".", 1)[0] for path in REQUIRED_ATTRIBUTES} - declared)

    assert not gone, (
        f"PotionUI's AppContainer (src/bootstrap/container.py) no longer declares {gone}. "
        "The core renamed or removed attributes model-browser relies on: update "
        "REQUIRED_ATTRIBUTES and the functions that use them in backend/core_bridge.py."
    )


@pytest.fixture
def live_container(monkeypatch, fake_container):
    """`fake_container` as the container `get_container()` hands core_bridge."""
    monkeypatch.setattr(core_bridge, "get_container", lambda: fake_container)
    return fake_container


# Phase 1: content policy and user groups -------------------------------------


@pytest.mark.parametrize("mode", ["allowed", "blur", "blocked"])
def test_effective_policy_is_the_mode_the_core_resolves_for_the_user(live_container, mode):
    asked = []

    def resolve(user_id):
        asked.append(user_id)
        return SimpleNamespace(mode=mode, restricted=False)

    live_container.content_policy_resolver.resolve = resolve

    assert core_bridge.effective_policy("user-1") == mode
    assert asked == ["user-1"]


@pytest.mark.parametrize("mode", ["restricted", "ALLOWED", "", None])
def test_effective_policy_counts_a_mode_it_does_not_know_as_blocked(live_container, mode):
    live_container.content_policy_resolver.resolve = lambda user_id: SimpleNamespace(mode=mode)

    assert core_bridge.effective_policy("user-1") == "blocked"


def _core_groups():
    """The core's own records, so a renamed field breaks this test rather than the plugin."""
    return [
        UserGroup(id="all_admins", name="All Admins", description="Every admin", is_system=True),
        UserGroup(id="artists", name="Artists", content_policy="blur"),
    ]


_GROUP_DICTS = [
    {"id": "all_admins", "name": "All Admins", "is_system": True, "content_policy": None},
    {"id": "artists", "name": "Artists", "is_system": False, "content_policy": "blur"},
]


def test_user_groups_are_the_users_groups_as_plain_dicts(live_container):
    asked = []

    def get_user_groups(user_id):
        asked.append(user_id)
        return _core_groups()

    live_container.user_group_repository.get_user_groups = get_user_groups

    assert core_bridge.user_groups("user-1") == _GROUP_DICTS
    assert asked == ["user-1"]


def test_list_groups_is_every_group_as_plain_dicts_in_the_cores_order(live_container):
    live_container.user_group_repository.get_all_groups = _core_groups

    assert core_bridge.list_groups() == _GROUP_DICTS


@pytest.mark.parametrize(
    "call, path",
    [
        (lambda: core_bridge.effective_policy("user-1"), "content_policy_resolver.resolve"),
        (lambda: core_bridge.user_groups("user-1"), "user_group_repository.get_user_groups"),
        (core_bridge.list_groups, "user_group_repository.get_all_groups"),
    ],
    ids=["effective_policy", "user_groups", "list_groups"],
)
def test_a_function_names_the_attribute_the_core_moved(live_container, call, path):
    del live_container.user_group_repository
    del live_container.content_policy_resolver.resolve

    with pytest.raises(RuntimeError) as raised:
        call()

    assert path in str(raised.value)
    assert "core_bridge.py" in str(raised.value)


def test_a_moved_attribute_only_breaks_the_functions_that_use_it(live_container):
    del live_container.plans
    live_container.content_policy_resolver.resolve = lambda user_id: SimpleNamespace(mode="blur")

    assert core_bridge.effective_policy("user-1") == "blur"


# Phase 3 stubs ----------------------------------------------------------------

_ADMIN = User(
    id="admin-1",
    username="admin",
    email="admin@test.com",
    password_hash="hash",
    account_type=AccountType.ADMIN,
)

# The functions PLAN.md §3 lists for core_bridge that phase 3 implements, with arguments of the right shape.
_STUB_CALLS = [
    ("queue_model_download", ("https://civitai.com/api/download/models/1",), {"checksum_sha256": "ab" * 32}),
    ("get_download", ("download-1",), {}),
    ("find_model_by_sha256", ("ab" * 32,), {}),
    ("visible_model_ids", ("user-1",), {}),
    ("assign_to_user", ("model-1", "user-1"), {}),
    ("assign_to_group", ("group-1", ["model-1"], _ADMIN), {}),
    ("run_provider_fetch", ("civitai", ["model-1"]), {}),
    ("write_attributes", ("model-1", {"mb_license": "CreativeML Open RAIL-M"}), {}),
    ("notify", (), {"user_id": "user-1", "notification_type": "model-browser.download_done", "title": "Done"}),
    ("limit_status", ("user-1", "model-browser.downloads"), {}),
]


@pytest.mark.parametrize("name, args, kwargs", _STUB_CALLS, ids=[call[0] for call in _STUB_CALLS])
async def test_bridge_functions_are_phase_3_stubs(name, args, kwargs):
    function = getattr(core_bridge, name)

    with pytest.raises(NotImplementedError, match="implemented in phase 3"):
        result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            await result
