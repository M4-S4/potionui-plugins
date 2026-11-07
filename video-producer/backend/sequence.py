import math
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

PATCH = 32
CHUNK_FRAMES = 17
CHUNK_HEAD = 5
CHUNK_LATENTS = 5
TEXT_ROWS = 600
VIDEO_ROWS = 780
SHORT_EDGE = 2048
CAP_PIXELS = 2 * 1344 * 768
MAX_RATIO = 4
EXPONENT = 1.22
CEILING = 28000
NOTICEABLE = 1.05


def latent_frames(frames: int) -> int:
    """The latent frames the video VAE of MiniMax-H3 makes of a number of frames, raised first to the next 17 n + 5 it encodes."""
    frames = max(1, int(frames))
    aligned = frames + (CHUNK_HEAD - frames) % CHUNK_FRAMES
    return (aligned - CHUNK_HEAD) // CHUNK_FRAMES * CHUNK_LATENTS + 2


def frame_rows(size: Optional[Tuple[int, int]]) -> int:
    """The rows one latent frame of a size takes in the sequence: one per 32 × 32 pixels."""
    if not size:
        return 0
    return (int(size[0]) // PATCH) * (int(size[1]) // PATCH)


def _ratio(size: Tuple[int, int]) -> float:
    return max(int(size[0]), int(size[1])) / min(int(size[0]), int(size[1]))


def reference_short_edge(size: Optional[Tuple[int, int]], final: bool, pictures: Iterable[Optional[Tuple[int, int]]] = ()) -> int:
    area = CAP_PIXELS if final or not size else min(CAP_PIXELS, int(size[0]) * int(size[1]))
    shape = _ratio(size) if size else 16 / 9
    ratios = [_ratio(picture) if picture else shape for picture in pictures] or [shape]
    return max(PATCH, min(math.floor(math.sqrt(area / min(MAX_RATIO, ratio))) for ratio in ratios))


def _snap(length: float, source: int) -> int:
    return max(PATCH, min(round(length / PATCH), source // PATCH) * PATCH)


def image_size(edge: int, picture: Tuple[int, int]) -> Tuple[int, int]:
    width, height = int(picture[0]), int(picture[1])
    if width > height * MAX_RATIO:
        height = math.ceil(width / MAX_RATIO)
    elif width * MAX_RATIO < height:
        width = math.ceil(height / MAX_RATIO)
    scale = edge / min(width, height)
    snapped_width, snapped_height = _snap(width * scale, width), _snap(height * scale, height)
    return min(snapped_width, snapped_height * MAX_RATIO), min(snapped_height, snapped_width * MAX_RATIO)


def image_rows(edge: int, picture: Optional[Tuple[int, int]], size: Optional[Tuple[int, int]] = None) -> int:
    shape = size or (16, 9)
    return frame_rows(image_size(edge, picture or (int(shape[0]) * SHORT_EDGE, int(shape[1]) * SHORT_EDGE)))


@dataclass(frozen=True)
class Rows:
    """The rows a Ref2VA take of MiniMax-H3 packs, without its reference video tracks and with them."""

    base: int
    tracks: int

    @property
    def total(self) -> int:
        return self.base + self.tracks

    @property
    def scale(self) -> float:
        """How much longer a step takes with the tracks than without: the step follows the rows to the power 1.22, fitted on the takes of the 27 October."""
        return (self.total / self.base) ** EXPONENT if self.base > 0 and self.tracks > 0 else 1.0

    @property
    def high(self) -> bool:
        """True when the tracks take the sequence past the rows a 12 GB card holds before it saturates."""
        return self.tracks > 0 and self.total > CEILING


def shot_rows(seconds: float, fps: float, size: Optional[Tuple[int, int]], images: Iterable[int], cuts: Iterable[Tuple[int, Tuple[int, int]]]) -> Rows:
    """The rows of a shot of some seconds at a size, with its images and the frames and size of each track it sends; the text and the videos are counted at what the takes measured."""
    base = latent_frames(round(seconds * fps)) * frame_rows(size) + sum(images) + TEXT_ROWS
    tracks = sum(latent_frames(frames) * frame_rows(cut) + VIDEO_ROWS for frames, cut in cuts)
    return Rows(base=base, tracks=tracks)
