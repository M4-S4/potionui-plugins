"""`backend.core_bridge`: the container attribute check and every bridge function, on a fake container."""

import dataclasses
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
        "plans.guard.resolution",
        "plans.guard.is_exempt",
        "plans.guard.measure",
        "plans.guard.settings.read",
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


# Phase 3: downloads, models, assignment, enrichment, notifications ---------------------
#
# The fakes hand back the core's own records and raise the core's own exceptions, so a
# renamed field or exception breaks these tests rather than the plugin.

_ADMIN = User(
    id="admin-1",
    username="admin",
    email="admin@test.com",
    password_hash="hash",
    account_type=AccountType.ADMIN,
)
_USER = User(id="user-1", username="user", email="user@test.com", password_hash="hash", account_type=AccountType.USER)
_SHA = "ab" * 32
_URL = "https://civitai.com/api/download/models/135867"


def _download(**fields):
    from src.features.downloads.models import Download, DownloadStatus

    values = dict(
        id="dl-1",
        url=_URL,
        destination_path="/app/models/loras/add-detail-xl.safetensors",
        filename="add-detail-xl.safetensors",
        status=DownloadStatus.PENDING,
        checksum_sha256=_SHA,
        provider_id="civitai",
        tags=["model-browser", "model-browser:civitai"],
        created_by="user-1",
    )
    values.update(fields)
    return Download(**values)


def _model(**fields):
    from src.features.models.records import Model

    values = dict(
        id="model-1",
        filename="add-detail-xl.safetensors",
        sha256=_SHA,
        model_type="lora",
        model_metadata={"strength": 0.8},
    )
    values.update(fields)
    return Model(**values)


async def test_queue_model_download_passes_every_argument_and_returns_the_download(live_container):
    calls = []

    async def queue_model_download(url, **kwargs):
        calls.append((url, kwargs))
        return _download()

    live_container.download_queue.queue_model_download = queue_model_download

    download = await core_bridge.queue_model_download(
        _URL,
        filename="add-detail-xl.safetensors",
        model_type="lora",
        subdir="sdxl",
        tags=("model-browser", "model-browser:civitai"),
        checksum_sha256=_SHA,
        provider_id="civitai",
        created_by="user-1",
        destination_backend_id="worker-1",
    )

    assert calls == [
        (
            _URL,
            {
                "filename": "add-detail-xl.safetensors",
                "tags": ["model-browser", "model-browser:civitai"],
                "checksum_sha256": _SHA,
                "provider_id": "civitai",
                "created_by": "user-1",
                "model_type": "lora",
                "subdir": "sdxl",
                "destination_backend_id": "worker-1",
            },
        )
    ]
    assert download == _download().to_dict()
    assert download["status"] == "pending" and download["id"] == "dl-1"


@pytest.mark.parametrize(
    "message, code",
    [
        ("Quota plugin: monthly download limit reached", "blocked"),
        ("No model root resolver is configured", "blocked"),
        ("Subfolder '../x' must be a relative path with no '..' segments", "invalid"),
        ("Destination directory 'x' escapes the configured directory '/app/models'", "invalid"),
        ("No backend configured with id 'worker-9'", "invalid"),
        ("Backend 'worker-1' is not a native.remote backend", "invalid"),
        ("Backend 'worker-1' is not fully configured", "invalid"),
    ],
)
async def test_queue_model_download_turns_the_cores_refusals_into_codes(live_container, message, code):
    from src.features.downloads.exceptions import DownloadQueueException

    async def queue_model_download(url, **kwargs):
        raise DownloadQueueException(message)

    live_container.download_queue.queue_model_download = queue_model_download

    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        await core_bridge.queue_model_download(_URL, model_type="lora")

    assert (raised.value.code, raised.value.message) == (code, message)


async def test_an_unsafe_file_name_is_invalid(live_container):
    from src.features.downloads.exceptions import UnsafeFilenameException

    async def queue_model_download(url, **kwargs):
        raise UnsafeFilenameException("Filename '..' would escape its directory")

    live_container.download_queue.queue_model_download = queue_model_download

    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        await core_bridge.queue_model_download(_URL, filename="..")

    assert raised.value.code == "invalid"


