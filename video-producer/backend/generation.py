import asyncio
import logging
import secrets
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from . import cadence, chaining, core_bridge, director, engine_options, estimate, limits, looks, models, notifications, projects, settings, soundtrack, takes, upscalers
from .core_bridge import AccountType, GenerationNotFoundException, IdempotencyKeyConflict, User
from .director import DirectorError, ShotPlan, note
from .estimate import Evaluation

logger = logging.getLogger("plugins.video-producer")

SEED_RANGE = director.SEED_RANGE

MESSAGE_LIMIT = 300

UNCLASSIFIED = "unclassified"

TRACEBACK = "Traceback (most recent call last)"

UPSCALE = "upscale"
RENDER = "render"
GUIDED = "guided"

METHODS = (UPSCALE, RENDER, GUIDED)

RETRYABLE = ("failed", "cancelled")

_SUBMITTING: Set[str] = set()

_PUMP_LOCKS: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}
_QUOTA_LOCKS: Dict[str, threading.Lock] = {}
_QUOTA_LOCKS_GUARD = threading.Lock()


class Blocked(Exception):
    """Takes the plugin refuses to start, with what blocks them."""

    def __init__(self, blocks: List[Dict[str, Any]]):
        super().__init__("; ".join(block["message"] for block in blocks))
        self.blocks = blocks


class TakeError(Exception):
    """A take in a state the asked action does not apply to."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def limit_ref(take_id: str) -> str:
    """The reference a take's GPU minutes are recorded under."""
    return f"video-producer:{take_id}"


def new_seed() -> int:
    """A fresh seed for a take."""
    return secrets.randbelow(SEED_RANGE)


def variant_letter(index: int) -> str:
    """The letter of the n-th variant: A, B, … Z, AA, AB, …"""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _letters() -> Iterator[str]:
    index = 0
    while True:
        yield variant_letter(index)
        index += 1


def next_variants(project_id: str, shot_id: str, quality: str, count: int) -> List[str]:
    """The first count variant letters no take of the shot at this quality uses yet."""
    used = {
        take["variant"]
        for take in takes.list_takes(project_id)
        if take["shot_id"] == shot_id and take["quality"] == quality and take["variant"]
    }
    free: List[str] = []
    for letter in _letters():
        if len(free) == count:
            return free
        if letter not in used:
            free.append(letter)
    return free


def reserves(quota: Mapping[str, Any]) -> bool:
    """True when the user's GPU minutes are limited, so a take must reserve them."""
    return quota.get("limit") is not None and not quota.get("exempt")


def missing_block(missing: List[str]) -> Dict[str, Any]:
    """The block of model fields left without an installed recommended file."""
    return note("missing_models", f"Install a recommended file for: {', '.join(missing)}.", fields=list(missing))


def _require_quota(owner: User, minutes: float) -> bool:
    status = limits.gpu_minutes_status(owner.id)
    remaining = status.get("remaining")
    if reserves(status) and remaining is not None and minutes > float(remaining) + 1e-9:
        raise Blocked([estimate.quota_block({"needed_minutes": round(minutes, 2), "remaining": remaining})])
    return reserves(status)


def _quota_lock(user_id: str) -> threading.Lock:
    with _QUOTA_LOCKS_GUARD:
        return _QUOTA_LOCKS.setdefault(user_id, threading.Lock())


@contextmanager
def reserving(owner: User, minutes: float) -> Iterator[bool]:
    """Hold the user's GPU minutes while the takes that need these minutes in all are created: their remaining minutes read again, Blocked when they no longer fit; yields whether the takes reserve."""
    with _quota_lock(owner.id):
        yield _require_quota(owner, minutes)


async def with_sound(owner: User, project: Mapping[str, Any], plans: List[ShotPlan]) -> None:
    """Cut and store the sound each plan sends, once per plan, the cuts of all of them at most soundtrack.MEASURES at a time; Blocked by the first that cannot be, in the order of the plans."""
    try:
        await soundtrack.attach_all(owner, project, plans)
    except soundtrack.SoundError as exc:
        raise Blocked([note(exc.code, exc.message, shot_id=exc.shot_id)]) from None


