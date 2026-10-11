"""`backend.watcher.Watcher`: the run loop, and the state machine that takes each pending row
from `queued` to `enriched` (or `failed`); the approved requests linked to a row, and the
quota refund of a failed one.

The core is `FakeCore` in place of `core_bridge`; the pending rows and the requests live in
a scratch database. The state machine is driven pass by pass with `run_pass()`.
"""

import asyncio
import hashlib
import logging

import pytest

from backend import core_bridge, downloads, pending, requests
from backend import watcher as watcher_module
from backend.core_bridge import CoreBridgeError
from backend.pending import NOHASH_PREFIX, PendingRow
from backend.tables import create_tables
from backend.watcher import Watcher, indexed_since, model_attributes, sha256_of_file

from .download_fakes import HF_URL, OTHER_SHA, SHA, FakeCore, civitai_detail, model

ATTRIBUTES = {"mb_base_model": "SDXL 1.0", "mb_license": "CreativeML Open RAIL++-M; no selling"}
HF_PATH = "/app/models/diffusion_models/transformer/flux1-dev.safetensors"


async def _until(predicate, timeout=1.0):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


@pytest.fixture
def core(plugin_db, monkeypatch):
    create_tables()
    return FakeCore().install(monkeypatch)


def _info():
    detail = civitai_detail()
    version = detail.versions[0]
    return downloads.pending_info(detail, version, version.files[0], "lora")


def _insert(key=SHA, **fields):
    values = dict(
        sha256=key,
        source="civitai",
        source_model_id="122359",
        source_version_id="135867",
        file_name="add-detail-xl.safetensors",
        requested_by="user-1",
        assign_to="user:user-1",
        info=_info(),
        download_id="dl-1",
    )
    values.update(fields)
    return pending.insert(PendingRow(**values))


def _row(key=SHA):
    return pending.get(key)


async def _passes(watcher, count=1):
    for _ in range(count):
        await watcher.run_pass()


# The run loop -----------------------------------------------------------------------------


@pytest.fixture
def no_pass(monkeypatch):
    """`run_pass` replaced by a counter: the loop tests never touch a database."""
    passes = []

    async def run_pass(self, *, reconcile=False):
        passes.append(reconcile)

    monkeypatch.setattr(Watcher, "run_pass", run_pass)
    return passes


async def test_run_returns_promptly_after_request_stop(monkeypatch, caplog, no_pass):
    caplog.set_level(logging.INFO, logger="plugins.model-browser")
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 0.01)
    watcher = Watcher()
    task = asyncio.create_task(watcher.run())
    await _until(lambda: watcher.running)
    await asyncio.sleep(0.05)  # a few passes
    assert not task.done()

    watcher.request_stop()
    await asyncio.wait_for(task, timeout=1)

    assert not watcher.running
    assert no_pass[0] is True and len(no_pass) > 1 and not any(no_pass[1:])  # the first pass reconciles
    messages = [record.getMessage() for record in caplog.records]
    assert any("Download watcher started" in message for message in messages)
    assert any("Download watcher stopped" in message for message in messages)


async def test_a_stop_from_another_thread_cuts_the_poll_interval_short(monkeypatch, no_pass):
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 60)
    watcher = Watcher()
    task = asyncio.create_task(watcher.run())
    await _until(lambda: watcher.running and no_pass)

    await asyncio.to_thread(watcher.request_stop)

    await asyncio.wait_for(task, timeout=1)
    assert no_pass == [True]


async def test_a_stop_requested_before_run_returns_at_once(monkeypatch, no_pass):
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 60)
    watcher = Watcher()

    watcher.request_stop()

    await asyncio.wait_for(watcher.run(), timeout=1)
    assert not watcher.running
    assert no_pass == []


