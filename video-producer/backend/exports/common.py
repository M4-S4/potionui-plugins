import json
import math
import re
from typing import Any, Dict, Mapping, Optional

LOCALES = ("en", "fr")

DEFAULT_CLIP = {"en": "Shot", "fr": "Plan"}

UNDEFINED = object()

MS_PER_SECOND = 1000.0

TIMED = ("clips", "audio", "titles")

_NOT_ALNUM = re.compile(r"[\W_]+")


def locale_of(locale: Optional[str]) -> str:
    """A supported locale, English otherwise."""
    return locale if locale in LOCALES else "en"


def js_round(value: Any) -> int:
    """Math.round: the nearest integer, halves toward +infinity."""
    floor = math.floor(value)
    return int(floor + 1 if value - floor >= 0.5 else floor)


def js_number(value: Any) -> str:
    """A number written the way JavaScript's String(number) writes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    mantissa, _, exponent = repr(abs(value)).partition("e")
    whole, _, fraction = mantissa.partition(".")
    raw = whole + fraction
    point = len(whole) - (len(raw) - len(raw.lstrip("0"))) + int(exponent or 0)
    digits = raw.strip("0")
    count = len(digits)
    if count <= point <= 21:
        text = digits + "0" * (point - count)
    elif 0 < point <= 21:
        text = f"{digits[:point]}.{digits[point:]}"
    elif -6 < point <= 0:
        text = f"0.{'0' * -point}{digits}"
    else:
        power = point - 1
        tail = f".{digits[1:]}" if count > 1 else ""
        text = f"{digits[0]}{tail}e{'+' if power >= 0 else '-'}{abs(power)}"
    return sign + text


def js_json(value: Any, indent: str = "  ", level: int = 0) -> str:
    """JSON.stringify(value, null, 2), UNDEFINED members left out."""
    if value is None:
        return "null"
    if isinstance(value, float) and not math.isfinite(value):
        return "null"
    if isinstance(value, (bool, int, float)):
        return js_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    inner, outer = indent * (level + 1), indent * level
    if isinstance(value, Mapping):
        members = [
            f"{inner}{json.dumps(str(key), ensure_ascii=False)}: {js_json(item, indent, level + 1)}"
            for key, item in value.items()
            if item is not UNDEFINED
        ]
        return "{\n" + ",\n".join(members) + f"\n{outer}}}" if members else "{}"
    items = [f"{inner}{'null' if item is UNDEFINED else js_json(item, indent, level + 1)}" for item in value]
    return "[\n" + ",\n".join(items) + f"\n{outer}]" if items else "[]"


def asset_of(doc: Mapping[str, Any], asset_id: Any) -> Optional[Dict[str, Any]]:
    """The asset with this id, or None."""
    if not asset_id:
        return None
    return next((asset for asset in doc.get("assets") or [] if asset.get("id") == asset_id), None)


def clip_label(doc: Mapping[str, Any], clip: Mapping[str, Any], locale: str = "en") -> str:
    """The label the page shows for a shot."""
    asset = asset_of(doc, clip.get("assetId"))
    return clip.get("label") or (asset or {}).get("name") or DEFAULT_CLIP[locale_of(locale)]


def word_safe(text: str) -> str:
    """Every run of characters other than letters and digits turned into one underscore."""
    return _NOT_ALNUM.sub("_", text)


def seq_duration(doc: Mapping[str, Any]) -> Any:
    """The running time of the sequence, at least 1 s."""
    ends = [item["start"] + item["dur"] for key in ("clips", "audio", "titles") for item in doc.get(key) or []]
    return max([1, *ends])


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def timing_error(doc: Mapping[str, Any], frames: bool = True) -> Optional[str]:
    """Why the times of a document cannot be written, or None: a frame rate that is not a positive number, a time too large to count."""
    fps = _finite(doc.get("fps"))
    if frames and (fps is None or fps <= 0):
        return "$.fps: must be a positive number of frames per second"
    scale = max(fps, MS_PER_SECOND) if frames else MS_PER_SECOND
    for key in TIMED:
        for index, item in enumerate(doc.get(key) or []):
            start, dur, source_in = (_finite(item.get(name) or 0) for name in ("start", "dur", "srcIn"))
            if start is None or dur is None or source_in is None:
                return f"$.{key}[{index}]: its times must be finite numbers"
            if not all(math.isfinite(value * scale) for value in (start, dur, source_in, start + dur, source_in + dur)):
                return f"$.{key}[{index}]: its times are too large to be counted"
    for index, asset in enumerate(doc.get("assets") or []):
        length = _finite(asset.get("srcDur") or 0)
        if length is None or not math.isfinite(length * scale):
            return f"$.assets[{index}].srcDur: too large to be counted"
    return None


def fps_of(doc: Mapping[str, Any]) -> Any:
    """The frame rate of the document, an integer when it is whole."""
    fps = doc.get("fps")
    return int(fps) if isinstance(fps, float) and fps.is_integer() else fps


class Timebase:
    """Frame counts, rational times and timecodes at the document's frame rate."""

    def __init__(self, doc: Mapping[str, Any]):
        self.fps = fps_of(doc)

    def frames(self, seconds: Any) -> int:
        return js_round(seconds * self.fps)

    def rational(self, seconds: Any) -> str:
        return self.count(self.frames(seconds))

    def count(self, frames: int) -> str:
        return f"{frames}/{js_number(self.fps)}s"

    def span(self, start: Any, seconds: Any) -> int:
        """The frames an item from start for seconds covers on the timeline: from the frame its start falls on to the frame its end falls on, so that items that follow each other stay frame for frame in step, and one frame at least."""
        return max(1, self.frames(start + seconds) - self.frames(start))

    def timecode(self, seconds: Any) -> str:
        count = self.frames(seconds)
        whole = math.floor(count / self.fps)
        rest = math.fmod(count, self.fps) if isinstance(self.fps, float) else count % self.fps
        parts = (math.floor(whole / 3600), math.floor((whole % 3600) / 60), whole % 60, rest)
        return ":".join(js_number(part).rjust(2, "0") for part in parts)
