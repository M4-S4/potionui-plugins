import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from . import chaining, core_bridge, generation, looks, takes
from .core_bridge import GenerationNotFoundException

logger = logging.getLogger("plugins.video-producer")

BUSY_INTERVAL = 2.0
IDLE_INTERVAL = 10.0

_UNREADABLE = object()


class Tracker:
    """Follows the takes in flight on the application loop and hands the queued takes to the core."""

    def __init__(self) -> None:
        self._future: Any = None
        self._stop: Optional[threading.Event] = None

    @property
    def running(self) -> bool:
        return self._future is not None and not self._future.done()

    def start(self) -> bool:
        """Start following the takes; False when it already does."""
        if self.running:
            return False
        stop = threading.Event()
        coroutine = self.run(stop)
        try:
            self._future = core_bridge.run_on_app_loop(coroutine)
        except Exception:
            coroutine.close()
            raise
        self._stop = stop
        return True

    def stop(self) -> None:
        """Stop following the takes."""
        if self._stop is not None:
            self._stop.set()
        if self._future is not None:
            self._future.cancel()
        self._future = None
        self._stop = None

    async def run(self, stop: threading.Event) -> None:
        """Check the takes every 2 s while some are queued or running, else every 10 s, until stopped."""
        while not stop.is_set():
            try:
                busy = await self.tick()
            except Exception:
                logger.exception("[VIDEO-PRODUCER] The take tracker failed a round")
                busy = False
            await asyncio.sleep(BUSY_INTERVAL if busy else IDLE_INTERVAL)

    async def tick(self) -> bool:
        """One round: follow each generation in flight, give the takes that wait for the last image of the previous shot that image once there is one, hand queued takes to the core, then, while no generation runs, compute one queued look; True while takes remain active or looks wait."""
        users: Dict[Optional[str], Any] = {}

        def owner(user_id: Optional[str]) -> Any:
            if user_id not in users:
                try:
                    users[user_id] = core_bridge.get_user(user_id) if user_id else None
                except Exception:
                    logger.warning("[VIDEO-PRODUCER] Could not read user %s", user_id, exc_info=True)
                    users[user_id] = _UNREADABLE
            return users[user_id]

        for take in takes.list_active():
            user = owner(take.get("user_id"))
            if user is _UNREADABLE:
                continue
            if user is None:
                generation.fail_take(take, "user_not_found", "The owner of this take no longer exists.")
                continue
            if not take.get("generation_id"):
                continue
            try:
                generation.apply_state(take, user, core_bridge.generation_state(user, take["generation_id"]))
            except GenerationNotFoundException:
                generation.fail_take(take, "generation_not_found", "The generation of this take is no longer available.")
            except Exception:
                logger.warning("[VIDEO-PRODUCER] Could not follow generation %s", take["generation_id"], exc_info=True)
        await chaining.take_frames(generation.fail_take)
        for user_id in takes.waiting_user_ids():
            user = owner(user_id)
            if user is not None and user is not _UNREADABLE:
                await generation.pump(user)
        await looks.run_once()
        return bool(takes.list_active()) or looks.queued_count() > 0


TRACKER = Tracker()


def ensure_running() -> None:
    """Start the tracker when it is not running, as when the plugin was enabled after the application started."""
    try:
        TRACKER.start()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not start the take tracker", exc_info=True)
