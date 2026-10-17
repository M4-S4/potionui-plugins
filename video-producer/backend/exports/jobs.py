import logging
import shutil
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import core_bridge, notifications, projects
from ..core_bridge import generate_ulid
from . import video
from .video import ExportError

logger = logging.getLogger("plugins.video-producer")

JOBS = "video_producer_export_jobs"

ACTIVE = ("queued", "running")

FINISHED = ("done", "failed", "cancelled")

COLUMNS = (
    "id",
    "project_id",
    "user_id",
    "format",
    "resolution",
    "status",
    "progress",
    "step",
    "file_name",
    "file_size",
    "media_item_id",
    "media_url",
    "error_code",
    "error_message",
    "created_at",
    "started_at",
    "finished_at",
)

FILE_URL = "/api/plugins/video-producer/exports/{job_id}/file"

_ACTIVE_SQL = "status IN ('queued', 'running')"

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {JOBS}"

_PROCESSES: Dict[str, Any] = {}


def now() -> str:
    """The current time as the jobs store it, ISO 8601 in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _job(row: Any) -> Dict[str, Any]:
    job = {column: row[column] for column in COLUMNS}
    job["progress"] = float(job["progress"] or 0)
    return job


def public(job: Dict[str, Any]) -> Dict[str, Any]:
    """An export job as the API returns it."""
    done = job["status"] == "done" and job.get("file_name")
    media = job.get("media_item_id") or job.get("media_url")
    return {
        "id": job["id"],
        "project_id": job["project_id"],
        "format": job["format"],
        "resolution": job["resolution"],
        "status": job["status"],
        "progress": round(job["progress"], 1),
        "step": job["step"],
        "file": {"name": job["file_name"], "size": job["file_size"], "url": FILE_URL.format(job_id=job["id"])} if done else None,
        "media": {"kind": "library", "item_id": job["media_item_id"], "url": job["media_url"]} if done and media else None,
        "error": {"code": job["error_code"], "message": job["error_message"] or ""} if job.get("error_code") else None,
        "created_at": job["created_at"],
        "finished_at": job["finished_at"],
    }


def _fetch(query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        return [_job(row) for row in cursor.fetchall()]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """One export job, or None."""
    found = _fetch(f"{_SELECT} WHERE id = ?", (job_id,))
    return found[0] if found else None


def list_project(project_id: str) -> List[Dict[str, Any]]:
    """The export jobs of a project, newest first."""
    return _fetch(f"{_SELECT} WHERE project_id = ? ORDER BY created_at DESC, id DESC", (project_id,))


def list_user(user_id: str) -> List[Dict[str, Any]]:
    """The export jobs of a user, oldest first."""
    return _fetch(f"{_SELECT} WHERE user_id = ? ORDER BY created_at, id", (user_id,))


def has_active(project_id: str) -> bool:
    """True while an export of the project is queued or running."""
    return bool(_fetch(f"{_SELECT} WHERE project_id = ? AND {_ACTIVE_SQL} LIMIT 1", (project_id,)))


def list_active() -> List[Dict[str, Any]]:
    """The queued and running export jobs, oldest first."""
    return _fetch(f"{_SELECT} WHERE {_ACTIVE_SQL} ORDER BY created_at, id")


def create_job(project_id: str, user_id: str, fmt: str, resolution: str) -> Optional[Dict[str, Any]]:
    """Queue an export of a project; None when one of the project is already queued or running."""
    from src.plugin_api import db

    job_id = generate_ulid()
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {JOBS} (id, project_id, user_id, format, resolution, status, progress, created_at) "
            f"SELECT ?, ?, ?, ?, ?, 'queued', 0, ? WHERE NOT EXISTS "
            f"(SELECT 1 FROM {JOBS} WHERE project_id = ? AND {_ACTIVE_SQL})",
            (job_id, project_id, user_id, fmt, resolution, now(), project_id),
        )
        if cursor.rowcount != 1:
            return None
    return get_job(job_id)


def _update(job_id: str, fields: Dict[str, Any], condition: str) -> bool:
    from src.plugin_api import db

    names = [name for name in fields if name in COLUMNS and name != "id"]
    if not names:
        return False
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {JOBS} SET {', '.join(f'{name} = ?' for name in names)} WHERE id = ? AND {condition}",
            (*(fields[name] for name in names), job_id),
        )
        return cursor.rowcount == 1


def claim_next() -> Optional[Dict[str, Any]]:
    """Start the oldest queued job; None when none is waiting."""
    for job in _fetch(f"{_SELECT} WHERE status = 'queued' ORDER BY created_at, id"):
        if _update(job["id"], {"status": "running", "progress": 0, "step": "assemble", "started_at": now()}, "status = 'queued'"):
            return get_job(job["id"])
    return None


def update_running(job_id: str, **fields: Any) -> bool:
    """Update a running job; False when it is no longer running."""
    return _update(job_id, fields, "status = 'running'")


def settle(job_id: str, status: str, **fields: Any) -> bool:
    """End a queued or running job; True only for the caller that ended it."""
    return _update(job_id, {**fields, "status": status, "finished_at": now()}, _ACTIVE_SQL)


def _delete_row(job_id: str) -> None:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {JOBS} WHERE id = ?", (job_id,))


def clear_folder(job: Dict[str, Any]) -> None:
    """Delete the working folder of a job."""
    shutil.rmtree(video.job_folder(job), ignore_errors=True)


def remove(job: Dict[str, Any]) -> None:
    """Delete a finished job and its folder."""
    clear_folder(job)
    _delete_row(job["id"])


def file_path(job: Dict[str, Any]) -> Optional[Any]:
    """The exported file of a done job when it is still on disk, else None."""
    if job["status"] != "done" or not job.get("file_name"):
        return None
    path = video.job_folder(job) / job["file_name"]
    return path if path.is_file() else None


def usage(user_id: str) -> int:
    """The bytes of a user's export cache."""
    return video.folder_size(video.exports_root(user_id))


