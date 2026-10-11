"""Test doubles for the sources layer: recorded CivitAI answers served through
`SourceHttp`'s injectable transport (no socket is ever opened), an in-memory cache,
fake settings and NSFW contexts.

The fixtures under `fixtures/civitai/` are real public answers, trimmed:
`{"_status": int, "_headers": {...}, "body": <json>}`.
"""

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlsplit

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "civitai"
API_BASE = "https://civitai.com/api/v1"

#: Request parameter value meaning "this parameter must be absent".
ABSENT = object()

Response = Union[str, Tuple[int, Dict[str, str], Any], Callable[[str, List[Tuple[str, str]]], Any]]


def load(name: str) -> Dict[str, Any]:
    """A whole fixture file: `_status`, `_headers` and `body`."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def body(name: str) -> Any:
    """A fresh copy of a fixture's JSON body."""
    return copy.deepcopy(load(name)["body"])


def item(name: str, model_id: int) -> Dict[str, Any]:
    """One model of a list fixture, by id."""
    for raw in body(name)["items"]:
        if raw["id"] == model_id:
            return raw
    raise KeyError(model_id)


def page_body(items: List[Dict[str, Any]], next_cursor: Optional[str] = None) -> Dict[str, Any]:
    metadata = {"nextCursor": next_cursor} if next_cursor else {}
    return {"items": items, "metadata": metadata}


class FakeTransport:
    """`fetch(url, params)` for `SourceHttp`, answering from routes registered with `add`.

    A route matches a request when the path is the same and every parameter it names has
    that value (`ABSENT`: is missing); the route naming the most parameters wins. A request
    no route matches gets a 404. Every request is recorded in `calls` as (path, params).
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, List[Tuple[str, str]]]] = []
        self._routes: List[Tuple[str, Dict[str, Any], Response]] = []

    def add(self, path: str, response: Response, **params: Any) -> "FakeTransport":
        """`response`: a fixture name, a `(status, headers, body)` tuple, or a callable(path, params) giving one."""
        self._routes.append((path, params, response))
        return self

    def calls_to(self, path: str) -> List[Dict[str, Any]]:
        """The parameters of each call to `path`, as dicts (repeated names give lists)."""
        return [_as_dict(params) for called, params in self.calls if called == path]

    async def __call__(self, url: str, params):
        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}".startswith(API_BASE), url
        path = parts.path[len(urlsplit(API_BASE).path):]
        params = [(str(name), str(value)) for name, value in params]
        self.calls.append((path, params))
        best = None
        for route_path, required, response in self._routes:
            if route_path != path or not _matches(required, params):
                continue
            if best is None or len(required) > len(best[0]):
                best = (required, response)
        if best is None:
            return 404, {"Content-Type": "application/json"}, b'{"error": "No model found"}'
        response = best[1]
        if callable(response):
            response = response(path, params)
        if isinstance(response, str):
            fixture = load(response)
            return fixture["_status"], dict(fixture["_headers"]), json.dumps(fixture["body"]).encode("utf-8")
        status, headers, payload = response
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return status, dict(headers or {}), data


def _matches(required: Dict[str, Any], params: List[Tuple[str, str]]) -> bool:
    names = {name for name, _ in params}
    for name, value in required.items():
        if value is ABSENT:
            if name in names:
                return False
        elif (name, str(value)) not in params:
            return False
    return True


def _as_dict(params: List[Tuple[str, str]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name, value in params:
        if name in result:
            existing = result[name]
            result[name] = existing + [value] if isinstance(existing, list) else [existing, value]
        else:
            result[name] = value
    return result


class MemoryCache:
    """The `Cache` interface over a dict, for tests of a source alone. Stores deep copies, like the real one stores text."""

    def __init__(self) -> None:
        self.entries: Dict[str, Any] = {}
        self.ttls: Dict[str, Optional[float]] = {}

    def get(self, source: str, request: Any, *, ttl_seconds: Optional[float] = None) -> Optional[Any]:
        from backend.cache import cache_key

        value = self.entries.get(cache_key(source, request))
        return copy.deepcopy(value) if value is not None else None

    def set(self, source: str, request: Any, payload: Any, *, ttl_seconds: Optional[float] = None) -> None:
        from backend.cache import cache_key

        key = cache_key(source, request)
        self.entries[key] = copy.deepcopy(payload)
        self.ttls[key] = ttl_seconds


def fake_settings(monkeypatch, **overrides: Any) -> Dict[str, Any]:
    """Replace `settings.get_setting` with the defaults plus `overrides`; returns the live dict to change later."""
    from backend import settings

    values = dict(settings.DEFAULTS)
    values.update(overrides)
    monkeypatch.setattr(settings, "get_setting", lambda key: values[key])
    return values


def make_source(transport: FakeTransport, cache: Any = None):
    """A `CivitaiSource` on the fake transport, no rate-limit delay, an in-memory cache unless one is given."""
    from backend.http import SourceHttp
    from backend.sources.civitai import CivitaiSource

    client = SourceHttp(fetch=transport, limits={"civitai": (0.0, 4)})
    return CivitaiSource(http_client=client, cache_store=cache if cache is not None else MemoryCache())


_ALLOWED_MODES = {"allowed": ("blur", "show", "hide"), "blur": ("blur", "hide"), "blocked": ("hide",)}


def context(ceiling: str = "allowed", mode: str = "show", max_level: int = 2, hide_poi: bool = False):
    """An `NsfwContext` as `nsfw.resolve_nsfw` would build it."""
    from backend.schema import NsfwContext

    return NsfwContext(
        ceiling=ceiling, mode=mode, allowed_modes=_ALLOWED_MODES[ceiling], max_level=max_level, hide_poi=hide_poi
    )


def image_urls(value: Any) -> List[str]:
    """Every image url anywhere in a dumped page or detail."""
    urls: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "blurhash" in node and node.get("url"):
                urls.append(node["url"])
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return urls
