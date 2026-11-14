import logging
import threading
import time
from collections import namedtuple
from pathlib import Path

import pytest
from PIL import Image

from src.plugin_api import limits
from src.plugin_api.media_tools import ToolCancelled, ToolContext, ToolFailed

from tools import common
from tools.audio import ConvertAudio
from tools.extract_audio import ExtractAudio
from tools.image import ConvertImage
from tools.video import ConvertVideo

from .conftest import make_audio, make_video, noisy_image, params_for, piped

Usage = namedtuple("Usage", "total used free")
MB = common.MEGABYTE
DISK_FULL = "The server cannot take this conversion now; try again later or ask an admin"


class Watched(set):
    def __init__(self):
        super().__init__()
        self.added = []

    def add(self, grant):
        self.added.append((grant.size, grant.folder))
        super().add(grant)


class Writer:
    def __init__(self, error=None):
        self.commands = []
        self.error = error

    def run(self, args, *, duration=None, on_progress=None, is_cancelled=None):
        self.commands.append(list(args))
        if self.error is not None:
            raise self.error
        size = int(args[args.index("-fs") + 1])
        with open(args[-1], "wb") as handle:
            handle.truncate(size)


@pytest.fixture
def watched(monkeypatch):
    grants = Watched()
    monkeypatch.setattr(common, "GRANTS", grants)
    return grants


def free_space(monkeypatch, free):
    monkeypatch.setattr(common.shutil, "disk_usage", lambda path: Usage(free * 4, free * 3, free))


def fill(folder, size, name="written.bin"):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / name).open("wb") as handle:
        handle.truncate(size)


@pytest.fixture
def sources(source_dir):
    return {
        "image": noisy_image(source_dir / "a.png", size=(64, 64)),
        "video": make_video(source_dir / "a.mp4"),
        "audio": make_audio(source_dir / "a.mp3", codec_args=("-c:a", "libmp3lame")),
    }


def cases(sources):
    return {
        "image": (ConvertImage(), sources["image"], "image", params_for("media-convert.image", format="jpeg")),
        "video": (ConvertVideo(), sources["video"], "video", params_for("media-convert.video", format="mov")),
        "audio": (ConvertAudio(), sources["audio"], "audio", params_for("media-convert.audio", format="flac")),
        "extract": (ExtractAudio(), sources["video"], "video", params_for("media-convert.extract-audio", format="wav")),
    }


TOOLS = ("image", "video", "audio", "extract")
ENCODED = ("video", "audio", "extract")


def test_a_granted_room_is_taken_from_the_disk_until_it_is_written(tmp_path, monkeypatch):
    free_space(monkeypatch, common.DISK_RESERVE + 1000 * MB)
    first = ToolContext(tmp_path / "first")
    second = ToolContext(tmp_path / "second")

    one = common.make_room(first, 4 << 30)
    assert one.size == 500 * MB
    assert common.promised() == 500 * MB

    two = common.make_room(second, 4 << 30)
    assert two.size == 250 * MB
    assert common.promised() == 750 * MB
    common.release(one)
    common.release(two)


def test_what_a_conversion_already_wrote_is_not_counted_twice(tmp_path, monkeypatch):
    free_space(monkeypatch, common.DISK_RESERVE + 1000 * MB)
    ctx = ToolContext(tmp_path / "scratch")
    fill(ctx.scratch_dir, 30 * MB, "earlier.bin")

    room = common.make_room(ctx, 4 << 30)
    assert common.promised() == room.size == 500 * MB

    (ctx.scratch_dir / "earlier.bin").unlink()
    assert common.promised() == 500 * MB

    fill(ctx.scratch_dir, 120 * MB, "out-001.wav")
    assert common.promised() == 410 * MB

    fill(ctx.scratch_dir, 600 * MB, "out-001.wav")
    assert common.promised() == 0
    common.release(room)


def test_a_released_room_stops_counting_and_a_second_release_changes_nothing(tmp_path, monkeypatch, watched):
    free_space(monkeypatch, common.DISK_RESERVE + 1000 * MB)
    first = common.make_room(ToolContext(tmp_path / "first"), 4 << 30)
    second = common.make_room(ToolContext(tmp_path / "second"), 4 << 30)

    common.release(first)
    assert common.promised() == 250 * MB
    common.release(first)
    common.release(common.Room(MB, "file"))
    assert common.promised() == 250 * MB
    common.release(second)
    assert common.promised() == 0
    assert len(watched) == 0
    third = common.make_room(ToolContext(tmp_path / "third"), 4 << 30)
    common.release(third)
    assert third.size == 500 * MB


