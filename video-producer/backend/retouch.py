import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from . import core_bridge, director, estimate, generation, models, presets, takes, workdir
from .core_bridge import GenerationNotFoundException, MediaRefError, User
from .director import DirectorError, ShotPlan
from .exports import video
from .exports.video import ExportError, num
from .generation import Blocked, TakeError
from .vreftrack import ENCODER

logger = logging.getLogger("plugins.video-producer")

REFINE = "refine_faces"
REMIX = "remix"
TASKS = (REFINE, REMIX)
STRENGTHS = ("light", "balanced", "strong")
DEFAULT_STRENGTH = "balanced"
MIN_SECONDS = {REFINE: 0.5, REMIX: 1.0}
MAX_SECONDS: Dict[str, Optional[float]] = {REFINE: None, REMIX: 3.0}
WORK_SCALE = {REFINE: 1.0, REMIX: 2.0}
ENGINES = {REFINE: (presets.MINIMAX_H3_12GB, presets.MINIMAX_H3_FAST_12GB), REMIX: (presets.MINIMAX_H3_12GB,)}
SOURCE_FIELD = {REFINE: "input_video", REMIX: "source_video"}
DETECTORS = {"faces": ("refine_faces", "face_detector_model", "face_landmarker.task"), "hands": ("refine_hands", "hand_detector_model", "hand_landmarker.task")}
PROMPT_LIMIT = 2000
REMIX_SECONDS = 14
EDGE_SECONDS = 0.04
WAITING = "waiting"
LANDED = "landed"
SPLICING_STEP = "Splicing the retouched range into the take"
AUDIO = ("-c:a", "aac", "-b:a", "192k")

_SPLICING: Set[str] = set()


@dataclass(frozen=True)
class Window:
    first: int
    last: int
    fps: float
    frames: int

    @property
    def count(self) -> int:
        return self.last - self.first

    @property
    def seconds(self) -> float:
        return self.count / self.fps

    @property
    def start_s(self) -> float:
        return self.first / self.fps

    @property
    def end_s(self) -> float:
        return self.last / self.fps


def _refused(code: str, message: str, status: int = 422) -> TakeError:
    return TakeError(status, code, message)


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def window_of(take: Mapping[str, Any], task: str, start_s: Any, end_s: Any) -> Window:
    fps = _number(take.get("fps")) or 0.0
    duration = _number(take.get("duration_s")) or 0.0
    if fps <= 0 or duration <= 0:
        raise _refused("take_unreadable", "The length or frame rate of this take is unknown.", 409)
    start, end = _number(start_s), _number(end_s)
    if start is None or end is None or start < 0 or end <= start:
        raise _refused("range_invalid", "Mark a range that ends after it starts.")
    if end > duration + max(EDGE_SECONDS, 1.0 / fps):
        raise _refused("range_outside_take", "The range ends after the end of the take.")
    total = max(1, round(duration * fps))
    first = round(start * fps)
    last = min(total, round(end * fps))
    if last - first < 1:
        raise _refused("range_invalid", "The range must hold at least one frame.")
    window = Window(first, last, fps, total)
    floor = MIN_SECONDS[task]
    if window.seconds < floor - 0.5 / fps:
        raise _refused("range_too_short", f"{label(task)} works on at least {floor:g} s; mark a longer section.")
    cap = MAX_SECONDS[task]
    if cap is not None and window.seconds > cap + 0.5 / fps:
        raise _refused("range_too_long", f"{label(task)} works on up to {cap:g} s with the 12 GB engines; mark a shorter section.")
    return window


def label(task: str) -> str:
    return "Refine faces" if task == REFINE else "Remix"


def _installed(filename: str) -> Optional[str]:
    try:
        return core_bridge.installed_model_for_file(filename)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not look up the detection model %s", filename, exc_info=True)
        return None


