"""The download watcher: the plugin's background task on PotionUI's event loop.

The core has no "download finished" hook (PLAN.md §3), so from phase 3 on this
task polls the downloads the plugin queued and takes each one through indexing,
assignment and enrichment (§7.4). `plugin.lifecycle.ready` starts it with
`run_on_app_loop(watcher.run())`; `plugin.lifecycle.disable` stops it.

Phase 0 proves the lifecycle only: the watcher logs, then idles until stopped.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("plugins.model-browser")

#: Seconds between two passes over the plugin's pending downloads.
POLL_INTERVAL_SECONDS = 5


class Watcher:
    """One run of the watcher: `run()` is awaited on the app loop, once.

    `request_stop()` may be called from any thread, before or during the run.
    """

    def __init__(self) -> None:
        self._stop_requested = False
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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
            while not self._stop_requested:
                # phase 3: reconcile the unfinished model_browser_pending rows on the first
                # pass, then move each queued row on from core_bridge.get_download().
                await self._sleep(POLL_INTERVAL_SECONDS)
        finally:
            self._loop = None
            logger.info("[MODEL-BROWSER] Download watcher stopped")

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