def create(
    owner: User,
    project_id: str,
    plan: ShotPlan,
    *,
    preset_id: str,
    quality: str,
    kind: str,
    seed: int,
    variant: str,
    minutes: float,
    parent_take_id: Optional[str] = None,
    revision: Optional[int] = None,
    chain: Optional[Dict[str, Any]] = None,
    frame_role: Optional[str] = None,
) -> Dict[str, Any]:
    """Store one take of a plan, with the GPU minutes it reserves, for a shot that starts from the last image of the previous shot what it waits for, and for a start or end image candidate the image it is made for; Blocked, nothing stored, when the core cannot record the minutes."""
    take_id = core_bridge.generate_ulid()
    reserved = minutes if minutes > 0 else 0.0
    if reserved > 0 and not core_bridge.record_limit_event(owner.id, limits.GPU_MINUTES, reserved, limit_ref(take_id)):
        raise Blocked([note("quota_unrecorded", "The GPU minutes of this take could not be reserved: try again in a moment.", shot_id=plan.shot_id)])
    try:
        return _store(owner, project_id, plan, take_id, reserved, preset_id, quality, kind, seed, variant, parent_take_id, revision, chain, frame_role)
    except Exception:
        if reserved > 0:
            core_bridge.refund_limit_event(limit_ref(take_id))
        raise


def _store(
    owner: User,
    project_id: str,
    plan: ShotPlan,
    take_id: str,
    reserved: float,
    preset_id: str,
    quality: str,
    kind: str,
    seed: int,
    variant: str,
    parent_take_id: Optional[str],
    revision: Optional[int],
    chain: Optional[Dict[str, Any]],
    frame_role: Optional[str],
) -> Dict[str, Any]:
    size = models.parse_size(plan.resolution)
    takes.create_take(
        {
            "id": take_id,
            "project_id": project_id,
            "shot_id": plan.shot_id,
            "user_id": owner.id,
            "quality": quality,
            "kind": kind,
            "parent_take_id": parent_take_id,
            "preset_id": preset_id,
            "mode": plan.preset_mode,
            "director_mode": plan.director_mode,
            "model_id": plan.model_id,
            "seed": seed,
            "resolution": plan.resolution,
            "variant": variant,
            "shot_revision": revision,
            "profile": plan.profile,
            "prompt_text": plan.prompt_text,
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            "duration_s": plan.seconds,
            "fps": plan.fps,
            "request": plan.request_for(take_id, seed),
            "chain": chain,
            "chain_wait": bool(chain) and chain["state"] == chaining.WAITING,
            "frame_role": frame_role,
            "video_refs": plan.video_trace(),
            "track_scale": plan.track_scale,
            "units_reserved": reserved,
        }
    )
    return takes.get_take(take_id)


@contextmanager
def whole_batch(created: List[Dict[str, Any]]) -> Iterator[None]:
    """Create the takes of one request together: when one of them is Blocked, the ones created before it are dropped and their minutes refunded, and the request is refused as a whole."""
    try:
        yield
    except Blocked:
        for take in created:
            _refund(take)
            takes.delete_take(take["id"])
        created.clear()
        raise


async def start(owner: User, project: Mapping[str, Any], evaluation: Evaluation) -> List[Dict[str, Any]]:
    """Create the takes each shot asks for on its own engine, one per variant, and hand what fits to the core."""
    if evaluation.blocked:
        raise Blocked(evaluation.payload["blocks"])
    applies = bool(evaluation.payload["quota"]["applies"])
    await with_sound(owner, project, evaluation.plans.shots)
    batch = core_bridge.generate_ulid()
    places = {clip.get("id"): index for index, clip in enumerate(project["doc"].get("clips") or [])}
    plans = sorted(evaluation.plans.shots, key=lambda plan: places.get(plan.shot_id, len(places)))
    needed = sum(evaluation.minutes.get(plan.shot_id, 0.0) * evaluation.count(plan.shot_id) for plan in plans if not plan.cloud) if applies else 0.0
    created: List[Dict[str, Any]] = []
    with reserving(owner, needed) as reserve, whole_batch(created):
        for plan in plans:
            for index, letter in enumerate(next_variants(project["id"], plan.shot_id, plan.quality, evaluation.count(plan.shot_id))):
                created.append(
                    create(
                        owner,
                        project["id"],
                        plan,
                        preset_id=plan.preset_id,
                        quality=plan.quality,
                        kind=RENDER,
                        seed=new_seed() if plan.seed is None else (plan.seed + index) % SEED_RANGE,
                        variant=letter,
                        minutes=evaluation.minutes.get(plan.shot_id, 0.0) if applies and reserve and not plan.cloud else 0.0,
                        revision=director.shot_revision(project["doc"], plan.shot_id),
                        chain=chaining.record(evaluation.waits.get(plan.shot_id), letter, created, batch),
                    )
                )
    await pump(owner)
    return [takes.get_take(take["id"]) for take in created]


