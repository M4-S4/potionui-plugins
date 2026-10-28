import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

TABLE_PATH = Path(__file__).with_name("reception.json")


def load_table(path: Path = TABLE_PATH) -> Dict[str, Any]:
    """The table of what each engine receives of the references, as the page reads it."""
    return json.loads(path.read_text(encoding="utf-8"))


TABLE = load_table()

LIMITS: Dict[str, int] = {kind: int(count) for kind, count in TABLE["limits"].items()}

ORDER: Tuple[str, ...] = tuple(TABLE["order"])

VIDEO_TRACKS: Dict[str, Any] = TABLE["videoTracks"]

SHEET: Dict[str, Any] = TABLE["sheet"]

SHEET_ID = "ic-sheet"

Box = Tuple[int, int, int, int]

MOTION = "motion"
CONTINUATION = "continuation"
UNDER = "under"
BEFORE = "before"
CANVAS = "canvas"
TAKE = "take"

EPSILON = 1e-6


def takes_sheet(family: Optional[str], profile: Optional[str]) -> bool:
    """Whether an engine family makes a profile's takes from a reference sheet: one picture of the cast's cards, sent as a still video to an IC-LoRA."""
    return family in SHEET["families"] and profile in SHEET["profiles"]


def takes_references(profile: Optional[str], family: Optional[str] = None) -> bool:
    """Whether a profile sends the references themselves to the engine, each kind within its limit; an engine family that makes it from a reference sheet sends the sheet instead."""
    return profile in TABLE["references"] and not takes_sheet(family, profile)


def sheet_size(aspect: float) -> Tuple[int, int]:
    """The width and height of a sheet take: the size the IC-LoRA was trained at when the aspect is within the table's tolerance of it, else the size on the table's grid closest to its pixel count at that aspect."""
    width, height = (int(side) for side in SHEET["size"])
    trained = width / height
    ratio = aspect if aspect > 0 else trained
    if abs(ratio / trained - 1) <= SHEET["tolerance"]:
        return width, height
    multiple = SHEET["multiple"]
    wide = math.sqrt(width * height * ratio)
    return max(multiple, round(wide / multiple) * multiple), max(multiple, round(wide / ratio / multiple) * multiple)


def sheet_frames(seconds: float) -> int:
    """The 1 + 8k frame count LTX renders at the sheet's rate closest to seconds, the lower one on a tie."""
    step = SHEET["frameStep"]
    frames = max(1, round(seconds * SHEET["fps"]))
    return 1 + step * max(0, math.ceil((frames - 1) / step - 0.5))


