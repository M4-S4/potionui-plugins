import asyncio
from pathlib import Path
from typing import Any, List, Sequence, Tuple

from . import reception
from .director import VideoCut
from .exports.video import ExportError, assemble, num

SUFFIX = ".mp4"

ENCODER = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p")


def cut_graph(spans: Sequence[Tuple[float, float]], frames: int, size: Tuple[int, int]) -> str:
    """The filter graph of one cut: each part read from its source between its two times, at the table's rate, scaled to cover the size and cropped to it, the parts joined end to end, then held on the last image and trimmed so that it holds exactly frames images."""
    fps = reception.VIDEO_TRACKS["fps"]
    width, height = size
    graph = [
        f"[{index}:v:0]trim=start={num(start)}:end={num(end)},setpts=PTS-STARTPTS,fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1,format=yuv420p[v{index}]"
        for index, (start, end) in enumerate(spans)
    ]
    joined = "".join(f"[v{index}]" for index in range(len(spans)))
    graph.append(f"{joined}concat=n={len(spans)}:v=1:a=0,tpad=stop_mode=clone:stop={fps},trim=end_frame={frames},setpts=PTS-STARTPTS[vout]")
    return ";".join(graph)


def cut_command(ffmpeg: str, inputs: Sequence[str], graph: str, frames: int, output: Path) -> List[str]:
    """The ffmpeg run that writes one cut as an H.264 video without sound, of exactly frames images at the table's rate."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *inputs,
        "-filter_complex", graph,
        "-map", "[vout]",
        "-an",
        *ENCODER,
        "-r", str(reception.VIDEO_TRACKS["fps"]),
        "-frames:v", str(frames),
        str(output),
    ]


async def cut(ffmpeg: str, sources: Any, cut: VideoCut, name: str) -> Path:
    """Write the cut a shot sends of a reference video track in the work folder of sources: the parts of its items, read from the start of each source, at the size of the cut; raises ExportError (video_source_missing, video_cut_failed)."""
    inputs: List[str] = []
    spans: List[Tuple[float, float]] = []
    for piece in cut.pieces:
        path = await asyncio.to_thread(sources.path, piece.asset_id)
        if path is None:
            raise ExportError("video_source_missing", "The video of a reference video track can no longer be read.")
        inputs.extend(["-i", path])
        spans.append((piece.source, piece.source + piece.end - piece.start))
    output = sources.folder / f"{name}{SUFFIX}"
    await assemble(cut_command(ffmpeg, inputs, cut_graph(spans, cut.frames, cut.size), cut.frames, output), cut.seconds, code="video_cut_failed")
    return output
