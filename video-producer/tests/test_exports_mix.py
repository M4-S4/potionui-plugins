import hashlib
import json
import math
import struct
from pathlib import Path

import pytest

from backend.exports import mix

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PAGE_COPY = PLUGIN_ROOT / "frontend" / "src" / "lib" / "mix.json"
PARITY = json.loads((FIXTURES / "mix_parity.json").read_text(encoding="utf-8"))


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _close(actual, expected, path="$"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and set(actual) == set(expected), path
        for key in expected:
            _close(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for index, (a, e) in enumerate(zip(actual, expected)):
            _close(a, e, f"{path}[{index}]")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15), (path, actual, expected)
    else:
        assert actual == expected, (path, actual, expected)


def test_the_page_reads_an_identical_copy_of_the_console_rule():
    assert json.loads(PAGE_COPY.read_text(encoding="utf-8")) == mix.RULE


def test_the_javascript_cases_were_generated_from_the_rule_in_use():
    assert PARITY["mixSha256"] == _canonical_sha(mix.RULE), "regenerate tests/fixtures/mix_parity.json with make_mix_parity.mjs"
    assert len(PARITY["strips"]) == len(PARITY["lanes"]) * len(PARITY["aux"]) * 2


def test_every_strip_plays_as_the_pages_console_does():
    for case in PARITY["strips"]:
        lane, aux = PARITY["lanes"][case["lane"]], PARITY["aux"][case["aux"]]
        _close(mix.strip_of(lane, aux, case["audible"]), case["strip"], f"strip {case['lane']}/{case['aux']}/{case['audible']}")


def test_the_levels_make_up_gains_pans_and_sends_agree_with_the_page():
    for case in PARITY["levels"]:
        _close(mix.gain_of(case["db"]), case["gain"], f"level {case['db']}")
    for case in PARITY["makeups"]:
        _close(mix.makeup_of(case["threshold"], case["ratio"]), case["makeup"], f"makeup {case}")
    for case in PARITY["pans"]:
        _close(mix.pan_of(case["pan"]), case["gains"], f"pan {case['pan']}")
    for case in PARITY["sends"]:
        lane, aux = PARITY["lanes"][case["lane"]], PARITY["aux"][case["aux"]]
        _close(mix.send_of(lane, aux, case["id"]), case["gain"], f"send {case}")
    _close(mix.delay_taps(), PARITY["taps"])


def test_the_seeded_generator_and_the_reverb_impulse_are_the_pages_to_the_bit():
    draw = mix.random(mix.RULE["reverb"]["seed"])
    assert [draw() for _ in PARITY["sequence"]] == PARITY["sequence"]
    for case in PARITY["impulses"]:
        channels = mix.reverb_impulse(case["rate"])
        assert [len(data) for data in channels] == [case["length"]] * 2
        packed = b"".join(struct.pack(f"<{len(data)}f", *data) for data in channels)
        assert hashlib.sha256(packed).hexdigest() == case["sha256"], case["rate"]
        floats = [list(struct.unpack(f"<{len(data)}f", struct.pack(f"<{len(data)}f", *data))) for data in channels]
        assert [data[:4] for data in floats] == case["head"]
        assert [data[-2:] for data in floats] == case["tail"]


def test_a_compressor_with_a_hard_knee_makes_up_what_it_takes_off_full_scale_to_the_rules_power():
    assert mix.makeup_of(-18, 3) == pytest.approx(10 ** (0.6 * 12 / 20))
    assert mix.makeup_of(0, 4) == 1.0
    assert mix.makeup_of(-30, 1) == 1.0
    assert mix.makeup_of(-60, 20) == pytest.approx(10 ** (0.6 * 57 / 20))


def test_the_pan_keeps_the_centre_as_it_is_and_folds_one_side_into_the_other_at_the_edges():
    centre = mix.pan_of(0)
    assert (centre["ll"], centre["lr"], centre["rr"]) == (1.0, 0.0, 1.0) and centre["rl"] == pytest.approx(0.0, abs=1e-15)
    assert mix.pan_of(-1) == pytest.approx({"ll": 1.0, "rl": 1.0, "lr": 0.0, "rr": 0.0}, abs=1e-15)
    assert mix.pan_of(1) == pytest.approx({"ll": 0.0, "rl": 0.0, "lr": 1.0, "rr": 1.0}, abs=1e-15)


def test_the_impulse_written_to_disk_is_a_float_stereo_wave_at_the_rate_asked(tmp_path):
    path = mix.write_impulse(tmp_path / "reverb.wav", 48000)

    data = path.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert struct.unpack("<HHIIHH", data[20:36]) == (3, 2, 48000, 384000, 8, 32)
    assert struct.unpack("<I", data[40:44])[0] == mix.impulse_length(48000) * 8
    assert len(data) == 44 + mix.impulse_length(48000) * 8


def test_the_delay_echoes_stop_under_the_floor():
    taps = mix.delay_taps()
    assert [round(tap["seconds"], 6) for tap in taps] == [0.32, 0.64, 0.96, 1.28, 1.6, 1.92, 2.24]
    assert taps[0]["gain"] == 1.0 and taps[-1]["gain"] >= 10 ** (-60 / 20) > taps[-1]["gain"] * 0.35
