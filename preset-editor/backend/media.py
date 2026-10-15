import io
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

import yaml
from PIL import Image

from src.plugin_api.presets import PRESET_COVER_VIDEO_MAX_BYTES, PRESET_MEDIA_MAX_BYTES, downscale_and_save_webp

from . import files
from .files import FilesError, MEDIA_EXTENSIONS, PUBLIC_DIR

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
CONVERTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm"})
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LONG_EDGE = {"cover": 1024, "gallery": 1024, "example": 1024}
ROLES = ("cover", "gallery", "example")
MAX_CAPTION_LENGTH = 200
MAX_GALLERY_ITEMS = 50
STYLES_PREFIX = f"{PUBLIC_DIR}/styles/"
KEEP = object()
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slug(name: str, fallback: str = "media") -> str:
    stem = PurePosixPath(name or "").stem
    cleaned = _NAME_RE.sub("-", stem).strip("-._")[:64]
    return cleaned or fallback


def public_path(draft_dir: Path, value: str) -> Path:
    target, relative = files.resolve(draft_dir, value)
    if not files.is_media(relative):
        raise FilesError("not_media", "only the media files under public/ are served")
    return target


def _unique(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def store(draft_dir: Path, role: str, filename: str, data: bytes) -> Dict[str, Any]:
    if role not in ROLES:
        raise FilesError("invalid_request", f"role is one of {', '.join(ROLES)}")
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix not in MEDIA_EXTENSIONS:
        raise FilesError("not_media", f"a media file is one of {', '.join(sorted(MEDIA_EXTENSIONS))}")
    if len(data) == 0:
        raise FilesError("invalid_request", "the file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FilesError("too_large", f"the file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB")
    image = None
    if suffix in IMAGE_EXTENSIONS:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as failure:
            raise FilesError("not_media", f"the file is not an image PotionUI can read: {failure}") from failure
    converted = suffix in CONVERTED_EXTENSIONS
    public = draft_dir / PUBLIC_DIR
    folder = public if role == "cover" else public / "examples"
    folder.mkdir(parents=True, exist_ok=True)
    stored_suffix = ".webp" if converted else suffix
    if role == "cover":
        for stale in public.glob("cover.*"):
            stale.unlink()
        destination = public / f"cover{stored_suffix}"
    else:
        destination = _unique(folder, slug(filename), stored_suffix)
    if converted:
        downscale_and_save_webp(image, destination, LONG_EDGE[role])
    else:
        destination.write_bytes(data)
    relative = destination.relative_to(draft_dir).as_posix()
    return {"path": relative, "size": destination.stat().st_size, "role": role}


def _manifest_text(draft_dir: Path) -> str:
    return (draft_dir / files.MANIFEST).read_text(encoding="utf-8")


def _media_block(text: str) -> Dict[str, Any]:
    data = yaml.safe_load(text) if text.strip() else {}
    media = (data or {}).get("media") if isinstance(data, dict) else None
    return dict(media) if isinstance(media, dict) else {}


def _write_media(draft_dir: Path, media: Dict[str, Any]) -> Dict[str, Any]:
    text = _manifest_text(draft_dir)
    cleaned = {key: value for key, value in media.items() if value not in (None, [], "")}
    block = yaml.safe_dump({"media": cleaned}, sort_keys=False, allow_unicode=True).rstrip("\n") if cleaned else None
    (draft_dir / files.MANIFEST).write_text(files.replace_top_level_block(text, "media", block), encoding="utf-8")
    return cleaned


def set_cover(draft_dir: Path, path: str) -> Dict[str, Any]:
    media = _media_block(_manifest_text(draft_dir))
    media["cover"] = path
    return _write_media(draft_dir, media)


def _gallery_item(path: str, *, caption: Optional[str] = None, mode: Optional[str] = None,
                  prompt: Optional[str] = None, seed: Optional[int] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"src": path}
    if caption:
        item["caption"] = caption[:MAX_CAPTION_LENGTH]
    if prompt:
        item["prompt"] = prompt
    if seed is not None:
        item["seed"] = int(seed)
    if mode:
        item["mode"] = mode
    return item


def add_gallery_item(draft_dir: Path, path: str, *, caption: Optional[str] = None, mode: Optional[str] = None,
                     prompt: Optional[str] = None, seed: Optional[int] = None) -> Dict[str, Any]:
    media = _media_block(_manifest_text(draft_dir))
    gallery = [item for item in media.get("gallery", []) if isinstance(item, dict)]
    item = _gallery_item(path, caption=caption, mode=mode, prompt=prompt, seed=seed)
    media["gallery"] = [entry for entry in gallery if entry.get("src") != path] + [item]
    return _write_media(draft_dir, media)


def _check_declared(draft_dir: Path, path: str) -> None:
    if not public_path(draft_dir, path).is_file():
        raise FilesError("not_found", f"no media file {path}")


def declare(draft_dir: Path, *, cover: Any = KEEP, gallery: Any = KEEP) -> Dict[str, Any]:
    media = _media_block(_manifest_text(draft_dir))
    if cover is not KEEP:
        if cover is None:
            media.pop("cover", None)
        else:
            _check_declared(draft_dir, cover)
            media["cover"] = cover
    if gallery is not KEEP:
        items: List[Dict[str, Any]] = []
        for entry in gallery:
            src = entry["src"]
            _check_declared(draft_dir, src)
            if any(item["src"] == src for item in items):
                raise FilesError("invalid_request", f"{src} is listed twice in the gallery")
            items.append(_gallery_item(src, caption=entry.get("caption"), mode=entry.get("mode"), prompt=entry.get("prompt"), seed=entry.get("seed")))
        media["gallery"] = items
    return _write_media(draft_dir, media)


def remove(draft_dir: Path, path: str) -> Dict[str, Any]:
    target = public_path(draft_dir, path)
    if not target.is_file():
        raise FilesError("not_found", f"no media file {path}")
    target.unlink()
    parent = target.parent
    while parent != draft_dir.resolve() and parent.name != PUBLIC_DIR and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    media = _media_block(_manifest_text(draft_dir))
    changed = False
    if media.get("cover") == path:
        media.pop("cover")
        changed = True
    gallery = [item for item in media.get("gallery", []) if not (isinstance(item, dict) and item.get("src") == path)]
    if len(gallery) != len(media.get("gallery", [])):
        media["gallery"] = gallery
        changed = True
    if changed:
        media = _write_media(draft_dir, media)
    return media


def listing(draft_dir: Path) -> Dict[str, Any]:
    media = _media_block(_manifest_text(draft_dir))
    gallery = {item.get("src"): item for item in media.get("gallery", []) if isinstance(item, dict)}
    entries: List[Dict[str, Any]] = []
    public = draft_dir / PUBLIC_DIR
    if public.is_dir():
        for path in sorted(public.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(draft_dir).as_posix()
            suffix = path.suffix.lower()
            if suffix not in MEDIA_EXTENSIONS:
                continue
            roles = []
            if media.get("cover") == relative:
                roles.append("cover")
            if relative in gallery:
                roles.append("gallery")
            if relative.startswith(STYLES_PREFIX):
                roles.append("style")
            entries.append({
                "path": relative,
                "size": path.stat().st_size,
                "kind": "video" if suffix in VIDEO_EXTENSIONS else "image",
                "roles": roles,
                "gallery": gallery.get(relative),
                "over_budget": path.stat().st_size > (PRESET_COVER_VIDEO_MAX_BYTES if "cover" in roles and suffix in VIDEO_EXTENSIONS else PRESET_MEDIA_MAX_BYTES),
            })
    return {"cover": media.get("cover"), "gallery": [item for item in media.get("gallery", []) if isinstance(item, dict)], "files": entries}
