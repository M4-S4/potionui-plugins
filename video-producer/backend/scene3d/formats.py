import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .. import core_bridge
from ..core_bridge import MediaRefError

SPLAT_FORMATS = ("ply", "spz", "splat")

MEDIA_TYPES = {"ply": "application/octet-stream", "spz": "application/octet-stream", "splat": "application/octet-stream"}

SPLAT_RECORD = 32

SPLAT_SAMPLE = 1024

SPLAT_FLOATS = struct.Struct("<6f")


class FormatError(ValueError):
    """A file that is not the scene format its name says."""


@dataclass(frozen=True)
class Probe:
    format: str
    count: Optional[int] = None
    view: Optional[Dict[str, float]] = None


def format_of(name: str) -> Optional[str]:
    """The scene format a file name says, from its extension, or None."""
    suffix = Path(str(name or "")).suffix.lower().lstrip(".")
    return suffix if suffix in SPLAT_FORMATS else None


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


def probe(fmt: str, path: Path) -> Probe:
    """What a scene file of a format holds; FormatError when it is not that format."""
    try:
        return probe_splat(fmt, path)
    except FormatError:
        raise
    except OSError as exc:
        raise FormatError(f"The file cannot be read: {exc.strerror or exc}") from None
    except (RecursionError, ValueError):
        raise FormatError(f"The file is not a .{fmt} file that can be read.") from None
