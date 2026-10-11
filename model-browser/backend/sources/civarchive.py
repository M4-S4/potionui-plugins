"""CivArchive as a model-browser source (PLAN.md §8.5), off unless the admin turns on `enable_civarchive`.

civarchive.com is a community index of CivitAI (and of other sites) with no API: the source
reads the data routes of its Next.js pages, as Stability Matrix's client does
(`StabilityMatrix.Core/Api/CivArchiveApiClient.cs`). Checked live on 2026-10-11; `robots.txt`
allows everything but `/api`, which is never asked for, and download links always point at the
sources (CivitAI, Hugging Face), never at civarchive.com.

The build id. Every data URL holds the id of the deployment, `/_next/data/<build id>/...json`;
it is read from the home page (`"buildId":"..."` in its `__NEXT_DATA__`, about 200 KB of HTML,
never cached) and kept in memory and in the plugin cache (`{"build_id": True}`) for
`BUILD_ID_TTL_SECONDS`, so a restart does not fetch the page again. An `asyncio.Lock` makes
concurrent first requests resolve it once. A data URL under a stale id answers 404 (an HTML
page): `_data` then resolves the id again (once for every request that saw the same stale id)
and repeats the request once; a second 404 is the answer itself (a model or hash detail not
found; an empty search page). A home page without a build id is `SourceUnavailable`.

What the data routes answer (raw answers cached without their `comments` / `faqSections`):
- `search.json` (`SEARCH_TTL_SECONDS`): `platform=civitai` always (without it CivitAI is a few
  results among PixAI, TensorArt ...), `kind=version`, `rating=safe` when the query asks for
  safe content (`rating=all` otherwise; `nsfw` is not a value), `sort`, `period`, `page`
  (1-based, 50 results, `total_hits` capped at 1000), `q`, `tags`, `username`, repeated `type`
  and `base_model`. `kind=model` answers no result at all for CivitAI (2026-10-11: the index
  holds versions, files and articles), so the source asks for versions and keeps one item per
  model on a page: the newest version, at the place of the model's first result.
- `models/<id>.json?platform=civitai&modelVersionId=<vid>` (`DETAIL_TTL_SECONDS`): the model
  with that version in full (files, mirrors, images); without a version, a `__N_REDIRECT` to the
  latest one, which is followed. An unknown model or version answers HTTP 500 with "Model not
  found" (`SourceNotFound`); a version of another model is answered with that other model's
  version, so the answer is checked.
- `sha256/<hash>.json` (`HASH_TTL_SECONDS`): the models using a file, and its mirrors; an
  unknown hash answers 200 with no model (the `civarchive` provider reads it).

Search box: `#tag`, `@user`, a pasted civarchive.com, civitai.com or civitai.red model link
(that model through its detail: one item, whose id names the link's version when it has one),
anything else is CivArchive's full-text search. Sorts `top` (default), `newest`, `downloads`,
`likes`, `updated`; periods as the CivitAI source's (`all_time` ...), so the page's URL state is
shared. The cursor is the next page number.

Ids: a model is its CivitAI id ("78291"). A detail id may name the version: "78291:83095" (or
"78291?modelVersionId=83095", or a pasted link); without one the latest version is shown.
Only that version comes in full: the model's other versions are listed as `partial` versions,
without files or images (the page loads "<model id>:<version id>" for them), and
`version_detail` loads the one a download names.

Normalisation, with CivitAI's vocabulary (`type_mapping.civitai_mb_type`, the bitmask helpers of
`sources/civitai.py`):
- NSFW (PLAN.md §5.3): a model or version is NSFW when its `nsfw_level` bitmask has a level above
  `max_level` (`is_nsfw` when it has no level), or, for the version shown and the model, when
  none of the version's images is safe (CivitAI's strict rule; images without a level are not
  safe). Images: their `nsfwLevel`, `hash` (blurhash) and `poi`; an image flagged `minor` is
  dropped; a model is `poi` when one of its images is. A list result has `is_nsfw` only: it is
  NSFW when `is_nsfw` is set or when the model was deleted from CivitAI (CivArchive does not
  keep `is_nsfw` up to date on deleted models: on 2026-10-11, 7 of the 50 deleted LoRAs a
  `rating=safe` search listed carried explicit tags), and its thumbnail with it. Conservative:
  the detail decides from the levels.
- Downloads (`download_for`): the file's CivitAI URL (`https://civitai.com/api/download/...`,
  provider `civitai`) while a `civitai` mirror of it is not deleted (it may be the same file
  under another version), or, without any `civitai` mirror, its own `download_url` while
  neither it, its version nor its model is deleted; otherwise the first Hugging Face mirror
  that is a `/resolve/` URL (not gated first; provider `huggingface`, percent-encoded); otherwise
  the file is left out (torrents, tensordrive.app, other sites). A version without a file has
  no `mb_type`: the page shows "Not downloadable". A model deleted from CivitAI says so in its
  description.
- No licence (CivArchive has none), no early access except a paid CivitAI mirror.
"""

import asyncio
import hashlib
import html
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from pydantic import ValidationError

from .. import cache as cache_module
from .. import http as http_module
from .. import settings
from ..http import SourceError, SourceInvalidRequest, SourceNotFound, SourceUnavailable
from ..schema import File, FilterOption, Image, ModelDetail, SearchItem, SearchPage, SourceInfo, Stats, Version
from ..security import is_allowed_download_url, sanitize_html
from ..type_mapping import civitai_mb_type
from . import civitai
from .base import SearchQuery

logger = logging.getLogger("plugins.model-browser")

SOURCE_ID = "civarchive"
LABEL = "CivArchive"
SITE = "https://civarchive.com"
#: The only platform asked for: the source is CivArchive's copy of CivitAI.
PLATFORM = "civitai"
#: Search results come as versions (`kind=model` answers nothing for CivitAI).
KIND = "version"
#: Results per search page (CivArchive's, not ours to choose).
PAGE_SIZE = 50

