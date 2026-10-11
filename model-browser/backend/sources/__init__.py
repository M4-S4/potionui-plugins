"""The model catalogues the browser can search (PLAN.md §8), and their registry.

Phase 1 registers CivitAI. Hugging Face, OpenModelDB and CivArchive come in later phases:
they register here, and an opt-in source (CivArchive) is only enabled when its admin
setting is on.
"""

from typing import Callable, Dict, List

from .. import settings
from .base import DEFAULT_LIMIT, MAX_LIMIT, MAX_QUERY_LENGTH, SearchQuery, Source, UnknownSource
from .civitai import CivitaiSource

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MAX_QUERY_LENGTH",
    "SearchQuery",
    "Source",
    "UnknownSource",
    "enabled_sources",
    "get_source",
    "is_enabled",
    "register_source",
]

#: Source id -> factory, in the order the page lists them.
_FACTORIES: Dict[str, Callable[[], Source]] = {
    "civitai": CivitaiSource,
}
#: Sources an admin setting has to switch on (PLAN.md §8.5).
_OPT_IN_SETTINGS = {"civarchive": "enable_civarchive"}

_instances: Dict[str, Source] = {}


def register_source(source_id: str, factory: Callable[[], Source]) -> None:
    """Add (or replace) a source; its instance is created on first use."""
    _FACTORIES[source_id] = factory
    _instances.pop(source_id, None)


def is_enabled(source_id: str) -> bool:
    if source_id not in _FACTORIES:
        return False
    setting = _OPT_IN_SETTINGS.get(source_id)
    return setting is None or bool(settings.get_setting(setting))


def get_source(source_id: str) -> Source:
    """The enabled source `source_id`; raises `UnknownSource` for an unknown or disabled one."""
    if not is_enabled(source_id):
        raise UnknownSource(source_id)
    instance = _instances.get(source_id)
    if instance is None:
        instance = _instances[source_id] = _FACTORIES[source_id]()
    return instance


def enabled_sources() -> List[Source]:
    """Every enabled source, in registry order."""
    return [get_source(source_id) for source_id in _FACTORIES if is_enabled(source_id)]
