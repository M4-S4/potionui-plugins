import logging
from typing import Optional

from ..core_bridge import User
from . import files, jobs, renders, storage

logger = logging.getLogger("plugins.video-producer")


def recover() -> int:
    """At startup, fail the scene jobs a stopped server left before the core took them and delete the renders left unfinished for a day; returns how many jobs failed."""
    failed = jobs.recover()
    try:
        renders.sweep()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not sweep the unfinished renders", exc_info=True)
    return failed


async def forget_project(owner: Optional[User], project_id: str) -> None:
    """Cancel the scene jobs and renders of a deleted project and delete its scene files, rows and folder."""
    await jobs.forget_project(owner, project_id)
    files.forget_project(project_id)
    try:
        renders.forget_project(project_id)
        storage.drop(storage.project_folder(project_id))
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not delete the scene storage of project %s", project_id, exc_info=True)