def detectors(kinds: List[str]) -> Tuple[Dict[str, str], List[str]]:
    values: Dict[str, str] = {}
    missing: List[str] = []
    for kind in kinds:
        _, field, filename = DETECTORS[kind]
        model_id = _installed(filename)
        if model_id:
            values[field] = f"{models.MODEL_REF}{model_id}"
        else:
            missing.append(filename)
    return values, missing


def engines(user: User, task: str) -> List[Dict[str, str]]:
    found = []
    for preset_id in ENGINES[task]:
        preset = director.find_preset(user, preset_id, video=False)
        if preset is not None and task in preset.modes:
            found.append({"preset_id": preset.id, "name": preset.name})
    return found


def offers(user: User) -> List[Dict[str, Any]]:
    listed = []
    for task in TASKS:
        engine_list = engines(user, task)
        missing = detectors(list(DETECTORS))[1] if task == REFINE else []
        reason = None
        if not engine_list:
            reason = "engine_missing"
        elif missing:
            reason = "detector_missing"
        listed.append(
            {
                "task": task,
                "engines": engine_list,
                "min_s": MIN_SECONDS[task],
                "max_s": MAX_SECONDS[task],
                "ready": reason is None,
                "reason": reason,
                "missing": missing,
            }
        )
    return listed


def _resolution(fields: models.Fields, source: Mapping[str, Any]) -> Optional[str]:
    spec = fields.get("resolution")
    if not spec:
        return None
    wanted = source.get("resolution")
    if not wanted and isinstance(source.get("width"), int) and isinstance(source.get("height"), int):
        wanted = f"{source['width']}x{source['height']}"
    values = [option.get("value") for option in spec.get("options") or []]
    if wanted in values or (not values and models.parse_size(wanted)):
        return str(wanted)
    default = spec.get("default")
    return str(default) if default else None


def _form(task: str, body: Mapping[str, Any], fields: models.Fields, source: Mapping[str, Any]) -> Tuple[Dict[str, Any], str]:
    form: Dict[str, Any] = {"seed": -1}
    if "quantity" in fields:
        form["quantity"] = 1
    if task == REMIX:
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise _refused("prompt_required", "Write the change Remix should make.")
        if len(prompt) > PROMPT_LIMIT:
            raise _refused("prompt_too_long", f"Keep the change under {PROMPT_LIMIT} characters.")
        form["keep_sound"] = True
        form["max_seconds"] = REMIX_SECONDS
        size = _resolution(fields, source)
        if size:
            form["resolution"] = size
        return form, prompt
    strength = body.get("strength") or DEFAULT_STRENGTH
    if strength not in STRENGTHS:
        raise _refused("strength_invalid", f"strength must be one of: {', '.join(STRENGTHS)}.")
    kinds = [kind for kind in DETECTORS if body.get(kind, True) is not False]
    if not kinds:
        raise _refused("nothing_to_refine", "Choose faces, hands or both.")
    values, missing = detectors(kinds)
    if missing:
        raise _refused(
            "detector_missing",
            f"Refine faces needs its detection models, which PotionUI does not list: {', '.join(missing)}. Ask an administrator to scan the models (Admin > Models), then to install them if they are still missing.",
            409,
        )
    form["enhancement_strength"] = strength
    for kind in DETECTORS:
        form[DETECTORS[kind][0]] = kind in kinds
    form.update(values)
    return form, ""


def _record(task: str, window: Window, source: Mapping[str, Any], preset_id: str, prompt: str, body: Mapping[str, Any]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "task": task,
        "start_s": round(window.start_s, 6),
        "end_s": round(window.end_s, 6),
        "start_frame": window.first,
        "end_frame": window.last,
        "frames": window.frames,
        "fps": window.fps,
        "source_take_id": source["id"],
        "preset_id": preset_id,
        "state": WAITING,
    }
    if prompt:
        record["prompt"] = prompt
    if task == REFINE:
        record["strength"] = body.get("strength") or DEFAULT_STRENGTH
        record["faces"] = body.get("faces", True) is not False
        record["hands"] = body.get("hands", True) is not False
    return record


