import json

import pytest

from backend import drafts, history, paths
from tests.conftest import FIXTURES

NATIVE = FIXTURES / "minimal-native"


def test_archive_copies_the_preset_and_records_why(roots):
    stamp = history.archive(roots, NATIVE, preset_id="fixture-minimal-native", target_dir="Fixture/native", reason="publish")

    entry = roots.history / "fixture-minimal-native" / stamp
    assert paths.STAMP_RE.match(stamp)
    assert (entry / "preset.yml").read_bytes() == (NATIVE / "preset.yml").read_bytes()
    assert (entry / "modes" / "txt2img" / "tabs" / "main.yml").is_file()
    meta = json.loads((entry / drafts.HISTORY_META_FILE).read_text(encoding="utf-8"))
    assert meta == {
        "preset_id": "fixture-minimal-native",
        "target_dir": "Fixture/native",
        "reason": "publish",
        "archived_at": meta["archived_at"],
        "name": "Minimal native",
        "version": "1.0.0",
    }
    assert meta["archived_at"].endswith("Z")


def test_entries_are_listed_newest_first_and_rotation_keeps_the_newest(roots, monkeypatch):
    stamps = iter(["20261015T100000.000001", "20261015T100000.000002", "20261015T100000.000003"])
    monkeypatch.setattr(history, "stamp_now", lambda: next(stamps))
    for reason in ("publish", "publish", "delete"):
        history.archive(roots, NATIVE, preset_id="p-id", target_dir="M/v", reason=reason)
    (roots.history / "p-id" / "junk").mkdir()

    entries = history.list_entries(roots, "p-id")

    assert [(e["stamp"], e["reason"]) for e in entries] == [
        ("20261015T100000.000003", "delete"), ("20261015T100000.000002", "publish"), ("20261015T100000.000001", "publish"),
    ]
    assert history.rotate(roots, "p-id", 2) == ["20261015T100000.000001"]
    assert [e["stamp"] for e in history.list_entries(roots, "p-id")] == ["20261015T100000.000003", "20261015T100000.000002"]
    assert history.rotate(roots, "p-id", 0) == ["20261015T100000.000002"]


def test_a_stamp_collision_picks_the_next_stamp(roots, monkeypatch):
    stamps = iter(["20261015T100000.000001", "20261015T100000.000001", "20261015T100000.000002"])
    monkeypatch.setattr(history, "stamp_now", lambda: next(stamps))

    first = history.archive(roots, NATIVE, preset_id="p-id", target_dir="M/v", reason="publish")
    second = history.archive(roots, NATIVE, preset_id="p-id", target_dir="M/v", reason="publish")

    assert (first, second) == ("20261015T100000.000001", "20261015T100000.000002")


def test_entry_dir_validates_the_stamp_and_the_presence_of_a_manifest(roots):
    stamp = history.archive(roots, NATIVE, preset_id="p-id", target_dir="M/v", reason="publish")

    assert history.entry_dir(roots, "p-id", stamp) == roots.history / "p-id" / stamp
    for bad in ("../x", "20261015T100000.999999", stamp + "/x"):
        with pytest.raises(drafts.DraftError) as failure:
            history.entry_dir(roots, "p-id", bad)
        assert failure.value.code == "not_found"


def test_listing_an_unknown_preset_gives_nothing(roots):
    assert history.list_entries(roots, "never-seen") == []
    assert history.rotate(roots, "never-seen", 3) == []
