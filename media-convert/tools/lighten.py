import math
from dataclasses import dataclass
from pathlib import Path

from src.plugin_api.media_tools import MediaTool, ToolFailed

from .common import (
    H264_PRESET,
    LENGTH_TOLERANCE,
    MAX_VIDEO_PIXELS,
    MEGABYTE,
    check_duration,
    count_frames,
    fit,
    guard,
    input_args,
    longest,
    make_room,
    max_seconds,
    metadata_args,
    quota_rooms,
    read_streams,
    refuse,
    release,
    scratch_bytes,
    thread_args,
)

TARGETS_MB = (8, 16, 18, 20, 30, 50)
DEFAULT_TARGET_MB = 16
MEGABYTE_SI = 1000 * 1000
MARGIN = 0.04
H264_GROWTH = 1.0
OTHER_GROWTH = 1.5
AUDIO_STEPS_KBPS = ((1000, 128), (500, 96), (0, 64))
MIN_VIDEO_KBPS = 150
SMALLEST_VIDEO_KBPS = 32
BITS_PER_PIXEL = 0.04
SIDES = (1920, 1280, 960, 640, 480)
FALLBACK_RATE = 30.0
CAP_FALLBACK_RATE = 60.0
FRAME_SLACK = 1.02
PASS_BYTES_PER_MACROBLOCK = 2
PASS_BYTES_PER_FRAME = 512
COPY_CONTAINERS = (".mp4", ".mov", ".m4v")
COPY_PIXELS = ("yuv420p", "yuvj420p")
NOT_AS_STATED = (
    "This video does not hold what its file states (its length or its frame rate is wrong); "
    "convert it with Convert video first, then lighten the result"
)
ROOM_TEXT = "Media Converter could not write the lightened video in the room it had; choose a smaller size"


@dataclass(frozen=True)
class Plan:
    video_kbps: int
    audio_kbps: int
    width: int
    height: int


def target_bytes(params: dict) -> int:
    value = int(params.get("target") or DEFAULT_TARGET_MB)
    if value not in TARGETS_MB:
        raise ToolFailed(f"Media Converter cannot aim at {value} MB")
    return value * MEGABYTE_SI


def length_text(seconds: float) -> str:
    if seconds < 120:
        return f"{math.ceil(seconds)} seconds"
    return f"{math.ceil(seconds / 60)} minutes"


def audio_kbps(total_kbps: float, track) -> int:
    if track is None:
        return 0
    rate = next(kbps for floor, kbps in AUDIO_STEPS_KBPS if total_kbps >= floor)
    if track.bit_rate:
        rate = min(rate, max(32, math.ceil(track.bit_rate / 1000)))
    return rate


def smallest_mb(duration: float, track) -> int:
    kbps = MIN_VIDEO_KBPS + audio_kbps(0, track)
    return math.ceil(kbps * 1000 * duration / 8 / (1 - MARGIN) / MEGABYTE_SI)


def impossible(target: int, duration: float, track) -> ToolFailed:
    smallest = smallest_mb(duration, track)
    size = target // MEGABYTE_SI
    larger = [item for item in TARGETS_MB if item >= smallest]
    hints = [f"choose {larger[0]} MB or more"] if larger else []
    if track is not None:
        quiet = [item for item in TARGETS_MB if item >= smallest_mb(duration, None)]
        if quiet and quiet[0] <= size:
            hints.append("turn off Keep the sound")
        elif quiet and not larger:
            hints.append(f"turn off Keep the sound and choose {quiet[0]} MB or more")
    if not larger:
        hints.append("trim it into shorter parts first")
    return ToolFailed(
        f"This video lasts {length_text(duration)}: to fit in {size} MB, its picture would be "
        f"too poor to watch. The smallest file Media Converter can make from it weighs about {smallest} MB; "
        + ", or ".join(hints)
    )


def encoded_seconds(streams, track, fallback: float) -> float:
    kept = [stream.duration for stream in (streams.video, track) if stream is not None and stream.duration]
    return max(kept) if kept else fallback


def plan(media, streams, track, target: int, seconds: float, source_seconds: float) -> Plan:
    budget = target * (1 - MARGIN)
    target_kbps = budget * 8 / seconds / 1000
    audio_at_target = audio_kbps(target_kbps, track)
    if target_kbps - audio_at_target < MIN_VIDEO_KBPS:
        raise impossible(target, seconds, track)
    growth = H264_GROWTH if streams.video is not None and streams.video.codec == "h264" else OTHER_GROWTH
    source_kbps = Path(media.path).stat().st_size * 8 / source_seconds / 1000
    total = min(target_kbps, source_kbps * growth * (1 - MARGIN))
    audio = min(audio_kbps(total, track), audio_at_target)
    video = max(SMALLEST_VIDEO_KBPS, int(total - audio))
    room = target_kbps - audio_at_target
    rate = (streams.video.rate if streams.video else None) or media.fps or FALLBACK_RATE
    for side in (max(media.width, media.height), *SIDES):
        if side > max(media.width, media.height):
            continue
        width, height = fit(media.width, media.height, side, even=True)
        if room * 1000 / (width * height * rate) >= BITS_PER_PIXEL:
            break
    return Plan(video, audio, width, height)


