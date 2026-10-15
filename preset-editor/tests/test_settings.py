from types import SimpleNamespace

import pytest

from backend import settings


@pytest.mark.parametrize(
    "key, raw, expected",
    [
        ("history_depth", None, 10),
        ("history_depth", "", 10),
        ("history_depth", "3", 3),
        ("history_depth", "0", 1),
        ("history_depth", "500", 100),
        ("history_depth", "ten", 10),
        ("install_after_publish", None, True),
        ("install_after_publish", "false", False),
        ("install_after_publish", "False", False),
        ("install_after_publish", "0", False),
        ("install_after_publish", "True", True),
        ("install_after_publish", "yes", True),
    ],
)
def test_settings_are_parsed_with_their_defaults_and_bounds(key, raw, expected):
    assert settings.parse_setting(key, raw) == expected


def test_an_unknown_setting_is_an_error():
    with pytest.raises(KeyError):
        settings.parse_setting("nope", "1")


def test_get_setting_reads_the_plugin_row(monkeypatch):
    import src.plugin_api

    rows = {"history_depth": SimpleNamespace(setting_value="4")}
    monkeypatch.setattr(
        src.plugin_api, "PluginRepository",
        lambda: SimpleNamespace(get_plugin_setting=lambda plugin_id, key: rows.get(key) if plugin_id == "preset-editor" else None),
    )

    assert settings.get_setting("history_depth") == 4
    assert settings.get_setting("install_after_publish") is True
