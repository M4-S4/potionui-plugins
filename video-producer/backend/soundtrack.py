import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import core_bridge, director, takes
from .core_bridge import User
from .director import CONDITION, MUX, TRACK_PREFIX, Plans, ShotPlan, TrackCut
from .exports import media
from .exports.common import asset_of
from .exports.video import SAMPLE_RATE, ExportError, assemble, kill_tree, last_line, num, sound_chain

logger = logging.getLogger("plugins.video-producer")

SUFFIX = ".wav"

H3_RATE = 32000

ENCODER = ("-c:a", "pcm_s16le", "-ac", "2")

LAYOUT = f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo"

SILENCE_DB = -60.0

PEAK_SECONDS = 60.0

PEAK_CACHE = 512

PEAK = re.compile(r"max_volume:\s*(-?(?:inf|\d+(?:\.\d+)?))\s*dB")

_PEAKS: Dict[Tuple[Any, ...], float] = {}


class SoundError(Exception):
    """The sound of a shot that could not be cut or stored."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def work_base() -> Path:
    """The folder the cuts of every user are written in before they are stored."""
    return core_bridge.storage_directory() / "video_producer" / "audio"


def mix_graph(
    doc: Mapping[str, Any],
    lanes: Sequence[str],
    start: float,
    end: float,
    sounds: Mapping[str, str],
    references: Sequence[str] = (),
) -> Tuple[List[str], str]:
    """The inputs and the filter graph of one cut: the items of the tracks heard between start and end, each with its gain and fades at its place, the references from their beginning, over silence that lasts the whole cut."""
    length = num(end - start)
    inputs: List[str] = []
    graph = [f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=duration={length}[bed]"]
    labels: List[str] = []

    def add(path: str, chain: List[str]) -> None:
        inputs.extend(["-i", path])
        label = f"[m{len(labels)}]"
        graph.append(f"[{len(labels)}:a]{','.join(chain)}{label}")
        labels.append(label)

    by_id = {lane["id"]: lane for lane in doc.get("lanes") or []}
    for lane_id in lanes:
        for item in director.lane_items(doc, lane_id, start, end):
            if item["id"] in sounds:
                add(sounds[item["id"]], sound_chain(item, by_id.get(lane_id) or {}, start))
    for path in references:
        add(path, [f"atrim=duration={length}", "asetpts=PTS-STARTPTS", LAYOUT])
    if labels:
        graph.append(f"[bed]{''.join(labels)}amix=inputs={len(labels) + 1}:duration=first:dropout_transition=0:normalize=0[aout]")
    else:
        graph.append("[bed]anull[aout]")
    return inputs, ";".join(graph)


def cut_command(ffmpeg: str, inputs: Sequence[str], graph: str, length: float, output: Path, rate: int = SAMPLE_RATE) -> List[str]:
    """The ffmpeg run that writes one cut as a stereo WAV file of exactly length seconds at rate Hz."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        *inputs,
        "-filter_complex", graph,
        "-map", "[aout]",
        "-t", num(length),
        *ENCODER, "-ar", str(rate),
        str(output),
    ]


def peak_command(ffmpeg: str, inputs: Sequence[str], graph: str, length: float, rate: int = SAMPLE_RATE) -> List[str]:
    """The ffmpeg run that reads the peak level of a cut as cut_command would write it at rate Hz, writing nothing."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "info", "-nostats",
        *inputs,
        "-filter_complex", f"{graph};[aout]aresample={rate},volumedetect[peak]",
        "-map", "[peak]",
        "-t", num(length),
        "-f", "null", "-",
    ]


def convert_command(ffmpeg: str, source: str, output: Path, rate: int) -> List[str]:
    """The ffmpeg run that writes a whole sound as a stereo WAV file at rate Hz."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", source, "-map", "0:a:0", "-vn", *ENCODER, "-ar", str(rate), str(output),
    ]


