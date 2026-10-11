"""Outbound HTTP for the sources (PLAN.md §7, §8, §12): one shared aiohttp session, a
User-Agent naming the plugin, a rate limit per source, and typed errors that
`routes_sources.py` turns into HTTP status codes.

- The session is created lazily on the running event loop (the core's TLS settings via
  `aiohttp_connector()`, `ClientTimeout(total=30)`); `shutdown()` closes it and is safe
  to call from the synchronous lifecycle `disable` handler.
- Each source has its own limiter: a minimum interval between two request starts and a
  small cap on requests in flight.
- The transport is injectable: `SourceHttp(fetch=...)` takes an async
  `fetch(url, params) -> (status, headers, body_bytes)`, so tests never open a socket.
- Reading: `get` gives a 2xx answer as `(status, headers, body_bytes)` (header names in
  lower case, e.g. `link` for Hugging Face's pagination), `get_json` its decoded JSON,
  `get_json_with_headers` both, `get_text` its text (charset from `Content-Type`, UTF-8
  by default). `max_bytes` lowers the size cap for one call (a README); `get`'s
  `accept_statuses` hands some error statuses back to read rather than raising (CivArchive
  answers an unknown model with a 500 page).
- Errors: `SourceNotFound` (404), `SourceRateLimited` (429, with `retry_after` from the
  `Retry-After` header), `SourceInvalidRequest` (any other 4xx, with the upstream message),
  `SourceUnavailable` (5xx, timeouts, connection and TLS errors, answers that are not JSON;
  `SourceAnswerTooLarge` for an answer over the size cap).
"""

import asyncio
import email.utils
import json
import logging
import math
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Collection, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

import aiohttp

from . import PLUGIN_VERSION

logger = logging.getLogger("plugins.model-browser")

USER_AGENT = f"PotionUI-ModelBrowser/{PLUGIN_VERSION} (+https://github.com/PotionUI/PotionUI)"
TIMEOUT_SECONDS = 30.0
#: Answers larger than this are refused (OpenModelDB's whole catalogue is about 1.5 MB).
MAX_BODY_BYTES = 32 * 1024 * 1024

#: Per source: (minimum seconds between two request starts, requests in flight).
DEFAULT_LIMITS: Dict[str, Tuple[float, int]] = {
    "civitai": (0.25, 4),
    "huggingface": (0.2, 4),
    "openmodeldb": (0.5, 2),
    # An unofficial site read through its pages' data routes, with no API and no stated limit: be
    # gentle, one request per second and one at a time (PLAN.md §8.5).
    "civarchive": (1.0, 1),
}
_FALLBACK_LIMIT = (0.5, 2)

SOURCE_LABELS = {
    "civitai": "CivitAI",
    "huggingface": "Hugging Face",
    "openmodeldb": "OpenModelDB",
    "civarchive": "CivArchive",
}

Params = List[Tuple[str, str]]
ParamsInput = Union[None, Mapping[str, Any], Sequence[Tuple[str, Any]]]
Fetch = Callable[[str, Params], Awaitable[Tuple[int, Mapping[str, str], bytes]]]


class SourceError(Exception):
    """A source could not give an answer. `status` is the upstream HTTP status when there was one."""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class SourceInvalidRequest(SourceError):
    """The source refused the request (a 4xx other than 404 and 429); `message` says why."""


class SourceNotFound(SourceError):
    """The source has no such model (404)."""


class SourceRateLimited(SourceError):
    """The source asks us to slow down (429); `retry_after` is in seconds, None when it did not say."""

    def __init__(self, message: str, retry_after: Optional[float] = None, status: Optional[int] = 429) -> None:
        super().__init__(message, status)
        self.retry_after = retry_after


class SourceUnavailable(SourceError):
    """The source is down or unreachable: 5xx, timeout, connection or TLS error, an answer that is not JSON."""


