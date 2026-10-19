import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .. import core_bridge, director, estimate, generation, limits, models, presets
from ..core_bridge import GenerationNotFoundException, MediaRefError, User, generate_ulid
from ..director import note
from ..generation import Blocked
from . import files, formats, storage
from .formats import FormatError
from .storage import SceneError

logger = logging.getLogger("plugins.video-producer")

JOBS = "video_producer_scene_jobs"

SPLAT_PRESET = presets.IMAGE_TO_SPLAT

SPLAT_MODE = "img2splat"

SOURCE_FIELD = "source_image"

RESERVED_MINUTES = 1.0

ACTIVE = ("queued", "running")

COLUMNS = (
    "id",
    "project_id",
    "scene_id",
    "user_id",
    "generation_id",
    "status",
    "progress",
    "source_asset_id",
    "source_time",
    "source_value",
    "backend_id",
    "file_id",
    "splat_count",
    "view",
    "units_reserved",
    "request",
    "error_code",
    "error_message",
    "created_at",
    "started_at",
    "finished_at",
)

_ACTIVE_SQL = "status IN ('queued', 'running')"

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {JOBS}"


def limit_ref(job_id: str) -> str:
    """The reference a scene job's GPU minutes are recorded under."""
    return f"video-producer:scene:{job_id}"


def _job(row: Any) -> Dict[str, Any]:
    job = {column: row[column] for column in COLUMNS}
    job["progress"] = float(job["progress"] or 0)
    job["units_reserved"] = float(job["units_reserved"] or 0)
    job["view"] = json.loads(job["view"]) if job["view"] else None
    job["request"] = json.loads(job["request"]) if job["request"] else None
    return job


def public(job: Dict[str, Any]) -> Dict[str, Any]:
    """A scene job as the API returns it, in the shape a splat scene of the document takes."""
    return {
        "id": job["id"],
        "sceneId": job["scene_id"],
        "status": job["status"],
        "progress": round(job["progress"], 1),
        "error": job["error_message"] if job["error_code"] else None,
        "errorCode": job["error_code"],
        "fileId": job["file_id"],
        "count": job["splat_count"],
        "view": job["view"],
        "generationId": job["generation_id"],
        "createdAt": job["created_at"],
        "finishedAt": job["finished_at"],
    }


def _fetch(query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        return [_job(row) for row in cursor.fetchall()]


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """One scene job, or None."""
    found = _fetch(f"{_SELECT} WHERE id = ?", (job_id,))
    return found[0] if found else None


def list_project(project_id: str) -> List[Dict[str, Any]]:
    """The scene jobs of a project, oldest first."""
    return _fetch(f"{_SELECT} WHERE project_id = ? ORDER BY created_at, id", (project_id,))


def has_active(project_id: str) -> bool:
    """True while a scene job of the project is queued or running."""
    return bool(_fetch(f"{_SELECT} WHERE project_id = ? AND {_ACTIVE_SQL} LIMIT 1", (project_id,)))


def list_active() -> List[Dict[str, Any]]:
    """The queued and running scene jobs, oldest first."""
    return _fetch(f"{_SELECT} WHERE {_ACTIVE_SQL} ORDER BY created_at, id")


def _insert(job: Dict[str, Any]) -> None:
    from src.plugin_api import db

    values = {column: job.get(column) for column in COLUMNS}
    values["request"] = json.dumps(values["request"]) if values["request"] else None
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {JOBS} ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(values[column] for column in COLUMNS),
        )


def _update(job_id: str, fields: Dict[str, Any], condition: str) -> bool:
    from src.plugin_api import db

    names = [name for name in fields if name in COLUMNS and name != "id"]
    if not names:
        return False
    values = [json.dumps(fields[name]) if name == "view" and fields[name] is not None else fields[name] for name in names]
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {JOBS} SET {', '.join(f'{name} = ?' for name in names)} WHERE id = ? AND {condition}",
            (*values, job_id),
        )
        return cursor.rowcount == 1


