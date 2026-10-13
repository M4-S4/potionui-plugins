"""`download.after_complete` handler of the model-browser plugin (PLAN.md §7.4): the normal
path from a finished download to its model.

PotionUI's download worker fires the hook for every download of the instance once the file
has landed and, for a local model download, once the catalog has indexed it: `model_id`, or
`duplicate_of` for a byte-for-byte copy of a model already indexed. The handler looks for
the plugin's row of the download (`pending.get_by_download_id`, else the row keyed by the
payload's checksum and URL while its download id is not stored yet) and leaves every other
download alone. A `queued` row is recorded `indexed` with its model (`watcher.record_indexed`;
a `nohash:` row moves to the model's real hash, read by the file's path, or by the model's id
for a copy), then the rest of the pipeline (assignment, enrichment, notifications) is handed
over to the application loop (`watcher.schedule_step`). A file the catalog did not index
fails the row there, with the indexer's warning when it gave one. A row that is not `queued`
any more is left as it is: a late completion of a download the plugin gave up on revives
nothing and records no quota again.

The handler runs on a thread of the worker, which gives it 30 seconds: it does database
work only and never raises. What it leaves (no application loop yet, an error, a download
sent to a remote backend, which the hook reports without a model id) is taken up by the
watcher's sweep (`backend/watcher.py`) on its next pass.
"""

import logging
from typing import Any, Dict, Optional

from src.plugin_api import HookContext

# Imported as `model_browser.hooks.download_hooks` by PotionUI's loader and as the
# top-level `hooks.download_hooks` by the tests (see lifecycle_hooks.py).
if __name__.count(".") >= 2:
    from ..backend import core_bridge, pending, watcher
    from ..backend.pending import PendingRow
else:
    from backend import core_bridge, pending, watcher
    from backend.pending import PendingRow

logger = logging.getLogger("plugins.model-browser")

#: Why a row fails when the core indexed none of its file.
NOT_INDEXED = "The file was downloaded but not indexed"


def on_download_complete(context: HookContext) -> HookContext:
    """Record the model of one of the plugin's downloads and schedule the rest; ignore any other download."""
    try:
        _complete(context)
    except Exception:
        logger.exception(
            "[MODEL-BROWSER] Could not take up the completed download %s; the sweep will", context.get("download_id")
        )
    return context


def _complete(context: HookContext) -> None:
    download_id = context.get("download_id")
    row = _row_of(download_id, context.get("checksum_sha256"), context.get("url"))
    if row is None:
        return
    if row.status != "queued":
        logger.info(
            "[MODEL-BROWSER] Download %s completed, but %s is %s already: left as it is", download_id, row.file_name, row.status
        )
        return
    model_id = context.get("model_id") or context.get("duplicate_of")
    if not model_id:
        if context.get("destination_backend_id"):
            logger.info(
                "[MODEL-BROWSER] %s landed on the remote backend %s; the sweep will find its model",
                row.file_name,
                context.get("destination_backend_id"),
            )
            return
        warning = context.get("warning")
        message = f"{NOT_INDEXED}: {warning}" if warning else f"{NOT_INDEXED}; an admin can index it from the Models page"
        watcher.schedule_step(watcher.fail(row, message), row.sha256)
        return
    if not context.get("model_id"):
        logger.info("[MODEL-BROWSER] %s is a copy of model %s", row.file_name, model_id)
    model = _model(row, model_id, copy=not context.get("model_id"), path=context.get("destination_path"))
    updated = watcher.record_indexed(row, model)
    if updated is not None and updated.status in watcher.FINISHING_STATUSES:
        watcher.schedule_step(watcher.carry_on(updated.sha256), updated.sha256)


def _row_of(download_id: Optional[str], checksum: Optional[str], url: Optional[str]) -> Optional[PendingRow]:
    """The plugin's row of this download: by its id, else by the key of its file while the
    row has no download id yet (it is stored once the queue call returns); None when the
    download is not the plugin's."""
    row = pending.get_by_download_id(download_id)
    if row is not None or not url:
        return row
    row = pending.get(pending.key_for(checksum, url))
    if row is not None and row.download_id in (None, download_id):
        return row
    return None


def _model(row: PendingRow, model_id: str, *, copy: bool, path: Optional[str]) -> Dict[str, Any]:
    """The model to record for `row`: its id, and for a `nohash:` row the hash the catalog
    computed (the model at the file's path, or the model it is a copy of)."""
    if not row.nohash:
        return {"id": model_id}
    found = core_bridge.find_model_by_path(path) if path and not copy else None
    if found is None or found.get("id") != model_id:
        found = core_bridge.find_model_by_id(model_id)
    sha256 = found.get("sha256") if found is not None and found.get("id") == model_id else None
    return {"id": model_id, "sha256": sha256}
