import asyncio
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import core_bridge, formats, frame_grab, reception, takes, workdir
from .core_bridge import User
from .exports import media
from .exports.common import asset_of
from .exports.video import ExportError, assemble, num
from .frame_grab import FrameError
from .vreftrack import ENCODER

SUFFIX = ".mp4"
EPSILON = 1e-6
AUDIO = ("-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k")


def cut_command(ffmpeg: str, source: str, start: float, frames: int, size: Tuple[int, int], output: Path, sound: bool = False) -> List[str]:
    fps = reception.VIDEO_TRACKS["fps"]
    width, height = size
    head = ["-ss", num(start)] if start > 0 else []
    graph = (
        f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},"
        f"setsar=1,format=yuv420p,tpad=stop_mode=clone:stop={fps}"
    )
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *head,
        "-i", source,
        "-map", "0:v:0",
        *(AUDIO if sound else ("-an",)),
        "-vf", graph,
        *ENCODER,
        "-r", str(fps),
        "-frames:v", str(frames),
        "-t", num(frames / fps),
        str(output),
    ]


def _source(project: Mapping[str, Any], previous: str, after: Optional[Mapping[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    doc = project["doc"]
    clip = next((item for item in doc.get("clips") or [] if item.get("id") == previous), None)
    if after is not None:
        length = float(clip.get("dur") or 0) * formats.speed_of(clip) if clip is not None else float(after.get("duration_s") or 0)
        return {"id": previous, "srcIn": 0, "dur": length}, frame_grab.take_asset(after)
    asset = asset_of(doc, (clip or {}).get("assetId"))
    if clip is None or asset is None or asset.get("kind") != "video":
        raise FrameError("no_media", "The previous shot has no video to continue.")
    return clip, asset


async def end_video(owner: User, project: Mapping[str, Any], previous: str, after: Optional[Mapping[str, Any]], frames: int, size: Tuple[int, int], sound: bool = False) -> Dict[str, Any]:
    clip, asset = _source(project, previous, after)
    shot_takes = takes.list_takes(project["id"])
    resolver = media.Resolver(owner)
    found = media.locate(asset, shot_takes, resolver)
    if found is None or not found.kind:
        raise FrameError("no_media", "The previous shot has no video to continue.")
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise FrameError("ffmpeg_missing", "ffmpeg is not available on this server: the end of the previous shot cannot be cut.", 503)
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    seconds = frames / reception.VIDEO_TRACKS["fps"]
    take = media.take_of(asset, shot_takes)
    try:
        folder = workdir.scratch(workdir.FRAMES, owner.id)
    except workdir.WorkdirError as exc:
        raise FrameError(exc.code, exc.message, 503) from None
    try:
        source = await asyncio.to_thread(resolver.local, found, folder)
        if source is None:
            raise FrameError("no_media", "The previous shot has no video to continue.")
        probe = await asyncio.to_thread(core_bridge.probe_video, source)
        end = frame_grab.end_of(clip)
        if probe is not None and probe.duration:
            end = min(end, float(probe.duration))
        start = end - seconds
        if start < -EPSILON:
            raise FrameError("chain_video_short", f"The previous take lasts less than the {seconds:.2f} s this shot continues.")
        output = folder / f"{Path(found.name).stem or 'shot'}-end-{num(end)}s{SUFFIX}"
        try:
            await assemble(cut_command(ffmpeg, str(source), max(start, 0.0), frames, size, output, sound), seconds, code="chain_video_failed")
        except ExportError as exc:
            raise FrameError(exc.code, exc.message, 502) from None
        stored = await core_bridge.save_user_media(owner, output)
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    return {
        "value": str(stored["value"]),
        "filename": output.name,
        "source": {"shotId": previous, "takeId": take["id"] if take else None, "assetId": asset["id"], "at": end},
        "frames": frames,
        "seconds": round(seconds, 6),
    }
