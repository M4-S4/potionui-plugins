import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import core_bridge
from src.plugin_api import AccountType, User
from tests.conftest import FIXTURES

ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


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
    repository = SimpleNamespace(list_all_presets=lambda: [{"id": "a"}, {"id": "b"}])
    installed = set()
    collaborators = SimpleNamespace(db_repo=SimpleNamespace())
    container = SimpleNamespace(
        preset_template_loader=loader, file_preset_repository=repository, preset_collaborators=collaborators
    )
    monkeypatch.setattr(core_bridge, "get_container", lambda: container)
    monkeypatch.setattr(core_bridge, "preset_template", lambda preset_id: {"id": preset_id})
    monkeypatch.setattr(
        core_bridge, "preset_install_state", lambda preset_id: SimpleNamespace(installed=preset_id in installed, assigned=False)
    )
    container.installed = installed
    return container


def test_the_bridge_reads_the_three_container_attributes(container):
    assert core_bridge.preset_loader() is container.preset_template_loader
    assert core_bridge.file_repository() is container.file_preset_repository
    assert core_bridge.collaborators() is container.preset_collaborators


def test_preset_roots_are_paths(container):
    assert core_bridge.preset_roots() == [Path("content/presets/marketplace"), Path("content/presets/local")]


def test_find_preset_asks_the_exported_preset_template_and_the_catalog_the_file_repository(container):
    assert core_bridge.find_preset("abc") == {"id": "abc"}
    assert [item["id"] for item in core_bridge.catalog()] == ["a", "b"]


def test_is_installed_reads_the_exported_install_state(container):
    assert core_bridge.is_installed("x") is False
    container.installed.add("x")
    assert core_bridge.is_installed("x") is True


def test_install_and_uninstall_go_through_the_exported_operations(container, monkeypatch):
    calls = []
    monkeypatch.setattr(core_bridge.preset_operations, "install_preset", lambda collaborators, preset_id, user: calls.append(("install", collaborators, preset_id, user.id)) or {"id": preset_id})
    monkeypatch.setattr(core_bridge.preset_operations, "uninstall_preset", lambda collaborators, preset_id, user: calls.append(("uninstall", collaborators, preset_id, user.id)) or "done")

    assert core_bridge.install_preset("x", ADMIN) == {"id": "x"}
    assert core_bridge.uninstall_preset("x", ADMIN) == "done"
    assert calls == [
        ("install", container.preset_collaborators, "x", "admin-1"), ("uninstall", container.preset_collaborators, "x", "admin-1"),
    ]


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


def _request(*headers):
    from fastapi import Request

    return Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": [(k.encode(), v.encode()) for k, v in headers]})


def test_media_token_prefers_the_bearer_and_falls_back_to_the_media_cookie():
    assert core_bridge.media_token(_request(("authorization", "Bearer abc"), ("cookie", "potionui_media_0123abcd4567=from-cookie"))) == "abc"
    assert core_bridge.media_token(_request(("cookie", "other=1; potionui_media_0123abcd4567=from-cookie"))) == "from-cookie"
    assert core_bridge.media_token(_request(("cookie", "potionui_media=plain"))) == "plain"
    assert core_bridge.media_token(_request(("authorization", "Bearer "), ("cookie", "potionui_mediax=no; session=1"))) is None
    assert core_bridge.media_token(_request()) is None


def test_media_viewer_validates_the_token_off_the_event_loop(monkeypatch):
    seen = []

    def authenticate(token):
        seen.append((token, threading.current_thread()))
        return (ADMIN, None) if token == "good" else (None, "Invalid token")

    monkeypatch.setattr(core_bridge, "authenticate_websocket_token", authenticate)

    assert asyncio.run(core_bridge.media_viewer(_request(("cookie", "potionui_media_1=good")))) is ADMIN
    assert asyncio.run(core_bridge.media_viewer(_request(("authorization", "Bearer bad")))) is None
    assert asyncio.run(core_bridge.media_viewer(_request())) is None
    assert [token for token, _ in seen] == ["good", "bad"]
    assert all(thread is not threading.main_thread() for _, thread in seen)


def test_lint_async_gives_the_same_report_from_a_thread(monkeypatch):
    threads = []

    def lint(path):
        threads.append(threading.current_thread())
        return ["e"], ["w"]

    monkeypatch.setattr(core_bridge, "lint", lint)

    assert asyncio.run(core_bridge.lint_async(Path("x"))) == (["e"], ["w"])
    assert threads[0] is not threading.main_thread()
