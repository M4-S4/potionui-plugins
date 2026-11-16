import asyncio
import copy
import logging
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple

from PIL import Image, ImageOps

from . import core_bridge, formats, tables, workdir
from .core_bridge import LimitExceeded, MediaRefError, User

logger = logging.getLogger(__name__)

TOLERANCE = formats.EXACT_LOSS

MAX_PIXELS = int(formats.TABLE["startImages"]["maxPixels"])

TURNED = (2, 3, 4, 5, 6, 7, 8)

ORIENTATION = 0x0112

CROPS = "video_producer_frame_crops"

ROLES = ("first", "last")

READABLE = ("PNG", "JPEG", "GIF", "WEBP", "BMP")

PHOTOS = ("JPEG", "MPO")

PHOTO_MODES = ("RGB", "L", "CMYK")

PHOTO_QUALITY = 95

NAME_LENGTH = 80

UNSAFE = re.compile(r"[\x00-\x1f\x7f/\\:*?\"<>|]+")

STORAGE_FULL = "storage_full"

UPLOAD_TOO_LARGE = "upload_too_large"

TOO_MANY_PIXELS = "too_many_pixels"

FAILED = "failed"

MESSAGES = {
    STORAGE_FULL: "is sent as it is, not cropped to the frame of the take: the storage of the project's owner is full.",
    UPLOAD_TOO_LARGE: "is sent as it is, not cropped to the frame of the take: its crop is larger than the largest file the project's owner may upload.",
    TOO_MANY_PIXELS: f"is sent as it is, not cropped to the frame of the take: it has more than {MAX_PIXELS // 1_000_000} million pixels.",
    FAILED: "is sent as it is: it could not be cropped to the frame of the take.",
}

LIMIT_CAUSES = {"storage_quota_exceeded": STORAGE_FULL, "upload_file_size_exceeded": UPLOAD_TOO_LARGE}

Ratio = Tuple[int, int]

Box = Tuple[int, int, int, int]

Stamp = Tuple[int, int]


class CropError(Exception):
    code = "frame_not_cropped"

    def __init__(self, cause: str = FAILED):
        self.cause = cause if cause in MESSAGES else FAILED
        self.message = MESSAGES[self.cause]
        super().__init__(self.message)


@dataclass(frozen=True)
class Fitted:
    source: str
    value: str
    item_id: Optional[str]
    width: int
    height: int


def ratio_of(value: Any) -> Optional[Ratio]:
    size = formats.parse_size(value)
    if size is not None:
        exact = Fraction(size[0], size[1])
    else:
        ratio = formats.ratio_of(value)
        if ratio is None:
            return None
        exact = Fraction(ratio).limit_denominator(1000)
    return exact.numerator, exact.denominator


def ratio_text(ratio: Ratio) -> str:
    return f"{ratio[0]}:{ratio[1]}"


def request_ratio(resolution: Any, request: Optional[Mapping[str, Any]] = None, aspect: Any = None) -> Optional[Ratio]:
    if formats.parse_size(resolution) is not None:
        return ratio_of(resolution)
    form = (request or {}).get("form_data") or {}
    for candidate in (form.get("aspect_ratio"), aspect):
        found = ratio_of(candidate) if candidate is not None else None
        if found is not None:
            return found
    return None


def plan_ratio(plan: Any) -> Optional[Ratio]:
    return request_ratio(plan.resolution, plan.request, (plan.cloud_params or {}).get("aspect_ratio"))


def lost(width: int, height: int, ratio: Ratio) -> float:
    return formats.loss(width / height, ratio[0] / ratio[1])


def _even(value: float, limit: int) -> int:
    rounded = max(2, 2 * round(value / 2))
    return rounded if rounded <= limit else limit - limit % 2


def crop_box(width: int, height: int, ratio: Ratio) -> Optional[Box]:
    if width < 2 or height < 2 or lost(width, height, ratio) <= TOLERANCE:
        return None
    wanted = ratio[0] / ratio[1]
    if width / height > wanted:
        kept_height = height - height % 2
        kept_width = _even(kept_height * wanted, width)
    else:
        kept_width = width - width % 2
        kept_height = _even(kept_width / wanted, height)
    if kept_width < 2 or kept_height < 2 or lost(kept_width, kept_height, ratio) > TOLERANCE:
        return None
    return (width - kept_width) // 2, (height - kept_height) // 2, kept_width, kept_height


def too_large(width: int, height: int) -> bool:
    return width * height > MAX_PIXELS


class Picture(NamedTuple):
    width: int
    height: int
    turned: bool = False
    oversize: bool = False


def _orientation(image: Image.Image) -> Any:
    if image.format == "PNG" and "exif" not in image.info:
        return None
    return image.getexif().get(ORIENTATION)


