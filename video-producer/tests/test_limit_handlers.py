import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from backend import core_bridge, limit_handlers, limits
from src.plugin_api.limits import AdmissionRequest, MeasureContext

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

UNLIMITED = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}


class _Events:
    def __init__(self, total):
        self._total = total
        self.recorded = []
        self.refunded = []

    def total(self):
        return self._total

    def record(self, units=1, ref_id=None):
        self.recorded.append((units, ref_id))
        return "event"

    def refund(self, ref_id):
        self.refunded.append(ref_id)
        return 0


def _measure_context(events):
    return MeasureContext(
        user_id="user-1", kind=limits.GPU_MINUTES, window_start=None, window_end=None, events=events
    )


def _manifest_kind():
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))
    [kind] = manifest["limit_kinds"]
    return kind


@pytest.mark.parametrize("point", ["submit", "upload", "download", "anything"])
def test_the_core_is_never_asked_to_apply_the_kind(point):
    assert limit_handlers.never_applies(AdmissionRequest(point=point, user_id="user-1")) is False


def test_never_applies_does_not_look_at_its_request():
    assert limit_handlers.never_applies(SimpleNamespace()) is False
    assert limit_handlers.never_applies(None) is False


@pytest.mark.parametrize("total, expected", [(0, 0.0), (3, 3.0), (12.5, 12.5), (0.25, 0.25)])
def test_the_usage_is_the_ledger_total_of_the_window(total, expected):
    usage = limit_handlers.ledger_total(SimpleNamespace(events=SimpleNamespace(total=lambda: total)))

    assert usage == expected
    assert isinstance(usage, float)


def test_the_usage_reads_the_events_of_a_measure_context_without_recording_any():
    events = _Events(total=42)

    assert limit_handlers.ledger_total(_measure_context(events)) == 42.0
    assert events.recorded == [] and events.refunded == []


def test_the_manifest_names_the_two_handlers_this_module_defines():
    kind = _manifest_kind()

    assert kind["measure_handler"] == "backend.limit_handlers.ledger_total"
    assert kind["applies_handler"] == "backend.limit_handlers.never_applies"
    assert limit_handlers.ledger_total.__name__ == "ledger_total"
    assert limit_handlers.never_applies.__name__ == "never_applies"


def test_the_gpu_minutes_kind_is_the_one_the_manifest_declares():
    assert limits.GPU_MINUTES == "video-producer.gpu_minutes"
    assert limits.GPU_MINUTES == _manifest_kind()["key"]


def test_gpu_minutes_status_asks_the_bridge_for_that_user_and_that_kind(monkeypatch):
    asked = []
    status = {"limit": 600, "used": 125.5, "remaining": 474.5, "exempt": False, "resets_at": "2026-11-01T00:00:00+00:00"}

    def limit_status(user_id, kind):
        asked.append((user_id, kind))
        return status

    monkeypatch.setattr(core_bridge, "limit_status", limit_status)

    assert limits.gpu_minutes_status("user-9") is status
    assert asked == [("user-9", "video-producer.gpu_minutes")]


def test_gpu_minutes_status_of_an_exempt_admin_is_passed_through(monkeypatch):
    exempt = {"limit": 600, "used": None, "remaining": None, "exempt": True, "resets_at": None}
    monkeypatch.setattr(core_bridge, "limit_status", lambda user_id, kind: exempt)

    assert limits.gpu_minutes_status("admin-1") == exempt


def test_gpu_minutes_status_is_unlimited_when_the_plans_cannot_be_read(monkeypatch, caplog):
    def no_container(user_id, kind):
        raise RuntimeError("AppContainer not initialized yet")

    monkeypatch.setattr(core_bridge, "api_limits", SimpleNamespace(limit_status=no_container))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        assert limits.gpu_minutes_status("user-1") == UNLIMITED

    assert "treating it as unlimited" in caplog.text
    assert "video-producer.gpu_minutes" in caplog.text
