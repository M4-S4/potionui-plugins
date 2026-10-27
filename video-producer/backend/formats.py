import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

TABLE_PATH = Path(__file__).with_name("formats.json")


def load_table(path: Path = TABLE_PATH) -> Dict[str, Any]:
    """The table of the film formats, the delivery sizes, the framing and the sizes each engine takes, as the page reads it."""
    return json.loads(path.read_text(encoding="utf-8"))


TABLE = load_table()

FORMATS: Tuple[str, ...] = tuple(item["id"] for item in TABLE["formats"])

DEFAULT_FORMAT: str = TABLE["defaultFormat"]

CUSTOM: Dict[str, Any] = TABLE["custom"]

RESOLUTIONS: Dict[str, int] = {name: int(base) for name, base in TABLE["resolutions"].items()}

DEFAULT_RESOLUTION: str = TABLE["defaultResolution"]

BOX = TABLE["box"][0] / TABLE["box"][1]

SOCIAL_FORMATS: Tuple[str, ...] = tuple(TABLE["social"]["formats"])

SOCIAL_DEFAULT: str = TABLE["social"]["default"]

FRAMINGS: Tuple[str, ...] = tuple(TABLE["framing"]["modes"])

DEFAULT_FRAMING: str = TABLE["framing"]["default"]

EXACT_LOSS = float(TABLE["framing"]["exact"])

CROP_LOSS = float(TABLE["framing"]["crop"])

SIZES: Dict[str, Any] = TABLE["sizes"]

ENGINES: Dict[str, Dict[str, Any]] = TABLE["engines"]

AUTO, CROP, BARS = "auto", "crop", "bars"

EXACT = "exact"

DRAFT, FINAL = "draft", "final"

QUALITIES = (DRAFT, FINAL)

SCALE = 1e9

_FORMAT = re.compile(r"^([0-9]+(?:\.[0-9]{1,%d})?):([0-9]+(?:\.[0-9]{1,%d})?)$" % (CUSTOM["decimals"], CUSTOM["decimals"]))

_SIZE = re.compile(r"^\s*([0-9]+)\s*[x×]\s*([0-9]+)\s*$")

_NUMBER = re.compile(r"^\s*[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?\s*$")

Size = Tuple[int, int]


def _key(value: float) -> int:
    return math.floor(value * SCALE + 0.5)


def half_up(value: float) -> int:
    """The nearest whole number, a half rounded up, as the page rounds."""
    return math.floor(value + 0.5)


def even(value: float) -> int:
    """The nearest even number of pixels, at least 2."""
    return max(2, 2 * half_up(value / 2))


def ratio_of(value: Any) -> Optional[float]:
    """The width over height of a format written W:H, W/H or WxH; None when it is not one."""
    text = str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""
    for separator in (":", "/", "x"):
        if text.count(separator) == 1:
            parts = text.split(separator)
            if not all(_NUMBER.match(part) for part in parts):
                return None
            width, height = float(parts[0]), float(parts[1])
            if math.isfinite(width) and math.isfinite(height) and width > 0 and height > 0:
                return width / height
            return None
    return None


def format_value(value: Any) -> str:
    """The format a document keeps: one of the table, a custom W:H between its bounds, else the default."""
    text = value.strip() if isinstance(value, str) else ""
    if text in FORMATS:
        return text
    match = _FORMAT.match(text)
    if match:
        width, height = float(match.group(1)), float(match.group(2))
        if width > 0 and height > 0 and CUSTOM["minRatio"] <= width / height <= CUSTOM["maxRatio"]:
            return text
    return DEFAULT_FORMAT


def resolution_value(value: Any) -> str:
    """The delivery resolution a document keeps: one of the table, else the default."""
    return value if isinstance(value, str) and value in RESOLUTIONS else DEFAULT_RESOLUTION


def framing_of(doc: Mapping[str, Any]) -> str:
    """How the film fits a take of another ratio: the project's choice, else auto."""
    value = doc.get("framing")
    return value if value in FRAMINGS else DEFAULT_FRAMING


def parse_size(value: Any) -> Optional[Size]:
    """A WxH size as two positive whole numbers, or None."""
    match = _SIZE.match(value) if isinstance(value, str) else None
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    return (width, height) if width > 0 and height > 0 else None


def size_text(size: Size) -> str:
    """A size written WxH."""
    return f"{size[0]}x{size[1]}"


def _value(option: Any) -> Any:
    return option.get("value") if isinstance(option, Mapping) else option


def _sizes(options: Sequence[Any]) -> List[Size]:
    return [size for size in (parse_size(_value(option)) for option in options or []) if size is not None]


