import asyncio
import base64
import json
import logging
import os
import shutil
import struct
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import bible, chain, core_bridge, director, takes
from .core_bridge import MediaRefError
from .exports import media
from .exports.common import asset_of
from .exports.video import num

logger = logging.getLogger("plugins.video-producer")

LOOKS = takes.LOOKS

SAMPLE_STEP = 1.0
MAX_SAMPLES = 12
END_MARGIN = 0.05

SEAM_LOW = 0.70
CAST_LOW = 0.60

TAKE = "take"
IMAGE = "image"

QUEUED = "queued"
DONE = "done"
FAILED = "failed"
UNAVAILABLE = "unavailable"
MISSING = "missing"

ERROR_LIMIT = 300

_COLUMNS = ("key", "user_id", "kind", "source", "model", "status", "frames", "error", "created_at", "updated_at")


def take_key(take_id: str) -> str:
    """The key of the look of a take."""
    return f"{TAKE}:{take_id}"


def image_key(value: str) -> str:
    """The key of the look of a stored image."""
    return f"{IMAGE}:{value}"


def pack(vector: Sequence[float]) -> str:
    """A vector as half floats in base64, the way the looks table keeps it."""
    return base64.b64encode(struct.pack(f"<{len(vector)}e", *vector)).decode("ascii")


def unpack(text: str) -> Tuple[float, ...]:
    """The vector pack wrote."""
    data = base64.b64decode(text)
    return struct.unpack(f"<{len(data) // 2}e", data)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """The cosine of two L2-normalized vectors."""
    return sum(x * y for x, y in zip(a, b))


def sample_times(length: float) -> List[float]:
    """The times a take is looked at: its start, then one image a second, at most MAX_SAMPLES in all, then its last image."""
    if length <= END_MARGIN:
        return [0.0]
    step = max(SAMPLE_STEP, length / (MAX_SAMPLES - 1))
    times: List[float] = []
    at = 0.0
    while at < length - END_MARGIN and len(times) < MAX_SAMPLES - 1:
        times.append(round(at, 3))
        at += step
    return times + [round(length, 3)]


def _row(row: Any) -> Dict[str, Any]:
    found = {column: row[column] for column in _COLUMNS}
    found["source"] = json.loads(found["source"]) if found["source"] else {}
    found["frames"] = json.loads(found["frames"]) if found["frames"] else []
    return found


