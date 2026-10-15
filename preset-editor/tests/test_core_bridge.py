import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import core_bridge
from tests.conftest import FIXTURES


class _Loader:
    def __init__(self):
        self.reloads = 0

    def all_preset_roots(self):
        return ["content/presets/marketplace", Path("content/presets/local")]

    def reload(self):
        self.reloads += 1


@pytest.fixture
def container(monkeypatch):
    loader = _Loader()
    repository = SimpleNamespace(find_preset_by_id=lambda preset_id: {"id": preset_id})
    collaborators = object()
    container = SimpleNamespace(
        preset_template_loader=loader, file_preset_repository=repository, preset_collaborators=collaborators
    )
    monkeypatch.setattr(core_bridge, "get_container", lambda: container)
    return container


def test_the_bridge_reads_the_three_container_attributes(container):
    assert core_bridge.preset_loader() is container.preset_template_loader
    assert core_bridge.file_repository() is container.file_preset_repository
    assert core_bridge.collaborators() is container.preset_collaborators


def test_preset_roots_are_paths(container):
    assert core_bridge.preset_roots() == [Path("content/presets/marketplace"), Path("content/presets/local")]


def test_find_preset_asks_the_file_repository(container):
    assert core_bridge.find_preset("abc") == {"id": "abc"}


def test_reload_presets_reloads_the_loader(container):
    core_bridge.reload_presets()

    assert container.preset_template_loader.reloads == 1


def test_reload_presets_async_runs_off_the_event_loop(container, monkeypatch):
    threads = []

    def reload():
        threads.append(threading.current_thread())

    monkeypatch.setattr(core_bridge, "reload_presets", reload)

    asyncio.run(core_bridge.reload_presets_async())

    assert threads and threads[0] is not threading.main_thread()


@pytest.mark.parametrize("fixture", ["minimal-native", "minimal-cloud"])
def test_the_fixtures_lint_without_errors(fixture):
    errors, warnings = core_bridge.lint(FIXTURES / fixture)

    assert errors == []
    assert len(warnings) == 1 and "no tests.yml" in warnings[0]


def test_lint_reports_a_broken_preset_as_errors(tmp_path):
    preset = tmp_path / "broken"
    preset.mkdir()
    (preset / "preset.yml").write_text('schema: 1\nid: "broken-preset"\nname: "Broken"\n', encoding="utf-8")

    errors, warnings = core_bridge.lint(preset)

    assert errors and all(error.startswith("[ERROR] ") and str(preset / "preset.yml") in error for error in errors)


def test_lint_async_gives_the_same_report_from_a_thread(monkeypatch):
    threads = []

    def lint(path):
        threads.append(threading.current_thread())
        return ["e"], ["w"]

    monkeypatch.setattr(core_bridge, "lint", lint)

    assert asyncio.run(core_bridge.lint_async(Path("x"))) == (["e"], ["w"])
    assert threads[0] is not threading.main_thread()