def _ffmpeg() -> str:
    found = core_bridge.find_ffmpeg()
    if not found:
        raise _refused("ffmpeg_missing", "ffmpeg is not available on this server: the range cannot be cut.", 503)
    return os.path.abspath(found) if os.path.dirname(found) else found


def cut_command(ffmpeg: str, source: str, window: Window, output: Path, sound: bool) -> List[str]:
    picture = f"trim=start_frame={window.first}:end_frame={window.last},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    sound_args = ["-map", "0:a:0", "-af", f"atrim=start={num(window.start_s)}:end={num(window.end_s)},asetpts=PTS-STARTPTS", *AUDIO] if sound else ["-an"]
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", source,
        "-map", "0:v:0",
        "-vf", picture,
        *sound_args,
        *ENCODER,
        "-r", num(window.fps),
        "-frames:v", str(window.count),
        str(output),
    ]


def splice_command(
    ffmpeg: str, source: str, result: str, window: Window, size: Tuple[int, int], output: Path, sound: bool
) -> List[str]:
    width, height = size
    tidy = "setsar=1,format=yuv420p"
    parts: List[str] = []
    labels: List[str] = []
    if window.first > 0:
        parts.append(f"[0:v]trim=end_frame={window.first},setpts=PTS-STARTPTS,{tidy}[head]")
        labels.append("[head]")
    parts.append(
        f"[1:v]fps={num(window.fps)},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},{tidy},"
        f"tpad=stop_mode=clone:stop={window.count},trim=end_frame={window.count},setpts=PTS-STARTPTS[middle]"
    )
    labels.append("[middle]")
    if window.last < window.frames:
        parts.append(f"[0:v]trim=start_frame={window.last},setpts=PTS-STARTPTS,{tidy}[tail]")
        labels.append("[tail]")
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[picture]")
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", source,
        "-i", result,
        "-filter_complex", ";".join(parts),
        "-map", "[picture]",
        *(["-map", "0:a:0", "-c:a", "copy"] if sound else ["-an"]),
        *ENCODER,
        "-r", num(window.fps),
        "-frames:v", str(window.frames),
        str(output),
    ]


def _scratch(owner_id: str) -> Path:
    try:
        return workdir.scratch(workdir.FRAMES, owner_id)
    except workdir.WorkdirError as exc:
        raise _refused(exc.code, exc.message, 503) from None


async def _local(owner: User, ref: Optional[Mapping[str, Any]], folder: Path, missing: str) -> Path:
    path = await asyncio.to_thread(core_bridge.local_media_file, owner, ref, folder) if ref else None
    if path is None:
        raise _refused("source_unavailable", missing, 409)
    return Path(path)


async def cut(owner: User, source: Mapping[str, Any], window: Window) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    folder = _scratch(owner.id)
    try:
        local = await _local(owner, takes.media_ref(source), folder, "The video of the source take is no longer available.")
        probe = await asyncio.to_thread(core_bridge.probe_video, local)
        output = folder / f"retouch-{source['id']}-{window.first}-{window.last}.mp4"
        try:
            await video.assemble(cut_command(ffmpeg, str(local), window, output, bool(probe and probe.has_audio)), window.seconds, cwd=str(folder), code="retouch_cut_failed")
        except ExportError as exc:
            raise _refused(exc.code, exc.message, 502) from None
        try:
            stored = await core_bridge.save_user_media(owner, output, purpose=core_bridge.DERIVED_PURPOSE)
        except MediaRefError as exc:
            raise _refused("retouch_cut_unstored", str(exc) or "The cut range could not be stored.", 502) from None
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    return stored


