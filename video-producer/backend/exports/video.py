import asyncio
import logging
import math
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Collection, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import psutil

from .. import core_bridge, director, takes
from ..core_bridge import User
from . import levels, match, media, slug
from .common import asset_of, fps_of, seq_duration, timing_error
from .mix import RULE as MIX_RULE, delay_taps, gain_of, pan_of, strip_of, write_impulse

logger = logging.getLogger("plugins.video-producer")

FORMATS = ("web", "social", "master", "archive")

LIBRARY_FORMATS = ("web", "social")

EXTENSIONS = {"master": "mov", "web": "mp4", "social": "mp4", "archive": "mp4"}

SUFFIXES = {"archive": "_archive"}

ROLE_STEMS = (("Dialogue", "dialogue"), ("Musique", "music"), ("Ambiance", "ambience"), ("SFX", "sfx"))

SHOTS_STEM = "shots"

STEM_NAMES = (*(name for _, name in ROLE_STEMS), SHOTS_STEM)

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

MEZZANINE = "mezzanine.mkv"

IMPULSE = "reverb.wav"

MIX_STEM = "mix-{}.wav"

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

IMPULSE_OPTION = "irnorm=-1"

LEGACY_IMPULSE_OPTION = "gtype=none"

VERSION_TIMEOUT = 15

RELEASE = re.compile(r"\bversion\s+n?(\d+)")

DECODER_THREADS = 4

PART_INPUTS = 40

MIX_INPUTS = 200

STALL_SECONDS = 300

STALL_POLL = 5.0

VIDEO_ENCODER = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p")

AUDIO_LAYOUT = ("-ar", str(SAMPLE_RATE), "-ac", "2")

ENCODER = (*VIDEO_ENCODER, "-c:a", "pcm_f32le", *AUDIO_LAYOUT)

PART_ENCODER = ENCODER

LANES_ENCODER = ("-c:a", "pcm_f32le", *AUDIO_LAYOUT)

STEM_ENCODER = ("-c:a", "pcm_f32le", *AUDIO_LAYOUT, "-rf64", "auto")

STEM_DELIVERY = ("-c:a", "pcm_s24le", *AUDIO_LAYOUT, "-rf64", "auto")

OPTION_SPECIAL = "\\':"

GRAPH_SPECIAL = "\\'[],;"

CROSSFADE_LIMIT = 2.0

MIN_CROSSFADE = 0.02

CROSSFADE_CURVE = "qsin"

MONO_UP = "pan=stereo|c0=c0|c1=c0"

DELIVERY = (
    "-c:v", "libx264", "-crf", "26", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "96k", "-f", "mp4",
)

MASTER_DELIVERY = (
    "-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le",
    "-c:a", "pcm_s24le", "-f", "mov",
)

ARCHIVE_DELIVERY = (
    "-c:v", "libx265", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1",
    "-x265-params", "log-level=error", "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "256k", "-f", "mp4",
)

DELIVERIES = {"master": MASTER_DELIVERY, "web": DELIVERY, "social": DELIVERY, "archive": ARCHIVE_DELIVERY}

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


def file_name(project_name: str, resolution: str, fmt: str = "web", stems: bool = False) -> str:
    """The name of an export: <slug>_<resolution>.mp4, .mov for the master, _archive.mp4 for the archive, the slug cut to 80 characters; with the stems, <slug>_<resolution>_<format>_stems.zip."""
    base = f"{slug(project_name)[:SLUG_LIMIT].rstrip('._')}_{resolution}"
    return f"{base}_{fmt}_stems.zip" if stems else f"{base}{SUFFIXES.get(fmt, '')}.{EXTENSIONS.get(fmt, 'mp4')}"


def download_name(project_name: str, resolution: str, fmt: str = "web", stems: bool = False) -> str:
    """The name an export downloads under, without its extension: the project's name as it is, then what file_name adds to its slug."""
    return f"{project_name}_{resolution}_{fmt}_stems" if stems else f"{project_name}_{resolution}{SUFFIXES.get(fmt, '')}"


def stem_file(video: str, name: str) -> str:
    """The name of a stem next to the video it goes with: the video's name without its extension, then the stem."""
    return f"{Path(video).stem}_{name}.wav"


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


def _escaped(text: str, special: str) -> str:
    return "".join("\\" + c if c in special else c for c in text)


def filter_value(text: str) -> str:
    """A text as the value of a filter option inside a filter graph: escaped for the option, then for the graph."""
    return _escaped(_escaped(text, OPTION_SPECIAL), GRAPH_SPECIAL)


