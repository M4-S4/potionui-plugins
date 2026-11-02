import re
from typing import Any, Dict, List, Mapping, Optional

from .common import js_round

_LINE_END = re.compile(r"\r\n|\r|\n")

_BLANK = re.compile(r"[ \t]*")


def fold(text: Any) -> str:
    """The text of a cue without blank lines, which would end the cue."""
    return "\n".join(line for line in _LINE_END.split(str(text)) if not _BLANK.fullmatch(line))


def cues(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The subtitles of the sequence: its titles, by start time."""
    found: List[Dict[str, Any]] = []
    for title in doc.get("titles") or []:
        text = "\n".join(part for part in (title.get("text"), title.get("sub")) if part)
        found.append({"start": title["start"], "end": title["start"] + title["dur"], "text": text})
    return sorted(found, key=lambda cue: cue["start"])


def timestamp(seconds: Any) -> str:
    """HH:MM:SS,mmm."""
    ms = js_round(seconds * 1000)
    return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"


def render(doc: Mapping[str, Any], files: Optional[Mapping[Any, Optional[Dict[str, str]]]] = None, locale: str = "en") -> str:
    """The subtitles of the sequence as SubRip; the files and the locale, which the other formats use, change nothing."""
    return "\n".join(
        f"{index + 1}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n{fold(cue['text'])}\n"
        for index, cue in enumerate(cues(doc))
    )
