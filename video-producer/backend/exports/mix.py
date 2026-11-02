import json
import math
import struct
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

MIX_PATH = Path(__file__).with_name("mix.json")

MASK = 0xFFFFFFFF

WAVE_FLOAT = 3


def load_mix(path: Path = MIX_PATH) -> Dict[str, Any]:
    """The shared rule of the console, as the page reads it."""
    return json.loads(path.read_text(encoding="utf-8"))


RULE = load_mix()


def _finite(value: Any, fallback: Any) -> Any:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else fallback


def _within(bounds: Sequence[float], value: float) -> float:
    return min(bounds[1], max(bounds[0], value))


def gain_of(db: Any, rule: Mapping[str, Any] = RULE) -> float:
    """The linear gain of a level in dB as the console plays it: none at the rule's silentAt and below."""
    value = _finite(db, 0.0)
    if value <= rule["silentAt"]:
        return 0.0
    try:
        return math.pow(10, value / 20)
    except OverflowError:
        return math.inf


def _insert(lane: Mapping[str, Any], kind: str) -> Optional[Mapping[str, Any]]:
    inserts = lane.get("inserts")
    for insert in inserts if isinstance(inserts, list) else []:
        if isinstance(insert, Mapping) and insert.get("type") == kind and insert.get("on") is True:
            return insert
    return None


def makeup_of(threshold: float, ratio: float, rule: Mapping[str, Any] = RULE) -> float:
    """The make-up gain the browser's compressor adds with a hard knee: the gain it takes off a full-scale signal, to the rule's power, at most its maxMakeup."""
    if not ratio > 1 or not threshold < 0:
        return 1.0
    reduced = -threshold * (1 - 1 / ratio)
    return min(math.pow(10, reduced * rule["comp"]["makeupPower"] / 20), rule["comp"]["maxMakeup"])


def pan_of(pan: Any) -> Dict[str, float]:
    """The gains of the browser's stereo panner: ll and rl make the left channel from the left and right inputs, lr and rr the right one."""
    p = min(1.0, max(-1.0, _finite(pan, 0.0)))
    x = p + 1 if p <= 0 else p
    near, far = math.cos(x * math.pi / 2), math.sin(x * math.pi / 2)
    return {"ll": 1.0, "rl": near, "lr": 0.0, "rr": far} if p <= 0 else {"ll": near, "rl": 0.0, "lr": far, "rr": 1.0}


def send_of(lane: Mapping[str, Any], aux: Any, bus_id: str, rule: Mapping[str, Any] = RULE) -> float:
    """The gain of a track's send to an auxiliary bus, the bus's own level included; none when the bus is muted."""
    bus = next((entry for entry in aux if isinstance(entry, Mapping) and entry.get("id") == bus_id), None) if isinstance(aux, list) else None
    if bus is not None and bus.get("mute"):
        return 0.0
    sends = lane.get("sends") if isinstance(lane.get("sends"), Mapping) else {}
    return gain_of(_finite(sends.get(bus_id), rule["silentAt"]), rule) * gain_of(_finite((bus or {}).get("vol"), 0.0), rule)


def _comp(comp: Optional[Mapping[str, Any]], rule: Mapping[str, Any]) -> Optional[Dict[str, float]]:
    if comp is None:
        return None
    bounds = rule["comp"]
    threshold = _within(bounds["threshold"], _finite(comp.get("threshold"), 0.0))
    ratio = _within(bounds["ratio"], _finite(comp.get("ratio"), 1.0))
    if not ratio > 1 or not threshold < 0:
        return None
    attack = _within(bounds["attack"], _finite(comp.get("attack"), bounds["attack"][0]))
    release = _within(bounds["release"], _finite(comp.get("release"), bounds["release"][0]))
    return {"threshold": threshold, "ratio": ratio, "attack": attack, "release": release, "knee": bounds["knee"], "makeup": makeup_of(threshold, ratio, rule)}


