import json
import logging
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from . import cadence, core_bridge, generation, notifications, takes
from .core_bridge import GenerationNotFoundException, User, generate_ulid
from .director import DirectorError, note

logger = logging.getLogger("plugins.video-producer")

RENDITIONS = "video_producer_renditions"

WAITING = "waiting"
QUEUED = "queued"
RUNNING = "running"
DONE = "done"

ACTIVE = (WAITING, QUEUED, RUNNING)

COLUMNS = (
    "id",
    "project_id",
    "shot_id",
    "take_id",
    "user_id",
    "fps",
    "source_fps",
    "interpolator",
    "preset_id",
    "mode",
    "resolution",
    "status",
    "generation_id",
    "request",
    "file_path",
    "file_id",
    "width",
    "height",
    "duration_s",
    "backend_id",
    "progress",
    "step",
    "error_code",
    "error_message",
    "created_at",
    "started_at",
    "finished_at",
    "factor",
    "source_rendition_id",
)

PUBLIC = (
    "id",
    "take_id",
    "shot_id",
    "fps",
    "source_fps",
    "interpolator",
    "factor",
    "source_rendition_id",
    "status",
    "progress",
    "step",
    "width",
    "height",
    "duration_s",
    "error_code",
    "error_message",
    "url",
    "created_at",
    "finished_at",
)

_ACTIVE_SQL = "status IN ('waiting', 'queued', 'running')"

_IN_CORE_SQL = "status IN ('queued', 'running')"

_READY_SQL = "status = 'queued' AND generation_id IS NULL"

_SELECT = f"SELECT {', '.join(COLUMNS)} FROM {RENDITIONS}"

_SUBMITTING: Set[str] = set()


class Refused(Exception):
    """A take that cannot be brought to the film's frame rate, with the block that says why."""

    def __init__(self, block: Dict[str, Any]):
        super().__init__(block["message"])
        self.block = block


def _rendition(row: Any) -> Dict[str, Any]:
    found = {column: row[column] for column in COLUMNS}
    found["request"] = json.loads(found["request"]) if found["request"] else None
    return found


def public(rendition: Mapping[str, Any]) -> Dict[str, Any]:
    """A version at the film's frame rate as the API returns it, with the URL of its video."""
    url = None
    if rendition.get("generation_id") and rendition.get("file_path"):
        name = str(rendition["file_path"]).replace("\\", "/").rsplit("/", 1)[-1]
        url = f"/api/media/generations/{rendition['generation_id']}/{name}"
    values = {**rendition, "url": url}
    return {key: values.get(key) for key in PUBLIC}


def _fetch_all(query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [_rendition(row) for row in rows]


def get(rendition_id: str) -> Optional[Dict[str, Any]]:
    """One version at a frame rate, or None."""
    found = _fetch_all(f"{_SELECT} WHERE id = ?", (rendition_id,))
    return found[0] if found else None


def for_generation(generation_id: str) -> Optional[Dict[str, Any]]:
    """The version a generation makes, or None."""
    if not generation_id:
        return None
    found = _fetch_all(f"{_SELECT} WHERE generation_id = ? ORDER BY created_at DESC LIMIT 1", (generation_id,))
    return found[0] if found else None


def list_for_project(project_id: str) -> List[Dict[str, Any]]:
    """The versions at a frame rate of a project's takes, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE project_id = ? ORDER BY created_at, id", (project_id,))


def list_for_take(take_id: str) -> List[Dict[str, Any]]:
    """The versions of one take, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE take_id = ? ORDER BY created_at, id", (take_id,))


def list_active() -> List[Dict[str, Any]]:
    """The versions waiting for their take, queued or running, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE {_ACTIVE_SQL} ORDER BY created_at, id")


def ready_to_submit(user_id: str) -> List[Dict[str, Any]]:
    """The user's queued versions not yet handed to the core, oldest first."""
    return _fetch_all(f"{_SELECT} WHERE user_id = ? AND {_READY_SQL} ORDER BY created_at, id", (user_id,))


def ready_user_ids() -> List[str]:
    """The users with queued versions not yet handed to the core."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT DISTINCT user_id FROM {RENDITIONS} WHERE {_READY_SQL} AND user_id IS NOT NULL")
        return [row["user_id"] for row in cursor.fetchall()]


def in_flight(user_id: str) -> int:
    """How many of the user's versions the core is making or holds in its queue."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM {RENDITIONS} WHERE user_id = ? AND generation_id IS NOT NULL AND {_IN_CORE_SQL}",
            (user_id,),
        )
        return int(cursor.fetchone()["count"])