def picture(path: Optional[Path]) -> Optional[Picture]:
    if path is None:
        return None
    try:
        with Image.open(path, formats=READABLE) as image:
            width, height = image.size
            orientation = _orientation(image)
    except Image.DecompressionBombError:
        return Picture(0, 0, False, True)
    except Exception:
        return None
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return Picture(width, height, orientation in TURNED, too_large(width, height))


def picture_size(path: Optional[Path]) -> Optional[Tuple[int, int]]:
    found = picture(path)
    return None if found is None or found.oversize and not found.width else (found.width, found.height)


def decide(found: Picture, ratio: Ratio) -> Tuple[Optional[Box], Optional[str]]:
    if found.oversize and not found.width:
        return None, TOO_MANY_PIXELS
    box = crop_box(found.width, found.height, ratio) or ((0, 0, found.width, found.height) if found.turned else None)
    if box is None:
        return None, None
    if found.oversize:
        return None, TOO_MANY_PIXELS
    return box, None


def stamp(path: Optional[Path]) -> Optional[Stamp]:
    if path is None:
        return None
    try:
        found = path.stat()
    except OSError:
        return None
    return found.st_size, found.st_mtime_ns


def bound(request: Mapping[str, Any]) -> List[Dict[str, Any]]:
    document = ((request or {}).get("form_data") or {}).get("video_director")
    if not isinstance(document, Mapping):
        return []
    return [
        entry
        for entry in document.get("media") or []
        if isinstance(entry, Mapping) and entry.get("role") in ROLES and (entry.get("media") or {}).get("type") == "image"
    ]


def values(request: Mapping[str, Any]) -> List[str]:
    found = [str((entry.get("media") or {}).get("path") or "") for entry in bound(request)]
    return list(dict.fromkeys(value for value in found if value))


def roles(request: Mapping[str, Any]) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for entry in bound(request):
        value = str((entry.get("media") or {}).get("path") or "")
        if value and entry["role"] not in found.setdefault(value, []):
            found[value].append(entry["role"])
    return found


def replace(request: Mapping[str, Any], old: str, new: str) -> Dict[str, Any]:
    changed = copy.deepcopy(dict(request))
    for entry in bound(changed):
        media = entry["media"]
        for key in ("path", "relative_path"):
            if media.get(key) == old:
                media[key] = new
    return changed


def _key(user_id: str, source: str, ratio: Ratio) -> str:
    return f"{user_id}|{ratio_text(ratio)}|{source}"


def _table(work):
    from src.plugin_api import db

    try:
        with db.get_cursor() as cursor:
            return work(cursor)
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
    tables.create_table(CROPS)
    with db.get_cursor() as cursor:
        return work(cursor)


@dataclass(frozen=True)
class Row:
    fitted: Fitted
    stamp: Optional[Stamp]


def recorded(user_id: str, source: str, ratio: Ratio) -> Optional[Row]:
    def work(cursor):
        cursor.execute(f"SELECT value, item_id, width, height, source_bytes, source_mtime FROM {CROPS} WHERE key = ?", (_key(user_id, source, ratio),))
        return cursor.fetchone()

    row = _table(work)
    if row is None:
        return None
    fitted = Fitted(source=source, value=row["value"], item_id=row["item_id"], width=int(row["width"]), height=int(row["height"]))
    found = (int(row["source_bytes"]), int(row["source_mtime"])) if row["source_bytes"] is not None and row["source_mtime"] is not None else None
    return Row(fitted=fitted, stamp=found)


