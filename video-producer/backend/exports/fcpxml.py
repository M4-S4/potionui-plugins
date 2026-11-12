import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote

from .. import formats
from ..dissolve import cuts
from .common import Timebase, asset_of, clip_label, js_number, seq_duration

NAMED_RATES = ("24", "25", "30", "50", "60")

DISSOLVE_NAME = "Cross Dissolve"

DISSOLVE_EFFECT = "FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265"

_URI_SAFE = ";,/?:@&=+$!*'()#"

_PATH_SAFE = ";,/:@&=+$!*'()"

_XML_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def esc(text: Any) -> str:
    """The page's XML escaping of an attribute value, without the characters XML 1.0 cannot hold."""
    plain = _XML_FORBIDDEN.sub("", str(text))
    return plain.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def encode_uri(text: str) -> str:
    """encodeURI: percent-encode everything but the URI's reserved and unreserved characters."""
    return quote(text, safe=_URI_SAFE)


def media_url(entry: Mapping[str, str]) -> str:
    """The file:// URL of a shot's file: its absolute path, a network share as its host, or its name under /Video Producer/ like the page."""
    location = str(entry["path"]).replace("\\", "/")
    if location.startswith("//") and not location.startswith("///"):
        return esc(f"file:{quote(location, safe=_PATH_SAFE)}")
    if not location.startswith("/") and location[1:3] == ":/":
        location = f"/{location}"
    if location.startswith("/"):
        return esc(f"file://{quote(location, safe=_PATH_SAFE)}")
    return esc(f"file://{encode_uri(f'/Video Producer/{location}')}")


def frame(doc: Mapping[str, Any]) -> Tuple[int, int]:
    """The frame of the sequence: the project's format inside the 16:9 box of its resolution, 16:9 past 1:4 or 4:1, as the video export frames it."""
    ratio = formats.ratio_of(doc.get("aspect"))
    if ratio is None or not 1 / 4 <= ratio <= 4:
        ratio = formats.BOX
    return formats.delivery_size(ratio, doc.get("resolution"))


def format_name(doc: Mapping[str, Any], fps: str) -> str:
    """The name attribute of the sequence's format, kept for a 16:9 frame at a named frame rate and left out otherwise, as for the other formats, which no named format describes."""
    if frame(doc) != formats.delivery_size(formats.BOX, doc.get("resolution")) or fps not in NAMED_RATES:
        return ""
    return f' name="FFVideoFormat{doc["resolution"]}{fps}"'


def render(doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """The sequence as FCPXML 1.10; a slowed shot carries a linear time map from its timeline time to the seconds of source its speed covers."""
    time = Timebase(doc)
    media = [(index, clip) for index, clip in enumerate(doc["clips"]) if files.get(("clips", index))]
    width, height = frame(doc)
    refs = {index: number + 2 for number, (index, _) in enumerate(media)}
    assets = []
    for index, clip in media:
        source = asset_of(doc, clip.get("assetId")) or {}
        length = source.get("srcDur") if source.get("srcDur") is not None else clip["srcIn"] + clip["dur"] * formats.speed_of(clip)
        assets.append(
            f'\t\t<asset id="r{refs[index]}" name="{esc(clip_label(doc, clip, locale))}" start="0s" '
            f'duration="{time.rational(length)}" hasVideo="1" format="r1">'
            f'<media-rep kind="original-media" src="{media_url(files[("clips", index)])}"/></asset>'
        )
    edits = cuts(doc["clips"], time.frames)
    effect = len(media) + 2
    if any(cut is not None and cut.overlap for cut in edits):
        assets.append(f'\t\t<effect id="r{effect}" name="{DISSOLVE_NAME}" uid="{DISSOLVE_EFFECT}"/>')
    spine = []
    for index, clip in enumerate(doc["clips"]):
        name = esc(clip_label(doc, clip, locale))
        speed = formats.speed_of(clip)
        cut = edits[index]
        length = time.span(clip["start"], clip["dur"]) if cut is None else cut.end - cut.start
        offset = time.rational(clip["start"]) if cut is None else time.count(cut.start)
        source = clip["srcIn"] if cut is None or not cut.head else clip["srcIn"] + cut.head / time.fps * speed
        if cut is not None and cut.overlap:
            spine.append(
                f'\t\t\t\t\t\t<transition name="{DISSOLVE_NAME}" offset="{time.count(cut.start - cut.head)}" duration="{time.count(cut.overlap)}">'
                f'<filter-video ref="r{effect}" name="{DISSOLVE_NAME}"/></transition>'
            )
        if index in refs and speed != 1:
            spine.append(
                f'\t\t\t\t\t\t<asset-clip ref="r{refs[index]}" name="{name}" offset="{offset}" '
                f'start="{time.rational(source)}" duration="{time.count(length)}">'
                f'<timeMap><timept time="{time.rational(source)}" value="{time.rational(source)}" interp="linear"/>'
                f'<timept time="{time.count(time.frames(source) + length)}" value="{time.rational(source + length / time.fps * speed)}" interp="linear"/>'
                "</timeMap></asset-clip>"
            )
        elif index in refs:
            spine.append(
                f'\t\t\t\t\t\t<asset-clip ref="r{refs[index]}" name="{name}" offset="{offset}" '
                f'start="{time.rational(source)}" duration="{time.count(length)}"/>'
            )
        else:
            spine.append(
                f'\t\t\t\t\t\t<gap name="{name}" offset="{offset}" start="0s" '
                f'duration="{time.count(length)}"/>'
            )
    fps = js_number(time.fps)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        '<fcpxml version="1.10">\n'
        "\t<resources>\n"
        f'\t\t<format id="r1"{format_name(doc, fps)} frameDuration="1/{fps}s" '
        f'width="{width}" height="{height}"/>\n'
        f"{chr(10).join(assets)}\n"
        "\t</resources>\n"
        "\t<library>\n"
        '\t\t<event name="Video Producer">\n'
        f'\t\t\t<project name="{esc(doc["name"])}">\n'
        f'\t\t\t\t<sequence format="r1" duration="{time.rational(seq_duration(doc))}" tcStart="0s">\n'
        "\t\t\t\t\t<spine>\n"
        f"{chr(10).join(spine)}\n"
        "\t\t\t\t\t</spine>\n"
        "\t\t\t\t</sequence>\n"
        "\t\t\t</project>\n"
        "\t\t</event>\n"
        "\t</library>\n"
        "</fcpxml>\n"
    )
