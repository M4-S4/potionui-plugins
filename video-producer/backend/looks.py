import asyncio
import base64
import json
import logging
import os
import shutil
import statistics
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import bible, chain, core_bridge, director, takes, workdir
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
FACE_LOW = 0.70
PLACE_LOW = 0.55
FINAL_LOW = 0.80
DRIFT_LOW = 0.80
PUSH_IN_HIGH = 1.5
IDENTITY_LOW = 0.50
END_WINDOW = 1.0

FACE_SCALE = 1.8
MIN_FACE = 32
FRONTAL_SCORE = 0.9
FRONTAL_TURN = 0.35
FRONTAL_EYES = 0.35
FACES = "faces"
IDENTITY = "identity"
FACE = "face"
WHOLE = "whole"
CHARACTER = "character"
PLACE = "place"

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
    """Ask for the look of a finished take, a start or end image candidate included."""
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


def face_detector() -> Dict[str, Any]:
    """The face detector of the application, as far as the looks need it: its model file and whether it can detect here."""
    try:
        info = core_bridge.face_detector()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the face detector", exc_info=True)
        return {"model": None, "available": False}
    return {"model": info.get("model"), "available": bool(info.get("available"))}


def identifier() -> Dict[str, Any]:
    """The face recognition model of the application, as far as the looks need it: its model file and whether it is there."""
    try:
        info = core_bridge.face_identifier()
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the face recognition model", exc_info=True)
        return {"model": None, "available": False}
    return {"model": info.get("model"), "available": bool(info.get("available"))}