async def test_the_first_pass_takes_up_the_rows_a_restart_left_unfinished(core, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="plugins.model-browser")
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 60)
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    _insert(SHA)
    _insert("c" * 64, status="indexed", model_id="model-2", download_id=None)
    _insert("d" * 64, status="assigned", model_id="model-3", download_id=None)
    watcher = Watcher()
    task = asyncio.create_task(watcher.run())

    await _until(lambda: all(_row(key).status == "enriched" for key in (SHA, "c" * 64, "d" * 64)), timeout=5)
    watcher.request_stop()
    await asyncio.wait_for(task, timeout=1)

    assert "Resuming 3 unfinished download(s)" in caplog.text
    # Rows written in the same second: their order does not matter here.
    assert sorted(core.calls_to("assign_to_user")) == [("model-1", "user-1"), ("model-2", "user-1")]
    assert sorted(call[1] for call in core.calls_to("run_provider_fetch")) == [["model-1"], ["model-2"], ["model-3"]]


async def test_a_pass_that_cannot_read_the_table_logs_once_and_carries_on(monkeypatch, caplog):
    def list_unfinished():
        raise RuntimeError("no such table: model_browser_pending")

    monkeypatch.setattr(pending, "list_unfinished", list_unfinished)
    watcher = Watcher()

    await _passes(watcher, 3)

    assert caplog.text.count("Could not read the pending downloads") == 1


# queued -> indexed -> assigned -> enriched -------------------------------------------------


async def test_a_completed_and_indexed_download_goes_all_the_way_in_one_pass(core):
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    _insert()

    await Watcher().run_pass()

    row = _row()
    assert (row.status, row.model_id, row.error) == ("enriched", "model-1", None)
    assert core.calls == [
        ("get_download", "dl-1"),
        ("find_model_by_sha256", SHA),
        ("assign_to_user", "model-1", "user-1"),
        ("run_provider_fetch", "model-browser", ["model-1"]),
        ("write_attributes", "model-1", ATTRIBUTES),
        ("notify", "model-browser.download_done"),
    ]
    [notification] = core.notifications
    assert (notification["user_id"], notification["level"], notification["title"]) == ("user-1", "success", "Model downloaded")
    assert notification["message"] == "Detail Tweaker XL (add-detail-xl.safetensors): it is now in your models."
    assert notification["metadata"] == {
        "source": "civitai",
        "source_model_id": "122359",
        "source_version_id": "135867",
        "sha256": SHA,
        "model_id": "model-1",
        "download_id": "dl-1",
    }


async def test_only_the_model_browser_provider_enriches_even_a_civitai_download(core):
    """The core's civitai provider would attach every image of the version as previews, NSFW ones included."""
    _insert(status="assigned", model_id="model-1")

    await Watcher().run_pass()

    assert core.calls_to("run_provider_fetch") == [("model-browser", ["model-1"])]
    assert _row().status == "enriched"


@pytest.mark.parametrize("status", ["pending", "downloading", "paused"])
async def test_a_download_still_on_its_way_is_left_as_it_is(core, status):
    core.add_download("dl-1", status)
    _insert()

    await Watcher().run_pass()

    assert _row().status == "queued"
    assert core.calls == [("get_download", "dl-1")]


async def test_the_model_is_found_on_a_later_pass_when_indexing_comes_after_completion(core):
    core.add_download("dl-1", "completed")
    _insert()
    watcher = Watcher()

    await watcher.run_pass()
    assert _row().status == "queued"

    core.models_by_sha[SHA] = model("model-1")
    await watcher.run_pass()

    assert (_row().status, _row().model_id) == ("enriched", "model-1")
    assert core.calls_to("find_model_by_sha256") == [(SHA,), (SHA,)]
    assert core.calls_to("find_model_by_path") == []


async def test_a_failed_download_fails_the_row_and_tells_the_requester(core):
    core.add_download("dl-1", "failed", error_message="Access denied (HTTP 401) fetching 'add-detail-xl.safetensors'")
    _insert()

    await Watcher().run_pass()

    row = _row()
    assert (row.status, row.error) == ("failed", "Access denied (HTTP 401) fetching 'add-detail-xl.safetensors'")
    assert "assign_to_user" not in core.names() and "run_provider_fetch" not in core.names()
    [notification] = core.notifications
    assert (notification["notification_type"], notification["level"]) == ("model-browser.download_failed", "error")
    assert notification["title"] == "Model download failed"
    assert notification["message"].endswith("Access denied (HTTP 401) fetching 'add-detail-xl.safetensors'")


