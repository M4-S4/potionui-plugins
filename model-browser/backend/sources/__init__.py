from typing import Callable, Dict, List

from .base import MAX_LIMIT, MAX_QUERY_LENGTH, SearchQuery, Source, UnknownSource
from .civitai import CivitaiSource
from .huggingface import HuggingFaceSource
from .openmodeldb import OpenModelDBSource

__all__ = [
    "MAX_LIMIT",
    "MAX_QUERY_LENGTH",
    "SearchQuery",
    "Source",
    "UnknownSource",
    "enabled_sources",
    "get_source",
]

_FACTORIES: Dict[str, Callable[[], Source]] = {
    "civitai": CivitaiSource,
    "huggingface": HuggingFaceSource,
    "openmodeldb": OpenModelDBSource,
}

_instances: Dict[str, Source] = {}


def is_enabled(source_id: str) -> bool:
    return source_id in _FACTORIES


def get_source(source_id: str) -> Source:
    if not is_enabled(source_id):
        raise UnknownSource(source_id)
    instance = _instances.get(source_id)
    if instance is None:
        instance = _instances[source_id] = _FACTORIES[source_id]()
    return instance


def enabled_sources() -> List[Source]:
    return [get_source(source_id) for source_id in _FACTORIES]