def filter_path(path: Any, cwd: Optional[str] = None) -> str:
    """A file as the value of a filter option inside a filter graph: named as reach names it, with forward slashes, then escaped for the option and for the graph, so that a drive letter, a quote or a comma reads as part of the name."""
    return filter_value(reach(path, cwd).replace(os.sep, "/"))


def _match(clip: Mapping[str, Any], options: Mapping[str, Any], cwd: Optional[str]) -> List[str]:
    path = (options.get("cubes") or {}).get(clip.get("id"))
    if path is None:
        return []
    return [f"lut3d=file={filter_path(path, cwd)}:interp=trilinear"]


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
    """The audio items heard in the mix with their lane: items of a missing or muted lane, of a lane whose fader is down to silence, or at a gain down to silence, left out, soloed lanes alone when any track is, the video track included."""
    lanes = {lane["id"]: lane for lane in doc.get("lanes") or []}
    soloed = any_solo(doc)
    playing = []
    for item in doc.get("audio") or []:
        lane = lanes.get(item.get("lane"))
        if lane is None or lane.get("mute") or (soloed and not lane.get("solo")) or float(item.get("dur") or 0) <= EPSILON:
            continue
        if gain_of(lane.get("vol")) == 0 or gain_of(item.get("gain")) == 0:
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


def sound_chain(item: Mapping[str, Any], lane: Mapping[str, Any], origin: float = 0.0, seek: float = 0.0, mono: bool = False) -> List[str]:
    """The filters that play an audio item at its place in a mix starting at origin seconds on the timeline: its part of the source, its gain with the volume of the lane given and its fades, the part before origin cut off; a mono source on both channels at its full level when mono is set, as the page's console plays it. Seek is the time of the source its input was sought to: the filters then take the source from there, timed as the whole item."""
    dur = float(item["dur"])
    start = float(item.get("start") or 0)
    gain = float(item.get("gain") or 0) + float(lane.get("vol") or 0)
    skipped = max(origin - start, 0.0)
    src_in = float(item.get("srcIn") or 0)
    head = max(seek - src_in, 0.0) if seek else 0.0
    trim = max(src_in - seek, 0.0) if seek else src_in
    return [
        f"atrim=start={num(trim)}:duration={num(dur - head)}",
        f"asetpts=PTS-STARTPTS+{num(head)}/TB" if head > EPSILON else "asetpts=PTS-STARTPTS",
        f"aresample={SAMPLE_RATE}",
        *([MONO_UP] if mono else []),
        "aformat=sample_fmts=fltp:channel_layouts=stereo",
        f"volume={num(gain)}dB",
        *_fades(item, dur, "afade"),
        *([f"atrim=start={num(skipped)}", "asetpts=PTS-STARTPTS"] if skipped > EPSILON else []),
        f"adelay=delays={round(max(start - origin, 0.0) * 1000)}:all=1",
    ]


def crossfade_of(doc: Mapping[str, Any]) -> float:
    """The length in seconds of the crossfade between neighbouring audio items of a lane, from the master's setting and at most CROSSFADE_LIMIT; 0 for hard cuts."""
    master = doc.get("master")
    value = master.get("crossfade") if isinstance(master, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value >= MIN_CROSSFADE:
        return 0.0
    return min(float(value), CROSSFADE_LIMIT)


@dataclass(frozen=True)
class Heard:
    """An audio item heard in the mix with its lane, the seconds of its source it also plays before and after its own span to crossfade with its neighbours, and the gap to the next one, which it plays on so that the next one starts on time."""

    item: Mapping[str, Any]
    lane: Mapping[str, Any]
    head: float = 0.0
    tail: float = 0.0
    gap: float = 0.0


def _tail_room(doc: Mapping[str, Any], item: Mapping[str, Any]) -> float:
    length = (asset_of(doc, item.get("assetId")) or {}).get("srcDur")
    if isinstance(length, bool) or not isinstance(length, (int, float)) or not length > 0:
        return float("inf")
    return max(float(length) - float(item.get("srcIn") or 0) - float(item["dur"]), 0.0)


def _overlap(doc: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any], fade: float) -> Tuple[float, float]:
    """How much of the source past the cut the item before and the item after play to crossfade: half the crossfade on each side, the rest taken from the other side when one source has too little, the whole at most half of either item."""
    length = min(fade, float(before["dur"]) / 2, float(after["dur"]) / 2)
    head_room, tail_room = max(float(after.get("srcIn") or 0), 0.0), _tail_room(doc, before)
    head = min(length / 2, head_room)
    tail = min(length - head, tail_room)
    return tail, min(length - tail, head_room)


