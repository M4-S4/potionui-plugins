import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import psutil

from .. import core_bridge, director, takes
from ..core_bridge import TranscodeSpec, User, VideoTranscodeError
from . import media, slug
from .common import asset_of, fps_of, seq_duration, timing_error

logger = logging.getLogger("plugins.video-producer")

FORMATS = ("web", "social")

RESOLUTIONS = {"720p": 720, "1080p": 1080, "4K": 2160}

DEFAULT_RESOLUTION = "1080p"

SOCIAL_ASPECT = 9 / 16

FALLBACK_ASPECT = 16 / 9

MIN_ASPECT, MAX_ASPECT = 1 / 4, 4.0

SLUG_LIMIT = 80

MIN_FADE = 0.01

SAMPLE_RATE = 48000

ASSEMBLE_SHARE = 70.0

MIX_FROM = 50.0

TRANSCODE_END = 95.0

MESSAGE_LIMIT = 300

EPSILON = 1e-6

MEZZANINE = "mezzanine.mp4"

GRAPH = "graph.txt"

DISCARD_TRIES = 5

DISCARD_PAUSE = 0.2

ENCODER = (
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-ar", str(SAMPLE_RATE), "-ac", "2", "-movflags", "+faststart",
)


class ExportError(Exception):
    """An export that stopped, with its error code and the last useful line of what failed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def cancelled() -> ExportError:
    """The error of an export cancelled while it ran."""
    return ExportError("cancelled", "The export was cancelled.")


def num(value: Any) -> str:
    """A number for an ffmpeg option: at most six decimals, no trailing zeros."""
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def last_line(text: str, limit: int = MESSAGE_LIMIT) -> str:
    """The last non-empty line of a text, at most limit characters."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


def exports_base() -> Path:
    """The export cache of every user."""
    return core_bridge.storage_directory() / "video_producer" / "exports"


def exports_root(user_id: str) -> Path:
    """The export cache of a user."""
    return exports_base() / user_id


def job_folder(job: Mapping[str, Any]) -> Path:
    """The working folder of an export job."""
    return exports_root(job["user_id"]) / job["id"]


def file_name(project_name: str, resolution: str) -> str:
    """The name of an exported video: <slug>_<resolution>.mp4, the slug cut to 80 characters."""
    return f"{slug(project_name)[:SLUG_LIMIT].rstrip('._')}_{resolution}.mp4"


def resolution_of(doc: Mapping[str, Any], requested: Optional[str] = None) -> str:
    """The export resolution: the one asked for, else the project's, else 1080p."""
    if requested in RESOLUTIONS:
        return requested
    return doc.get("resolution") if doc.get("resolution") in RESOLUTIONS else DEFAULT_RESOLUTION


def _even(value: float) -> int:
    whole = int(round(value))
    return max(2, whole - whole % 2)


def frame_size(doc: Mapping[str, Any], fmt: str, resolution: str) -> Tuple[int, int]:
    """The frame of the export: the short side from the resolution, the long side from the aspect (9:16 for social, 16:9 past 1:4 or 4:1)."""
    base = RESOLUTIONS.get(resolution, RESOLUTIONS[DEFAULT_RESOLUTION])
    aspect = SOCIAL_ASPECT if fmt == "social" else director.aspect_of(doc)
    if not MIN_ASPECT <= aspect <= MAX_ASPECT:
        aspect = FALLBACK_ASPECT
    if aspect >= 1:
        return _even(base * aspect), base
    return base, _even(base / aspect)


def timeline(doc: Mapping[str, Any]) -> Tuple[List[Tuple[float, Optional[Mapping[str, Any]]]], float]:
    """The shots in document order with black where nothing plays, and the running time of the sequence."""
    segments: List[Tuple[float, Optional[Mapping[str, Any]]]] = []
    cursor = 0.0
    for clip in doc.get("clips") or []:
        dur = float(clip.get("dur") or 0)
        if dur <= EPSILON:
            continue
        start = float(clip.get("start") or 0)
        if start > cursor + EPSILON:
            segments.append((start - cursor, None))
            cursor = start
        segments.append((dur, clip))
        cursor += dur
    total = float(seq_duration(doc))
    if total > cursor + EPSILON:
        segments.append((total - cursor, None))
    return segments, total