def test_get_download_is_the_download_or_none_once_the_core_dropped_it(live_container):
    from src.features.downloads.exceptions import DownloadNotFoundException
    from src.features.downloads.models import DownloadStatus

    def get_download(download_id):
        if download_id == "dl-1":
            return _download(status=DownloadStatus.COMPLETED, progress=1.0)
        raise DownloadNotFoundException(f"Download '{download_id}' not found")

    live_container.download_queue.get_download = get_download

    assert core_bridge.get_download("dl-1")["status"] == "completed"
    assert core_bridge.get_download("dl-404") is None
    assert core_bridge.get_download(None) is None
    assert core_bridge.get_download("") is None


def test_find_model_by_sha256_looks_the_lower_case_hash_up_without_providers(live_container):
    asked = []

    def get_by_sha256(sha256, include_providers=True):
        asked.append((sha256, include_providers))
        return _model() if sha256 == _SHA else None

    live_container.model_repository.get_by_sha256 = get_by_sha256

    found = core_bridge.find_model_by_sha256(" " + _SHA.upper())

    assert asked == [(_SHA, False)]
    assert (found["id"], found["sha256"], found["model_type"], found["filename"]) == (
        "model-1",
        _SHA,
        "lora",
        "add-detail-xl.safetensors",
    )
    assert found["model_metadata"] == {"strength": 0.8} and found["is_available"] is True
    assert core_bridge.find_model_by_sha256("cd" * 32) is None
    assert core_bridge.find_model_by_sha256("") is None


def test_find_model_by_path_is_the_exported_model_for_path(monkeypatch):
    asked = []
    monkeypatch.setattr(core_bridge, "model_for_path", lambda path: asked.append(path) or {"id": "model-1"})

    assert core_bridge.find_model_by_path("/app/models/loras/x.safetensors") == {"id": "model-1"}
    assert core_bridge.find_model_by_path("") is None
    assert asked == ["/app/models/loras/x.safetensors"]


def test_visible_model_ids_are_the_users_direct_and_group_models(live_container):
    live_container.model_repository.get_available_model_ids_for_user = lambda user_id: iter(["model-1", "model-2"])

    assert core_bridge.visible_model_ids("user-1") == ["model-1", "model-2"]


def test_assign_to_user_says_whether_the_model_was_newly_assigned(live_container):
    from src.features.models.exceptions import ModelAlreadyAssignedException, ModelAssignmentException

    assigned = []

    def assign_model_to_user(model_id, user_id):
        if (model_id, user_id) in assigned:
            raise ModelAlreadyAssignedException(f"Model '{model_id}' is already assigned to user '{user_id}'")
        if user_id == "ghost":
            raise ModelAssignmentException(f"Could not assign model '{model_id}' to user '{user_id}' - no such user")
        assigned.append((model_id, user_id))
        return {"assignment": {}}

    live_container.model_index_manager.assignments.assign_model_to_user = assign_model_to_user

    assert core_bridge.assign_to_user("model-1", "user-1") is True
    assert core_bridge.assign_to_user("model-1", "user-1") is False
    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.assign_to_user("model-1", "ghost")
    assert raised.value.code == "refused" and "no such user" in raised.value.message


def _group_repository(live_container, groups=("artists",), existing=()):
    from src.features.user_groups.records import UserGroupModel

    store = {group_id: list(existing) for group_id in groups}

    def get_group_by_id(group_id):
        return UserGroup(id=group_id, name=group_id.title()) if group_id in store else None

    def assign_model_to_group(group_id, model_id):
        if group_id not in store or model_id in store[group_id]:
            return None
        store[group_id].append(model_id)
        return UserGroupModel(id=f"a-{model_id}", group_id=group_id, model_id=model_id)

    live_container.user_group_repository.get_group_by_id = get_group_by_id
    live_container.user_group_repository.assign_model_to_group = assign_model_to_group
    return store


def test_assign_to_group_without_an_admin_assigns_through_the_repository(live_container):
    store = _group_repository(live_container, existing=["model-1"])

    assert core_bridge.assign_to_group("artists", ["model-1", "model-2", ""]) == ["model-2"]
    assert store["artists"] == ["model-1", "model-2"]
    assert core_bridge.assign_to_group("artists", []) == []


