import re
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import quote

from .common import Timebase, asset_of, clip_label, js_number, seq_duration

SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "4K": (3840, 2160)}

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


def render(doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """The sequence as FCPXML 1.10."""
    time = Timebase(doc)
    media = [(index, clip) for index, clip in enumerate(doc["clips"]) if files.get(("clips", index))]
    width, height = SIZES.get(doc["resolution"], (1920, 1080))
    refs = {index: number + 2 for number, (index, _) in enumerate(media)}
    assets = []
    for index, clip in media:
        source = asset_of(doc, clip.get("assetId")) or {}
        length = source.get("srcDur") if source.get("srcDur") is not None else clip["srcIn"] + clip["dur"]
        assets.append(
            f'\t\t<asset id="r{refs[index]}" name="{esc(clip_label(doc, clip, locale))}" start="0s" '
            f'duration="{time.rational(length)}" hasVideo="1" format="r1">'
            f'<media-rep kind="original-media" src="{media_url(files[("clips", index)])}"/></asset>'
        )
    spine = []
    for index, clip in enumerate(doc["clips"]):
        name = esc(clip_label(doc, clip, locale))
        if index in refs:
            spine.append(
                f'\t\t\t\t\t\t<asset-clip ref="r{refs[index]}" name="{name}" offset="{time.rational(clip["start"])}" '
                f'start="{time.rational(clip["srcIn"])}" duration="{time.rational(clip["dur"])}"/>'
            )
        else:
            spine.append(
                f'\t\t\t\t\t\t<gap name="{name}" offset="{time.rational(clip["start"])}" start="0s" '
                f'duration="{time.rational(clip["dur"])}"/>'
            )
    fps = js_number(time.fps)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        '<fcpxml version="1.10">\n'
        "\t<resources>\n"
        f'\t\t<format id="r1" name="FFVideoFormat{doc["resolution"]}{fps}" frameDuration="1/{fps}s" '
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