class _Sources:
    def __init__(self, owner: User, doc: Mapping[str, Any], project_id: str, folder: Optional[Path]):
        self.doc = doc
        self.folder = folder
        self.resolver = media.Resolver(owner)
        self.takes = takes.list_takes(project_id)
        self.found: Dict[str, Optional[media.Found]] = {}
        self.cache: Dict[str, Optional[Path]] = {}

    def located(self, asset_id: Any) -> Optional[media.Found]:
        key = str(asset_id)
        if key not in self.found:
            asset = asset_of(self.doc, asset_id)
            found = media.locate(asset, self.takes, self.resolver) if asset else None
            self.found[key] = found if found and found.kind else None
        return self.found[key]

    def path(self, asset_id: Any) -> Optional[str]:
        key = str(asset_id)
        if key not in self.cache:
            found = self.located(asset_id)
            self.cache[key] = self.resolver.local(found.kind, found.value, self.folder) if found else None
        path = self.cache[key]
        return None if path is None else str(path)

    def signature(self, lane_id: str, start: float, end: float) -> Optional[Tuple[Any, ...]]:
        """What the cut of one track depends on, read without opening a file: the media of its items and the graph that mixes them; None when none of them is found."""
        sounds = {}
        for item in director.lane_items(self.doc, lane_id, start, end):
            found = self.located(item.get("assetId"))
            if found is not None:
                sounds[item["id"]] = f"{found.kind}:{found.value}"
        if not sounds:
            return None
        inputs, graph = mix_graph(self.doc, [lane_id], start, end, sounds)
        return (*inputs, graph)

    def items(self, lanes: Sequence[str], start: float, end: float) -> Dict[str, str]:
        sounds: Dict[str, str] = {}
        for lane_id in lanes:
            found = 0
            for item in director.lane_items(self.doc, lane_id, start, end):
                path = self.path(item.get("assetId"))
                if path is not None:
                    sounds[item["id"]] = path
                    found += 1
            if not found:
                raise SoundError("audio_source_missing", "The sound of a reference track can no longer be read.")
        return sounds


async def cut(
    ffmpeg: str,
    sources: _Sources,
    lanes: Sequence[str],
    start: float,
    end: float,
    name: str,
    references: Sequence[Any] = (),
    rate: int = SAMPLE_RATE,
) -> Path:
    """Write the cut of tracks and references between start and end in the work folder at rate Hz; raises SoundError."""
    sounds = await asyncio.to_thread(sources.items, lanes, start, end)
    paths = []
    for asset_id in references:
        path = await asyncio.to_thread(sources.path, asset_id)
        if path is None:
            raise SoundError("audio_source_missing", "The sound of an audio reference can no longer be read.")
        if path not in paths:
            paths.append(path)
    inputs, graph = mix_graph(sources.doc, lanes, start, end, sounds, paths)
    output = sources.folder / f"{name}{SUFFIX}"
    try:
        await assemble(cut_command(ffmpeg, inputs, graph, end - start, output, rate), end - start, code="audio_cut_failed")
    except ExportError as exc:
        raise SoundError(exc.code, exc.message) from None
    return output


async def convert(ffmpeg: str, sources: _Sources, asset_id: Any, name: str, rate: int) -> Path:
    """Write a whole sound reference at rate Hz in the work folder; raises SoundError."""
    path = await asyncio.to_thread(sources.path, asset_id)
    if path is None:
        raise SoundError("audio_source_missing", "The sound of an audio reference can no longer be read.")
    output = sources.folder / f"{name}{SUFFIX}"
    try:
        await assemble(convert_command(ffmpeg, path, output, rate), 0.0, code="audio_cut_failed")
    except ExportError as exc:
        raise SoundError(exc.code, exc.message) from None
    return output


