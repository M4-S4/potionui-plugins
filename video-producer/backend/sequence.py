from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

PATCH = 32
CHUNK_FRAMES = 17
CHUNK_HEAD = 5
CHUNK_LATENTS = 5
TEXT_ROWS = 600
VIDEO_ROWS = 780
IMAGE_ROWS = 2040
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


def shot_rows(seconds: float, fps: float, size: Optional[Tuple[int, int]], images: int, fitted: bool, cuts: Iterable[Tuple[int, Tuple[int, int]]]) -> Rows:
    """The rows of a shot of some seconds at a size, with its images (fitted to the size of the take, else at the cap of the core) and the frames and size of each track it sends; the text and the videos are counted at what the takes measured."""
    target = frame_rows(size)
    image = min(IMAGE_ROWS, target) if fitted else IMAGE_ROWS
    base = latent_frames(round(seconds * fps)) * target + max(0, images) * image + TEXT_ROWS
    tracks = sum(latent_frames(frames) * frame_rows(cut) + VIDEO_ROWS for frames, cut in cuts)
    return Rows(base=base, tracks=tracks)
