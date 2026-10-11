"""Lifecycle handlers of the model-browser plugin (PLAN.md §3).

- `plugin.lifecycle.boot`, on every process start and right after a runtime
  enable: create the plugin's tables.
- `plugin.lifecycle.ready`, once the application's event loop runs: start the
  download watcher with `run_on_app_loop`.
- `plugin.lifecycle.disable`, broadcast to every enabled plugin: stop the
  watcher when the plugin being disabled is this one.

Handlers are synchronous, never raise, and return the context they were given.
`run_on_app_loop` and `get_app_loop` are imported inside the functions that use
them, so this module still imports on a core that predates them.
"""

import logging
import threading

from src.plugin_api import HookContext

# PotionUI's PluginLoader imports this file as `model_browser.hooks.lifecycle_hooks`,
# the plugin root being the `model_browser` package; the plugin's tests import it as
# the top-level `hooks.lifecycle_hooks`, with the plugin root on sys.path. Inside the
# app it must never be a bare `import backend`: every plugin that ships a `backend`
# package competes for that top-level name.
if __name__.count(".") >= 2:
    from ..backend import PLUGIN_ID, tables
    from ..backend.watcher import Watcher
else:
    from backend import PLUGIN_ID, tables
    from backend.watcher import Watcher

logger = logging.getLogger("plugins.model-browser")

#: Seconds a stopping watcher gets to return on its own before its task is cancelled.
STOP_GRACE_SECONDS = 10.0

_lock = threading.Lock()
_watcher = None  # the Watcher this module started, until it is stopped
_watcher_future = None  # its concurrent.futures.Future, from run_on_app_loop


def on_boot(context: HookContext) -> HookContext:
    """Create the plugin's tables (idempotent).

    Also starts the watcher when the app loop already runs, which means a runtime
    enable: the core fires `ready` once per plugin and process
    (`PluginRegistry.run_ready_hook`), so a plugin disabled then enabled again gets
    `boot` but no second `ready`. At process start the loop is not running yet, and
    `on_ready` starts the watcher.
    """
    try:
        tables.create_tables()
        logger.info("[MODEL-BROWSER] Tables ready: %s", ", ".join(tables.TABLE_NAMES))
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not create the plugin's tables")
    try:
        if _app_loop_running():
            _start_watcher()
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not start the download watcher")
    return context


def on_ready(context: HookContext) -> HookContext:
    """Start the download watcher on the application's event loop."""
    try:
        _start_watcher()
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not start the download watcher")
    return context


def on_disable(context: HookContext) -> HookContext:
    """Stop the download watcher when the plugin being disabled is this one.

    `disable` is broadcast to every enabled plugin's handler; `plugin_id` in the
    payload names the plugin being disabled.
    """
    try:
        if context.get("plugin_id") == PLUGIN_ID:
            _stop_watcher()
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not stop the download watcher")
    return context


def _app_loop_running() -> bool:
    """Whether PotionUI's event loop is up; False during the boot of a process start."""
    try:
        from src.plugin_api.hooks import get_app_loop

        return get_app_loop().is_running()
    except (ImportError, RuntimeError):
        return False


def _start_watcher() -> None:
    """Schedule a new watcher on the app loop, unless the previous one is still running."""
    global _watcher, _watcher_future
    from src.plugin_api.hooks import run_on_app_loop

    with _lock:
        if _watcher_future is not None and not _watcher_future.done():
            return
        watcher = Watcher()
        _watcher_future = run_on_app_loop(watcher.run())
        _watcher = watcher


def _stop_watcher() -> None:
    """Ask the watcher to return; cancel its task if it has not after `STOP_GRACE_SECONDS`.

    Never waits: the handler may be running on the very loop the watcher runs on.
    """
    global _watcher, _watcher_future
    with _lock:
        watcher, future = _watcher, _watcher_future
        _watcher = _watcher_future = None
    if watcher is None or future is None or future.done():
        logger.info("[MODEL-BROWSER] Disabled; no download watcher was running")
        return

    watcher.request_stop()
    loop = watcher.loop
    if loop is None:
        # Scheduled but not started yet: drop the task before it runs.
        future.cancel()
    elif not loop.is_closed():
        # Fallback for a watcher stuck in a step. Cancelling the future that
        # run_on_app_loop returned cancels the task on the app loop; it is a no-op
        # once the watcher has returned.
        loop.call_soon_threadsafe(loop.call_later, STOP_GRACE_SECONDS, future.cancel)
    logger.info("[MODEL-BROWSER] Disabled; stopping the download watcher")