async def test_a_cancelled_download_fails_the_row(core):
    core.add_download("dl-1", "cancelled")
    _insert()

    await Watcher().run_pass()

    assert (_row().status, _row().error) == ("failed", "The download was cancelled")


async def test_a_download_gone_from_the_queue_fails_the_row_unless_its_file_is_indexed(core):
    _insert(SHA)
    _insert(OTHER_SHA, download_id="dl-2")
    core.models_by_sha[OTHER_SHA] = model("model-2", OTHER_SHA)

    await Watcher().run_pass()

    assert (_row(SHA).status, _row(SHA).error) == ("failed", "The download is no longer on the download queue")
    assert (_row(OTHER_SHA).status, _row(OTHER_SHA).model_id) == ("enriched", "model-2")


async def test_a_row_that_never_got_a_download_id_fails_after_the_grace_passes(core, monkeypatch):
    monkeypatch.setattr(watcher_module, "UNQUEUED_GRACE_PASSES", 1)
    _insert(download_id=None)
    watcher = Watcher()

    await watcher.run_pass()
    assert _row().status == "queued"
    await watcher.run_pass()

    assert _row().status == "failed"
    assert "never put on the queue" in _row().error
    assert "get_download" not in core.names()


async def test_a_completed_download_that_never_shows_up_in_the_index_fails(core, monkeypatch):
    monkeypatch.setattr(watcher_module, "MAX_INDEX_LOOKUPS", 2)
    core.add_download("dl-1", "completed")
    _insert()
    watcher = Watcher()

    await _passes(watcher, 2)

    assert _row().status == "failed"
    assert "never showed up in the model index" in _row().error
    assert core.notifications[-1]["notification_type"] == "model-browser.download_failed"


# Finding the model by path and by hash -----------------------------------------------------


async def test_a_nohash_row_moves_to_the_hash_of_the_model_found_at_its_path(core):
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=HF_PATH)
    core.models_by_path[HF_PATH] = model("model-2", OTHER_SHA)
    _insert(key, source="huggingface")

    await Watcher().run_pass()

    assert _row(key) is None
    row = _row(OTHER_SHA)
    assert (row.status, row.model_id, row.download_id) == ("enriched", "model-2", "dl-1")
    assert core.names()[:2] == ["get_download", "find_model_by_path"]
    assert "find_model_by_sha256" not in core.names()
    assert core.calls_to("run_provider_fetch") == [("model-browser", ["model-2"])]


async def test_a_nohash_row_keeps_its_key_when_another_row_already_has_the_models_hash(core):
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=HF_PATH)
    core.models_by_path[HF_PATH] = model("model-2", OTHER_SHA)
    _insert(key, source="huggingface")
    _insert(OTHER_SHA, status="enriched", requested_by="user-2", model_id="model-2", download_id="dl-9")

    await Watcher().run_pass()

    row = _row(key)
    assert (row.status, row.model_id) == ("enriched", "model-2")
    assert _row(OTHER_SHA).requested_by == "user-2"
    assert core.calls_to("assign_to_user") == [("model-2", "user-1")]


async def test_a_model_found_by_path_but_indexed_before_the_download_is_not_taken(core):
    """For a path it has not indexed, the core answers the one model with the same file name."""
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=HF_PATH)
    core.models_by_path[HF_PATH] = model("someone-elses-model", OTHER_SHA, created="long_ago")
    _insert(key, source="huggingface")

    await Watcher().run_pass()

    assert _row(key).status == "queued"
    assert "assign_to_user" not in core.names()


async def test_a_nohash_file_identical_to_an_installed_model_is_found_by_hashing_it(core, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher_module, "HASH_FALLBACK_AFTER", 2)
    weights = tmp_path / "flux1-dev.safetensors"
    weights.write_bytes(b"the same weights as an installed model")
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    hashed = []
    monkeypatch.setattr(watcher_module, "sha256_of_file", lambda path: hashed.append(path) or sha256_of_file(path))
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=str(weights))
    core.models_by_sha[digest] = model("model-4", digest, created="long_ago")  # the indexer saw a duplicate
    _insert(key, source="huggingface")
    watcher = Watcher()

    await watcher.run_pass()
    assert _row(key).status == "queued" and hashed == []
    await watcher.run_pass()

    assert hashed == [str(weights)]
    assert _row(key) is None
    assert (_row(digest).status, _row(digest).model_id) == ("enriched", "model-4")


