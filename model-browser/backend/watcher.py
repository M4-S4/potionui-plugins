"""Following the plugin's downloads to an assigned, enriched model (PLAN.md §3, §7.4).

Each file the plugin downloads has a row in `model_browser_pending` (`backend/pending.py`),
moved on step by step:

- `queued`: the core download. Normally the `download.after_complete` hook ends this step
  (`hooks/download_hooks.py`): the core fires it once the file has landed and been indexed,
  and the handler records the model (`record_indexed`), then hands the rest over to the
  application loop (`schedule_step`, `carry_on`). Otherwise the sweep (below) follows the
  core download (`core_bridge.get_download`): `pending`, `downloading`, `paused`: wait.
  `failed`, `cancelled`, or the record gone (unless the file is indexed already): `failed`.
  `completed`: find the indexed model (below), then `indexed`. A row that never got a
  download id (the server stopped while queuing it) fails after `UNQUEUED_GRACE_PASSES`
  passes.
- `indexed`: assign per `assign_to`: `user:<id>` to that user, `group:<id>` to the group,
  `none` to nobody (an admin's download, every admin sees every model). A group is assigned
  through the core's group operation, in the name of an admin (`permissions.acting_admin`:
  the requester, else the approver of the request the row comes from, else the admin who
  last saved the group's permissions); without one, or when the group is gone, the model
  is assigned to the requester instead, with a note. Then `assigned`; a refusal from the
  core is `failed`. The other approved requests for the same file
  (`requests.list_approved_for_sha256`: users who asked for it while it was on its way for
  someone else) are assigned at the same step, each to its own `assign_to`, the same way.
- `assigned`: enrich: the `model-browser` provider fetch (`provider/pending_provider.py`,
  which answers from this row: description, trigger words, tags, safe previews, the source
  page as the model's mirror), then the `mb_base_model` / `mb_license` attributes from the
  row's `info`. Then `enriched`: a step that failed is noted in `error`, the row still ends
  `enriched` (the model is downloaded and visible). The core's own `civitai` provider is
  never asked: it hands every image of the version to the core as previews, NSFW ones
  included, and previews are shown to everyone the model is assigned to.
When a row ends, its requester is notified (`model-browser.download_done` or
`model-browser.download_failed`), and the approved requests linked to it (its own
`request_id`, and every approved request with its `sha256`) are closed: `done` (a requester
approved after the assignment step is assigned then), or `failed`; each of their requesters
is notified too, once. A failed row refunds its quota events (`limits.refund(limit_ref_id)`),
whatever the cause: the user got no model.

The hook handler, the steps it schedules and the sweep may reach the same row at once: each
status change is made only from the status it moves on from (`pending.update(...,
only_from=...)`). A step that finds the row moved on stops there, and only the step that
ended a row notifies, refunds and closes its requests.

The sweep (`Watcher`) is the plugin's background task on PotionUI's event loop: every
`POLL_INTERVAL_SECONDS` it goes over the unfinished rows and moves each on as far as it can
go. It covers what the hook does not: failed and cancelled downloads (the core fires no hook
for them), records that vanished, downloads sent to a remote backend (the hook carries no
model id for them), completions missed while the plugin was disabled or whose handler did
not finish, rows a restart left `indexed` or `assigned`, rows that never got a download id.

Finding the model once the download is `completed`, in the sweep: the worker marks a
download completed *before* indexing it, so the lookup is retried on each pass:
- a row keyed by SHA256 looks the hash up (`find_model_by_sha256`); a file identical to a
  model already indexed (`duplicate_of`) is found the same way. After
  `PATH_FALLBACK_AFTER` lookups, the download's `destination_path` is tried as well
  (`find_model_by_path`), for a file whose content did not match the expected hash;
- a `nohash:` row looks the path up, and moves to the model's real hash (`pending.rekey`)
  once found. After `HASH_FALLBACK_AFTER` lookups, the downloaded file (local
  destinations only) is hashed once, and the hash looked up: this finds the model when
  the file was the duplicate of one already indexed, which the indexer leaves unindexed.
A model found by path only counts when it was indexed after the row was written: for an
unknown path, the core answers the one model with the same file name, which may be
another file. After `MAX_INDEX_LOOKUPS` lookups (about 30 minutes) the row fails.

The first pass after a start is the reconciliation (PLAN.md §7.4 step 8): rows left
unfinished by a restart are simply taken up where they were, and approved requests whose
row ended while the server was stopping are closed. One row's error never stops the pass:
it is logged and retried on the next pass, and a row that fails `MAX_ROW_ERRORS` passes in
a row is given up (`failed`).

`plugin.lifecycle.ready` starts the sweep with `run_on_app_loop(watcher.run())`;
`plugin.lifecycle.disable` stops it.
"""