def frame_cap(seconds: float, rate: float) -> int:
    return math.ceil(min(seconds, max_seconds() + 1) * rate * FRAME_SLACK) + 2


def frames_to_encode(media, streams, seconds: float) -> int:
    counted = count_frames(media.path, streams.video.index)
    if counted:
        return math.ceil(counted * FRAME_SLACK) + 2
    return frame_cap(seconds, streams.video.rate or media.fps or CAP_FALLBACK_RATE)


def first_pass_frames(prefix: Path) -> int:
    log = prefix.parent / f"{prefix.name}-0.log"
    try:
        with log.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for line in handle if line.startswith("in:"))
    except OSError:
        return 0


def pass_log_bytes(frames: int, width: int, height: int) -> int:
    macroblocks = math.ceil(width / 16) * math.ceil(height / 16)
    return frames * (macroblocks * PASS_BYTES_PER_MACROBLOCK + PASS_BYTES_PER_FRAME) + MEGABYTE


def size_mb(count: int) -> str:
    return f"{math.floor(count * 10 / MEGABYTE_SI) / 10:g} MB"


def quota_refusal(room) -> ToolFailed:
    if room.reason == "storage":
        return ToolFailed(
            "This video would not fit in what is left of your storage; free some space or choose a smaller size"
        )
    fitting = [item for item in TARGETS_MB if item * MEGABYTE_SI <= room.size]
    if fitting:
        return ToolFailed(f"Your files may weigh at most {size_mb(room.size)}; choose {fitting[-1]} MB or less")
    return ToolFailed(
        f"Your files may weigh at most {size_mb(room.size)}, less than the smallest size Lighten for sending makes"
    )


def lighten_room(ctx, cap: int, needed: int, scratch: int, result: int):
    folder = Path(ctx.scratch_dir)
    folder.mkdir(parents=True, exist_ok=True)
    for room in quota_rooms(ctx, scratch_bytes(folder)):
        if room.size < result:
            raise quota_refusal(room)
    return make_room(ctx, cap, needed=needed, scratch=scratch)


def lighten_refuse(room, written: int) -> None:
    if room.reason in ("run", "disk"):
        refuse(room, written)
    raise ToolFailed(ROOM_TEXT)


def copyable(media, streams, track) -> bool:
    picture = streams.video
    if Path(media.path).suffix.lower() not in COPY_CONTAINERS or picture is None:
        return False
    if picture.codec != "h264" or picture.pix_fmt not in COPY_PIXELS:
        return False
    return track is None or (track.codec == "aac" and track.channels <= 2)


def scratch_files(prefix: Path) -> list:
    return sorted(prefix.parent.glob(prefix.name + "-*"))


