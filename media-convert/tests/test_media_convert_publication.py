import shutil
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from src.features.generation.file_repository import FileRepository
from src.features.media.media_types import MediaTypeResolver
from src.features.media.records import Upload
from src.features.media.upload_repository import UploadRepository
from src.features.media_tools.jobs import MediaToolJobManager
from src.features.media_tools.repository import MediaToolParamsRepository
from src.features.media_tools.service import MediaToolService
from src.features.plugins.records import Plugin
from src.features.plugins.repository import PluginRepository
from src.platform.filesystem.storage_driver import LocalFileStorageDriver
from src.platform.media_tools import MediaToolRegistry
from src.platform.media_tools.ops import register_core_tools
from src.platform.plugins import runtime_registries
from src.platform.plugins.registry import PluginRegistry
from src.plugin_api.testing import scratch_database, use_database

from .conftest import PLUGIN_ROOT, make_audio, make_image, make_video, need_encoders

USER = "mc-user"
WAIT_SECONDS = 60


class Guard:
    def __init__(self):
        self.admits = []

    def check(self, request):
        return None

    def admit(self, request):
        self.admits.append(request)
        return []


@pytest.fixture
def library(tmp_path, monkeypatch):
    database = scratch_database(tmp_path / "db.sqlite")
    with use_database(database):
        with database.get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (id, username, email, password_hash, account_type) VALUES (?, ?, ?, ?, ?)",
                (USER, USER, "mc@example.com", "hash", "USER"),
            )
        marketplace, local = tmp_path / "marketplace", tmp_path / "local"
        marketplace.mkdir()
        shutil.copytree(PLUGIN_ROOT, local / "media-convert", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        tools = MediaToolRegistry()
        register_core_tools(tools)
        plugins = PluginRegistry(str(marketplace), str(local), media_tool_registry=tools)
        monkeypatch.setattr(runtime_registries, "_global_plugin_registry", plugins)
        assert plugins.enable_plugin("media-convert")
        storage = tmp_path / "storage"
        (storage / "uploads").mkdir(parents=True)
        guard = Guard()
        jobs = MediaToolJobManager()
        service = MediaToolService(
            registry=tools,
            params_repository=MediaToolParamsRepository(),
            upload_repository=UploadRepository(),
            file_repository=FileRepository(),
            media_type_resolver=MediaTypeResolver(),
            storage_driver=LocalFileStorageDriver(str(storage)),
            limit_guard=guard,
            jobs=jobs,
            scratch_root=tmp_path / "scratch",
            thumbnail_runner=lambda work: work(),
        )
        yield Library(service, guard, storage / "uploads", tools, jobs)
        jobs.join_all()


class Library:
    def __init__(self, service, guard, uploads, tools, jobs):
        self.service, self.guard, self.uploads, self.tools, self.jobs = service, guard, uploads, tools, jobs
        self.repo = UploadRepository()

    def add(self, path, name, kind):
        stored = self.uploads / f"src-{len(list(self.uploads.iterdir()))}{Path(path).suffix}"
        shutil.copyfile(path, stored)
        return self.repo.create(Upload(
            user_id=USER, filename=stored.name, original_filename=name, media_type=kind,
            mime_type=MediaTypeResolver().get_media_type(stored.suffix), file_size=stored.stat().st_size,
        ))

    def run(self, tool, params, *items):
        return self.service.run_blocking(
            USER, [{"tool": tool, "params": params}], [{"item_id": item.id} for item in items], timeout=WAIT_SECONDS,
        )

    def file(self, item):
        return self.uploads / item.filename

    def rows(self):
        return self.repo.list_for_user(USER, limit=100)

    def thumbnails(self, item):
        row = self.repo.get_by_id(item.id, USER)
        found = [getattr(row, f"thumbnail_{size}") for size in ("small", "medium", "large")]
        return [path for path in found if path and (self.uploads / path).is_file()]


def test_the_four_tools_register_from_the_manifest_for_the_library_and_the_history(library):
    ours = {"media-convert.image", "media-convert.video", "media-convert.audio", "media-convert.extract-audio"}
    for scope in ("library", "history"):
        listed = {tool.id: tool for tool in library.service.catalog(USER, scope=scope) if tool.source == "media-convert"}
        assert set(listed) == ours
        assert all(tool.runnable for tool in listed.values())
    assert not [tool for tool in library.service.catalog(USER, scope="field") if tool.source == "media-convert"]
    for_videos = {tool.id for tool in library.service.catalog(USER, kind="video", scope="library") if tool.source == "media-convert"}
    assert for_videos == {"media-convert.video", "media-convert.extract-audio"}


def test_a_png_published_as_webp_keeps_its_name_with_the_new_extension(library, source_dir):
    item = library.add(make_image(source_dir / "a.png", size=(120, 80), mode="RGBA", color=(10, 200, 10, 128)), "Chat.png", "image")

    result = library.run("media-convert.image", {"format": "webp"}, item)

    assert result.ok, result.error
    [made] = result.items
    assert made.original_filename == "Chat.webp"
    assert made.media_type == "image" and made.mime_type == "image/webp"
    assert made.filename.endswith(".webp") and made.id != item.id
    assert library.thumbnails(made)
    assert made.thumbnail_small or made.thumbnail_medium or made.thumbnail_large
    with Image.open(library.file(made)) as image:
        assert image.format == "WEBP" and image.size == (120, 80)
    assert library.guard.admits[-1].incoming_bytes == library.file(made).stat().st_size
    assert library.repo.get_by_id(item.id, USER).original_filename == "Chat.png"


def test_a_selection_of_three_converts_in_one_run_and_one_admission(library, source_dir):
    items = [
        library.add(make_image(source_dir / f"{index}.jpg", size=(40 + index, 30)), f"Photo {index}.jpg", "image")
        for index in range(3)
    ]

    result = library.run("media-convert.image", {"format": "png"}, *items)

    assert result.ok, result.error
    assert sorted(made.original_filename for made in result.items) == ["Photo 0.png", "Photo 1.png", "Photo 2.png"]
    assert len(library.guard.admits) == 1
    assert library.guard.admits[0].item_bytes == tuple(library.file(made).stat().st_size for made in result.items)
    assert len(library.rows()) == 6


def test_a_video_is_published_as_mp4_with_its_thumbnails(library, source_dir):
    need_encoders("libx264", "aac")
    item = library.add(make_video(source_dir / "a.mkv", size=(64, 48)), "Holiday.mkv", "video")

    result = library.run("media-convert.video", {"format": "mp4", "quality": "small"}, item)

    assert result.ok, result.error
    [made] = result.items
    assert made.original_filename == "Holiday.mp4" and made.mime_type == "video/mp4"
    row = library.repo.get_by_id(made.id, USER)
    assert row.media_type == "video" and row.width == 64 and row.height == 48
    assert library.thumbnails(made)


def test_sound_extracted_from_a_video_is_a_new_sound_item(library, source_dir):
    need_encoders("libx264", "aac", "libmp3lame")
    item = library.add(make_video(source_dir / "a.mp4"), "Holiday.mp4", "video")

    result = library.run("media-convert.extract-audio", {"format": "mp3"}, item)

    assert result.ok, result.error
    [made] = result.items
    assert made.original_filename == "Holiday.mp3"
    assert made.media_type == "audio" and made.mime_type == "audio/mpeg"


def test_a_sound_is_published_in_its_new_format(library, source_dir):
    need_encoders("libopus")
    item = library.add(make_audio(source_dir / "a.wav", codec_args=("-c:a", "pcm_s16le")), "Voice.wav", "audio")

    result = library.run("media-convert.audio", {"format": "ogg"}, item)

    assert result.ok, result.error
    assert result.items[0].original_filename == "Voice.ogg"
    assert result.items[0].mime_type == "audio/ogg"


def test_a_video_without_sound_is_refused_by_the_core_before_the_tool_runs(library, source_dir):
    item = library.add(make_video(source_dir / "a.mp4", audio=False), "Silent.mp4", "video")

    result = library.run("media-convert.extract-audio", {}, item)

    assert result.status == "failed"
    assert (result.error.code, result.error.message) == ("unsupported_media", "Extract sound needs a video with sound")
    assert len(library.rows()) == 1 and library.guard.admits == []


def test_a_refusal_shows_the_plugin_message_and_publishes_nothing(library, source_dir):
    frames = [Image.new("RGB", (16, 16), color) for color in ("red", "blue")]
    path = source_dir / "loop.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    item = library.add(path, "Loop.gif", "image")

    result = library.run("media-convert.image", {"format": "png"}, item)

    assert result.status == "failed"
    assert result.error.code == "tool_failed"
    assert result.error.message == "This image is animated (2 frames); Media Converter converts still images only"
    assert len(library.rows()) == 1 and library.guard.admits == []


def test_the_admin_thread_setting_reaches_ffmpeg(library, source_dir, monkeypatch):
    need_encoders("libx264", "aac")
    repository = PluginRepository()
    repository.create_plugin(Plugin(
        id="media-convert", name="Media Converter", version="0.1.0", type="backend-only", enabled=True,
        manifest_path=str(PLUGIN_ROOT / "manifest.yml"),
    ))
    repository.set_plugin_setting("media-convert", "ffmpeg_threads", "2")
    seen = []
    runner = type(library.tools.get("media-convert.video").impl)
    real = runner.run

    def spy(self, inputs, params, ctx):
        outputs = real(self, inputs, params, ctx)
        seen.extend(ctx.commands)
        return outputs

    monkeypatch.setattr(runner, "run", spy)
    item = library.add(make_video(source_dir / "a.mp4"), "Clip.mp4", "video")

    assert library.run("media-convert.video", {"format": "mov"}, item).ok

    assert seen and seen[-1][seen[-1].index("-threads") + 1] == "2"


def test_cancelling_a_run_kills_the_encode_and_publishes_nothing(library, source_dir):
    need_encoders("libx264", "aac")
    path = make_video(source_dir / "long.mp4", seconds=20.0, size=(640, 360), fps=25, source="testsrc2")
    item = library.add(path, "Long.mp4", "video")

    run_id = library.service.start_run(USER, [{"tool": "media-convert.video", "params": {"quality": "high"}}], [{"item_id": item.id}])
    deadline = time.monotonic() + WAIT_SECONDS
    while library.service.get_run(USER, run_id).progress <= 0.0 and time.monotonic() < deadline:
        threading.Event().wait(0.05)
    library.service.cancel_run(USER, run_id)
    run = library.jobs.wait(USER, run_id, WAIT_SECONDS)

    assert run.status == "cancelled"
    assert run.items == []
    assert len(library.rows()) == 1 and library.guard.admits == []