import asyncio
import concurrent.futures
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Coroutine, Dict, Iterable, List, Mapping, Optional, Tuple

from src.plugin_api import User

from . import PLUGIN_ID, core_bridge, limits, notifications, pending, permissions, requests
from .core_bridge import CoreBridgeError
from .pending import PendingRow
from .requests import Request

logger = logging.getLogger("plugins.model-browser")

#: Seconds between two passes of the sweep over the plugin's pending downloads.
POLL_INTERVAL_SECONDS = 60
#: Lookups by hash, after `completed`, before the download's path is tried as well (the
#: second lookup, a pass after the first: ~1 min).
PATH_FALLBACK_AFTER = 2
#: Lookups by path of a `nohash:` row before the downloaded file is hashed (~5 min: the
#: indexer, which hashes it too, has normally indexed a new file by then).
HASH_FALLBACK_AFTER = 6
#: Lookups after which a completed download that never showed up in the index fails (~30 min).
MAX_INDEX_LOOKUPS = 30
#: Passes a `queued` row may spend without a download id (being queued) before it fails (~5 min).
UNQUEUED_GRACE_PASSES = 5
#: Passes in a row one row may raise on before it is given up (~10 min).
MAX_ROW_ERRORS = 10
#: Longest `error` stored on a row.
MAX_ERROR_LENGTH = 2000

#: Core download statuses that mean "not finished yet".
WAITING_STATUSES = frozenset({"pending", "downloading", "paused"})
#: Row statuses `finish` takes a row on from: its model is known.
FINISHING_STATUSES = ("indexed", "assigned")

#: The plugin's own provider (`provider/pending_provider.py`), which answers from the pending rows.
PENDING_PROVIDER_ID = PLUGIN_ID
NOTIFY_DOWNLOAD_DONE = notifications.DOWNLOAD_DONE
NOTIFY_DOWNLOAD_FAILED = notifications.DOWNLOAD_FAILED
#: Why a requester whose request was linked to a finished download did not get its model.
NOT_ASSIGNED_TO_REQUESTER = "The model was downloaded but could not be made visible to you"

_HASH_CHUNK_BYTES = 8 * 1024 * 1024


def model_attributes(info: Mapping[str, Any]) -> Dict[str, str]:
    """The `mb_base_model` and `mb_license` attribute values a row's `info` gives, empty ones left out."""
    model = info.get("model") if isinstance(info.get("model"), Mapping) else {}
    versions = [version for version in model.get("versions") or [] if isinstance(version, Mapping)]
    version = next((version for version in versions if str(version.get("id")) == str(info.get("version_id"))), None)
    if version is None:
        version = versions[0] if versions else {}
    license_ = model.get("license") if isinstance(model.get("license"), Mapping) else {}
    values = {"mb_base_model": version.get("base_model"), "mb_license": license_.get("summary")}
    return {key: value.strip() for key, value in values.items() if isinstance(value, str) and value.strip()}


def _timestamp(value: Any) -> Optional[datetime]:
    """A stored timestamp as an aware UTC datetime (SQLite's `CURRENT_TIMESTAMP` text, or the core's ISO strings)."""
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def indexed_since(model: Mapping[str, Any], row: PendingRow) -> bool:
    """Whether `model` was first indexed after `row` was written: a model found by path is ours only then."""
    created, written = _timestamp(model.get("created_at")), _timestamp(row.created_at)
    return created is not None and written is not None and created >= written


