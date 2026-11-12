import asyncio
import concurrent.futures
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from fastapi import HTTPException

from . import bible, core_bridge, director, workdir
from .core_bridge import User
from .director import DirectorError
from .responses import fail

logger = logging.getLogger("plugins.video-producer")

MAX_REQUEST_CHARS = 1000
MAX_INSTRUCTION_CHARS = 4000
MAX_LABEL_CHARS = 80
MAX_LABELS = 12
CURRENT = "The shot's current prompt, to rewrite as the request says: \"{text}\""
CUT = "The current prompt is cut short where it ends with an ellipsis: keep what it says, and do not continue it."
WRITE_TIMEOUT_S = 120.0
POLL_S = 0.25
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_EDGE = 1024
MAX_PIXELS = 40_000_000
WORK_AREA = "writer"
STALE_S = 2 * WRITE_TIMEOUT_S
GRACE_S = 1.0

writing: Set[str] = set()
pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="vp-writer")

FRAMING = (
    "You write the prompt of one shot of a video made with Video Producer, for the engine of this preset. "
    "Video Producer adds the rest of the engine's prompt itself: the labelled sections or fields its guide describes, "
    "the [Shot 1] marker, the global direction of the film, the cast definitions from the project's bible with their "
    "<Subject N> and <Picture N> tags, the dialogue and the sound. Follow the guide for its vocabulary (camera moves, "
    "framing, motion, light), not for its layout: reply with one to three plain sentences that say what the camera "
    "sees in this shot, with no section label and no [Shot] marker. Name every character and place by its label, and write "
    "no tag in angle brackets at all, no <Subject N>, <Picture N>, <Video N> or <Audio N>: Video Producer numbers them itself "
    "when it composes the prompt."
)

