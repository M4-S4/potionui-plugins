import re
from typing import Any, Dict, Mapping, Optional, Tuple

from .. import formats
from ..dissolve import cuts, moved, placement
from .common import Timebase, clip_label

_LINE_BREAK = re.compile(r"[\r\n]")


def one_line(text: Any) -> str:
    """A text without the line breaks that would start a new line of the list."""
    return _LINE_BREAK.sub("", str(text))


def render(doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """The sequence as a CMX 3600 edit decision list, non-drop frame, CRLF line ends; a slowed shot reads the seconds of source its speed covers and carries an M2 line with the rate its source plays at."""
    time = Timebase(doc)
    lines = [f"TITLE: {one_line(doc['name']).upper()}", "FCM: NON-DROP FRAME", ""]
    clips = doc["clips"]
    edits = cuts(clips, time.frames)
    joins = [*(cut.overlap if cut is not None else 0 for cut in edits), 0]
    places = placement(clips) if any(joins) else [None] * len(clips)
    for index, clip in enumerate(clips):
        number = str(index + 1).rjust(3, "0")
        entry = files.get(("clips", index))
        reel = f"VP{number}" if entry else "BL"
        source_in, record_in = clip["srcIn"], clip["start"]
        speed = formats.speed_of(clip)
        shifted = moved(clip, places[index])
        if shifted:
            record_in = places[index].start
        if joins[index + 1] > 0:
            record_out = clips[index + 1]["start"]
            source_out = source_in + (record_out - record_in) * speed
        elif shifted:
            record_out = places[index].end
            source_out = source_in + (record_out - record_in) * speed
        elif places[index] is not None:
            record_out = places[index].end
            source_out = source_in + clip["dur"] * speed
        else:
            record_out = record_in + clip["dur"]
            source_out = source_in + clip["dur"] * speed
        if joins[index] > 0:
            before = clips[index - 1]
            held = before["srcIn"] + (record_in - before["start"]) * formats.speed_of(before)
            before_reel = f"VP{str(index).rjust(3, '0')}" if files.get(("clips", index - 1)) else "BL"
            lines.append(f"{number}  {before_reel.ljust(8)} V     C        {time.timecode(held)} {time.timecode(held)} {time.timecode(record_in)} {time.timecode(record_in)}")
            cut = f"D    {str(joins[index]).rjust(3, '0')}"
        else:
            cut = "C       "
        lines.append(
            f"{number}  {reel.ljust(8)} V     {cut} {time.timecode(source_in)} {time.timecode(source_out)} "
            f"{time.timecode(record_in)} {time.timecode(record_out)}"
        )
        if speed != 1:
            lines.append(f"M2   {reel.ljust(8)}       {float(time.fps) * speed:05.1f}                {time.timecode(source_in)}")
        if joins[index] > 0:
            lines.append(f"* FROM CLIP NAME: {one_line(clip_label(doc, clips[index - 1], locale))}")
            lines.append(f"* TO CLIP NAME: {one_line(clip_label(doc, clip, locale))}")
        else:
            lines.append(f"* FROM CLIP NAME: {one_line(clip_label(doc, clip, locale))}")
        if entry:
            lines.append(f"* SOURCE FILE: {one_line(entry['path'])}")
        lines.append("")
    return "\r\n".join(lines)