def sha256_of_file(path: str) -> Optional[str]:
    """The SHA256 of a local file, or None when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _label(row: PendingRow) -> str:
    model = row.info.get("model") if isinstance(row.info.get("model"), Mapping) else {}
    name = model.get("name")
    if isinstance(name, str) and name.strip() and name.strip() != row.file_name:
        return f"{name.strip()} ({row.file_name})"
    return row.file_name


def _where(assign_to: str) -> str:
    """Where a finished download put the model, for the notification of a user it was assigned to as `assign_to`."""
    if assign_to.startswith("group:"):
        return "it is now available to your group"
    if assign_to == "none":
        return "it is now installed"
    return "it is now in your models"


def _metadata(row: PendingRow) -> Dict[str, Any]:
    """What a download notification carries."""
    return {
        "source": row.source,
        "source_model_id": row.source_model_id,
        "source_version_id": row.source_version_id,
        "sha256": None if row.nohash else row.sha256,
        "model_id": row.model_id,
        "download_id": row.download_id,
    }


# Handing a row over to the application loop ---------------------------------------------


def schedule_step(step: Coroutine[Any, Any, Any], key: str) -> bool:
    """Run `step`, a step of the row `key` (`carry_on(key)`, `fail(...)`), on the application
    loop without waiting for it: how the `download.after_complete` handler and a file found
    installed hand a row over. An error in the step is logged and left to the sweep.

    Returns False, logged, when there is no loop to run it on (`run_on_app_loop` raises before
    the application has started): the sweep takes the row up instead. Never raises.
    """
    try:
        from src.plugin_api.hooks import run_on_app_loop

        future = run_on_app_loop(step)
    except Exception as exc:
        step.close()
        logger.warning(
            "[MODEL-BROWSER] Could not hand %s over to the application loop (%s); the sweep will take it up", key, exc
        )
        return False
    future.add_done_callback(lambda done: _log_step_error(done, key))
    return True


def _log_step_error(future: concurrent.futures.Future, key: str) -> None:
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error("[MODEL-BROWSER] Could not move %s on; the sweep will retry", key, exc_info=error)


async def carry_on(key: str) -> Optional[PendingRow]:
    """Take the row `key`, read afresh, from `indexed` or `assigned` to its end (`finish`); a row
    in another status is left as it is. Returns the row as stored (None when it is gone)."""
    row = await asyncio.to_thread(pending.get, key)
    if row is None or row.status not in FINISHING_STATUSES:
        return row
    return await finish(row)


async def finish(row: PendingRow) -> Optional[PendingRow]:
    """`indexed` -> `assigned` -> `enriched`, as far as `row` goes now. The requests the
    assignment step assigns are carried on to the settlement at the end of this chain.

    Returns the row as stored; None when it is gone or another step moved it on first.
    """
    assigned: Dict[str, str] = {}
    if row.status == "indexed":
        row, assigned = await assign(row)
    if row is not None and row.status == "assigned":
        row = await enrich(row, assigned)
    return row


# queued -> indexed --------------------------------------------------------------------------


def record_indexed(row: PendingRow, model: Mapping[str, Any]) -> Optional[PendingRow]:
    """Record the model found for the `queued` row `row`: `indexed`, with the model's id, under
    the model's real hash (`model["sha256"]`, when known) when the row had another key.

    Synchronous: the hook handler calls it on its thread, the sweep through `asyncio.to_thread`.
    Returns the row as stored: the row it merged into when one with that hash was written
    meanwhile, None when it is gone or was no longer `queued` (another step recorded it first).
    """
    key = row.sha256
    model_sha = str(model.get("sha256") or "").strip().lower()
    if model_sha and model_sha != key:
        if pending.get(model_sha) is None:
            moved = pending.rekey(key, model_sha)
            # The requests linked to the old key follow the row (or the row it merged into).
            requests.relink(key, model_sha)
            if moved is None or moved.download_id != row.download_id:
                logger.warning("[MODEL-BROWSER] %s merged into the row of %s meanwhile", key, model_sha)
                return moved
            key = model_sha
        else:
            # The same file is on its way under its hash too: that row describes it to the
            # providers, this one keeps its own key and still gets its model assigned.
            logger.info("[MODEL-BROWSER] %s is the model of another row (%s); keeping its key", key, model_sha)
    updated = pending.update(key, only_from=("queued",), model_id=model.get("id"), status="indexed", error=None)
    if updated is None:
        logger.info("[MODEL-BROWSER] %s was no longer queued: model %s not recorded again", row.file_name, model.get("id"))
        return None
    logger.info("[MODEL-BROWSER] %s indexed as model %s", row.file_name, model.get("id"))
    return updated


# indexed -> assigned ------------------------------------------------------------------------


async def assign(row: PendingRow) -> Tuple[Optional[PendingRow], Dict[str, str]]:
    """`indexed` -> `assigned`: make the model visible per `assign_to`, then to the requesters of
    the other approved requests linked to the row.

    Returns the row as stored (None when it is gone or another step assigned it first) and the
    requests assigned, as `{request id: where the model went}`. A refusal from the core fails
    the row.
    """
    if not row.model_id:
        return await fail(row, "No model to assign"), {}
    kind, _, target = row.assign_to.partition(":")
    assign_to, note = row.assign_to, None
    try:
        if row.assign_to == "none":
            pass  # an admin's download: admins see every model
        elif kind == "group" and target:
            admin = await asyncio.to_thread(_acting_admin, row, target)
            if admin is None:
                note = f"No admin could act for the group '{target}': the model was assigned to its requester instead"
            else:
                try:
                    await asyncio.to_thread(core_bridge.assign_to_group, target, [row.model_id], admin)
                except CoreBridgeError as exc:
                    if exc.code != "not_found":
                        raise
                    note = f"The group '{target}' no longer exists: the model was assigned to its requester instead"
            if note is not None:
                logger.warning("[MODEL-BROWSER] %s", note)
                await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, row.requested_by)
                assign_to = f"user:{row.requested_by}"
        else:
            user_id = target if kind == "user" and target else row.requested_by
            if kind != "user":
                logger.warning("[MODEL-BROWSER] Unknown assign_to %r on %s: assigning to the requester", row.assign_to, row.sha256)
            await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, user_id)
            assign_to = f"user:{user_id}"
    except CoreBridgeError as exc:
        return await fail(row, f"The model was downloaded but could not be made visible: {exc.message}"), {}
    fields: Dict[str, Any] = {"status": "assigned", "error": note}
    if assign_to != row.assign_to:
        fields["assign_to"] = assign_to
    updated = await asyncio.to_thread(pending.update, row.sha256, only_from=("indexed",), **fields)
    if updated is None:
        logger.info("[MODEL-BROWSER] %s was no longer indexed: left to the step that moved it on", row.file_name)
        return None, {}
    return updated, await _assign_requests(updated)


def _acting_admin(row: PendingRow, group_id: str) -> Optional[User]:
    """The admin in whose name `row`'s model is assigned to `group_id`: `permissions.acting_admin`
    of its requester and of the approver of the request it comes from, if any."""
    request = requests.get(row.request_id) if row.request_id else None
    return permissions.acting_admin(row.requested_by, request.decided_by if request is not None else None, group_id)


# Requests linked to a row -------------------------------------------------------------------


def _linked_requests(row: PendingRow) -> List[Request]:
    """The approved requests waiting for `row`: its own (`request_id`) and every one linked by `sha256`."""
    linked = {request.id: request for request in requests.list_approved_for_sha256(row.sha256)}
    if row.request_id and row.request_id not in linked:
        own = requests.get(row.request_id)
        if own is not None and own.status == requests.APPROVED:
            linked[own.id] = own
    return list(linked.values())


async def _assign_requests(row: PendingRow) -> Dict[str, str]:
    """Assign `row`'s model to the requesters of the other approved requests linked to it;
    returns where it went for each, `{request id: assign_to}`, refusals left out. Never raises."""
    assigned: Dict[str, str] = {}
    try:
        linked = await asyncio.to_thread(_linked_requests, row)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not read the requests waiting for %s", row.sha256, exc_info=True)
        return assigned
    for request in linked:
        if request.id == row.request_id:
            continue
        target = await _assign_request(row, request)
        if target is not None:
            assigned[request.id] = target
    return assigned


async def _assign_request(row: PendingRow, request: Request) -> Optional[str]:
    """Make `row`'s model visible as `request.assign_to` says (to its requester by default);
    returns where it went (`user:<id>`, `group:<id>`, `none`), None when the core refused.
    Never raises.

    A group is assigned in the name of an admin (`permissions.acting_admin` of the requester
    and the approver), through the core's group operation and its hooks; without one, or when
    the group no longer exists, the model goes to the requester.
    """
    target = request.assign_to or f"user:{request.user_id}"
    kind, _, target_id = target.partition(":")
    try:
        if target == "none":
            return target  # an admin's request: admins see every model
        if kind == "group" and target_id:
            admin = await asyncio.to_thread(permissions.acting_admin, request.user_id, request.decided_by, target_id)
            if admin is None:
                logger.warning(
                    "[MODEL-BROWSER] No admin could act for the group '%s' of request %s: assigning its requester",
                    target_id,
                    request.id,
                )
            else:
                try:
                    await asyncio.to_thread(core_bridge.assign_to_group, target_id, [row.model_id], admin)
                    return target
                except CoreBridgeError as exc:
                    if exc.code != "not_found":
                        raise
                    logger.warning(
                        "[MODEL-BROWSER] The group '%s' of request %s no longer exists: assigning its requester",
                        target_id,
                        request.id,
                    )
            await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, request.user_id)
            return f"user:{request.user_id}"
        user_id = target_id if kind == "user" and target_id else request.user_id
        await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, user_id)
        return f"user:{user_id}"
    except Exception as exc:
        message = exc.message if isinstance(exc, CoreBridgeError) else str(exc)
        logger.warning("[MODEL-BROWSER] Could not assign model %s for request %s: %s", row.model_id, request.id, message)
        return None


async def settle_requests(row: PendingRow, *, done: bool, assigned: Optional[Mapping[str, str]] = None) -> None:
    """Close the approved requests linked to `row`, which just ended: `done` with where the
    model went (`assigned`: what the assignment step of this chain assigned; any other request
    is assigned now), or `failed`. Each of their requesters is notified, but the row's own, who
    already was. Never raises."""
    try:
        linked = await asyncio.to_thread(_linked_requests, row)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not read the requests waiting for %s", row.sha256, exc_info=True)
        return
    assigned = assigned or {}
    for request in linked:
        target: Optional[str] = None
        if done:
            if request.id == row.request_id:
                target = row.assign_to
            elif request.id in assigned:
                target = assigned[request.id]
            else:
                target = await _assign_request(row, request)
        status = requests.DONE if target is not None else requests.FAILED
        try:
            closed = await asyncio.to_thread(
                lambda: requests.set_status(request.id, status, assign_to=target, only_from=(requests.APPROVED,))
            )
        except Exception:
            logger.warning("[MODEL-BROWSER] Could not close request %s", request.id, exc_info=True)
            continue
        if closed is None:
            continue  # closed meanwhile
        logger.info("[MODEL-BROWSER] Request %s %s", closed.id, status)
        if closed.user_id != row.requested_by:
            await _notify_requester(row, closed, served=target is not None)


async def _notify_requester(row: PendingRow, request: Request, *, served: bool) -> None:
    metadata = {**_metadata(row), "request_id": request.id}
    if served:
        where = _where(request.assign_to or f"user:{request.user_id}")
        await asyncio.to_thread(notifications.download_done, request.user_id, _label(row), where, metadata)
    else:
        reason = NOT_ASSIGNED_TO_REQUESTER if row.status == "enriched" else row.error
        await asyncio.to_thread(notifications.download_failed, request.user_id, _label(row), reason, metadata)


# assigned -> enriched -----------------------------------------------------------------------


async def enrich(row: PendingRow, assigned: Optional[Mapping[str, str]] = None) -> Optional[PendingRow]:
    """`assigned` -> `enriched`: the provider fetch and the attributes, then the requester is
    notified and the linked requests closed (`assigned`: see `settle_requests`).

    Returns the row as stored; None, with nobody notified, when it is gone or another step
    ended it first.
    """
    notes: List[str] = [row.error] if row.error else []
    notes += await _fetch(PENDING_PROVIDER_ID, row.model_id)
    attributes = model_attributes(row.info)
    if attributes:
        try:
            await asyncio.to_thread(core_bridge.write_attributes, row.model_id, attributes)
        except Exception as exc:
            message = exc.message if isinstance(exc, CoreBridgeError) else str(exc)
            logger.warning("[MODEL-BROWSER] Could not write the attributes of model %s: %s", row.model_id, message)
            notes.append(f"attributes: {message}")
    error = "; ".join(notes)[:MAX_ERROR_LENGTH] or None
    updated = await asyncio.to_thread(pending.update, row.sha256, only_from=("assigned",), status="enriched", error=error)
    if updated is None:
        logger.info("[MODEL-BROWSER] %s was no longer assigned: left to the step that ended it", row.file_name)
        return None
    logger.info("[MODEL-BROWSER] %s ready (model %s)%s", row.file_name, row.model_id, f": {error}" if error else "")
    await _notify(updated, done=True)
    await settle_requests(updated, done=True, assigned=assigned)
    return updated


async def _fetch(provider: str, model_id: Optional[str]) -> List[str]:
    """One provider fetch for the model; the reasons it failed, if it did."""
    try:
        summary = await core_bridge.run_provider_fetch(provider, [model_id] if model_id else [])
    except Exception as exc:
        logger.warning("[MODEL-BROWSER] The %s fetch for model %s failed: %s", provider, model_id, exc)
        return [f"{provider}: {exc}"]
    if summary.get("successful"):
        return []
    reasons = [
        str(error.get("reason"))
        for error in summary.get("errors") or []
        if isinstance(error, Mapping) and error.get("reason")
    ]
    if reasons:
        return [f"{provider}: {reason}" for reason in reasons]
    return [f"{provider}: no information found"] if summary.get("failed") else []


# Endings ------------------------------------------------------------------------------------


async def fail(row: PendingRow, message: str) -> Optional[PendingRow]:
    """End `row` as `failed` with `message`: its quota events are refunded, its requester is
    notified and its linked requests are closed `failed`.

    Returns the row as stored; None, with nothing else done, when it is gone or had ended
    already (another step ended it first).
    """
    updated = await asyncio.to_thread(
        pending.update, row.sha256, only_from=pending.UNFINISHED, status="failed", error=message[:MAX_ERROR_LENGTH]
    )
    if updated is None:
        logger.info("[MODEL-BROWSER] %s had ended already, not failing it: %s", row.file_name, message)
        return None
    logger.warning("[MODEL-BROWSER] %s failed: %s", row.file_name, message)
    if updated.limit_ref_id:
        refunded = await asyncio.to_thread(limits.refund, updated.limit_ref_id)
        if refunded:
            logger.info("[MODEL-BROWSER] Refunded %d quota event(s) of %s", refunded, row.file_name)
    await _notify(updated, done=False)
    await settle_requests(updated, done=False)
    return updated


async def _notify(row: PendingRow, *, done: bool) -> None:
    """Tell the row's requester how it ended (`notifications.download_done` / `download_failed`)."""
    if done:
        await asyncio.to_thread(
            notifications.download_done, row.requested_by, _label(row), _where(row.assign_to), _metadata(row)
        )
    else:
        await asyncio.to_thread(notifications.download_failed, row.requested_by, _label(row), row.error, _metadata(row))