async def test_a_file_on_a_remote_backend_is_never_hashed(core, monkeypatch):
    monkeypatch.setattr(watcher_module, "HASH_FALLBACK_AFTER", 1)
    monkeypatch.setattr(watcher_module, "sha256_of_file", lambda path: pytest.fail("hashed a remote file"))
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=HF_PATH, destination_backend_id="worker-1")
    _insert(key, source="huggingface")

    await _passes(Watcher(), 2)

    assert _row(key).status == "queued"


async def test_a_hash_row_tries_the_path_after_some_lookups(core, monkeypatch):
    monkeypatch.setattr(watcher_module, "PATH_FALLBACK_AFTER", 2)
    path = "/app/models/loras/add-detail-xl.safetensors"
    core.add_download("dl-1", "completed", destination_path=path)
    core.models_by_path[path] = model("model-5", OTHER_SHA)  # the file did not match the expected hash
    _insert()
    watcher = Watcher()

    await watcher.run_pass()
    assert _row().status == "queued" and core.calls_to("find_model_by_path") == []
    await watcher.run_pass()

    assert core.calls_to("find_model_by_path") == [(path,)]
    assert _row(SHA) is None
    assert (_row(OTHER_SHA).status, _row(OTHER_SHA).model_id) == ("enriched", "model-5")


# Assignment -----------------------------------------------------------------------------


async def test_a_group_download_is_assigned_to_the_group(core):
    _insert(status="indexed", model_id="model-1", assign_to="group:artists")

    await Watcher().run_pass()

    assert core.calls_to("assign_to_group") == [("artists", ["model-1"])]
    assert "assign_to_user" not in core.names()
    assert _row().status == "enriched"
    assert core.notifications[0]["message"].endswith("it is now available to your group.")


async def test_a_group_that_no_longer_exists_falls_back_to_the_requester(core):
    core.assign_group_error = CoreBridgeError("not_found", "There is no user group with the id 'artists'")
    _insert(status="indexed", model_id="model-1", assign_to="group:artists")

    await Watcher().run_pass()

    row = _row()
    assert core.calls_to("assign_to_user") == [("model-1", "user-1")]
    assert (row.status, row.assign_to) == ("enriched", "user:user-1")
    assert "no longer exists" in row.error
    assert core.notifications[0]["notification_type"] == "model-browser.download_done"


async def test_a_refused_assignment_fails_the_row(core):
    core.assign_user_error = CoreBridgeError("refused", "Could not assign model 'model-1' to user 'user-1' - no such user")
    _insert(status="indexed", model_id="model-1")

    await Watcher().run_pass()

    row = _row()
    assert row.status == "failed"
    assert row.error == "The model was downloaded but could not be made visible: Could not assign model 'model-1' to user 'user-1' - no such user"
    assert "run_provider_fetch" not in core.names()
    assert core.notifications[0]["notification_type"] == "model-browser.download_failed"


async def test_an_admins_download_for_the_instance_is_assigned_to_nobody(core):
    _insert(status="indexed", model_id="model-1", assign_to="none", requested_by="admin-1")

    await Watcher().run_pass()

    assert "assign_to_user" not in core.names() and "assign_to_group" not in core.names()
    assert _row().status == "enriched"
    [notification] = core.notifications
    assert notification["user_id"] == "admin-1"
    assert notification["message"].endswith("it is now installed.")


# Enrichment -----------------------------------------------------------------------------


