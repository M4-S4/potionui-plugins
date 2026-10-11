"""Routes that browse the sources: `GET /sources`, `GET /{source}/search`,
`GET /{source}/models/{id}`, `GET /{source}/models/{id}/nsfw-media` (PLAN.md §7.3).

Included by `backend/api.py` under `/api/plugins/model-browser`. Every route needs the
`browse` capability; what the user sees then depends on their NSFW context (`nsfw.py`),
applied by `nsfw_filter.py` to every answer:
- search asks the source for safe content when the user cannot see NSFW at all
  (`blocked` ceiling or `hide` mode), then filters, following the source's cursor
  (up to `MAX_UPSTREAM_PAGES` pages) until the page has `limit` items;
- a detail the user may not see is a 404, like `nsfw-media` under a `blocked` ceiling.

Success: `{"success": true, "data": ...}`. Errors: `HTTPException` with
`{"success": false, "error": <code>, "message": ...}`: `unknown_source` and `not_found`
(404), `invalid_request` (400), `rate_limited` (429, with `Retry-After`),
`source_unavailable` (502).
"""

import logging
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from . import nsfw, nsfw_filter, sources
from .http import SourceError, SourceInvalidRequest, SourceNotFound, SourceRateLimited
from .permissions import Principal, require_browse
from .schema import NsfwContext, SearchItem, SearchPage
from .sources import MAX_LIMIT, MAX_QUERY_LENGTH, SearchQuery, Source, UnknownSource

logger = logging.getLogger("plugins.model-browser")

router = APIRouter()

#: Upstream pages one search may read to fill a page after filtering (PLAN.md §8.1).
MAX_UPSTREAM_PAGES = 10
#: `Retry-After` sent when the source rate-limited us without saying for how long.
DEFAULT_RETRY_AFTER_SECONDS = 60


def nsfw_context(principal: Principal = Depends(require_browse)) -> NsfwContext:
    """The caller's NSFW ceiling and display mode. Synchronous: FastAPI runs its database reads in a worker thread."""
    return nsfw.resolve_nsfw(principal.user)


def wants_safe_results(ctx: NsfwContext) -> bool:
    """Ask the sources for safe content only: the user never sees NSFW (`blocked` ceiling or `hide` mode)."""
    return ctx.ceiling == "blocked" or ctx.mode == "hide"


def _error(status: int, code: str, message: str, headers: Optional[Dict[str, str]] = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"success": False, "error": code, "message": message},
        headers=headers,
    )


def source_http_error(exc: SourceError) -> HTTPException:
    """A source failure as the HTTP error the page gets."""
    if isinstance(exc, SourceNotFound):
        return _error(404, "not_found", exc.message)
    if isinstance(exc, SourceRateLimited):
        wait = exc.retry_after if exc.retry_after is not None else DEFAULT_RETRY_AFTER_SECONDS
        seconds = max(1, math.ceil(wait))
        return _error(
            429, "rate_limited", f"{exc.message}; try again in {seconds} s", headers={"Retry-After": str(seconds)}
        )
    if isinstance(exc, SourceInvalidRequest):
        return _error(400, "invalid_request", exc.message)
    return _error(502, "source_unavailable", exc.message)


def _get_source(source_id: str) -> Source:
    try:
        return sources.get_source(source_id)
    except UnknownSource:
        raise _error(404, "unknown_source", f"Unknown source '{source_id[:64]}'") from None


def _values(values: Optional[List[str]]) -> List[str]:
    """Repeated query parameters, each of which may also be a comma-separated list."""
    return [part.strip() for value in values or [] for part in value.split(",") if part.strip()]