def test_assign_to_group_refuses_a_group_that_does_not_exist(live_container):
    _group_repository(live_container)

    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.assign_to_group("ghosts", ["model-1"])

    assert raised.value.code == "not_found"


class _FakePlugins:
    """A plugin registry whose hooks only record what they were given; `blocked` model ids are vetoed."""

    def __init__(self, blocked=()):
        self.fired = []
        self.blocked = set(blocked)

    def execute_hook(self, hook, initial_data):
        name = str(getattr(hook, "name", hook))
        self.fired.append((name, dict(initial_data)))
        data = dict(initial_data)
        if name.endswith("before_assign_resource") and data.get("resource_id") in self.blocked:
            data.update(blocked=True, block_reason="not this one")
        return SimpleNamespace(data=data), []


def test_assign_to_group_as_an_admin_goes_through_the_cores_group_operation(live_container):
    store = _group_repository(live_container)
    plugins = live_container.plugin_registry = _FakePlugins(blocked={"model-3"})

    assigned = core_bridge.assign_to_group("artists", ["model-1", "model-3"], acting_admin=_ADMIN)

    assert assigned == ["model-1"]
    assert store["artists"] == ["model-1"]
    before = [data for name, data in plugins.fired if name.endswith("before_assign_resource")]
    after = [data for name, data in plugins.fired if name.endswith("after_assign_resource")]
    assert [(data["resource_type"], data["resource_id"], data["admin_id"]) for data in before] == [
        ("model", "model-1", "admin-1"),
        ("model", "model-3", "admin-1"),
    ]
    assert [data["resource_id"] for data in after] == ["model-1"]


def test_assign_to_group_refuses_an_acting_user_who_is_not_an_admin(live_container):
    _group_repository(live_container)
    live_container.plugin_registry = _FakePlugins()

    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.assign_to_group("artists", ["model-1"], acting_admin=_USER)

    assert raised.value.code == "refused" and "Admin" in raised.value.message


async def test_run_provider_fetch_asks_for_these_models_only(live_container):
    calls = []

    async def run_provider_fetch(provider, model_ids=None, force_refresh=False):
        calls.append((provider, model_ids, force_refresh))
        return {"successful": 1, "failed": 0}

    live_container.model_index_manager.provider_info.run_provider_fetch = run_provider_fetch

    assert await core_bridge.run_provider_fetch("model-browser", ("model-1", "")) == {"successful": 1, "failed": 0}
    assert calls == [("model-browser", ["model-1"], False)]
    # An empty list would make the core fetch every model without provider info.
    assert await core_bridge.run_provider_fetch("model-browser", []) == {"successful": 0, "failed": 0}
    assert len(calls) == 1


def test_read_attributes_is_a_copy_of_the_models_metadata(live_container):
    stored = _model()
    live_container.model_repository.get_by_id = (
        lambda model_id, include_providers=True, include_tags=True: stored if model_id == "model-1" else None
    )

    values = core_bridge.read_attributes("model-1")
    values["strength"] = 1.0

    assert stored.model_metadata == {"strength": 0.8}
    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.read_attributes("model-404")
    assert raised.value.code == "not_found"


def test_write_attributes_merges_with_the_current_values(live_container):
    from src.features.models.exceptions import InvalidModelMetadataException, ModelNotFoundException

    stored = _model()
    written = []
    live_container.model_repository.get_by_id = lambda model_id, include_providers=True, include_tags=True: stored

    def update_model_metadata(model_id, values):
        if "unknown" in values:
            raise InvalidModelMetadataException("'unknown' is not a declared attribute for model type 'lora'")
        if model_id == "model-gone":
            raise ModelNotFoundException("Model 'model-gone' not found")
        written.append((model_id, dict(values)))
        stored.model_metadata = dict(values)
        return {}

    live_container.model_index_manager.metadata.update_model_metadata = update_model_metadata

    core_bridge.write_attributes("model-1", {"mb_base_model": "SDXL 1.0", "mb_license": "MIT"})
    assert written == [("model-1", {"strength": 0.8, "mb_base_model": "SDXL 1.0", "mb_license": "MIT"})]

    core_bridge.write_attributes("model-1", {"mb_license": "MIT"})  # nothing changes: nothing written
    assert len(written) == 1

    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.write_attributes("model-1", {"unknown": "x"})
    assert raised.value.code == "invalid"
    with pytest.raises(core_bridge.CoreBridgeError) as raised:
        core_bridge.write_attributes("model-gone", {"mb_license": "Apache-2.0"})
    assert raised.value.code == "not_found"


