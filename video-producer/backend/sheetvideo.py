import asyncio
from pathlib import Path
from typing import Any, List, Sequence, Tuple

from . import reception
from .director import SheetPlan
from .exports.video import ExportError, assemble, num

SUFFIX = ".mp4"

ENCODER = ("-c:v", "libx264", "-preset", "slow", "-crf", "10", "-tune", "stillimage", "-pix_fmt", "yuv420p")


def bands(boxes: Sequence[reception.Box]) -> List[Tuple[reception.Box, List[int]]]:
    """The band of each run of pictures that share one, in order, with the input numbers of its pictures (input 0 being the canvas)."""
    found: List[Tuple[reception.Box, List[int]]] = []
    for index, box in enumerate(boxes, start=1):
        if found and found[-1][0] == box:
            found[-1][1].append(index)
        else:
            found.append((box, [index]))
    return found


def sheet_graph(boxes: Sequence[reception.Box]) -> str:
    """The filter graph of a sheet, as the measured sheet was drawn: in each band, its pictures scaled whole to its height and put side by side with the table's gap between them, the row shrunk to fit the band's width when it is wider, then centred in the band over the black canvas of input 0."""
    gap = reception.SHEET["gap"]
    graph: List[str] = []
    base = "0:v"
    for number, ((x, y, width, height), inputs) in enumerate(bands(boxes), start=1):
        for position, index in enumerate(inputs):
            pad = f",pad=iw+{gap}:ih:0:0:color=black" if position < len(inputs) - 1 else ""
            graph.append(f"[{index}:v]scale=-2:{height}:flags=lanczos,setsar=1,format=yuv420p{pad}[p{index}]")
        joined = "".join(f"[p{index}]" for index in inputs)
        stack = f"{joined}hstack=inputs={len(inputs)}," if len(inputs) > 1 else joined
        graph.append(f"{stack}scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,setsar=1[r{number}]")
        graph.append(f"[{base}][r{number}]overlay=x={x}+({width}-overlay_w)/2:y={y}+({height}-overlay_h)/2:eof_action=repeat:format=yuv420[b{number}]")
        base = f"b{number}"
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