def test_an_image_counts_the_largest_result_it_may_write(tmp_path, monkeypatch, watched):
    free_space(monkeypatch, common.DISK_RESERVE + 1000 * MB)
    monkeypatch.setattr(common, "RUN_BUDGET", 2 * MB)
    room = common.make_room(ToolContext(tmp_path / "scratch"), 40 * MB, unstoppable=40 * MB)

    assert room.size == 2 * MB
    assert watched.added == [(40 * MB, tmp_path / "scratch")]
    assert common.promised() == 40 * MB
    common.release(room)


def test_a_refused_room_is_never_counted(tmp_path, monkeypatch, watched):
    free_space(monkeypatch, common.DISK_RESERVE + MB)

    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        common.make_room(ToolContext(tmp_path / "scratch"), 4 << 30)

    assert watched.added == []
    assert common.promised() == 0


def test_rooms_asked_at_the_same_moment_never_share_the_same_free_space(tmp_path, monkeypatch):
    free_space(monkeypatch, common.DISK_RESERVE + 800 * MB)
    measure = common.scratch_bytes

    def slow(folder):
        time.sleep(0.05)
        return measure(folder)

    monkeypatch.setattr(common, "scratch_bytes", slow)
    start = threading.Barrier(4)
    given = []

    def ask(index):
        start.wait()
        given.append(common.make_room(ToolContext(tmp_path / f"run-{index}"), 4 << 30))

    workers = [threading.Thread(target=ask, args=(index,)) for index in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    for room in given:
        common.release(room)
    assert sorted((room.size for room in given), reverse=True) == [400 * MB, 200 * MB, 100 * MB, 50 * MB]


def test_what_another_conversion_writes_while_the_disk_is_measured_never_eats_the_reserve(tmp_path, monkeypatch):
    start = common.DISK_RESERVE + 1010 * MB
    burst = 20 * MB
    other = tmp_path / "other"
    state = {"written": 0}
    monkeypatch.setattr(common.shutil, "disk_usage", lambda path: Usage(64 << 30, 0, start - state["written"]))

    def walk(folder):
        if Path(folder) == other:
            state["written"] += burst
            return state["written"]
        return 0

    monkeypatch.setattr(common, "scratch_bytes", walk)
    held = common.Grant(other, 1000 * MB, 0)
    common.GRANTS.add(held)

    room = common.make_room(ToolContext(tmp_path / "new"), 4 << 30)
    common.release(room)
    common.GRANTS.discard(held)

    assert room.size == 5 * MB
    assert start - 1000 * MB - room.size >= common.DISK_RESERVE


def test_the_plan_of_the_user_is_read_before_the_disk_room_is_locked(tmp_path, monkeypatch):
    seen = []

    def status(user_id, kind):
        seen.append(common.GRANTS_LOCK.locked())
        return limits.LimitStatus(kind=kind, limit=500 * MB, used=0)

    monkeypatch.setattr(limits, "limit_status", status)
    room = common.make_room(ToolContext(tmp_path / "scratch", user_id="someone"), 4 << 30)
    common.release(room)

    assert room == common.Room(500 * MB, "storage")
    assert seen == [False, False]


def test_a_disk_refusal_logs_what_is_promised_to_the_conversions_still_running(tmp_path, monkeypatch, caplog):
    free = common.DISK_RESERVE + 3 * MB
    free_space(monkeypatch, free)
    held = common.make_room(ToolContext(tmp_path / "other"), 4 << 30)

    with caplog.at_level(logging.WARNING, logger="plugins.media-convert"):
        with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
            common.make_room(ToolContext(tmp_path / "scratch"), 4 << 30)
    common.release(held)

    assert held.size == 3 * MB // 2
    [line] = [record.getMessage() for record in caplog.records if record.name == "plugins.media-convert"]
    assert line == (
        "Media Converter refused a conversion for lack of disk space: "
        f"{free} bytes free, {2 << 30} bytes kept free, {held.size} bytes promised to conversions still running, "
        f"{3 * MB // 4} bytes for this conversion, at least {MB} bytes needed"
    )


@pytest.mark.parametrize("name", TOOLS)
def test_a_finished_conversion_leaves_no_room_counted(tmp_path, sources, watched, name):
    tool, path, kind, params = cases(sources)[name]
    ctx = ToolContext(tmp_path / "scratch")

    [made] = tool.run([ctx.probe(path, kind)], params, ctx)

    assert made.path.is_file()
    assert len(watched.added) == 1
    assert len(watched) == 0
    assert common.promised() == 0


@pytest.mark.parametrize("name", TOOLS)
def test_a_conversion_refused_before_encoding_counts_no_room(tmp_path, sources, monkeypatch, watched, name):
    tool, path, kind, params = cases(sources)[name]
    free_space(monkeypatch, common.DISK_RESERVE + MB)
    ctx = ToolContext(tmp_path / "scratch")

    with pytest.raises(ToolFailed, match=f"^{DISK_FULL}$"):
        tool.run([ctx.probe(path, kind)], params, ctx)

    assert watched.added == []
    assert ctx.commands == []


@pytest.mark.parametrize("name", ENCODED)
def test_a_result_refused_after_encoding_gives_its_room_back(tmp_path, sources, monkeypatch, watched, name):
    tool, path, kind, params = cases(sources)[name]
    monkeypatch.setattr(common, "RUN_BUDGET", 2 * MB)
    ctx = ToolContext(tmp_path / "scratch", runner=Writer())

    with pytest.raises(ToolFailed, match="convert fewer items at a time"):
        tool.run([ctx.probe(path, kind)], params, ctx)

    assert len(ctx.commands) == 1
    assert len(watched.added) == 1
    assert len(watched) == 0


def test_an_image_refused_after_saving_gives_its_room_back(tmp_path, source_dir, monkeypatch, watched):
    picture = noisy_image(source_dir / "big.jpg", size=(1024, 1024), quality=95)
    monkeypatch.setattr(common, "RUN_BUDGET", common.MIN_ROOM)
    ctx = ToolContext(tmp_path / "scratch")

    with pytest.raises(ToolFailed, match="convert fewer items at a time"):
        ConvertImage().run([ctx.probe(picture, "image")], params_for("media-convert.image", format="png"), ctx)

    assert len(watched.added) == 1
    assert len(watched) == 0


@pytest.mark.parametrize("name", TOOLS)
def test_a_conversion_cancelled_while_its_room_is_held_gives_it_back(tmp_path, sources, watched, name):
    tool, path, kind, params = cases(sources)[name]
    ctx = ToolContext(tmp_path / "scratch", is_cancelled=lambda: bool(watched))
    media = ctx.probe(path, kind)

    with pytest.raises(ToolCancelled):
        tool.run([media], params, ctx)

    assert len(watched.added) == 1
    assert len(watched) == 0


@pytest.mark.parametrize("name", ENCODED)
def test_an_encoder_that_breaks_gives_the_room_back(tmp_path, sources, watched, name):
    tool, path, kind, params = cases(sources)[name]
    ctx = ToolContext(tmp_path / "scratch", runner=Writer(RuntimeError("the encoder broke")))

    with pytest.raises(RuntimeError, match="the encoder broke"):
        tool.run([ctx.probe(path, kind)], params, ctx)

    assert len(watched.added) == 1
    assert len(watched) == 0


def test_an_image_that_cannot_be_saved_gives_the_room_back(tmp_path, sources, monkeypatch, watched):
    ctx = ToolContext(tmp_path / "scratch")
    media = ctx.probe(sources["image"], "image")

    def broken(self, *args, **kwargs):
        raise OSError("the disk went away")

    monkeypatch.setattr(Image.Image, "save", broken)

    with pytest.raises(OSError, match="the disk went away"):
        ConvertImage().run([media], params_for("media-convert.image", format="jpeg"), ctx)

    assert len(watched.added) == 1
    assert len(watched) == 0


def test_a_long_sound_beside_a_finished_one_gets_the_room_the_first_gave_back(tmp_path, source_dir, monkeypatch, watched):
    path = piped(source_dir / "noise.flac", "-f", "lavfi", "-i", "anoisesrc=d=2:c=white:r=44100", "-ac", "2", "-c:a", "flac", "-f", "flac")
    free_space(monkeypatch, common.DISK_RESERVE + 40 * MB)
    held = common.make_room(ToolContext(tmp_path / "other"), 4 << 30)
    assert held.size == 20 * MB
    ctx = ToolContext(tmp_path / "scratch")

    [made] = ConvertAudio().run([ctx.probe(path, "audio")], params_for("media-convert.audio", format="wav"), ctx)
    assert ctx.commands[0][ctx.commands[0].index("-fs") + 1] == str(10 * MB)

    common.release(held)
    again = ToolContext(tmp_path / "again")
    ConvertAudio().run([again.probe(path, "audio")], params_for("media-convert.audio", format="wav"), again)
    assert again.commands[0][again.commands[0].index("-fs") + 1] == str(20 * MB)
    assert made.path.stat().st_size < 10 * MB
    assert len(watched) == 0