def _minutes(plan: ShotPlan, preset_id: str, task: str, window: Window, backend_id: Optional[str]) -> float:
    sized = ShotPlan(
        shot_id=plan.shot_id,
        profile=None,
        director_mode=None,
        preset_mode=task,
        seconds=window.seconds,
        resolution=plan.resolution,
        fps=plan.fps,
        prompt_text="",
        request={},
        work_scale=WORK_SCALE[task],
    )
    return estimate.plan_minutes(sized, preset_id, backend_id)


async def start(owner: User, project: Mapping[str, Any], source: Mapping[str, Any], body: Mapping[str, Any]) -> Dict[str, Any]:
    task = body.get("task")
    if task not in TASKS:
        raise _refused("task_invalid", f"task must be one of: {', '.join(TASKS)}.")
    if source.get("kind") == takes.KEYFRAME:
        raise _refused("keyframe_take", "A start image candidate cannot be retouched.", 409)
    if source.get("status") != "done" or not takes.media_ref(source):
        raise _refused("take_not_done", "Only a finished take can be retouched.", 409)
    preset_id = body.get("preset_id") or ENGINES[task][0]
    if preset_id not in ENGINES[task] or not any(engine["preset_id"] == preset_id for engine in engines(owner, task)):
        raise _refused("task_not_offered", f"{label(task)} is not offered by this engine.")
    window = window_of(source, task, body.get("start_s"), body.get("end_s"))
    try:
        director.native_engine_or_block("A retouch")
    except DirectorError as exc:
        raise Blocked([exc.note()]) from None
    fields = models.form_fields(preset_id, task)
    form, prompt = _form(task, body, fields, source)
    resolved = models.resolve_models(preset_id, task, None, fields)
    if resolved.missing:
        raise Blocked([generation.missing_block(resolved.missing)])
    form.update(resolved.values)
    plan = ShotPlan(
        shot_id=str(source["shot_id"]),
        profile=None,
        director_mode=None,
        preset_mode=task,
        seconds=float(source.get("duration_s") or 0),
        resolution=source.get("resolution") or (f"{source['width']}x{source['height']}" if source.get("width") and source.get("height") else None),
        fps=source.get("fps"),
        prompt_text=prompt,
        request={},
    )
    minutes = _minutes(plan, preset_id, task, window, source.get("backend_id"))
    stored = await cut(owner, source, window)
    form[SOURCE_FIELD[task]] = str(stored["value"])
    plan.request = {"preset_id": preset_id, "mode": task, "prompts": [{"positive": prompt, "negative": ""}], "form_data": form}
    record = _record(task, window, source, preset_id, prompt, body)
    record["cut"] = stored.get("ref")
    letter = generation.next_variants(project["id"], plan.shot_id, source["quality"], 1)[0]
    with generation.reserving(owner, minutes) as reserve:
        take = generation.create(
            owner,
            project["id"],
            plan,
            preset_id=preset_id,
            quality=source["quality"],
            kind=takes.RETOUCH,
            seed=generation.new_seed(),
            variant=letter,
            minutes=minutes if reserve else 0.0,
            parent_take_id=source["id"],
            revision=source.get("shot_revision"),
        )
    takes.set_retouch(take["id"], record)
    await generation.pump(owner)
    return takes.get_take(take["id"])


async def retry(owner: User, project: Mapping[str, Any], failed: Mapping[str, Any]) -> Dict[str, Any]:
    if failed["status"] not in generation.RETRYABLE:
        raise _refused("take_not_retryable", "Only a failed or cancelled take can be retried.", 409)
    record = failed.get("retouch") or {}
    source = takes.get_take(record.get("source_take_id") or "")
    if source is None or source.get("project_id") != project["id"]:
        raise _refused("take_not_done", "The take this one retouched is no longer available.", 409)
    body = {key: record[key] for key in ("task", "start_s", "end_s", "preset_id", "prompt", "strength", "faces", "hands") if key in record}
    return await start(owner, project, source, body)