def update_active(job_id: str, **fields: Any) -> bool:
    """Update a queued or running job; False when it has already ended."""
    return _update(job_id, fields, _ACTIVE_SQL)


def settle(job_id: str, status: str, **fields: Any) -> bool:
    """End a queued or running job; True only for the caller that ended it."""
    return _update(job_id, {**fields, "status": status, "finished_at": storage.now()}, _ACTIVE_SQL)


def _refund(job: Mapping[str, Any]) -> None:
    if float(job.get("units_reserved") or 0) > 0:
        core_bridge.refund_limit_event(limit_ref(job["id"]))


def fail(job: Mapping[str, Any], code: str, message: str) -> bool:
    """End a job as failed and refund its minutes; False when it had already ended."""
    if not settle(job["id"], "failed", error_code=code, error_message=message[: generation.MESSAGE_LIMIT]):
        return False
    _refund(job)
    return True


def cancel_local(job: Mapping[str, Any]) -> bool:
    """End a job as cancelled and refund its minutes; False when it had already ended."""
    if not settle(job["id"], "cancelled", error_code="cancelled", error_message="The scene was cancelled."):
        return False
    _refund(job)
    return True


def _adjust(job: Mapping[str, Any], duration_ms: Optional[int]) -> None:
    reserved = float(job.get("units_reserved") or 0)
    if reserved <= 0 or not duration_ms:
        return
    actual = round(duration_ms / 60000, 3)
    ref = limit_ref(job["id"])
    if actual > reserved + 1e-6:
        core_bridge.record_limit_event(job["user_id"], limits.GPU_MINUTES, round(actual - reserved, 3), f"{ref}:adjust")
    elif actual < reserved - 1e-6:
        core_bridge.refund_limit_event(ref)
        core_bridge.record_limit_event(job["user_id"], limits.GPU_MINUTES, actual, f"{ref}:actual")


def _asset(doc: Mapping[str, Any], asset_id: str) -> Dict[str, Any]:
    asset = next((item for item in doc.get("assets") or [] if item.get("id") == asset_id), None)
    if asset is None:
        raise SceneError(404, "asset_not_found", "The project has no such asset.")
    return asset


async def source_image(owner: User, doc: Mapping[str, Any], asset_id: str, time: Optional[float]) -> str:
    """The image a splat is made from: the asset itself when it is an image, its frame at time when it is a video; SceneError otherwise."""
    asset = _asset(doc, asset_id)
    ref = director.media_ref(asset.get("origin"))
    kind = asset.get("kind")
    if ref is None or kind not in ("image", "video"):
        raise SceneError(422, "invalid_source", "The asset must be an image or a video of the library or the history.")
    if kind == "video":
        if time is None:
            raise SceneError(422, "invalid_request", "time is needed to take a frame of a video.")
        try:
            frame = await core_bridge.extract_frame(owner, ref, time)
        except MediaRefError as exc:
            if exc.code == "not_found":
                raise SceneError(404, "media_not_found", "The media is not available.") from None
            raise SceneError(502, "extract_failed", str(exc) or "The frame could not be extracted.") from None
        return str(frame["value"])
    try:
        resolved = core_bridge.resolve_media(owner, ref)
    except MediaRefError:
        raise SceneError(404, "media_not_found", "The media is not available.") from None
    if str(resolved.get("media_type") or "").split("/", 1)[0].lower() != "image":
        raise SceneError(422, "invalid_source", "The asset must be an image or a video of the library or the history.")
    return str(resolved["value"])