SECTION = re.compile(r"^[ \t]*(?:detailed_description|integrated_multimodal_description)[ \t]*:[ \t]*", re.MULTILINE)
NEXT_SECTION = re.compile(r"\n[ \t]*[a-z_]+[ \t]*:")
SHOT_MARKER = re.compile(r"\[Shot 1\]\s*")
TAGGED = r"\s*\(\s*<(?:Subject|Picture|Video|Audio) \d+>\s*\)"
BARE = re.compile(r"<(?:Subject|Picture|Video|Audio) \d+>")
SPACED = re.compile(r"[ \t]+([,.;:!?])")
FENCE = re.compile(r"```[A-Za-z]*[ \t]*\n?(.*?)```", re.DOTALL)
PREAMBLE = re.compile(
    r"^(?:(?:sure|okay|ok|certainly|of course|absolutely)\b[^\n]{0,20}?)?"
    r"(?:here(?:'s| is| are| it is)\b|below is\b|this is\b|(?:the )?(?:new |rewritten |revised |final |shot )*prompt\b)"
    r"[^\n]{0,100}:[ \t]*\n+",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[.!?\u2026][\"')\]]?(?=\s)")
MAX_WRITTEN_CHARS = 1500

UNAVAILABLE = {
    "available": False,
    "vision": False,
    "name": None,
    "code": "writer_unavailable",
    "message": "The prompt writer of the application cannot be reached.",
}


def status(user: User) -> Dict[str, Any]:
    try:
        found = core_bridge.prompt_writer_status(user.id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the prompt writer status", exc_info=True)
        return dict(UNAVAILABLE)
    available = found.get("available") is True
    return {
        "available": available,
        "vision": available and found.get("vision") is True,
        "name": found.get("name") if isinstance(found.get("name"), str) else None,
        "code": None if available else (found.get("code") if isinstance(found.get("code"), str) else "no_llm"),
        "message": None if available else (found.get("message") if isinstance(found.get("message"), str) else None),
    }


def _label(text: str) -> str:
    return " ".join(text.split())[:MAX_LABEL_CHARS]


def _quoted(labels: Sequence[str]) -> str:
    return ", ".join(f'"{_label(label)}"' for label in labels[:MAX_LABELS])


def _shortened(text: str, room: int) -> str:
    if room <= 1:
        return ""
    cut = text[: room - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


def instruction(
    request: str,
    *,
    current: str,
    seconds: float,
    characters: Sequence[str],
    place: Optional[str],
    images: Sequence[str],
) -> str:
    lines = [request.strip()[:MAX_REQUEST_CHARS], "", FRAMING]
    lines.append(f"Write in English. The shot lasts {seconds:.1f} seconds.")
    if characters:
        lines.append(
            "Name each character the shot casts by its label, written exactly as given, and do not describe their looks: "
            f"their card in the bible does. The characters: {_quoted(characters)}."
        )
    if place:
        lines.append(f'The shot takes place in "{_label(place)}"; name it by that label.')
    if list(images) == ["first", "last"]:
        lines.append("Image 1 is the shot's first frame and image 2 its last frame: describe the motion from one to the other, not what the images already show.")
    elif list(images) == ["first"]:
        lines.append("The image is the shot's first frame: describe the motion forward from it, not what it already shows.")
    elif list(images) == ["last"]:
        lines.append("The image is the shot's last frame: describe the motion that leads to it, not what it already shows.")
    text = current.strip()
    tags = vref_tags(current)
    if tags:
        lines.append(f"Keep the tags {', '.join(tags)} exactly as they are written, where the action needs them: each one cites a reference video of the shot.")
    if text:
        room = MAX_INSTRUCTION_CHARS - len("\n".join(lines)) - len(CURRENT.format(text="")) - 1
        if len(text) <= room:
            lines.append(CURRENT.format(text=text))
        else:
            lines.append(CURRENT.format(text=_shortened(text, room - len(CUT) - 1)))
            lines.append(CUT)
    return "\n".join(lines)[:MAX_INSTRUCTION_CHARS]


def vref_tags(text: str) -> List[str]:
    return [f"@vref{slot}" for slot in director.cited_slots(text)]


def lost_tags(current: str, written: str) -> List[str]:
    kept = set(director.cited_slots(written))
    return [f"@vref{slot}" for slot in director.cited_slots(current) if slot not in kept]


def bounded(text: str) -> str:
    if len(text) <= MAX_WRITTEN_CHARS:
        return text
    cut = text[:MAX_WRITTEN_CHARS]
    ends = [match.end() for match in SENTENCE_END.finditer(cut + " ")]
    if ends and ends[-1] > MAX_WRITTEN_CHARS // 2:
        return cut[: ends[-1]].strip()
    return (cut[: MAX_WRITTEN_CHARS - 1].rsplit(" ", 1)[0] if " " in cut else cut[: MAX_WRITTEN_CHARS - 1]).rstrip() + "\u2026"


def kept_tags(written: str) -> List[str]:
    return list(dict.fromkeys(BARE.findall(written)))


def _untagged(text: str, labels: Sequence[str]) -> str:
    whole = {" ".join(label.split()) for label in labels if isinstance(label, str)}
    named = {name for label in whole for name in (label, label[:MAX_LABEL_CHARS])} - {""}
    for label in sorted(named, key=len, reverse=True):
        spaced = r"\s+".join(re.escape(word) for word in label.split())
        text = re.sub(rf"(?<!\w)({spaced}){TAGGED}", r"\1", text, flags=re.IGNORECASE)
    return text


def cleaned(text: Any, labels: Sequence[str] = ()) -> str:
    written = text.strip() if isinstance(text, str) else ""
    fence = FENCE.search(written)
    if fence is not None:
        written = fence.group(1).strip()
    section = SECTION.search(written)
    if section is None:
        written = PREAMBLE.sub("", written, count=1)
    else:
        rest = written[section.end():]
        following = NEXT_SECTION.search(rest)
        written = rest[: following.start()] if following is not None else rest
    marker = SHOT_MARKER.search(written)
    if marker is not None:
        written = written[marker.end():]
    written = SPACED.sub(r"\1", _untagged(written, labels))
    return bounded("\n".join(" ".join(line.split()) for line in written.strip().splitlines()).strip())


def _plan(owner: User, doc: Mapping[str, Any], shot_id: str, preset_id: str, model_id: Optional[str]) -> Tuple[str, Optional[str], Optional[Dict[str, Any]]]:
    try:
        plans = director.build_plans(owner, doc, [shot_id], preset_id, "draft", model_id, overrides=True)
    except DirectorError:
        return preset_id, None, None
    plan = next((item for item in plans.shots if item.shot_id == shot_id), None)
    if plan is None:
        return preset_id, None, None
    form_data = plan.request.get("form_data") if isinstance(plan.request, Mapping) else None
    return plan.preset_id or preset_id, plan.preset_mode or None, dict(form_data) if isinstance(form_data, Mapping) else None


def _flattened(picture: Any) -> Any:
    from PIL import Image

    if picture.mode == "I":
        return picture.point(lambda value: value * (1 / 256)).convert("L").convert("RGB")
    if picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info:
        layered = picture.convert("RGBA")
        canvas = Image.new("RGB", layered.size, (255, 255, 255))
        canvas.paste(layered, mask=layered.getchannel("A"))
        return canvas
    return picture.convert("RGB")


def _within(image: Any) -> None:
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"{image.width}x{image.height} is past {MAX_PIXELS} pixels")


def _shrunk(source: Path, target: Path) -> None:
    from PIL import Image, ImageOps

    with Image.open(source) as image:
        _within(image)
        image.draft("RGB", (IMAGE_EDGE, IMAGE_EDGE))
        if image.mode.startswith("I;16"):
            image = image.convert("I")
        image.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
        picture = _flattened(ImageOps.exif_transpose(image))
        picture.save(target, "JPEG", quality=90)


def work_folder(owner: User) -> Optional[Path]:
    try:
        return workdir.area(WORK_AREA, owner.id) / uuid.uuid4().hex
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the file storage directory for the prompt writer", exc_info=True)
        return None


def _plain_folder(path: Path) -> bool:
    return not path.is_symlink() and not path.is_junction() and path.is_dir()


def clear_work_area(now: Optional[float] = None) -> int:
    area = workdir.area(WORK_AREA)
    if not area.is_dir():
        return 0
    limit = (time.time() if now is None else now) - STALE_S
    cleared = 0
    for owner in [path for path in area.iterdir() if _plain_folder(path)]:
        for folder in [path for path in owner.iterdir() if _plain_folder(path)]:
            if folder.stat().st_mtime < limit:
                shutil.rmtree(folder)
                cleared += 1
        try:
            owner.rmdir()
        except OSError:
            pass
    return cleared


def readable(source: Path) -> bool:
    from PIL import Image

    try:
        with Image.open(source) as image:
            _within(image)
            image.draft("RGB", (IMAGE_EDGE, IMAGE_EDGE))
            image.load()
    except Exception:
        return False
    return True


def inside(root: Path, value: Any) -> Optional[Path]:
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    base = root.resolve()
    located = (base / relative).resolve()
    return located if located.is_relative_to(base) else None


def fitted(owner: User, media: Sequence[Mapping[str, Any]], folder: Optional[Path]) -> Tuple[List[Dict[str, Any]], int]:
    try:
        root = core_bridge.storage_directory()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the file storage directory; the key frames go as they are", exc_info=True)
        return [dict(item) for item in media], 0
    sent: List[Dict[str, Any]] = []
    dropped = 0
    for index, item in enumerate(media):
        source = inside(root, item.get("value"))
        if source is None:
            logger.warning("[VIDEO-PRODUCER] A key frame of the prompt writer is outside the file storage: %s", item.get("value"))
            dropped += 1
            continue
        try:
            size = source.stat().st_size if source.is_file() else None
        except OSError:
            size = None
        if size is None:
            logger.warning("[VIDEO-PRODUCER] A key frame of the prompt writer is not on the disk: %s", item.get("value"))
            dropped += 1
            continue
        if size <= MAX_IMAGE_BYTES:
            if readable(source):
                sent.append(dict(item))
            else:
                logger.warning("[VIDEO-PRODUCER] A key frame of the prompt writer cannot be read: %s", item.get("value"))
                dropped += 1
            continue
        try:
            if folder is None:
                raise OSError("no work folder")
            workdir.make(folder)
            target = folder / f"frame-{index + 1}.jpg"
            _shrunk(source, target)
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not shrink the key frame %s for the prompt writer", item.get("value"), exc_info=True)
            dropped += 1
            continue
        sent.append({**item, "value": target.relative_to(root).as_posix()})
    return sent, dropped


def _seconds(clip: Mapping[str, Any]) -> float:
    value = clip.get("dur")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0.0


def remove_when_done(folder: Path, jobs: Sequence[Any]) -> None:
    def finished(_: Any = None) -> None:
        if all(job.done() for job in jobs):
            shutil.rmtree(folder, ignore_errors=True)

    pending = [job for job in jobs if not job.done()]
    if not pending:
        finished()
        return
    for job in pending:
        job.add_done_callback(finished)


async def _answer(task: "asyncio.Future[Any]", gone: Optional[Callable[[], Awaitable[bool]]]) -> Any:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WRITE_TIMEOUT_S
    try:
        while True:
            left = deadline - loop.time()
            if left <= 0:
                fail(504, "write_timeout", f"The language model did not answer within {WRITE_TIMEOUT_S:.0f} seconds.")
            done, _ = await asyncio.wait({task}, timeout=min(POLL_S, left))
            if done:
                return task.result()
            if gone is not None and await gone():
                fail(409, "write_cancelled", "The page stopped waiting for the prompt.")
    finally:
        if not task.done():
            task.cancel()
            await asyncio.wait({task}, timeout=GRACE_S)


async def write(
    user: User,
    owner: User,
    doc: Mapping[str, Any],
    clip: Mapping[str, Any],
    request: str,
    preset_id: str,
    model_id: Optional[str],
    current: str,
    gone: Optional[Callable[[], Awaitable[bool]]] = None,
) -> Dict[str, Any]:
    if user.id in writing:
        fail(409, "write_busy", "A prompt is already being written for you: wait for it, or cancel it first.")
    writing.add(user.id)
    try:
        return await _write(user, owner, doc, clip, request, preset_id, model_id, current, gone)
    finally:
        writing.discard(user.id)


async def _write(
    user: User,
    owner: User,
    doc: Mapping[str, Any],
    clip: Mapping[str, Any],
    request: str,
    preset_id: str,
    model_id: Optional[str],
    current: str,
    gone: Optional[Callable[[], Awaitable[bool]]],
) -> Dict[str, Any]:
    found = await asyncio.to_thread(status, user)
    if not found["available"]:
        fail(409, found["code"] or "no_llm", found["message"] or "No language model is available to you.")
    shot_id = str(clip.get("id"))
    preset, mode, form_data = await asyncio.to_thread(_plan, owner, doc, shot_id, preset_id, model_id)
    frames: List[Dict[str, Any]] = await asyncio.to_thread(director.key_frame_media, owner, doc, shot_id)
    folder = await asyncio.to_thread(work_folder, owner) if found["vision"] else None
    jobs: List[Any] = []
    try:
        if found["vision"]:
            prepared = pool.submit(fitted, owner, frames, folder)
            jobs.append(prepared)
            media, dropped = await asyncio.wrap_future(prepared)
        else:
            media, dropped = [], 0
        return await _written(user, found, shot_id, doc, clip, request, current, preset, mode, form_data, frames, media, dropped, gone, jobs)
    finally:
        if folder is not None:
            remove_when_done(folder, jobs)


async def _written(
    user: User,
    found: Mapping[str, Any],
    shot_id: str,
    doc: Mapping[str, Any],
    clip: Mapping[str, Any],
    request: str,
    current: str,
    preset: str,
    mode: Optional[str],
    form_data: Optional[Dict[str, Any]],
    frames: Sequence[Mapping[str, Any]],
    media: List[Dict[str, Any]],
    dropped: int,
    gone: Optional[Callable[[], Awaitable[bool]]],
    jobs: List[Any],
) -> Dict[str, Any]:
    characters, place = bible.cast_of(doc, clip)
    text = instruction(
        request,
        current=current,
        seconds=_seconds(clip),
        characters=[card.label for card in characters],
        place=place.label if place is not None else None,
        images=[str(item.get("role")) for item in media],
    )
    sent = [{"value": item["value"], "media_type": item["media_type"]} for item in media]
    try:
        call = asyncio.ensure_future(core_bridge.write_prompt_for_preset(user.id, text, preset_id=preset, mode=mode, form_data=form_data, media=sent))
        jobs.append(call)
        reply = await _answer(call, gone)
    except HTTPException:
        raise
    except core_bridge.PromptWriteRefused as exc:
        fail(422, getattr(exc, "code", None) or "write_refused", str(exc))
    except Exception:
        logger.warning("[VIDEO-PRODUCER] The prompt writer failed for shot %s", shot_id, exc_info=True)
        fail(502, "write_failed", "The language model could not write the prompt.")
    labels = [card.label for card in characters] + ([place.label] if place is not None else [])
    written = cleaned(reply.get("text") if isinstance(reply, Mapping) else None, labels)
    if not written:
        fail(502, "empty_reply", "The language model returned no prompt.")
    return {
        "text": written,
        "name": found["name"],
        "images": len(media),
        "images_skipped": 0 if found["vision"] else len(frames),
        "images_dropped": dropped,
        "lost_tags": lost_tags(current, written),
        "kept_tags": kept_tags(written),
    }
