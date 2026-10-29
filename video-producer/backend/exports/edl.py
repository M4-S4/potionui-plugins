import re
from typing import Any, Dict, Mapping, Optional, Tuple

from .. import formats
from .common import Timebase, clip_label

_LINE_BREAK = re.compile(r"[\r\n]")


def one_line(text: Any) -> str:
    """A text without the line breaks that would start a new line of the list."""
    return _LINE_BREAK.sub("", str(text))


def render(doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """The sequence as a CMX 3600 edit decision list, non-drop frame, CRLF line ends; a slowed shot reads the seconds of source its speed covers and carries an M2 line with the rate its source plays at."""
    time = Timebase(doc)
    lines = [f"TITLE: {one_line(doc['name']).upper()}", "FCM: NON-DROP FRAME", ""]
    for index, clip in enumerate(doc["clips"]):
        number = str(index + 1).rjust(3, "0")
        entry = files.get(("clips", index))
        reel = f"VP{number}" if entry else "BL"
        source_in, record_in = clip["srcIn"], clip["start"]
        speed = formats.speed_of(clip)
        lines.append(
            f"{number}  {reel.ljust(8)} V     C        {time.timecode(source_in)} {time.timecode(source_in + clip['dur'] * speed)} "
            f"{time.timecode(record_in)} {time.timecode(record_in + clip['dur'])}"
        )
        if speed != 1:
            lines.append(f"M2   {reel.ljust(8)}       {float(time.fps) * speed:05.1f}                {time.timecode(source_in)}")
        lines.append(f"* FROM CLIP NAME: {one_line(clip_label(doc, clip, locale))}")
        if entry:
            lines.append(f"* SOURCE FILE: {one_line(entry['path'])}")
        lines.append("")
    return "\r\n".join(lines)
