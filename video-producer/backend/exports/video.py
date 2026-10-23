import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import psutil

from .. import core_bridge, director, takes
from ..core_bridge import User
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

PART_NAME = "part-{}-{}.mkv"

PART_GRAPH = "graph-{}-{}.txt"

LANES_NAME = "lanes-{}.wav"

LANES_GRAPH = "graph-lanes-{}.txt"

DISCARD_TRIES = 5

DISCARD_PAUSE = 0.2

GRAPH_OPTION = "-/filter_complex"

LEGACY_GRAPH_OPTION = "-filter_complex_script"

GRAPH_OPTION_SINCE = 7

VERSION_TIMEOUT = 15

RELEASE = re.compile(r"\bversion\s+n?(\d+)")

DECODER_THREADS = 4

PART_INPUTS = 40

MIX_INPUTS = 200

STALL_SECONDS = 300

STALL_POLL = 5.0

VIDEO_ENCODER = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p")

AUDIO_LAYOUT = ("-ar", str(SAMPLE_RATE), "-ac", "2")

ENCODER = (*VIDEO_ENCODER, "-c:a", "aac", "-b:a", "192k", *AUDIO_LAYOUT, "-movflags", "+faststart")

PART_ENCODER = (*VIDEO_ENCODER, "-c:a", "pcm_f32le", *AUDIO_LAYOUT)

LANES_ENCODER = ("-c:a", "pcm_f32le", *AUDIO_LAYOUT)

DELIVERY = (
    "-c:v", "libx264", "-crf", "26", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "96k", "-f", "mp4",
)

Segment = Tuple[float, Optional[Mapping[str, Any]]]


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


def timeline(doc: Mapping[str, Any]) -> Tuple[List[Segment], float]:
    """The shots in document order with black where nothing plays, and the running time of the sequence."""
    segments: List[Segment] = []
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


def video_track(doc: Mapping[str, Any]) -> Dict[str, bool]:
    """The mute and solo of the video track, both off when the document has none."""
    video = doc.get("video")
    video = video if isinstance(video, Mapping) else {}
    return {"mute": video.get("mute") is True, "solo": video.get("solo") is True}


def any_solo(doc: Mapping[str, Any]) -> bool:
    """Whether a track is soloed, the video track counted with the audio lanes."""
    return video_track(doc)["solo"] or any(lane.get("solo") is True for lane in doc.get("lanes") or [])


