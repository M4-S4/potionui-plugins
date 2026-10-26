import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import core_bridge, takes
from .core_bridge import User
from .exports import media
from .exports.common import asset_of
from .exports.video import kill_tree, last_line, num

logger = logging.getLogger("plugins.video-producer")

PREROLL = 1.0

FRAME_SECONDS = 60.0


class ChainError(Exception):
    """The last frame of a shot that could not be taken, with the HTTP status it answers."""

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def work_base() -> Path:
    """The folder the frames of every user are written in before they are stored."""
    return core_bridge.storage_directory() / "video_producer" / "frames"


def end_of(clip: Mapping[str, Any]) -> float:
    """The time of its source the cut of a shot ends at, srcIn + dur, to the millisecond."""
    return round(max(float(clip.get("srcIn") or 0), 0.0) + max(float(clip.get("dur") or 0), 0.0), 3)


def start_of(clip: Mapping[str, Any]) -> float:
    """The time of its source the cut of a shot starts at, srcIn, to the millisecond."""
    return round(max(float(clip.get("srcIn") or 0), 0.0), 3)


def frame_command(ffmpeg: str, source: str, end: float, output: Path, length: Optional[float] = None) -> List[str]:
    """The ffmpeg command that writes the last frame a video of length seconds shows before end seconds into output: it decodes from PREROLL seconds before end, or before the end of the video when end is past it, drops every frame from end on and overwrites output with each frame it keeps."""
    seek = max(round(min(end, length or end) - PREROLL, 3), 0.0)
    head = ["-ss", num(seek)] if seek > 0 else []
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *head,
        "-i",
        source,
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        f"trim=end={num(end - seek)}",
        "-fps_mode",
        "passthrough",
        "-update",
        "1",
        "-y",
        str(output),
    ]


def first_frame_command(ffmpeg: str, source: str, start: float, output: Path) -> List[str]:
    """The ffmpeg command that writes the first frame a video shows from start seconds into output: a seek on the input, which ffmpeg makes exact by decoding from the keyframe before, then one frame."""
    head = ["-ss", num(start)] if start > 0 else []
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *head,
        "-i",
        source,
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-frames:v",
        "1",
        "-y",
        str(output),
    ]


async def run(command: List[str]) -> None:
    """Run one ffmpeg command; raises ChainError when it fails, writes nothing or runs longer than FRAME_SECONDS."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
    except OSError as exc:
        raise ChainError("extract_failed", last_line(str(exc)) or "ffmpeg could not start.", 502) from None
    try:
        _, errors = await asyncio.wait_for(process.communicate(), FRAME_SECONDS)
    except asyncio.TimeoutError:
        raise ChainError("extract_failed", f"Taking the frame took longer than {FRAME_SECONDS:g} s.", 502) from None
    finally:
        if kill_tree(process):
            await process.wait()
    output = Path(command[-1])
    if process.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        message = last_line(errors.decode("utf-8", "replace"))
        logger.warning("[VIDEO-PRODUCER] Could not take the last frame of a shot: %s", message)
        raise ChainError("extract_failed", message or "The frame could not be taken from the video.", 502)


def _no_media(first: bool = False) -> ChainError:
    which = "first" if first else "last"
    return ChainError("no_media", f"The shot has no video to take its {which} frame from.")


def _placed(project: Mapping[str, Any], shot_id: str, first: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    doc = project["doc"]
    clip = next((item for item in doc.get("clips") or [] if item.get("id") == shot_id), None)
    if clip is None:
        raise ChainError("shot_not_found", "The shot does not exist.", 404)
    asset = asset_of(doc, clip.get("assetId"))
    if asset is None or asset.get("kind") != "video":
        raise _no_media(first)
    return clip, asset


async def end_frame(owner: User, project: Mapping[str, Any], shot_id: str) -> Dict[str, Any]:
    """Store, as the owner's upload, the last frame a shot shows at the end of its cut of its placed take or video, named <file>-frame-<end>s.png; the stored key, the file name and where it was taken: shot, take, asset and end. Raises ChainError, MediaRefError or LimitExceeded."""
    clip, asset = _placed(project, shot_id, False)
    return await cut_frame(owner, project["id"], clip, asset)


async def start_frame(owner: User, project: Mapping[str, Any], shot_id: str) -> Dict[str, Any]:
    """Store, as end_frame does, the first frame a shot shows at the start of its cut (srcIn) of its placed take or video; where it was taken gives that start."""
    clip, asset = _placed(project, shot_id, True)
    return await cut_frame(owner, project["id"], clip, asset, first=True)


def take_asset(take: Mapping[str, Any]) -> Dict[str, Any]:
    """The asset the page makes of a finished take, as far as finding its file needs."""
    return {"id": f"gen-{take['id']}", "kind": "video", "resultId": take["id"], "generated": True}


async def take_end_frame(owner: User, project: Mapping[str, Any], shot_id: str, take: Mapping[str, Any]) -> Dict[str, Any]:
    """Store the frame a finished take of a shot ends on once placed on it: the shot's cut starts at 0 on a take just placed, so the end is its duration, or the take's when the shot is gone; as end_frame does."""
    clip = next((item for item in project["doc"].get("clips") or [] if item.get("id") == shot_id), None)
    length = float(clip.get("dur") or 0) if clip is not None else float(take.get("duration_s") or 0)
    return await cut_frame(owner, project["id"], {"id": shot_id, "srcIn": 0, "dur": length}, take_asset(take))


def media_of(owner_id: str, frame: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The library media of a stored frame, as the page reads it, or None when its library item cannot be found."""
    item = core_bridge.upload_item(owner_id, frame["value"]) or {}
    if not item.get("item_id"):
        return None
    return {
        "kind": "library",
        "item_id": item["item_id"],
        "media_type": "image",
        "url": f"/api/media/uploads/{media.basename(frame['value'])}",
        "filename": frame["filename"],
        "width": item.get("width"),
        "height": item.get("height"),
        "origin": {"kind": "library", "itemId": item["item_id"]},
    }


async def cut_frame(owner: User, project_id: str, clip: Mapping[str, Any], asset: Mapping[str, Any], first: bool = False) -> Dict[str, Any]:
    """Store the last frame the video of asset shows at the end of the cut of clip, as end_frame does, or its first frame at the start of the cut."""
    shot_takes = takes.list_takes(project_id)
    resolver = media.Resolver(owner)
    found = media.locate(asset, shot_takes, resolver)
    if found is None or not found.kind:
        raise _no_media(first)
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise ChainError("ffmpeg_missing", "ffmpeg is not available on this server: the last frame cannot be taken.", 503)
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    end = end_of(clip)
    at = start_of(clip) if first else end
    take = media.take_of(asset, shot_takes)
    base = work_base() / owner.id
    base.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=base))
    try:
        source = await asyncio.to_thread(resolver.local, found.kind, found.value, folder)
        if source is None:
            raise _no_media(first)
        output = folder / f"{Path(found.name).stem or 'shot'}-frame-{num(at)}s.png"
        if first:
            await run(first_frame_command(ffmpeg, str(source), at, output))
        else:
            probe = await asyncio.to_thread(core_bridge.probe_video, source)
            await run(frame_command(ffmpeg, str(source), end, output, probe.duration if probe else None))
        stored = await core_bridge.save_user_media(owner, output)
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    return {
        "value": str(stored["value"]),
        "filename": output.name,
        "source": {"shotId": clip["id"], "takeId": take["id"] if take else None, "assetId": asset["id"], "at": at},
    }