def rows(keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """The stored looks of some keys."""
    from src.plugin_api import db

    wanted = list(dict.fromkeys(keys))
    found: Dict[str, Dict[str, Any]] = {}
    with db.get_cursor() as cursor:
        for start in range(0, len(wanted), 400):
            part = wanted[start : start + 400]
            cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM {LOOKS} WHERE key IN ({', '.join('?' for _ in part)})", tuple(part))
            found.update({row["key"]: _row(row) for row in cursor.fetchall()})
    return found


def _queue(key: str, user_id: Optional[str], kind: str, source: Mapping[str, Any]) -> None:
    from src.plugin_api import db

    now = takes.now()
    with db.get_cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {LOOKS} (key, user_id, kind, source, model, status, frames, error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET status = excluded.status, user_id = excluded.user_id, source = excluded.source, "
            "error = NULL, updated_at = excluded.updated_at",
            (key, user_id, kind, json.dumps(source), QUEUED, now, now),
        )


def queue_take(take: Mapping[str, Any]) -> None:
    """Ask for the look of a finished take."""
    if take.get("kind") != takes.KEYFRAME:
        _queue(take_key(take["id"]), take.get("user_id"), TAKE, {"take_id": take["id"]})


def queue_image(user_id: str, ref: Mapping[str, Any], value: str) -> None:
    """Ask for the look of a stored image of a user."""
    _queue(image_key(value), user_id, IMAGE, {"ref": dict(ref), "value": value})


def queued_count() -> int:
    """How many looks wait to be computed."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS count FROM {LOOKS} WHERE status = ?", (QUEUED,))
        return int(cursor.fetchone()["count"])


def _next() -> Optional[Dict[str, Any]]:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT {', '.join(_COLUMNS)} FROM {LOOKS} WHERE status = ? ORDER BY kind = ?, updated_at, key LIMIT 1", (QUEUED, TAKE))
        row = cursor.fetchone()
    return None if row is None else _row(row)


def _mark(key: str, status: str, model: Optional[str] = None, frames: Optional[List[Any]] = None, error: Optional[str] = None) -> None:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(
            f"UPDATE {LOOKS} SET status = ?, model = ?, frames = ?, error = ?, updated_at = ? WHERE key = ? AND status = ?",
            (status, model, json.dumps(frames) if frames is not None else None, error[:ERROR_LIMIT] if error else None, takes.now(), key, QUEUED),
        )


def _unavailable_all(reason: str) -> None:
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"UPDATE {LOOKS} SET status = ?, error = ?, updated_at = ? WHERE status = ?", (UNAVAILABLE, reason, takes.now(), QUEUED))


def embedder() -> Dict[str, Any]:
    """The image embedder of the application, as far as the looks need it: its model slug and whether it can embed here."""
    try:
        info = core_bridge.image_embedder()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the image embedder", exc_info=True)
        return {"model": None, "slug": None, "available": False}
    return {"model": info.get("model"), "slug": info.get("slug"), "available": bool(info.get("available"))}


def _ffmpeg() -> str:
    found = core_bridge.find_ffmpeg()
    if not found:
        raise chain.ChainError("ffmpeg_missing", "ffmpeg is not available on this server: the images of the take cannot be taken.", 503)
    return os.path.abspath(found) if os.path.dirname(found) else found


def _still(ffmpeg: str, source: Path, at: float, output: Path) -> List[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", num(at), "-i", str(source), "-map", "0:v:0", "-frames:v", "1", "-y", str(output)]


async def _take_frames(owner: Any, take: Mapping[str, Any], folder: Path) -> List[Tuple[float, Path]]:
    asset = chain.take_asset(take)
    found = media.locate(asset, [take], media.Resolver(owner))
    if found is None or not found.kind:
        raise chain.ChainError("no_media", "The video of the take is no longer available.")
    source = await asyncio.to_thread(media.Resolver(owner).local, found.kind, found.value, folder)
    if source is None:
        raise chain.ChainError("no_media", "The video of the take is no longer available.")
    probe = await asyncio.to_thread(core_bridge.probe_video, source)
    length = probe.duration if probe and probe.duration else float(take.get("duration_s") or 0)
    ffmpeg = _ffmpeg()
    times = sample_times(length)
    picked: List[Tuple[float, Path]] = []
    for index, at in enumerate(times):
        output = folder / f"look-{index:02d}.png"
        last = index == len(times) - 1 and len(times) > 1
        await chain.run(chain.frame_command(ffmpeg, str(source), at, output, length) if last else _still(ffmpeg, source, at, output))
        picked.append((at, output))
    return picked


async def _image_frames(owner: Any, source: Mapping[str, Any], folder: Path) -> List[Tuple[Optional[float], Path]]:
    ref = source.get("ref") or {}
    path = await asyncio.to_thread(media.Resolver(owner).local, ref.get("kind"), source.get("value"), folder)
    if path is None:
        raise chain.ChainError("no_media", "The image is no longer available.")
    return [(None, path)]


def _cast_images(owner: Any, project: Mapping[str, Any], shot_id: str) -> List[Tuple[str, Dict[str, Any], str]]:
    doc = project["doc"]
    clip = director.clip_of(doc, shot_id)
    if clip is None:
        return []
    characters, _ = bible.cast_of(doc, clip)
    found = []
    for card in characters:
        found.extend(_card_images(owner, doc, card))
    return found


def _card_images(owner: Any, doc: Mapping[str, Any], card: bible.Card) -> List[Tuple[str, Dict[str, Any], str]]:
    references = {item.get("id"): item for item in doc.get("references") or [] if isinstance(item, Mapping)}
    found = []
    for reference_id in card.references:
        asset = asset_of(doc, (references.get(reference_id) or {}).get("assetId"))
        if asset is None or asset.get("kind") != "image":
            continue
        resolved = director._resolve(owner, asset)
        if resolved is not None and resolved["media_type"] == "image":
            found.append((card.id, director.media_ref(asset.get("origin")), str(resolved["value"])))
    return found


async def compute(row: Mapping[str, Any], model: str) -> None:
    """Compute one queued look: the images of a take at its sample times, or a stored image, embedded by the image embedder of the application; the look of a take also asks for the images of the bible cards of its shot's cast."""
    owner = core_bridge.get_user(row.get("user_id")) if row.get("user_id") else None
    if owner is None:
        return _mark(row["key"], FAILED, error="The owner of this media no longer exists.")
    work = chain.work_base() / owner.id
    work.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=work))
    try:
        if row["kind"] == TAKE:
            take = takes.get_take(row["source"].get("take_id") or "")
            if take is None or take["status"] != "done":
                return _mark(row["key"], FAILED, error="The take is no longer finished.")
            picked = await _take_frames(owner, take, folder)
        else:
            picked = await _image_frames(owner, row["source"], folder)
        vectors = await asyncio.to_thread(core_bridge.embed_images, [str(path) for _, path in picked])
    except (chain.ChainError, MediaRefError) as exc:
        return _mark(row["key"], FAILED, error=getattr(exc, "message", None) or str(exc))
    except FileNotFoundError as exc:
        return _mark(row["key"], UNAVAILABLE, error=str(exc))
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    _mark(row["key"], DONE, model=model, frames=[[at, pack(vector)] for (at, _), vector in zip(picked, vectors)])
    if row["kind"] == TAKE:
        from . import projects

        project = projects.get_project(take["project_id"])
        if project is not None:
            for _, ref, value in _cast_images(owner, project, take["shot_id"]):
                if value and not _current(rows([image_key(value)]).get(image_key(value)), model):
                    queue_image(owner.id, ref, value)