def _gap(before: Mapping[str, Any], after: Mapping[str, Any]) -> float:
    return float(after.get("start") or 0) - float(before.get("start") or 0) - float(before["dur"])


def runs(doc: Mapping[str, Any], sounds: Mapping[str, str]) -> List[List[Heard]]:
    """The audio items heard in the mix that have a file, in runs that crossfade, in the order of their first item: neighbours on one lane, the end of one within half a frame of the start of the next; one item alone when it has no neighbour or the crossfade is off."""
    playing = [(item, lane) for item, lane in audible(doc) if item["id"] in sounds]
    fade = crossfade_of(doc)
    if fade <= 0:
        return [[Heard(item, lane)] for item, lane in playing]
    slack = 0.5 / fps_of(doc)
    by_lane: Dict[str, List[int]] = {}
    for index, (item, _) in enumerate(playing):
        by_lane.setdefault(item["lane"], []).append(index)
    groups: List[List[int]] = []
    for indexes in by_lane.values():
        indexes.sort(key=lambda index: float(playing[index][0].get("start") or 0))
        group = [indexes[0]]
        for index in indexes[1:]:
            before, after = playing[group[-1]][0], playing[index][0]
            if abs(_gap(before, after)) <= slack + EPSILON and sum(_overlap(doc, before, after, fade)) >= MIN_CROSSFADE:
                group.append(index)
            else:
                groups.append(group)
                group = [index]
        groups.append(group)
    groups.sort(key=lambda group: group[0])
    result: List[List[Heard]] = []
    for group in groups:
        sides = [_overlap(doc, playing[a][0], playing[b][0], fade) for a, b in zip(group, group[1:])]
        heads, tails = [0.0] + [head for _, head in sides], [tail for tail, _ in sides] + [0.0]
        gaps = [_gap(playing[a][0], playing[b][0]) for a, b in zip(group, group[1:])] + [0.0]
        result.append([Heard(*playing[index], heads[k], tails[k], gaps[k]) for k, index in enumerate(group)])
    return result


def _crossfaded(run: Sequence[Heard], sources: Sequence[int], label: str, lifts: Sequence[bool] = ()) -> List[str]:
    """The chains of a run of neighbours: each item played with its extra source and without its own fade where it crossfades, at its own gain, a source whose lift is set on both channels, every pair joined by acrossfade, the whole set at the start of its first item."""
    chains: List[str] = []
    name = label.strip("[]")
    last = len(run) - 1
    for k, (heard, source) in enumerate(zip(run, sources)):
        item = heard.item
        dur = float(item["dur"]) + heard.head + heard.tail + heard.gap
        stretched = {
            **item,
            "start": float(item.get("start") or 0) - heard.head,
            "srcIn": float(item.get("srcIn") or 0) - heard.head,
            "dur": dur,
            "fadeIn": item.get("fadeIn") if k == 0 else 0,
            "fadeOut": item.get("fadeOut") if k == last else 0,
        }
        lifted = bool(lifts[k]) if k < len(lifts) else False
        steps = [step for step in sound_chain(stretched, {}, mono=lifted) if not step.startswith("adelay=")]
        chains.append(f"[{source}:a]{','.join([*steps, f'apad=whole_dur={num(dur)}'])}[{name}x{k}]")
    joined = f"[{name}x0]"
    for k in range(1, len(run)):
        length = run[k - 1].tail + run[k].head
        chains.append(f"{joined}[{name}x{k}]acrossfade=d={num(length)}:c1={CROSSFADE_CURVE}:c2={CROSSFADE_CURVE}[{name}j{k}]")
        joined = f"[{name}j{k}]"
    start = float(run[0].item.get("start") or 0)
    chains.append(f"{joined}adelay=delays={round(max(start, 0.0) * 1000)}:all=1{label}")
    return chains


def _lanes(doc: Mapping[str, Any], sounds: Mapping[str, str], inputs: _Inputs, mono: Collection[str] = ()) -> Tuple[List[str], List[str]]:
    """The chains of the audio items heard in the mix, each from its own input at its own gain, its track's volume left to the strip, neighbours crossfaded when the master asks for it, a file among mono on both channels, and their labels, one per run in the order of runs()."""
    chains: List[str] = []
    labels: List[str] = []
    for run in runs(doc, sounds):
        files = [sounds[heard.item["id"]] for heard in run]
        sources = [inputs.sound(path) for path in files]
        lifts = [str(path) in mono for path in files]
        label = f"[m{len(labels)}]"
        if len(run) == 1:
            chains.append(f"[{sources[0]}:a]{','.join(sound_chain(run[0].item, {}, mono=lifts[0]))}{label}")
        else:
            chains.extend(_crossfaded(run, sources, label, lifts))
        labels.append(label)
    return chains, labels


