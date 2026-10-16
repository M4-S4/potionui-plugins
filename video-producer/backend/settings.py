import math
from typing import Any, Callable, Dict, Optional

from . import core_bridge

DRAFT_RESOLUTIONS = ("832x480", "960x544", "1280x720")

LOCALES = ("en", "fr")

LOCALE_KEY = "locale"

DEFAULTS: Dict[str, Any] = {
    "draft_resolution": "832x480",
    "max_parallel_jobs": 2,
    "export_dir_quota_mb": 2048,
}


def _parse_choice(*choices: str) -> Callable[[Any], str]:
    def parse(value: Any) -> str:
        value = str(value).strip().lower()
        if value not in choices:
            raise ValueError(value)
        return value

    return parse


def _parse_int(lo: int, hi: int) -> Callable[[Any], int]:
    def parse(value: Any) -> int:
        number = float(str(value).strip())
        if not math.isfinite(number) or not number.is_integer():
            raise ValueError(value)
        return min(max(int(number), lo), hi)

    return parse


_PARSERS: Dict[str, Callable[[Any], Any]] = {
    "draft_resolution": _parse_choice(*DRAFT_RESOLUTIONS),
    "max_parallel_jobs": _parse_int(1, 16),
    "export_dir_quota_mb": _parse_int(1, 1048576),
}


def parse_setting(key: str, raw: Any) -> Any:
    """Parse a stored setting string; an unset or invalid value falls back to the default."""
    if key not in DEFAULTS:
        raise KeyError(f"video-producer has no setting {key!r}")
    if raw is None or str(raw).strip() == "":
        return DEFAULTS[key]
    try:
        return _PARSERS[key](raw)
    except (ValueError, TypeError):
        return DEFAULTS[key]


def get_setting(key: str) -> Any:
    """The admin's value for one plugin setting, typed."""
    return parse_setting(key, core_bridge.get_plugin_setting(key))


def all_settings() -> Dict[str, Any]:
    """Every plugin setting, typed."""
    return {key: get_setting(key) for key in DEFAULTS}


def parse_locale(raw: Any) -> Optional[str]:
    """A supported locale code, or None."""
    value = str(raw).strip().lower() if raw is not None else ""
    return value if value in LOCALES else None


def user_locale(user_id: str) -> Optional[str]:
    """The locale the user chose in Video Producer, or None when they never chose one."""
    return parse_locale(core_bridge.get_plugin_setting(LOCALE_KEY, user_id=user_id))


def set_user_locale(user_id: str, locale: Any) -> str:
    """Save the user's locale; raises ValueError for an unsupported one."""
    if not isinstance(locale, str) or locale not in LOCALES:
        raise ValueError(locale)
    core_bridge.set_plugin_setting(LOCALE_KEY, locale, user_id=user_id)
    return locale