def record(user_id: str, ratio: Ratio, fitted: Fitted, source_stamp: Optional[Stamp]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    size, changed = source_stamp if source_stamp is not None else (None, None)

    def work(cursor):
        cursor.execute(
            f"INSERT INTO {CROPS} (key, user_id, source, ratio, value, item_id, width, height, source_bytes, source_mtime, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, item_id = excluded.item_id, width = excluded.width, height = excluded.height, "
            "source_bytes = excluded.source_bytes, source_mtime = excluded.source_mtime, created_at = excluded.created_at",
            (_key(user_id, fitted.source, ratio), user_id, fitted.source, ratio_text(ratio), fitted.value, fitted.item_id, fitted.width, fitted.height, size, changed, now),
        )

    _table(work)


def forget(user_id: str, source: str, ratio: Ratio) -> None:
    def work(cursor):
        cursor.execute(f"DELETE FROM {CROPS} WHERE key = ?", (_key(user_id, source, ratio),))

    _table(work)


def _still_there(owner: User, fitted: Fitted) -> bool:
    if not fitted.item_id:
        return False
    try:
        resolved = core_bridge.resolve_media(owner, {"kind": "library", "item_id": fitted.item_id})
    except MediaRefError:
        return False
    return str(resolved.get("value")) == fitted.value


def _known(owner: User, source: str, ratio: Ratio, source_stamp: Optional[Stamp]) -> Optional[Fitted]:
    found = recorded(owner.id, source, ratio)
    if found is None:
        return None
    fresh = source_stamp is None or found.stamp is None or found.stamp == source_stamp
    if fresh and _still_there(owner, found.fitted):
        return found.fitted
    forget(owner.id, source, ratio)
    return None


def _local(owner: User, ref: Mapping[str, Any]) -> Optional[Path]:
    try:
        path = core_bridge.media_file_path(owner, ref)
    except Exception:
        return None
    return Path(path) if path and Path(path).is_file() else None


def _copied(owner: User, ref: Mapping[str, Any], folder: Path) -> Optional[Path]:
    try:
        return core_bridge.local_media_file(owner, ref, folder)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the picture %s to crop it", ref, exc_info=True)
        return None


def cropped_name(name: str, box: Box, suffix: str = ".png", word: str = "crop") -> str:
    stem = re.split(r"[/\\]", str(name or ""))[-1]
    stem = Path(stem).stem if "." in stem.strip(".") else stem
    stem = UNSAFE.sub("-", stem).strip(" .-")[:NAME_LENGTH].strip(" .-") or "image"
    return f"{stem}-{word}-{box[2]}x{box[3]}{suffix}"


def crop_file(source: Path, box: Box, folder: Path, name: str) -> Path:
    left, top, width, height = box
    with Image.open(source, formats=READABLE) as opened:
        photo = opened.format in PHOTOS
        profile = opened.info.get("icc_profile")
        mode = opened.mode
        image = ImageOps.exif_transpose(opened)
        word = "upright" if (left, top, width, height) == (0, 0, *image.size) else "crop"
        kept = image.crop((left, top, left + width, top + height))
        if photo and kept.mode in PHOTO_MODES:
            output = folder / cropped_name(name, box, ".jpg", word)
            kept = kept if kept.mode in ("RGB", "L") else kept.convert("RGB")
            kept.save(output, format="JPEG", quality=PHOTO_QUALITY, subsampling=0, icc_profile=profile if kept.mode == mode else None)
            return output
        if kept.mode not in ("1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"):
            kept = kept.convert("RGB")
        output = folder / cropped_name(name, box, ".png", word)
        kept.save(output, format="PNG", icc_profile=profile if kept.mode == mode else None)
    return output


def _stored_cause(exc: Exception) -> str:
    if isinstance(exc, LimitExceeded):
        return LIMIT_CAUSES.get(str(exc.primary.get("code")), FAILED)
    return FAILED


async def _fit(owner: User, source: str, ref: Mapping[str, Any], ratio: Ratio, name: str, refused: Optional[str]) -> Optional[Fitted]:
    path = await asyncio.to_thread(_local, owner, ref)
    source_stamp = await asyncio.to_thread(stamp, path)
    known = await asyncio.to_thread(_known, owner, source, ratio, source_stamp)
    if known is not None:
        return known
    folders: List[Path] = []
    try:
        local_file = path
        if local_file is None:
            try:
                folders.append(workdir.scratch(workdir.FRAMES, owner.id))
            except Exception:
                logger.warning("[VIDEO-PRODUCER] No work folder to read the picture %s in", ref, exc_info=True)
                return None
            local_file = await asyncio.to_thread(_copied, owner, ref, folders[-1])
            if local_file is None:
                return None
        found = await asyncio.to_thread(picture, local_file)
        if found is None:
            return None
        box, cause = decide(found, ratio)
        if cause is not None:
            raise CropError(cause)
        if box is None:
            return None
        if refused is not None:
            raise CropError(refused)
        folders.append(workdir.scratch(workdir.FRAMES, owner.id))
        output = await asyncio.to_thread(crop_file, local_file, box, folders[-1], name)
        try:
            stored = await core_bridge.save_user_media(owner, output)
        except Exception as exc:
            cause = _stored_cause(exc)
            logger.warning("[VIDEO-PRODUCER] Could not store the cropped picture of %s (%s)", source, cause, exc_info=cause == FAILED)
            raise CropError(cause) from None
    finally:
        for folder in folders:
            await asyncio.to_thread(shutil.rmtree, folder, True)
    fitted = Fitted(source=source, value=str(stored["value"]), item_id=(stored.get("ref") or {}).get("item_id"), width=box[2], height=box[3])
    await asyncio.to_thread(record, owner.id, ratio, fitted, source_stamp)
    return fitted


async def fit(owner: User, source: str, ref: Mapping[str, Any], ratio: Ratio, name: str, refused: Optional[str] = None) -> Optional[Fitted]:
    try:
        return await _fit(owner, source, ref, ratio, name, refused)
    except CropError as exc:
        failure = exc
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not crop the picture %s", source, exc_info=True)
        failure = CropError(FAILED)
    logger.warning("[VIDEO-PRODUCER] The picture %s is not cropped (%s): the take gets it as it is", source, failure.cause)
    raise failure
