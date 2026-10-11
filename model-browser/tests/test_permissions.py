"""`backend.permissions`: a user's groups merged into their grant, and the FastAPI dependencies.

The core's group membership is faked on `core_bridge.user_groups`; the plugin's rows
live in a scratch database.
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import core_bridge, permissions
from backend.permissions import (
    ADMIN_GRANT,
    CAPABILITIES,
    DEFAULT_SOURCES,
    Grant,
    Principal,
    current_principal,
    merge_rows,
    require,
    require_browse,
    require_download,
    resolve_grant,
)
from backend.permissions_store import Row, default_row, load_rows, save_rows
from backend.tables import create_tables
from src.plugin_api import AccountType, User, get_current_active_user

_FORBIDDEN_DOWNLOAD = {
    "success": False,
    "error": "forbidden",
    "message": "This action needs the 'download' permission",
}


def _user(user_id="user-1", account_type=AccountType.USER):
    return User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@test.com",
        password_hash="hash",
        account_type=account_type,
    )


@pytest.fixture
def membership(plugin_db, monkeypatch):
    """The core's group membership by user id, for the test to fill; the plugin's table starts empty."""
    create_tables()
    members = {}

    def user_groups(user_id):
        return [
            {
                "id": group_id,
                "name": group_id,
                "is_system": group_id in ("all_users", "all_admins"),
                "content_policy": None,
            }
            for group_id in members.get(user_id, [])
        ]

    monkeypatch.setattr(core_bridge, "user_groups", user_groups)
    return members


def _download_row(group_id, **params):
    return Row(group_id=group_id, capabilities=frozenset({"download"}), **params)


def test_the_public_names_stay_importable_from_permissions():
    assert permissions.CAPABILITIES == ("browse", "request", "download", "approve")
    assert permissions.DEFAULT_CAPABILITIES["all_users"] == {"browse", "request"}
    assert permissions.DEFAULT_CAPABILITIES["all_admins"] == set(CAPABILITIES)
    assert permissions.DEFAULT_SOURCES == {"civitai", "huggingface", "openmodeldb"}


# Resolution ---------------------------------------------------------------------


def test_an_admin_gets_the_admin_grant_without_a_group_lookup(monkeypatch):
    def user_groups(user_id):
        raise AssertionError("an admin's groups are not read")

    monkeypatch.setattr(core_bridge, "user_groups", user_groups)

    grant = resolve_grant(_user("admin-1", AccountType.ADMIN))

    assert grant is ADMIN_GRANT
    assert grant.unrestricted
    assert all(grant.has(capability) for capability in CAPABILITIES)


def test_a_user_in_all_users_only_may_browse_and_request_by_default(membership):
    membership["user-1"] = ["all_users"]

    grant = resolve_grant(_user())

    assert grant.capabilities == {"browse", "request"}
    assert not grant.has("download") and not grant.has("approve")
    assert not grant.unrestricted
    # No group grants `download`, so no download parameter applies.
    assert (grant.sources, grant.model_types, grant.max_file_gb, grant.assign_to, grant.allow_remote) == (
        frozenset(),
        frozenset(),
        None,
        "user",
        False,
    )


def test_a_non_admin_account_in_all_admins_gets_every_capability_with_the_default_parameters(membership):
    membership["user-1"] = ["all_users", "all_admins"]

    grant = resolve_grant(_user())

    assert grant.capabilities == set(CAPABILITIES)
    assert not grant.unrestricted
    assert grant.sources == DEFAULT_SOURCES
    assert not grant.allows_source("civarchive")
    assert grant.model_types == frozenset()
    assert (grant.max_file_gb, grant.assign_to, grant.allow_remote) == (None, "user", False)


def test_a_stored_row_replaces_the_groups_default(membership):
    membership["user-1"] = ["all_users"]
    save_rows([Row(group_id="all_users", capabilities=frozenset({"browse"}))])

    assert resolve_grant(_user()).capabilities == {"browse"}


def test_two_downloading_groups_merge_their_parameters(membership):
    membership["user-1"] = ["all_users", "lora-makers", "hf-users"]
    save_rows(
        [
            _download_row("lora-makers", sources={"civitai"}, model_types={"lora"}, max_file_gb=2.0),
            Row(
                group_id="hf-users",
                capabilities=frozenset({"browse", "download"}),
                sources=frozenset({"huggingface"}),
                model_types=frozenset(),
                max_file_gb=10.0,
                assign_to="group",
                allow_remote=True,
            ),
        ]
    )

    grant = resolve_grant(_user())

    assert grant.capabilities == {"browse", "request", "download"}
    assert grant.sources == {"civitai", "huggingface"}
    assert grant.model_types == frozenset()  # hf-users lists no type: every type
    assert grant.allows_type("checkpoint")
    assert grant.max_file_gb == 10.0
    assert grant.assign_to == "group"
    assert grant.allow_remote is True


def test_a_group_without_a_row_that_has_no_default_grants_nothing(membership):
    membership["user-1"] = ["artists"]

    grant = resolve_grant(_user())

    assert grant.capabilities == frozenset()
    assert not any(grant.has(capability) for capability in CAPABILITIES)


def test_a_user_in_no_group_may_do_nothing(membership):
    grant = resolve_grant(_user("loner"))

    assert grant.capabilities == frozenset()
    assert not any(grant.has(capability) for capability in CAPABILITIES)


def test_the_row_of_a_deleted_group_is_ignored_and_left_for_the_admin_routes(membership):
    membership["user-1"] = ["all_users"]
    save_rows([Row(group_id="deleted-group", capabilities=frozenset(CAPABILITIES))])

    assert not resolve_grant(_user()).has("download")
    assert "deleted-group" in load_rows()


# Merge rules ------------------------------------------------------------------------


def test_capabilities_are_united_across_groups():
    grant = merge_rows(
        [Row(group_id="a", capabilities=frozenset({"browse"})), Row(group_id="b", capabilities=frozenset({"approve"}))]
    )

    assert grant.capabilities == {"browse", "approve"}


def test_model_types_are_united_when_every_downloading_group_lists_some():
    grant = merge_rows(
        [_download_row("a", model_types={"lora"}), _download_row("b", model_types={"embedding", "vae"})]
    )

    assert grant.model_types == {"lora", "embedding", "vae"}
    assert not grant.allows_type("checkpoint")


@pytest.mark.parametrize(
    "sizes, merged",
    [((2.0, 8.5), 8.5), ((2.0, None), None), ((None,), None), ((4.0,), 4.0)],
)
def test_the_largest_size_wins_and_no_limit_beats_any_limit(sizes, merged):
    grant = merge_rows([_download_row(f"g{index}", max_file_gb=size) for index, size in enumerate(sizes)])

    assert grant.max_file_gb == merged


@pytest.mark.parametrize(
    "assign_tos, merged",
    [(("user", "user"), "user"), (("user", "group"), "group"), (("group",), "group")],
)
def test_assign_to_is_group_as_soon_as_one_group_says_so(assign_tos, merged):
    grant = merge_rows([_download_row(f"g{index}", assign_to=value) for index, value in enumerate(assign_tos)])

    assert grant.assign_to == merged


@pytest.mark.parametrize("remotes, merged", [((False, False), False), ((False, True), True)])
def test_allow_remote_when_one_group_allows_it(remotes, merged):
    grant = merge_rows([_download_row(f"g{index}", allow_remote=value) for index, value in enumerate(remotes)])

    assert grant.allow_remote is merged


def test_parameters_come_only_from_the_groups_that_grant_download():
    browse_only = Row(
        group_id="browsers",
        capabilities=frozenset({"browse", "request"}),
        sources=frozenset({"civarchive"}),
        model_types=frozenset(),
        max_file_gb=None,
        assign_to="group",
        allow_remote=True,
    )
    downloader = _download_row("downloaders", sources={"civitai"}, model_types={"lora"}, max_file_gb=1.5)

    grant = merge_rows([browse_only, downloader])

    assert grant.capabilities == {"browse", "request", "download"}
    assert grant.sources == {"civitai"}
    assert grant.model_types == {"lora"}
    assert grant.max_file_gb == 1.5
    assert grant.assign_to == "user"
    assert grant.allow_remote is False


def test_merging_no_row_grants_nothing():
    assert merge_rows([]) == merge_rows([default_row("artists")])
    assert merge_rows([]).capabilities == frozenset()


# Grant checks -----------------------------------------------------------------------


def _grant(**changes):
    values = dict(
        capabilities=frozenset({"browse", "download"}),
        sources=frozenset({"civitai"}),
        model_types=frozenset({"lora"}),
        max_file_gb=None,
        assign_to="user",
        allow_remote=False,
        unrestricted=False,
    )
    values.update(changes)
    return Grant(**values)


def test_allows_source_is_membership_and_no_source_allows_none():
    assert _grant().allows_source("civitai")
    assert not _grant().allows_source("huggingface")
    assert not _grant(sources=frozenset()).allows_source("civitai")


def test_allows_type_is_membership_and_no_type_allows_every_type():
    assert _grant().allows_type("lora")
    assert not _grant().allows_type("checkpoint")
    assert _grant(model_types=frozenset()).allows_type("checkpoint")


def test_an_unrestricted_grant_allows_everything():
    assert ADMIN_GRANT.allows_source("civarchive")
    assert ADMIN_GRANT.allows_type("checkpoint")
    assert _grant(sources=frozenset(), unrestricted=True).allows_source("huggingface")
    assert _grant(capabilities=frozenset(), unrestricted=True).has("approve")


# Dependencies -----------------------------------------------------------------------


def test_require_download_refuses_a_browse_only_user_with_the_envelope(membership):
    membership["user-1"] = ["all_users"]

    with pytest.raises(HTTPException) as raised:
        require_download(user=_user())

    assert raised.value.status_code == 403
    assert raised.value.detail == _FORBIDDEN_DOWNLOAD


def test_require_yields_the_principal_when_the_capability_is_granted(membership):
    membership["user-1"] = ["all_users"]

    principal = require_browse(user=_user())

    assert isinstance(principal, Principal)
    assert principal.user.id == "user-1"
    assert principal.grant.capabilities == {"browse", "request"}
    assert not principal.is_admin


def test_require_rejects_an_unknown_capability():
    with pytest.raises(ValueError):
        require("manage")


def test_current_principal_needs_no_capability(membership):
    assert current_principal(user=_user("loner")).grant.capabilities == frozenset()
    assert current_principal(user=_user("admin-1", AccountType.ADMIN)).is_admin


def test_a_route_behind_require_download_answers_403_then_200(membership):
    app = FastAPI()

    @app.get("/download-only")
    def download_only(principal: Principal = Depends(require_download)):
        return {"user": principal.user.id}

    app.dependency_overrides[get_current_active_user] = lambda: _user()
    membership["user-1"] = ["all_users"]

    with TestClient(app) as client:
        refused = client.get("/download-only")
        save_rows([Row(group_id="all_users", capabilities=frozenset({"browse", "download"}))])
        allowed = client.get("/download-only")

    assert refused.status_code == 403
    assert refused.json() == {"detail": _FORBIDDEN_DOWNLOAD}
    assert allowed.status_code == 200
    assert allowed.json() == {"user": "user-1"}