async def test_enrichment_failures_are_noted_and_the_row_still_ends_enriched(core):
    core.fetch_results["model-browser"] = {
        "successful": 0,
        "failed": 1,
        "errors": [{"model_id": "model-1", "reason": "Not found on Model-Browser"}],
    }
    core.attributes_error = CoreBridgeError("invalid", "'mb_license' is not a declared attribute for model type 'lora'")
    _insert(status="assigned", model_id="model-1")

    await Watcher().run_pass()

    row = _row()
    assert row.status == "enriched"
    assert row.error == (
        "model-browser: Not found on Model-Browser; "
        "attributes: 'mb_license' is not a declared attribute for model type 'lora'"
    )
    assert core.notifications[0]["notification_type"] == "model-browser.download_done"


async def test_a_provider_fetch_that_raises_is_noted_too(core):
    core.fetch_errors["model-browser"] = RuntimeError("model_index_manager.provider_info.run_provider_fetch moved")
    _insert(status="assigned", model_id="model-1")

    await Watcher().run_pass()

    assert _row().status == "enriched"
    assert _row().error == "model-browser: model_index_manager.provider_info.run_provider_fetch moved"
    assert core.calls_to("write_attributes") == [("model-1", ATTRIBUTES)]


async def test_a_note_from_the_assignment_is_kept_with_the_enrichment_notes(core):
    core.assign_group_error = CoreBridgeError("not_found", "gone")
    core.fetch_results["model-browser"] = {"successful": 0, "failed": 1}
    _insert(status="indexed", model_id="model-1", assign_to="group:artists")

    await Watcher().run_pass()

    assert _row().error.endswith("; model-browser: no information found")
    assert "no longer exists" in _row().error


async def test_nothing_is_written_when_the_info_has_no_attribute_value(core):
    info = _info()
    info["model"]["license"] = None
    info["model"]["versions"][0]["base_model"] = "  "
    _insert(status="assigned", model_id="model-1", info=info)

    await Watcher().run_pass()

    assert core.calls_to("write_attributes") == []
    assert _row().status == "enriched"


async def test_a_notification_that_cannot_be_sent_does_not_change_the_row(core, monkeypatch):
    def notify(**kwargs):
        raise RuntimeError("notifications are down")

    monkeypatch.setattr(core_bridge, "notify", notify)
    _insert(status="assigned", model_id="model-1")

    await Watcher().run_pass()

    assert _row().status == "enriched"


# Errors ---------------------------------------------------------------------------------


async def test_one_rows_error_does_not_stop_the_others_and_a_row_that_keeps_failing_is_given_up(
    core, plugin_db, monkeypatch, caplog
):
    monkeypatch.setattr(watcher_module, "MAX_ROW_ERRORS", 2)
    real_get_download = core.get_download

    def get_download(download_id):
        if download_id == "dl-bad":
            raise RuntimeError("database is locked")
        return real_get_download(download_id)

    monkeypatch.setattr(core_bridge, "get_download", get_download)
    _insert("c" * 64, download_id="dl-bad")
    _insert(SHA, download_id="dl-1")
    with plugin_db.get_cursor() as cursor:  # the failing row comes first
        cursor.execute(f"UPDATE {pending.TABLE} SET created_at = '2026-10-11 09:00:00' WHERE sha256 = ?", ("c" * 64,))
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    watcher = Watcher()

    await watcher.run_pass()

    assert _row("c" * 64).status == "queued"
    assert _row(SHA).status == "enriched"
    assert caplog.text.count("Could not move") == 1

    await watcher.run_pass()

    assert _row("c" * 64).status == "failed"
    assert _row("c" * 64).error == "Stopped following this download after repeated errors: database is locked"
    assert caplog.text.count("Could not move") == 1  # logged in full once


# Requests linked to a row ---------------------------------------------------------------

LABEL = "Detail Tweaker XL (add-detail-xl.safetensors)"


def _approved_request(user_id, *, sha256=SHA, assign_to="user", decided_by="admin-1"):
    """An approved request of `user_id` linked to the row `sha256`; `assign_to="user"` means `user:<user_id>`."""
    created = requests.create(
        user_id=user_id,
        source="civitai",
        source_model_id="122359",
        source_version_id="135867",
        file_id="1001",
        snapshot={"name": "Detail Tweaker XL", "file_name": "add-detail-xl.safetensors"},
    )
    return requests.set_status(
        created.id,
        "approved",
        decided_by=decided_by,
        sha256=sha256,
        assign_to=f"user:{user_id}" if assign_to == "user" else assign_to,
    )