def land(take: Mapping[str, Any], user: User, state: Mapping[str, Any]) -> bool:
    record = dict(take.get("retouch") or {})
    if record.get("state") == LANDED:
        return False
    try:
        files = core_bridge.list_generation_files(user, take["generation_id"])
    except GenerationNotFoundException:
        return generation.fail_take(take, "generation_not_found", "The generation of this take is no longer available.")
    output = generation.output_of(files, "video")
    if output is None:
        return generation.fail_take(take, "no_output", "The generation finished without a video.")
    record.update(
        {
            "state": LANDED,
            "output": {"generation_id": str(take["generation_id"]), "file_id": str(output.get("id")), "file_path": output.get("file_path")},
            "duration_ms": generation.state_duration_ms(state),
            "backend_id": state.get("backend_id") or take.get("backend_id"),
        }
    )
    return takes.land_retouch(take["id"], record, SPLICING_STEP)


async def splice_landed() -> int:
    done = 0
    for take in takes.list_active():
        record = take.get("retouch") or {}
        if take.get("kind") != takes.RETOUCH or record.get("state") != LANDED or take["id"] in _SPLICING:
            continue
        _SPLICING.add(take["id"])
        try:
            done += int(await _splice(take))
        finally:
            _SPLICING.discard(take["id"])
    return done


async def _splice(take: Mapping[str, Any]) -> bool:
    user = core_bridge.get_user(take["user_id"]) if take.get("user_id") else None
    if user is None:
        return generation.fail_take(take, "user_not_found", "The owner of this take no longer exists.")
    record = take["retouch"]
    source = takes.get_take(record.get("source_take_id") or "")
    if source is None or not takes.media_ref(source):
        return generation.fail_take(take, "source_unavailable", "The take this one retouches is no longer available.")
    window = Window(int(record["start_frame"]), int(record["end_frame"]), float(record["fps"]), int(record["frames"]))
    output = record.get("output") or {}
    result_ref = {"kind": "history", "generation_id": output.get("generation_id"), "file_id": output.get("file_id")}
    try:
        ffmpeg = _ffmpeg()
        folder = _scratch(user.id)
    except TakeError as exc:
        return generation.fail_take(take, exc.code, exc.message)
    try:
        original = await _local(user, takes.media_ref(source), folder, "The video of the source take is no longer available.")
        result = await _local(user, result_ref, folder, "The retouched range is no longer available.")
        probe = await asyncio.to_thread(core_bridge.probe_video, original)
        width = (probe.width if probe else None) or source.get("width")
        height = (probe.height if probe else None) or source.get("height")
        if not width or not height:
            return generation.fail_take(take, "take_unreadable", "The size of the source take could not be read.")
        spliced = folder / f"{source['id']}-{take['variant']}-retouch.mp4"
        await video.assemble(
            splice_command(ffmpeg, str(original), str(result), window, (int(width), int(height)), spliced, bool(probe and probe.has_audio)),
            window.frames / window.fps,
            cwd=str(folder),
            code="retouch_splice_failed",
        )
        stored = await core_bridge.save_user_media(user, spliced, purpose=core_bridge.DERIVED_PURPOSE)
    except TakeError as exc:
        return generation.fail_take(take, exc.code, exc.message)
    except ExportError as exc:
        return generation.fail_take(take, exc.code, exc.message)
    except MediaRefError as exc:
        return generation.fail_take(take, "retouch_unstored", str(exc) or "The retouched take could not be stored.")
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    fields = {
        "file_path": stored["value"],
        "file_id": None,
        "thumb_path": None,
        "media_ref": stored.get("ref"),
        "width": int(width),
        "height": int(height),
        "duration_s": source.get("duration_s"),
        "fps": source.get("fps"),
        "backend_id": record.get("backend_id") or take.get("backend_id"),
    }
    return generation.complete_retouch(take, fields, record.get("duration_ms"))