BUILD_ID_TTL_SECONDS = 3600
#: A 404 under a build id renewed this recently reuses the renewed one rather than reading the home page again.
RENEW_HOLD_SECONDS = 30
SEARCH_TTL_SECONDS = 120
DETAIL_TTL_SECONDS = 300
HASH_TTL_SECONDS = 300
FILTERS_TTL_SECONDS = 3600
#: After the filter lists failed, `info()` answers without them this long rather than asking again.
FILTERS_RETRY_SECONDS = 60
#: The home page is about 200 KB.
HOME_MAX_BYTES = 4 * 1024 * 1024
#: The cache key of the build id.
BUILD_ID_REQUEST = {"build_id": True}
#: What the data answers hold that the source never reads (large: the comments of a model).
UNUSED_KEYS = frozenset({"comments", "faqSections", "footerLinks"})

NOTICE = (
    "Unofficial source: civarchive.com is a community index of CivitAI, not an official API. "
    "Deleted models may be unavailable, or come from third-party mirrors."
)
SEARCH_HELP = "Text, #tag, @user, or a civarchive.com / civitai.com model link"

#: Our sort ids (CivArchive's values) with their labels, in the order the page lists them.
SORTS: Tuple[Tuple[str, str], ...] = (
    ("top", "Top"),
    ("newest", "Newest"),
    ("downloads", "Most downloaded"),
    ("likes", "Most liked"),
    ("updated", "Recently updated"),
)
DEFAULT_SORT = "top"
#: Our period ids (the CivitAI source's) -> CivArchive `period` values, with labels.
PERIODS: Tuple[Tuple[str, str, str], ...] = (
    ("all_time", "all", "All time"),
    ("year", "year", "Past year"),
    ("month", "month", "Past month"),
    ("week", "week", "Past week"),
    ("day", "day", "Past day"),
)
_SORT_KEYS = frozenset(key for key, _ in SORTS)
_PERIOD_VALUES = {key: value for key, value, _ in PERIODS}

#: A file name's extension -> `File.format`.
_FORMATS = {
    ".safetensors": "SafeTensor",
    ".ckpt": "PickleTensor",
    ".pt": "PickleTensor",
    ".pth": "PickleTensor",
    ".bin": "PickleTensor",
    ".gguf": "GGUF",
}

_BUILD_ID = re.compile(r'"buildId":"([^"]+)"')
#: What a build id may hold before it goes into a URL path.
_BUILD_ID_TEXT = re.compile(r"[A-Za-z0-9_-]{1,128}")
#: The title of the 500 page CivArchive answers for an unknown model or version.
_NOT_FOUND_PAGE = re.compile(r"Model (?:version )?not found", re.I)
_DIGITS = re.compile(r"[0-9]{1,12}")
_MODEL_REF = re.compile(r"([0-9]{1,12})(?::([0-9]{1,12}))?")
_MODEL_PATH = re.compile(r"^/models/([0-9]{1,12})(?:/[^/]*)?/?$")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_CURSOR = re.compile(r"[0-9]{1,4}")
_IMAGE_ID_IN_URL = re.compile(r"/([0-9]{1,15})(?:\.[A-Za-z0-9]{2,5})?$")
_VIDEO_PATH = re.compile(r"\.(?:mp4|webm|mov)$", re.I)
#: Never part of an image URL the page is given.
_ODD_URL_CHARACTERS = frozenset("\\\"'<>`")
#: Characters a URL path or query keeps as they are (RFC 3986 `pchar`, `/`, `?` and `%`).
_URL_SAFE = "/%!$&'()*+,;=:@-._~?"


# Values ---------------------------------------------------------------------------


def _text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _id(value: Any) -> Optional[int]:
    """A positive CivitAI id, given as a number or as digits."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value > 0 else None
    if isinstance(value, str) and _DIGITS.fullmatch(value.strip()):
        return int(value.strip()) or None
    return None


def _is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def _list(value: Any) -> List[Any]:
    """`value` when it is a list, else an empty one (a string is never iterated)."""
    return value if isinstance(value, list) else []


def _dicts(value: Any) -> List[Dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _strings(values: Any) -> List[str]:
    """The non-empty strings of a list, stripped, once each, in order."""
    return list(dict.fromkeys(value.strip() for value in _list(values) if isinstance(value, str) and value.strip()))


def _sha256(value: Any) -> Optional[str]:
    return value.lower() if isinstance(value, str) and _SHA256.fullmatch(value) else None


def _epoch_text(value: Any) -> Optional[str]:
    """Epoch seconds (a list result's `created_at`) as "2023-02-10T12:56:41Z"; None when unusable."""
    seconds = _float(value)
    if seconds is None or seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _deleted(value: Any) -> bool:
    """A `deleted_at` (ISO text or epoch seconds) is set."""
    return _text(value) is not None or (_float(value) is not None and _float(value) > 0)


def _day(value: Any) -> Optional[str]:
    """The date part ("2025-08-07") of a `deleted_at`, ISO text or epoch seconds."""
    text = _text(value)
    if text is not None:
        return text[:10] if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text[:10]) else None
    epoch = _epoch_text(value)
    return epoch[:10] if epoch else None


def model_page_url(model_id: Any, version_id: Any = None) -> str:
    """`https://civarchive.com/models/<id>`, with `?modelVersionId=<vid>` when a version is given."""
    url = f"{SITE}/models/{model_id}"
    return f"{url}?modelVersionId={version_id}" if version_id not in (None, "") else url


def level_nsfw(level: Any, is_nsfw: Any, max_level: int) -> bool:
    """A model, version or file `nsfw_level` bitmask has a level above `max_level`; without a
    level (missing or 0), CivArchive's own `is_nsfw` decides."""
    mask = _int(level)
    if mask is not None and mask > 0:
        return civitai.mask_exceeds(mask, max_level)
    return _is_true(is_nsfw)


# Ids and the search box -----------------------------------------------------------