# The sweep ----------------------------------------------------------------------------------


class Watcher:
    """One run of the sweep: `run()` is awaited on the app loop, once.

    `request_stop()` may be called from any thread, before or during the run. The sweep's
    retry counters live in memory: a restart gives every row a fresh budget.
    """

    def __init__(self) -> None:
        self._stop_requested = False
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        #: Per row key: lookups since the download completed, passes without a download id,
        #: the hash of a downloaded `nohash:` file, passes that raised.
        self._lookups: Dict[str, int] = {}
        self._unqueued: Dict[str, int] = {}
        self._digests: Dict[str, Optional[str]] = {}
        self._errors: Dict[str, int] = {}
        self._pass_failing = False

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """The loop `run()` is running on, or None before it starts and after it returns."""
        return self._loop

    @property
    def running(self) -> bool:
        return self._loop is not None

    async def run(self) -> None:
        # Created here, not in __init__, so the event belongs to the loop this runs on.
        # Event first, loop second: request_stop() reads them in the other order.
        self._stop_event = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        logger.info("[MODEL-BROWSER] Download watcher started (a sweep every %ss)", POLL_INTERVAL_SECONDS)
        try:
            reconcile = True
            while not self._stop_requested:
                await self.run_pass(reconcile=reconcile)
                reconcile = False
                if self._stop_requested:
                    break
                await self._sleep(POLL_INTERVAL_SECONDS)
        finally:
            self._loop = None
            await self._release_resources()
            logger.info("[MODEL-BROWSER] Download watcher stopped")

    async def _release_resources(self) -> None:
        """Close the sources' shared aiohttp session on this loop.

        The core fires no shutdown hook for plugins; this task is cancelled when the
        application loop stops, so this is the last chance to close the session before
        `ClientSession.__del__` complains about it during interpreter teardown.
        """
        try:
            from .http import http as source_http

            await source_http.close()
        except Exception:
            logger.debug("[MODEL-BROWSER] Could not close the sources' HTTP session", exc_info=True)

    def request_stop(self) -> None:
        """Make `run()` return at its next await, without waiting for it. Safe from any thread."""
        self._stop_requested = True
        loop, event = self._loop, self._stop_event
        if loop is None or event is None:
            return  # not started (run() checks the flag first) or already returned
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            pass  # the loop is closed: nothing will run this task again

    async def _sleep(self, seconds: float) -> None:
        """`asyncio.sleep(seconds)` that ends early when a stop is requested."""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # One pass ---------------------------------------------------------------

    async def run_pass(self, *, reconcile: bool = False) -> None:
        """Move every unfinished row on, oldest first; with `reconcile`, close the approved
        requests of rows that ended meanwhile too. Never raises (but for a cancellation)."""
        try:
            rows = await asyncio.to_thread(pending.list_unfinished)
        except Exception:
            if not self._pass_failing:
                logger.exception("[MODEL-BROWSER] Could not read the pending downloads; retrying every pass")
            self._pass_failing = True
            return
        self._pass_failing = False
        self._prune(rows)
        if reconcile and rows:
            logger.info("[MODEL-BROWSER] Resuming %d unfinished download(s)", len(rows))
        for row in rows:
            if self._stop_requested:
                return
            await self._advance_safely(row)
        if reconcile and not self._stop_requested:
            await self._settle_orphans()

    def _prune(self, rows: Iterable[PendingRow]) -> None:
        """Drop the counters of rows that are no longer where they were counted: the hook handler
        and the steps it schedules move rows on without the sweep."""
        rows = list(rows)
        queued = {row.sha256 for row in rows if row.status == "queued"}
        unfinished = {row.sha256 for row in rows}
        for counters, kept in (
            (self._lookups, queued),
            (self._unqueued, queued),
            (self._digests, queued),
            (self._errors, unfinished),
        ):
            for key in [key for key in counters if key not in kept]:
                del counters[key]

    async def _settle_orphans(self) -> None:
        """Close the approved requests whose row already ended (the server stopped in between)."""
        try:
            approved = await asyncio.to_thread(lambda: requests.list_rows(statuses=[requests.APPROVED], limit=1000))
            ended: Dict[str, PendingRow] = {}
            for request in approved:
                if request.sha256 and request.sha256 not in ended:
                    row = await asyncio.to_thread(pending.get, request.sha256)
                    if row is not None and row.finished:
                        ended[row.sha256] = row
            for row in ended.values():
                await settle_requests(row, done=row.status == "enriched")
        except Exception:
            logger.warning("[MODEL-BROWSER] Could not close the requests of finished downloads", exc_info=True)

    async def _advance_safely(self, row: PendingRow) -> None:
        try:
            await self.advance(row)
        except Exception as exc:
            count = self._errors.get(row.sha256, 0) + 1
            self._errors[row.sha256] = count
            if count == 1:
                logger.exception("[MODEL-BROWSER] Could not move %s on (%s); retrying on the next pass", row.sha256, row.status)
            else:
                logger.debug("[MODEL-BROWSER] %s still failing (%d): %s", row.sha256, count, exc)
            if count >= MAX_ROW_ERRORS:
                self._errors.pop(row.sha256, None)
                try:
                    await self._fail(row, f"Stopped following this download after repeated errors: {exc}")
                except Exception:
                    logger.exception("[MODEL-BROWSER] Could not mark %s failed", row.sha256)
        else:
            self._errors.pop(row.sha256, None)

    async def advance(self, row: PendingRow) -> Optional[PendingRow]:
        """Take one row as far as it can go now; returns it as stored (None when it is gone, or
        another step moved it on meanwhile)."""
        if row.status == "queued":
            row = await self._follow_download(row)
        if row is not None and row.status in FINISHING_STATUSES:
            row = await finish(row)
        return row

    # queued -> indexed, from the core download ------------------------------------

    async def _follow_download(self, row: PendingRow) -> Optional[PendingRow]:
        key = row.sha256
        if not row.download_id:
            waits = self._unqueued.get(key, 0) + 1
            self._unqueued[key] = waits
            if waits > UNQUEUED_GRACE_PASSES:
                return await self._fail(row, "The download was never put on the queue (the server stopped while queuing it)")
            return row
        self._unqueued.pop(key, None)

        download = await asyncio.to_thread(core_bridge.get_download, row.download_id)
        if download is None:
            if not row.nohash:
                model = await asyncio.to_thread(core_bridge.find_model_by_sha256, key)
                if model is not None:
                    return await self._indexed(row, model)
            return await self._fail(row, "The download is no longer on the download queue")
        status = download.get("status")
        if status in WAITING_STATUSES:
            return row
        if status in ("failed", "cancelled"):
            reason = download.get("error_message") or (
                "The download was cancelled" if status == "cancelled" else "The download failed"
            )
            return await self._fail(row, str(reason))
        if status != "completed":
            logger.warning("[MODEL-BROWSER] Download %s has an unknown status %r", row.download_id, status)
            return row
        return await self._locate(row, download)

    async def _locate(self, row: PendingRow, download: Mapping[str, Any]) -> Optional[PendingRow]:
        """The completed download's model, looked up once more; `indexed` when found."""
        key = row.sha256
        attempts = self._lookups.get(key, 0) + 1
        self._lookups[key] = attempts
        path = str(download.get("destination_path") or "")
        model = None
        if not row.nohash:
            model = await asyncio.to_thread(core_bridge.find_model_by_sha256, key)
        if model is None and path and (row.nohash or attempts >= PATH_FALLBACK_AFTER):
            candidate = await asyncio.to_thread(core_bridge.find_model_by_path, path)
            if candidate is not None and indexed_since(candidate, row):
                model = candidate
        if model is None and row.nohash and attempts >= HASH_FALLBACK_AFTER and path:
            if not download.get("destination_backend_id"):  # a remote download has no local file
                digest = await self._digest(key, path)
                if digest:
                    model = await asyncio.to_thread(core_bridge.find_model_by_sha256, digest)
        if model is None:
            if attempts >= MAX_INDEX_LOOKUPS:
                return await self._fail(
                    row,
                    "The file was downloaded but never showed up in the model index; "
                    "an admin can index it from the Models page",
                )
            return row
        return await self._indexed(row, model)

    async def _digest(self, key: str, path: str) -> Optional[str]:
        if key not in self._digests:
            logger.info("[MODEL-BROWSER] Hashing %s to find its model", path)
            self._digests[key] = await asyncio.to_thread(sha256_of_file, path)
        return self._digests[key]

    async def _indexed(self, row: PendingRow, model: Mapping[str, Any]) -> Optional[PendingRow]:
        self._forget(row.sha256)
        return await asyncio.to_thread(record_indexed, row, model)

    async def _fail(self, row: PendingRow, message: str) -> Optional[PendingRow]:
        self._forget(row.sha256)
        return await fail(row, message)

    def _forget(self, key: str) -> None:
        for counters in (self._lookups, self._unqueued, self._digests):
            counters.pop(key, None)
