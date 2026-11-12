import math
from typing import Iterable, List, Optional, Tuple

TILE = 32
MIN_PIXELS = 65536
MAX_PIXELS = 16777216
FPS = 24.0
SAMPLE_FPS = 2.0
TEMPORAL_PATCH = 2
MAX_RATIO = 4
CANVAS_SHORT_EDGE = 768
CANVAS_MAX_PIXELS = 768 * 1344
LIMIT_12GB = 2200

Size = Tuple[int, int]


def max_pixels(budget: Optional[float], output: Optional[Size]) -> int:
    if not budget or budget <= 0 or not output or output[0] <= 0 or output[1] <= 0:
        return MAX_PIXELS
    return max(int(budget * output[0] * output[1]), MIN_PIXELS)


def smart_grid(height: int, width: int, limit: int) -> Size:
    h_bar = round(height / TILE) * TILE
    w_bar = round(width / TILE) * TILE
    if h_bar * w_bar > limit:
        beta = ((height * width) / limit) ** 0.5
        h_bar = max(TILE, int(height / beta / TILE) * TILE)
        w_bar = max(TILE, int(width / beta / TILE) * TILE)
    elif h_bar * w_bar < MIN_PIXELS:
        beta = (MIN_PIXELS / (height * width)) ** 0.5
        h_bar = -(-int(height * beta) // TILE) * TILE
        w_bar = -(-int(width * beta) // TILE) * TILE
    return h_bar, w_bar


def _tiles(grid: Size) -> int:
    return (grid[0] // TILE) * (grid[1] // TILE)


def padded(picture: Size) -> Size:
    width, height = int(picture[0]), int(picture[1])
    if width > height * MAX_RATIO:
        return width, math.ceil(width / MAX_RATIO)
    if width < height / MAX_RATIO:
        return math.ceil(height / MAX_RATIO), height
    return width, height


def image_tokens(picture: Optional[Size], limit: int) -> int:
    if picture is None:
        return limit // (TILE * TILE)
    width, height = padded(picture)
    return _tiles(smart_grid(height, width, limit))


def _snap(length: float, source: int) -> int:
    return max(TILE, min(round(length / TILE), source // TILE) * TILE)


def video_canvas(size: Size) -> Size:
    width, height = int(size[0]), int(size[1])
    ratio = width / height
    canvas_width, canvas_height = (CANVAS_SHORT_EDGE * ratio, float(CANVAS_SHORT_EDGE)) if ratio >= 1 else (float(CANVAS_SHORT_EDGE), CANVAS_SHORT_EDGE / ratio)
    area = canvas_width * canvas_height
    if area > CANVAS_MAX_PIXELS:
        scale = (CANVAS_MAX_PIXELS / area) ** 0.5
        canvas_width, canvas_height = canvas_width * scale, canvas_height * scale
    canvas_height = max(TILE, round(canvas_height / TILE) * TILE)
    canvas_width = max(TILE, round(canvas_width / TILE) * TILE)
    snapped_height, snapped_width = _snap(canvas_height, height), _snap(canvas_width, width)
    return min(snapped_height, snapped_width * MAX_RATIO), min(snapped_width, snapped_height * MAX_RATIO)


def sampled_frames(frames: int) -> List[int]:
    stride = FPS / SAMPLE_FPS
    indices: List[int] = []
    cursor = 0.0
    while round(cursor) < frames:
        if not indices or round(cursor) > indices[-1]:
            indices.append(round(cursor))
        cursor += stride
    return indices


def video_tokens(frames: int, size: Size, limit: int) -> int:
    if frames <= 0:
        return 0
    blocks = -(-len(sampled_frames(frames)) // TEMPORAL_PATCH)
    height, width = video_canvas(size)
    return blocks * _tiles(smart_grid(height, width, limit))


def vision_tokens(pictures: Iterable[Optional[Size]], videos: Iterable[Tuple[int, Size]], limit: int) -> int:
    return sum(image_tokens(picture, limit) for picture in pictures) + sum(video_tokens(frames, size, limit) for frames, size in videos)
