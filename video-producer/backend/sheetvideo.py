import asyncio
from pathlib import Path
from typing import Any, List, Sequence

from . import reception
from .director import SheetPlan
from .exports.video import ExportError, assemble, num

SUFFIX = ".mp4"

ENCODER = ("-c:v", "libx264", "-preset", "slow", "-crf", "10", "-tune", "stillimage", "-pix_fmt", "yuv420p")


def sheet_graph(boxes: Sequence[reception.Box]) -> str:
    """The filter graph of a sheet: each picture scaled to fit its box without cropping and centred in it over the black canvas of input 0, one after the other."""
    graph: List[str] = []
    base = "0:v"
    for index, (x, y, width, height) in enumerate(boxes, start=1):
        graph.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,setsar=1,format=yuv420p[p{index}]"
        )
        graph.append(f"[{base}][p{index}]overlay=x={x}+({width}-overlay_w)/2:y={y}+({height}-overlay_h)/2:eof_action=repeat:format=yuv420[b{index}]")
        base = f"b{index}"
    graph.append(f"[{base}]format=yuv420p,setsar=1[vout]")
    return ";".join(graph)


def sheet_command(ffmpeg: str, pictures: Sequence[str], sheet: SheetPlan, output: Path) -> List[str]:
    """The ffmpeg run that writes a sheet as an H.264 still video without sound: a black canvas of its size, each picture held over it, exactly its frames at its rate."""
    width, height = sheet.size
    rate = num(sheet.fps)
    inputs: List[str] = ["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={rate}"]
    for path in pictures:
        inputs.extend(["-loop", "1", "-framerate", rate, "-i", path])
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *inputs,
        "-filter_complex", sheet_graph([panel.box for panel in sheet.panels]),
        "-map", "[vout]",
        "-an",
        *ENCODER,
        "-r", rate,
        "-frames:v", str(sheet.frames),
        str(output),
    ]


async def make(ffmpeg: str, sources: Any, sheet: SheetPlan, name: str) -> Path:
    """Write a shot's reference sheet in the work folder of sources from the pictures of its panels; raises ExportError (sheet_source_missing, sheet_failed)."""
    pictures: List[str] = []
    for panel in sheet.panels:
        path = await asyncio.to_thread(sources.path, panel.asset_id)
        if path is None:
            raise ExportError("sheet_source_missing", "A picture of the reference sheet can no longer be read.")
        pictures.append(path)
    output = sources.folder / f"{name}{SUFFIX}"
    await assemble(sheet_command(ffmpeg, pictures, sheet, output), sheet.seconds, code="sheet_failed")
    return output