def sheet_layout(size: Tuple[int, int], counts: Sequence[int], place: bool) -> Tuple[List[Box], Optional[Box]]:
    """The boxes of a sheet on its black canvas, as x, y, width and height: one per picture of the characters, left to right in a band across the top, then the place in a band across the bottom; a band takes the whole height when the other is empty."""
    width, height = size
    gap = SHEET["gap"]
    cells = sum(count for count in counts if count > 0)
    top = (round(height * SHEET["split"]) if place else height) if cells else 0
    boxes: List[Box] = []
    if cells:
        each = (width - gap * (cells + 1)) // cells
        left = (width - cells * each - (cells - 1) * gap) // 2
        tall = top - gap - (gap // 2 if place else gap)
        boxes = [(left + index * (each + gap), gap, each, tall) for index in range(cells)]
    setting = (gap, top + (gap // 2 if cells else gap), width - 2 * gap, height - top - gap - (gap // 2 if cells else gap)) if place else None
    return boxes, setting


def sheet_work(form: Mapping[str, Any]) -> float:
    """How much longer than the same take without a sheet a request runs: the table's measured factor when its director document sends a sheet, else 1."""
    document = form.get("video_director") if isinstance(form, Mapping) else None
    entries = document.get("ic_lora") if isinstance(document, Mapping) else None
    sent = any(isinstance(entry, Mapping) and entry.get("id") == SHEET_ID for entry in entries or [])
    return float(SHEET["work"]) if sent else 1.0


def _matches(rule: Mapping[str, Any], family: str, profile: Optional[str]) -> bool:
    return ("profiles" not in rule or profile in rule["profiles"]) and ("families" not in rule or family in rule["families"])


def layout(family: str, profile: Optional[str] = None) -> str:
    """The layout of the part of a shot's prompt made from its references and its cast: the first rule of the table that matches the engine family and the profile."""
    return next(str(rule["layout"]) for rule in TABLE["layouts"] if _matches(rule, family, profile))


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def video_frames(seconds: Any) -> int:
    """The longest frame count MiniMax-H3 encodes whole (chunk * n + head frames at the table's rate) that lasts at most seconds; 0 below head frames."""
    value = _number(seconds)
    if value is None or value <= 0:
        return 0
    frames = math.floor(value * VIDEO_TRACKS["fps"] + EPSILON)
    head, chunk = VIDEO_TRACKS["head"], VIDEO_TRACKS["chunk"]
    return (frames - head) // chunk * chunk + head if frames >= head else 0


def least_seconds() -> float:
    """The shortest video a track sends, in seconds: the table's minimum frame count at its rate."""
    return VIDEO_TRACKS["minFrames"] / VIDEO_TRACKS["fps"]


def video_cap(seconds: Any) -> float:
    """The seconds a track sends at most: its own setting, never under the table's minimum, or the minimum when it sets none."""
    value = _number(seconds)
    return max(value, least_seconds()) if value is not None and value > 0 else least_seconds()


def window_side(role: Any) -> str:
    """Where a track's cut is taken for a shot: under it, or just before it."""
    return str(VIDEO_TRACKS["roles"].get(role if role in VIDEO_TRACKS["roles"] else MOTION))


def video_region(role: Any, start: float, seconds: float, cap: Any = None) -> Tuple[float, float]:
    """The part of the timeline a track's cut is taken from for a shot that starts at start and lasts seconds: under the shot for a motion track, just before it for a continuation, as long as the shot and the track's cap allow, never before 0."""
    length = max(0.0, min(float(seconds), video_cap(cap)))
    if window_side(role) == BEFORE:
        return max(0.0, start - length), float(start)
    return float(start), start + length


def video_pieces(items: Sequence[Mapping[str, Any]], role: Any, start: float, seconds: float, cap: Any = None) -> Tuple[int, List[Dict[str, Any]]]:
    """The frames a track sends to a shot and the parts of its items they come from, in timeline order: the items that play in its region put end to end without the gaps, then cut to the longest whole frame count, from the start for a motion track and up to the shot for a continuation."""
    begin, end = video_region(role, start, seconds, cap)
    spans = []
    for item in items:
        item_start, item_dur = _number(item.get("start")), _number(item.get("dur"))
        if item_start is None or item_dur is None or item_dur <= EPSILON:
            continue
        low, high = max(begin, item_start), min(end, item_start + item_dur)
        if high - low > EPSILON:
            spans.append((low, high, item))
    spans.sort(key=lambda span: span[0])
    frames = video_frames(sum(high - low for low, high, _ in spans))
    left = frames / VIDEO_TRACKS["fps"]
    pieces: List[Dict[str, Any]] = []
    ordered = spans if window_side(role) == UNDER else list(reversed(spans))
    for low, high, item in ordered:
        if left <= EPSILON:
            break
        take = min(left, high - low)
        left -= take
        part = (low, low + take) if window_side(role) == UNDER else (high - take, high)
        pieces.append({"id": item.get("id"), "from": round(part[0], 6), "to": round(part[1], 6)})
    pieces.sort(key=lambda piece: piece["from"])
    return frames, pieces


def cut_size(aspect: float, resolution: Optional[Tuple[int, int]] = None, setting: Optional[str] = None) -> Tuple[int, int]:
    """The width and height a track's cut is written at: MiniMax-H3's own canvas for the aspect (short edge, capped area, both sides to the multiple), or the size of the shot's own take."""
    chosen = setting if setting in VIDEO_TRACKS["sizes"] else VIDEO_TRACKS["size"]
    if chosen == TAKE and resolution:
        return int(resolution[0]), int(resolution[1])
    canvas = VIDEO_TRACKS["canvas"]
    edge, most, multiple = canvas["shortEdge"], canvas["maxPixels"], canvas["multiple"]
    ratio = aspect if aspect > 0 else 16 / 9
    width, height = (edge * ratio, float(edge)) if ratio >= 1 else (float(edge), edge / ratio)
    if width * height > most:
        scale = (most / (width * height)) ** 0.5
        width, height = width * scale, height * scale
    return max(multiple, round(width / multiple) * multiple), max(multiple, round(height / multiple) * multiple)
