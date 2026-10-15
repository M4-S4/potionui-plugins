from typing import Any, Callable, Dict

from . import PLUGIN_ID

DEFAULTS: Dict[str, Any] = {
    "history_depth": 10,
    "install_after_publish": True,
}

MAX_HISTORY_DEPTH = 100


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_depth(value: Any) -> int:
    return min(max(int(str(value).strip()), 1), MAX_HISTORY_DEPTH)


_PARSERS: Dict[str, Callable[[Any], Any]] = {
    "history_depth": _parse_depth,
    "install_after_publish": _parse_bool,
}


def parse_setting(key: str, raw: Any) -> Any:
    if key not in DEFAULTS:
        raise KeyError(f"preset-editor has no setting {key!r}")
    if raw is None or str(raw).strip() == "":
        return DEFAULTS[key]
    try:
        return _PARSERS[key](raw)
    except (ValueError, TypeError):
        return DEFAULTS[key]


def get_setting(key: str) -> Any:
    from src.plugin_api import PluginRepository

    row = PluginRepository().get_plugin_setting(PLUGIN_ID, key)
    return parse_setting(key, None if row is None else row.setting_value)