def parse_model_link(text: str) -> Optional[Tuple[int, Optional[int]]]:
    """(model id, version id or None) from a civarchive.com, civitai.com or civitai.red model link."""
    text = (text or "").strip()
    if not text or any(char.isspace() for char in text):
        return None
    candidate = text if "://" in text else f"https://{text}"
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if host.startswith("www."):
        host = host[4:]
    if host != "civarchive.com":
        return civitai.parse_model_url(text)
    match = _MODEL_PATH.match(parts.path)
    if not match or _id(match.group(1)) is None:
        return None
    version = (parse_qs(parts.query).get("modelVersionId") or [""])[0]
    return int(match.group(1)), _id(version)


def parse_model_ref(value: Any) -> Optional[Tuple[int, Optional[int]]]:
    """(model id, version id or None) from a detail id: "78291", "78291:83095",
    "78291?modelVersionId=83095" or a model link; None for anything else."""
    text = str(value or "").strip()
    match = _MODEL_REF.fullmatch(text)
    if match:
        model_id = _id(match.group(1))
        version = match.group(2)
        if model_id is None or (version is not None and _id(version) is None):
            return None
        return model_id, _id(version) if version is not None else None
    head, separator, query = text.partition("?")
    if separator and _id(head) is not None and _DIGITS.fullmatch(head):
        version = (parse_qs(query).get("modelVersionId") or [""])[0]
        return int(head), _id(version)
    return parse_model_link(text)


def model_ref(model_id: int, version_id: Optional[int] = None) -> str:
    """A detail id: "78291", or "78291:83095" with a version."""
    return f"{model_id}:{version_id}" if version_id is not None else str(model_id)


def page_url_for(model_id: Any, version_id: Any = None) -> Optional[str]:
    """The civarchive.com page of a model id ("78291", or "78291:83095" naming its version), with
    `version_id` when the id names none; None for anything that is not such an id. No request."""
    if not isinstance(model_id, str) or not _MODEL_REF.fullmatch(model_id.strip()):
        return None
    ref = parse_model_ref(model_id)
    if ref is None:
        return None
    version = ref[1]
    if version is None and not isinstance(version_id, bool):
        version = _id(version_id.strip() if isinstance(version_id, str) else version_id)
    return model_page_url(ref[0], version)


@dataclass(frozen=True)
class ParsedQuery:
    """What the search box asks CivArchive for."""

    #: "all" (no text), "text", "tag", "username" or "model" (a pasted link).
    kind: str = "all"
    value: str = ""
    model_id: Optional[int] = None
    version_id: Optional[int] = None


def parse_query(q: Optional[str]) -> ParsedQuery:
    """The search box text: a model link, `#tag`, `@user` or free text."""
    text = (q or "").strip()
    if not text:
        return ParsedQuery()
    link = parse_model_link(text)
    if link is not None:
        return ParsedQuery(kind="model", model_id=link[0], version_id=link[1])
    if text.startswith("#"):
        tag = text[1:].strip()
        return ParsedQuery(kind="tag", value=tag) if tag else ParsedQuery()
    if text.startswith("@"):
        username = text[1:].strip()
        return ParsedQuery(kind="username", value=username) if username else ParsedQuery()
    return ParsedQuery(kind="text", value=text)


def parse_cursor(cursor: Optional[str]) -> int:
    """The page a cursor names; 1 without one. `SourceInvalidRequest` for anything but a page number."""
    if cursor is None or cursor == "":
        return 1
    if not _CURSOR.fullmatch(cursor) or int(cursor) < 1:
        raise SourceInvalidRequest("Invalid CivArchive cursor")
    return int(cursor)


def _sort(value: Optional[str]) -> str:
    if value is None or value == "":
        return DEFAULT_SORT
    if value not in _SORT_KEYS:
        raise SourceInvalidRequest(
            f"Unknown sort {str(value)[:40]!r}; use one of: {', '.join(key for key, _ in SORTS)}"
        )
    return value


def _period(value: Optional[str]) -> str:
    if value is None or value == "":
        return _PERIOD_VALUES["all_time"]
    try:
        return _PERIOD_VALUES[value]
    except KeyError:
        raise SourceInvalidRequest(
            f"Unknown period {str(value)[:40]!r}; use one of: {', '.join(_PERIOD_VALUES)}"
        ) from None


def _clean_list(values: Iterable[str]) -> List[str]:
    """Stripped, non-empty, distinct and sorted: the same selection always gives the same request."""
    return sorted({str(value).strip() for value in values or () if str(value).strip()})


def search_params(parsed: ParsedQuery, query: SearchQuery, page: int) -> List[Tuple[str, str]]:
    """The `search.json` parameters of one page (`parsed` is not a model link)."""
    params = [
        ("platform", PLATFORM),
        ("kind", KIND),
        ("rating", "safe" if query.safe else "all"),
        ("sort", _sort(query.sort)),
        ("period", _period(query.period)),
        ("page", str(page)),
    ]
    if parsed.kind == "text":
        params.append(("q", parsed.value))
    elif parsed.kind == "tag":
        params.append(("tags", parsed.value))
    elif parsed.kind == "username":
        params.append(("username", parsed.value))
    params += [("type", value) for value in _clean_list(query.types)]
    params += [("base_model", value) for value in _clean_list(query.base_models)]
    return params


def parse_redirect(value: Any) -> Optional[Tuple[int, Optional[int]]]:
    """(model id, version id) of a `__N_REDIRECT` such as "/models/78291?modelVersionId=83095"."""
    text = _text(value)
    if text is None:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.netloc and (parts.hostname or "").lower() not in ("civarchive.com", "www.civarchive.com"):
        return None
    match = _MODEL_PATH.match(parts.path)
    if not match:
        return None
    version = (parse_qs(parts.query).get("modelVersionId") or [""])[0]
    return int(match.group(1)), _id(version)


# Images -----------------------------------------------------------------------------


