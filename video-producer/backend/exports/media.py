import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.parse import unquote

from .. import core_bridge
from ..core_bridge import MediaRefError, User
from ..routes_media import ORIGIN_KEYS
from .common import asset_of, clip_label, word_safe

MEDIA_MODES = ("path", "name")

_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class Found:
    name: str
    kind: Optional[str] = None
    value: Optional[str] = None


def basename(value: str) -> str:
    """The last segment of a path or URL, without its query or fragment."""
    return value.split("?", 1)[0].split("#", 1)[0].replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def url_basename(url: str) -> str:
    """The last segment of a URL, percent-decoded like decodeURIComponent, raw when it cannot be."""
    last = url.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1]
    if _BAD_ESCAPE.search(last):
        return last
    try:
        return unquote(last, errors="strict")
    except UnicodeDecodeError:
        return last


def core_ref(origin: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The core media reference of a document origin, or None when it is not one."""
    keys = ORIGIN_KEYS.get(origin.get("kind")) if isinstance(origin, Mapping) else None
    if keys is None or any(not origin.get(key) for key in keys):
        return None
    return {"kind": origin["kind"], **{core: origin[key] for key, core in keys.items()}}


class Resolver:
    """Resolves the media of a project as one user and finds their files on this server."""

    def __init__(self, user: User):
        self.user = user
        self._resolved: Dict[Tuple[Any, ...], Any] = {}

    def resolve(self, ref: Mapping[str, Any]) -> Dict[str, Any]:
        key = tuple(sorted(ref.items()))
        if key not in self._resolved:
            try:
                self._resolved[key] = core_bridge.resolve_media(self.user, ref)
            except MediaRefError as exc:
                self._resolved[key] = exc
        found = self._resolved[key]
        if isinstance(found, MediaRefError):
            raise found
        return found

    def path(self, kind: str, value: str) -> Optional[str]:
        return core_bridge.media_file_path(kind, value)

    def local(self, kind: str, value: str, folder: Path) -> Optional[Path]:
        return core_bridge.local_media_file(kind, value, folder)


def take_of(asset: Mapping[str, Any], takes: Iterable[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The finished take an asset shows: the take of its result, else the take of its history origin."""
    done = [take for take in takes if take.get("status") == "done" and take.get("file_path")]
    result_id = asset.get("resultId")
    if result_id:
        take = next((take for take in done if take["id"] == result_id), None)
        if take is not None:
            return take
    origin = asset.get("origin") or {}
    if origin.get("kind") != "history":
        return None
    for take in done:
        same_file = not take.get("file_id") or not origin.get("fileId") or take["file_id"] == origin["fileId"]
        if take.get("generation_id") == origin.get("generationId") and same_file:
            return take
    return None


def locate(asset: Mapping[str, Any], takes: Iterable[Mapping[str, Any]], resolver: Any) -> Optional[Found]:
    """Where an asset's file is: its take, the media its origin resolves to, or only the name in its URL."""
    take = take_of(asset, takes)
    if take is not None:
        return Found(basename(take["file_path"]), "history", take["file_path"])
    ref = core_ref(asset.get("origin") or {})
    if ref is not None:
        try:
            resolved = resolver.resolve(ref)
        except MediaRefError:
            resolved = None
        if resolved and resolved.get("value"):
            return Found(basename(resolved["value"]), ref["kind"], resolved["value"])
    if asset.get("src") and url_basename(asset["src"]):
        return Found(url_basename(asset["src"]))
    return None


def synthetic_name(doc: Mapping[str, Any], clip: Mapping[str, Any], asset: Mapping[str, Any], locale: str = "en") -> str:
    """The prototype's name for a generated shot whose file is unknown."""
    return f"{word_safe(clip_label(doc, clip, locale))}_{asset.get('quality')}_{asset.get('resultId')}.mov"


def file_of(
    doc: Mapping[str, Any], clip: Mapping[str, Any], takes: Iterable[Mapping[str, Any]], resolver: Any, locale: str = "en"
) -> Optional[Dict[str, str]]:
    """A shot's file: its real name and its absolute path on this server (the name when it has none), or None."""
    asset = asset_of(doc, clip.get("assetId"))
    if asset is None:
        return None
    found = locate(asset, takes, resolver)
    if found is not None:
        path = resolver.path(found.kind, found.value) if found.kind else None
        return {"name": found.name, "path": path or found.name}
    if asset.get("generated"):
        name = synthetic_name(doc, clip, asset, locale)
        return {"name": name, "path": name}
    return None


def files_of(
    doc: Mapping[str, Any], takes: Iterable[Mapping[str, Any]], resolver: Any, media: str = "path", locale: str = "en"
) -> Dict[Tuple[str, int], Optional[Dict[str, str]]]:
    """The file of every shot and audio item, keyed by ("clips" | "audio", position); with media=name each path is the file's name."""
    takes = list(takes)
    files: Dict[Tuple[str, int], Optional[Dict[str, str]]] = {}
    for key in ("clips", "audio"):
        for index, item in enumerate(doc.get(key) or []):
            entry = file_of(doc, item, takes, resolver, locale)
            files[(key, index)] = {"name": entry["name"], "path": entry["name"]} if entry and media == "name" else entry
    return files


def exportable(doc: Mapping[str, Any], takes: Iterable[Mapping[str, Any]], resolver: Any) -> bool:
    """True when at least one shot has a real file to assemble."""
    takes = list(takes)
    for clip in doc.get("clips") or []:
        asset = asset_of(doc, clip.get("assetId"))
        found = locate(asset, takes, resolver) if asset else None
        if found is not None and found.kind:
            return True
    return False


def local_inputs(
    doc: Mapping[str, Any], takes: Iterable[Mapping[str, Any]], resolver: Any, folder: Path
) -> Tuple[Dict[str, Optional[Dict[str, Any]]], Dict[str, str]]:
    """The local files the assembly reads: per shot ({name, path, still, sound}) and per audio item (path)."""
    takes = list(takes)
    cache: Dict[Tuple[str, str], Optional[Path]] = {}

    def local(asset: Optional[Mapping[str, Any]]) -> Optional[Path]:
        found = locate(asset, takes, resolver) if asset else None
        if found is None or not found.kind:
            return None
        key = (found.kind, found.value)
        if key not in cache:
            cache[key] = resolver.local(found.kind, found.value, folder)
        return cache[key]

    shots: Dict[str, Optional[Dict[str, Any]]] = {}
    for clip in doc.get("clips") or []:
        asset = asset_of(doc, clip.get("assetId"))
        path = local(asset)
        shots[clip["id"]] = None if path is None else {
            "name": path.name,
            "path": str(path),
            "still": asset.get("kind") == "image",
            "sound": asset.get("kind") == "audio",
        }
    sounds: Dict[str, str] = {}
    for item in doc.get("audio") or []:
        path = local(asset_of(doc, item.get("assetId")))
        if path is not None:
            sounds[item["id"]] = str(path)
    return shots, sounds