def sizes_value(value: Any) -> Dict[str, Dict[str, str]]:
    """The sizes a project chose per preset and quality, kept to a preset id and a WxH size within the bounds for each."""
    kept: Dict[str, Dict[str, str]] = {}
    if not isinstance(value, Mapping):
        return kept
    for preset_id, chosen in value.items():
        if not isinstance(preset_id, str) or not preset_id or not isinstance(chosen, Mapping):
            continue
        entry: Dict[str, str] = {}
        for quality in QUALITIES:
            size = parse_size(chosen.get(quality))
            if size is not None and _bounded(size):
                entry[quality] = size_text(size)
        if entry:
            kept[preset_id] = entry
    return kept


def _bounded(size: Optional[Size]) -> bool:
    return size is not None and all(SIZES["min"] <= side <= SIZES["max"] for side in size)


def chosen_size(doc: Mapping[str, Any], preset_id: Optional[str], quality: str) -> Optional[str]:
    """The size the project chose for a preset at a quality, or None for the automatic one."""
    sizes = sizes_value((doc.get("engine") or {}).get("sizes")) if isinstance(doc.get("engine"), Mapping) else {}
    return sizes.get(preset_id or "", {}).get(quality)


def engine_of(preset_id: Optional[str]) -> Dict[str, Any]:
    """The grid and the limits of the engine a preset runs, empty for an engine the table does not know."""
    return next((engine for engine in ENGINES.values() if preset_id in engine["presets"]), {})


def grid_of(preset_id: Optional[str]) -> int:
    """The pixel multiple the engine of a preset works in."""
    return int(engine_of(preset_id).get("grid") or SIZES["grid"])


def snap(value: float, multiple: int) -> int:
    """The nearest multiple, a tie rounded down, at least one multiple, as the engine rounds."""
    return max(1, math.ceil(value / multiple - 0.5)) * multiple


def snap_size(size: Size, multiple: int) -> Size:
    """A size put on a pixel grid."""
    return snap(size[0], multiple), snap(size[1], multiple)


def size_problem(size: Size, preset_id: Optional[str]) -> Optional[str]:
    """Why the engine of a preset would refuse a size (bounds, ratio or area), None when it takes it."""
    if not _bounded(size):
        return "bounds"
    engine = engine_of(preset_id)
    ratio = size[0] / size[1]
    if "minRatio" in engine and not engine["minRatio"] <= ratio <= engine["maxRatio"]:
        return "ratio"
    if "maxPixels" in engine and size[0] * size[1] > engine["maxPixels"]:
        return "area"
    return None


def _log_ratio(size: Size) -> float:
    return math.log(size[0] / size[1])


def families(sizes: Sequence[Size]) -> List[List[Size]]:
    """The sizes grouped by ratio, largest first, each family led by its largest size and a size joining the first family whose leader is within the tolerance."""
    found: List[List[Size]] = []
    for size in sorted(dict.fromkeys(sizes), key=lambda size: -size[0] * size[1]):
        for family in found:
            if _key(abs(_log_ratio(size) - _log_ratio(family[0]))) <= _key(SIZES["tolerance"]):
                family.append(size)
                break
        else:
            found.append([size])
    return found


def working_family(options: Sequence[Any], ratio: float, preset_id: Optional[str] = None) -> List[Size]:
    """The family of sizes a preset makes a film of this ratio in: of those with a final size and a draft size, the closest in ratio."""
    sizes = [snap_size(size, grid_of(preset_id)) for size in _sizes(options)]
    found = families(sizes)
    if not found:
        return []
    top = max(width * height for width, height in sizes)
    eligible = [
        family for family in found if family[0][0] * family[0][1] >= SIZES["finalShare"] * top and min(w * h for w, h in family) <= SIZES["draftMax"]
    ] or found
    target = math.log(ratio)
    return min(eligible, key=lambda family: _key(abs(_log_ratio(family[0]) - target)))


def _oriented(size: Size, landscape: bool) -> Size:
    return size if (size[0] >= size[1]) == landscape else (size[1], size[0])


def draft_size(options: Sequence[Any], setting: Any, ratio: float, preset_id: Optional[str] = None) -> Optional[str]:
    """The draft size: the admin's setting turned to the family's orientation when the family has it, else the family's size closest to it in area."""
    wanted = parse_size(setting)
    if wanted is None:
        return None
    family = working_family(options, ratio, preset_id)
    if not family:
        return size_text(snap_size(_oriented(wanted, ratio >= 1), grid_of(preset_id)))
    wanted = snap_size(_oriented(wanted, family[0][0] >= family[0][1]), grid_of(preset_id))
    if wanted in family:
        return size_text(wanted)
    area = wanted[0] * wanted[1]
    return size_text(min(family, key=lambda size: (abs(size[0] * size[1] - area), size[0] * size[1])))