def busy() -> bool:
    """True while a generation runs or waits, in this plugin or anywhere in the application: no look is computed then."""
    if takes.list_active():
        return True
    try:
        return core_bridge.generation_active()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the generation queue", exc_info=True)
        return True


async def run_once() -> bool:
    """Compute the oldest queued look, the takes first, unless a generation runs; mark every queued look unavailable when the embedder's weights are not on this server. True when one was computed."""
    row = _next()
    if row is None or busy():
        return False
    info = embedder()
    if not info["available"] or not info["slug"]:
        _unavailable_all(f"The weights of {info['model'] or 'the image embedder'} are not on this server.")
        return False
    try:
        await compute(row, info["slug"])
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] Could not compute the look of %s", row["key"], exc_info=True)
        _mark(row["key"], FAILED, error=str(exc) or "The look could not be computed.")
    return True


def _current(row: Optional[Mapping[str, Any]], model: Optional[str]) -> bool:
    return bool(row) and row["status"] == DONE and row["model"] == model


def _state(row: Optional[Mapping[str, Any]], model: Optional[str]) -> str:
    if row is None:
        return MISSING
    if row["status"] == DONE:
        return DONE if row["model"] == model else MISSING
    return row["status"]


def _vectors(row: Mapping[str, Any]) -> List[Tuple[Optional[float], Tuple[float, ...]]]:
    return [(at, unpack(vector)) for at, vector in row["frames"]]


def _near(frames: List[Tuple[Optional[float], Tuple[float, ...]]], at: float) -> Tuple[float, ...]:
    return min(frames, key=lambda frame: abs((frame[0] or 0.0) - at))[1]