def make_room(user_id: str, quota_bytes: int) -> bool:
    """Delete the user's oldest finished jobs until the cache is under the quota; False when it cannot get there."""
    used = usage(user_id)
    for job in list_user(user_id):
        if used < quota_bytes:
            break
        if job["status"] in FINISHED:
            remove(job)
            used = usage(user_id)
    return used < quota_bytes


def kill(job_id: str) -> bool:
    """Kill the ffmpeg process of a running job; False when it has none."""
    process = _PROCESSES.get(job_id)
    if process is None or process.returncode is not None:
        return False
    try:
        process.kill()
    except ProcessLookupError:
        return False
    return True


def cancel(job: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel a queued or running job, killing its ffmpeg process; returns the job as it now stands."""
    if settle(job["id"], "cancelled", step=None, error_code="cancelled", error_message="The export was cancelled."):
        kill(job["id"])
        if job["status"] == "queued":
            clear_folder(job)
    return get_job(job["id"]) or job


def forget_project(project_id: str) -> None:
    """Cancel the jobs of a deleted project and delete them with their folders."""
    for job in list_project(project_id):
        if job["status"] in ACTIVE:
            job = cancel(job)
        if job["status"] in FINISHED:
            remove(job)


def _notify(job: Dict[str, Any], done: bool, message: str = "") -> None:
    project = projects.get_project(job["project_id"])
    name = project["name"] if project else "Video Producer"
    what = f"the {job['format']} video ({job['resolution']})"
    text = f"{name}: {what} is ready." if done else f"{name}: {what} could not be exported."
    core_bridge.notify(
        user_id=job["user_id"],
        notification_type=notifications.EXPORT_DONE if done else notifications.EXPORT_FAILED,
        title="Export ready" if done else "Export failed",
        message=f"{text} {message}".strip(),
        level="success" if done else "error",
        metadata={"project_id": job["project_id"], "job_id": job["id"], "url": FILE_URL.format(job_id=job["id"]) if done else None},
    )


def fail(job: Dict[str, Any], code: str, message: str) -> bool:
    """End a job as failed and tell its owner; False when it had already ended, as when it was cancelled."""
    ended = code != "cancelled" and settle(job["id"], "failed", step=None, error_code=code, error_message=message[:300])
    clear_folder(job)
    if ended:
        _notify(job, done=False, message=message)
    return ended


async def execute(job: Dict[str, Any]) -> None:
    """Run one claimed job to its end."""
    project = projects.get_project(job["project_id"])
    owner = core_bridge.get_user(project["user_id"]) if project else None
    requester = core_bridge.get_user(job["user_id"])
    if project is None or owner is None or requester is None:
        fail(job, "ffmpeg_failed", "The project or its owner no longer exists.")
        return

    def report(progress: float, step: str) -> bool:
        return update_running(job["id"], progress=round(min(max(progress, 0.0), 100.0), 1), step=step)

    def on_process(process: Any) -> None:
        if process is None:
            _PROCESSES.pop(job["id"], None)
        else:
            _PROCESSES[job["id"]] = process

    try:
        result = await video.render(job, project, owner, requester, report, on_process)
    except ExportError as exc:
        fail(job, exc.code, exc.message)
        return
    except Exception as exc:
        logger.exception("[VIDEO-PRODUCER] Export %s failed", job["id"])
        fail(job, "ffmpeg_failed", video.last_line(str(exc)) or "The export failed.")
        return
    if settle(job["id"], "done", progress=100.0, step=None, **result):
        _notify(job, done=True)
    else:
        clear_folder(job)


class Runner:
    """Runs the queued export jobs one at a time, oldest first, on the application loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._future: Any = None

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> bool:
        """Start working through the queue; False when it already does."""
        with self._lock:
            if self._active:
                return False
            self._active = True
        coroutine = self.run()
        try:
            self._future = core_bridge.run_on_app_loop(coroutine)
        except Exception:
            coroutine.close()
            with self._lock:
                self._active = False
            raise
        return True

    async def run(self) -> None:
        """Claim and run jobs until the queue is empty."""
        try:
            while True:
                with self._lock:
                    job = claim_next()
                    if job is None:
                        self._active = False
                        return
                await execute(job)
        except BaseException:
            with self._lock:
                self._active = False
            raise

    def stop(self) -> None:
        """Stop working through the queue and kill the running ffmpeg process."""
        for job_id in list(_PROCESSES):
            kill(job_id)
        if self._future is not None:
            self._future.cancel()
        self._future = None
        with self._lock:
            self._active = False


RUNNER = Runner()


def ensure_running() -> None:
    """Start the runner when it is not running."""
    try:
        RUNNER.start()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not start the export runner", exc_info=True)


def recover() -> int:
    """At startup, fail the jobs a stopped server left running and resume the queue; returns how many failed."""
    failed = 0
    for job in list_active():
        if job["status"] == "running" and fail(job, "ffmpeg_failed", "The server stopped during the export."):
            failed += 1
    if any(job["status"] == "queued" for job in list_active()):
        ensure_running()
    return failed