def refusal(exc: Exception) -> Tuple[str, str]:
    """The error code and message of a request the core refused."""
    if isinstance(exc, PermissionError):
        return "preset_not_available", "The preset is not available to you."
    if isinstance(exc, IdempotencyKeyConflict):
        return "duplicate_submission", "This take was already submitted with another request."
    if isinstance(exc, ValueError):
        return "invalid_request", (str(exc) or "The core refused the request.")[:MESSAGE_LIMIT]
    if isinstance(exc, RuntimeError):
        return "no_backend", "No backend can run this take right now."
    return "submit_failed", "The take could not be started."


async def quiet_cancel(user: User, generation_id: str) -> None:
    """Cancel a generation, logging instead of raising when it cannot be cancelled."""
    try:
        await core_bridge.cancel_generation(user, generation_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not cancel generation %s", generation_id, exc_info=True)


async def _submit(user: User, take: Dict[str, Any]) -> bool:
    try:
        submitted = await core_bridge.submit_generation(user, take["request"] or {})
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] The core refused take %s", take["id"], exc_info=True)
        code, message = refusal(exc)
        fail_take(take, code, message)
        return False
    generation_id = str(submitted["generation_id"])
    if takes.attach_generation(take["id"], generation_id):
        takes.add_job(take["id"], generation_id, limit_ref(take["id"]), take["units_reserved"])
        return True
    await quiet_cancel(user, generation_id)
    return False


