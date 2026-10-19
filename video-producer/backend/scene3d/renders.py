import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from .. import core_bridge
from ..core_bridge import User, generate_ulid
from ..exports import video
from ..exports.video import ExportError, num
from . import captures, storage
from .storage import SceneError

META = "render.json"

FRAME_NAME = "{:06d}.jpg"

PATTERN = "%06d.jpg"

MAX_SIDE = 4096

MAX_FPS = 120

MAX_FRAMES = 400

MAX_BATCH = 24

MAX_FRAME_BYTES = 8 * storage.MIB

BODY_LIMIT = 32 * storage.MIB

MAX_RENDER_BYTES = 2 * storage.GIB

MAX_OPEN = 2

STALE_SECONDS = 3600

ENCODER = ("-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-movflags", "+faststart", "-an")

_PROCESSES: Dict[str, Any] = {}

_FINISHING: Set[str] = set()


def folder_of(project_id: str, render_id: str) -> Path:
    """The working folder of a render."""
    return storage.renders_folder(project_id) / render_id


def _read_meta(folder: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((folder / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def get_render(project_id: str, render_id: str) -> Optional[Dict[str, Any]]:
    """A render in progress of a project, or None."""
    if not storage.is_id(render_id):
        return None
    meta = _read_meta(folder_of(project_id, render_id))
    return meta if meta is not None and meta.get("project_id") == project_id else None


def _abandoned(entry: Path, limit: float) -> bool:
    try:
        idle = entry.stat().st_mtime < limit
    except OSError:
        return False
    return idle and entry.name not in _FINISHING and entry.name not in _PROCESSES


def create(project_id: str, user_id: str, width: int, height: int, fps: float, frames: int, name: str) -> Dict[str, Any]:
    """Open a render: a folder that receives its JPEG frames before they are encoded; the project's renders left without a write for an hour go first, and SceneError when MAX_OPEN others are still open."""
    limit = time.time() - STALE_SECONDS
    still_open = []
    for folder in storage.folders(storage.renders_folder(project_id)):
        if _abandoned(folder, limit):
            storage.drop(folder)
        else:
            still_open.append(folder)
    if len(still_open) >= MAX_OPEN:
        raise SceneError(409, "render_limit", f"A project has at most {MAX_OPEN} renders open at once.", limit=MAX_OPEN)
    render_id = generate_ulid()
    folder = folder_of(project_id, render_id)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": render_id,
        "project_id": project_id,
        "user_id": user_id,
        "width": width,
        "height": height,
        "fps": fps,
        "frames": frames,
        "name": name,
        "created_at": storage.now(),
    }
    (folder / META).write_text(json.dumps(meta), encoding="utf-8")
    return meta


def received(render: Dict[str, Any]) -> int:
    """How many of a render's frames are on disk."""
    folder = folder_of(render["project_id"], render["id"])
    return sum(1 for index in range(render["frames"]) if (folder / FRAME_NAME.format(index)).is_file())


def busy(render_id: str) -> bool:
    """True while a render is being encoded."""
    return render_id in _FINISHING


def _frames_bytes(folder: Path, replaced: Set[str]) -> int:
    total = 0
    for path in folder.glob("*.jpg"):
        if path.name not in replaced:
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def add_frames(render: Dict[str, Any], start: int, images: Sequence[bytes]) -> int:
    """Store a batch of JPEG frames from frame start on; returns how many frames of the render are on disk, SceneError when it is being encoded, is gone or would pass MAX_RENDER_BYTES."""
    if busy(render["id"]):
        raise SceneError(409, "render_busy", "This render is already being encoded.")
    folder = folder_of(render["project_id"], render["id"])
    replaced = {FRAME_NAME.format(start + offset) for offset in range(len(images))}
    if _frames_bytes(folder, replaced) + sum(len(data) for data in images) > MAX_RENDER_BYTES:
        raise SceneError(413, "render_too_large", f"The frames of a render take at most {MAX_RENDER_BYTES // storage.GIB} GiB.", limit=MAX_RENDER_BYTES)
    try:
        for offset, data in enumerate(images):
            path = folder / FRAME_NAME.format(start + offset)
            part = path.with_suffix(".part")
            part.write_bytes(data)
            part.replace(path)
        os.utime(folder)
    except FileNotFoundError:
        raise SceneError(404, "render_not_found", "The render does not exist.") from None
    return received(render)


def add_batch(render: Dict[str, Any], start: int, images: Sequence[Any]) -> int:
    """Decode a batch of JPEG data URLs and store them as frames from frame start on; SceneError for an image that is not one."""
    decoded = []
    for index, image in enumerate(images):
        data = captures.decode(image, "jpeg", MAX_FRAME_BYTES)
        if data is None:
            raise SceneError(
                422, "invalid_request", f"images[{index}] is not a base64 data URL of a JPEG image of at most {MAX_FRAME_BYTES // storage.MIB} MiB."
            )
        decoded.append(data)
    return add_frames(render, start, decoded)


def command(ffmpeg: str, render: Dict[str, Any], output: str) -> List[str]:
    """The ffmpeg run that encodes a render's frames, read from its folder, into an H.264 MP4 at crf 18 in limited-range yuv420p, written to ./output in that folder."""
    rate = num(render["fps"])
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-f", "image2", "-framerate", rate, "-start_number", "0", "-i", PATTERN,
        "-frames:v", str(render["frames"]), "-vf", f"scale={render['width']}:{render['height']}:flags=lanczos:out_range=tv", "-r", rate,
        *ENCODER, f"./{output}",
    ]


def kill(render_id: str) -> bool:
    """Kill the ffmpeg run of a render being encoded; False when it has none."""
    process = _PROCESSES.get(render_id)
    return process is not None and video.kill_tree(process)


def _track(render_id: str):
    def on_process(process: Any) -> None:
        if process is None:
            _PROCESSES.pop(render_id, None)
        else:
            _PROCESSES[render_id] = process

    return on_process


async def finish(owner: User, render: Dict[str, Any]) -> Dict[str, Any]:
    """Encode a render whose frames all arrived and store the video in the project owner's library; SceneError otherwise."""
    render_id = render["id"]
    if render_id in _FINISHING:
        raise SceneError(409, "render_busy", "This render is already being encoded.")
    missing = render["frames"] - received(render)
    if missing:
        raise SceneError(409, "frames_missing", f"{missing} frame(s) of the render have not arrived.", missing=missing)
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise SceneError(409, "ffmpeg_unavailable", "ffmpeg is missing on the server.")
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    folder = folder_of(render["project_id"], render_id)
    output = f"{captures.file_stem(render.get('name'), 'render')}.mp4"
    _FINISHING.add(render_id)
    try:
        seconds = render["frames"] / render["fps"]
        try:
            await video.assemble(command(ffmpeg, render, output), seconds, None, _track(render_id), str(folder), "encode_failed")
        except ExportError as exc:
            if not folder.is_dir():
                raise SceneError(404, "render_not_found", "The render was deleted while it was being encoded.") from None
            raise SceneError(502, exc.code, exc.message) from None
        if not folder.is_dir():
            raise SceneError(404, "render_not_found", "The render was deleted while it was being encoded.")
        path = folder / output
        if not path.is_file() or path.stat().st_size == 0:
            raise SceneError(502, "encode_failed", "ffmpeg wrote an empty video.")
        stored, item = await captures.store_media(owner, path)
    finally:
        _FINISHING.discard(render_id)
    storage.drop(folder)
    return captures.media(
        stored,
        item,
        "video",
        width=item.get("width") or render["width"],
        height=item.get("height") or render["height"],
        fps=render["fps"],
        duration=round(seconds, 3),
    )


def delete(render: Dict[str, Any]) -> None:
    """Stop and delete a render in progress with its frames."""
    kill(render["id"])
    storage.drop(folder_of(render["project_id"], render["id"]))


def forget_project(project_id: str) -> None:
    """Stop the renders of a deleted project."""
    for folder in storage.folders(storage.renders_folder(project_id)):
        kill(folder.name)


def sweep(max_age: float = STALE_SECONDS, now: Optional[float] = None) -> int:
    """Delete the renders and work files left without a write for more than an hour; returns how many it deleted."""
    limit = (time.time() if now is None else now) - max_age
    removed = 0
    for project in storage.folders(storage.scenes_base()):
        for parent in (storage.renders_folder(project.name), storage.work_folder(project.name)):
            try:
                entries = list(parent.iterdir())
            except OSError:
                continue
            for entry in entries:
                if _abandoned(entry, limit):
                    storage.drop(entry)
                    removed += 1
    return removed
