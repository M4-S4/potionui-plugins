"""What every source implements, and the search request the routes hand it (PLAN.md §7.3).

A source turns its own API into the normalised models of `backend/schema.py`. It marks
NSFW content from the admin's `nsfw_max_level` (`max_level`, passed in so one request
uses one value everywhere) but never filters per user: `backend/nsfw_filter.py` does,
on every request, after the source answered. It caches raw upstream answers only
(`backend/cache.py`).
"""

from typing import List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..schema import ModelDetail, SearchPage, SourceInfo

DEFAULT_LIMIT = 24
MAX_LIMIT = 50
#: Long enough for `$#` with 1000 ids (CivitAI ids have up to 7 digits).
MAX_QUERY_LENGTH = 8192


class SearchQuery(BaseModel):
    """One page of search, as the page asked for it."""

    model_config = ConfigDict(frozen=True)

    #: Free text, or the source's special syntax (CivitAI: `#tag`, `@user`, `$#id1,id2`, a model URL).
    q: str = Field("", max_length=MAX_QUERY_LENGTH)
    #: The source's own model types (`SourceInfo.types` values).
    types: List[str] = Field(default_factory=list)
    #: The source's base model names (`SourceInfo.base_models` values).
    base_models: List[str] = Field(default_factory=list)
    #: A `SourceInfo.sorts` / `SourceInfo.periods` value; None for the source's default.
    sort: Optional[str] = None
    period: Optional[str] = None
    #: `SearchPage.next_cursor` of the previous page; None for the first page.
    cursor: Optional[str] = None
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    #: Ask the source for safe content only, when it can (CivitAI `nsfw=false`). A hint
    #: that saves bandwidth: the per-user filter stays the authority.
    safe: bool = False


@runtime_checkable
class Source(Protocol):
    """A model catalogue the browser can search."""

    id: str
    label: str

    async def info(self) -> SourceInfo:
        """The source and its filters (types, base models, sorts, periods) for `GET /sources`."""
        ...

    async def search(self, query: SearchQuery, *, max_level: Optional[int] = None) -> SearchPage:
        """One upstream page for `query`, normalised and unfiltered; `next_cursor` continues it.

        `max_level` defaults to the `nsfw_max_level` setting. Raises the `SourceError`
        subclasses of `backend/http.py`.
        """
        ...

    async def detail(self, model_id: str, *, max_level: Optional[int] = None) -> ModelDetail:
        """One model with its versions, files and images, normalised and unfiltered.

        A source that answers one version in full and lists the others without files
        (CivArchive) also has `version_detail(model_id, version_id, *, max_level=None)`, the
        model with that version in full: a download checks its file against it
        (`downloads.source_detail`).
        """
        ...


class UnknownSource(LookupError):
    """No enabled source has this id."""

    def __init__(self, source_id: str) -> None:
        super().__init__(f"Unknown source {source_id!r}")
        self.source_id = source_id
