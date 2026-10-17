import asyncio
import logging
import secrets
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from . import core_bridge, director, estimate, limits, models, notifications, projects, settings, takes
from .core_bridge import AccountType, GenerationNotFoundException, IdempotencyKeyConflict, User
from .director import DirectorError, ShotPlan, note
from .estimate import Evaluation

logger = logging.getLogger("plugins.video-producer")

SEED_RANGE = 2**31

MESSAGE_LIMIT = 300

UNCLASSIFIED = "unclassified"

TRACEBACK = "Traceback (most recent call last)"

UPSCALE = "upscale"
RENDER = "render"

METHODS = (UPSCALE, RENDER)

RETRYABLE = ("failed", "cancelled")

_SUBMITTING: Set[str] = set()

_PUMP_LOCKS: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}


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


def _missing_block(missing: List[str]) -> Dict[str, Any]:
    return note("missing_models", f"Install a recommended file for: {', '.join(missing)}.", fields=list(missing))


def _require_quota(owner: User, minutes: float) -> bool:
    status = limits.gpu_minutes_status(owner.id)
    remaining = status.get("remaining")
    if reserves(status) and remaining is not None and minutes > float(remaining) + 1e-9:
        raise Blocked([estimate.quota_block({"needed_minutes": round(minutes, 2), "remaining": remaining})])
    return reserves(status)


def _create(
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
) -> Dict[str, Any]:
    size = models.parse_size(plan.resolution)
    take_id = core_bridge.generate_ulid()
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
            "profile": plan.profile,
            "prompt_text": plan.prompt_text,
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            "duration_s": plan.seconds,
            "fps": plan.fps,
            "request": plan.request_for(take_id, seed),
        }
    )
    if minutes > 0 and core_bridge.record_limit_event(owner.id, limits.GPU_MINUTES, minutes, limit_ref(take_id)):
        takes.update_active(take_id, units_reserved=minutes)
    return takes.get_take(take_id)


async def start(owner: User, project: Mapping[str, Any], evaluation: Evaluation) -> List[Dict[str, Any]]:
    """Create one take per shot and variant, each with its own seed, and hand what fits to the core."""
    if evaluation.blocked:
        raise Blocked(evaluation.payload["blocks"])
    plans = evaluation.plans
    quota = evaluation.payload["quota"]
    reserve = bool(quota["applies"]) and reserves(quota)
    created = [
        _create(
            owner,
            project["id"],
            plan,
            preset_id=plans.preset.id,
            quality=plans.quality,
            kind=RENDER,
            seed=new_seed(),
            variant=letter,
            minutes=evaluation.minutes.get(plan.shot_id, 0.0) if reserve else 0.0,
        )
        for plan in plans.shots
        for letter in next_variants(project["id"], plan.shot_id, plans.quality, evaluation.variants)
    ]
    await pump(owner)
    return [takes.get_take(take["id"]) for take in created]


def _refusal(exc: Exception) -> Tuple[str, str]:
    if isinstance(exc, PermissionError):
        return "preset_not_available", "The preset is not available to you."
    if isinstance(exc, IdempotencyKeyConflict):
        return "duplicate_submission", "This take was already submitted with another request."
    if isinstance(exc, ValueError):
        return "invalid_request", (str(exc) or "The core refused the request.")[:MESSAGE_LIMIT]
    if isinstance(exc, RuntimeError):
        return "no_backend", "No backend can run this take right now."
    return "submit_failed", "The take could not be started."


async def _quiet_cancel(user: User, generation_id: str) -> None:
    try:
        await core_bridge.cancel_generation(user, generation_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not cancel generation %s", generation_id, exc_info=True)


async def _submit(user: User, take: Dict[str, Any]) -> bool:
    try:
        submitted = await core_bridge.submit_generation(user, take["request"] or {})
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] The core refused take %s", take["id"], exc_info=True)
        code, message = _refusal(exc)
        fail_take(take, code, message)
        return False
    generation_id = str(submitted["generation_id"])
    if takes.attach_generation(take["id"], generation_id):
        takes.add_job(take["id"], generation_id, limit_ref(take["id"]), take["units_reserved"])
        return True
    await _quiet_cancel(user, generation_id)
    return False


