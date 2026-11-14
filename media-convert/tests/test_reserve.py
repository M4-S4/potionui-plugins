from collections import namedtuple
from pathlib import Path

import pytest

from src.plugin_api.media_tools import ToolContext, ToolFailed

from tools import common

GB = 1 << 30
Usage = namedtuple("Usage", "total used free")


def test_quick_conversions_beside_a_slow_one_leave_the_reserve_free(tmp_path, monkeypatch):
    start_free = common.DISK_RESERVE + 8 * GB
    written = {}
    monkeypatch.setattr(common, "scratch_bytes", lambda folder: written.get(Path(folder), 0))
    monkeypatch.setattr(
        common.shutil, "disk_usage", lambda path: Usage(64 * GB, 0, start_free - sum(written.values()))
    )
    quick = ToolContext(tmp_path / "quick")
    slow = ToolContext(tmp_path / "slow")

    def write(ctx, size):
        written[ctx.scratch_dir] = written.get(ctx.scratch_dir, 0) + size

    first = common.make_room(quick, 4 * GB)
    other = common.make_room(slow, 4 * GB)
    write(quick, first.size)
    granted = [first.size, other.size]
    for _ in range(40):
        try:
            room = common.make_room(quick, 4 * GB)
        except ToolFailed:
            break
        granted.append(room.size)
        write(quick, room.size)
    else:
        pytest.fail("the quick conversions were never refused")
    write(slow, other.size)

    assert sum(granted) <= start_free - common.DISK_RESERVE
    assert start_free - sum(written.values()) >= common.DISK_RESERVE