def _update(rendition_id: str, fields: Dict[str, Any], condition: str) -> bool:
    from src.plugin_api import db

    names = [name for name in fields if name in COLUMNS and name != "id"]
    values = [json.dumps(fields[name]) if name == "request" and fields[name] is not None else fields[name] for name in names]
    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {RENDITIONS} SET {', '.join(f'{name} = ?' for name in names)} WHERE id = ? AND {condition}",
            (*values, rendition_id),
        )
        return cursor.rowcount == 1


def settle(rendition_id: str, status: str, **fields: Any) -> bool:
    """End a version still waiting, queued or running; True only for the caller that ended it."""
    return _update(rendition_id, {**fields, "status": status, "step": None, "finished_at": takes.now()}, _ACTIVE_SQL)


def _create(fields: Dict[str, Any]) -> Dict[str, Any]:
    from src.plugin_api import db

    row = {column: None for column in COLUMNS}
    row.update({"id": generate_ulid(), "created_at": takes.now()})
    row.update({key: value for key, value in fields.items() if key in COLUMNS})
    values = {**row, "request": json.dumps(row["request"]) if row["request"] else None}
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {RENDITIONS} ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
            tuple(values[column] for column in COLUMNS),
        )
    return get(row["id"])


def _same_fps(a: Any, b: Any) -> bool:
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(float(a) - float(b)) < 1e-6


def current_for(take_id: str, fps: Any) -> Optional[Dict[str, Any]]:
    """The version of a take at a frame rate that is finished or still on its way, newest first; None when there is none."""
    return next(
        (item for item in reversed(list_for_take(take_id)) if _same_fps(item["fps"], fps) and item["status"] in (*ACTIVE, DONE)),
        None,
    )


def _source_fields(take: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "source_fps": take.get("fps"),
        "resolution": size_of(take),
        "width": take.get("width"),
        "height": take.get("height"),
        "duration_s": take.get("duration_s"),
    }