def _pan_terms(left: float, right: float) -> str:
    terms = [f"{num(gain)}*c{channel}" for channel, gain in ((0, left), (1, right)) if num(gain) != "0"]
    return "+".join(terms) or "0*c0"


def strip_filters(strip: Mapping[str, Any], vol: float) -> List[str]:
    """The ffmpeg filters of a track's strip as strip_of describes it, wired as the page's console: the three bands of the equalizer, the low-pass filter, the compressor, the pan and the fader at vol dB; nothing for what leaves the sound as it is."""
    filters: List[str] = []
    for band in ("low", "mid", "high"):
        gain = strip["eq"][band]
        if not gain:
            continue
        spec = MIX_RULE["eq"][band]
        if spec["type"] == "peaking":
            filters.append(f"equalizer=f={num(spec['frequency'])}:t=q:w={num(spec['q'])}:g={num(gain)}")
        else:
            filters.append(f"{spec['type']}=f={num(spec['frequency'])}:t=s:w={num(MIX_RULE['eq']['slope'])}:g={num(gain)}")
    if strip["cutoff"] is not None:
        filters.append(f"lowpass=f={num(strip['cutoff'])}:p=2:t=q:w={num(math.pow(10, MIX_RULE['filter']['qDb'] / 20))}")
    comp = strip["comp"]
    if comp is not None:
        filters.append(
            f"acompressor=threshold={num(math.pow(10, comp['threshold'] / 20))}:ratio={num(comp['ratio'])}"
            f":attack={num(comp['attack'])}:release={num(comp['release'])}:makeup={num(comp['makeup'])}"
            f":knee={num(max(math.pow(10, comp['knee'] / 20), 1.0))}"
            f":detection={MIX_RULE['comp']['detection']}:link={MIX_RULE['comp']['link']}"
        )
    if strip["pan"]:
        gains = pan_of(strip["pan"])
        filters.append(f"pan=stereo|c0={_pan_terms(gains['ll'], gains['rl'])}|c1={_pan_terms(gains['lr'], gains['rr'])}")
    if vol:
        filters.append(f"volume={num(vol)}dB")
    return filters