def measure_key(info: Mapping[str, Any], faces: Mapping[str, Any], identity: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """The name a look is measured under: the embedder's slug, marked when the faces are cropped too and again when they are identified, so that a look measured without the face detector or the face recognition counts as missing once it is here."""
    slug = info.get("slug")
    if not slug or not faces.get("available"):
        return slug
    return f"{slug}+{FACES}+{IDENTITY}" if identity and identity.get("available") else f"{slug}+{FACES}"


def frontal(face: Mapping[str, Any]) -> bool:
    """True for a face seen from the front, which a face recognition can read: a sure detection, the nose near the middle of the eyes and the eyes far enough apart for the width of the face."""
    points = face.get("landmarks") or []
    if len(points) < 3 or float(face.get("score") or 0) < FRONTAL_SCORE or float(face.get("width") or 0) <= 0:
        return False
    (right_x, right_y), (left_x, left_y), (nose_x, _) = points[0], points[1], points[2]
    span = ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5
    return span > 0 and abs(nose_x - (right_x + left_x) / 2) / span <= FRONTAL_TURN and span / float(face["width"]) >= FRONTAL_EYES


def _face_crop(path: Path, box: Mapping[str, float], output: Path) -> Path:
    from PIL import Image

    with Image.open(path) as image:
        picture = image.convert("RGB")
    side = min(max(float(box["width"]), float(box["height"])) * FACE_SCALE, float(max(picture.width, picture.height)))
    left = min(max(float(box["x"]) + float(box["width"]) / 2 - side / 2, 0.0), max(picture.width - side, 0.0))
    top = min(max(float(box["y"]) + float(box["height"]) / 2 - side / 2, 0.0), max(picture.height - side, 0.0))
    picture.crop((round(left), round(top), round(min(left + side, picture.width)), round(min(top + side, picture.height)))).save(output)
    return output


def overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """The share of the smaller of two face boxes that the other covers, 0 when they do not meet."""
    width = min(float(a["x"]) + float(a["width"]), float(b["x"]) + float(b["width"])) - max(float(a["x"]), float(b["x"]))
    height = min(float(a["y"]) + float(a["height"]), float(b["y"]) + float(b["height"])) - max(float(a["y"]), float(b["y"]))
    smaller = min(float(a["width"]) * float(a["height"]), float(b["width"]) * float(b["height"]))
    return width * height / smaller if width > 0 and height > 0 and smaller > 0 else 0.0


def follow(followed: Optional[Mapping[str, Any]], faces: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The face of an image that goes on with the one followed so far: the best face when none is followed yet, else the face whose box covers most of it, or None when no face meets it."""
    if not faces:
        return None
    if followed is None:
        return faces[0]
    best = max(faces, key=lambda face: overlap(followed, face))
    return best if overlap(followed, best) > 0 else None


def _face_vectors(picked: Sequence[Tuple[Any, Path]], folder: Path, identify: bool = False) -> List[Tuple[Optional[List[float]], Optional[float], Optional[List[float]]]]:
    found: List[Optional[List[float]]] = [None] * len(picked)
    heights: List[Optional[float]] = [None] * len(picked)
    identities: List[Optional[List[float]]] = [None] * len(picked)
    try:
        boxes = core_bridge.detect_faces([str(path) for _, path in picked])
    except FileNotFoundError:
        return list(zip(found, heights, identities))
    crops: List[Tuple[int, Path]] = []
    readable: List[Tuple[int, str, Any]] = []
    followed: Optional[Mapping[str, Any]] = None
    for index, ((_, path), faces) in enumerate(zip(picked, boxes)):
        face = follow(followed, faces)
        if face is not None:
            followed = face
            heights[index] = round(float(face["height"]), 1)
            if identify and float(face["height"]) >= MIN_FACE and frontal(face):
                readable.append((index, str(path), face["landmarks"]))
        large = [face for face in faces if float(face["height"]) >= MIN_FACE]
        if large:
            crops.append((index, _face_crop(Path(path), large[0], folder / f"face-{index:02d}.png")))
    vectors = core_bridge.embed_images([str(path) for _, path in crops]) if crops else []
    for (index, _), vector in zip(crops, vectors):
        found[index] = vector
    if readable:
        try:
            read = core_bridge.identify_faces([(path, landmarks) for _, path, landmarks in readable])
        except FileNotFoundError:
            read = []
        for (index, _, _), vector in zip(readable, read):
            identities[index] = vector
    return list(zip(found, heights, identities))


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
    if take.get("kind") == takes.KEYFRAME:
        return [(0.0, source)]
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
    characters, place = bible.cast_of(doc, clip)
    found = []
    for card in [*characters, *([place] if place is not None else [])]:
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


async def compute(row: Mapping[str, Any], model: str, faces: bool = False, identity: bool = False) -> None:
    """Compute one queued look: the images of a take at its sample times, or a stored image, embedded by the image embedder of the application, with faces the best face of each image cropped and embedded too, and with identity the followed face identified where it is seen from the front; the look of a take also asks for the images of the bible cards of its shot's cast."""
    owner = core_bridge.get_user(row.get("user_id")) if row.get("user_id") else None
    if owner is None:
        return _mark(row["key"], FAILED, error="The owner of this media no longer exists.")
    try:
        folder = workdir.scratch(workdir.FRAMES, owner.id)
    except workdir.WorkdirError as exc:
        return _mark(row["key"], FAILED, error=exc.message)
    try:
        if row["kind"] == TAKE:
            take = takes.get_take(row["source"].get("take_id") or "")
            if take is None or take["status"] != "done":
                return _mark(row["key"], FAILED, error="The take is no longer finished.")
            picked = await _take_frames(owner, take, folder)
        else:
            picked = await _image_frames(owner, row["source"], folder)
        vectors = await asyncio.to_thread(core_bridge.embed_images, [str(path) for _, path in picked])
        crops = await asyncio.to_thread(_face_vectors, picked, folder, identity) if faces else [(None, None, None)] * len(picked)
    except (chain.ChainError, MediaRefError) as exc:
        return _mark(row["key"], FAILED, error=getattr(exc, "message", None) or str(exc))
    except FileNotFoundError as exc:
        return _mark(row["key"], UNAVAILABLE, error=str(exc))
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    _mark(row["key"], DONE, model=model, frames=[[at, pack(vector), pack(face) if face else None, height, pack(known) if known else None] for (at, _), vector, (face, height, known) in zip(picked, vectors, crops)])
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
    faces = face_detector()
    identity = identifier()
    try:
        await compute(row, measure_key(info, faces, identity), faces["available"], faces["available"] and identity["available"])
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] Could not compute the look of %s", row["key"], exc_info=True)
        _mark(row["key"], FAILED, error=str(exc) or "The look could not be computed.")
    return True


def _current(row: Optional[Mapping[str, Any]], model: Optional[str]) -> bool:
    return bool(row) and row["status"] == DONE and row["model"] == model


def _unsized(row: Optional[Mapping[str, Any]], model: Optional[str]) -> bool:
    return _current(row, model) and f"+{FACES}" in str(model or "") and any(len(frame) < 4 for frame in row["frames"] or [])


def _state(row: Optional[Mapping[str, Any]], model: Optional[str]) -> str:
    if row is None:
        return MISSING
    if row["status"] == DONE:
        return DONE if row["model"] == model else MISSING
    return row["status"]


def _vectors(row: Mapping[str, Any]) -> List[Tuple[Optional[float], Tuple[float, ...]]]:
    return [(frame[0], unpack(frame[1])) for frame in row["frames"]]


def _faces(row: Mapping[str, Any]) -> List[Tuple[Optional[float], Tuple[float, ...]]]:
    return [(frame[0], unpack(frame[2])) for frame in row["frames"] if len(frame) > 2 and frame[2]]


def push_in(row: Optional[Mapping[str, Any]], model: Optional[str]) -> Optional[float]:
    """How many times the face a take shows grows from the first image that shows one to the largest, or None without two such images."""
    if not _current(row, model):
        return None
    heights = [float(frame[3]) for frame in row["frames"] or [] if len(frame) > 3 and frame[3]]
    return round(max(heights) / heights[0], 2) if len(heights) > 1 else None


def _identities(row: Mapping[str, Any]) -> List[Tuple[Optional[float], Tuple[float, ...]]]:
    return [(frame[0], unpack(frame[4])) for frame in row["frames"] or [] if len(frame) > 4 and frame[4]]


def identity_drift(row: Optional[Mapping[str, Any]], model: Optional[str]) -> Optional[Dict[str, Any]]:
    """How much of the first face a take shows from the front is left at its end, by face recognition: the median cosine with the first of its frontal images of the last second, or of its last frontal image when that second shows none, and the time of the last one; None without two frontal images. A face turned away and back in between does not count, a face that ends as someone else does."""
    if not _current(row, model):
        return None
    known = _identities(row)
    if len(known) < 2:
        return None
    first, later = known[0][1], known[1:]
    end = max(float(frame[0] or 0.0) for frame in row["frames"])
    last = [(at, vector) for at, vector in later if float(at or 0.0) >= end - END_WINDOW] or later[-1:]
    score = statistics.median(cosine(first, vector) for _, vector in last)
    return {"score": round(score, 3), "at": last[-1][0]}


def _signature(faces: Sequence[Tuple[Optional[float], Tuple[float, ...]]]) -> Optional[Tuple[float, ...]]:
    if not faces:
        return None
    total = [sum(values) for values in zip(*(face for _, face in faces))]
    norm = sum(value * value for value in total) ** 0.5
    return tuple(value / norm for value in total) if norm else None


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
        score = identity = None
        if states == [DONE, DONE]:
            score = round(cosine(_near(_vectors(rows_of[0]), _cut(before)[1]), _near(_vectors(rows_of[1]), _cut(after)[0])), 3)
            if _chained(doc, after):
                identity = _seam_identity(rows_of[0], rows_of[1], _cut(before)[1], _cut(after)[0])
        state = DONE if score is not None else next(s for s in (FAILED, UNAVAILABLE, QUEUED, MISSING) if s in states)
        seams.append({"shot_id": after["id"], "previous_id": before["id"], "from_take": left["id"], "to_take": right["id"], "score": score, "identity": identity, "status": state})
    return seams


def _seam_identity(before: Mapping[str, Any], after: Mapping[str, Any], end: float, start: float) -> Optional[float]:
    left, right = _identities(before), _identities(after)
    if not left or not right:
        return None
    return round(cosine(_near(left, end), _near(right, start)), 3)


def _cards(take_row: Optional[Mapping[str, Any]], images: Sequence[Tuple[str, Dict[str, Any], str]], cards: Sequence[bible.Card], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    current = _current(take_row, model)
    frames = _vectors(take_row) if current else []
    faces = _faces(take_row) if current else []
    cropping = f"+{FACES}" in str(model or "")
    result = []
    for card in cards:
        kind = PLACE if card.kind == bible.PLACES else CHARACTER
        entry = {"card_id": card.id, "label": card.label, "kind": kind, "score": None, "method": None, "seen": None}
        mine = [value for card_id, _, value in images if card_id == card.id]
        if not mine:
            result.append({**entry, "status": "no_images"})
            continue
        ready = [found.get(image_key(value)) for value in mine]
        done = [row for row in ready if _current(row, model)]
        if not frames or not done:
            states = [_state(row, model) for row in ready] + ([_state(take_row, model)] if not frames else [])
            state = next((s for s in (FAILED, UNAVAILABLE, QUEUED, MISSING) if s in states), MISSING)
            result.append({**entry, "status": state})
            continue
        pictures = [image for row in done for _, image in _vectors(row)]
        portraits = [face for row in done for _, face in _faces(row)]
        if kind == PLACE:
            score = statistics.median(max(cosine(vector, image) for image in pictures) for _, vector in frames)
            result.append({**entry, "score": round(score, 3), "method": WHOLE, "status": DONE})
        elif faces and portraits:
            score = statistics.median(max(cosine(face, portrait) for portrait in portraits) for _, face in faces)
            result.append({**entry, "score": round(score, 3), "method": FACE, "seen": round(len(faces) / len(frames), 3), "status": DONE})
        else:
            score = max(cosine(vector, image) for _, vector in frames for image in pictures)
            result.append({**entry, "score": round(score, 3), "method": WHOLE, "seen": 0.0 if cropping else None, "status": DONE})
    return result


def _chained(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> bool:
    own = clip.get("firstFromPrevious")
    return own if isinstance(own, bool) else doc.get("firstFromPrevious") is not False


def chained_pairs(doc: Mapping[str, Any], project_takes: Sequence[Mapping[str, Any]]) -> List[Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]]:
    """The neighbor shots whose second starts from the last frame of the first and casts characters, with the take the first plays."""
    clips = doc.get("clips") or []
    found = []
    for before, after in zip(clips, clips[1:]):
        take = placed_take(doc, before, project_takes)
        if take is not None and _chained(doc, after) and bible.cast_of(doc, after)[0]:
            found.append((before, after, take))
    return found


def _chains(doc: Mapping[str, Any], project_takes: Sequence[Mapping[str, Any]], images: Mapping[str, Sequence[Tuple[str, Dict[str, Any], str]]], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    result = []
    for before, after, take in chained_pairs(doc, project_takes):
        row = found.get(take_key(take["id"]))
        if _current(row, model) and row["frames"]:
            end = _cut(before)[1]
            row = {**row, "frames": [min(row["frames"], key=lambda frame: abs((frame[0] or 0.0) - end))]}
        cards = _cards(row, images.get(after["id"], []), bible.cast_of(doc, after)[0], found, model)
        result.append({"shot_id": after["id"], "previous_id": before["id"], "from_take": take["id"], "cards": cards})
    return result


def _finals(project_takes: Sequence[Mapping[str, Any]], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    by_id = {take["id"]: take for take in project_takes}
    result = []
    for take in project_takes:
        parent = by_id.get(take.get("parent_take_id") or "")
        if take.get("quality") != "final" or parent is None:
            continue
        rows_of = [found.get(take_key(take["id"])), found.get(take_key(parent["id"]))]
        states = [_state(row, model) for row in rows_of]
        entry = {"take_id": take["id"], "parent_id": parent["id"], "shot_id": take["shot_id"], "score": None, "face": None}
        if states != [DONE, DONE]:
            result.append({**entry, "status": next(s for s in (FAILED, UNAVAILABLE, QUEUED, MISSING) if s in states)})
            continue
        mine, theirs = _vectors(rows_of[0]), _vectors(rows_of[1])
        score = statistics.median(cosine(vector, _near(theirs, at or 0.0)) for at, vector in mine)
        faces, parent_faces = _faces(rows_of[0]), _faces(rows_of[1])
        face = statistics.median(max(cosine(item, other) for _, other in parent_faces) for _, item in faces) if faces and parent_faces else None
        result.append({**entry, "score": round(score, 3), "face": round(face, 3) if face is not None else None, "status": DONE})
    return result


def _drift(doc: Mapping[str, Any], project_takes: Sequence[Mapping[str, Any]], found: Mapping[str, Mapping[str, Any]], model: Optional[str]) -> List[Dict[str, Any]]:
    placed: List[Tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for clip in doc.get("clips") or []:
        take = placed_take(doc, clip, project_takes)
        if take is not None:
            placed.append((clip, take))
    result = []
    for card in bible.cards(doc, bible.CHARACTERS):
        signed = []
        for clip, take in placed:
            row = found.get(take_key(take["id"]))
            if card.id in {item.id for item in bible.cast_of(doc, clip)[0]} and _current(row, model):
                signature = _signature(_faces(row))
                if signature is not None:
                    signed.append((clip, take, signature))
        if len(signed) < 3:
            continue
        for clip, take, signature in signed:
            others = [cosine(signature, other) for _, item, other in signed if item["id"] != take["id"]]
            result.append({"card_id": card.id, "shot_id": clip["id"], "take_id": take["id"], "score": round(sum(others) / len(others), 3)})
    return result


def report(owner: Any, project: Mapping[str, Any], enqueue: bool = False) -> Dict[str, Any]:
    """The looks of a project's finished takes, from the stored ones: the score of each seam between two placed takes, at the end of the cut of the first and the start of the cut of the second, and for each take and each start or end image candidate the score of each bible card of its shot's cast, the best match of its images with the card's pictures. With enqueue, every look missing for the project is asked for first."""
    doc = project["doc"]
    info = embedder()
    faces = face_detector()
    identity = identifier()
    model = measure_key(info, faces, identity)
    project_takes = [take for take in takes.list_takes(project["id"]) if take["status"] == "done" and take.get("file_path")]
    candidates = [take for take in takes.list_keyframes(project["id"]) if take["status"] == "done" and take.get("file_path")]
    shots = {take["shot_id"] for take in (*project_takes, *candidates)} | {after["id"] for _, after, _ in chained_pairs(doc, project_takes)}
    images = {shot_id: _cast_images(owner, project, shot_id) for shot_id in shots}
    keys = [take_key(take["id"]) for take in (*project_takes, *candidates)] + [image_key(value) for found in images.values() for _, _, value in found]
    found = rows(keys)
    if enqueue:
        for take in (*project_takes, *candidates):
            row = found.get(take_key(take["id"]))
            stale = not _current(row, model) or (take.get("kind") != takes.KEYFRAME and _unsized(row, model))
            if stale and _state(row, model) != QUEUED:
                queue_take(take)
        unique: Dict[str, Tuple[str, Dict[str, Any], str]] = {}
        for items in images.values():
            for item in items:
                unique.setdefault(item[2], item)
        for _, ref, value in unique.values():
            if not _current(found.get(image_key(value)), model) and _state(found.get(image_key(value)), model) != QUEUED:
                queue_image(owner.id, ref, value)
        found = rows(keys)
    def measured(take: Mapping[str, Any]) -> Dict[str, Any]:
        clip = director.clip_of(doc, take["shot_id"])
        characters, place = bible.cast_of(doc, clip) if clip is not None else ([], None)
        row = found.get(take_key(take["id"]))
        cast = [*characters, *([place] if place is not None else [])]
        return {"take_id": take["id"], "shot_id": take["shot_id"], "status": _state(row, model), "cards": _cards(row, images.get(take["shot_id"], []), cast, found, model), "push_in": push_in(row, model), "identity": identity_drift(row, model)}

    takes_out = [measured(take) for take in project_takes]
    states = [_state(found.get(key), model) for key in keys]
    return {
        "embedder": {"model": info["model"], "available": info["available"]},
        "faces": {"model": faces["model"], "available": faces["available"]},
        "identity": {"model": identity["model"], "available": identity["available"]},
        "thresholds": {"seam": SEAM_LOW, "cast": CAST_LOW, "face": FACE_LOW, "place": PLACE_LOW, "final": FINAL_LOW, "drift": DRIFT_LOW, "push_in": PUSH_IN_HIGH, "identity": IDENTITY_LOW},
        "seams": _seams(doc, project_takes, found, model),
        "takes": takes_out,
        "candidates": [measured(take) for take in candidates],
        "finals": _finals(project_takes, found, model),
        "chains": _chains(doc, project_takes, images, found, model),
        "drift": _drift(doc, project_takes, found, model),
        "missing": sum(1 for state in states if state in (MISSING, FAILED, UNAVAILABLE)),
        "queued": sum(1 for state in states if state == QUEUED),
    }