class LightenVideo(MediaTool):
    def run(self, inputs, params, ctx):
        return [self.lighten(media, params, ctx) for media in inputs]

    def lighten(self, media, params, ctx):
        target = target_bytes(params)
        keep_sound = bool(params.get("keep_sound", True))
        keep = bool(params.get("keep_metadata", False))
        check_duration(media.duration)
        if not media.width or not media.height:
            raise ToolFailed("Media Converter cannot read the size of this video")
        if media.width * media.height > MAX_VIDEO_PIXELS:
            raise ToolFailed(
                f"This video is {media.width} × {media.height} pixels; Media Converter takes videos "
                "of up to 4096 × 2304 pixels (about 9.4 million)"
            )
        guard(ctx)
        streams = read_streams(media.path)
        check_duration(streams.duration)
        if streams.video is None:
            raise ToolFailed("This video has no picture to convert")
        duration = longest(media.duration, streams.duration)
        if not duration:
            raise ToolFailed("Media Converter cannot read the length of this video")
        track = streams.audio[0] if keep_sound and streams.audio else None
        seconds = encoded_seconds(streams, track, duration)
        if Path(media.path).stat().st_size < target and copyable(media, streams, track):
            copied = self.copy(media, streams, track, keep, target, ctx)
            if copied is not None:
                return copied
        return self.encode(media, streams, track, keep, target, seconds, duration, ctx)

    def mapping(self, media, streams, track) -> list[str]:
        args = ["-map", f"0:{streams.video.index}"]
        if track is not None:
            args += ["-map", f"0:{track.index}"]
        return args

    def copy(self, media, streams, track, keep, target, ctx):
        out = ctx.new_path(".mp4")
        size = Path(media.path).stat().st_size
        room = lighten_room(ctx, target, needed=size, scratch=0, result=size)
        try:
            ctx.ffmpeg(
                [
                    *input_args(media.path), *self.mapping(media, streams, track), "-sn", "-dn", "-c", "copy",
                    *metadata_args(streams, None, keep), "-movflags", "+faststart",
                    "-t", f"{max_seconds() + 1:.3f}", "-fs", str(room.size), str(out),
                ],
                duration=media.duration,
            )
            guard(ctx)
            written = out.stat().st_size
        finally:
            release(room)
        if written >= target:
            out.unlink(missing_ok=True)
            return None
        if written >= room.size:
            out.unlink(missing_ok=True)
            lighten_refuse(room, written)
        return ctx.probe(out, "video")

    def encode(self, media, streams, track, keep, target, seconds, duration, ctx):
        chosen = plan(media, streams, track, target, seconds, duration)
        frames = frames_to_encode(media, streams, seconds)
        logs = pass_log_bytes(frames, chosen.width, chosen.height)
        prefix = ctx.new_path("", stem="pass")
        room = lighten_room(ctx, target + logs, needed=target + logs, scratch=logs, result=target)
        outputs = []
        try:
            self.first_pass(media, streams, chosen, prefix, frames, ctx.scoped(0.0, 0.4))
            guard(ctx)
            if first_pass_frames(prefix) >= frames:
                raise ToolFailed(NOT_AS_STATED)
            out = ctx.new_path(".mp4")
            outputs.append(out)
            self.second_pass(media, streams, track, keep, chosen, prefix, room, out, ctx.scoped(0.4, 0.9))
            guard(ctx)
            written = out.stat().st_size
            if written >= target:
                budget = target * (1 - MARGIN)
                cut = math.ceil((written - budget) * 8 / seconds / 1000) + 1
                retry = Plan(max(SMALLEST_VIDEO_KBPS, chosen.video_kbps - cut), chosen.audio_kbps, chosen.width, chosen.height)
                out.unlink(missing_ok=True)
                out = ctx.new_path(".mp4")
                outputs.append(out)
                self.second_pass(media, streams, track, keep, retry, prefix, room, out, ctx.scoped(0.9, 1.0))
                guard(ctx)
                written = out.stat().st_size
            if written >= target:
                raise ToolFailed(
                    f"Media Converter could not bring this video under {target // MEGABYTE_SI} MB; "
                    "choose a larger size"
                )
            if written >= self.limit(room, prefix):
                lighten_refuse(room, written)
        except BaseException:
            for path in outputs:
                path.unlink(missing_ok=True)
            raise
        finally:
            for path in scratch_files(prefix):
                path.unlink(missing_ok=True)
            release(room)
        made = read_streams(out)
        if streams.video.duration:
            shown, expected = (made.video.duration if made.video else None) or made.duration, streams.video.duration
        else:
            shown, expected = made.duration, seconds
        if shown is None or shown < expected - LENGTH_TOLERANCE:
            out.unlink(missing_ok=True)
            raise ToolFailed(NOT_AS_STATED)
        return ctx.probe(out, "video")

    def video_args(self, media, chosen: Plan, prefix: Path, number: int) -> list[str]:
        args = []
        if (chosen.width, chosen.height) != (media.width, media.height):
            args += ["-vf", f"scale={chosen.width}:{chosen.height}:flags=lanczos"]
        return [
            *args, "-fps_mode", "vfr", "-c:v", "libx264", "-preset", H264_PRESET,
            "-b:v", f"{chosen.video_kbps}k", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-pass", str(number), "-passlogfile", str(prefix),
        ]

    def first_pass(self, media, streams, chosen, prefix, frames, ctx):
        ctx.ffmpeg(
            [
                *thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), "-map", f"0:{streams.video.index}",
                "-an", "-sn", "-dn", *self.video_args(media, chosen, prefix, 1), "-frames:v", str(frames),
                "-t", f"{max_seconds() + 1:.3f}", *thread_args()[:2], "-f", "null", "-",
            ],
            duration=media.duration,
        )

    def limit(self, room, prefix: Path) -> int:
        return room.size - sum(path.stat().st_size for path in scratch_files(prefix))

    def second_pass(self, media, streams, track, keep, chosen, prefix, room, out, ctx) -> None:
        sound = []
        if track is not None:
            sound = ["-c:a", "aac", "-b:a", f"{chosen.audio_kbps}k"]
            if track.channels > 2:
                sound += ["-ac", "2"]
        ctx.ffmpeg(
            [
                *thread_args(), *input_args(media.path, MAX_VIDEO_PIXELS), *self.mapping(media, streams, track),
                "-sn", "-dn", *self.video_args(media, chosen, prefix, 2), *sound,
                *metadata_args(streams, None, keep), "-movflags", "+faststart",
                "-t", f"{max_seconds() + 1:.3f}", "-fs", str(self.limit(room, prefix)), *thread_args()[:2], str(out),
            ],
            duration=media.duration,
        )