def final_size(options: Sequence[Any], ratio: float, preset_id: Optional[str] = None) -> Optional[str]:
    """The final size: the largest of the family."""
    family = working_family(options, ratio, preset_id)
    return size_text(family[0]) if family else None


@dataclass(frozen=True)
class SizeChoice:
    """The size a take is asked at: the automatic one or the project's choice put on the engine's grid, and the choice left out when the engine would refuse it."""

    size: Optional[str]
    chosen: Optional[str] = None
    refused: Optional[str] = None
    problem: Optional[str] = None


def pick_size(
    options: Sequence[Any], ratio: float, quality: str, setting: Any, chosen: Optional[str] = None, preset_id: Optional[str] = None
) -> SizeChoice:
    """The size of a take at a quality: the project's choice for the preset when the engine takes it, else the draft or the final size of the family."""
    size = parse_size(chosen)
    if size is not None:
        snapped = snap_size(size, grid_of(preset_id))
        problem = size_problem(snapped, preset_id)
        if problem is None:
            return SizeChoice(size=size_text(snapped), chosen=chosen)
        automatic = final_size(options, ratio, preset_id) if quality == FINAL else draft_size(options, setting, ratio, preset_id)
        return SizeChoice(size=automatic, refused=chosen, problem=problem)
    return SizeChoice(size=final_size(options, ratio, preset_id) if quality == FINAL else draft_size(options, setting, ratio, preset_id))


def loss(take_ratio: float, frame_ratio: float) -> float:
    """The share of a take's picture the film's frame leaves out when it crops it."""
    return 1 - min(take_ratio, frame_ratio) / max(take_ratio, frame_ratio)


def fit(take_ratio: float, frame_ratio: float, framing: str = DEFAULT_FRAMING) -> str:
    """How the film shows a take: exact when the ratios agree within the tolerance, else crop or bars as the framing asks, auto cropping up to its threshold."""
    lost = _key(loss(take_ratio, frame_ratio))
    if lost <= _key(EXACT_LOSS):
        return EXACT
    if framing == CROP or framing == BARS:
        return framing
    return CROP if lost <= _key(CROP_LOSS) else BARS


def keep_share(framing: str) -> float:
    """The smallest share of a take's side the film keeps by cropping before it puts bars instead: 0 crops always."""
    if framing == CROP:
        return 0.0
    return 1 - (EXACT_LOSS if framing == BARS else CROP_LOSS)


def delivery_size(ratio: float, resolution: Any) -> Size:
    """The frame of a film of this ratio at a resolution: inside the 16:9 box of the resolution, lying for a landscape format and standing for a portrait one, touching two of its sides."""
    base = RESOLUTIONS.get(resolution, RESOLUTIONS[DEFAULT_RESOLUTION]) if isinstance(resolution, str) else RESOLUTIONS[DEFAULT_RESOLUTION]
    long = base * BOX
    if ratio >= 1:
        width, height = (long, long / ratio) if ratio >= BOX else (base * ratio, base)
    else:
        width, height = (long * ratio, long) if 1 / ratio >= BOX else (base, base / ratio)
    return even(width), even(height)


def closest_format(values: Sequence[Any], ratio: float) -> Optional[str]:
    """The offered format closest in ratio, the first on a tie."""
    found = [(text, value) for text, value in ((str(value), ratio_of(value)) for value in values or []) if value is not None]
    if not found:
        return None
    return min(found, key=lambda item: _key(abs(math.log(item[1]) - math.log(ratio))))[0]


def ratio_text(ratio: float) -> str:
    """A ratio as the film formats write it: the table's format within the tolerance, else two decimals to 1."""
    known = closest_format(FORMATS, ratio)
    if known is not None and fit(ratio_of(known) or ratio, ratio) == EXACT:
        return known
    return f"{ratio:.2f}:1"


def time_scale(measured: Any, wanted: Any) -> Optional[float]:
    """How much longer a take at the wanted size runs than one at the measured size: their areas' ratio to the table's exponent."""
    old, new = parse_size(measured), parse_size(wanted)
    if old is None or new is None:
        return None
    return ((new[0] * new[1]) / (old[0] * old[1])) ** float(SIZES["timeExponent"])


def nearest_measured(measured: Sequence[Any], wanted: Any) -> Optional[str]:
    """Of the sizes measured, the closest in area to the wanted one, the larger on a tie."""
    target = parse_size(wanted)
    sizes = [(text, size) for text, size in ((str(text), parse_size(text)) for text in measured) if size is not None]
    if target is None or not sizes:
        return None
    area = target[0] * target[1]
    return min(sizes, key=lambda item: (_key(abs(math.log(item[1][0] * item[1][1] / area))), -item[1][0] * item[1][1]))[0]
