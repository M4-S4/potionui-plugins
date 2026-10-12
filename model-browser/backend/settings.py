"""Typed access to the plugin's admin settings (manifest `settings:`) and to the one core
user setting the plugin reads, `media_nsfw_filter_mode` (PLAN.md §5.1).

The core stores plugin settings as strings and does not seed the manifest defaults, so
every read goes through `DEFAULTS` and a parser: an unreadable or unknown value falls
back to the default, and `cache_ttl_minutes` is clamped to its range, rather than
breaking a request.
"""

from typing import Any, Callable, Dict, List
from urllib.parse import urlsplit

from . import PLUGIN_ID

CORE_USER_NSFW_SETTING = "media_nsfw_filter_mode"
USER_NSFW_MODES = ("show", "blur", "hide")

DEFAULTS: Dict[str, Any] = {
    "nsfw_ceiling": "inherit",            # inherit | blur | blocked (PLAN.md §5.1)
    "nsfw_max_level": 2,                  # 1 PG | 2 PG-13 | 4 R | 8 X (§5.3)
    "hide_poi": False,                    # hide CivitAI models flagged `poi` (real people); see BOOLEAN_SETTINGS
    "civitai_api_base": "https://civitai.com/api/v1",
    "enable_civarchive": False,
    "cache_ttl_minutes": 10,
}


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _parse_choice(*choices: str) -> Callable[[str], str]:
    def parse(value: str) -> str:
        value = str(value).strip().lower()
        if value not in choices:
            raise ValueError(value)
        return value

    return parse


def _parse_int(lo: int, hi: int, allowed: tuple = ()) -> Callable[[str], int]:
    def parse(value: str) -> int:
        number = int(str(value).strip())
        if allowed and number not in allowed:
            raise ValueError(value)
        return min(max(number, lo), hi)

    return parse


def _parse_api_base(value: str) -> str:
    value = str(value).strip().rstrip("/")
    # urlsplit raises ValueError for a URL it cannot parse ("https://[::1/api").
    if not value.startswith("https://") or not urlsplit(value).netloc:
        raise ValueError(value)
    return value


#: The yes/no settings. The manifest declares them as a two-option `select` ("true" /
#: "false") rather than `boolean`: PotionUI's admin form (0.0.15, `PluginsTab.svelte`) stores
#: a boolean as `str(value)` ("False") and shows any non-empty stored string as checked, so
#: a `boolean` switched off came back on after every save. A select is stored and shown as
#: the string it was given. Rows written while they were `boolean` hold "True" / "False":
#: `normalise_stored_booleans` rewrites them at boot so the form shows the stored choice.
BOOLEAN_SETTINGS = ("hide_poi", "enable_civarchive")

_PARSERS: Dict[str, Callable[[str], Any]] = {
    "nsfw_ceiling": _parse_choice("inherit", "blur", "blocked"),
    "nsfw_max_level": _parse_int(1, 8, allowed=(1, 2, 4, 8)),
    "hide_poi": _parse_bool,
    "civitai_api_base": _parse_api_base,
    "enable_civarchive": _parse_bool,
    "cache_ttl_minutes": _parse_int(1, 1440),
}


def parse_setting(key: str, raw: Any) -> Any:
    """`raw` (what the core stored) as the typed value, or the default when it is unset or invalid."""
    if key not in DEFAULTS:
        raise KeyError(f"model-browser has no setting {key!r}")
    if raw is None or str(raw).strip() == "":
        return DEFAULTS[key]
    try:
        return _PARSERS[key](raw)
    except (ValueError, TypeError):
        return DEFAULTS[key]


def get_setting(key: str) -> Any:
    """The admin's value for one of the plugin's settings, typed, with the manifest default as fallback."""
    from src.plugin_api import PluginRepository

    row = PluginRepository().get_plugin_setting(PLUGIN_ID, key)
    return parse_setting(key, None if row is None else row.setting_value)


def normalise_stored_booleans() -> List[str]:
    """Rewrite the stored rows of `BOOLEAN_SETTINGS` that are not "true" / "false" (the manifest's
    option values) as the lowercase form of what they parse to, and return the keys rewritten.

    A row the core wrote while the setting was a `boolean` holds "True" / "False": the plugin
    reads it fine, but the admin form's select shows no choice until the admin clicks one. A
    missing row is left alone (the form shows the manifest default). The value's meaning never
    changes, so no audit entry is recorded.
    """
    from src.plugin_api import PluginRepository

    repository = PluginRepository()
    rewritten: List[str] = []
    for key in BOOLEAN_SETTINGS:
        row = repository.get_plugin_setting(PLUGIN_ID, key)
        if row is None or row.setting_value in ("true", "false"):
            continue
        value = "true" if parse_setting(key, row.setting_value) else "false"
        repository.set_plugin_setting(plugin_id=PLUGIN_ID, setting_key=key, setting_value=value)
        rewritten.append(key)
    return rewritten


def user_nsfw_mode(user_id: str) -> str:
    """The user's own display mode for NSFW media (`media_nsfw_filter_mode`), `blur` when unset or unknown."""
    from src.plugin_api import SettingRepository

    value = SettingRepository().get_user_setting_by_key(user_id, CORE_USER_NSFW_SETTING)
    value = str(value).strip().lower() if value is not None else ""
    return value if value in USER_NSFW_MODES else "blur"