def _summed(labels: Sequence[str], then: Sequence[str] = ()) -> str:
    """The labels and the filters that sum them, then the filters given: amix when there are several."""
    steps = [f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0"] if len(labels) > 1 else []
    steps.extend(then)
    return f"{''.join(labels)}{','.join(steps or ['anull'])}"


def _with_impulse_option(options: Mapping[str, Any], paths: Mapping[str, Any]) -> Mapping[str, Any]:
    if options.get("impulse_option"):
        return options
    return {**options, "impulse_option": impulse_option_of(paths.get("graph_option") or LEGACY_GRAPH_OPTION)}


def impulse_option_of(graph_option: str) -> str:
    """How afir is told to take the impulse response as it is: gtype=none for an ffmpeg older than 7, which reads its graph with -filter_complex_script, irnorm=-1 since, where gtype became a gain of its own."""
    return LEGACY_IMPULSE_OPTION if graph_option == LEGACY_GRAPH_OPTION else IMPULSE_OPTION


def master_level(doc: Mapping[str, Any]) -> Optional[str]:
    """The filter of the master's fader, None at 0 dB: volume=0 when it is down to silence."""
    master = doc.get("master")
    vol = master.get("vol") if isinstance(master, Mapping) else 0
    if gain_of(vol) == 0:
        return "volume=0"
    return f"volume={num(vol)}dB" if vol else None


def _console(doc: Mapping[str, Any], sounds: Mapping[str, str], inputs: _Inputs, options: Mapping[str, Any]) -> List[str]:
    """The chains that play the audio items through the console as the page does and mix them with the shots' sound at [bed] into [aout]: the items of each track summed over the whole sequence and run through its strip, the tracks of each role summed with what they send to the reverb (afir on the impulse response at options["impulse"]) and to the delay (its echoes unrolled), the roles and the shots' sound summed under the master's fader. With options["stems"], the shots' sound and each role also at [stem_<name>], under the master's fader and as long as the sequence, a role nothing plays in silent."""
    length = num(timeline(doc)[1])
    chains, labels = _lanes(doc, sounds, inputs, set(options.get("mono") or ()))
    tracks: Dict[str, List[str]] = {}
    lanes: Dict[str, Mapping[str, Any]] = {}
    for label, run in zip(labels, runs(doc, sounds)):
        tracks.setdefault(run[0].lane["id"], []).append(label)
        lanes[run[0].lane["id"]] = run[0].lane
    reverb, delay = MIX_RULE["reverb"]["id"], MIX_RULE["delay"]["id"]
    known = {role for role, _ in ROLE_STEMS}
    parts: Dict[str, List[str]] = {}
    sent: Dict[Tuple[str, str], List[str]] = {}
    for n, (lane_id, items) in enumerate(tracks.items()):
        lane = lanes[lane_id]
        strip = strip_of(lane, doc.get("aux"))
        role = lane.get("role") if lane.get("role") in known else ROLE_STEMS[-1][0]
        buses = [bus for bus in (reverb, delay) if strip["sends"][bus] > 0]
        outs = [f"[t{n}]", *(f"[t{n}{bus}]" for bus in buses)]
        steps = [f"apad=whole_dur={length}", f"atrim=duration={length}", *strip_filters(strip, float(lane.get("vol") or 0))]
        chains.append(f"{_summed(items, [*steps, *([f'asplit={len(outs)}'] if buses else [])])}{''.join(outs)}")
        parts.setdefault(role, []).append(f"[t{n}]")
        for bus in buses:
            chains.append(f"[t{n}{bus}]volume={num(20 * math.log10(strip['sends'][bus]))}dB[t{n}{bus}s]")
            sent.setdefault((role, bus), []).append(f"[t{n}{bus}s]")
    wet = [role for role, _ in ROLE_STEMS if (role, reverb) in sent]
    if wet:
        impulse = inputs.sound(options["impulse"])
        responses = [f"[{impulse}:a]"] if len(wet) == 1 else [f"[ir{k}]" for k in range(len(wet))]
        if len(wet) > 1:
            chains.append(f"[{impulse}:a]asplit={len(wet)}{''.join(responses)}")
        option = options.get("impulse_option") or LEGACY_IMPULSE_OPTION
        for role, response in zip(wet, responses):
            name, senders = dict(ROLE_STEMS)[role], sent[(role, reverb)]
            source = senders[0] if len(senders) == 1 else f"[{name}{reverb}in]"
            if len(senders) > 1:
                chains.append(f"{_summed(senders)}{source}")
            chains.append(f"{source}{response}afir={option}[{name}{reverb}]")
            parts[role].append(f"[{name}{reverb}]")
    taps = delay_taps()
    echoes = f"aecho=in_gain=0:out_gain=1:delays={'|'.join(num(tap['seconds'] * 1000) for tap in taps)}:decays={'|'.join(num(tap['gain']) for tap in taps)}"
    for role, name in ROLE_STEMS:
        if (role, delay) in sent:
            chains.append(f"{_summed(sent[(role, delay)], [echoes, f'atrim=duration={length}'])}[{name}{delay}]")
            parts[role].append(f"[{name}{delay}]")
    heard = [(name, parts[role]) for role, name in ROLE_STEMS if parts.get(role)]
    for name, labels in heard:
        chains.append(f"{_summed(labels)}[{name}]")
    level = master_level(doc)
    mains = ["[bed]", *(f"[{name}]" for name, _ in heard)]
    if options.get("stems"):
        playing = {SHOTS_STEM: "[bed]", **{name: f"[{name}]" for name, _ in heard}}
        mains = []
        for name in STEM_NAMES:
            stem = f"[stem_{name}]"
            if name not in playing:
                chains.append(f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length}{stem}")
                continue
            chains.append(f"{playing[name]}asplit=2[{name}m][{name}s]")
            chains.append(f"[{name}s]{','.join([*([level] if level else []), f'apad=whole_dur={length}', f'atrim=duration={length}'])}{stem}")
            mains.append(f"[{name}m]")
        mains.sort(key=lambda label: label != f"[{SHOTS_STEM}m]")
    tail = [level] if level else []
    if len(mains) == 1:
        chains.append(f"{mains[0]}{','.join(tail or ['anull'])}[aout]")
    else:
        chains.append(f"{''.join(mains)}{','.join([f'amix=inputs={len(mains)}:duration=first:dropout_transition=0:normalize=0', *tail])}[aout]")
    return chains


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
    mono = set(options.get("mono") or ())
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
                    *(["deflicker"] if not shot.still and shot.clip.get("deflicker") is True else []),
                    *_match(shot.clip, options, cwd),
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
                lift = f"{MONO_UP}," if str(shot.entry["path"]) in mono else ""
                graph.append(
                    f"[{source}:a]atrim=start={num(shot.start)}:duration={length},asetpts=PTS-STARTPTS,"
                    f"aresample={SAMPLE_RATE},{lift}aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"apad=whole_dur={length},atrim=duration={length}{''.join(',' + fade for fade in _fades(shot.clip, shot.dur, 'afade'))}[a{index}]"
                )
            else:
                graph.append(silence)
        pairs.append(f"[v{index}][a{index}]")
    graph.append(f"{''.join(pairs)}concat=n={len(shots)}:v=1:a=1[vout][{'bed' if mix else 'aout'}]")
    if not mix:
        return inputs.args, graph
    graph.extend(_console(doc, sounds, inputs, options))
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
    return ";".join(_assembly(doc, files, _with_impulse_option(options, paths), paths.get("audio") or {})[1])


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
    inputs, _ = _assembly(doc, files, _with_impulse_option(options, paths), paths.get("audio") or {}, paths.get("cwd"))
    _, total = timeline(doc)
    return _command(paths, inputs, ENCODER, total, fps_of(doc))


def convert_command(
    ffmpeg: str, mezzanine: Path, final: Path, size: Tuple[int, int], fps: Any, audio_filter: Optional[str] = None, fmt: str = "web"
) -> List[str]:
    """The ffmpeg run that writes the delivery file from the mezzanine: for the web and social formats the host converter's settings (H.264 at crf 26 with the slow preset, AAC at 96 kb/s, an MP4 that plays while it downloads), for the master ProRes 422 HQ in 10 bits with 24-bit PCM in a MOV, for the archive H.265 in 10 bits at crf 18 with AAC at 256 kb/s in an MP4; the sound through audio_filter when given."""
    rate = num(fps)
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", str(mezzanine), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale='min({size[0]},iw)':-2:flags=lanczos,fps={rate}", "-r", rate, "-map_metadata", "-1",
        *(["-af", audio_filter] if audio_filter else []),
        *DELIVERIES.get(fmt, DELIVERY), str(final),
    ]


