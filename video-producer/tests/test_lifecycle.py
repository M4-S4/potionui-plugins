import logging

import pytest

from backend import notifications, tables
from hooks import lifecycle_hooks, notification_hooks
from src.plugin_api import HookContext
from src.plugin_api.notifications import NotificationTypeRegistry, NotificationTypeSpec

LOGGER = "plugins.video-producer"


def _context(hook, subject="video-producer", data=None):
    return HookContext(
        hook_name=hook,
        plugin_id="video-producer",
        data={"plugin_id": subject} if data is None else data,
    )


def _table_names(db):
    with db.get_cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
        return {row["name"] for row in cursor.fetchall()}


def test_on_boot_creates_the_tables_and_returns_its_context(plugin_db):
    context = _context("plugin.lifecycle.boot")

    assert lifecycle_hooks.on_boot(context) is context
    assert _table_names(plugin_db) == set(tables.TABLE_NAMES)
    assert context.data == {"plugin_id": "video-producer"}


def test_on_boot_can_run_again_on_an_existing_database(plugin_db):
    lifecycle_hooks.on_boot(_context("plugin.lifecycle.boot"))
    with plugin_db.get_cursor() as cursor:
        cursor.execute("INSERT INTO video_producer_projects (id, user_id, name, doc) VALUES ('p-1', 'user-1', 'Trailer', '{}')")

    context = _context("plugin.lifecycle.boot")

    assert lifecycle_hooks.on_boot(context) is context
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM video_producer_projects")
        assert [row["id"] for row in cursor.fetchall()] == ["p-1"]


def test_on_boot_logs_the_tables_it_prepared(plugin_db, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        lifecycle_hooks.on_boot(_context("plugin.lifecycle.boot"))

    assert "Tables ready: " + ", ".join(tables.TABLE_NAMES) in caplog.text


def test_on_boot_logs_and_swallows_a_table_error(monkeypatch, caplog):
    def create_tables():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(tables, "create_tables", create_tables)
    context = _context("plugin.lifecycle.boot")

    assert lifecycle_hooks.on_boot(context) is context
    assert "Could not create the plugin's tables" in caplog.text
    assert "database is locked" in caplog.text
    assert "Tables ready" not in caplog.text


def test_on_ready_returns_its_context_untouched():
    context = _context("plugin.lifecycle.ready", data={"started": True})

    assert lifecycle_hooks.on_ready(context) is context
    assert context.data == {"started": True}


def test_on_disable_accepts_its_own_plugin_id(caplog):
    context = _context("plugin.lifecycle.disable")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        assert lifecycle_hooks.on_disable(context) is context

    assert "Disabled" in caplog.text


@pytest.mark.parametrize("data", [{"plugin_id": "civitai-provider"}, {"plugin_id": ""}, {"plugin_id": None}, {"other": 1}])
def test_on_disable_ignores_another_plugin(caplog, data):
    context = _context("plugin.lifecycle.disable", data=data)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        assert lifecycle_hooks.on_disable(context) is context

    assert "Disabled" not in caplog.text
    assert context.data == data


def test_the_notification_types_are_take_done_and_take_failed():
    assert (notifications.TAKE_DONE, notifications.TAKE_FAILED) == ("video-producer.take_done", "video-producer.take_failed")
    assert [item.key for item in notifications.TYPES] == ["video-producer.take_done", "video-producer.take_failed"]


def test_register_types_declares_both_types_on_the_registry():
    registry = NotificationTypeRegistry()
    context = _context("notification_type.register", data={"registry": registry})

    assert notification_hooks.register_types(context) is context

    assert [spec.key for spec in registry.all()] == ["video-producer.take_done", "video-producer.take_failed"]
    for spec in registry.all():
        assert isinstance(spec, NotificationTypeSpec)
        assert spec.label.startswith("Video Producer: ") and spec.description
        assert (spec.category, spec.default_enabled, spec.admin_only) == ("plugin", True, False)
    assert len({spec.label for spec in registry.all()}) == 2


def test_register_types_twice_declares_each_type_once(caplog):
    registry = NotificationTypeRegistry()
    context = _context("notification_type.register", data={"registry": registry})

    with caplog.at_level(logging.INFO, logger=LOGGER):
        notification_hooks.register_types(context)
        assert "Notification types declared: video-producer.take_done, video-producer.take_failed" in caplog.text
        caplog.clear()
        assert notification_hooks.register_types(context) is context

    assert len(registry.all()) == 2
    assert "Notification types declared: none new" in caplog.text


def test_register_types_keeps_a_type_another_party_already_declared():
    registry = NotificationTypeRegistry()
    registry.register(NotificationTypeSpec(key="video-producer.take_done", label="Already there"))

    notification_hooks.register_types(_context("notification_type.register", data={"registry": registry}))

    assert registry.get("video-producer.take_done").label == "Already there"
    assert registry.has("video-producer.take_failed")


@pytest.mark.parametrize("data", [{}, {"registry": None}, None])
def test_register_types_without_a_registry_warns_and_returns_its_context(caplog, data):
    context = HookContext(hook_name="notification_type.register", plugin_id="system", data=data)

    assert notification_hooks.register_types(context) is context
    assert "carried no registry" in caplog.text


def test_register_types_swallows_a_registry_that_is_not_one(caplog):
    context = _context("notification_type.register", data={"registry": "not one"})

    assert notification_hooks.register_types(context) is context
    assert "Could not declare the plugin's notification types" in caplog.text
