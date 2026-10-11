"""`backend.watcher.Watcher`: starts, idles, and stops promptly when asked."""

import asyncio
import logging

from backend import watcher as watcher_module
from backend.watcher import Watcher


async def _until(predicate, timeout=1.0):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


async def test_run_returns_promptly_after_request_stop(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="plugins.model-browser")
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 0.01)
    watcher = Watcher()
    task = asyncio.create_task(watcher.run())
    await _until(lambda: watcher.running)
    await asyncio.sleep(0.05)  # a few idle passes
    assert not task.done()

    watcher.request_stop()
    await asyncio.wait_for(task, timeout=1)

    assert not watcher.running
    messages = [record.getMessage() for record in caplog.records]
    assert any("Download watcher started" in message for message in messages)
    assert any("Download watcher stopped" in message for message in messages)


async def test_a_stop_from_another_thread_cuts_the_poll_interval_short(monkeypatch):
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 60)
    watcher = Watcher()
    task = asyncio.create_task(watcher.run())
    await _until(lambda: watcher.running)

    await asyncio.to_thread(watcher.request_stop)

    await asyncio.wait_for(task, timeout=1)


async def test_a_stop_requested_before_run_returns_at_once(monkeypatch):
    monkeypatch.setattr(watcher_module, "POLL_INTERVAL_SECONDS", 60)
    watcher = Watcher()

    watcher.request_stop()

    await asyncio.wait_for(watcher.run(), timeout=1)
    assert not watcher.running