def size_of(take: Mapping[str, Any]) -> Optional[str]:
    """The size of a take's video as "WxH", its asked resolution when the video's is unknown."""
    width, height = take.get("width"), take.get("height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return f"{width}x{height}"
    return take.get("resolution")


def _request(user: User, source: Mapping[str, Any], fps: float, interpolator: str, rendition_id: str, factor: Optional[int] = None) -> Dict[str, Any]:
    try:
        request, missing = cadence.build_request(user, source, fps, interpolator, factor)
    except DirectorError as exc:
        raise Refused(exc.note()) from None
    if missing:
        raise Refused(generation.missing_block(missing))
    return {**request, "idempotency_key": f"vp:rendition:{rendition_id}"}


def shot_of(project: Mapping[str, Any], shot_id: Any) -> Optional[Dict[str, Any]]:
    """The shot of the film with this id, or None."""
    return next((clip for clip in (project.get("doc") or {}).get("clips") or [] if clip.get("id") == shot_id), None)


def placed_take(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[str]:
    """The id of the take a shot shows, read from its asset; None when it shows no take."""
    asset = next((item for item in doc.get("assets") or [] if item.get("id") == clip.get("assetId")), None)
    result = (asset or {}).get("resultId")
    return str(result) if result else None


def _row(owner: User, project: Mapping[str, Any], take: Mapping[str, Any], fps: float, interpolator: str, factor: Optional[int], source: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    rendition_id = generate_ulid()
    fields: Dict[str, Any] = {
        "id": rendition_id,
        "project_id": project["id"],
        "shot_id": take["shot_id"],
        "take_id": take["id"],
        "user_id": owner.id,
        "fps": float(fps),
        "interpolator": interpolator,
        "preset_id": cadence.PRESET_OF[interpolator],
        "mode": cadence.MODE,
        "status": WAITING,
        "factor": factor,
        "source_rendition_id": source["id"] if source is not None else None,
        **_source_fields(take),
    }
    ready = source["status"] == DONE if source is not None else take["status"] == "done"
    if ready:
        fields.update(status=QUEUED, request=_request(owner, source if source is not None else take, fps, interpolator, rendition_id, factor))
    return _create(fields)


def order(
    owner: User, project: Mapping[str, Any], take: Mapping[str, Any], choice: Optional[str] = None, clip: Optional[Mapping[str, Any]] = None
) -> Dict[str, Any]:
    """Bring a take to the frame rate a shot needs, the film's divided by its speed (the film's without a shot): the version already finished or on its way, else a new one, queued for a finished take and waiting for one still being made; past the frame rates an interpolator takes, a multiple of the film's rate made from the version at the film's rate, ordered as well when the take does not run at it; Refused when the take cannot be."""
    doc = project.get("doc") or {}
    film = cadence.target_of(doc)
    if film is None:
        raise Refused(note("cadence_unknown", "The frame rate of the film is not one a take can be brought to."))
    if take.get("kind") == takes.KEYFRAME:
        raise Refused(note("keyframe_take", "A start image candidate has no frame rate."))
    if take["status"] not in ("done", *takes.ACTIVE):
        raise Refused(note("take_not_done", "Only a finished take, or one still being made, can be brought to the film's frame rate."))
    fps = cadence.needed_fps(doc, clip, take.get("fps"))
    if fps is None:
        raise Refused(note("not_slower", "This take is not slower than its shot: the export plays it as it is.", fps=take.get("fps")))
    found = current_for(take["id"], fps)
    if found is not None:
        return found
    chosen = cadence.choice_of(doc) if choice is None else choice
    interpolator = cadence.pick(chosen, cadence.ready(owner))
    if interpolator is None:
        raise Refused(cadence.missing_note(chosen))
    steps = cadence.passes(take.get("fps"), fps, film)
    source: Optional[Dict[str, Any]] = None
    if len(steps) == 2:
        source = current_for(take["id"], steps[0][0]) or _row(owner, project, take, steps[0][0], interpolator, None, None)
    rate, factor = steps[-1]
    return _row(owner, project, take, rate, interpolator, factor, source)


def interpolator_for(
    owner: User, doc: Mapping[str, Any], take_fps: Any, choice: Optional[str] = None, clip: Optional[Mapping[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """Whether a take at this frame rate needs a version on its shot, and the interpolator that would make it, None when none is ready."""
    if cadence.needed_fps(doc, clip, take_fps) is None:
        return False, None
    return True, cadence.pick(cadence.choice_of(doc) if choice is None else choice, cadence.ready(owner))


def order_quietly(owner: User, project: Mapping[str, Any], take: Mapping[str, Any], choice: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Order the version a new take needs on its shot when it needs one; None when it does not or cannot have one."""
    try:
        return order(owner, project, take, choice, shot_of(project, take.get("shot_id")))
    except Refused as exc:
        if exc.block["code"] != "not_slower":
            logger.warning("[VIDEO-PRODUCER] Take %s gets no version at a frame rate: %s", take.get("id"), exc.block["message"])
        return None


def _prepare(rendition: Mapping[str, Any]) -> None:
    take = takes.get_take(rendition["take_id"])
    if take is None or take["status"] in ("failed", "cancelled"):
        settle(rendition["id"], "cancelled", error_code="take_ended", error_message="The take this version was waiting for did not finish.")
        return
    source = get(rendition["source_rendition_id"]) if rendition.get("source_rendition_id") else None
    if rendition.get("source_rendition_id") and (source is None or source["status"] in ("failed", "cancelled")):
        settle(rendition["id"], "cancelled", error_code="source_ended", error_message="The version at the film's frame rate this version was made from did not finish.")
        return
    if take["status"] != "done" or (source is not None and source["status"] != DONE):
        return
    user = core_bridge.get_user(rendition["user_id"]) if rendition.get("user_id") else None
    if user is None:
        fail(rendition, "user_not_found", "The owner of this version no longer exists.")
        return
    try:
        request = _request(user, source or take, float(rendition["fps"]), rendition["interpolator"], rendition["id"], rendition.get("factor"))
    except Refused as exc:
        fail(rendition, exc.block["code"], exc.block["message"])
        return
    _update(rendition["id"], {**_source_fields(take), "request": request, "status": QUEUED}, f"status = '{WAITING}'")


async def submit(user: User, free: int) -> int:
    """Hand the user's queued versions to the core while slots are free; how many were handed."""
    submitted = 0
    for rendition in ready_to_submit(user.id):
        if free - submitted <= 0:
            break
        if rendition["id"] in _SUBMITTING:
            continue
        _SUBMITTING.add(rendition["id"])
        try:
            started = await _submit(user, rendition)
        finally:
            _SUBMITTING.discard(rendition["id"])
        submitted += int(started)
    return submitted


async def _submit(user: User, rendition: Mapping[str, Any]) -> bool:
    try:
        submitted = await core_bridge.submit_generation(user, rendition["request"] or {})
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] The core refused version %s", rendition["id"], exc_info=True)
        code, message = generation.refusal(exc)
        fail(rendition, code, message)
        return False
    generation_id = str(submitted["generation_id"])
    if _update(rendition["id"], {"generation_id": generation_id}, _READY_SQL):
        return True
    await generation.quiet_cancel(user, generation_id)
    return False


def _notify_failed(rendition: Mapping[str, Any], message: str) -> None:
    take = takes.get_take(rendition["take_id"]) or {}
    variant = f" {take['variant']}" if take.get("variant") else ""
    fps = rendition.get("fps")
    rate = f"{fps:g}" if isinstance(fps, (int, float)) else "?"
    core_bridge.notify(
        user_id=rendition.get("user_id"),
        notification_type=notifications.TAKE_FAILED,
        title="Frame rate version failed",
        message=f"The {rate} fps version of take{variant} failed. {message}".strip(),
        level="error",
        metadata={"project_id": rendition["project_id"], "take_id": rendition["take_id"], "shot_id": rendition["shot_id"], "rendition_id": rendition["id"]},
    )


def fail(rendition: Mapping[str, Any], code: str, message: str) -> bool:
    """End a version as failed and tell its owner; False when it had already ended."""
    if not settle(rendition["id"], "failed", error_code=code, error_message=message):
        return False
    _notify_failed(rendition, message)
    return True


def _finish(rendition: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> bool:
    try:
        files = core_bridge.list_generation_files(user, rendition["generation_id"])
    except GenerationNotFoundException:
        return fail(rendition, "generation_not_found", "The generation of this version is no longer available.")
    output = generation.output_of(files, "video")
    if output is None:
        return fail(rendition, "no_output", "The generation finished without a video.")
    backend_id = state.get("backend_id") or rendition.get("backend_id")
    fields = {
        "file_path": output.get("file_path"),
        "file_id": None if output.get("id") is None else str(output["id"]),
        "width": output.get("width") or rendition.get("width"),
        "height": output.get("height") or rendition.get("height"),
        "duration_s": output.get("duration_seconds") or rendition.get("duration_s"),
        "backend_id": backend_id,
        "progress": 100.0,
        "started_at": rendition.get("started_at") or state.get("started_at"),
    }
    if not settle(rendition["id"], DONE, **fields):
        return False
    duration_ms = generation.state_duration_ms(state)
    seconds = float(rendition.get("duration_s") or 0)
    if duration_ms and backend_id and seconds > 0 and rendition.get("resolution") and rendition.get("preset_id"):
        takes.add_calibration(rendition["preset_id"], backend_id, rendition["resolution"], seconds, duration_ms)
    return True


def apply_state(rendition: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> None:
    """Bring a version in line with the status of its generation."""
    status = str(state.get("status") or "").lower()
    if status == "completed":
        _finish(rendition, user, state)
    elif status == "failed":
        code = str(state.get("error_code") or "generation_failed")
        fail(rendition, code, generation.failure_message(state, error_code=code, admin=generation.is_admin(user), error_id=rendition.get("generation_id")))
    elif status == "cancelled":
        settle(rendition["id"], "cancelled")
    elif status == "running":
        _update(
            rendition["id"],
            {
                "status": RUNNING,
                "progress": generation.percent(state.get("progress")),
                "step": state.get("current_step") or state.get("message"),
                "backend_id": state.get("backend_id") or rendition.get("backend_id"),
                "started_at": rendition.get("started_at") or state.get("started_at") or takes.now(),
            },
            _IN_CORE_SQL,
        )


def settle_from_hook(
    generation_id: Any, status: str, *, duration: Any = None, error_code: Optional[str] = None, message: Optional[str] = None
) -> bool:
    """End the version of a generation the core reports finished; False when no version is waiting on it."""
    rendition = for_generation(str(generation_id or ""))
    if rendition is None or rendition["status"] not in ACTIVE:
        return False
    if status == "cancelled":
        return settle(rendition["id"], "cancelled")
    if status not in ("completed", "failed"):
        return False
    user = core_bridge.get_user(rendition["user_id"]) if rendition.get("user_id") else None
    if user is None:
        return fail(rendition, "user_not_found", "The owner of this version no longer exists.")
    try:
        state = core_bridge.generation_state(user, rendition["generation_id"])
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read generation %s", generation_id, exc_info=True)
        state = {}
    if status == "failed":
        code = str(error_code or state.get("error_code") or "generation_failed")
        return fail(rendition, code, generation.failure_message(state, message, code, admin=generation.is_admin(user), error_id=rendition.get("generation_id")))
    if not generation.state_duration_ms(state) and isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        state = {**state, "duration_ms": int(duration * 1000)}
    return _finish(rendition, user, state)


async def follow(owner: Callable[[Optional[str]], Any], unreadable: Any) -> bool:
    """One round of the tracker over the versions: make ready the ones whose take finished, follow the ones the core runs, hand the queued ones to the core; True while any remains active."""
    for rendition in list_active():
        if rendition["status"] == WAITING:
            _prepare(rendition)
            continue
        if not rendition.get("generation_id"):
            continue
        user = owner(rendition.get("user_id"))
        if user is unreadable:
            continue
        if user is None:
            fail(rendition, "user_not_found", "The owner of this version no longer exists.")
            continue
        try:
            apply_state(rendition, user, core_bridge.generation_state(user, rendition["generation_id"]))
        except GenerationNotFoundException:
            fail(rendition, "generation_not_found", "The generation of this version is no longer available.")
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not follow generation %s", rendition["generation_id"], exc_info=True)
    for user_id in ready_user_ids():
        user = owner(user_id)
        if user is not None and user is not unreadable:
            await generation.pump(user)
    return bool(list_active())


async def cancel(owner: User, rendition: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Cancel a version still waiting, queued or running, with its generation."""
    if rendition["status"] in ACTIVE:
        if rendition.get("generation_id"):
            try:
                await core_bridge.cancel_generation(owner, rendition["generation_id"])
            except GenerationNotFoundException:
                pass
            except Exception:
                logger.warning("[VIDEO-PRODUCER] Could not cancel generation %s", rendition["generation_id"], exc_info=True)
        settle(rendition["id"], "cancelled")
    return get(rendition["id"])


async def drop_for_take(owner: User, take_id: str) -> int:
    """Cancel the versions of a take still on their way and delete them all; how many were deleted."""
    from src.plugin_api import db

    for rendition in list_for_take(take_id):
        if rendition["status"] in ACTIVE:
            await cancel(owner, rendition)
    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {RENDITIONS} WHERE take_id = ?", (take_id,))
        return cursor.rowcount


def shot_versions(project_id: str, doc: Mapping[str, Any], found: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The finished version each shot of the film reads, keyed by shot id: the newest at the frame rate the shot needs for the finished take it shows, the film's divided by its speed."""
    done = {take["id"]: take for take in found if take.get("status") == "done"}
    wanted: Dict[str, Tuple[str, float]] = {}
    for clip in doc.get("clips") or []:
        take = done.get(placed_take(doc, clip) or "")
        fps = cadence.needed_fps(doc, clip, take.get("fps")) if take is not None else None
        if fps is not None:
            wanted[clip["id"]] = (take["id"], fps)
    if not wanted:
        return {}
    versions: Dict[Tuple[str, float], Dict[str, Any]] = {}
    for item in list_for_project(project_id):
        if item["status"] == DONE and item.get("file_path") and isinstance(item.get("fps"), (int, float)):
            versions[(item["take_id"], round(float(item["fps"]), 6))] = item
    return {
        shot_id: versions[(take_id, round(float(fps), 6))]
        for shot_id, (take_id, fps) in wanted.items()
        if (take_id, round(float(fps), 6)) in versions
    }
