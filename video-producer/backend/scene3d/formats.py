import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .. import core_bridge
from ..core_bridge import MediaRefError

SPLAT_FORMATS = ("ply", "spz", "splat")

GLB = "glb"

KINDS = {"splat": SPLAT_FORMATS, "glb": (GLB,)}

MEDIA_TYPES = {"ply": "application/octet-stream", "spz": "application/octet-stream", "splat": "application/octet-stream", GLB: "model/gltf-binary"}

SPLAT_RECORD = 32

SPLAT_SAMPLE = 1024

SPLAT_FLOATS = struct.Struct("<6f")

GLB_MAGIC = b"glTF"

GLB_JSON = 0x4E4F534A

MOVING_PATHS = ("translation", "rotation", "scale")


class FormatError(ValueError):
    """A file that is not the scene format its name says."""


@dataclass(frozen=True)
class Probe:
    format: str
    count: Optional[int] = None
    view: Optional[Dict[str, float]] = None
    cameras: Optional[List[Dict[str, Any]]] = field(default=None)


def format_of(name: str) -> Optional[str]:
    """The scene format a file name says, from its extension, or None."""
    suffix = Path(str(name or "")).suffix.lower().lstrip(".")
    return suffix if suffix in (*SPLAT_FORMATS, GLB) else None


def _view(view: Optional[Mapping[str, Any]]) -> Optional[Dict[str, float]]:
    if not view:
        return None
    return {"fov": float(view["fov_y"]), "aspect": float(view["aspect"]), "depth": float(view["depth"])}


def _splat_records(path: Path) -> None:
    with path.open("rb") as handle:
        head = handle.read(SPLAT_RECORD * SPLAT_SAMPLE)
    for offset in range(0, len(head) - SPLAT_RECORD + 1, SPLAT_RECORD):
        if not all(math.isfinite(value) for value in SPLAT_FLOATS.unpack_from(head, offset)):
            raise FormatError("The .splat file does not hold gaussians: a position or a scale of its first gaussians is not a finite number.")


def probe_splat(fmt: str, path: Path) -> Probe:
    """The gaussian count and source view the core reads in a .ply, .spz or .splat file named with its format; for a .splat, also finite positions and scales in its first gaussians; FormatError otherwise."""
    try:
        info = core_bridge.probe_splat(path)
    except MediaRefError as exc:
        raise FormatError(str(exc)) from None
    if info.get("format") != fmt:
        raise FormatError(f"The file is not a .{fmt} splat.")
    if fmt == "splat":
        _splat_records(path)
    return Probe(format=fmt, count=info.get("count"), view=_view(info.get("view")))


def glb_json(path: Path) -> Dict[str, Any]:
    """The JSON chunk of a binary glTF 2.0 file; FormatError otherwise."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) < 20 or header[:4] != GLB_MAGIC:
            raise FormatError("The file is not a binary glTF (.glb) file.")
        version, length, chunk_length, chunk_type = struct.unpack_from("<IIII", header, 4)
        if version != 2:
            raise FormatError(f"The glTF file is version {version}; only version 2 is read.")
        if length != size or chunk_type != GLB_JSON or chunk_length > size - 20:
            raise FormatError("The glTF file is cut short or has no JSON chunk.")
        raw = handle.read(chunk_length)
    try:
        data = json.loads(raw.decode("utf-8").rstrip(" \x00"))
    except (UnicodeDecodeError, ValueError):
        raise FormatError("The JSON chunk of the glTF file cannot be read.") from None
    if not isinstance(data, dict):
        raise FormatError("The JSON chunk of the glTF file is not an object.")
    return data


def _list(data: Dict[str, Any], key: str) -> List[Any]:
    value = data.get(key)
    return value if isinstance(value, list) else []


def _parents(nodes: List[Any]) -> Dict[int, int]:
    parents: Dict[int, int] = {}
    for parent, node in enumerate(nodes):
        for child in _list(node, "children") if isinstance(node, dict) else []:
            if isinstance(child, int):
                parents.setdefault(child, parent)
    return parents


def _ancestors(parents: Dict[int, int], index: int) -> List[int]:
    chain, seen = [index], {index}
    while chain[-1] in parents and parents[chain[-1]] not in seen:
        seen.add(parents[chain[-1]])
        chain.append(parents[chain[-1]])
    return chain


def _channel_end(animation: Dict[str, Any], channel: Dict[str, Any], accessors: List[Any]) -> Optional[float]:
    samplers = _list(animation, "samplers")
    sampler = channel.get("sampler")
    if not isinstance(sampler, int) or not 0 <= sampler < len(samplers) or not isinstance(samplers[sampler], dict):
        return None
    accessor = samplers[sampler].get("input")
    if not isinstance(accessor, int) or not 0 <= accessor < len(accessors) or not isinstance(accessors[accessor], dict):
        return None
    maximum = accessors[accessor].get("max")
    if not isinstance(maximum, list) or not maximum or not isinstance(maximum[0], (int, float)):
        return None
    return float(maximum[0])


def glb_cameras(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The cameras of a glTF scene, each with its name, whether an animation moves it or a parent, and how long that animation lasts."""
    nodes, cameras, accessors = _list(data, "nodes"), _list(data, "cameras"), _list(data, "accessors")
    moving: Dict[int, List[Optional[float]]] = {}
    for animation in _list(data, "animations"):
        if not isinstance(animation, dict):
            continue
        for channel in _list(animation, "channels"):
            target = channel.get("target") if isinstance(channel, dict) else None
            if isinstance(target, dict) and isinstance(target.get("node"), int) and target.get("path") in MOVING_PATHS:
                moving.setdefault(target["node"], []).append(_channel_end(animation, channel, accessors))
    parents = _parents(nodes)
    found = []
    for index, node in enumerate(nodes):
        camera = node.get("camera") if isinstance(node, dict) else None
        if not isinstance(camera, int):
            continue
        spec = cameras[camera] if 0 <= camera < len(cameras) and isinstance(cameras[camera], dict) else {}
        name = node.get("name") or spec.get("name") or f"camera-{index}"
        ends = [end for ancestor in _ancestors(parents, index) for end in moving.get(ancestor, [])]
        known = [end for end in ends if end is not None]
        found.append({"name": str(name), "animated": bool(ends), "duration": max(known) if known else None})
    return found


def probe_glb(path: Path) -> Probe:
    """The cameras of a binary glTF 2.0 file; FormatError otherwise."""
    return Probe(format=GLB, cameras=glb_cameras(glb_json(path)))


def probe(fmt: str, path: Path) -> Probe:
    """What a scene file of a format holds; FormatError when it is not that format."""
    try:
        return probe_glb(path) if fmt == GLB else probe_splat(fmt, path)
    except OSError as exc:
        raise FormatError(f"The file cannot be read: {exc.strerror or exc}") from None