class SourceAnswerTooLarge(SourceUnavailable):
    """The answer is larger than the size cap (the client's, or the `max_bytes` of the call)."""


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id)


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Seconds to wait from a `Retry-After` header: delta-seconds or an HTTP date; None when absent or unreadable."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return max(0.0, seconds) if math.isfinite(seconds) else None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (when - now).total_seconds())


def upstream_message(body: bytes, limit: int = 300) -> Optional[str]:
    """The error message a source put in its answer, shortened; None when there is none.

    Understands `{"error": "..."}`, `{"message": "..."}` and CivitAI's ZodError
    `{"error": {"name": "ZodError", "message": "<JSON list of issues>"}}`.
    """
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    message: Optional[str] = None
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, str):
            message = error
        elif isinstance(error, dict):
            message = _zod_message(error.get("message")) or (
                error.get("message") if isinstance(error.get("message"), str) else None
            )
        if not message and isinstance(data.get("message"), str):
            message = data["message"]
    if not message:
        return None
    message = " ".join(message.split())
    return message if len(message) <= limit else message[: limit - 1].rstrip() + "…"


def _zod_message(raw: Any) -> Optional[str]:
    """`path: message; ...` from the JSON list of issues a ZodError carries."""
    if not isinstance(raw, str):
        return None
    try:
        issues = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(issues, list):
        return None
    parts = []
    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("message"), str):
            continue
        path = ".".join(str(part) for part in issue.get("path") or [])
        parts.append(f"{path}: {issue['message']}" if path else issue["message"])
    return "; ".join(parts) or None


def normalise_params(params: ParamsInput) -> Params:
    """Query parameters as (name, text) pairs; a list value repeats the name, None values are dropped."""
    if not params:
        return []
    items = params.items() if isinstance(params, Mapping) else params
    pairs: Params = []
    for name, value in items:
        values = value if isinstance(value, (list, tuple)) else [value]
        for item in values:
            if item is None:
                continue
            if isinstance(item, bool):
                item = "true" if item else "false"
            pairs.append((str(name), str(item)))
    return pairs


def decode_json(source_id: str, status: int, body: bytes) -> Any:
    """The JSON of an answer body; `SourceUnavailable` when it is not JSON (a challenge page, a proxy error)."""
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        raise SourceUnavailable(
            f"{source_label(source_id)} sent an answer that is not JSON (HTTP {status})", status
        ) from None


def decode_text(headers: Mapping[str, str], body: bytes) -> str:
    """An answer body as text: the `Content-Type` charset (UTF-8 by default), undecodable bytes replaced, BOM dropped."""
    charset = "utf-8"
    content_type = next((str(value) for name, value in (headers or {}).items() if str(name).lower() == "content-type"), "")
    for part in content_type.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        if name.strip().lower() == "charset" and value.strip().strip('"'):
            charset = value.strip().strip('"')
    try:
        text = (body or b"").decode(charset, errors="replace")
    except LookupError:  # an unknown charset, or a codec that is not a text encoding ("base64")
        text = (body or b"").decode("utf-8", errors="replace")
    return text[1:] if text.startswith("\N{ZERO WIDTH NO-BREAK SPACE}") else text


class _Limiter:
    """Spaces request starts by `min_interval` seconds and caps the requests in flight.

    Bound to the event loop it was created on (its semaphore is).
    """

    def __init__(self, min_interval: float, concurrency: int, clock: Callable[[], float], sleep) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self._clock = clock
        self._sleep = sleep
        self._next_start: Optional[float] = None

    async def __aenter__(self) -> "_Limiter":
        await self._semaphore.acquire()
        try:
            # Reserve the next slot before sleeping: no await between reading and writing it.
            now = self._clock()
            start = now if self._next_start is None else max(now, self._next_start)
            self._next_start = start + self.min_interval
            if start > now:
                await self._sleep(start - now)
        except BaseException:
            self._semaphore.release()
            raise
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._semaphore.release()