def test_notify_sends_one_users_notification_from_the_plugin(live_container):
    sent = []
    live_container.notification_manager = lambda **kwargs: sent.append(kwargs) or []

    core_bridge.notify(
        user_id="user-1",
        notification_type="model-browser.download_done",
        title="Model downloaded",
        message="Detail Tweaker XL is ready",
        level="success",
        metadata={"model_id": "model-1"},
    )

    assert sent == [
        {
            "level": "success",
            "title": "Model downloaded",
            "message": "Detail Tweaker XL is ready",
            "category": "plugin",
            "user_id": "user-1",
            "source": "model-browser",
            "metadata": {"model_id": "model-1"},
            "type": "model-browser.download_done",
        }
    ]


def test_notify_never_broadcasts_and_never_raises(live_container, caplog):
    sent = []

    def notification_manager(**kwargs):
        sent.append(kwargs)
        raise ValueError("'loud' is not a valid NotificationLevel")

    live_container.notification_manager = notification_manager

    core_bridge.notify(user_id="", notification_type="model-browser.download_done", title="x")
    assert sent == []
    core_bridge.notify(user_id="user-1", notification_type="model-browser.download_done", title="x", level="loud")
    assert len(sent) == 1 and sent[0]["metadata"] is None
    assert "Could not send" in caplog.text


@pytest.mark.parametrize(
    "call, path",
    [
        (lambda: core_bridge.get_download("dl-1"), "download_queue.get_download"),
        (lambda: core_bridge.find_model_by_sha256("ab" * 32), "model_repository.get_by_sha256"),
        (
            lambda: core_bridge.assign_to_user("model-1", "user-1"),
            "model_index_manager.assignments.assign_model_to_user",
        ),
    ],
    ids=["get_download", "find_model_by_sha256", "assign_to_user"],
)
def test_a_phase_3_function_names_the_attribute_the_core_moved(live_container, call, path):
    del live_container.download_queue
    del live_container.model_repository.get_by_sha256
    del live_container.model_index_manager.assignments

    with pytest.raises(RuntimeError) as raised:
        call()

    assert path in str(raised.value)


# Phase 5: group members, notification types, plan limits -------------------------------


def test_group_member_ids_are_the_members_user_ids_once_each(live_container):
    from src.features.user_groups.records import UserGroupMember

    asked = []

    def get_group_members(group_id):
        asked.append(group_id)
        return [
            UserGroupMember(group_id=group_id, user_id="user-2", id="m-2"),
            UserGroupMember(group_id=group_id, user_id="user-1", id="m-1"),
            UserGroupMember(group_id=group_id, user_id="user-2", id="m-3"),
        ]

    live_container.user_group_repository.get_group_members = get_group_members

    assert core_bridge.group_member_ids("approvers") == ["user-2", "user-1"]
    assert asked == ["approvers"]


def test_register_notification_types_declares_each_type_once_on_the_cores_registry():
    from src.features.notifications.types import NotificationTypeRegistry, NotificationTypeSpec

    registry = NotificationTypeRegistry()
    registry.register(NotificationTypeSpec(key="model-browser.download_done", label="Already there"))
    types = [
        SimpleNamespace(key="model-browser.download_done", label="Model ready", description="d", category="plugin"),
        SimpleNamespace(key="model-browser.request_received", label="New request", description="r", category="plugin"),
    ]

    assert core_bridge.register_notification_types(registry, types) == ["model-browser.request_received"]
    assert core_bridge.register_notification_types(registry, types) == []
    spec = registry.get("model-browser.request_received")
    assert isinstance(spec, NotificationTypeSpec)
    assert (spec.label, spec.description, spec.category, spec.default_enabled, spec.admin_only) == (
        "New request", "r", "plugin", True, False,
    )
    assert registry.get("model-browser.download_done").label == "Already there"