def clip_heard(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> bool:
    """Whether a shot's own sound is in the mix: neither the video track nor the shot muted, and the video track soloed when any track is."""
    video = video_track(doc)
    return not video["mute"] and not clip.get("mute") and (not any_solo(doc) or video["solo"])


def audible(doc: Mapping[str, Any]) -> List[Tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """The audio items heard in the mix with their lane: items of a missing or muted lane left out, soloed lanes alone when any track is, the video track included."""
    lanes = {lane["id"]: lane for lane in doc.get("lanes") or []}
    soloed = any_solo(doc)
    playing = []
    for item in doc.get("audio") or []:
        lane = lanes.get(item.get("lane"))
        if lane is None or lane.get("mute") or (soloed and not lane.get("solo")) or float(item.get("dur") or 0) <= EPSILON:
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


@dataclass(frozen=True)
class Shot:
    """What one segment of the timeline plays: the file entry (None for black), where it starts in its source, whether it is a still, the length of its source, whether its sound is heard and whether its picture is."""

    dur: float
    clip: Optional[Mapping[str, Any]]
    entry: Optional[Mapping[str, Any]]
    start: float
    still: bool
    source_end: Optional[float]
    sound: bool
    blind: bool


def _shots(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    segments: Sequence[Segment],
) -> List[Shot]:
    clip_audio, stills = options.get("audio") or {}, set(options.get("stills") or ())
    blind, lengths = set(options.get("blind") or ()), options.get("lengths") or {}
    shots = []
    for dur, clip in segments:
        entry = files.get(clip["id"]) if clip is not None else None
        start = float(clip.get("srcIn") or 0) if clip is not None else 0.0
        still = entry is not None and clip["id"] in stills
        source_end = None if entry is None or still else _source_length(doc, clip, lengths)
        sound = entry is not None and not still and bool(clip_audio.get(clip["id"])) and clip_heard(doc, clip)
        if source_end is not None and start >= source_end - EPSILON:
            entry = None
        elif entry is not None and clip["id"] in blind and not sound:
            entry = None
        shots.append(Shot(dur, clip, entry, start, still, source_end, sound, clip is not None and clip["id"] in blind))
    return shots


class _Inputs:
    """The inputs of one ffmpeg run: a shot's file opened once while the shots read on through it, so that ffmpeg never holds the frames of later cuts in memory, and every picture decoder held to DECODER_THREADS threads."""

    def __init__(self, fps: str = "1", cwd: Optional[str] = None):
        self.fps = fps
        self.cwd = cwd
        self.args: List[str] = []
        self.count = 0
        self.reading: Dict[str, Tuple[int, float]] = {}

    def opens(self, shot: Shot) -> bool:
        """Whether the shot needs an input of its own."""
        if shot.entry is None:
            return False
        if shot.still:
            return True
        last = self.reading.get(shot.entry["path"])
        return last is None or shot.start < last[1] - EPSILON

    def add(self, path: Any, still_for: Optional[float] = None, picture: bool = True) -> int:
        if picture:
            self.args.extend(["-threads", str(DECODER_THREADS)])
        if still_for is not None:
            self.args.extend(["-loop", "1", "-framerate", self.fps, "-t", num(still_for)])
        self.args.extend(["-i", reach(path, self.cwd)])
        self.count += 1
        return self.count - 1

    def sound(self, path: Any) -> int:
        return self.add(path, picture=False)

    def shot(self, shot: Shot) -> int:
        path = shot.entry["path"]
        if shot.still:
            return self.add(path, shot.start + shot.dur)
        index = self.add(path) if self.opens(shot) else self.reading[path][0]
        self.reading[path] = (index, shot.start + shot.dur)
        return index


def _lanes(doc: Mapping[str, Any], sounds: Mapping[str, str], inputs: _Inputs) -> Tuple[List[str], List[str]]:
    """The chains of the audio items heard in the mix, each from its own input, and their labels."""
    chains: List[str] = []
    labels: List[str] = []
    for item, lane in audible(doc):
        if item["id"] not in sounds:
            continue
        dur = float(item["dur"])
        source = inputs.sound(sounds[item["id"]])
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
        label = f"[m{len(labels)}]"
        chains.append(f"[{source}:a]{','.join(chain)}{label}")
        labels.append(label)
    return chains, labels


def _assembly(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    sounds: Mapping[str, str],
    cwd: Optional[str] = None,
    segments: Optional[Sequence[Segment]] = None,
    mix: bool = True,
) -> Tuple[List[str], List[str]]:
    fmt, resolution = options["format"], options["resolution"]
    width, height = frame_size(doc, fmt, resolution)
    rate = fps_of(doc)
    fps = num(rate)
    inputs = _Inputs(fps, cwd)
    graph: List[str] = []
    pairs: List[str] = []
    shots = _shots(doc, files, options, timeline(doc)[0] if segments is None else segments)
    for index, shot in enumerate(shots):
        length = num(shot.dur)
        black = f"color=c=black:s={width}x{height}:r={fps}:d={length},setsar=1,format=yuv420p[v{index}]"
        silence = f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length}[a{index}]"
        if shot.entry is None:
            graph.append(black)
            graph.append(silence)
        else:
            source = inputs.shot(shot)
            if shot.blind:
                graph.append(black)
            else:
                # one frame of slack: a file can end a frame before its probed length
                pad = shot.dur if shot.source_end is None else min(shot.dur, max(shot.start + shot.dur - shot.source_end, 0.0) + 1 / rate)
                video = [
                    f"trim=start={num(shot.start)}:duration={length}",
                    "setpts=PTS-STARTPTS",
                    f"fps={fps}",
                    _fit(fmt, width, height),
                    "setsar=1",
                    "format=yuv420p",
                    f"tpad=stop_mode=clone:stop_duration={num(pad)}",
                    f"trim=duration={length}",
                    *_look(shot.clip),
                    *_fades(shot.clip, shot.dur, "fade"),
                ]
                graph.append(f"[{source}:v]{','.join(video)}[v{index}]")
            if shot.sound:
                graph.append(
                    f"[{source}:a]atrim=start={num(shot.start)}:duration={length},asetpts=PTS-STARTPTS,"
                    f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"apad=whole_dur={length},atrim=duration={length}{''.join(',' + fade for fade in _fades(shot.clip, shot.dur, 'afade'))}[a{index}]"
                )
            else:
                graph.append(silence)
        pairs.append(f"[v{index}][a{index}]")
    graph.append(f"{''.join(pairs)}concat=n={len(shots)}:v=1:a=1[vout][{'bed' if mix else 'aout'}]")
    if not mix:
        return inputs.args, graph
    chains, labels = _lanes(doc, sounds, inputs)
    graph.extend(chains)
    if labels:
        graph.append(f"[bed]{''.join(labels)}amix=inputs={len(labels) + 1}:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        graph.append("[bed]anull[aout]")
    return inputs.args, graph


def plan_parts(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    segments: Sequence[Segment],
    limit: Optional[int] = None,
) -> List[List[Segment]]:
    """The segments cut into runs of consecutive segments that each open at most limit inputs (PART_INPUTS by default); one run when the whole sequence does."""
    limit = PART_INPUTS if limit is None else limit
    groups: List[List[Segment]] = []
    current: List[Segment] = []
    inputs = _Inputs()
    for segment, shot in zip(segments, _shots(doc, files, options, segments)):
        if current and inputs.opens(shot) and inputs.count >= limit:
            groups.append(current)
            current, inputs = [], _Inputs()
        if shot.entry is not None:
            inputs.shot(shot)
        current.append(segment)
    groups.append(current)
    return groups


def _rounds(groups: int, limit: Optional[int] = None) -> int:
    """How many rounds of part runs a sequence cut into that many groups takes before one run can join them."""
    limit = PART_INPUTS if limit is None else limit
    rounds = 0
    while groups > 1:
        rounds += 1
        groups = -(-groups // limit)
    return rounds


def filter_graph(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> str:
    """The filter graph that assembles, grades, fades and mixes the sequence in one run: the text of the file build_command's run reads."""
    return ";".join(_assembly(doc, files, options, paths.get("audio") or {})[1])


def graph_option_of(banner: str) -> str:
    """The option that reads a filter graph from a file, by the first line of what ffmpeg -version prints: -filter_complex_script before FFmpeg 7, which FFmpeg 9 removed, else -/filter_complex; a version that is not a release number, as a git build's, is a recent one."""
    release = RELEASE.search(str(banner or "").partition("\n")[0])
    if release is not None and int(release.group(1)) < GRAPH_OPTION_SINCE:
        return LEGACY_GRAPH_OPTION
    return GRAPH_OPTION


_graph_options: Dict[str, str] = {}


def graph_option(ffmpeg: str) -> str:
    """The option that reads a filter graph from a file for this ffmpeg executable, asked of it once; the recent option when it does not answer."""
    known = _graph_options.get(ffmpeg)
    if known is not None:
        return known
    try:
        run = subprocess.run([ffmpeg, "-version"], stdin=subprocess.DEVNULL, capture_output=True, timeout=VERSION_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return GRAPH_OPTION
    if run.returncode != 0:
        return GRAPH_OPTION
    option = graph_option_of(run.stdout.decode("utf-8", "replace"))
    _graph_options[ffmpeg] = option
    return option


def _command(
    paths: Mapping[str, Any],
    inputs: Sequence[str],
    encoder: Sequence[str],
    total: Optional[float] = None,
    fps: Any = None,
    maps: Sequence[str] = ("[vout]", "[aout]"),
) -> List[str]:
    return [
        paths["ffmpeg"], "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *inputs,
        paths.get("graph_option") or LEGACY_GRAPH_OPTION, str(paths["graph"]),
        *[argument for label in maps for argument in ("-map", label)],
        *(["-t", num(total)] if total is not None else []),
        *(["-r", num(fps)] if fps is not None else []),
        *encoder,
        str(paths["output"]),
    ]


def build_command(
    doc: Mapping[str, Any],
    files: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> List[str]:
    """The one ffmpeg run that writes the mezzanine file, its filter graph read from the file at paths["graph"] by the option paths["graph_option"] (-filter_complex_script when absent); with paths["cwd"], run from that folder, the input files are named relative to it."""
    inputs, _ = _assembly(doc, files, options, paths.get("audio") or {}, paths.get("cwd"))
    _, total = timeline(doc)
    return _command(paths, inputs, ENCODER, total, fps_of(doc))


def convert_command(ffmpeg: str, mezzanine: Path, final: Path, size: Tuple[int, int], fps: Any) -> List[str]:
    """The ffmpeg run that writes the delivery file from the mezzanine with the host converter's settings: H.264 at crf 26 with the slow preset, AAC at 96 kb/s, an MP4 that plays while it downloads."""
    rate = num(fps)
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", str(mezzanine), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale='min({size[0]},iw)':-2:flags=lanczos,fps={rate}", "-r", rate, "-map_metadata", "-1",
        *DELIVERY, str(final),
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
    code: str = "ffmpeg_failed",
) -> None:
    """Run one ffmpeg command from the folder cwd, reporting the share of the running time written; raises ExportError(code) when it fails, and kills it when it writes nothing new for STALL_SECONDS more than a second before the end."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )
    except OSError as exc:
        raise ExportError(code, last_line(str(exc)) or "ffmpeg could not start.") from exc
    if on_process is not None:
        on_process(process)
    errors = asyncio.ensure_future(process.stderr.read())
    loop = asyncio.get_running_loop()
    reached, moved, stalled = 0.0, loop.time(), False
    try:
        while True:
            try:
                raw = await asyncio.wait_for(process.stdout.readline(), STALL_POLL)
            except asyncio.TimeoutError:
                raw = None
            if raw == b"":
                break
            seconds = _progress_seconds(raw.decode("utf-8", "replace").strip()) if raw else None
            if seconds is not None and seconds > reached:
                reached, moved = seconds, loop.time()
                if on_progress is not None and total > 0:
                    on_progress(min(max(seconds / total, 0.0), 1.0))
            elif reached + 1.0 < total and loop.time() - moved > STALL_SECONDS:
                stalled = kill_tree(process)
                break
        returncode = await process.wait()
        stderr = (await errors).decode("utf-8", "replace")
    finally:
        if on_process is not None:
            on_process(None)
        kill_tree(process)
    if stalled:
        raise ExportError(code, f"ffmpeg wrote nothing new for {num(STALL_SECONDS / 60)} minutes and was stopped.")
    if returncode != 0:
        raise ExportError(code, last_line(stderr) or f"ffmpeg stopped with code {returncode}.")


def _progress(report: Callable[[float, str], bool], start: float, width: float, ceiling: float = ASSEMBLE_SHARE) -> Callable[[float], None]:
    """Report the share of one ffmpeg run as the progress from start over width, at most ceiling; the mix step from MIX_FROM on."""

    def advance(share: float) -> None:
        progress = min(start + share * width, ceiling)
        report(progress, "mix" if progress >= MIX_FROM else "assemble")

    return advance


def _step(report: Callable[[float, str], bool], progress: float) -> None:
    if not report(progress, "mix" if progress >= MIX_FROM else "assemble"):
        raise cancelled()


async def _premix(
    doc: Mapping[str, Any],
    sounds: Mapping[str, str],
    paths: Mapping[str, Any],
    folder: Path,
    total: float,
    on_process: Optional[Callable[[Any], Any]],
) -> Tuple[Mapping[str, Any], Mapping[str, str]]:
    """The document and sounds the last run mixes: as they are with at most MIX_INPUTS audio items, else each run of that many items mixed first into a file of its own, heard as one item."""
    playing = [item for item, _ in audible(doc) if item["id"] in sounds]
    if len(playing) <= MIX_INPUTS:
        return doc, sounds
    cwd = common_folder([sounds[item["id"]] for item in playing])
    mixes: Dict[str, str] = {}
    for number, first in enumerate(range(0, len(playing), MIX_INPUTS)):
        group = {**doc, "audio": playing[first:first + MIX_INPUTS]}
        inputs = _Inputs(cwd=cwd)
        chains, labels = _lanes(group, sounds, inputs)
        mix = "anull" if len(labels) == 1 else f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0"
        graph = folder / LANES_GRAPH.format(number)
        graph.write_text(";".join([*chains, f"{''.join(labels)}{mix}[aout]"]), encoding="utf-8")
        output = folder / LANES_NAME.format(number)
        run = {**paths, "graph": str(graph), "output": str(output)}
        await assemble(_command(run, inputs.args, LANES_ENCODER, total, maps=("[aout]",)), total, None, on_process, cwd)
        mixes[f"lanes-{number}"] = str(output)
    items = [{"id": key, "lane": "lanes", "start": 0, "dur": total, "srcIn": 0, "gain": 0} for key in mixes]
    return {**doc, "lanes": [{"id": "lanes", "vol": 0, "solo": any_solo(doc)}], "audio": items}, mixes


async def _part_length(path: Path, nominal: float) -> float:
    probe = await asyncio.to_thread(core_bridge.probe_video, path) if core_bridge.find_ffprobe() else None
    return float(probe.duration) if probe is not None and probe.duration > 0 else nominal


async def assemble_sequence(
    doc: Mapping[str, Any],
    shots: Mapping[str, Optional[Mapping[str, Any]]],
    options: Mapping[str, Any],
    paths: Mapping[str, Any],
    folder: Path,
    report: Callable[[float, str], bool],
    on_process: Optional[Callable[[Any], Any]] = None,
) -> None:
    """Write the mezzanine at paths["output"]: in one ffmpeg run when the sequence opens at most PART_INPUTS inputs, else in parts of consecutive shots that each open at most that many, joined by a last run that mixes the audio items in, so that neither the memory ffmpeg holds per open input nor the length of its command line grows with the sequence."""
    segments, total = timeline(doc)
    fps = fps_of(doc)
    sounds: Mapping[str, str] = paths.get("audio") or {}
    files, picks, cwd = shots, options, paths.get("cwd")
    groups = plan_parts(doc, files, picks, segments)
    rounds = _rounds(len(groups))
    work = max(rounds * total, EPSILON)
    done, level, ceiling = 0.0, 0, MIX_FROM - 0.1
    while len(groups) > 1:
        parts: Dict[str, Mapping[str, Any]] = {}
        lengths: Dict[str, float] = {}
        joined: List[Segment] = []
        for index, group in enumerate(groups):
            start = min(done / work * MIX_FROM, ceiling)
            _step(report, start)
            span = sum(dur for dur, _ in group)
            graph, output = folder / PART_GRAPH.format(level, index), folder / PART_NAME.format(level, index)
            inputs, chains = _assembly(doc, files, picks, {}, cwd, group, mix=False)
            graph.write_text(";".join(chains), encoding="utf-8")
            command = _command({**paths, "graph": str(graph), "output": str(output)}, inputs, PART_ENCODER, fps=fps)
            await assemble(command, span, _progress(report, start, span / work * MIX_FROM, ceiling), on_process, cwd)
            done += span
            key = f"part-{level}-{index}"
            parts[key] = {"name": output.name, "path": str(output), "still": False}
            lengths[key] = await _part_length(output, span)
            joined.append((lengths[key], {"id": key}))
        files, cwd, segments = parts, str(folder), joined
        picks = {**options, "audio": {key: True for key in parts}, "stills": [], "blind": [], "lengths": lengths}
        groups = plan_parts(doc, files, picks, segments)
        level += 1
    start = MIX_FROM if level else 0.0
    if level:
        _step(report, start)
    mix_doc, sounds = await _premix(doc, sounds, paths, folder, total, on_process)
    cwd = common_folder([entry["path"] for entry in files.values() if entry is not None] + list(sounds.values()))
    inputs, chains = _assembly(mix_doc, files, picks, sounds, cwd, segments)
    Path(paths["graph"]).write_text(";".join(chains), encoding="utf-8")
    command = _command(paths, inputs, ENCODER, total, fps)
    await assemble(command, total, _progress(report, start, ASSEMBLE_SHARE - start), on_process, cwd)


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
    """Delete what only the assembly needs: the filter graphs, the parts, the audio premixes and the local copies of the sources."""
    for pattern in ("graph*.txt", "part-*.mkv", "lanes-*.wav", f"{core_bridge.SOURCE_PREFIX}*"):
        for path in folder.glob(pattern):
            await discard(path)


async def convert(
    ffmpeg: str,
    mezzanine: Path,
    final: Path,
    size: Tuple[int, int],
    fps: Any,
    total: float,
    report: Callable[[float, str], bool],
    on_process: Optional[Callable[[Any], Any]] = None,
) -> None:
    """Write the delivery file from the mezzanine, reporting the transcode step from ASSEMBLE_SHARE to TRANSCODE_END; raises ExportError(transcode_failed)."""

    def converted(share: float) -> None:
        report(ASSEMBLE_SHARE + share * (TRANSCODE_END - ASSEMBLE_SHARE), "transcode")

    await assemble(convert_command(ffmpeg, mezzanine, final, size, fps), total, converted, on_process, None, "transcode_failed")
    if not final.exists() or final.stat().st_size == 0:
        raise ExportError("transcode_failed", "ffmpeg wrote an empty video.")


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
    _, total = timeline(doc)
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
        paths = {
            "ffmpeg": ffmpeg,
            "graph_option": await asyncio.to_thread(graph_option, ffmpeg),
            "output": str(mezzanine),
            "graph": str(folder / GRAPH),
            "audio": sounds,
        }
        sources = [entry["path"] for entry in shots.values() if entry is not None] + list(sounds.values())
        paths["cwd"] = common_folder(sources)
        if not report(0, "assemble"):
            raise cancelled()
        await assemble_sequence(doc, shots, options, paths, folder, report, on_process)
    finally:
        await discard_work(folder)
    if not report(ASSEMBLE_SHARE, "transcode"):
        raise cancelled()
    try:
        await convert(ffmpeg, mezzanine, final, size, fps_of(doc), total, report, on_process)
    finally:
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
