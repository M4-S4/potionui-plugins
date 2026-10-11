"""The download watcher: the plugin's background task on PotionUI's event loop (PLAN.md §3, §7.4).

The core has no "download finished" hook, so this task polls the downloads the plugin
queued (`model_browser_pending`, `backend/pending.py`) every `POLL_INTERVAL_SECONDS` and
moves each unfinished row on, as far as it can go in one pass:

- `queued`: the core download (`core_bridge.get_download`). `pending`, `downloading`,
  `paused`: wait. `failed`, `cancelled`, or the record gone (unless the file is indexed
  already): `failed`. `completed`: find the indexed model (below), then `indexed`. A row
  that never got a download id (the server stopped while queuing it) fails after
  `UNQUEUED_GRACE_PASSES` passes.
- `indexed`: assign per `assign_to`: `user:<id>` to that user, `group:<id>` to the group
  (to the requester when the group is gone), `none` to nobody (an admin's download, every
  admin sees every model). Then `assigned`; a refusal from the core is `failed`.
- `assigned`: enrich: the `model-browser` provider fetch (`provider/pending_provider.py`,
  which answers from this row: description, trigger words, tags, safe previews, the source
  page as the model's mirror), then the `mb_base_model` / `mb_license` attributes from the
  row's `info`. Then `enriched`: a step that failed is noted in `error`, the row still ends
  `enriched` (the model is downloaded and visible). The core's own `civitai` provider is
  never asked: it hands every image of the version to the core as previews, NSFW ones
  included, and previews are shown to everyone the model is assigned to.
The requester is notified when a row ends: `model-browser.download_done` or
`model-browser.download_failed`.

Finding the model once the download is `completed`: the worker marks a download
completed *before* indexing it, so the lookup is retried on each pass:
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
unfinished by a restart are simply taken up where they were. One row's error never stops
the pass: it is logged and retried on the next pass, and a row that fails
`MAX_ROW_ERRORS` passes in a row is given up (`failed`).

`plugin.lifecycle.ready` starts this task with `run_on_app_loop(watcher.run())`;
`plugin.lifecycle.disable` stops it.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from . import PLUGIN_ID, core_bridge, pending
from .core_bridge import CoreBridgeError
from .pending import PendingRow

logger = logging.getLogger("plugins.model-browser")

#: Seconds between two passes over the plugin's pending downloads.
POLL_INTERVAL_SECONDS = 5
#: Lookups by hash, after `completed`, before the download's path is tried as well.
PATH_FALLBACK_AFTER = 12
#: Lookups by path of a `nohash:` row before the downloaded file is hashed (~5 min: the
#: indexer, which hashes it too, has normally indexed a new file by then).
HASH_FALLBACK_AFTER = 60
#: Lookups after which a completed download that never showed up in the index fails (~30 min).
MAX_INDEX_LOOKUPS = 360
#: Passes a `queued` row may spend without a download id (being queued) before it fails.
UNQUEUED_GRACE_PASSES = 60
#: Passes in a row one row may raise on before it is given up.
MAX_ROW_ERRORS = 120
#: Longest `error` stored on a row.
MAX_ERROR_LENGTH = 2000

#: Core download statuses that mean "not finished yet".
WAITING_STATUSES = frozenset({"pending", "downloading", "paused"})

#: The plugin's own provider (`provider/pending_provider.py`), which answers from the pending rows.
PENDING_PROVIDER_ID = PLUGIN_ID
NOTIFY_DOWNLOAD_DONE = "model-browser.download_done"
NOTIFY_DOWNLOAD_FAILED = "model-browser.download_failed"

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


class Watcher:
    """One run of the watcher: `run()` is awaited on the app loop, once.

    `request_stop()` may be called from any thread, before or during the run. The
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
        logger.info("[MODEL-BROWSER] Download watcher started (every %ss)", POLL_INTERVAL_SECONDS)
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
        """Move every unfinished row on, oldest first. Never raises (but for a cancellation)."""
        try:
            rows = await asyncio.to_thread(pending.list_unfinished)
        except Exception:
            if not self._pass_failing:
                logger.exception("[MODEL-BROWSER] Could not read the pending downloads; retrying every pass")
            self._pass_failing = True
            return
        self._pass_failing = False
        if reconcile and rows:
            logger.info("[MODEL-BROWSER] Resuming %d unfinished download(s)", len(rows))
        for row in rows:
            if self._stop_requested:
                return
            await self._advance_safely(row)

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
        """Take one row as far as it can go now; returns it as stored (None when it is gone)."""
        if row.status == "queued":
            row = await self._follow_download(row)
        if row is not None and row.status == "indexed":
            row = await self._assign(row)
        if row is not None and row.status == "assigned":
            row = await self._enrich(row)
        return row

    # queued -> indexed ---------------------------------------------------------

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
        """Record the model found for `row`, under the model's real hash when the row had another key."""
        key = row.sha256
        model_sha = str(model.get("sha256") or "").strip().lower()
        if model_sha and model_sha != key:
            if await asyncio.to_thread(pending.get, model_sha) is None:
                moved = await asyncio.to_thread(pending.rekey, key, model_sha)
                if moved is None or moved.download_id != row.download_id:
                    logger.warning("[MODEL-BROWSER] %s merged into the row of %s meanwhile", key, model_sha)
                    self._forget(key)
                    return moved
                key = model_sha
            else:
                # The same file is on its way under its hash too: that row describes it to the
                # providers, this one keeps its own key and still gets its model assigned.
                logger.info("[MODEL-BROWSER] %s is the model of another row (%s); keeping its key", key, model_sha)
        self._forget(row.sha256)
        updated = await asyncio.to_thread(pending.update, key, model_id=model.get("id"), status="indexed", error=None)
        logger.info("[MODEL-BROWSER] %s indexed as model %s", row.file_name, model.get("id"))
        return updated

    # indexed -> assigned ------------------------------------------------------

    async def _assign(self, row: PendingRow) -> Optional[PendingRow]:
        if not row.model_id:
            return await self._fail(row, "No model to assign")
        kind, _, target = row.assign_to.partition(":")
        assign_to, note = row.assign_to, None
        try:
            if row.assign_to == "none":
                pass  # an admin's download: admins see every model
            elif kind == "group" and target:
                try:
                    await asyncio.to_thread(core_bridge.assign_to_group, target, [row.model_id])
                except CoreBridgeError as exc:
                    if exc.code != "not_found":
                        raise
                    await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, row.requested_by)
                    assign_to = f"user:{row.requested_by}"
                    note = f"The group '{target}' no longer exists: the model was assigned to its requester instead"
                    logger.warning("[MODEL-BROWSER] %s", note)
            else:
                user_id = target if kind == "user" and target else row.requested_by
                if kind != "user":
                    logger.warning("[MODEL-BROWSER] Unknown assign_to %r on %s: assigning to the requester", row.assign_to, row.sha256)
                await asyncio.to_thread(core_bridge.assign_to_user, row.model_id, user_id)
                assign_to = f"user:{user_id}"
        except CoreBridgeError as exc:
            return await self._fail(row, f"The model was downloaded but could not be made visible: {exc.message}")
        fields: Dict[str, Any] = {"status": "assigned", "error": note}
        if assign_to != row.assign_to:
            fields["assign_to"] = assign_to
        return await asyncio.to_thread(pending.update, row.sha256, **fields)

    # assigned -> enriched -----------------------------------------------------

    async def _enrich(self, row: PendingRow) -> Optional[PendingRow]:
        notes: List[str] = [row.error] if row.error else []
        notes += await self._fetch(PENDING_PROVIDER_ID, row.model_id)
        attributes = model_attributes(row.info)
        if attributes:
            try:
                await asyncio.to_thread(core_bridge.write_attributes, row.model_id, attributes)
            except Exception as exc:
                message = exc.message if isinstance(exc, CoreBridgeError) else str(exc)
                logger.warning("[MODEL-BROWSER] Could not write the attributes of model %s: %s", row.model_id, message)
                notes.append(f"attributes: {message}")
        error = "; ".join(notes)[:MAX_ERROR_LENGTH] or None
        updated = await asyncio.to_thread(pending.update, row.sha256, status="enriched", error=error)
        logger.info("[MODEL-BROWSER] %s ready (model %s)%s", row.file_name, row.model_id, f": {error}" if error else "")
        await self._notify(updated or row, done=True)
        return updated

    async def _fetch(self, provider: str, model_id: Optional[str]) -> List[str]:
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

    # Endings ----------------------------------------------------------------

    async def _fail(self, row: PendingRow, message: str) -> Optional[PendingRow]:
        self._forget(row.sha256)
        updated = await asyncio.to_thread(pending.update, row.sha256, status="failed", error=message[:MAX_ERROR_LENGTH])
        logger.warning("[MODEL-BROWSER] %s failed: %s", row.file_name, message)
        await self._notify(updated or pending.with_status(row, "failed", message), done=False)
        return updated

    async def _notify(self, row: PendingRow, *, done: bool) -> None:
        label = _label(row)
        if done:
            if row.assign_to.startswith("group:"):
                where = "it is now available to your group"
            elif row.assign_to == "none":
                where = "it is now installed"
            else:
                where = "it is now in your models"
            title, message, level, kind = "Model downloaded", f"{label}: {where}.", "success", NOTIFY_DOWNLOAD_DONE
        else:
            title, message, level, kind = "Model download failed", f"{label}: {row.error}", "error", NOTIFY_DOWNLOAD_FAILED
        metadata = {
            "source": row.source,
            "source_model_id": row.source_model_id,
            "source_version_id": row.source_version_id,
            "sha256": None if row.nohash else row.sha256,
            "model_id": row.model_id,
            "download_id": row.download_id,
        }
        try:
            await asyncio.to_thread(
                core_bridge.notify,
                user_id=row.requested_by,
                notification_type=kind,
                title=title,
                message=message,
                level=level,
                metadata=metadata,
            )
        except Exception:
            logger.warning("[MODEL-BROWSER] Could not notify %s about %s", row.requested_by, row.sha256, exc_info=True)

    def _forget(self, key: str) -> None:
        for counters in (self._lookups, self._unqueued, self._digests):
            counters.pop(key, None)