class SourceHttp:
    """GET JSON and text from the sources, politely. One instance is shared by every source (`http` below)."""

    def __init__(
        self,
        fetch: Optional[Fetch] = None,
        *,
        limits: Optional[Mapping[str, Tuple[float, int]]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Optional[Callable[[float], Awaitable[Any]]] = None,
        timeout_seconds: float = TIMEOUT_SECONDS,
        max_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        self._fetch = fetch
        self._limits = dict(DEFAULT_LIMITS)
        self._limits.update(limits or {})
        self._clock = clock
        self._sleep = sleep
        self._timeout_seconds = timeout_seconds
        self._max_body_bytes = max_body_bytes
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._limiters: Dict[str, _Limiter] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_loop: Optional[asyncio.AbstractEventLoop] = None
        self._closing: Set["asyncio.Future[Any]"] = set()

    # Requests ----------------------------------------------------------------

    async def get(
        self,
        source_id: str,
        url: str,
        params: ParamsInput = None,
        *,
        max_bytes: Optional[int] = None,
        accept_statuses: Collection[int] = (),
    ) -> Tuple[int, Dict[str, str], bytes]:
        """GET `url` with `params`: the status, the headers (names in lower case) and the body of a 2xx answer.

        Raises a `SourceError` subclass for any other answer or failure, except for the statuses
        of `accept_statuses`, answered like a 2xx for the caller to read (CivArchive's 500 page
        that says "Model not found"); `max_bytes` (never above the client's own cap) refuses a
        larger body with `SourceAnswerTooLarge`.
        """
        pairs = normalise_params(params)
        label = source_label(source_id)
        cap = self._max_body_bytes if max_bytes is None else max(0, min(int(max_bytes), self._max_body_bytes))
        started = time.monotonic()
        async with self._limiter(source_id):
            try:
                if self._fetch is not None:
                    status, headers, body = await self._fetch(url, pairs)
                else:
                    status, headers, body = await self._aiohttp_fetch(url, pairs, max_bytes=cap)
            except SourceError:
                raise
            except asyncio.TimeoutError:
                raise SourceUnavailable(f"{label} did not answer within {self._timeout_seconds:g} s") from None
            except (aiohttp.ClientConnectorCertificateError, ssl.SSLCertVerificationError) as exc:
                raise SourceUnavailable(
                    f"Could not verify {label}'s TLS certificate; check the system certificate store "
                    f"or SSL_CERT_FILE ({exc})"
                ) from None
            except (aiohttp.ClientError, ssl.SSLError, OSError) as exc:
                raise SourceUnavailable(f"Could not reach {label}: {exc.__class__.__name__}: {exc}") from None
        headers = {str(name).lower(): str(value) for name, value in (headers or {}).items()}
        body = body or b""
        logger.debug(
            "[MODEL-BROWSER] GET %s %s -> %s (%d bytes, %.0f ms)",
            url, pairs, status, len(body), (time.monotonic() - started) * 1000,
        )
        if len(body) > cap:
            raise SourceAnswerTooLarge(f"{label} sent an answer larger than {cap} bytes", status)
        if status not in accept_statuses:
            self._raise_for_status(source_id, status, headers, body)
        return status, headers, body

    async def get_json(self, source_id: str, url: str, params: ParamsInput = None) -> Any:
        """GET `url` with `params` and return the decoded JSON body; raises a `SourceError` subclass."""
        status, _, body = await self.get(source_id, url, params)
        return decode_json(source_id, status, body)

    async def get_json_with_headers(
        self, source_id: str, url: str, params: ParamsInput = None
    ) -> Tuple[Any, Dict[str, str]]:
        """`get_json`, with the answer's headers (names in lower case) for the pagination `link`."""
        status, headers, body = await self.get(source_id, url, params)
        return decode_json(source_id, status, body), headers

    async def get_text(
        self, source_id: str, url: str, params: ParamsInput = None, *, max_bytes: Optional[int] = None
    ) -> str:
        """GET `url` and return the body as text (see `decode_text`); same errors as `get`."""
        _, headers, body = await self.get(source_id, url, params, max_bytes=max_bytes)
        return decode_text(headers, body)

    @staticmethod
    def _raise_for_status(source_id: str, status: int, headers: Mapping[str, str], body: bytes) -> None:
        if 200 <= status < 300:
            return
        label = source_label(source_id)
        message = upstream_message(body)
        if status == 404:
            raise SourceNotFound(message or f"Not found on {label}", status)
        if status == 429:
            retry_after = parse_retry_after(headers.get("retry-after"))
            logger.warning("[MODEL-BROWSER] %s rate limit reached (retry after %s s)", label, retry_after)
            raise SourceRateLimited(f"{label} rate limit reached", retry_after, status)
        if 400 <= status < 500:
            raise SourceInvalidRequest(
                f"{label} refused the request: {message}" if message else f"{label} refused the request (HTTP {status})",
                status,
            )
        logger.warning("[MODEL-BROWSER] %s answered HTTP %s", label, status)
        raise SourceUnavailable(f"{label} answered HTTP {status}", status)

    # Event-loop bound state ----------------------------------------------------

    def _bind_loop(self) -> asyncio.AbstractEventLoop:
        """Reset the limiters (and let go of the session) when called from a new event loop."""
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            if self._session is not None and self._session_loop is not loop:
                self.close_soon()
            self._loop = loop
            self._limiters = {}
        return loop

    def _limiter(self, source_id: str) -> _Limiter:
        self._bind_loop()
        limiter = self._limiters.get(source_id)
        if limiter is None:
            interval, concurrency = self._limits.get(source_id, _FALLBACK_LIMIT)
            limiter = _Limiter(interval, concurrency, self._clock, self._sleep or asyncio.sleep)
            self._limiters[source_id] = limiter
        return limiter


    def _get_session(self) -> aiohttp.ClientSession:
        """The shared session, created on the running loop the first time it is needed."""
        loop = self._bind_loop()
        if self._session is None or self._session.closed:
            from src.plugin_api.providers import aiohttp_connector

            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                connector=aiohttp_connector(),
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
            )
            self._session_loop = loop
        return self._session

    async def _aiohttp_fetch(
        self, url: str, params: Params, max_bytes: Optional[int] = None
    ) -> Tuple[int, Mapping[str, str], bytes]:
        cap = self._max_body_bytes if max_bytes is None else max_bytes
        session = self._get_session()
        async with session.get(url, params=params) as response:
            too_large = SourceAnswerTooLarge(
                f"The answer from {response.url.host} is larger than {cap} bytes", response.status
            )
            length = response.content_length
            if length is not None and length > cap:
                raise too_large
            chunks: List[bytes] = []
            size = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                size += len(chunk)
                if size > cap:
                    raise too_large
                chunks.append(chunk)
            return response.status, response.headers, b"".join(chunks)

    # Shutdown ----------------------------------------------------------------

    async def close(self) -> None:
        """Close the shared session (from the loop it runs on); the next request opens a new one."""
        session, self._session = self._session, None
        self._session_loop = None
        if session is not None and not session.closed:
            await session.close()

    def close_soon(self) -> None:
        """Close the shared session without waiting; safe from any thread, a no-op when there is none."""
        session, loop = self._session, self._session_loop
        self._session = None
        self._session_loop = None
        if session is None or session.closed or loop is None or loop.is_closed():
            return

        def _close() -> None:
            task = loop.create_task(session.close())
            self._closing.add(task)
            task.add_done_callback(self._closing.discard)

        try:
            loop.call_soon_threadsafe(_close)
        except RuntimeError:
            pass  # the loop closed in between: nothing left to close on it


#: The instance every source uses.
http = SourceHttp()


def shutdown() -> None:
    """Close the shared session without waiting; for the synchronous `plugin.lifecycle.disable` handler."""
    http.close_soon()