def _odd(char: str) -> bool:
    return char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F or char in _ODD_URL_CHARACTERS


def https_url(value: Any) -> Optional[str]:
    """`value` when it is an https URL with a host and nothing odd in it."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(_odd(char) for char in value):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not parts.hostname or "@" in parts.netloc:
        return None
    return value


def image_id(url: str) -> str:
    """The CivitAI image id at the end of a URL path ("…/width=450/88246.jpeg" -> "88246"),
    else a short hash of the URL: what lets `nsfw-media` answer for this image."""
    try:
        match = _IMAGE_ID_IN_URL.search(urlsplit(url).path)
    except ValueError:
        match = None
    if match:
        return match.group(1)
    return hashlib.md5(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _is_video(url: Optional[str]) -> bool:
    try:
        return bool(url) and bool(_VIDEO_PATH.search(urlsplit(url).path))
    except ValueError:
        return False


def normalize_image(raw: Any, max_level: int) -> Optional[Image]:
    """One preview of a version (CivitAI's shape: `url`, `nsfwLevel`, `hash`, `type`, `poi`); None
    for an image flagged `minor`, or one with neither an https url nor a blurhash.

    An image without a level is NSFW (CivitAI's rule). An `.mp4` without a `type` is a video;
    an image without an id gets one from its URL.
    """
    if not isinstance(raw, dict) or _is_true(raw.get("minor")):
        return None
    image = civitai.normalize_image(raw, max_level)
    if image is None:
        return None
    updates: Dict[str, Any] = {}
    if image.kind != "video" and _is_video(image.url):
        updates["kind"] = "video"
    if image.id is None and image.url:
        updates["id"] = image_id(image.url)
    return image.model_copy(update=updates) if updates else image


def list_thumbnail(raw: Mapping[str, Any], nsfw: bool) -> Optional[Image]:
    """A list result's image (`image_url`, else `video_url`): no level, no blurhash, NSFW with its model."""
    url, kind = https_url(raw.get("image_url")), "image"
    if url is None:
        url, kind = https_url(raw.get("video_url")), "video"
    if url is None:
        return None
    if _is_video(url):
        kind = "video"
    return Image(url=url, blurhash=None, nsfw=nsfw, nsfw_level=None, kind=kind, poi=False, id=image_id(url))


# Downloads --------------------------------------------------------------------------


@dataclass(frozen=True)
class Download:
    """Where a file is downloaded from, and who authenticates it."""

    url: str
    #: The marketplace provider of the queue: "civitai" or "huggingface".
    auth_provider_id: str
    #: A gated Hugging Face repository: the user's token must have access.
    gated: bool = False
    #: A paid (early access) CivitAI version.
    paid: bool = False


def _encoded(url: str) -> Optional[str]:
    """`url` with its path and query percent-encoded where needed (spaces, non-ASCII), existing escapes kept."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    path = quote(parts.path, safe=_URL_SAFE)
    query = quote(parts.query, safe=_URL_SAFE)
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def civitai_download_url(value: Any) -> Optional[str]:
    """A CivitAI download URL as the queue gets it: absolute, on civitai.com (a civitai.red one is
    moved), under `/api/download/`, and accepted by the allowlist; None otherwise."""
    text = _text(value)
    if text is None:
        return None
    if text.startswith("/api/download/"):
        text = "https://civitai.com" + text
    url = _encoded(civitai.com_download_url(text))
    if url is None or not is_allowed_download_url(SOURCE_ID, url):
        return None
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "civitai.com" or not parts.path.startswith("/api/download/"):
        return None
    return url


def huggingface_download_url(value: Any) -> Optional[str]:
    """A Hugging Face mirror as a download URL: on huggingface.co, a `/resolve/` path, percent-encoded,
    accepted by the allowlist; None otherwise (a `/blob/` page, another host)."""
    text = _text(value)
    if text is None:
        return None
    url = _encoded(text)
    if url is None or not is_allowed_download_url(SOURCE_ID, url):
        return None
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "huggingface.co" or "/resolve/" not in parts.path:
        return None
    return url


def mirrors(raw_file: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _dicts(raw_file.get("mirrors"))


def download_for(raw_file: Mapping[str, Any], *, served_by_civitai: bool) -> Optional[Download]:
    """The download policy of one file (see the module docstring); None when no URL is offered.

    `served_by_civitai`: neither the file, its version nor its model is deleted, so the file's own
    `download_url` works when no `civitai` mirror says otherwise.
    """
    entries = mirrors(raw_file)
    civitai_entries = [mirror for mirror in entries if mirror.get("source") == "civitai"]
    for mirror in civitai_entries:
        if _deleted(mirror.get("deleted_at")):
            continue
        url = civitai_download_url(mirror.get("url"))
        if url is not None:
            return Download(url=url, auth_provider_id="civitai", paid=_is_true(mirror.get("is_paid")))
    if not civitai_entries and served_by_civitai:
        url = civitai_download_url(raw_file.get("download_url"))
        if url is not None:
            return Download(url=url, auth_provider_id="civitai")
    found: List[Download] = []
    for mirror in entries:
        if mirror.get("source") != "huggingface" or _deleted(mirror.get("deleted_at")):
            continue
        url = huggingface_download_url(mirror.get("url"))
        if url is not None:
            found.append(Download(url=url, auth_provider_id="huggingface", gated=_is_true(mirror.get("is_gated"))))
    open_first = sorted(found, key=lambda download: download.gated)
    return open_first[0] if open_first else None


def file_format(name: str) -> Optional[str]:
    """"SafeTensor", "PickleTensor" or "GGUF" from the file name's extension; None for anything else."""
    lowered = name.lower()
    return next((label for extension, label in _FORMATS.items() if lowered.endswith(extension)), None)


def normalize_file(raw: Any, *, served_by_civitai: bool) -> Optional[Tuple[File, Download]]:
    """One file and where it downloads from; None without an id or a download URL (`download_for`)."""
    if not isinstance(raw, dict):
        return None
    file_id = _id(raw.get("id"))
    if file_id is None:
        return None
    download = download_for(raw, served_by_civitai=served_by_civitai and not _deleted(raw.get("deleted_at")))
    if download is None:
        return None
    name = _text(raw.get("name")) or f"file-{file_id}"
    size_kb = _float(raw.get("size_kb"))
    file = File(
        id=str(file_id),
        name=name,
        size_bytes=round(size_kb * 1024) if size_kb is not None and size_kb > 0 else None,
        sha256=_sha256(raw.get("sha256")),
        format=file_format(name),
        precision=None,
        file_type=_text(raw.get("type")),
        primary=_is_true(raw.get("is_primary")),
        download_url=download.url,
        auth_provider_id=download.auth_provider_id,
    )
    return file, download


def _with_primary(files: List[File]) -> List[File]:
    """The files, one of them primary: the one CivArchive flags, else the first `Model` file, else the first."""
    if not files or any(file.primary for file in files):
        return files
    chosen = next((index for index, file in enumerate(files) if (file.file_type or "").lower() == "model"), 0)
    return [file.model_copy(update={"primary": True}) if index == chosen else file for index, file in enumerate(files)]


# Models and versions ---------------------------------------------------------------------


def _trigger_words(raw_version: Mapping[str, Any]) -> List[str]:
    words: Dict[str, None] = {}
    for word in _list(raw_version.get("trigger")):
        if isinstance(word, str):
            cleaned = word.strip().strip(",").strip()
            if cleaned:
                words.setdefault(cleaned, None)
    return list(words)


def _creator(raw: Mapping[str, Any]) -> Optional[str]:
    return _text(raw.get("username")) or _text(raw.get("creator_username"))


@dataclass(frozen=True)
class VersionParts:
    """A version shown in full, with where each of its files downloads from."""

    version: Version
    downloads: Tuple[Download, ...]


def normalize_version(raw_model: Mapping[str, Any], raw_version: Mapping[str, Any], max_level: int) -> VersionParts:
    """The version shown in full: its downloadable files, its images, NSFW by its level or when
    none of its images is safe."""
    version_id = _id(raw_version.get("id"))
    if version_id is None:
        raise ValueError("version without an id")
    images = [image for image in (normalize_image(raw, max_level) for raw in _list(raw_version.get("images"))) if image]
    served = not _deleted(raw_model.get("deleted_at")) and not _deleted(raw_version.get("deleted_at"))
    files: List[File] = []
    downloads: List[Download] = []
    for raw_file in _list(raw_version.get("files")):
        found = normalize_file(raw_file, served_by_civitai=served)
        if found is not None:
            files.append(found[0])
            downloads.append(found[1])
    nsfw = level_nsfw(raw_version.get("nsfw_level"), raw_version.get("is_nsfw"), max_level) or not any(
        not image.nsfw for image in images
    )
    version = Version(
        id=str(version_id),
        name=_text(raw_version.get("name")) or str(version_id),
        base_model=_text(raw_version.get("base_model")),
        trigger_words=_trigger_words(raw_version),
        created_at=_text(raw_version.get("created_at")),
        early_access=any(download.paid for download in downloads),
        nsfw=nsfw,
        images=images,
        files=_with_primary(files),
    )
    return VersionParts(version=version, downloads=tuple(downloads))


def version_shells(raw_model: Mapping[str, Any], shown: str, nsfw: bool) -> List[Version]:
    """The model's other versions, as CivArchive lists them: `partial`, a name and a date, no
    file, no image. `nsfw` is the model's level rule: a version's level is never above its model's."""
    shells: List[Version] = []
    seen = {shown}
    for entry in _dicts(raw_model.get("versions")):
        version_id = _id(entry.get("id"))
        if version_id is None or str(version_id) in seen:
            continue
        seen.add(str(version_id))
        shells.append(
            Version(
                id=str(version_id),
                name=_text(entry.get("name")) or str(version_id),
                created_at=_text(entry.get("created_at")),
                nsfw=nsfw,
                partial=True,
            )
        )
    return shells


def deleted_note(
    raw_model: Mapping[str, Any], raw_version: Mapping[str, Any], downloads: Sequence[Download]
) -> Optional[str]:
    """One line for a model (or version) deleted from CivitAI: when, and where its files come from."""
    if _deleted(raw_model.get("deleted_at")):
        day = _day(raw_model.get("deleted_at"))
        line = "Deleted from CivitAI" + (f" on {day}" if day else "")
    elif _deleted(raw_version.get("deleted_at")):
        day = _day(raw_version.get("deleted_at"))
        line = "This version was deleted from CivitAI" + (f" on {day}" if day else "")
    else:
        return None
    providers = {download.auth_provider_id for download in downloads}
    if not downloads:
        return line + ": none of its files is on a host this browser downloads from."
    if providers == {"huggingface"}:
        return line + ": its files come from Hugging Face mirrors uploaded by other people."
    return line + "."


def _model_id(raw: Mapping[str, Any]) -> str:
    model_id = _id(raw.get("id"))
    if model_id is None:
        raise ValueError("model without an id")
    return str(model_id)


def normalize_detail(raw: Mapping[str, Any], max_level: int) -> ModelDetail:
    """A model answer (its `version` in full) as a model detail: that version first, then the
    others as `partial` shells (`version_shells`); NSFW marked, description sanitised, nothing filtered."""
    model_id = _model_id(raw)
    raw_version = raw.get("version")
    if not isinstance(raw_version, dict):
        raise ValueError("model without a version")
    shown = normalize_version(raw, raw_version, max_level)
    version = shown.version
    level_rule = level_nsfw(raw.get("nsfw_level"), raw.get("is_nsfw"), max_level)
    model_type = _text(raw.get("type")) or "Other"
    description = raw.get("description")
    parts = [description if isinstance(description, str) else ""]
    note = deleted_note(raw, raw_version, shown.downloads)
    if note:
        parts.append(f"<p>{html.escape(note)}</p>")
    return ModelDetail(
        source=SOURCE_ID,
        id=model_id,
        name=_text(raw.get("name")) or f"Model {model_id}",
        type=model_type,
        mb_type=civitai_mb_type(model_type) if version.files else None,
        creator=_creator(raw),
        description_html=sanitize_html("".join(parts)) or None,
        tags=_strings(raw.get("tags")),
        license=None,
        source_url=model_page_url(model_id, version.id),
        nsfw=level_rule or version.nsfw,
        poi=any(image.poi for image in version.images),
        gated=any(download.gated for download in shown.downloads),
        stats=Stats(downloads=_int(raw.get("download_count"))),
        versions=[version] + version_shells(raw, version.id, level_rule),
    )


def item_from_detail(detail: ModelDetail, item_id: str) -> SearchItem:
    """A search result made from a detail (a pasted link): the version shown, its primary file's hash."""
    version = detail.versions[0] if detail.versions else None
    primary = next((file for file in version.files if file.primary), None) if version else None
    base_model = version.base_model if version else None
    return SearchItem(
        source=SOURCE_ID,
        id=item_id,
        name=detail.name,
        type=detail.type,
        mb_type=detail.mb_type,
        base_model=base_model,
        base_models=[base_model] if base_model else [],
        creator=detail.creator,
        nsfw=detail.nsfw,
        poi=detail.poi,
        early_access=bool(version and version.early_access),
        gated=detail.gated,
        thumbnail=civitai.pick_thumbnail(version.images) if version else None,
        stats=detail.stats,
        tags=list(detail.tags),
        updated_at=version.created_at if version else None,
        source_url=detail.source_url,
        primary_sha256=primary.sha256 if primary else None,
    )


def is_listed(raw: Any) -> bool:
    """A search result the source shows: a CivitAI version with a model id."""
    return (
        isinstance(raw, dict)
        and raw.get("platform", PLATFORM) == PLATFORM
        and raw.get("kind", KIND) == KIND
        and _id(raw.get("model_id")) is not None
    )


def newest_per_model(results: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """One result per model: its newest version (`created_at`, then the version id), at the
    place of the model's first result."""
    chosen: Dict[int, Mapping[str, Any]] = {}

    def age(raw: Mapping[str, Any]) -> Tuple[float, int]:
        return (_float(raw.get("created_at")) or 0.0, _id(raw.get("version_id")) or 0)

    for raw in results:
        model_id = _id(raw.get("model_id"))
        known = chosen.get(model_id)
        if known is None or age(raw) > age(known):
            chosen[model_id] = raw
    return list(chosen.values())


def normalize_item(raw: Mapping[str, Any]) -> SearchItem:
    """A search result (a version of a model). NSFW when `is_nsfw` is set or the model was deleted
    from CivitAI (see the module docstring); no hash, so no `primary_sha256`."""
    model_id = _id(raw.get("model_id"))
    if model_id is None:
        raise ValueError("result without a model id")
    version_id = _id(raw.get("version_id"))
    nsfw = _is_true(raw.get("is_nsfw")) or _is_true(raw.get("is_deleted")) or _deleted(raw.get("deleted_at"))
    model_type = _text(raw.get("type")) or "Other"
    base_model = _text(raw.get("base_model"))
    return SearchItem(
        source=SOURCE_ID,
        id=str(model_id),
        name=_text(raw.get("name")) or f"Model {model_id}",
        type=model_type,
        mb_type=civitai_mb_type(model_type),
        base_model=base_model,
        base_models=[base_model] if base_model else [],
        creator=_text(raw.get("username")),
        nsfw=nsfw,
        poi=False,
        early_access=False,
        gated=False,
        thumbnail=list_thumbnail(raw, nsfw),
        stats=Stats(downloads=_int(raw.get("download_count"))),
        tags=_strings(raw.get("tags")),
        updated_at=_epoch_text(raw.get("created_at")),
        source_url=model_page_url(model_id, version_id),
        primary_sha256=None,
    )


class ModelNotOnCivArchive(SourceNotFound):
    """CivArchive answered that the model or version does not exist (a 500 page): the build id is fine."""


# The source ---------------------------------------------------------------------------


class CivArchiveSource:
    """CivArchive behind the `Source` interface. `http_client` / `cache_store` default to the shared
    instances; `clock` gives epoch seconds (tests move it)."""

    id = SOURCE_ID
    label = LABEL

    def __init__(
        self, http_client: Any = None, cache_store: Any = None, clock: Callable[[], float] = time.time
    ) -> None:
        self._http_client = http_client
        self._cache_store = cache_store
        self._clock = clock
        #: (build id, epoch seconds it was read from the home page).
        self._build: Optional[Tuple[str, float]] = None
        #: (the stale build id, when it was replaced): later 404s under that id reuse the new one.
        self._renewed: Optional[Tuple[str, float]] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._filters_failed_at: Optional[float] = None

    def _client(self) -> Any:
        return self._http_client if self._http_client is not None else http_module.http

    def _store(self) -> Any:
        return self._cache_store if self._cache_store is not None else cache_module.cache

    @staticmethod
    def _max_level(max_level: Optional[int]) -> int:
        return int(settings.get_setting("nsfw_max_level") if max_level is None else max_level)

    def _loop_lock(self) -> asyncio.Lock:
        """The build id lock of the running event loop (an asyncio lock belongs to one loop)."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    # Cache ----------------------------------------------------------------------------

    def _cache_get(self, request: Any, ttl_seconds: float) -> Any:
        try:
            return self._store().get(SOURCE_ID, request, ttl_seconds=ttl_seconds)
        except Exception:  # noqa: BLE001 - the cache is an optimisation
            logger.warning("[MODEL-BROWSER] Could not read the cache; asking CivArchive", exc_info=True)
            return None

    def _cache_set(self, request: Any, payload: Any, ttl_seconds: float) -> None:
        try:
            self._store().set(SOURCE_ID, request, payload, ttl_seconds=ttl_seconds)
        except Exception:  # noqa: BLE001
            logger.warning("[MODEL-BROWSER] Could not write the cache", exc_info=True)

    # The build id ---------------------------------------------------------------------

    def _fresh_build(self) -> Optional[str]:
        if self._build is None:
            return None
        build_id, resolved_at = self._build
        return build_id if 0 <= self._clock() - resolved_at < BUILD_ID_TTL_SECONDS else None

    async def build_id(self) -> str:
        """The deployment's build id: from memory, else the cache, else the home page (one request
        for concurrent callers). Raises `SourceUnavailable` when the page has none."""
        current = self._fresh_build()
        if current is not None:
            return current
        async with self._loop_lock():
            current = self._fresh_build()
            if current is not None:
                return current
            cached = self._cache_get(BUILD_ID_REQUEST, BUILD_ID_TTL_SECONDS)
            if isinstance(cached, dict) and isinstance(cached.get("build_id"), str):
                resolved_at = _float(cached.get("resolved_at"))
                if _BUILD_ID_TEXT.fullmatch(cached["build_id"]) and resolved_at is not None:
                    self._build = (cached["build_id"], resolved_at)
                    if self._fresh_build() is not None:
                        return cached["build_id"]
            return await self._resolve()

    async def renew_build_id(self, stale: str) -> str:
        """A new build id after `stale` answered 404: the home page is read once for every caller
        that saw the same stale id (within `RENEW_HOLD_SECONDS`, even when it gave that id again)."""
        async with self._loop_lock():
            current = self._fresh_build()
            renewed = self._renewed
            just_renewed = (
                renewed is not None and renewed[0] == stale and 0 <= self._clock() - renewed[1] < RENEW_HOLD_SECONDS
            )
            if current is not None and (current != stale or just_renewed):
                return current
            self._build = None
            build_id = await self._resolve()
            self._renewed = (stale, self._clock())
            if build_id != stale:
                logger.info("[MODEL-BROWSER] CivArchive deployed a new version: build id renewed")
            return build_id

    async def _resolve(self) -> str:
        """Read the build id from the home page; store it in memory and in the cache. Call under the lock."""
        page = await self._client().get_text(SOURCE_ID, SITE + "/", max_bytes=HOME_MAX_BYTES)
        match = _BUILD_ID.search(page)
        if match is None or not _BUILD_ID_TEXT.fullmatch(match.group(1)):
            raise SourceUnavailable("CivArchive changed its page layout: no build id")
        build_id, now = match.group(1), self._clock()
        self._build = (build_id, now)
        self._cache_set(BUILD_ID_REQUEST, {"build_id": build_id, "resolved_at": now}, BUILD_ID_TTL_SECONDS)
        return build_id

    # Data routes ----------------------------------------------------------------------

    async def _data(self, path: str, params: Sequence[Tuple[str, Any]], *, ttl_seconds: float) -> Dict[str, Any]:
        """The `pageProps` of `/_next/data/<build id>/<path>` with `params`, through the cache.

        A 404 is read as a stale build id: renewed, then the request is made once more, whose
        404 is raised (`SourceNotFound`).
        """
        pairs = http_module.normalise_params(list(params))
        request = {"path": path, "params": [list(pair) for pair in sorted(pairs)]}
        cached = self._cache_get(request, ttl_seconds)
        if isinstance(cached, dict):
            return cached
        build_id = await self.build_id()
        try:
            props = await self._fetch(build_id, path, pairs)
        except ModelNotOnCivArchive:
            raise
        except SourceNotFound:
            props = await self._fetch(await self.renew_build_id(build_id), path, pairs)
        self._cache_set(request, props, ttl_seconds)
        return props

    async def _fetch(self, build_id: str, path: str, pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
        url = f"{SITE}/_next/data/{build_id}/{path}"
        status, headers, body = await self._client().get(SOURCE_ID, url, pairs, accept_statuses=(500,))
        if status == 500:
            if _NOT_FOUND_PAGE.search(http_module.decode_text(headers, body[:65536])):
                raise ModelNotOnCivArchive("CivArchive has no such model or version", 500)
            logger.warning("[MODEL-BROWSER] CivArchive answered HTTP 500")
            raise SourceUnavailable("CivArchive answered HTTP 500", 500)
        data = http_module.decode_json(SOURCE_ID, status, body)
        props = data.get("pageProps") if isinstance(data, dict) else None
        if not isinstance(props, dict):
            raise SourceUnavailable("CivArchive sent an answer this browser cannot read")
        return {key: value for key, value in props.items() if key not in UNUSED_KEYS}

    async def raw_model(self, model_id: int, version_id: Optional[int] = None) -> Dict[str, Any]:
        """The model with `version_id` (else its latest version, through CivArchive's redirect) in full.

        `SourceNotFound` for an unknown model or version, and for a version of another model.
        """
        params: List[Tuple[str, Any]] = [("platform", PLATFORM)]
        path = f"models/{int(model_id)}.json"
        if version_id is None:
            props = await self._data(path, params, ttl_seconds=DETAIL_TTL_SECONDS)
            if not isinstance(props.get("model"), dict):
                target = parse_redirect(props.get("__N_REDIRECT"))
                if target is None or target[0] != model_id or target[1] is None:
                    raise SourceNotFound(f"CivArchive has no page for model {model_id}")
                version_id = target[1]
            else:
                return self._checked(props["model"], model_id, None)
        props = await self._data(path, params + [("modelVersionId", int(version_id))], ttl_seconds=DETAIL_TTL_SECONDS)
        return self._checked(props.get("model"), model_id, version_id)

    @staticmethod
    def _checked(raw: Any, model_id: int, version_id: Optional[int]) -> Dict[str, Any]:
        """`raw` when it is model `model_id` with version `version_id` of that model."""
        if not isinstance(raw, dict) or not isinstance(raw.get("version"), dict):
            raise SourceUnavailable("CivArchive sent an unexpected answer for a model")
        version = raw["version"]
        owner = _id(version.get("model_id")) or _id(version.get("civitai_model_id"))
        if (
            _id(raw.get("id")) != model_id
            or (version_id is not None and _id(version.get("id")) != version_id)
            or (owner is not None and owner != model_id)
        ):
            raise SourceNotFound(f"CivArchive has no version {version_id} of model {model_id}")
        return raw

    async def hash_page(self, sha256: str) -> Dict[str, Any]:
        """`sha256/<hash>.json`: `files` (its mirrors) and `models` (each with the version that has it, in full)."""
        key = _sha256(str(sha256).strip())
        if key is None:
            raise SourceInvalidRequest("A SHA256 is 64 hexadecimal characters")
        return await self._data(f"sha256/{key}.json", [], ttl_seconds=HASH_TTL_SECONDS)

    # Source interface ------------------------------------------------------------------

    async def info(self) -> SourceInfo:
        """Types and base models from a search's `filterOptions` (cached an hour); empty lists when
        CivArchive is unreachable (not asked again for `FILTERS_RETRY_SECONDS`)."""
        types: List[FilterOption] = []
        base_models: List[FilterOption] = []
        failed_at = self._filters_failed_at
        if failed_at is None or not 0 <= self._clock() - failed_at < FILTERS_RETRY_SECONDS:
            try:
                props = await self._data("search.json", [("platform", PLATFORM)], ttl_seconds=FILTERS_TTL_SECONDS)
            except SourceError as exc:
                self._filters_failed_at = self._clock()
                logger.warning("[MODEL-BROWSER] CivArchive filter lists unavailable: %s", exc.message)
            else:
                self._filters_failed_at = None
                options = props.get("filterOptions") if isinstance(props.get("filterOptions"), dict) else {}
                types = [FilterOption(value=name, label=name) for name in _strings(options.get("modelTypes"))]
                base_models = [FilterOption(value=name, label=name) for name in _strings(options.get("baseModels"))]
        return SourceInfo(
            id=SOURCE_ID,
            label=LABEL,
            enabled=True,
            types=types,
            base_models=base_models,
            sorts=[FilterOption(value=key, label=label) for key, label in SORTS],
            periods=[FilterOption(value=key, label=label) for key, _, label in PERIODS],
            search_help=SEARCH_HELP,
            notice=NOTICE,
        )

    async def search(self, query: SearchQuery, *, max_level: Optional[int] = None) -> SearchPage:
        """One CivArchive page (50 versions, one item per model) for `query`; NSFW is marked, not filtered."""
        level = self._max_level(max_level)
        page = parse_cursor(query.cursor)
        parsed = parse_query(query.q)
        # A bad sort or period is a 400 whatever the search box holds.
        _sort(query.sort)
        _period(query.period)
        if parsed.kind == "model":
            return await self._search_model(parsed, page, level)
        params = search_params(parsed, query, page)
        try:
            props = await self._data("search.json", params, ttl_seconds=SEARCH_TTL_SECONDS)
        except SourceNotFound:
            return SearchPage(source=SOURCE_ID, items=[], next_cursor=None)
        data = props.get("data") if isinstance(props.get("data"), dict) else {}
        results = _list(data.get("results"))
        total = _int(data.get("total_hits"))
        more = len(results) >= PAGE_SIZE and (total is None or page * PAGE_SIZE < total)
        return SearchPage(
            source=SOURCE_ID,
            items=self._normalise_items(results),
            next_cursor=str(page + 1) if more else None,
        )

    async def detail(self, model_id: str, *, max_level: Optional[int] = None) -> ModelDetail:
        """A model with one version in full: the one `model_id` names ("78291:83095"), else the latest."""
        level = self._max_level(max_level)
        ref = parse_model_ref(model_id)
        if ref is None:
            raise SourceNotFound("CivArchive model ids are CivitAI model numbers, such as 78291 or 78291:83095")
        raw = await self.raw_model(*ref)
        try:
            return normalize_detail(raw, level)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise SourceUnavailable(
                f"CivArchive sent a model this browser cannot read ({exc.__class__.__name__})"
            ) from None

    async def version_detail(self, model_id: str, version_id: Any, *, max_level: Optional[int] = None) -> ModelDetail:
        """The model with `version_id` in full, whatever version `model_id` names: what a download
        checks its file against (`downloads.prepare_download`)."""
        ref = parse_model_ref(model_id)
        if ref is None:
            raise SourceNotFound("CivArchive model ids are CivitAI model numbers, such as 78291 or 78291:83095")
        wanted = _id(version_id)
        return await self.detail(model_ref(ref[0], wanted if wanted is not None else ref[1]), max_level=max_level)

    # Steps ------------------------------------------------------------------------------

    async def _search_model(self, parsed: ParsedQuery, page: int, level: int) -> SearchPage:
        """A pasted link: that model, as one item (none past the first page, or when CivArchive has no such model)."""
        if page != 1 or parsed.model_id is None:
            return SearchPage(source=SOURCE_ID, items=[], next_cursor=None)
        item_id = model_ref(parsed.model_id, parsed.version_id)
        try:
            detail = await self.detail(item_id, max_level=level)
        except SourceNotFound:
            return SearchPage(source=SOURCE_ID, items=[], next_cursor=None)
        return SearchPage(source=SOURCE_ID, items=[item_from_detail(detail, item_id)], next_cursor=None)

    @staticmethod
    def _normalise_items(results: Sequence[Any]) -> List[SearchItem]:
        items: List[SearchItem] = []
        for raw in newest_per_model([raw for raw in results if is_listed(raw)]):
            try:
                items.append(normalize_item(raw))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.warning(
                    "[MODEL-BROWSER] Skipping a CivArchive result this browser cannot read (model %r): %s",
                    raw.get("model_id"),
                    exc,
                )
        return items