def stems_command(ffmpeg: str, stems: Mapping[str, Path], finals: Mapping[str, Path], gain: float = 0.0) -> List[str]:
    """The ffmpeg run that writes each stem of the mezzanine as a 24-bit WAV, at the gain in dB the loudness target gave the mix, so that the stems still add up to its sound."""
    command = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    for path in stems.values():
        command.extend(["-i", str(path)])
    for index, name in enumerate(stems):
        command.extend(["-map", f"{index}:a:0", *(["-af", f"volume={num(gain)}dB"] if gain else []), *STEM_DELIVERY, str(finals[name])])
    return command


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
) -> str:
    """Run one ffmpeg command from the folder cwd, reporting the share of the running time written, and return what it wrote on stderr; raises ExportError(code) when it fails, and kills it when it writes nothing new for STALL_SECONDS more than a second before the end."""
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
    return stderr


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
    mono: Collection[str] = (),
) -> Tuple[Mapping[str, Any], Mapping[str, str]]:
    """The document and sounds the last run mixes: as they are with at most MIX_INPUTS audio items, else the items of each track mixed first, in batches of at most that many, into files of their own, each heard as one item of its track, so that the strip of the track still plays them; a run of crossfading neighbours kept in one batch unless it alone is longer."""
    playing = [item for item, _ in audible(doc) if item["id"] in sounds]
    if len(playing) <= MIX_INPUTS:
        return doc, sounds
    cwd = common_folder([sounds[item["id"]] for item in playing])
    tracks: Dict[str, List[List[Mapping[str, Any]]]] = {}
    for run in runs(doc, sounds):
        batches = tracks.setdefault(run[0].lane["id"], [[]])
        for piece in [run] if len(run) <= MIX_INPUTS else [[heard] for heard in run]:
            if len(batches[-1]) + len(piece) > MIX_INPUTS:
                batches.append([])
            batches[-1].extend(heard.item for heard in piece)
    mixes: Dict[str, str] = {}
    items: List[Dict[str, Any]] = []
    for lane_id, batch in [(lane_id, batch) for lane_id, batches in tracks.items() for batch in batches]:
        number = len(mixes)
        group = {**doc, "audio": batch}
        inputs = _Inputs(cwd=cwd)
        chains, labels = _lanes(group, sounds, inputs, set(mono))
        summed = "anull" if len(labels) == 1 else f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0"
        graph = folder / LANES_GRAPH.format(number)
        graph.write_text(";".join([*chains, f"{''.join(labels)}{summed}[aout]"]), encoding="utf-8")
        output = folder / LANES_NAME.format(number)
        run = {**paths, "graph": str(graph), "output": str(output)}
        await assemble(_command(run, inputs.args, LANES_ENCODER, total, maps=("[aout]",)), total, None, on_process, cwd)
        mixes[f"lanes-{number}"] = str(output)
        items.append({"id": f"lanes-{number}", "lane": lane_id, "start": 0, "dur": total, "srcIn": 0, "gain": 0})
    return {**doc, "audio": items}, mixes


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
) -> Dict[str, Path]:
    """Write the mezzanine at paths["output"]: in one ffmpeg run when the sequence opens at most PART_INPUTS inputs, else in parts of consecutive shots that each open at most that many, joined by a last run that mixes the audio items in, so that neither the memory ffmpeg holds per open input nor the length of its command line grows with the sequence. With options["stems"], the last run also writes each stem in the folder; returns their files by name."""
    segments, total = timeline(doc)
    fps = fps_of(doc)
    sounds: Mapping[str, str] = paths.get("audio") or {}
    options = _with_impulse_option(options, paths)
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
    mix_doc, sounds = await _premix(doc, sounds, paths, folder, total, on_process, options.get("mono") or ())
    cwd = common_folder([entry["path"] for entry in files.values() if entry is not None] + list(sounds.values()))
    inputs, chains = _assembly(mix_doc, files, picks, sounds, cwd, segments)
    Path(paths["graph"]).write_text(";".join(chains), encoding="utf-8")
    stems = {name: folder / MIX_STEM.format(name) for name in STEM_NAMES} if options.get("stems") else {}
    command = _command(paths, inputs, ENCODER, total, fps)
    for name, path in stems.items():
        command.extend(["-map", f"[stem_{name}]", "-t", num(total), *STEM_ENCODER, str(path)])
    await assemble(command, total, _progress(report, start, ASSEMBLE_SHARE - start), on_process, cwd)
    return stems


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
    """Delete what only the assembly needs: the filter graphs, the parts, the audio premixes, the reverb's impulse response, the color match LUTs and the local copies of the sources."""
    for pattern in ("graph*.txt", "part-*.mkv", "lanes-*.wav", IMPULSE, "match-*.cube", f"{core_bridge.SOURCE_PREFIX}*"):
        for path in folder.glob(pattern):
            await discard(path)


