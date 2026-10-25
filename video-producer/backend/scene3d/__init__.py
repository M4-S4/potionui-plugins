import logging
from typing import Optional

from ..core_bridge import User
from . import files, jobs, storage

logger = logging.getLogger("plugins.video-producer")


def sweep() -> int:
    """Delete the work files left without a write for an hour, and the scene files no stored version of their project cites any more once they are a day old; returns how many it deleted."""
    removed = 0
    for step, what in ((storage.sweep_work, "the abandoned work files"), (files.collect_orphans, "the orphan scene files")):
        try:
            removed += step()
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not sweep %s", what, exc_info=True)
    return removed


def recover() -> int:
    """At startup, fail the scene jobs a stopped server left before the core took them and sweep the scene storage; returns how many jobs failed."""
    failed = jobs.recover()
    sweep()
    return failed


async def forget_project(owner: Optional[User], project_id: str) -> None:
    """Cancel the scene jobs of a deleted project and delete its scene files, rows and folder."""
    await jobs.forget_project(owner, project_id)
    files.forget_project(project_id)
    try:
        storage.drop(storage.project_folder(project_id))
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not delete the scene storage of project %s", project_id, exc_info=True)