def strip_of(lane: Mapping[str, Any], aux: Any, audible: bool = True, rule: Mapping[str, Any] = RULE) -> Dict[str, Any]:
    """What a track's strip does to its sound, as the page's console plays it: the equalizer gains, the low-pass cutoff, the compressor, the pan, the fader gain and the gains of its sends."""
    eq, cut = _insert(lane, "eq"), _insert(lane, "filter")
    cutoff = _finite(cut.get("cutoff"), None) if cut is not None else None
    return {
        "eq": {band: _within(rule["eq"]["gain"], _finite(eq.get(band), 0.0)) if eq is not None else 0.0 for band in ("low", "mid", "high")},
        "cutoff": _within(rule["filter"]["cutoff"], cutoff) if cutoff is not None else None,
        "comp": _comp(_insert(lane, "comp"), rule),
        "pan": min(1.0, max(-1.0, _finite(lane.get("pan"), 0.0))),
        "fader": gain_of(lane.get("vol"), rule) if audible else 0.0,
        "sends": {bus: send_of(lane, aux, bus, rule) for bus in (rule["reverb"]["id"], rule["delay"]["id"])},
    }


def _imul(a: int, b: int) -> int:
    return (a * b) & MASK


def random(seed: int) -> Callable[[], float]:
    """The page's seeded generator (mulberry32): numbers in [0, 1), the same sequence for the same seed."""
    state = [seed & MASK]

    def next_value() -> float:
        a = (state[0] + 0x6D2B79F5) & MASK
        state[0] = a
        t = _imul(a ^ (a >> 15), a | 1)
        t = ((t + _imul(t ^ (t >> 7), t | 61)) & MASK) ^ t
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    return next_value


def impulse_length(rate: int, rule: Mapping[str, Any] = RULE) -> int:
    """The samples of each channel of the reverb's impulse response at a sample rate."""
    return math.floor(rate * rule["reverb"]["seconds"] + 0.5)


def reverb_impulse(rate: int, rule: Mapping[str, Any] = RULE) -> List[List[float]]:
    """The impulse response of the reverb bus at a sample rate, as the page builds it: seeded noise on a falling curve, one channel then the other, brought to the calibrated level."""
    reverb = rule["reverb"]
    length = impulse_length(rate, rule)
    next_value = random(reverb["seed"])
    channels: List[List[float]] = []
    power = 0.0
    for _ in range(2):
        data = []
        for i in range(length):
            fall = 1 - i / length
            envelope = 1.0
            for _ in range(reverb["decay"]):
                envelope *= fall
            value = (next_value() * 2 - 1) * envelope
            data.append(value)
            power += value * value
        channels.append(data)
    scale = (reverb["calibration"] / math.sqrt(power / (2 * length))) * (reverb["calibrationRate"] / rate)
    return [[value * scale for value in data] for data in channels]


def write_impulse(path: Path, rate: int, rule: Mapping[str, Any] = RULE) -> Path:
    """Write the reverb's impulse response as a 32-bit float stereo WAV file."""
    left, right = reverb_impulse(rate, rule)
    frames = [value for pair in zip(left, right) for value in pair]
    data = struct.pack(f"<{len(frames)}f", *frames)
    fmt = struct.pack("<HHIIHH", WAVE_FLOAT, 2, rate, rate * 8, 8, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    Path(path).write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return Path(path)


def delay_taps(rule: Mapping[str, Any] = RULE) -> List[Dict[str, float]]:
    """The echoes of the delay bus, its feedback unrolled: each at a multiple of the delay, down to the rule's floor."""
    delay = rule["delay"]
    least = math.pow(10, delay["floor"] / 20)
    taps: List[Dict[str, float]] = []
    gain, k = 1.0, 1
    while gain >= least:
        taps.append({"seconds": delay["seconds"] * k, "gain": gain})
        gain *= delay["feedback"]
        k += 1
    return taps