async def loudness_of(
    ffmpeg: str, mezzanine: Path, target: float, total: float, on_process: Optional[Callable[[Any], Any]] = None
) -> Optional[Dict[str, float]]:
    """What a first ffmpeg run measures of the mezzanine's sound for the loudness target; None for a silent mix; raises ExportError(transcode_failed)."""
    stderr = await assemble(levels.measure_command(ffmpeg, mezzanine, target), total, None, on_process, None, "transcode_failed")
    return levels.parse(stderr)


async def loudness_filter(
    ffmpeg: str, mezzanine: Path, target: float, total: float, on_process: Optional[Callable[[Any], Any]] = None
) -> Optional[str]:
    """The second loudnorm pass for the mezzanine's sound, from a first ffmpeg run that measures it; None for a silent mix; raises ExportError(transcode_failed)."""
    measured = await loudness_of(ffmpeg, mezzanine, target, total, on_process)
    return None if measured is None else levels.normalize_filter(target, measured, SAMPLE_RATE)


async def convert(
    ffmpeg: str,
    mezzanine: Path,
    final: Path,
    size: Tuple[int, int],
    fps: Any,
    total: float,
    report: Callable[[float, str], bool],
    on_process: Optional[Callable[[Any], Any]] = None,
    loudness: Optional[float] = None,
    fmt: str = "web",
) -> float:
    """Write the delivery file of the format from the mezzanine, its sound brought to the loudness target in LUFS when given, reporting the transcode step from ASSEMBLE_SHARE to TRANSCODE_END; returns the gain in dB the target gave the mix, 0 without one; raises ExportError(transcode_failed)."""

    def converted(share: float) -> None:
        report(ASSEMBLE_SHARE + share * (TRANSCODE_END - ASSEMBLE_SHARE), "transcode")

    measured = None if loudness is None else await loudness_of(ffmpeg, mezzanine, loudness, total, on_process)
    audio_filter = None if measured is None else levels.normalize_filter(loudness, measured, SAMPLE_RATE)
    command = convert_command(ffmpeg, mezzanine, final, size, fps, audio_filter, fmt)
    await assemble(command, total, converted, on_process, None, "transcode_failed")
    if not final.exists() or final.stat().st_size == 0:
        raise ExportError("transcode_failed", "ffmpeg wrote an empty video.")
    return 0.0 if measured is None else levels.normalize_gain(loudness, measured)


