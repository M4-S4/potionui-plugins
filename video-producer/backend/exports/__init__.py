import re
import unicodedata
from typing import Any, Callable, Dict, Mapping, NamedTuple, Optional, Tuple
from urllib.parse import quote

from . import edl, fcpxml, otio, srt

FALLBACK_NAME = "video-producer"

_UNSAFE = re.compile(r"[^A-Za-z0-9.-]+")
_SPACES = re.compile(r"[\s\ufeff]+")
_RESERVED = re.compile(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?")
_LETTERS = str.maketrans({"œ": "oe", "Œ": "Oe", "æ": "ae", "Æ": "Ae", "ß": "ss", "ẞ": "SS", "ø": "o", "Ø": "O"})


class Exchange(NamedTuple):
    render: Callable[..., str]
    content_type: str
    extension: str


EXCHANGE: Dict[str, Exchange] = {
    "fcpxml": Exchange(fcpxml.render, "application/xml", "fcpxml"),
    "otio": Exchange(otio.render, "application/json", "otio"),
    "edl": Exchange(edl.render, "text/plain; charset=utf-8", "edl"),
    "srt": Exchange(srt.render, "application/x-subrip", "srt"),
}


def render(fmt: str, doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """One exchange format of a document."""
    return EXCHANGE[fmt].render(doc, files, locale=locale)


def unicode_name(name: str) -> str:
    """A project name made a file name: spaces turned into underscores."""
    return _SPACES.sub("_", str(name or "").strip()) or FALLBACK_NAME


def slug(name: str) -> str:
    """An ASCII file name for a project name, œ, æ, ß and ø spelled out in letters, a name Windows reserves (NUL, COM1, LPT1 ...) before its first dot made safe by a leading underscore. The page spells it the same way."""
    plain = unicodedata.normalize("NFKD", unicode_name(name).translate(_LETTERS)).encode("ascii", "ignore").decode("ascii")
    safe = _UNSAFE.sub("_", plain).strip("._") or FALLBACK_NAME
    return f"_{safe}" if _RESERVED.fullmatch(safe) else safe


def content_disposition(name: str, extension: str) -> str:
    """An attachment header with the ASCII slug and the UTF-8 name of the file."""
    ascii_name, utf8_name = f"{slug(name)}.{extension}", f"{unicode_name(name)}.{extension}"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(utf8_name, safe='')}"
