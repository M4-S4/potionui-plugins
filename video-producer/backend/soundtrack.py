import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import core_bridge, director, takes
from .core_bridge import User
from .director import CONDITION, MUX, TRACK_PREFIX, ShotPlan
from .exports import media
from .exports.common import asset_of
from .exports.video import SAMPLE_RATE, ExportError, assemble, last_line, num, sound_chain

logger = logging.getLogger("plugins.video-producer")

SUFFIX = ".wav"

H3_RATE = 32000

ENCODER = ("-c:a", "pcm_s16le", "-ac", "2")

LAYOUT = f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo"


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


def convert_command(ffmpeg: str, source: str, output: Path, rate: int) -> List[str]:
    """The ffmpeg run that writes a whole sound as a stereo WAV file at rate Hz."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
        "-i", source, "-map", "0:a:0", "-vn", *ENCODER, "-ar", str(rate), str(output),
    ]


class _Sources:
    def __init__(self, owner: User, doc: Mapping[str, Any], project_id: str, folder: Path):
        self.doc = doc
        self.folder = folder
        self.resolver = media.Resolver(owner)
        self.takes = takes.list_takes(project_id)
        self.cache: Dict[str, Optional[Path]] = {}

    def path(self, asset_id: Any) -> Optional[str]:
        key = str(asset_id)
        if key not in self.cache:
            asset = asset_of(self.doc, asset_id)
            found = media.locate(asset, self.takes, self.resolver) if asset else None
            self.cache[key] = self.resolver.local(found.kind, found.value, self.folder) if found and found.kind else None
        path = self.cache[key]
        return None if path is None else str(path)

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
