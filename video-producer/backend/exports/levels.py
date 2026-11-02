import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional

TARGETS = {"web": -14.0, "broadcast": -23.0}

TRUE_PEAK = -1.0

LOUDNESS_RANGE = 11.0

MAX_RANGE = 50.0

PEAK_MARGIN = 0.1

SILENCE = -70.0

MEASURED = {
    "input_i": ("measured_I", -99.0, 0.0),
    "input_tp": ("measured_TP", -99.0, 99.0),
    "input_lra": ("measured_LRA", 0.0, 99.0),
    "input_thresh": ("measured_thresh", -99.0, 0.0),
}

_REPORT = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")


def target_of(doc: Mapping[str, Any]) -> Optional[float]:
    """The integrated loudness the export aims at in LUFS, from the master's loudness setting; None when the export keeps the level of the mix."""
    master = doc.get("master")
    return TARGETS.get(master.get("loudness")) if isinstance(master, Mapping) else None


def _num(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def measure_filter(target: float) -> str:
    """The filter of the first pass, which only measures the mix and prints what it read as JSON."""
    return f"loudnorm=I={_num(target)}:TP={_num(TRUE_PEAK)}:LRA={_num(LOUDNESS_RANGE)}:print_format=json"


def measure_command(ffmpeg: str, path: Any, target: float) -> List[str]:
    """The ffmpeg run that measures the loudness of a file's first audio stream, its report printed on stderr."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "info", "-progress", "pipe:1", "-nostats",
        "-i", str(path), "-map", "0:a:0", "-vn", "-af", measure_filter(target), "-f", "null", "-",
    ]


def parse(stderr: str) -> Optional[Dict[str, float]]:
    """What the first pass measured, from the last JSON report on stderr; None without a report or for a silent mix."""
    found = _REPORT.findall(str(stderr or ""))
    if not found:
        return None
    try:
        report = json.loads(found[-1])
        values = {key: float(report[key]) for key in MEASURED}
    except (ValueError, KeyError, TypeError):
        return None
    if not all(math.isfinite(value) for value in values.values()) or values["input_i"] <= SILENCE:
        return None
    return values


def _goal(target: float, measured: Mapping[str, float]) -> float:
    reach = TRUE_PEAK - PEAK_MARGIN - measured["input_tp"] + measured["input_i"]
    return max(min(target, reach), SILENCE)


def normalize_gain(target: float, measured: Mapping[str, float]) -> float:
    """The gain in dB the second pass gives the whole mix in the linear mode: the loudness it aims at less the loudness measured, both as its options write them."""
    _, low, high = MEASURED["input_i"]
    return float(_num(_goal(target, measured))) - float(_num(min(max(measured["input_i"], low), high)))


def normalize_filter(target: float, measured: Mapping[str, float], rate: int) -> str:
    """The filter of the second pass: one gain for the whole mix that brings it to the target, lowered so that its true peak stays under the ceiling, with a loudness range target no narrower than the measured one so that loudnorm keeps the linear mode."""
    goal = _goal(target, measured)
    spread = min(max(LOUDNESS_RANGE, math.ceil(measured["input_lra"] * 10) / 10), MAX_RANGE)
    known = ":".join(
        f"{option}={_num(min(max(measured[key], low), high))}" for key, (option, low, high) in MEASURED.items()
    )
    return f"loudnorm=I={_num(goal)}:TP={_num(TRUE_PEAK)}:LRA={_num(spread)}:{known}:linear=true,aresample={rate}"
