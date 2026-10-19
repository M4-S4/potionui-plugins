import gzip
import json
import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SPLAT_FORMATS = ("ply", "spz", "splat")

GLB = "glb"

KINDS = {"splat": SPLAT_FORMATS, "glb": (GLB,)}

MEDIA_TYPES = {"ply": "application/octet-stream", "spz": "application/octet-stream", "splat": "application/octet-stream", GLB: "model/gltf-binary"}

PLY_HEADER_LIMIT = 64 * 1024

PLY_FORMAT = "format binary_little_endian 1.0"

GAUSSIAN_PROPERTIES = (
    "x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
)

PLY_SIZES = {
    "char": 1, "uchar": 1, "int8": 1, "uint8": 1,
    "short": 2, "ushort": 2, "int16": 2, "uint16": 2,
    "int": 4, "uint": 4, "float": 4, "int32": 4, "uint32": 4, "float32": 4,
    "double": 8, "float64": 8,
}

VIEW_COMMENT = "potionui_view"

VIEW_KEYS = {"fov_y": "fov", "aspect": "aspect", "depth": "depth"}

SPZ_MAGIC = b"NGSP"

GZIP_MAGIC = b"\x1f\x8b"

SPLAT_RECORD = 32

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


def _positive(text: str) -> Optional[float]:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def view_of(comment: str) -> Optional[Dict[str, float]]:
    """The source view a potionui_view header comment describes, or None when it lacks the field of view, the aspect or the depth."""
    words = comment.split()
    if not words or words[0] != VIEW_COMMENT:
        return None
    values = dict(word.split("=", 1) for word in words[1:] if "=" in word)
    view = {name: _positive(values.get(key, "")) for key, name in VIEW_KEYS.items()}
    return None if any(value is None for value in view.values()) else view


def _ply_header(path: Path) -> Tuple[List[str], int]:
    with path.open("rb") as handle:
        head = handle.read(PLY_HEADER_LIMIT)
    end = head.find(b"end_header")
    if not head.startswith(b"ply") or end < 0:
        raise FormatError("The file is not a PLY file.")
    stop = head.find(b"\n", end)
    if stop < 0:
        raise FormatError("The PLY header has no end.")
    lines = head[:end].decode("ascii", "replace").splitlines()
    return [line.strip() for line in lines], stop + 1


def probe_ply(path: Path) -> Probe:
    """The gaussian count and source view of a binary little-endian 3DGS PLY file; FormatError otherwise."""
    lines, header_size = _ply_header(path)
    if PLY_FORMAT not in lines:
        raise FormatError("The PLY file must be binary little-endian.")
    elements: List[Tuple[str, int, List[Tuple[str, str]]]] = []
    view = None
    for line in lines[1:]:
        words = line.split()
        if not words:
            continue
        if words[0] == "comment" and len(words) > 1:
            view = view_of(line.split(None, 1)[1]) or view
        elif words[0] == "element" and len(words) == 3 and words[2].isdigit():
            elements.append((words[1], int(words[2]), []))
        elif words[0] == "property" and elements:
            if words[1] == "list" or len(words) != 3 or words[1] not in PLY_SIZES:
                raise FormatError("The PLY file has a property a gaussian splat does not use.")
            elements[-1][2].append((words[1], words[2]))
    if not elements or elements[0][0] != "vertex":
        raise FormatError("The PLY file has no gaussians.")
    _, count, properties = elements[0]
    names = {name for _, name in properties}
    missing = [name for name in GAUSSIAN_PROPERTIES if name not in names]
    if missing:
        raise FormatError(f"The PLY file is not a gaussian splat: it has no {', '.join(missing)}.")
    if count <= 0:
        raise FormatError("The PLY file has no gaussians.")
    stride = sum(PLY_SIZES[kind] for kind, _ in properties)
    if path.stat().st_size < header_size + count * stride:
        raise FormatError("The PLY file is shorter than its header says.")
    return Probe(format="ply", count=count, view=view)


def probe_spz(path: Path) -> Probe:
    """The gaussian count of a gzip-compressed SPZ file; FormatError otherwise."""
    with path.open("rb") as handle:
        if handle.read(2) != GZIP_MAGIC:
            raise FormatError("The SPZ file is not gzip-compressed.")
    try:
        with gzip.open(path, "rb") as handle:
            header = handle.read(16)
    except (OSError, EOFError, zlib.error):
        raise FormatError("The SPZ file cannot be decompressed.") from None
    if len(header) < 16 or header[:4] != SPZ_MAGIC:
        raise FormatError("The SPZ file does not start with the NGSP magic.")
    count = struct.unpack_from("<I", header, 8)[0]
    if count <= 0:
        raise FormatError("The SPZ file has no gaussians.")
    return Probe(format="spz", count=count)


def probe_splat(path: Path) -> Probe:
    """The gaussian count of an antimatter15 .splat file, 32 bytes per gaussian; FormatError otherwise."""
    size = path.stat().st_size
    if size <= 0 or size % SPLAT_RECORD:
        raise FormatError(f"A .splat file holds {SPLAT_RECORD} bytes per gaussian; this one has {size} bytes.")
    return Probe(format="splat", count=size // SPLAT_RECORD)


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


PROBES = {"ply": probe_ply, "spz": probe_spz, "splat": probe_splat, GLB: probe_glb}


def probe(fmt: str, path: Path) -> Probe:
    """What a scene file of a format holds; FormatError when it is not that format."""
    try:
        return PROBES[fmt](path)
    except OSError as exc:
        raise FormatError(f"The file cannot be read: {exc.strerror or exc}") from None