def _plan(owner: User) -> Tuple[Dict[str, Any], float]:
    preset = director.find_preset(owner, SPLAT_PRESET, video=False)
    if preset is None or SPLAT_MODE not in preset.modes:
        raise Blocked([note("no_preset", "The Image to Splat preset is not available to you.", preset_id=SPLAT_PRESET)])
    fields = models.form_fields(SPLAT_PRESET, SPLAT_MODE)
    resolved = models.resolve_models(SPLAT_PRESET, SPLAT_MODE, None, fields)
    if resolved.missing:
        raise Blocked([generation.missing_block(list(resolved.missing))])
    form: Dict[str, Any] = dict(resolved.values)
    if "seed" in fields:
        form["seed"] = -1
    minutes = 0.0
    if not preset.cloud:
        status = limits.gpu_minutes_status(owner.id)
        remaining = status.get("remaining")
        if generation.reserves(status):
            if remaining is not None and RESERVED_MINUTES > float(remaining) + 1e-9:
                raise Blocked([estimate.quota_block({"needed_minutes": RESERVED_MINUTES, "remaining": remaining})])
            minutes = RESERVED_MINUTES
    return form, minutes


async def _submit(owner: User, job: Dict[str, Any]) -> None:
    try:
        submitted = await core_bridge.submit_generation(owner, job["request"])
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] The core refused scene job %s", job["id"], exc_info=True)
        fail(job, *generation.refusal(exc))
        return
    generation_id = str(submitted["generation_id"])
    if not update_active(job["id"], generation_id=generation_id):
        await generation.quiet_cancel(owner, generation_id)


async def from_image(
    owner: User, project: Mapping[str, Any], scene_id: str, asset_id: str, time: Optional[float]
) -> Dict[str, Any]:
    """Make a splat of an image of the project, or of a frame of one of its videos: reserve its minutes and hand it to the core; SceneError 413 when the project or its owner has no storage room left."""
    form, minutes = _plan(owner)
    files.ensure_room(project["id"], owner.id, 1)
    value = await source_image(owner, project["doc"], asset_id, time)
    job_id = generate_ulid()
    request = {
        "preset_id": SPLAT_PRESET,
        "mode": SPLAT_MODE,
        "prompts": [{"positive": "", "negative": ""}],
        "form_data": {SOURCE_FIELD: value, **form},
        "idempotency_key": f"vp-scene:{job_id}",
    }
    _insert(
        {
            "id": job_id,
            "project_id": project["id"],
            "scene_id": scene_id,
            "user_id": owner.id,
            "status": "queued",
            "progress": 0.0,
            "source_asset_id": asset_id,
            "source_time": time,
            "source_value": value,
            "units_reserved": 0.0,
            "request": request,
            "created_at": storage.now(),
        }
    )
    if minutes > 0 and core_bridge.record_limit_event(owner.id, limits.GPU_MINUTES, minutes, limit_ref(job_id)):
        update_active(job_id, units_reserved=minutes)
    await _submit(owner, get_job(job_id))
    return get_job(job_id)