async def peak(command: Sequence[str]) -> Optional[float]:
    """The peak level in dBFS a measuring run of ffmpeg reports, or None when it fails or runs longer than PEAK_SECONDS."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
    except OSError:
        logger.warning("[VIDEO-PRODUCER] ffmpeg could not start to measure a sound", exc_info=True)
        return None
    try:
        _, errors = await asyncio.wait_for(process.communicate(), PEAK_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("[VIDEO-PRODUCER] Measuring a sound took longer than %g s", PEAK_SECONDS)
        return None
    finally:
        if kill_tree(process):
            await process.wait()
    text = errors.decode("utf-8", "replace")
    found = PEAK.findall(text)
    if process.returncode != 0 or not found:
        logger.warning("[VIDEO-PRODUCER] Could not measure a sound: %s", last_line(text))
        return None
    return float(found[-1])


def _remember(key: Tuple[Any, ...], level: float) -> None:
    _PEAKS[key] = level
    while len(_PEAKS) > PEAK_CACHE:
        _PEAKS.pop(next(iter(_PEAKS)))


async def track_peak(ffmpeg: str, sources: _Sources, cut: TrackCut) -> Optional[float]:
    """The peak level in dBFS of the cut of one guided track, mixed and resampled as attach writes it; None when it cannot be read."""
    try:
        sounds = await asyncio.to_thread(sources.items, [cut.lane_id], cut.start, cut.end)
    except SoundError:
        return None
    inputs, graph = mix_graph(sources.doc, [cut.lane_id], cut.start, cut.end, sounds)
    return await peak(peak_command(ffmpeg, inputs, graph, cut.end - cut.start, H3_RATE))


async def silent_lanes(owner: User, project_id: str, doc: Mapping[str, Any], cuts: Sequence[TrackCut]) -> Dict[str, List[str]]:
    """The reference tracks each guided shot would send silent, their cut peaking at SILENCE_DB or below, each cut measured once per owner, media and graph, in a work folder made only when one must be; a track whose cut cannot be measured is kept, and fails at the cut as before."""
    ffmpeg = core_bridge.find_ffmpeg() if cuts else None
    if not ffmpeg:
        return {}
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    silent: Dict[str, List[str]] = {}
    folder: Optional[Path] = None
    try:
        sources = _Sources(owner, doc, project_id, None)
        keys: Dict[TrackCut, Tuple[Any, ...]] = {}
        for cut in cuts:
            signature = await asyncio.to_thread(sources.signature, cut.lane_id, cut.start, cut.end)
            if signature is not None:
                keys[cut] = (owner.id, *signature)
        levels = {key: _PEAKS[key] for key in keys.values() if key in _PEAKS}
        missing = {key: cut for cut, key in keys.items() if key not in levels}
        if missing:
            base = work_base() / owner.id
            base.mkdir(parents=True, exist_ok=True)
            folder = sources.folder = Path(tempfile.mkdtemp(dir=base))
        for key, cut in missing.items():
            level = await track_peak(ffmpeg, sources, cut)
            if level is not None:
                levels[key] = level
                _remember(key, level)
        for cut, key in keys.items():
            level = levels.get(key)
            if level is not None and level <= SILENCE_DB:
                silent.setdefault(cut.shot_id, []).append(cut.lane_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not measure the reference tracks of the guided shots", exc_info=True)
    finally:
        if folder is not None:
            await asyncio.to_thread(shutil.rmtree, folder, True)
    return silent


async def heard_plans(owner: User, project_id: str, doc: Mapping[str, Any], *args: Any, **kwargs: Any) -> Plans:
    """director.build_plans with the reference tracks a guided shot would send silent left out before its references are ranked and its prompt written, each said by an audio_track_silent warning."""
    plans = director.build_plans(owner, doc, *args, **kwargs)
    silent = await silent_lanes(owner, project_id, doc, plans.track_cuts)
    return director.build_plans(owner, doc, *args, **kwargs, silent=silent) if silent else plans


async def _store(owner: User, path: Path) -> str:
    try:
        stored = await core_bridge.save_user_media(owner, path)
    except Exception as exc:
        logger.warning("[VIDEO-PRODUCER] Could not store the sound %s", path.name, exc_info=True)
        raise SoundError("audio_store_failed", last_line(str(exc)) or "The sound of the shot could not be stored.") from None
    return str(stored["value"])


def _file_name(doc: Mapping[str, Any], plan: ShotPlan, suffix: str) -> str:
    index = next((i for i, clip in enumerate(doc.get("clips") or []) if clip.get("id") == plan.shot_id), 0)
    return f"vp-sound-shot-{index + 1:02d}-{suffix}"


def _lane_code(doc: Mapping[str, Any], lane_id: str) -> str:
    index = next((i for i, lane in enumerate(doc.get("lanes") or []) if lane.get("id") == lane_id), None)
    return f"a{index + 1}" if index is not None else "track"


async def attach(owner: User, project: Mapping[str, Any], plan: ShotPlan) -> None:
    """Cut the sound a plan sends, store each cut once as the owner's upload and put it in the plan's request: for a guided shot, each reference track in place of its placeholder and each sound reference in place of its file, both at the 32 kHz MiniMax-H3 encodes without resampling; for a mixed shot, one mix of the tracks and the audio references as the mux entry of its director document; raises SoundError."""
    audio = plan.audio
    if not plan.needs_audio or audio is None:
        return
    ffmpeg = core_bridge.find_ffmpeg()
    if not ffmpeg:
        raise SoundError("audio_ffmpeg_missing", "ffmpeg is not available on this server: the sound of the shot cannot be cut.")
    ffmpeg = os.path.abspath(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg
    doc = project["doc"]
    base = work_base() / owner.id
    base.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=base))
    try:
        sources = _Sources(owner, doc, project["id"], folder)
        form = plan.request["form_data"]
        if audio.behavior == CONDITION:
            stored = {}
            for lane_id in audio.lanes:
                name = _file_name(doc, plan, _lane_code(doc, lane_id))
                path = await cut(ffmpeg, sources, [lane_id], audio.start, audio.end, name, rate=H3_RATE)
                stored[f"{TRACK_PREFIX}{lane_id}"] = await _store(owner, path)
            for index, asset_id in enumerate(audio.references, start=1):
                path = await convert(ffmpeg, sources, asset_id, _file_name(doc, plan, f"sound{index}"), H3_RATE)
                stored[audio.sent[asset_id]] = await _store(owner, path)
            form["references"] = [stored.get(value, value) for value in form.get("references") or []]
        elif audio.behavior == MUX:
            path = await cut(ffmpeg, sources, audio.lanes, audio.start, audio.end, _file_name(doc, plan, "mix"), audio.references)
            value = await _store(owner, path)
            form["video_director"]["audio"] = [director.mux_entry(value, audio.length)]
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