def _pump_lock(user_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    held = _PUMP_LOCKS.get(user_id)
    if held is None or held[0] is not loop:
        held = (loop, asyncio.Lock())
        _PUMP_LOCKS[user_id] = held
    return held[1]


async def pump(user: Optional[User]) -> int:
    """Hand the user's queued takes to the core while they have fewer than max_parallel_jobs in flight, one pump at a time per user."""
    if user is None:
        return 0
    async with _pump_lock(user.id):
        return await _pump(user)


async def _pump(user: User) -> int:
    free = int(settings.get_setting("max_parallel_jobs")) - takes.in_flight(user.id)
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
    return submitted


def _project_name(project_id: str) -> str:
    project = projects.get_project(project_id)
    return project["name"] if project else "Video Producer"


def _notify(take: Mapping[str, Any], done: bool, message: str = "") -> None:
    name = _project_name(take["project_id"])
    quality = "final" if take.get("quality") == "final" else "draft"
    variant = f" {take['variant']}" if take.get("variant") else ""
    text = f"{name}: the {quality} take{variant} is ready." if done else f"{name}: the {quality} take{variant} failed."
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


def _video(files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    videos = [
        item
        for item in files
        if str(item.get("file_type") or "").lower() == "video" or str(item.get("mime_type") or "").lower().startswith("video/")
    ]
    return videos[0] if videos else None


def _adjust(take: Mapping[str, Any], duration_ms: Optional[int]) -> None:
    reserved = float(take.get("units_reserved") or 0)
    if reserved <= 0 or not duration_ms or not take.get("user_id"):
        return
    actual = round(duration_ms / 60000, 3)
    ref = limit_ref(take["id"])
    if actual > reserved + 1e-6:
        core_bridge.record_limit_event(take["user_id"], limits.GPU_MINUTES, round(actual - reserved, 3), f"{ref}:adjust")
    elif actual < reserved - 1e-6:
        core_bridge.refund_limit_event(ref)
        core_bridge.record_limit_event(take["user_id"], limits.GPU_MINUTES, actual, f"{ref}:actual")


def _duration_ms(state: Mapping[str, Any]) -> Optional[int]:
    value = state.get("duration_ms")
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def finish_done(take: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> bool:
    """End a take whose generation completed: its video, thumbnail, calibration, quota adjustment and notification."""
    try:
        files = core_bridge.list_generation_files(user, take["generation_id"])
    except GenerationNotFoundException:
        return fail_take(take, "generation_not_found", "The generation of this take is no longer available.")
    video = _video(files)
    if video is None:
        return fail_take(take, "no_output", "The generation finished without a video.")
    backend_id = state.get("backend_id") or take.get("backend_id")
    fields = {
        "file_path": video.get("file_path"),
        "file_id": None if video.get("id") is None else str(video["id"]),
        "thumb_path": video.get("thumbnail_medium"),
        "width": video.get("width") or take.get("width"),
        "height": video.get("height") or take.get("height"),
        "duration_s": video.get("duration_seconds") or take.get("duration_s"),
        "fps": video.get("fps") or take.get("fps"),
        "backend_id": backend_id,
        "progress": 100.0,
        "step": None,
        "started_at": take.get("started_at") or state.get("started_at"),
        "finished_at": takes.now(),
    }
    if not takes.settle(take["id"], "done", **fields):
        return False
    duration_ms = _duration_ms(state)
    seconds = float(take.get("duration_s") or 0)
    if duration_ms and backend_id and seconds > 0 and take.get("resolution") and take.get("preset_id"):
        takes.add_calibration(take["preset_id"], backend_id, take["resolution"], seconds, duration_ms)
    _adjust(take, duration_ms)
    takes.close_jobs(take["id"])
    _notify(take, done=True)
    return True


def _percent(value: Any) -> Optional[float]:
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


def _is_admin(user: Optional[User]) -> bool:
    return getattr(user, "account_type", None) == AccountType.ADMIN


def apply_state(take: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> None:
    """Bring a take in line with the status of its generation."""
    status = str(state.get("status") or "").lower()
    if status == "completed":
        finish_done(take, user, state)
    elif status == "failed":
        code = str(state.get("error_code") or "generation_failed")
        fail_take(take, code, failure_message(state, error_code=code, admin=_is_admin(user), error_id=take.get("generation_id")))
    elif status == "cancelled":
        cancel_local(take)
    elif status == "running":
        takes.update_active(
            take["id"],
            status="running",
            progress=_percent(state.get("progress")),
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
    """End the take of a generation the core reports finished; False when no take is waiting on it."""
    take = takes.take_for_generation(str(generation_id or ""))
    if take is None or take["status"] not in takes.ACTIVE:
        return False
    if status == "cancelled":
        return cancel_local(take)
    if status not in ("completed", "failed"):
        return False
    if status == "failed":
        user, state = _quiet_state(take)
        code = str(error_code or state.get("error_code") or "generation_failed")
        reason = failure_message(state, message, code, admin=_is_admin(user), error_id=take.get("generation_id"))
        return fail_take(take, code, reason)
    user = core_bridge.get_user(take["user_id"])
    if user is None:
        return fail_take(take, "user_not_found", "The owner of this take no longer exists.")
    try:
        state = core_bridge.generation_state(user, take["generation_id"])
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read generation %s", generation_id, exc_info=True)
        state = {}
    if not _duration_ms(state) and isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
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
    """Delete a take, cancelling it first while it is queued or running; the host generation is kept."""
    if take["status"] in takes.ACTIVE:
        await cancel(owner, take)
    return takes.delete_take(take["id"])


def _checked(plan: ShotPlan, preset_id: str, native: bool, owner: User, backend_id: Optional[str]) -> float:
    if plan.missing_models:
        raise Blocked([_missing_block(plan.missing_models)])
    if not native:
        return 0.0
    minutes = estimate.plan_minutes(plan, preset_id, backend_id)
    return minutes if _require_quota(owner, minutes) else 0.0


def _render_plan(
    owner: User, project: Mapping[str, Any], source: Mapping[str, Any], quality: str
) -> Tuple[ShotPlan, str, bool]:
    plans = director.build_plans(
        owner, project["doc"], [source["shot_id"]], source["preset_id"], quality, source.get("model_id"), source.get("profile")
    )
    if plans.blocks:
        raise Blocked(plans.blocks)
    return plans.shots[0], plans.preset.id, not plans.preset.cloud


def _upscale_plan(owner: User, source: Mapping[str, Any], target: str) -> Tuple[ShotPlan, str, bool]:
    try:
        plan = director.build_upscale(owner, source, target)
    except DirectorError as exc:
        raise Blocked([exc.note()]) from None
    return plan, plan.request["preset_id"], True


async def final(owner: User, project: Mapping[str, Any], source: Mapping[str, Any], method: str, target: str) -> Dict[str, Any]:
    """A final take of a finished take: upscaled by SeedVR2 or MiniMax-H3, or rendered again at the largest size."""
    if source["status"] != "done":
        raise TakeError(409, "take_not_done", "Only a finished take can be made final.")
    plan, preset_id, native = (
        _upscale_plan(owner, source, target) if method == UPSCALE else _render_plan(owner, project, source, "final")
    )
    minutes = _checked(plan, preset_id, native, owner, source.get("backend_id"))
    take = _create(
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
    )
    await pump(owner)
    return takes.get_take(take["id"])


async def retry(owner: User, project: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    """A new take like a failed or cancelled one: same shot, seed, quality and preset."""
    if source["status"] not in RETRYABLE:
        raise TakeError(409, "take_not_retryable", "Only a failed or cancelled take can be retried.")
    if source["kind"] == UPSCALE:
        parent = takes.get_take(source.get("parent_take_id") or "")
        if parent is None or parent["status"] != "done":
            raise TakeError(409, "take_not_done", "The take this one upscaled is no longer finished.")
        plan, preset_id, native = _upscale_plan(owner, parent, director.upscale_target(source))
    else:
        plan, preset_id, native = _render_plan(owner, project, source, source["quality"])
    minutes = _checked(plan, preset_id, native, owner, source.get("backend_id"))
    take = _create(
        owner,
        project["id"],
        plan,
        preset_id=preset_id,
        quality=source["quality"],
        kind=source["kind"],
        seed=int(source["seed"]) if source.get("seed") is not None else new_seed(),
        variant=source.get("variant") or variant_letter(0),
        minutes=minutes,
        parent_take_id=source.get("parent_take_id"),
    )
    await pump(owner)
    return takes.get_take(take["id"])