def _look(clip: Mapping[str, Any]) -> List[str]:
    filters = []
    exposure, contrast, saturation = clip.get("exposure") or 0, clip.get("contrast", 100), clip.get("saturation", 100)
    if exposure or contrast != 100 or saturation != 100:
        filters.append(
            f"eq=contrast={num(contrast / 100)}:saturation={num(saturation / 100)}:brightness={num(exposure * 0.125)}"
        )
    if clip.get("temperature"):
        filters.append(f"colortemperature=temperature={num(6500 - clip['temperature'] * 20)}:pl=1")
    return filters


def _fades(item: Mapping[str, Any], dur: float, name: str) -> List[str]:
    filters = []
    fade_in, fade_out = float(item.get("fadeIn") or 0), float(item.get("fadeOut") or 0)
    if fade_in >= MIN_FADE:
        filters.append(f"{name}=t=in:st=0:d={num(min(fade_in, dur))}")
    if fade_out >= MIN_FADE:
        filters.append(f"{name}=t=out:st={num(max(dur - fade_out, 0))}:d={num(min(fade_out, dur))}")
    return filters


def _fit(fmt: str, width: int, height: int) -> str:
    if fmt == "social":
        return f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={width}:{height}"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )


def audible(doc: Mapping[str, Any]) -> List[Tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """The audio items heard in the mix with their lane: muted lanes left out, soloed lanes alone when any is."""
    lanes = {lane["id"]: lane for lane in doc.get("lanes") or []}
    soloed = any(lane.get("solo") for lane in lanes.values())
    playing = []
    for item in doc.get("audio") or []:
        lane = lanes.get(item.get("lane")) or {}
        if lane.get("mute") or (soloed and not lane.get("solo")) or float(item.get("dur") or 0) <= EPSILON:
            continue
        playing.append((item, lane))
    return playing


def reach(path: Any, cwd: Optional[str] = None) -> str:
    """How ffmpeg is told to open a file: its path, or, from the working folder cwd, its path relative to it behind ./ so that no name reads as an option or as a protocol."""
    text = str(path)
    if cwd is None:
        return text
    try:
        return os.path.join(os.curdir, os.path.relpath(text, cwd))
    except ValueError:
        return text


def common_folder(paths: Iterable[Any]) -> Optional[str]:
    """The deepest folder that holds all these files, or None when they do not sit on one drive."""
    folders = [os.path.dirname(os.path.abspath(str(path))) for path in paths]
    try:
        return os.path.commonpath(folders) if folders else None
    except ValueError:
        return None


def _source_length(doc: Mapping[str, Any], clip: Mapping[str, Any], lengths: Mapping[str, Any]) -> Optional[float]:
    length = lengths.get(clip["id"])
    if length is None:
        length = (asset_of(doc, clip.get("assetId")) or {}).get("srcDur")
    if isinstance(length, bool) or not isinstance(length, (int, float)) or not length > 0:
        return None
    return float(length)


def _assembly(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    sounds: Mapping[str, str],
    cwd: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    fmt, resolution = options["format"], options["resolution"]
    width, height = frame_size(doc, fmt, resolution)
    rate = fps_of(doc)
    fps = num(rate)
    clip_audio, stills = options.get("audio") or {}, set(options.get("stills") or ())
    blind, lengths = set(options.get("blind") or ()), options.get("lengths") or {}
    inputs: List[str] = []
    graph: List[str] = []
    pairs: List[str] = []
    reading: Dict[str, Tuple[int, float]] = {}
    count = 0

    def add_input(path: str, still_for: Optional[float] = None) -> int:
        nonlocal count
        if still_for is not None:
            inputs.extend(["-loop", "1", "-framerate", fps, "-t", num(still_for)])
        inputs.extend(["-i", reach(path, cwd)])
        count += 1
        return count - 1

    def shot_input(path: str, start: float, end: float) -> int:
        """The input of a shot's file: the one already open when the shot reads on from where the last one stopped, else a new one, so that ffmpeg never holds the frames of later cuts in memory."""
        last = reading.get(path)
        index = last[0] if last is not None and start >= last[1] - EPSILON else add_input(path)
        reading[path] = (index, end)
        return index

    segments, _ = timeline(doc)
    for index, (dur, clip) in enumerate(segments):
        entry = files.get(clip["id"]) if clip is not None else None
        length = num(dur)
        black = f"color=c=black:s={width}x{height}:r={fps}:d={length},setsar=1,format=yuv420p[v{index}]"
        silence = f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length}[a{index}]"
        start = float(clip.get("srcIn") or 0) if clip is not None else 0.0
        still = entry is not None and clip["id"] in stills
        source_end = None if entry is None or still else _source_length(doc, clip, lengths)
        sound = entry is not None and not still and bool(clip_audio.get(clip["id"]))
        if source_end is not None and start >= source_end - EPSILON:
            entry = None
        elif entry is not None and clip["id"] in blind and not sound:
            entry = None
        if entry is None:
            graph.append(black)
            graph.append(silence)
        else:
            source = add_input(entry["path"], start + dur) if still else shot_input(entry["path"], start, start + dur)
            if clip["id"] in blind:
                graph.append(black)
            else:
                # one frame of slack: a file can end a frame before its probed length
                pad = dur if source_end is None else min(dur, max(start + dur - source_end, 0.0) + 1 / rate)
                video = [
                    f"trim=start={num(start)}:duration={length}",
                    "setpts=PTS-STARTPTS",
                    f"fps={fps}",
                    _fit(fmt, width, height),
                    "setsar=1",
                    "format=yuv420p",
                    f"tpad=stop_mode=clone:stop_duration={num(pad)}",
                    f"trim=duration={length}",
                    *_look(clip),
                    *_fades(clip, dur, "fade"),
                ]
                graph.append(f"[{source}:v]{','.join(video)}[v{index}]")
            if sound:
                graph.append(
                    f"[{source}:a]atrim=start={num(start)}:duration={length},asetpts=PTS-STARTPTS,"
                    f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"apad=whole_dur={length},atrim=duration={length}[a{index}]"
                )
            else:
                graph.append(silence)
        pairs.append(f"[v{index}][a{index}]")
    graph.append(f"{''.join(pairs)}concat=n={len(segments)}:v=1:a=1[vout][bed]")
    mixed: List[str] = []
    for item, lane in audible(doc):
        if item["id"] not in sounds:
            continue
        dur = float(item["dur"])
        source = add_input(sounds[item["id"]])
        gain = float(item.get("gain") or 0) + float(lane.get("vol") or 0)
        chain = [
            f"atrim=start={num(item.get('srcIn') or 0)}:duration={num(dur)}",
            "asetpts=PTS-STARTPTS",
            f"aresample={SAMPLE_RATE}",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
            f"volume={num(gain)}dB",
            *_fades(item, dur, "afade"),
            f"adelay=delays={round(float(item.get('start') or 0) * 1000)}:all=1",
        ]
        graph.append(f"[{source}:a]{','.join(chain)}[m{len(mixed)}]")
        mixed.append(f"[m{len(mixed)}]")
    if mixed:
        graph.append(f"[bed]{''.join(mixed)}amix=inputs={len(mixed) + 1}:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        graph.append("[bed]anull[aout]")
    return inputs, graph


def filter_graph(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> str:
    """The filter graph that assembles, grades, fades and mixes the sequence: the text of the file build_command's run reads."""
    return ";".join(_assembly(doc, files, options, paths.get("audio") or {})[1])


def build_command(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> List[str]:
    """The one ffmpeg run that writes the mezzanine file, its filter graph read from the file at paths["graph"]; with paths["cwd"], run from that folder, the input files are named relative to it."""
    cwd = paths.get("cwd")
    inputs, _ = _assembly(doc, files, options, paths.get("audio") or {}, cwd)
    _, total = timeline(doc)
    return [
        paths["ffmpeg"], "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *inputs,
        "-filter_complex_script", str(paths["graph"]),
        "-map", "[vout]", "-map", "[aout]",
        "-t", num(total), "-r", num(fps_of(doc)),
        *ENCODER,
        str(paths["output"]),
    ]


def _progress_seconds(line: str) -> Optional[float]:
    key, _, value = line.partition("=")
    if key not in ("out_time_us", "out_time_ms"):
        return None
    try:
        return int(value) / 1_000_000
    except ValueError:
        return None


def kill_tree(process: Any) -> bool:
    """Kill an ffmpeg process and every process it started, as a launcher that runs the real ffmpeg as a child needs; False when it had already ended."""
    if process.returncode is not None:
        return False
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        children = []
    for child in children:
        try:
            child.kill()
        except psutil.Error:
            pass
    try:
        process.kill()
    except (ProcessLookupError, PermissionError):
        return False
    return True


async def assemble(
    command: Sequence[str],
    total: float,
    on_progress: Optional[Callable[[float], Any]] = None,
    on_process: Optional[Callable[[Any], Any]] = None,
    cwd: Optional[str] = None,
) -> None:
    """Run the assembly from the folder cwd, reporting the share of the running time written; raises ExportError(ffmpeg_failed)."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )
    except OSError as exc:
        raise ExportError("ffmpeg_failed", last_line(str(exc)) or "ffmpeg could not start.") from exc
    if on_process is not None:
        on_process(process)
    errors = asyncio.ensure_future(process.stderr.read())
    try:
        async for raw in process.stdout:
            seconds = _progress_seconds(raw.decode("utf-8", "replace").strip())
            if seconds is not None and on_progress is not None and total > 0:
                on_progress(min(max(seconds / total, 0.0), 1.0))
        code = await process.wait()
        stderr = (await errors).decode("utf-8", "replace")
    finally:
        if on_process is not None:
            on_process(None)
        kill_tree(process)
    if code != 0:
        raise ExportError("ffmpeg_failed", last_line(stderr) or f"ffmpeg stopped with code {code}.")


async def discard(path: Path) -> bool:
    """Delete a work file, trying again for a moment when another program holds it open; False when it stays."""
    for attempt in range(DISCARD_TRIES):
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            if attempt + 1 < DISCARD_TRIES:
                await asyncio.sleep(DISCARD_PAUSE)
    logger.info("[VIDEO-PRODUCER] Could not delete %s; the export cache sweep takes it later", path)
    return False


async def discard_work(folder: Path) -> None:
    """Delete what only the assembly needs: the filter graph and the local copies of the sources."""
    for path in [folder / GRAPH, *folder.glob(f"{core_bridge.SOURCE_PREFIX}*")]:
        await discard(path)


def transcode(mezzanine: Path, final: Path, size: Tuple[int, int], fps: Any) -> Any:
    """The delivery file from the mezzanine, by the host's converter: MP4 H.264 with its audio."""
    spec = TranscodeSpec(container="mp4", max_width=size[0], fps=float(fps), keep_audio=True)
    return core_bridge.transcode_video(mezzanine, final, spec)


def folder_size(path: Path) -> int:
    """The bytes of every file under a folder."""
    total = 0
    for root, _, names in os.walk(path):
        for name in names:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def inspect(shots: Mapping[str, Optional[Mapping[str, Any]]]) -> Dict[str, Any]:
    """What ffprobe reads of the shots' files, each file once: the shots with sound, the shots without picture, the length of each source."""
    probing = core_bridge.find_ffprobe() is not None
    probes: Dict[str, Any] = {}
    audio: Dict[str, bool] = {}
    blind: List[str] = []
    lengths: Dict[str, float] = {}
    for clip_id, entry in shots.items():
        if entry is None or entry.get("still"):
            continue
        path = str(entry["path"])
        if probing and path not in probes:
            probes[path] = core_bridge.probe_video(Path(path))
        probe = probes.get(path)
        if probe is not None and probe.duration > 0:
            lengths[clip_id] = float(probe.duration)
        if entry.get("sound") or (probing and probe is None):
            blind.append(clip_id)
            audio[clip_id] = probe is None or bool(probe.has_audio)
        else:
            audio[clip_id] = bool(probe and probe.has_audio)
    return {"audio": audio, "blind": blind, "lengths": lengths}


async def render(
    job: Mapping[str, Any],
    project: Mapping[str, Any],
    owner: User,
    requester: User,
    report: Callable[[float, str], bool],
    on_process: Optional[Callable[[Any], Any]] = None,
) -> Dict[str, Any]:
    """Assemble, transcode and store one export; returns its file and library item, raises ExportError."""
    doc = project["doc"]
    untimed = timing_error(doc)
    if untimed is not None:
        raise ExportError("ffmpeg_failed", untimed)
    folder = job_folder(job)
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise ExportError("ffmpeg_failed", "ffmpeg is not available on this server.")
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    resolver = media.Resolver(owner)
    size = frame_size(doc, job["format"], job["resolution"])
    mezzanine, final = folder / MEZZANINE, folder / file_name(project["name"], job["resolution"])
    try:
        shots, sounds = await asyncio.to_thread(media.local_inputs, doc, takes.list_takes(project["id"]), resolver, folder)
        if not any(shots.values()):
            raise ExportError("ffmpeg_failed", "No shot of the sequence has a file to assemble.")
        options = {
            "format": job["format"],
            "resolution": job["resolution"],
            "stills": [clip_id for clip_id, entry in shots.items() if entry is not None and entry["still"]],
            **await asyncio.to_thread(inspect, shots),
        }
        paths = {"ffmpeg": ffmpeg, "output": str(mezzanine), "graph": str(folder / GRAPH), "audio": sounds}
        sources = [entry["path"] for entry in shots.values() if entry is not None] + list(sounds.values())
        paths["cwd"] = common_folder(sources)
        Path(paths["graph"]).write_text(filter_graph(doc, shots, options, paths), encoding="utf-8")
        command = build_command(doc, shots, options, paths)
        _, total = timeline(doc)

        def assembled(share: float) -> None:
            progress = share * ASSEMBLE_SHARE
            report(progress, "mix" if progress >= MIX_FROM else "assemble")

        if not report(0, "assemble"):
            raise cancelled()
        await assemble(command, total, assembled, on_process, paths["cwd"])
    finally:
        await discard_work(folder)
    if not report(ASSEMBLE_SHARE, "transcode"):
        raise cancelled()
    try:
        await asyncio.to_thread(transcode, mezzanine, final, size, fps_of(doc))
    except VideoTranscodeError as exc:
        raise ExportError("transcode_failed", last_line(str(exc)) or "The video could not be converted.") from exc
    await discard(mezzanine)
    if not report(TRANSCODE_END, "store"):
        raise cancelled()
    try:
        stored = await core_bridge.save_user_media(requester, final)
        item = core_bridge.upload_item(requester.id, stored["value"]) or {}
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] Could not store export %s in the library", job["id"], exc_info=True)
        raise ExportError("store_failed", last_line(str(exc)) or "The video could not be stored in the library.") from exc
    return {
        "file_name": final.name,
        "file_size": final.stat().st_size,
        "media_item_id": item.get("item_id"),
        "media_url": f"/api/media/uploads/{media.basename(stored['value'])}",
    }