def placed_take(doc: Mapping[str, Any], clip: Mapping[str, Any], project_takes: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The finished take a shot plays, or None."""
    asset = asset_of(doc, clip.get("assetId"))
    if asset is None or asset.get("kind") != "video" or not asset.get("generated"):
        return None
    return media.take_of(asset, project_takes)


def _cut(clip: Mapping[str, Any]) -> Tuple[float, float]:
    start = max(float(clip.get("srcIn") or 0), 0.0)
    return start, chain.end_of(clip)


def _seams(doc: Mapping[str, Any], project_takes: Sequence[Mapping[str, Any]], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    clips = doc.get("clips") or []
    seams = []
    for before, after in zip(clips, clips[1:]):
        left, right = placed_take(doc, before, project_takes), placed_take(doc, after, project_takes)
        if left is None or right is None:
            continue
        rows_of = [found.get(take_key(left["id"])), found.get(take_key(right["id"]))]
        states = [_state(row, model) for row in rows_of]
        score = None
        if states == [DONE, DONE]:
            score = round(cosine(_near(_vectors(rows_of[0]), _cut(before)[1]), _near(_vectors(rows_of[1]), _cut(after)[0])), 3)
        state = DONE if score is not None else next(s for s in (FAILED, UNAVAILABLE, QUEUED, MISSING) if s in states)
        seams.append({"shot_id": after["id"], "previous_id": before["id"], "from_take": left["id"], "to_take": right["id"], "score": score, "status": state})
    return seams


def _cards(take_row: Optional[Mapping[str, Any]], images: Sequence[Tuple[str, Dict[str, Any], str]], cards: Sequence[bible.Card], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    frames = _vectors(take_row) if _current(take_row, model) else []
    result = []
    for card in cards:
        mine = [value for card_id, _, value in images if card_id == card.id]
        if not mine:
            result.append({"card_id": card.id, "label": card.label, "score": None, "status": "no_images"})
            continue
        ready = [found.get(image_key(value)) for value in mine]
        done = [row for row in ready if _current(row, model)]
        if not frames or not done:
            states = [_state(row, model) for row in ready] + ([_state(take_row, model)] if not frames else [])
            state = next((s for s in (FAILED, UNAVAILABLE, QUEUED, MISSING) if s in states), MISSING)
            result.append({"card_id": card.id, "label": card.label, "score": None, "status": state})
            continue
        score = max(cosine(vector, image) for _, vector in frames for row in done for _, image in _vectors(row))
        result.append({"card_id": card.id, "label": card.label, "score": round(score, 3), "status": DONE})
    return result


def report(owner: Any, project: Mapping[str, Any], enqueue: bool = False) -> Dict[str, Any]:
    """The looks of a project's finished takes, from the stored ones: the score of each seam between two placed takes, at the end of the cut of the first and the start of the cut of the second, and for each take the score of each bible card of its shot's cast, the best match of its images with the card's pictures. With enqueue, every look missing for the project is asked for first."""
    doc = project["doc"]
    info = embedder()
    model = info["slug"]
    project_takes = [take for take in takes.list_takes(project["id"]) if take["status"] == "done" and take.get("file_path")]
    shots = {take["shot_id"] for take in project_takes}
    images = {shot_id: _cast_images(owner, project, shot_id) for shot_id in shots}
    keys = [take_key(take["id"]) for take in project_takes] + [image_key(value) for found in images.values() for _, _, value in found]
    found = rows(keys)
    if enqueue:
        for take in project_takes:
            if not _current(found.get(take_key(take["id"])), model) and _state(found.get(take_key(take["id"])), model) != QUEUED:
                queue_take(take)
        unique: Dict[str, Tuple[str, Dict[str, Any], str]] = {}
        for items in images.values():
            for item in items:
                unique.setdefault(item[2], item)
        for _, ref, value in unique.values():
            if not _current(found.get(image_key(value)), model) and _state(found.get(image_key(value)), model) != QUEUED:
                queue_image(owner.id, ref, value)
        found = rows(keys)
    takes_out = []
    for take in project_takes:
        clip = director.clip_of(doc, take["shot_id"])
        characters = bible.cast_of(doc, clip)[0] if clip is not None else []
        row = found.get(take_key(take["id"]))
        takes_out.append({"take_id": take["id"], "shot_id": take["shot_id"], "status": _state(row, model), "cards": _cards(row, images.get(take["shot_id"], []), characters, found, model)})
    states = [_state(found.get(key), model) for key in keys]
    return {
        "embedder": {"model": info["model"], "available": info["available"]},
        "thresholds": {"seam": SEAM_LOW, "cast": CAST_LOW},
        "seams": _seams(doc, project_takes, found, model),
        "takes": takes_out,
        "missing": sum(1 for state in states if state in (MISSING, FAILED, UNAVAILABLE)),
        "queued": sum(1 for state in states if state == QUEUED),
    }