def _splat(found: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for item in found:
        name = str(item.get("file_path") or "")
        if str(item.get("file_type") or "").lower() == "splat" or formats.format_of(name) in formats.SPLAT_FORMATS:
            return item
    return None


def _copy(job: Mapping[str, Any], item: Mapping[str, Any], file_id: str) -> Tuple[Path, formats.Probe]:
    folder = storage.project_folder(job["project_id"])
    folder.mkdir(parents=True, exist_ok=True)
    fmt = formats.format_of(str(item.get("file_path") or "")) or str(item.get("splat_format") or "ply")
    local = core_bridge.local_media_file("history", str(item["file_path"]), folder)
    if local is None:
        raise FileNotFoundError(item["file_path"])
    target = folder / files.stored_name(file_id, fmt)
    if local.parent == folder and local.name.startswith(core_bridge.SOURCE_PREFIX):
        local.replace(target)
    else:
        shutil.copyfile(local, target)
    try:
        return target, formats.probe(fmt, target)
    except FormatError:
        target.unlink(missing_ok=True)
        raise


async def finish_done(job: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> bool:
    """End a job whose generation completed: copy its splat into the project's scene storage when the project and its owner have room for it, read its view, adjust its minutes."""
    try:
        found = core_bridge.list_generation_files(user, job["generation_id"])
    except GenerationNotFoundException:
        return fail(job, "generation_not_found", "The generation of this scene is no longer available.")
    item = _splat(found)
    if item is None or not item.get("file_path"):
        return fail(job, "no_output", "The generation finished without a splat.")
    file_id = generate_ulid()
    try:
        target, probe = await asyncio.to_thread(_copy, job, item, file_id)
    except FormatError as exc:
        return fail(job, "invalid_output", str(exc))
    except OSError:
        logger.warning("[VIDEO-PRODUCER] Could not copy the splat of scene job %s", job["id"], exc_info=True)
        return fail(job, "output_missing", "The splat of the generation could not be copied.")
    size = target.stat().st_size
    try:
        files.ensure_room(job["project_id"], job["user_id"], size)
    except SceneError as exc:
        target.unlink(missing_ok=True)
        return fail(job, exc.error, exc.message)
    count = item.get("splat_count") if isinstance(item.get("splat_count"), int) else probe.count
    stored = files.add_file(file_id, job["project_id"], job["user_id"], "splat", target.name, size, probe, job_id=job["id"])
    fields = {
        "file_id": file_id,
        "splat_count": count,
        "view": probe.view,
        "progress": 100.0,
        "backend_id": state.get("backend_id") or job.get("backend_id"),
        "started_at": job.get("started_at") or state.get("started_at"),
    }
    if not settle(job["id"], "done", **fields):
        files.delete_file(stored)
        return False
    _adjust(job, generation.state_duration_ms(state))
    return True


async def apply_state(job: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> None:
    """Bring a scene job in line with the status of its generation."""
    status = str(state.get("status") or "").lower()
    if status == "completed":
        await finish_done(job, user, state)
    elif status == "failed":
        code = str(state.get("error_code") or "generation_failed")
        fail(job, code, generation.failure_message(state, error_code=code, admin=generation.is_admin(user), error_id=job.get("generation_id")))
    elif status == "cancelled":
        cancel_local(job)
    elif status == "running":
        update_active(
            job["id"],
            status="running",
            progress=generation.percent(state.get("progress")),
            backend_id=state.get("backend_id") or job.get("backend_id"),
            started_at=job.get("started_at") or state.get("started_at") or storage.now(),
        )


async def follow(owner: Callable[[Optional[str]], Any], unreadable: Any) -> bool:
    """One tracker round over the scene jobs in flight; True while some remain active."""
    for job in list_active():
        user = owner(job.get("user_id"))
        if user is unreadable or not job.get("generation_id"):
            continue
        if user is None:
            fail(job, "user_not_found", "The owner of this scene no longer exists.")
            continue
        try:
            await apply_state(job, user, core_bridge.generation_state(user, job["generation_id"]))
        except GenerationNotFoundException:
            fail(job, "generation_not_found", "The generation of this scene is no longer available.")
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not follow scene generation %s", job["generation_id"], exc_info=True)
    return bool(list_active())


async def cancel(owner: User, job: Mapping[str, Any]) -> Dict[str, Any]:
    """Cancel a queued or running scene job, its generation and its reservation."""
    if job["status"] in ACTIVE:
        if job.get("generation_id"):
            try:
                await core_bridge.cancel_generation(owner, job["generation_id"])
            except GenerationNotFoundException:
                pass
            except Exception:
                logger.warning("[VIDEO-PRODUCER] Could not cancel scene generation %s", job["generation_id"], exc_info=True)
        current = get_job(job["id"])
        if current is not None:
            cancel_local(current)
    return get_job(job["id"]) or dict(job)


def recover() -> int:
    """At startup, fail the jobs a stopped server left before the core took them; returns how many failed."""
    return sum(
        fail(job, "submit_failed", "The server stopped before the scene was started.")
        for job in list_active()
        if not job.get("generation_id")
    )


async def forget_project(owner: Optional[User], project_id: str) -> None:
    """Cancel the jobs of a deleted project and delete their rows."""
    from src.plugin_api import db

    for job in list_project(project_id):
        if job["status"] in ACTIVE:
            if owner is not None:
                await cancel(owner, job)
            else:
                cancel_local(job)
    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {JOBS} WHERE project_id = ?", (project_id,))
