"""Test doubles for the Hugging Face source: recorded answers served through `SourceHttp`'s
injectable transport (no socket is ever opened).

The fixtures under `fixtures/huggingface/` are real public answers, trimmed:
`{"_status": int, "_headers": {...}, "body": <json or text>}` (the `Link` header is kept
for lists; a README body is its raw text). `scripts/capture-huggingface-fixtures.py`
at the repository root regenerates them.
"""

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urlsplit

from .civitai_fakes import ABSENT, MemoryCache

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "huggingface"
SITE = "https://huggingface.co"

#: Fixture key -> repo id, for the model / tree / README fixtures of one repo.
REPOS = {
    "lcm_lora_sdxl": "latent-consistency/lcm-lora-sdxl",
    "flux_dev_gated": "black-forest-labs/FLUX.1-dev",
    "sd35_large": "stabilityai/stable-diffusion-3.5-large",
    "sdxl_base": "stabilityai/stable-diffusion-xl-base-1.0",
    "real_esrgan": "ai-forever/Real-ESRGAN",
}

Response = Union[str, Tuple[int, Dict[str, str], Any], Callable[[str, List[Tuple[str, str]]], Any]]


def load(name: str) -> Dict[str, Any]:
    """A whole fixture file: `_status`, `_headers` and `body`."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def body(name: str) -> Any:
    """A fresh copy of a fixture's body (JSON, or the text of a README)."""
    return copy.deepcopy(load(name)["body"])


def item(name: str, repo: str) -> Dict[str, Any]:
    """One repo of a list fixture, by id."""
    for raw in body(name):
        if raw["id"] == repo:
            return raw
    raise KeyError(repo)


def link_header(name: str) -> Optional[str]:
    return load(name)["_headers"].get("Link")


def cursor_of(name: str) -> str:
    """The decoded `cursor` of a list fixture's `Link: <...>; rel="next"` header, read independently of the source."""
    link = link_header(name)
    url = link[link.index("<") + 1:link.index(">")]
    return unquote(url.split("cursor=", 1)[1])


def encode(headers: Dict[str, str], payload: Any) -> bytes:
    """A body as bytes: text for a text answer, JSON otherwise."""
    if isinstance(payload, bytes):
        return payload
    content_type = next((value for key, value in (headers or {}).items() if key.lower() == "content-type"), "")
    if isinstance(payload, str) and not content_type.startswith("application/json"):
        return payload.encode("utf-8")
    return json.dumps(payload).encode("utf-8")


class HuggingFaceTransport:
    """`fetch(url, params)` for `SourceHttp`, answering huggingface.co paths from routes registered with `add`.

    Paths are as Hugging Face has them: `/api/models`, `/api/models/{repo}`,
    `/api/models/{repo}/tree/main`, `/{repo}/raw/main/README.md`. A route matches when the
    path is the same and every parameter it names has that value (`ABSENT`: is missing);
    the route naming the most parameters wins, and among those the last one added (a test
    overrides a route of `add_repo` by adding it again). A request no route matches gets a
    404. Every request is recorded in `calls` as (path, params).
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, List[Tuple[str, str]]]] = []
        self._routes: List[Tuple[str, Dict[str, Any], Response]] = []

    def add(self, path: str, response: Response, **params: Any) -> "HuggingFaceTransport":
        """`response`: a fixture name, a `(status, headers, body)` tuple, or a callable(path, params) giving one."""
        self._routes.append((path, params, response))
        return self

    def add_repo(self, key: str, *, readme: Optional[Response] = None) -> str:
        """The model, tree and (when there is one) README fixtures of `REPOS[key]`; returns the repo id."""
        repo = REPOS[key]
        self.add(f"/api/models/{repo}", f"model_{key}")
        self.add(f"/api/models/{repo}/tree/main", f"tree_{key}")
        if readme is None and (FIXTURES / f"readme_{key}.json").exists():
            readme = f"readme_{key}"
        if readme is not None:
            self.add(f"/{repo}/raw/main/README.md", readme)
        return repo

    def paths(self) -> List[str]:
        return [path for path, _ in self.calls]

    def calls_to(self, path: str) -> List[Dict[str, Any]]:
        """The parameters of each call to `path`, as dicts (repeated names give lists)."""
        return [_as_dict(params) for called, params in self.calls if called == path]

    async def __call__(self, url: str, params):
        parts = urlsplit(url)
        assert f"{parts.scheme}://{parts.netloc}" == SITE, url
        assert not parts.query, url
        path = parts.path
        params = [(str(name), str(value)) for name, value in params]
        self.calls.append((path, params))
        best = None
        for route_path, required, response in self._routes:
            if route_path != path or not _matches(required, params):
                continue
            if best is None or len(required) >= len(best[0]):
                best = (required, response)
        if best is None:
            return 404, {"Content-Type": "application/json"}, b'{"error": "Repository not found"}'
        response = best[1]
        if callable(response):
            response = response(path, params)
        if isinstance(response, str):
            fixture = load(response)
            headers = dict(fixture["_headers"])
            return fixture["_status"], headers, encode(headers, fixture["body"])
        status, headers, payload = response
        headers = dict(headers or {})
        if isinstance(payload, (dict, list)):
            headers.setdefault("Content-Type", "application/json; charset=utf-8")
        return status, headers, encode(headers, payload)


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


def make_source(transport: HuggingFaceTransport, cache: Any = None):
    """A `HuggingFaceSource` on the fake transport, no rate-limit delay, an in-memory cache unless one is given."""
    from backend.http import SourceHttp
    from backend.sources.huggingface import HuggingFaceSource

    client = SourceHttp(fetch=transport, limits={"huggingface": (0.0, 4)})
    return HuggingFaceSource(http_client=client, cache_store=cache if cache is not None else MemoryCache())


#: OpenModelDB's and CivArchive's sites (`openmodeldb_fakes.SITE`, `civarchive_fakes.SITE`), for `combined_fetch`.
OPENMODELDB_SITE = "https://openmodeldb.info"
CIVARCHIVE_SITE = "https://civarchive.com"


def combined_fetch(civitai, huggingface, openmodeldb=None, civarchive=None):
    """One `fetch` for the shared `SourceHttp` of the route tests: huggingface.co URLs to one
    fake, openmodeldb.info URLs to `openmodeldb` and civarchive.com URLs to `civarchive` (a 503
    without one), the rest to `civitai`."""

    async def fetch(url: str, params):
        if url.startswith(SITE + "/"):
            return await huggingface(url, params)
        if url.startswith(OPENMODELDB_SITE + "/"):
            if openmodeldb is None:
                return 503, {"Content-Type": "text/plain"}, b"OpenModelDB is not faked in this test"
            return await openmodeldb(url, params)
        if url.startswith(CIVARCHIVE_SITE + "/"):
            if civarchive is None:
                return 503, {"Content-Type": "text/plain"}, b"CivArchive is not faked in this test"
            return await civarchive(url, params)
        return await civitai(url, params)

    return fetch
