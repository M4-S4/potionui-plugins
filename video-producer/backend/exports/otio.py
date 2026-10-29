from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import formats
from .common import UNDEFINED, Timebase, asset_of, clip_label, js_json


def reference(entry: Optional[Mapping[str, str]]) -> Dict[str, Any]:
    """The media references of a clip: its file, or a missing reference when it has none."""
    if entry:
        return {"DEFAULT_MEDIA": {"OTIO_SCHEMA": "ExternalReference.1", "target_url": entry["path"]}}
    return {"DEFAULT_MEDIA": {"OTIO_SCHEMA": "MissingReference.1"}}


def render(doc: Mapping[str, Any], files: Mapping[Tuple[str, int], Optional[Dict[str, str]]], locale: str = "en") -> str:
    """The sequence as an OpenTimelineIO timeline: the shots on V1, a slowed shot from its in point for its duration on the timeline with a linear time warp, one audio track per lane named A1, A2… by its position."""
    time = Timebase(doc)

    def span(start: Any, dur: Any) -> Dict[str, Any]:
        return {
            "OTIO_SCHEMA": "TimeRange.1",
            "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": time.fps, "value": time.frames(start)},
            "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": time.fps, "value": time.frames(dur)},
        }

    video: List[Dict[str, Any]] = []
    for index, clip in enumerate(doc["clips"]):
        entry = files.get(("clips", index))
        if entry:
            speed = formats.speed_of(clip)
            item: Dict[str, Any] = {
                "OTIO_SCHEMA": "Clip.2",
                "name": clip_label(doc, clip, locale),
                "source_range": span(clip["srcIn"], clip["dur"]),
                "media_references": reference(entry),
                "active_media_reference_key": "DEFAULT_MEDIA",
                "metadata": {"video_producer": {"stage": clip.get("stage", UNDEFINED), "take": clip.get("take", UNDEFINED)}},
            }
            if speed != 1:
                item["effects"] = [{"OTIO_SCHEMA": "LinearTimeWarp.1", "name": "", "effect_name": "LinearTimeWarp", "metadata": {}, "time_scalar": speed}]
            video.append(item)
        else:
            video.append({"OTIO_SCHEMA": "Gap.1", "name": clip_label(doc, clip, locale), "source_range": span(0, clip["dur"])})
    lanes = []
    audio = list(enumerate(doc.get("audio") or []))
    for position, lane in enumerate(doc.get("lanes") or [], start=1):
        items = sorted((pair for pair in audio if pair[1].get("lane") == lane["id"]), key=lambda pair: pair[1]["start"])
        children: List[Dict[str, Any]] = []
        at: Any = 0
        for index, item in items:
            if item["start"] > at:
                children.append({"OTIO_SCHEMA": "Gap.1", "source_range": span(0, item["start"] - at)})
            source = asset_of(doc, item.get("assetId"))
            children.append(
                {
                    "OTIO_SCHEMA": "Clip.2",
                    "name": source.get("name", UNDEFINED) if source else UNDEFINED,
                    "source_range": span(item["srcIn"], item["dur"]),
                    "media_references": reference(files.get(("audio", index))),
                    "active_media_reference_key": "DEFAULT_MEDIA",
                    "metadata":{"video_producer": {"role": lane.get("role", UNDEFINED), "gain_db": item.get("gain", UNDEFINED)}},
                }
            )
            at = item["start"] + item["dur"]
        lanes.append({"OTIO_SCHEMA": "Track.1", "name": f"A{position} · {lane['name']}", "kind": "Audio", "children": children})
    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": doc["name"],
        "global_start_time": None,
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": [{"OTIO_SCHEMA": "Track.1", "name": "V1", "kind": "Video", "children": video}, *lanes],
        },
    }
    return js_json(timeline)