def _status(request):
    return requests.get(request.id).status


def _sent(core, kind):
    return [(n["user_id"], n["message"]) for n in core.notifications if n["notification_type"] == kind]


async def test_other_approved_requesters_are_assigned_with_the_row_and_closed_when_the_model_is_ready(core):
    core.add_user("admin-1", admin=True)
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    _insert(requested_by="user-2", assign_to="user:user-2")  # someone else's download
    first = _approved_request("user-1")
    grouped = _approved_request("user-3", assign_to="group:artists")

    await Watcher().run_pass()

    assert _row().status == "enriched"
    assert core.calls_to("assign_to_user") == [("model-1", "user-2"), ("model-1", "user-1")]
    assert core.calls_to("assign_to_group") == [("artists", ["model-1"])]
    assert core.group_admins == ["admin-1"]  # in the name of the admin who approved
    names = core.names()
    assert names.index("assign_to_group") < names.index("run_provider_fetch")  # at the assignment step
    assert (_status(first), _status(grouped)) == ("done", "done")
    assert _sent(core, "model-browser.download_done") == [
        ("user-2", f"{LABEL}: it is now in your models."),
        ("user-1", f"{LABEL}: it is now in your models."),
        ("user-3", f"{LABEL}: it is now available to your group."),
    ]
    assert core.notifications[1]["metadata"]["request_id"] == first.id
    assert core.notifications[1]["metadata"]["model_id"] == "model-1"


async def test_the_rows_own_request_is_done_and_its_requester_notified_once(core):
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    own = _approved_request("user-1")
    _insert(request_id=own.id)

    await Watcher().run_pass()

    assert _status(own) == "done"
    assert core.calls_to("assign_to_user") == [("model-1", "user-1")]
    assert [n["user_id"] for n in core.notifications] == ["user-1"]


async def test_another_request_of_the_rows_own_requester_is_closed_without_a_second_notification(core):
    _insert(status="assigned", model_id="model-1")  # user-1's own direct download
    duplicate = _approved_request("user-1")

    await Watcher().run_pass()

    assert _status(duplicate) == "done"
    assert [n["user_id"] for n in core.notifications] == ["user-1"]


@pytest.mark.parametrize(
    "decided_by, admin_id",
    [("admin-1", "admin-1"), ("approver-1", None), ("gone", None)],
    ids=["admin", "non-admin-approver", "approver-gone"],
)
async def test_a_group_picked_at_approval_is_assigned_in_the_approving_admins_name(core, decided_by, admin_id):
    core.add_user("admin-1", admin=True)
    core.add_user("approver-1")
    own = _approved_request("user-1", assign_to="group:artists", decided_by=decided_by)
    _insert(status="indexed", model_id="model-1", assign_to="group:artists", request_id=own.id)

    await Watcher().run_pass()

    assert core.calls_to("assign_to_group") == [("artists", ["model-1"])]
    assert core.group_admins == [admin_id]
    assert _status(own) == "done"


async def test_a_direct_group_download_has_no_acting_admin(core):
    core.add_user("admin-1", admin=True)
    _insert(status="indexed", model_id="model-1", assign_to="group:artists")

    await Watcher().run_pass()

    assert core.group_admins == [None]


async def test_a_request_approved_after_the_assignment_step_is_assigned_when_the_model_is_ready(core):
    _insert(status="assigned", model_id="model-1", requested_by="user-2", assign_to="user:user-2")
    created = requests.create(
        user_id="user-1", source="civitai", source_model_id="122359", source_version_id="135867", file_id="1001",
        snapshot={},
    )
    late = requests.set_status(created.id, "approved", decided_by="admin-1", sha256=SHA)  # no assign_to: the requester

    await Watcher().run_pass()

    assert core.calls_to("assign_to_user") == [("model-1", "user-1")]
    assert _status(late) == "done"


