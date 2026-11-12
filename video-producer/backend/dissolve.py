import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, List, Mapping, Optional, Sequence

KEY = "dissolve"
MAX_DISSOLVE = 2
GRID = 0.04
MIN_STEPS = 2
MIN_DISSOLVE = MIN_STEPS * GRID
STEP_SLACK = 1e-6
EPSILON = 1e-6
MICRO = Decimal("0.000001")
COARSE = 1e15


def _seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if math.isfinite(number) and number > 0 else 0.0


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if math.isfinite(number) else 0.0


def rounded(value: float) -> float:
    return float(Decimal(value).quantize(MICRO, rounding=ROUND_HALF_UP)) if math.isfinite(value) and abs(value) < COARSE else value


def frames_of(seconds: Any, fps: Any) -> int:
    return math.floor(_number(seconds) * _seconds(fps) + 0.5)


def dissolve_of(before: Optional[Mapping[str, Any]], clip: Optional[Mapping[str, Any]]) -> float:
    if before is None or clip is None:
        return 0.0
    asked = _seconds(clip.get(KEY))
    if asked <= 0:
        return 0.0
    length = min(asked, MAX_DISSOLVE, min(_seconds(before.get("dur")), _seconds(clip.get("dur"))) / 2)
    steps = math.floor(length / GRID + STEP_SLACK)
    return rounded(steps * GRID) if steps >= MIN_STEPS else 0.0


def played(before: Optional[Mapping[str, Any]], clip: Optional[Mapping[str, Any]]) -> float:
    length = dissolve_of(before, clip)
    if not length:
        return 0.0
    overlap = _number(before.get("start")) + _number(before.get("dur")) - _number(clip.get("start"))
    if overlap <= GRID / 2 or overlap > length + EPSILON:
        return 0.0
    return rounded(overlap)


@dataclass(frozen=True)
class Place:
    start: float
    end: float
    overlap: float


def placement(clips: Sequence[Mapping[str, Any]]) -> List[Optional[Place]]:
    places: List[Optional[Place]] = [None] * len(clips)
    last: Optional[int] = None
    for index, clip in enumerate(clips):
        dur = _seconds(clip.get("dur"))
        if dur <= EPSILON:
            continue
        start, overlap = _number(clip.get("start")), 0.0
        if last is not None:
            before = places[last]
            joined = played(clips[last], clip) if last == index - 1 and before.start == _number(clips[last].get("start")) else 0.0
            if joined:
                overlap = joined
            elif start < before.end - EPSILON:
                if start > before.start + before.overlap + EPSILON:
                    places[last] = Place(before.start, start, before.overlap)
                else:
                    start = before.end
        places[index] = Place(start, rounded(start + dur), overlap)
        last = index
    return places


def moved(clip: Mapping[str, Any], place: Optional[Place]) -> bool:
    return place is not None and (place.start != _number(clip.get("start")) or place.end != rounded(place.start + _seconds(clip.get("dur"))))


def joins(clips: Sequence[Mapping[str, Any]]) -> List[float]:
    return [place.overlap if place is not None else 0.0 for place in placement(clips)]


def dissolving(clips: Sequence[Mapping[str, Any]]) -> bool:
    return any(joins(clips))


def shown(clips: Sequence[Mapping[str, Any]]) -> List[Place]:
    places = placement(clips)
    if not any(place is not None and place.overlap for place in places):
        return [Place(_number(clip.get("start")), _number(clip.get("start")) + _number(clip.get("dur")), 0.0) for clip in clips]
    starts = [place.start + place.overlap / 2 if place is not None else _number(clips[index].get("start")) for index, place in enumerate(places)]
    ends = [place.end if place is not None else starts[index] for index, place in enumerate(places)]
    for index, place in enumerate(places):
        following = places[index + 1] if index + 1 < len(places) else None
        if place is None or following is None or not following.overlap > 0:
            continue
        starts[index + 1] = max(starts[index + 1], starts[index])
        ends[index] = starts[index + 1]
    return [Place(starts[index], max(ends[index], starts[index]), place.overlap if place is not None else 0.0) for index, place in enumerate(places)]


def chained(clips: Sequence[Mapping[str, Any]]) -> bool:
    return any(dissolve_of(before, clip) for before, clip in zip(clips, clips[1:]))


def layout(clips: Sequence[Mapping[str, Any]], snap: Callable[[float], float]) -> List[float]:
    starts: List[float] = []
    exact, at = chained(clips), 0.0
    for index, clip in enumerate(clips):
        if not exact:
            starts.append(snap(at))
        elif not index:
            starts.append(0.0)
        else:
            starts.append(rounded(starts[-1] + _number(clips[index - 1].get("dur")) - dissolve_of(clips[index - 1], clip)))
        at += _number(clip.get("dur"))
    return starts


@dataclass(frozen=True)
class Cut:
    start: int
    end: int
    overlap: int
    head: int


def cuts(clips: Sequence[Mapping[str, Any]], frames: Callable[[Any], int]) -> List[Optional[Cut]]:
    places = placement(clips)
    if not any(place is not None and place.overlap for place in places):
        return [None] * len(clips)
    starts = [frames(place.start) if place is not None else 0 for place in places]
    ends = [frames(place.end) if place is not None else 0 for place in places]
    overlaps = [0] * len(clips)
    for index in range(1, len(clips)):
        if places[index] is not None and places[index].overlap:
            ends[index - 1] = max(ends[index - 1], starts[index] + 1)
            overlaps[index] = ends[index - 1] - starts[index]
        elif places[index] is not None:
            ends[index - 1] = min(ends[index - 1], starts[index])
    edits = [start + overlap // 2 for start, overlap in zip(starts, overlaps)]
    result: List[Optional[Cut]] = []
    for index, clip in enumerate(clips):
        place = places[index]
        following = index + 1 < len(clips) and overlaps[index + 1] > 0
        if place is None or not (overlaps[index] or following or moved(clip, place)):
            result.append(None)
            continue
        start = edits[index] if overlaps[index] else starts[index]
        end = edits[index + 1] if following else ends[index]
        result.append(Cut(start, end, overlaps[index], start - starts[index]))
    return result
