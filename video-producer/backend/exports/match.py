import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

LUT_SIZE = 33

MAX_SCALE = 1.5

MIN_SPREAD = 1e-3

IDENTITY = 1e-4

STATS = 6

CUBE_NAME = "match-{}.cube"

CUBE_TITLE = "Video Producer match"

WHITE = (0.95047, 1.0, 1.08883)

TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)

TO_RGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)

EDGE = 6 / 29

Transfer = Tuple[Tuple[float, float, float], Tuple[float, float, float]]


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _encoded(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _f(t: float) -> float:
    return t ** (1 / 3) if t > EDGE**3 else t / (3 * EDGE**2) + 4 / 29


def _f_inverse(t: float) -> float:
    return t**3 if t > EDGE else 3 * EDGE**2 * (t - 4 / 29)


def _lab_of_linear(r: float, g: float, b: float) -> Tuple[float, float, float]:
    x, y, z = (row[0] * r + row[1] * g + row[2] * b for row in TO_XYZ)
    fx, fy, fz = _f(x / WHITE[0]), _f(y / WHITE[1]), _f(z / WHITE[2])
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def to_lab(rgb: Sequence[float]) -> Tuple[float, float, float]:
    """CIELAB (D65) of an sRGB color with channels from 0 to 1."""
    return _lab_of_linear(*(_linear(c) for c in rgb))


def from_lab(lab: Sequence[float]) -> Tuple[float, float, float]:
    """The sRGB color of a CIELAB (D65) one, each channel held between 0 and 1."""
    fy = (lab[0] + 16) / 116
    x, y, z = WHITE[0] * _f_inverse(fy + lab[1] / 500), WHITE[1] * _f_inverse(fy), WHITE[2] * _f_inverse(fy - lab[2] / 200)
    return tuple(min(max(_encoded(max(row[0] * x + row[1] * y + row[2] * z, 0.0)), 0.0), 1.0) for row in TO_RGB)


def _stats(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != STATS:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value):
        return None
    return [float(v) for v in value]


def transfer(match: Any) -> Optional[Transfer]:
    """The gain and offset on L, a and b that move the measured take toward its anchor: the Reinhard transfer of the means and spreads, each spread ratio held between 2/3 and 3/2, scaled by the strength in percent; None for a match that cannot be read."""
    if not isinstance(match, Mapping):
        return None
    source, target, strength = _stats(match.get("source")), _stats(match.get("target")), match.get("strength")
    if source is None or target is None or isinstance(strength, bool) or not isinstance(strength, (int, float)):
        return None
    amount = min(max(float(strength) / 100, 0.0), 1.0)
    gains, offsets = [], []
    for k in range(3):
        spread_source, spread_target = source[k + 3], target[k + 3]
        scale = spread_target / spread_source if spread_source > MIN_SPREAD and spread_target > MIN_SPREAD else 1.0
        scale = min(max(scale, 1 / MAX_SCALE), MAX_SCALE)
        gains.append(1 + amount * (scale - 1))
        offsets.append(amount * (target[k] - scale * source[k]))
    return (gains[0], gains[1], gains[2]), (offsets[0], offsets[1], offsets[2])


def is_identity(moves: Transfer) -> bool:
    """Whether a transfer leaves every color as it is."""
    gains, offsets = moves
    return all(abs(g - 1) < IDENTITY for g in gains) and all(abs(o) < IDENTITY * 100 for o in offsets)


def active(clip: Mapping[str, Any]) -> Optional[Transfer]:
    """The transfer of a shot's color match when it applies: measured on the asset the shot shows now and not an identity; None otherwise."""
    match = clip.get("match")
    if not isinstance(match, Mapping) or clip.get("assetId") is None or match.get("assetId") != clip.get("assetId"):
        return None
    moves = transfer(match)
    return None if moves is None or is_identity(moves) else moves


def apply(moves: Transfer, rgb: Sequence[float]) -> Tuple[float, float, float]:
    """An sRGB color moved by a transfer."""
    gains, offsets = moves
    lab = to_lab(rgb)
    return from_lab([lab[k] * gains[k] + offsets[k] for k in range(3)])


def lut(moves: Transfer, size: int = LUT_SIZE) -> List[Tuple[float, float, float]]:
    """The transfer sampled on a size³ grid, red varying fastest, then green, then blue: the order of a .cube file."""
    gains, offsets = moves
    levels = [_linear(i / (size - 1)) for i in range(size)]
    points = []
    for b in levels:
        for g in levels:
            for r in levels:
                lab = _lab_of_linear(r, g, b)
                points.append(from_lab((lab[0] * gains[0] + offsets[0], lab[1] * gains[1] + offsets[1], lab[2] * gains[2] + offsets[2])))
    return points


def cube(moves: Transfer, size: int = LUT_SIZE) -> str:
    """The text of the .cube file of a transfer."""
    lines = [f'TITLE "{CUBE_TITLE}"', f"LUT_3D_SIZE {size}"]
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in lut(moves, size)]
    return "\n".join(lines) + "\n"


def write_cubes(doc: Mapping[str, Any], folder: Path) -> Dict[str, str]:
    """Write the .cube file of every shot whose color match applies into the folder; the path of each by shot id."""
    paths: Dict[str, str] = {}
    for index, clip in enumerate(doc.get("clips") or []):
        moves = active(clip)
        if moves is None:
            continue
        path = folder / CUBE_NAME.format(index)
        path.write_text(cube(moves), encoding="ascii")
        paths[clip["id"]] = str(path)
    return paths