async def write_stems(
    ffmpeg: str, stems: Mapping[str, Path], finals: Mapping[str, Path], gain: float, total: float, on_process: Optional[Callable[[Any], Any]] = None
) -> None:
    """Write the delivered stems from those of the mezzanine; raises ExportError(transcode_failed)."""
    await assemble(stems_command(ffmpeg, stems, finals, gain), total, None, on_process, None, "transcode_failed")
    empty = [name for name, path in finals.items() if not path.exists() or path.stat().st_size == 0]
    if empty:
        raise ExportError("transcode_failed", f"ffmpeg wrote an empty stem: {', '.join(empty)}.")


def pack(target: Path, files: Sequence[Path]) -> Path:
    """A ZIP of the files, stored without compression, each under its own name."""
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return target


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


def channels_of(ffprobe: str, path: Any) -> Optional[int]:
    """The channels of a file's first audio stream as ffprobe reads them, None when it cannot tell."""
    try:
        run = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=VERSION_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = run.stdout.decode("utf-8", "replace").strip().splitlines() if run.returncode == 0 else []
    return int(text[0]) if text and text[0].strip().isdigit() else None


def mono_files(paths: Iterable[Any]) -> List[str]:
    """The files among these whose sound has one channel, each file read once; none without ffprobe."""
    ffprobe = core_bridge.find_ffprobe()
    if not ffprobe:
        return []
    return [path for path in dict.fromkeys(str(path) for path in paths) if channels_of(ffprobe, path) == 1]


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
    """Assemble, transcode and store one export: the video of its format, packed in a ZIP with its stems when the job asks for them, the web and social videos also stored in the requester's library; returns its file and library item, raises ExportError."""
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
    fmt, resolution = job["format"], job["resolution"]
    size = frame_size(doc, fmt, resolution)
    mezzanine, final = folder / MEZZANINE, folder / file_name(project["name"], resolution, fmt)
    _, total = timeline(doc)
    try:
        shots, sounds = await asyncio.to_thread(media.local_inputs, doc, takes.list_takes(project["id"]), resolver, folder)
        if not any(shots.values()):
            raise ExportError("ffmpeg_failed", "No shot of the sequence has a file to assemble.")
        paths = {
            "ffmpeg": ffmpeg,
            "graph_option": await asyncio.to_thread(graph_option, ffmpeg),
            "output": str(mezzanine),
            "graph": str(folder / GRAPH),
            "audio": sounds,
        }
        sources = [entry["path"] for entry in shots.values() if entry is not None] + list(sounds.values())
        paths["cwd"] = common_folder(sources)
        options = {
            "format": fmt,
            "resolution": resolution,
            "stills": [clip_id for clip_id, entry in shots.items() if entry is not None and entry["still"]],
            "cubes": await asyncio.to_thread(match.write_cubes, doc, folder),
            **await asyncio.to_thread(inspect, shots),
            "mono": await asyncio.to_thread(mono_files, sources),
            "impulse": str(await asyncio.to_thread(write_impulse, folder / IMPULSE, SAMPLE_RATE)),
            "stems": bool(job.get("stems")),
        }
        if not report(0, "assemble"):
            raise cancelled()
        mixed = await assemble_sequence(doc, shots, options, paths, folder, report, on_process)
    finally:
        await discard_work(folder)
    if not report(ASSEMBLE_SHARE, "transcode"):
        raise cancelled()
    stems = {name: folder / stem_file(final.name, name) for name in mixed}
    try:
        gain = await convert(ffmpeg, mezzanine, final, size, fps_of(doc), total, report, on_process, levels.target_of(doc), fmt)
        if mixed:
            await write_stems(ffmpeg, mixed, stems, gain, total, on_process)
    finally:
        await discard(mezzanine)
        for path in mixed.values():
            await discard(path)
    if not report(TRANSCODE_END, "store"):
        raise cancelled()
    result: Dict[str, Any] = {"file_name": final.name, "file_size": final.stat().st_size, "media_item_id": None, "media_url": None}
    if fmt in LIBRARY_FORMATS:
        try:
            stored = await core_bridge.save_user_media(requester, final)
            item = core_bridge.upload_item(requester.id, stored["value"]) or {}
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Could not store export %s in the library", job["id"], exc_info=True)
            raise ExportError("store_failed", last_line(str(exc)) or "The video could not be stored in the library.") from exc
        result.update(media_item_id=item.get("item_id"), media_url=f"/api/media/uploads/{media.basename(stored['value'])}")
    if stems:
        files = [final, *stems.values()]
        try:
            packed = await asyncio.to_thread(pack, folder / file_name(project["name"], resolution, fmt, stems=True), files)
        except OSError as exc:
            raise ExportError("store_failed", last_line(str(exc)) or "The stems could not be packed.") from exc
        for path in files:
            await discard(path)
        result.update(file_name=packed.name, file_size=packed.stat().st_size)
    return result