def _plans(live_container, *, limit=None, admin=False, exempt_admins=True, used=2.0, registered=True):
    """The plans machinery the way `limit_status` reads it, built from the core's own records."""
    from datetime import datetime, timezone

    from src.features.plans.guard import Measured, PlanSettings
    from src.features.plans.records import Plan, PlanLimit, PlanSubject
    from src.features.plans.resolver import PlanResolver
    from src.platform.plugins.limit_kinds import LimitKind

    kind = LimitKind(key="model-browser.downloads", label="Model downloads per month", value_type="count",
                     window="month", measure=lambda context: 0, source="model-browser")
    limits = (PlanLimit(kind="model-browser.downloads", value=limit),) if limit is not None else ()
    plans = {"plan-1": Plan(id="plan-1", name="Starter", limits=limits)}
    subject = PlanSubject(user_id="user-1", username="user", email="u@test.com",
                          account_type="ADMIN" if admin else "USER", override_plan_id="plan-1",
                          groups=(), default_plan_id=None)
    resolver = PlanResolver(is_active=lambda key: registered and key == kind.key)
    measured_for = []

    def measure(limit_kind, user_id, tz_name=None, now=None):
        measured_for.append((limit_kind, user_id, tz_name))
        return Measured(used=used, window_start=datetime(2026, 10, 1, tzinfo=timezone.utc),
                        resets_at=datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc))

    settings = PlanSettings(exempt_admins=exempt_admins, day_timezone="Europe/Paris", contact_line="Ask your admin.")
    guard = live_container.plans.guard
    guard.resolution = lambda user_id: resolver.resolve(subject, plans) if user_id == "user-1" else None
    guard.is_exempt = lambda subject, settings: settings.exempt_admins and subject.is_admin
    guard.measure = measure
    guard.settings.read = lambda: settings
    live_container.limit_kind_registry.get = lambda key: kind if registered and key == kind.key else None
    return SimpleNamespace(kind=kind, measured_for=measured_for)


def test_limit_status_measures_the_usage_against_the_users_limit(live_container):
    plans = _plans(live_container, limit=5, used=2.0)

    status = core_bridge.limit_status("user-1", "model-browser.downloads")

    assert status == {
        "kind": "model-browser.downloads",
        "limit": 5,
        "used": 2.0,
        "exempt": False,
        "resets_at": "2026-11-01T00:00:00+01:00",  # the end of the window, in the plans' time zone
        "contact_line": "Ask your admin.",
    }
    assert plans.measured_for == [(plans.kind, "user-1", "Europe/Paris")]  # the LimitKind, not its key


@pytest.mark.parametrize(
    "case",
    ["no-plan-limit", "unknown-user", "kind-not-registered"],
)
def test_limit_status_is_unlimited_without_a_limit_for_the_kind(live_container, case):
    plans = _plans(live_container, limit=None if case == "no-plan-limit" else 5, registered=case != "kind-not-registered")
    user_id = "ghost" if case == "unknown-user" else "user-1"

    status = core_bridge.limit_status(user_id, "model-browser.downloads")

    assert (status["limit"], status["used"], status["exempt"]) == (None, None, False)
    assert plans.measured_for == []


def test_limit_status_of_an_exempt_admin_is_not_measured(live_container):
    plans = _plans(live_container, limit=1, admin=True)

    status = core_bridge.limit_status("user-1", "model-browser.downloads")

    assert (status["limit"], status["exempt"], status["used"]) == (1, True, None)
    assert plans.measured_for == []


def test_limit_status_measures_an_admin_when_admins_are_not_exempt(live_container):
    _plans(live_container, limit=1, admin=True, exempt_admins=False, used=1.0)

    status = core_bridge.limit_status("user-1", "model-browser.downloads")

    assert (status["exempt"], status["used"], status["limit"]) == (False, 1.0, 1)


def test_limit_status_reads_unlimited_when_the_plans_cannot_be_read(live_container, caplog):
    _plans(live_container, limit=1)

    def broken(user_id):
        raise RuntimeError("no such table: plans")

    live_container.plans.guard.resolution = broken

    status = core_bridge.limit_status("user-1", "model-browser.downloads")

    assert status["limit"] is None
    assert "treating it as unlimited" in caplog.text


def test_limit_status_reads_unlimited_when_the_core_moved_the_plans(live_container):
    del live_container.plans

    assert core_bridge.limit_status("user-1", "model-browser.downloads")["limit"] is None