async def fill_page(source: Source, query: SearchQuery, ctx: NsfwContext) -> SearchPage:
    """Read upstream pages from `query.cursor` on, filter each for `ctx`, until `query.limit` items are collected.

    Stops after `MAX_UPSTREAM_PAGES` pages, at the last page, or when the cursor stops
    moving; `next_cursor` is the one after the last page read. A page may hold more than
    `limit` items: what an upstream page brings is kept, as its cursor cannot point inside it.
    An upstream failure after the first page ends the page early (its cursor is returned
    so the next request retries); on the first page it is raised.
    """
    items: List[SearchItem] = []
    seen = set()
    cursor = query.cursor
    next_cursor: Optional[str] = None
    for page_number in range(MAX_UPSTREAM_PAGES):
        try:
            page = await source.search(query.model_copy(update={"cursor": cursor}), max_level=ctx.max_level)
        except SourceError as exc:
            if page_number == 0:
                raise
            logger.warning("[MODEL-BROWSER] %s: stopping a page early: %s", source.label, exc.message)
            next_cursor = cursor
            break
        for item in nsfw_filter.filter_page(page, ctx).items:
            if item.id not in seen:
                seen.add(item.id)
                items.append(item)
        next_cursor = page.next_cursor
        if next_cursor == cursor:
            next_cursor = None  # the source did not move on: do not let the page ask for it again
        if len(items) >= query.limit or not next_cursor:
            break
        cursor = next_cursor
    return SearchPage(source=source.id, items=items, next_cursor=next_cursor)


@router.get("/sources")
async def list_sources(principal: Principal = Depends(require_browse)) -> Dict[str, Any]:
    """The enabled sources and their filters."""
    infos = [(await source.info()).model_dump(mode="json") for source in sources.enabled_sources()]
    return {"success": True, "data": infos}


@router.get("/{source_id}/search")
async def search(
    source_id: str,
    q: str = Query("", max_length=MAX_QUERY_LENGTH),
    types: Optional[List[str]] = Query(None),
    base_models: Optional[List[str]] = Query(None),
    sort: Optional[str] = Query(None, max_length=64),
    period: Optional[str] = Query(None, max_length=64),
    cursor: Optional[str] = Query(None, max_length=512),
    limit: int = Query(24, ge=1, le=MAX_LIMIT),
    ctx: NsfwContext = Depends(nsfw_context),
) -> Dict[str, Any]:
    """One page of results for this user: `SearchPage` filtered for their NSFW context."""
    source = _get_source(source_id)
    try:
        query = SearchQuery(
            q=q,
            types=_values(types),
            base_models=_values(base_models),
            sort=sort or None,
            period=period or None,
            cursor=cursor or None,
            limit=limit,
            safe=wants_safe_results(ctx),
        )
    except ValidationError as exc:
        raise _error(400, "invalid_request", str(exc.errors()[0].get("msg", "Invalid search"))) from None
    try:
        page = await fill_page(source, query, ctx)
    except SourceError as exc:
        raise source_http_error(exc) from None
    return {"success": True, "data": page.model_dump(mode="json")}


@router.get("/{source_id}/models/{model_id}")
async def model_detail(source_id: str, model_id: str, ctx: NsfwContext = Depends(nsfw_context)) -> Dict[str, Any]:
    """One model filtered for this user; 404 when they may not see it at all."""
    source = _get_source(source_id)
    try:
        detail = await source.detail(model_id, max_level=ctx.max_level)
    except SourceError as exc:
        raise source_http_error(exc) from None
    visible = nsfw_filter.filter_detail(detail, ctx)
    if visible is None:
        raise _error(404, "not_found", "Model not found")
    return {"success": True, "data": visible.model_dump(mode="json")}


@router.get("/{source_id}/models/{model_id}/nsfw-media")
async def model_nsfw_media(source_id: str, model_id: str, ctx: NsfwContext = Depends(nsfw_context)) -> Dict[str, Any]:
    """The urls of a model's NSFW images, for the "reveal" click in blur mode; 404 under a `blocked` ceiling."""
    source = _get_source(source_id)
    if ctx.ceiling == "blocked":
        raise _error(404, "not_found", "Model not found")
    try:
        detail = await source.detail(model_id, max_level=ctx.max_level)
    except SourceError as exc:
        raise source_http_error(exc) from None
    if nsfw_filter.filter_detail(detail, ctx) is None:
        raise _error(404, "not_found", "Model not found")
    try:
        images = nsfw_filter.nsfw_media(detail, ctx)
    except nsfw_filter.NsfwForbidden:
        raise _error(404, "not_found", "Model not found") from None
    return {"success": True, "data": {"images": [image.model_dump(mode="json") for image in images]}}