async def test_a_requester_who_cannot_be_assigned_gets_a_failed_request(core, monkeypatch):
    real_assign = core.assign_to_user

    def assign_to_user(model_id, user_id):
        if user_id == "user-1":
            raise CoreBridgeError("refused", "Could not assign model 'model-1' to user 'user-1' - no such user")
        return real_assign(model_id, user_id)

    monkeypatch.setattr(core_bridge, "assign_to_user", assign_to_user)
    core.add_download("dl-1", "completed")
    core.models_by_sha[SHA] = model("model-1")
    _insert(requested_by="user-2", assign_to="user:user-2")
    request = _approved_request("user-1")

    await Watcher().run_pass()

    assert _row().status == "enriched"
    assert _status(request) == "failed"
    assert _sent(core, "model-browser.download_failed") == [
        ("user-1", f"{LABEL}: The model was downloaded but could not be made visible to you"),
    ]


async def test_a_group_gone_since_the_approval_falls_back_to_the_requester(core):
    core.assign_group_error = CoreBridgeError("not_found", "There is no user group with the id 'artists'")
    _insert(status="assigned", model_id="model-1", requested_by="user-2", assign_to="user:user-2")
    request = _approved_request("user-1", assign_to="group:artists")

    await Watcher().run_pass()

    assert core.calls_to("assign_to_user") == [("model-1", "user-1")]
    closed = requests.get(request.id)
    assert (closed.status, closed.assign_to) == ("done", "user:user-1")
    assert _sent(core, "model-browser.download_done")[-1] == ("user-1", f"{LABEL}: it is now in your models.")


async def test_the_rows_own_request_records_where_the_model_went(core):
    core.assign_group_error = CoreBridgeError("not_found", "There is no user group with the id 'artists'")
    own = _approved_request("user-1", assign_to="group:artists")
    _insert(status="indexed", model_id="model-1", assign_to="group:artists", request_id=own.id)

    await Watcher().run_pass()

    assert (_row().assign_to, requests.get(own.id).assign_to) == ("user:user-1", "user:user-1")


async def test_a_failed_download_fails_its_requests_refunds_the_quota_and_tells_every_requester(core):
    core.add_download("dl-1", "failed", error_message="Access denied (HTTP 401)")
    own = _approved_request("user-1")
    other = _approved_request("user-2")
    _insert(request_id=own.id, limit_ref_id="model-browser:ref-1")

    await Watcher().run_pass()

    assert _row().status == "failed"
    assert core.refunds == ["model-browser:ref-1"]
    assert (_status(own), _status(other)) == ("failed", "failed")
    assert _sent(core, "model-browser.download_failed") == [
        ("user-1", f"{LABEL}: Access denied (HTTP 401)"),
        ("user-2", f"{LABEL}: Access denied (HTTP 401)"),
    ]
    assert "assign_to_user" not in core.names()


@pytest.mark.parametrize("ending", ["cancelled", "gone-from-the-queue", "never-queued", "never-indexed"])
async def test_a_download_that_ends_without_a_model_refunds_its_quota(core, monkeypatch, ending):
    monkeypatch.setattr(watcher_module, "UNQUEUED_GRACE_PASSES", 0)
    monkeypatch.setattr(watcher_module, "MAX_INDEX_LOOKUPS", 1)
    if ending == "cancelled":
        core.add_download("dl-1", "cancelled")
    elif ending == "never-indexed":
        core.add_download("dl-1", "completed")
    _insert(limit_ref_id="model-browser:ref-1", download_id=None if ending == "never-queued" else "dl-1")

    await Watcher().run_pass()

    assert _row().status == "failed"
    assert core.refunds == ["model-browser:ref-1"]


async def test_a_download_that_succeeds_or_fails_without_a_ref_refunds_nothing(core):
    core.add_download("dl-1", "completed")
    core.add_download("dl-2", "failed", error_message="HTTP 500")
    core.models_by_sha[SHA] = model("model-1")
    _insert(SHA, limit_ref_id="model-browser:ref-1")
    _insert(OTHER_SHA, download_id="dl-2")

    await Watcher().run_pass()

    assert (_row(SHA).status, _row(OTHER_SHA).status) == ("enriched", "failed")
    assert core.refunds == []