def _pump_lock(user_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    held = _PUMP_LOCKS.get(user_id)
    if held is None or held[0] is not loop:
        held = (loop, asyncio.Lock())
        _PUMP_LOCKS[user_id] = held
    return held[1]


async def pump(user: Optional[User]) -> int:
    """Hand the user's queued takes, then their queued versions at a frame rate, to the core while they have fewer than max_parallel_jobs of both in flight, one pump at a time per user."""
    if user is None:
        return 0
    async with _pump_lock(user.id):
        return await _pump(user)


async def _pump(user: User) -> int:
    from . import renditions

    free = int(settings.get_setting("max_parallel_jobs")) - takes.in_flight(user.id) - renditions.in_flight(user.id)
    submitted = 0
    for take in takes.waiting(user.id):
        if free <= 0:
            break
        if take["id"] in _SUBMITTING:
            continue
        _SUBMITTING.add(take["id"])
        try:
            started = await _submit(user, take)
        finally:
            _SUBMITTING.discard(take["id"])
        if started:
            free -= 1
            submitted += 1
    return submitted + await renditions.submit(user, free)


def _project_name(project_id: str) -> str:
    project = projects.get_project(project_id)
    return project["name"] if project else "Video Producer"


def _notify(take: Mapping[str, Any], done: bool, message: str = "") -> None:
    name = _project_name(take["project_id"])
    quality = "final" if take.get("quality") == "final" else "draft"
    variant = f" {take['variant']}" if take.get("variant") else ""
    image = "end" if take.get("frame_role") == "last" else "start"
    subject = f"{image} image candidate{variant}" if take.get("kind") == takes.KEYFRAME else f"{quality} take{variant}"
    text = f"{name}: the {subject} is ready." if done else f"{name}: the {subject} failed."
    core_bridge.notify(
        user_id=take.get("user_id"),
        notification_type=notifications.TAKE_DONE if done else notifications.TAKE_FAILED,
        title="Take ready" if done else "Take failed",
        message=f"{text} {message}".strip(),
        level="success" if done else "error",
        metadata={"project_id": take["project_id"], "take_id": take["id"], "shot_id": take["shot_id"]},
    )


def _refund(take: Mapping[str, Any]) -> None:
    if float(take.get("units_reserved") or 0) > 0:
        core_bridge.refund_limit_event(limit_ref(take["id"]))


def fail_take(take: Mapping[str, Any], code: str, message: str) -> bool:
    """End a take as failed, refund its minutes and tell its owner; False when it had already ended."""
    if not takes.settle(take["id"], "failed", error_code=code, error_message=message, step=None, finished_at=takes.now()):
        return False
    _refund(take)
    takes.close_jobs(take["id"])
    _notify(take, done=False, message=message)
    return True


def cancel_local(take: Mapping[str, Any]) -> bool:
    """End a take as cancelled and refund its minutes; False when it had already ended."""
    if not takes.settle(take["id"], "cancelled", step=None, finished_at=takes.now()):
        return False
    _refund(take)
    takes.close_jobs(take["id"])
    return True


def output_of(files: List[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    """The first file of a generation of a kind, video or image, or None."""
    found = [
        item
        for item in files
        if str(item.get("file_type") or "").lower() == kind or str(item.get("mime_type") or "").lower().startswith(f"{kind}/")
    ]
    return found[0] if found else None


def _adjust(take: Mapping[str, Any], duration_ms: Optional[int]) -> None:
    reserved = float(take.get("units_reserved") or 0)
    if reserved <= 0 or not duration_ms or not take.get("user_id"):
        return
    actual = round(duration_ms / 60000, 3)
    ref = limit_ref(take["id"])
    if actual > reserved + 1e-6:
        core_bridge.record_limit_event(take["user_id"], limits.GPU_MINUTES, round(actual - reserved, 3), f"{ref}:adjust")
    elif actual < reserved - 1e-6:
        if core_bridge.refund_limit_event(ref) > 0:
            core_bridge.record_limit_event(take["user_id"], limits.GPU_MINUTES, actual, f"{ref}:actual")
        else:
            logger.warning("[VIDEO-PRODUCER] Take %s keeps its %s reserved minutes: the core did not refund them, so its %s actual minutes are not recorded", take["id"], reserved, actual)


def state_duration_ms(state: Mapping[str, Any]) -> Optional[int]:
    """How long a generation ran, in milliseconds, or None when its state does not say."""
    value = state.get("duration_ms")
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def finish_done(take: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> bool:
    """End a take whose generation completed: its video (its image for a start image candidate), thumbnail, calibration, quota adjustment and notification."""
    try:
        files = core_bridge.list_generation_files(user, take["generation_id"])
    except GenerationNotFoundException:
        return fail_take(take, "generation_not_found", "The generation of this take is no longer available.")
    keyframe = take.get("kind") == takes.KEYFRAME
    output = output_of(files, "image" if keyframe else "video")
    if output is None:
        missing = "an image" if keyframe else "a video"
        return fail_take(take, "no_output", f"The generation finished without {missing}.")
    backend_id = state.get("backend_id") or take.get("backend_id")
    fields = {
        "file_path": output.get("file_path"),
        "file_id": None if output.get("id") is None else str(output["id"]),
        "thumb_path": output.get("thumbnail_medium"),
        "width": output.get("width") or take.get("width"),
        "height": output.get("height") or take.get("height"),
        "duration_s": output.get("duration_seconds") or take.get("duration_s"),
        "fps": output.get("fps") or take.get("fps"),
        "backend_id": backend_id,
        "progress": 100.0,
        "step": None,
        "started_at": take.get("started_at") or state.get("started_at"),
        "finished_at": takes.now(),
    }
    if not takes.settle(take["id"], "done", **fields):
        return False
    duration_ms = state_duration_ms(state)
    seconds = 1.0 if keyframe else float(take.get("duration_s") or 0)
    if duration_ms and backend_id and seconds > 0 and take.get("resolution") and take.get("preset_id"):
        takes.add_calibration(take["preset_id"], backend_id, take["resolution"], seconds * engine_options.take_scale(take) * takes.track_scale(take), duration_ms)
    _adjust(take, duration_ms)
    takes.close_jobs(take["id"])
    _notify(take, done=True)
    looks.queue_take(take)
    return True


def percent(value: Any) -> Optional[float]:
    """A progress the core reports, as a fraction or a percentage, as a percentage from 0 to 100."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    percent = float(value) * 100 if 0 <= value <= 1 else float(value)
    return round(min(max(percent, 0.0), 100.0), 1)


def _clean(text: Any) -> str:
    text = str(text or "")
    if TRACEBACK in text:
        text = text[: text.index(TRACEBACK)]
    return text.strip()[:MESSAGE_LIMIT].strip()


def failure_message(
    state: Mapping[str, Any],
    hook_message: Optional[str] = None,
    error_code: Optional[str] = None,
    admin: bool = False,
    error_id: Optional[str] = None,
) -> str:
    """The most telling reason a generation failed, in the order hook message, user message, stored message, then, for an administrator only, the raw error without traceback; for anyone else an unclassified failure keeps the fullest core message and its error ID."""
    summary = _clean(state.get("error_message"))
    raw = _clean(str(state.get("error_detail") or "").split("\n\n", 1)[0]) if admin else ""
    candidates = [
        text
        for text in (_clean(hook_message), _clean(state.get("error_user_message")), summary, raw)
        if text
    ]
    generic = (error_code or state.get("error_code")) == UNCLASSIFIED and bool(summary)
    telling = [text for text in candidates if not (generic and text.startswith(summary) and text != raw)]
    if telling:
        return telling[0]
    fullest = max(candidates, key=len) if candidates else _clean(state.get("message")) or "The generation failed."
    return f"{fullest}\nError ID: {error_id}" if generic and not admin and error_id else fullest


def is_admin(user: Optional[User]) -> bool:
    """True for an administrator."""
    return getattr(user, "account_type", None) == AccountType.ADMIN


def apply_state(take: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> None:
    """Bring a take in line with the status of its generation."""
    status = str(state.get("status") or "").lower()
    if status == "completed":
        finish_done(take, user, state)
    elif status == "failed":
        code = str(state.get("error_code") or "generation_failed")
        fail_take(take, code, failure_message(state, error_code=code, admin=is_admin(user), error_id=take.get("generation_id")))
    elif status == "cancelled":
        cancel_local(take)
    elif status == "running":
        takes.update_active(
            take["id"],
            status="running",
            progress=percent(state.get("progress")),
            step=state.get("current_step") or state.get("message"),
            backend_id=state.get("backend_id") or take.get("backend_id"),
            started_at=take.get("started_at") or state.get("started_at") or takes.now(),
        )
    elif state.get("backend_id") and not take.get("backend_id"):
        takes.update_active(take["id"], backend_id=state["backend_id"])


def _quiet_state(take: Mapping[str, Any]) -> Tuple[Optional[User], Dict[str, Any]]:
    user = None
    try:
        user = core_bridge.get_user(take["user_id"])
        return user, core_bridge.generation_state(user, take["generation_id"]) if user is not None else {}
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read generation %s", take.get("generation_id"), exc_info=True)
        return user, {}


def settle_from_hook(
    generation_id: Any,
    status: str,
    *,
    duration: Any = None,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
) -> bool:
    """End the take, or the version at a frame rate, of a generation the core reports finished; False when nothing is waiting on it."""
    take = takes.take_for_generation(str(generation_id or ""))
    if take is None:
        from . import renditions

        return renditions.settle_from_hook(generation_id, status, duration=duration, error_code=error_code, message=message)
    if take["status"] not in takes.ACTIVE:
        return False
    if status == "cancelled":
        return cancel_local(take)
    if status not in ("completed", "failed"):
        return False
    if status == "failed":
        user, state = _quiet_state(take)
        code = str(error_code or state.get("error_code") or "generation_failed")
        reason = failure_message(state, message, code, admin=is_admin(user), error_id=take.get("generation_id"))
        return fail_take(take, code, reason)
    user = core_bridge.get_user(take["user_id"])
    if user is None:
        return fail_take(take, "user_not_found", "The owner of this take no longer exists.")
    try:
        state = core_bridge.generation_state(user, take["generation_id"])
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read generation %s", generation_id, exc_info=True)
        state = {}
    if not state_duration_ms(state) and isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        state = {**state, "duration_ms": int(duration * 1000)}
    return finish_done(take, user, state)


async def cancel(owner: User, take: Mapping[str, Any]) -> Dict[str, Any]:
    """Cancel a queued or running take, its generation and its reservation."""
    if take["status"] in takes.ACTIVE:
        if take.get("generation_id"):
            try:
                await core_bridge.cancel_generation(owner, take["generation_id"])
            except GenerationNotFoundException:
                pass
            except Exception:
                logger.warning("[VIDEO-PRODUCER] Could not cancel generation %s", take["generation_id"], exc_info=True)
        current = takes.get_take(take["id"])
        if current is not None:
            cancel_local(current)
    return takes.get_take(take["id"])


async def delete(owner: User, take: Mapping[str, Any]) -> bool:
    """Delete a take with its versions at a frame rate, cancelling them first while they are queued or running; the host generations are kept."""
    from . import renditions

    if take["status"] in takes.ACTIVE:
        await cancel(owner, take)
    await renditions.drop_for_take(owner, take["id"])
    return takes.delete_take(take["id"])


def _checked(plan: ShotPlan, preset_id: str, native: bool, owner: User, backend_id: Optional[str]) -> float:
    if plan.missing_models:
        raise Blocked([missing_block(plan.missing_models)])
    if not native:
        return 0.0
    minutes = estimate.plan_minutes(plan, preset_id, backend_id)
    _require_quota(owner, minutes)
    return minutes


async def _render_plan(
    owner: User, project: Mapping[str, Any], source: Mapping[str, Any], quality: str, found: Optional[Mapping[str, chaining.Wait]] = None
) -> Tuple[ShotPlan, str, bool]:
    plans = await soundtrack.heard_plans(
        owner,
        project["id"],
        project["doc"],
        [source["shot_id"]],
        source["preset_id"],
        quality,
        source.get("model_id"),
        source.get("profile"),
        chained=chaining.chain_map(found or {}),
    )
    if plans.blocks:
        raise Blocked(plans.blocks)
    return plans.shots[0], plans.shots[0].preset_id, not plans.shots[0].cloud


def _upscale_plan(
    owner: User, source: Mapping[str, Any], target: str, upscaler: str = upscalers.AUTO, rtx_source: str = upscalers.DEFAULT_RTX_SOURCE
) -> Tuple[ShotPlan, str, bool]:
    try:
        plan = director.build_upscale(owner, source, target, upscaler, rtx_source)
    except DirectorError as exc:
        raise Blocked([exc.note()]) from None
    return plan, plan.request["preset_id"], True


async def _guided_plan(owner: User, project: Mapping[str, Any], source: Mapping[str, Any]) -> Tuple[ShotPlan, str, bool]:
    try:
        sound = await asyncio.to_thread(director.draft_sound, owner, project["doc"], source)
        plan = director.build_guided(owner, project["doc"], source, sound)
    except DirectorError as exc:
        raise Blocked([exc.note()]) from None
    return plan, plan.request["preset_id"], True


async def final_plan(
    owner: User,
    project: Mapping[str, Any],
    source: Mapping[str, Any],
    method: str,
    target: str,
    upscaler: str = upscalers.AUTO,
    rtx_source: str = upscalers.DEFAULT_RTX_SOURCE,
) -> Tuple[ShotPlan, str, bool]:
    """The plan of the final take of a finished take, its preset and whether a native backend runs it."""
    if source.get("kind") == takes.KEYFRAME:
        raise TakeError(409, "keyframe_take", "A start image candidate has no final take: use it as a frame of its shot.")
    if source["status"] != "done":
        raise TakeError(409, "take_not_done", "Only a finished take can be made final.")
    if method == UPSCALE:
        return _upscale_plan(owner, source, upscalers.resolve_target(target, project.get("doc") or {}, source), upscaler, rtx_source)
    if method == GUIDED:
        return await _guided_plan(owner, project, source)
    return await _render_plan(owner, project, source, "final")


async def with_first(owner: User, pairs: List[Tuple[Mapping[str, Any], ShotPlan]]) -> None:
    """Bind the first frame of the video of its take to each guided plan that has none yet, stored as the owner's upload; Blocked by the first that cannot be, in the order of the plans."""
    for source, plan in pairs:
        if not director.is_guided(plan) or director.has_first(plan):
            continue
        ref = {"kind": "history", "generation_id": str(source.get("generation_id")), "file_id": str(source.get("file_id"))}
        try:
            stored = await core_bridge.extract_frame(owner, ref, at=0.0)
            director.bind_first(owner, plan, {"value": stored["value"], "media_type": "image"})
        except DirectorError as exc:
            raise Blocked([exc.note()]) from None
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not take the first frame of take %s", source.get("id"), exc_info=True)
            raise Blocked([note("guided_frame_failed", "The first frame of the take could not be taken.", shot_id=plan.shot_id)]) from None


def create_final(
    owner: User, project: Mapping[str, Any], source: Mapping[str, Any], method: str, plan: ShotPlan, preset_id: str, minutes: float
) -> Dict[str, Any]:
    """Store the final take of a finished take: its seed and letter, linked to it, the revision of the shot when it is rendered again, the revision of the take when it follows or enlarges its video."""
    return create(
        owner,
        project["id"],
        plan,
        preset_id=preset_id,
        quality="final",
        kind=method,
        seed=int(source["seed"]) if source.get("seed") is not None else new_seed(),
        variant=source.get("variant") or variant_letter(0),
        minutes=minutes,
        parent_take_id=source["id"],
        revision=director.shot_revision(project["doc"], source["shot_id"]) if method == RENDER else source.get("shot_revision"),
    )


async def final(
    owner: User,
    project: Mapping[str, Any],
    source: Mapping[str, Any],
    method: str,
    target: str,
    upscaler: str = upscalers.AUTO,
    rtx_source: str = upscalers.DEFAULT_RTX_SOURCE,
    conform: bool = False,
) -> Dict[str, Any]:
    """A final take of a finished take, with its version at the frame rate its shot needs after it when asked."""
    from . import renditions

    plan, preset_id, native = await final_plan(owner, project, source, method, target, upscaler, rtx_source)
    if conform:
        needed, interpolator = renditions.interpolator_for(owner, project.get("doc") or {}, plan.fps, clip=renditions.shot_of(project, source["shot_id"]))
        if needed and interpolator is None:
            raise Blocked([cadence.missing_note(cadence.choice_of(project.get("doc") or {}))])
    minutes = _checked(plan, preset_id, native, owner, source.get("backend_id"))
    await with_sound(owner, project, [plan])
    await with_first(owner, [(source, plan)])
    with reserving(owner, minutes) as reserve:
        take = create_final(owner, project, source, method, plan, preset_id, minutes if reserve else 0.0)
    if conform:
        renditions.order_quietly(owner, project, take)
    await pump(owner)
    return takes.get_take(take["id"])


async def retry(owner: User, project: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    """A new take like a failed or cancelled one: same shot, seed, quality and preset; a rendered take of a shot that starts from the last image of the previous shot waits for it again, and a take that was to have a version at the film's frame rate orders it again."""
    if source["status"] not in RETRYABLE:
        raise TakeError(409, "take_not_retryable", "Only a failed or cancelled take can be retried.")
    found: Dict[str, chaining.Wait] = {}
    parent = None
    if source["kind"] == UPSCALE:
        parent = takes.get_take(source.get("parent_take_id") or "")
        if parent is None or parent["status"] != "done":
            raise TakeError(409, "take_not_done", "The take this one upscaled is no longer finished.")
        plan, preset_id, native = _upscale_plan(
            owner, parent, director.upscale_target(source), upscalers.of_preset(source.get("preset_id")), director.upscale_rtx_source(source)
        )
        revision = parent.get("shot_revision")
    elif source["kind"] == GUIDED:
        parent = takes.get_take(source.get("parent_take_id") or "")
        if parent is None or parent["status"] != "done":
            raise TakeError(409, "take_not_done", "The take this one followed is no longer finished.")
        plan, preset_id, native = await _guided_plan(owner, project, parent)
        revision = parent.get("shot_revision")
    else:
        found = chaining.waits(project["id"], project["doc"], [source["shot_id"]])
        plan, preset_id, native = await _render_plan(owner, project, source, source["quality"], found)
        revision = director.shot_revision(project["doc"], source["shot_id"])
    minutes = _checked(plan, preset_id, native, owner, source.get("backend_id"))
    await with_sound(owner, project, [plan])
    if parent is not None:
        await with_first(owner, [(parent, plan)])
    with reserving(owner, minutes) as reserve:
        take = create(
            owner,
            project["id"],
            plan,
            preset_id=preset_id,
            quality=source["quality"],
            kind=source["kind"],
            seed=int(source["seed"]) if source.get("seed") is not None else new_seed(),
            variant=source.get("variant") or variant_letter(0),
            minutes=minutes if reserve else 0.0,
            parent_take_id=source.get("parent_take_id"),
            revision=revision,
            chain=chaining.record(found.get(plan.shot_id) if plan.chain else None, source.get("variant") or variant_letter(0), [], core_bridge.generate_ulid()),
        )
    from . import renditions

    if renditions.list_for_take(source["id"]):
        renditions.order_quietly(owner, project, take)
    await pump(owner)
    return takes.get_take(take["id"])
