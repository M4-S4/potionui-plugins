import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

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


def _no_media() -> ChainError:
    return ChainError("no_media", "The shot has no video to take its last frame from.")


async def end_frame(owner: User, project: Mapping[str, Any], shot_id: str) -> Dict[str, Any]:
    """Store, as the owner's upload, the last frame a shot shows at the end of its cut of its placed take or video, named <file>-frame-<end>s.png; the stored key, the file name and where it was taken: shot, take, asset and end. Raises ChainError, MediaRefError or LimitExceeded."""
    doc = project["doc"]
    clip = next((item for item in doc.get("clips") or [] if item.get("id") == shot_id), None)
    if clip is None:
        raise ChainError("shot_not_found", "The shot does not exist.", 404)
    asset = asset_of(doc, clip.get("assetId"))
    if asset is None or asset.get("kind") != "video":
        raise _no_media()
    shot_takes = takes.list_takes(project["id"])
    resolver = media.Resolver(owner)
    found = media.locate(asset, shot_takes, resolver)
    if found is None or not found.kind:
        raise _no_media()
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise ChainError("ffmpeg_missing", "ffmpeg is not available on this server: the last frame cannot be taken.", 503)
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    end = end_of(clip)
    take = media.take_of(asset, shot_takes)
    base = work_base() / owner.id
    base.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=base))
    try:
        source = await asyncio.to_thread(resolver.local, found.kind, found.value, folder)
        if source is None:
            raise _no_media()
        probe = await asyncio.to_thread(core_bridge.probe_video, source)
        output = folder / f"{Path(found.name).stem or 'shot'}-frame-{num(end)}s.png"
        await run(frame_command(ffmpeg, str(source), end, output, probe.duration if probe else None))
        stored = await core_bridge.save_user_media(owner, output)
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    return {
        "value": str(stored["value"]),
        "filename": output.name,
        "source": {"shotId": clip["id"], "takeId": take["id"] if take else None, "assetId": asset["id"], "at": end},
    }