async def test_a_nohash_row_moved_to_its_models_hash_takes_its_requests_along(core):
    key = NOHASH_PREFIX + HF_URL
    core.add_download("dl-1", "completed", destination_path=HF_PATH)
    core.models_by_path[HF_PATH] = model("model-2", OTHER_SHA)
    own = _approved_request("user-1", sha256=key)
    other = _approved_request("user-2", sha256=key)
    _insert(key, source="huggingface", request_id=own.id)

    await Watcher().run_pass()

    assert _row(OTHER_SHA).status == "enriched"
    assert requests.get(own.id).sha256 == OTHER_SHA
    assert (_status(own), _status(other)) == ("done", "done")
    assert core.calls_to("assign_to_user") == [("model-2", "user-1"), ("model-2", "user-2")]


async def test_the_reconciliation_closes_the_requests_of_rows_that_ended_meanwhile(core):
    _insert(SHA, status="enriched", model_id="model-1", requested_by="user-2", download_id="dl-1")
    _insert(OTHER_SHA, status="failed", error="HTTP 500", requested_by="user-2", download_id="dl-2")
    done = _approved_request("user-1")
    failed = _approved_request("user-3", sha256=OTHER_SHA)
    unlinked = _approved_request("user-4", sha256=None)
    watcher = Watcher()

    await watcher.run_pass()
    assert (_status(done), _status(failed)) == ("approved", "approved")  # only a reconciliation looks

    await watcher.run_pass(reconcile=True)

    assert (_status(done), _status(failed), _status(unlinked)) == ("done", "failed", "approved")
    assert core.calls_to("assign_to_user") == [("model-1", "user-1")]
    assert sorted((n["user_id"], n["notification_type"]) for n in core.notifications) == [
        ("user-1", "model-browser.download_done"),
        ("user-3", "model-browser.download_failed"),
    ]


async def test_requests_that_cannot_be_read_never_stop_a_row(core, monkeypatch, caplog):
    def broken(sha256):
        raise RuntimeError("no such table: model_browser_requests")

    monkeypatch.setattr(requests, "list_approved_for_sha256", broken)
    _insert(status="indexed", model_id="model-1")

    await Watcher().run_pass()

    assert _row().status == "enriched"
    assert "Could not read the requests waiting for" in caplog.text


# Helpers --------------------------------------------------------------------------------


def test_model_attributes_come_from_the_chosen_version_and_the_license():
    info = _info()
    assert model_attributes(info) == ATTRIBUTES

    info["model"]["versions"].insert(0, dict(info["model"]["versions"][0], id="other", base_model="SD 1.5"))
    assert model_attributes(info)["mb_base_model"] == "SDXL 1.0"  # picked by version id
    info["version_id"] = "missing"
    assert model_attributes(info)["mb_base_model"] == "SD 1.5"  # else the first version
    assert model_attributes({}) == {}
    assert model_attributes({"model": {"versions": ["junk"], "license": "MIT"}}) == {}


def test_indexed_since_compares_the_models_first_index_with_the_rows_creation():
    row = PendingRow(
        sha256=SHA, source="civitai", source_model_id="1", file_name="x", requested_by="u", assign_to="none",
        created_at="2026-10-11 10:00:00",
    )

    assert indexed_since({"created_at": "2026-10-11T10:00:00+00:00"}, row)
    assert indexed_since({"created_at": "2026-10-11T12:30:00+02:00"}, row)
    assert not indexed_since({"created_at": "2026-10-11T09:59:59+00:00"}, row)
    assert not indexed_since({"created_at": None}, row)
    assert not indexed_since({"created_at": "yesterday"}, row)


def test_sha256_of_file_is_none_for_a_file_that_cannot_be_read(tmp_path):
    assert sha256_of_file(str(tmp_path / "missing.safetensors")) is None
    present = tmp_path / "x.bin"
    present.write_bytes(b"abc")
    assert sha256_of_file(str(present)) == hashlib.sha256(b"abc").hexdigest()
