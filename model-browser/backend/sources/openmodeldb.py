"""OpenModelDB as a model-browser source (PLAN.md §8.4).

OpenModelDB (https://openmodeldb.info) has no search API: it publishes its whole catalogue
of upscalers as three static files under `/api/v1`, `models.json` (an object keyed by model
id, about 1.5 MB), `tags.json` (tag key -> name) and `architectures.json` (key -> name,
input). The source downloads them through the shared `SourceHttp`, keeps the raw answers in
the plugin cache as `{"body", "fetched_at"}` for `CATALOG_TTL_SECONDS` (6 hours), and
answers from a parsed in-memory snapshot (`Catalog`: the models, a sha256 index of their
files, the tag and architecture labels, the search entries in each sort order):
- the snapshot is rebuilt once it is older than the TTL: from the cache rows while they are
  fresh (after a restart), else from the network. An `asyncio.Lock` makes concurrent loads
  share one download;
- a failed refresh keeps the previous snapshot (with a warning) and is tried again after
  `RETRY_SECONDS`. Without any snapshot, the `SourceError` of `http.py` is raised, and the
  same error is given for `FAILURE_HOLD_SECONDS` rather than asking again;
- `tags.json` and `architectures.json` are optional: without them the keys are the labels.

Search runs over the snapshot: `@author` (one of the model's authors, case-insensitive),
`#tag` (a tag key or its name), a pasted `openmodeldb.info/models/<id>` link (that model,
whatever the filters), free text (every word somewhere in the id, name, authors,
description, tags or architecture); `types` are architecture keys, `base_models` scales
("4"); sorts `downloadable` (the models this browser can download first, then as `newest`;
the default), `newest` (date, then name), `oldest` and `name`; no periods (a period is
ignored). The cursor is the offset of the next page ("24").

Normalisation: one version per model ("Release"), whose files are the resources the
download worker can fetch as they are (`direct_url`: a Hugging Face `/resolve/` URL, a
GitHub release asset or raw file, Oracle or Backblaze object storage, whose file name has
the resource's extension: a `.zip` holding several models is not the file), except the
ONNX exports, which PotionUI can neither index nor load (`file_url`). A model with such a
file is an `upscaler`; a model without one (Google Drive, Mega, OneDrive ... only, or ONNX
only) has no `mb_type` and the page shows it as not downloadable. The description starts
with the model's facts (architecture, scale, input, channels, dataset, training), then
names what only the OpenModelDB page offers ("Other downloads ...: Google Drive, ONNX"),
and ends with a note when PotionUI's built-in upscaler may not run the model (it loads
ESRGAN `.pth` checkpoints only). Previews: the model's own thumbnail (a crop OpenModelDB
serves from `/thumbs/`) first, then its gallery, never from the hosts whose image links are
dead (`DEAD_IMAGE_HOSTS`); the card shows the model's thumbnail, else the small one
OpenModelDB made of a gallery image.

NSFW: OpenModelDB has none. Models, versions and images are never NSFW (every image is
level 1): `max_level` and `query.safe` change nothing.
"""

import asyncio
import hashlib
import html
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from .. import cache as cache_module
from .. import http as http_module
from ..http import SourceError, SourceInvalidRequest, SourceNotFound, SourceRateLimited, SourceUnavailable
from ..schema import (
    File,
    FilterOption,
    Image,
    License,
    ModelDetail,
    SearchItem,
    SearchPage,
    SourceInfo,
    Stats,
    Version,
)
from ..security import is_allowed_download_url, sanitize_html
from .base import SearchQuery
from .huggingface import MARKDOWN_EXTRAS

logger = logging.getLogger("plugins.model-browser")

SOURCE_ID = "openmodeldb"
LABEL = "OpenModelDB"
SITE = "https://openmodeldb.info"
API_BASE = SITE + "/api/v1"
MODELS_URL = API_BASE + "/models.json"
TAGS_URL = API_BASE + "/tags.json"
ARCHITECTURES_URL = API_BASE + "/architectures.json"

#: How long a downloaded catalogue is used. OpenModelDB says `max-age=600`, but its
#: catalogue changes a few times a week and weighs 1.5 MB.
CATALOG_TTL_SECONDS = 6 * 3600
#: After a failed refresh, the previous catalogue is served this long before trying again.
RETRY_SECONDS = 10 * 60
#: Without any catalogue, a failed load is answered with the same error this long.
FAILURE_HOLD_SECONDS = 30

#: The PotionUI type of every downloadable OpenModelDB model.
MB_TYPE = "upscaler"
#: The level of every image: OpenModelDB has no NSFW content.
IMAGE_LEVEL = 1
#: The name of a model's one version.
VERSION_NAME = "Release"
#: Previews of a model kept at most, its own thumbnail included.
MAX_IMAGES = 12
#: Image hosts never used, probed over the whole catalogue on 2026-10-11: every imgsli.com
#: `/i/<uuid>.jpg` answers 404 (587 gallery images), github.com links are HTML pages of blobs,
#: not images (403, 44 images), and private-user-images.githubusercontent.com links are
#: signed (`?jwt=`) and expired (404, 4 images). A host's subdomains are left out too. The
#: others answer 200: i.slow.pics, images2.imgbox.com, raw.githubusercontent.com, i.ibb.co,
#: i.imgur.com, user-images.githubusercontent.com and openmodeldb.info's `/thumbs/`.
DEAD_IMAGE_HOSTS: Tuple[str, ...] = ("imgsli.com", "github.com", "private-user-images.githubusercontent.com")
#: A longer description is shown as escaped paragraphs: it never reaches markdown2.
MAX_MARKDOWN_CHARS = 32 * 1024

#: Our sort ids with their labels, in the order the page lists them.
SORTS: Tuple[Tuple[str, str], ...] = (
    ("downloadable", "Downloadable first"),
    ("newest", "Newest"),
    ("oldest", "Oldest"),
    ("name", "Name"),
)
DEFAULT_SORT = "downloadable"
_SORT_KEYS = frozenset(key for key, _ in SORTS)

SEARCH_HELP = "Text, #tag (anime, photo, restoration, …), @author, or an openmodeldb.info model link"

#: A resource's `type` -> `File.format`.
_FORMATS = {
    "safetensors": "SafeTensor",
    "pth": "PickleTensor",
    "pt": "PickleTensor",
    "ckpt": "PickleTensor",
    "bin": "PickleTensor",
}
#: A resource's `platform` -> `File.file_type`.
_PLATFORMS = {"pytorch": "PyTorch"}
_PYTORCH = "pytorch"
#: The `platform` and `type` of an ONNX export: never offered as a file. `.onnx` is not one of
#: the core's model extensions (`SUPPORTED_MODEL_EXTENSIONS`: a rescan never sees it) and its
#: upscaler loads PyTorch checkpoints only.
_ONNX = "onnx"
#: Architectures PotionUI's built-in upscaler loads: core fa493ae,
#: `src/pipelines/pipes/upscaler/main.py`, builds an ESRGAN `RRDBNet` from `torch.load` of a `.pth`.
_LOADABLE_ARCHITECTURES = frozenset({"esrgan", "esrgan+"})

#: Hosts that only serve files, and the suffixes of object storage hosts.
_FILE_HOSTS = frozenset({"objects.githubusercontent.com", "raw.githubusercontent.com"})
_FILE_HOST_SUFFIXES = (".oraclecloud.com", ".backblazeb2.com")

#: How the description names the hosts of the downloads only the OpenModelDB page offers
#: (a host, or any of its subdomains); other hosts are named as they are, without `www.`.
_HOST_LABELS: Tuple[Tuple[str, str], ...] = (
    ("drive.google.com", "Google Drive"),
    ("docs.google.com", "Google Drive"),
    ("mega.nz", "Mega"),
    ("mega.co.nz", "Mega"),
    ("1drv.ms", "OneDrive"),
    ("onedrive.live.com", "OneDrive"),
    ("mediafire.com", "MediaFire"),
    ("pcloud.link", "pCloud"),
    ("pcloud.com", "pCloud"),
    ("drive.proton.me", "Proton Drive"),
    ("icedrive.net", "Icedrive"),
    ("1fichier.com", "1fichier"),
    ("dropbox.com", "Dropbox"),
    ("zippyshare.com", "Zippyshare"),
    ("catbox.moe", "Catbox"),
    ("lbry.tv", "LBRY"),
    ("github.com", "GitHub"),
    ("githubusercontent.com", "GitHub"),
    ("huggingface.co", "Hugging Face"),
    ("oraclecloud.com", "Oracle Cloud"),
    ("backblazeb2.com", "Backblaze B2"),
)

# A model id as OpenModelDB makes them ("4x-UltraSharp"), never more than a route accepts.
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CURSOR = re.compile(r"[0-9]{1,9}")
_SCALE = re.compile(r"([0-9]{1,3})x?", re.I)
_EXTENSION = re.compile(r"[a-z0-9]{1,16}")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
#: Never part of an image URL the page is given.
_ODD_URL_CHARACTERS = frozenset("\\\"'<>`")


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


def _positive(value: Any) -> Optional[int]:
    number = _int(value)
    return number if number is not None and number > 0 else None


def _list(value: Any) -> List[Any]:
    """`value` when it is a list, else an empty one (a string is never iterated)."""
    return value if isinstance(value, list) else []


def _strings(values: Any) -> List[str]:
    """The non-empty strings of a list, stripped, once each, in order."""
    return list(dict.fromkeys(value.strip() for value in _list(values) if isinstance(value, str) and value.strip()))


def _sha256(value: Any) -> Optional[str]:
    return value.lower() if isinstance(value, str) and _SHA256.fullmatch(value) else None


def is_model_id(value: Any) -> bool:
    """An OpenModelDB model id: letters, digits, `.`, `_`, `+` and `-`, at most 200 characters, no `..`."""
    return isinstance(value, str) and ".." not in value and bool(_MODEL_ID.fullmatch(value))


def model_page_url(model_id: str) -> str:
    return f"{SITE}/models/{model_id}"


def authors(raw: Mapping[str, Any]) -> List[str]:
    """`author`: one name, or a list of names (16 models have several)."""
    value = raw.get("author")
    return _strings(value) if isinstance(value, list) else ([value.strip()] if _text(value) else [])


def scale_of(raw: Mapping[str, Any]) -> Optional[int]:
    return _positive(raw.get("scale"))


def date_of(raw: Mapping[str, Any]) -> Optional[str]:
    value = _text(raw.get("date"))
    return value if value is not None and _DATE.fullmatch(value) else None


def resources(raw: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [resource for resource in _list(raw.get("resources")) if isinstance(resource, dict)]


# Direct downloads -----------------------------------------------------------------


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def is_direct_url(url: Any) -> bool:
    """Whether the download worker can fetch `url` as the file itself (no page, no login).

    An https URL that `security.is_allowed_download_url("openmodeldb", ...)` accepts, on
    huggingface.co with `/resolve/` in its path, on github.com as a release asset
    (`/<owner>/<repo>/releases/download/...`) or a raw file (`/<owner>/<repo>/raw/...`,
    which GitHub redirects to raw.githubusercontent.com), or on a host that only serves
    files (objects.githubusercontent.com, raw.githubusercontent.com, Oracle and Backblaze
    object storage). Google Drive, Mega, OneDrive, MediaFire ... answer a page: never direct.
    """
    if not isinstance(url, str) or not is_allowed_download_url(SOURCE_ID, url):
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "huggingface.co":
        return "/resolve/" in parts.path
    if host == "github.com":
        segments = parts.path.split("/")[1:]
        if len(segments) >= 6 and segments[2:4] == ["releases", "download"]:
            return all(segments[:2]) and bool(segments[-1])
        if len(segments) >= 5 and segments[2] == "raw":
            return all(segments[:2]) and bool(segments[-1])
        return False
    return host in _FILE_HOSTS or host.endswith(_FILE_HOST_SUFFIXES)


def _extension(kind: Any) -> str:
    """The file name extension a resource `type` implies (".pth"), "" for no usable type."""
    kind = kind.strip().lower() if isinstance(kind, str) else ""
    return f".{kind}" if _EXTENSION.fullmatch(kind) else ""


def direct_url(resource: Mapping[str, Any]) -> Optional[str]:
    """The first URL of a resource the worker can download as the file itself; None when it has none.

    A direct URL (`is_direct_url`) whose file name ends with the resource's extension: a
    release asset that is an archive (`.zip`, `.pth.tar`) holds more than the file, and its
    bytes would never match the resource's SHA256.
    """
    extension = _extension(resource.get("type"))
    for url in _strings(resource.get("urls")):
        if not is_direct_url(url):
            continue
        name = url_file_name(url)
        if extension and not (name and name.lower().endswith(extension)):
            continue
        return url
    return None


def is_onnx(resource: Mapping[str, Any]) -> bool:
    """An ONNX export: its `platform` or its `type` is onnx."""
    return _ONNX in ((_text(resource.get("platform")) or "").lower(), (_text(resource.get("type")) or "").lower())


def file_url(resource: Mapping[str, Any]) -> Optional[str]:
    """The URL a resource is offered as a file with: its `direct_url`, unless it is an ONNX
    export (PotionUI can neither index nor load one); None when it is not offered."""
    return None if is_onnx(resource) else direct_url(resource)


def host_label(host: str) -> str:
    """A host as the description names it: "Google Drive", "Mega" ..., else the host without `www.`."""
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    for domain, label in _HOST_LABELS:
        if host == domain or host.endswith("." + domain):
            return label
    return host


def other_downloads(raw: Mapping[str, Any]) -> List[str]:
    """What only the OpenModelDB page offers, once each, in the resources' order: "ONNX" for an
    ONNX export, else the hosts (as `host_label` names them) of a resource without a direct URL."""
    labels: Dict[str, None] = {}
    for resource in resources(raw):
        urls = _strings(resource.get("urls"))
        if not urls or file_url(resource) is not None:
            continue
        if is_onnx(resource):
            labels.setdefault("ONNX", None)
            continue
        for url in urls:
            host = _host(url)
            if host:
                labels.setdefault(host_label(host), None)
    return list(labels)


def url_file_name(url: str) -> Optional[str]:
    """The last segment of the URL's path, percent-decoded, when it is a plain file name."""
    try:
        segment = urlsplit(url).path.rsplit("/", 1)[-1]
    except ValueError:
        return None
    name = unquote(segment).strip()
    if not name or name in (".", "..") or any(char in "/\\:" for char in name):
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
        return None
    return name


def file_name(model_id: str, url: str, kind: Optional[str]) -> str:
    """The URL's file name when it ends with the resource's extension, else `<model id>.<type>`."""
    extension = _extension(kind)
    name = url_file_name(url)
    if name and (not extension or name.lower().endswith(extension)):
        return name
    return f"{model_id}{extension}"


def model_files(model_id: str, raw: Mapping[str, Any]) -> List[File]:
    """The resources offered as files (`file_url`: a direct URL, no ONNX export), the primary one first.

    The id is the resource's SHA256 (its index without one); a second resource with the
    same SHA256 is left out. `primary` is the first PyTorch file, else the first file; the
    others keep the catalogue's order.
    """
    found: List[Tuple[Dict[str, Any], str, str]] = []
    seen = set()
    for index, resource in enumerate(resources(raw)):
        url = file_url(resource)
        if url is None:
            continue
        sha256 = _sha256(resource.get("sha256"))
        file_id = sha256 or str(index)
        if file_id in seen:
            continue
        seen.add(file_id)
        found.append((resource, url, file_id))
    platforms = [(_text(resource.get("platform")) or "").lower() for resource, _, _ in found]
    primary = next((index for index, platform in enumerate(platforms) if platform == _PYTORCH), 0)
    files: List[File] = []
    for index, (resource, url, file_id) in enumerate(found):
        kind = _text(resource.get("type"))
        platform = _text(resource.get("platform"))
        size = _int(resource.get("size"))
        files.append(
            File(
                id=file_id,
                name=file_name(model_id, url, kind),
                size_bytes=size if size is not None and size >= 0 else None,
                sha256=_sha256(resource.get("sha256")),
                format=_FORMATS.get(kind.lower()) if kind else None,
                precision=None,
                file_type=_PLATFORMS.get(platform.lower(), platform) if platform else None,
                primary=index == primary,
                download_url=url,
                auth_provider_id=None,
            )
        )
    return files[primary:primary + 1] + files[:primary] + files[primary + 1:]


# Images ---------------------------------------------------------------------------


def https_url(value: Any) -> Optional[str]:
    """`value` when it is an https URL with a host, on the default port, without credentials or odd characters."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or any(
        char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F or char in _ODD_URL_CHARACTERS for char in value
    ):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not parts.hostname or port not in (None, 443) or "@" in parts.netloc:
        return None
    return value


def site_url(value: Any) -> Optional[str]:
    """An image URL: an https URL as it is, a path of openmodeldb.info (`/thumbs/...`) made absolute."""
    if isinstance(value, str) and value.strip().startswith("/") and not value.strip().startswith("//"):
        return https_url(SITE + value.strip())
    return https_url(value)


def preview_url(value: Any) -> Optional[str]:
    """`site_url`, unless the image is on a host of `DEAD_IMAGE_HOSTS` (or one of its subdomains)."""
    url = site_url(value)
    if url is None:
        return None
    host = _host(url)
    if any(host == dead or host.endswith("." + dead) for dead in DEAD_IMAGE_HOSTS):
        return None
    return url


def _image(url: str, width: Optional[int] = None, height: Optional[int] = None) -> Image:
    return Image(
        url=url,
        nsfw=False,
        nsfw_level=IMAGE_LEVEL,
        width=width,
        height=height,
        kind="image",
        id=hashlib.md5(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16],
    )


def _gallery(raw: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [image for image in _list(raw.get("images")) if isinstance(image, dict)]


def _gallery_url(image: Mapping[str, Any]) -> Optional[str]:
    """The image a gallery entry shows (`preview_url`): the upscaled side (`SR`) of a pair, else its `url`."""
    if image.get("type") == "paired":
        return preview_url(image.get("SR"))
    return preview_url(image.get("url")) or preview_url(image.get("SR"))


def model_thumbnail(raw: Mapping[str, Any]) -> Optional[Image]:
    """The model's own thumbnail (`preview_url`): the `SR` of a pair, with its size, else its `url`; None without one."""
    own = raw.get("thumbnail")
    if not isinstance(own, dict):
        return None
    if own.get("type") == "paired":
        url = preview_url(own.get("SR"))
        if url:
            sizes = own.get("SRSize") if isinstance(own.get("SRSize"), dict) else {}
            return _image(url, _positive(sizes.get("width")), _positive(sizes.get("height")))
    url = preview_url(own.get("url")) or preview_url(own.get("SR"))
    return _image(url) if url else None


def version_images(raw: Mapping[str, Any]) -> List[Image]:
    """A model's previews, once each, at most `MAX_IMAGES`: its own thumbnail first, then its
    gallery (the `SR` of a pair, the `url` of a standalone image); https only, never on a dead
    host. Empty when nothing is left."""
    images: List[Image] = []
    seen = set()
    own = model_thumbnail(raw)
    if own is not None:
        images.append(own)
        seen.add(own.url)
    for entry in _gallery(raw):
        if len(images) >= MAX_IMAGES:
            break
        url = _gallery_url(entry)
        if url is None or url in seen:
            continue
        seen.add(url)
        images.append(_image(url))
    return images


def thumbnail(raw: Mapping[str, Any]) -> Optional[Image]:
    """The card's image: the model's own thumbnail, else the first small thumbnail OpenModelDB
    made of a gallery image (`/thumbs/small/...`, about 1 KB), else None."""
    own = model_thumbnail(raw)
    if own is not None:
        return own
    for entry in _gallery(raw):
        small = preview_url(entry.get("thumbnail"))
        if small:
            return _image(small)
    return None


# Licence --------------------------------------------------------------------------

_SPDX_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,63}")
NO_LICENSE = "No license stated"


def license_from(raw: Mapping[str, Any]) -> License:
    """The SPDX id OpenModelDB gives (with its spdx.org page), or "No license stated"."""
    value = _text(raw.get("license"))
    if value is None:
        return License(summary=NO_LICENSE)
    url = f"https://spdx.org/licenses/{value}.html" if _SPDX_ID.fullmatch(value) else None
    return License(summary=value, url=url)


# The catalogue --------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """One model as the search sees it: casefolded values, read once per catalogue."""

    id: str
    raw: Mapping[str, Any]
    name_key: str
    #: "YYYY-MM-DD", or "" when the model has none.
    date: str
    authors: FrozenSet[str]
    #: Tag keys and tag names.
    tags: FrozenSet[str]
    architecture: Optional[str]
    scale: Optional[int]
    #: Whether a resource is offered as a file (`file_url`): the model has an `mb_type`.
    downloadable: bool
    #: Everything free text is looked for in.
    text: str


@dataclass(frozen=True)
class Catalog:
    """A parsed catalogue: never changed once built, shared by every request until the next one."""

    #: The models by id, in OpenModelDB's order.
    models: Mapping[str, Mapping[str, Any]]
    #: A lower-case SHA256 -> (model id, the resource that has it).
    by_sha256: Mapping[str, Tuple[str, Mapping[str, Any]]]
    #: A tag key -> its name.
    tags: Mapping[str, str]
    #: An architecture key -> {"name", "input"}.
    architectures: Mapping[str, Mapping[str, Optional[str]]]
    #: Epoch seconds of the `models.json` download.
    fetched_at: float
    #: The search entries in each sort order.
    orders: Mapping[str, Tuple[Entry, ...]]
    #: A casefolded model id -> the model id.
    folded_ids: Mapping[str, str]

    def tag_name(self, key: str) -> str:
        return self.tags.get(key, key)

    def architecture_label(self, key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        known = self.architectures.get(key)
        return (known.get("name") if known else None) or key

    def architecture_input(self, key: Optional[str]) -> Optional[str]:
        known = self.architectures.get(key) if key else None
        return known.get("input") if known else None

    def find(self, model_id: str) -> Optional[str]:
        """The id of the model `model_id` names (exactly, else ignoring case); None when there is none."""
        if model_id in self.models:
            return model_id
        return self.folded_ids.get(model_id.casefold())

    def architecture_options(self) -> List[Tuple[str, str]]:
        """(key, label) of every architecture a model uses, by label."""
        keys = {entry.architecture for entry in self.orders["name"] if entry.architecture}
        options = [(key, self.architecture_label(key) or key) for key in keys]
        return sorted(options, key=lambda option: (option[1].casefold(), option[0]))

    def architecture_keys(self) -> List[str]:
        """Every architecture a filter may name: the ones models use and the ones `architectures.json` lists."""
        keys = {entry.architecture for entry in self.orders["name"] if entry.architecture}
        return sorted(keys | set(self.architectures))

    def scales(self) -> List[int]:
        return sorted({entry.scale for entry in self.orders["name"] if entry.scale})


def _parse_tags(body: Any) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(key, str) and key.strip():
                tags[key] = (_text(value.get("name")) if isinstance(value, dict) else None) or key
    return tags


def _parse_architectures(body: Any) -> Dict[str, Dict[str, Optional[str]]]:
    architectures: Dict[str, Dict[str, Optional[str]]] = {}
    if isinstance(body, dict):
        for key, value in body.items():
            if isinstance(key, str) and key.strip() and isinstance(value, dict):
                architectures[key] = {"name": _text(value.get("name")) or key, "input": _text(value.get("input"))}
    return architectures


def _entry(model_id: str, raw: Mapping[str, Any], tags: Mapping[str, str], architectures: Mapping[str, Any]) -> Entry:
    name = _text(raw.get("name")) or model_id
    names = authors(raw)
    keys = _strings(raw.get("tags"))
    labels = [tags.get(key, key) for key in keys]
    architecture = _text(raw.get("architecture"))
    known = architectures.get(architecture) if architecture else None
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    words = [model_id, name, *names, description, *keys, *labels]
    if architecture:
        words += [architecture, (known or {}).get("name") or ""]
    return Entry(
        id=model_id,
        raw=raw,
        name_key=name.casefold(),
        date=date_of(raw) or "",
        authors=frozenset(author.casefold() for author in names),
        tags=frozenset(tag.casefold() for tag in keys + labels),
        architecture=architecture,
        scale=scale_of(raw),
        downloadable=any(file_url(resource) is not None for resource in resources(raw)),
        text="\n".join(words).casefold(),
    )


def build_catalog(
    models_body: Any, tags_body: Any = None, architectures_body: Any = None, fetched_at: float = 0.0
) -> Catalog:
    """The catalogue from the three raw answers (`tags_body` / `architectures_body` None when unavailable).

    Raises `SourceUnavailable` when `models.json` is not an object; models with an id this
    browser cannot use, or that are not objects, are left out (with a warning).
    """
    if not isinstance(models_body, dict):
        raise SourceUnavailable("OpenModelDB sent a catalogue this browser cannot read")
    tags = _parse_tags(tags_body)
    architectures = _parse_architectures(architectures_body)
    models: Dict[str, Mapping[str, Any]] = {}
    skipped = 0
    for model_id, raw in models_body.items():
        if is_model_id(model_id) and isinstance(raw, dict):
            models[model_id] = raw
        else:
            skipped += 1
    if skipped:
        logger.warning("[MODEL-BROWSER] OpenModelDB: left out %d catalogue entries this browser cannot read", skipped)

    by_sha256: Dict[str, Tuple[str, Mapping[str, Any]]] = {}
    for model_id, raw in models.items():
        for resource in resources(raw):
            sha256 = _sha256(resource.get("sha256"))
            if sha256 is None:
                continue
            known = by_sha256.get(sha256)
            # The first model listing a file wins, unless only a later one offers it as a file.
            if known is None or (file_url(known[1]) is None and file_url(resource) is not None):
                by_sha256[sha256] = (model_id, resource)

    entries = [_entry(model_id, raw, tags, architectures) for model_id, raw in models.items()]
    by_name = sorted(entries, key=lambda entry: (entry.name_key, entry.id))
    # Stable sorts: equal dates keep the name order; models without a date come last.
    newest = sorted(by_name, key=lambda entry: entry.date, reverse=True)
    orders = {
        "downloadable": tuple(sorted(newest, key=lambda entry: not entry.downloadable)),
        "newest": tuple(newest),
        "oldest": tuple(sorted(by_name, key=lambda entry: (entry.date == "", entry.date))),
        "name": tuple(by_name),
    }
    folded: Dict[str, str] = {}
    for model_id in models:
        folded.setdefault(model_id.casefold(), model_id)
    return Catalog(
        models=models,
        by_sha256=by_sha256,
        tags=tags,
        architectures=architectures,
        fetched_at=float(fetched_at),
        orders=orders,
        folded_ids=folded,
    )


# Description ----------------------------------------------------------------------

#: Rendered descriptions kept in memory (keyed by a hash of the text).
_RENDER_MEMO_SIZE = 64
_render_memo: "OrderedDict[str, str]" = OrderedDict()
_render_lock = threading.Lock()


def _paragraphs(text: str) -> str:
    """Escaped paragraphs: what a description becomes without markdown2."""
    return "".join(f"<p>{html.escape(part.strip())}</p>" for part in _PARAGRAPH_BREAK.split(text) if part.strip())


def _render(text: str) -> str:
    if len(text) > MAX_MARKDOWN_CHARS:
        return _paragraphs(text)
    try:
        import markdown2
    except ImportError:
        return _paragraphs(text)
    try:
        return str(markdown2.markdown(text, extras=dict(MARKDOWN_EXTRAS)))
    except Exception:  # noqa: BLE001 - a description must never break a model page
        logger.warning("[MODEL-BROWSER] OpenModelDB: could not convert a description; showing it as text", exc_info=True)
        return _paragraphs(text)


def render_markdown(text: str) -> str:
    """A description as HTML through markdown2 (escaped paragraphs without it, when it fails, or
    for a text over `MAX_MARKDOWN_CHARS`). Not sanitised: `description_html` does that."""
    key = hashlib.md5(text.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()
    with _render_lock:
        hit = _render_memo.get(key)
        if hit is not None:
            _render_memo.move_to_end(key)
            return hit
    markup = _render(text)
    with _render_lock:
        _render_memo[key] = markup
        while len(_render_memo) > _RENDER_MEMO_SIZE:
            _render_memo.popitem(last=False)
    return markup


def facts_line(raw: Mapping[str, Any], catalog: Catalog) -> Optional[str]:
    """"Architecture: ESRGAN · Scale: 4x · Input: image · Channels: 3 → 3 · Dataset: … · Training: …",
    with only the facts the model gives; None without any."""
    facts: List[str] = []
    architecture = _text(raw.get("architecture"))
    label = catalog.architecture_label(architecture)
    if label:
        facts.append(f"Architecture: {label}")
    scale = scale_of(raw)
    if scale:
        facts.append(f"Scale: {scale}x")
    kind = catalog.architecture_input(architecture)
    if kind:
        facts.append(f"Input: {kind}")
    channels_in, channels_out = _positive(raw.get("inputChannels")), _positive(raw.get("outputChannels"))
    if channels_in and channels_out:
        facts.append(f"Channels: {channels_in} → {channels_out}")
    dataset = _text(raw.get("dataset"))
    if dataset:
        facts.append(f"Dataset: {' '.join(dataset.split())}")
    iterations, epochs = _positive(raw.get("trainingIterations")), _positive(raw.get("trainingEpochs"))
    training = [f"{iterations:,} iterations" if iterations else "", f"{epochs:,} epochs" if epochs else ""]
    if any(training):
        facts.append("Training: " + ", ".join(part for part in training if part))
    return " · ".join(facts) or None


def compatibility_note(raw: Mapping[str, Any], catalog: Catalog, files: Sequence[File]) -> Optional[str]:
    """The note for a downloadable model PotionUI's built-in upscaler may not run (it loads
    ESRGAN `.pth` checkpoints only): an architecture other than ESRGAN / ESRGAN+, or a primary
    file that is not a `.pth`. None for a model without files, or one the upscaler loads."""
    if not files:
        return None
    architecture = _text(raw.get("architecture"))
    primary = next((file for file in files if file.primary), files[0])
    if (architecture or "").lower() in _LOADABLE_ARCHITECTURES and primary.name.lower().endswith(".pth"):
        return None
    label = catalog.architecture_label(architecture)
    return (
        "Note: PotionUI's built-in upscaler currently loads ESRGAN (.pth) models only; "
        f"this {label + ' ' if label else ''}model will download and index but may not run in PotionUI."
    )


def description_html(
    model_id: str,
    raw: Mapping[str, Any],
    catalog: Catalog,
    *,
    notes: bool = True,
    files: Optional[Sequence[File]] = None,
) -> Optional[str]:
    """The facts line and the description (markdown), sanitised; None when empty.

    With `notes`, two closing paragraphs when they apply: what only the OpenModelDB page
    offers ("Other downloads on the OpenModelDB page: Google Drive, ONNX", `other_downloads`),
    then the `compatibility_note`. `files`: the model's files, when the caller has them.
    """
    parts: List[str] = []
    facts = facts_line(raw, catalog)
    if facts:
        parts.append(f"<p>{html.escape(facts)}</p>")
    text = _text(raw.get("description"))
    if text:
        parts.append(render_markdown(text))
    if notes:
        others = other_downloads(raw)
        if others:
            page = html.escape(model_page_url(model_id), quote=True)
            parts.append(
                f'<p>Other downloads on the <a href="{page}">OpenModelDB page</a>: {html.escape(", ".join(others))}</p>'
            )
        note = compatibility_note(raw, catalog, model_files(model_id, raw) if files is None else files)
        if note:
            parts.append(f"<p>{html.escape(note)}</p>")
    return sanitize_html("".join(parts)) or None


# Normalisation --------------------------------------------------------------------


def base_model_of(raw: Mapping[str, Any], catalog: Catalog) -> Optional[str]:
    """"ESRGAN 4x": the architecture's label and the scale, either alone when the other is unknown."""
    label = catalog.architecture_label(_text(raw.get("architecture")))
    scale = scale_of(raw)
    return " ".join(part for part in (label, f"{scale}x" if scale else None) if part) or None


def tag_names(raw: Mapping[str, Any], catalog: Catalog) -> List[str]:
    return list(dict.fromkeys(catalog.tag_name(key) for key in _strings(raw.get("tags"))))


def normalize_item(model_id: str, raw: Mapping[str, Any], catalog: Catalog) -> SearchItem:
    """A catalogue entry as a search result."""
    files = model_files(model_id, raw)
    primary = next((file for file in files if file.primary), None)
    base_model = base_model_of(raw, catalog)
    return SearchItem(
        source=SOURCE_ID,
        id=model_id,
        name=_text(raw.get("name")) or model_id,
        type=catalog.architecture_label(_text(raw.get("architecture"))) or "Upscaler",
        mb_type=MB_TYPE if files else None,
        base_model=base_model,
        base_models=[base_model] if base_model else [],
        creator=", ".join(authors(raw)) or None,
        nsfw=False,
        poi=False,
        early_access=False,
        gated=False,
        thumbnail=thumbnail(raw),
        stats=Stats(),
        tags=tag_names(raw, catalog),
        updated_at=date_of(raw),
        source_url=model_page_url(model_id),
        primary_sha256=primary.sha256 if primary is not None else None,
    )


def normalize_detail(model_id: str, raw: Mapping[str, Any], catalog: Catalog) -> ModelDetail:
    """A catalogue entry as a model detail with one version, "Release"."""
    files = model_files(model_id, raw)
    version = Version(
        id=model_id,
        name=VERSION_NAME,
        base_model=base_model_of(raw, catalog),
        trigger_words=[],
        created_at=date_of(raw),
        early_access=False,
        nsfw=False,
        images=version_images(raw),
        files=files,
    )
    return ModelDetail(
        source=SOURCE_ID,
        id=model_id,
        name=_text(raw.get("name")) or model_id,
        type=catalog.architecture_label(_text(raw.get("architecture"))) or "Upscaler",
        mb_type=MB_TYPE if files else None,
        creator=", ".join(authors(raw)) or None,
        description_html=description_html(model_id, raw, catalog, files=files),
        tags=tag_names(raw, catalog),
        license=license_from(raw),
        source_url=model_page_url(model_id),
        nsfw=False,
        poi=False,
        gated=False,
        stats=Stats(),
        versions=[version],
    )


# Search box -----------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedQuery:
    """What the search box asks for."""

    #: "all" (no text), "text", "author", "tag" or "model" (a pasted link).
    kind: str = "all"
    value: str = ""
    #: Free text, casefolded and split.
    words: Tuple[str, ...] = ()


def parse_model_url(text: str) -> Optional[str]:
    """The model id of a pasted openmodeldb.info/models/<id> link, else None."""
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
    if host != "openmodeldb.info":
        return None
    segments = [unquote(segment) for segment in parts.path.split("/") if segment]
    if len(segments) < 2 or segments[0] != "models" or not is_model_id(segments[1]):
        return None
    return segments[1]


def parse_query(q: Optional[str]) -> ParsedQuery:
    """The search box text: a link, `@author`, `#tag` or free text."""
    text = (q or "").strip()
    if not text:
        return ParsedQuery()
    model_id = parse_model_url(text)
    if model_id is not None:
        return ParsedQuery(kind="model", value=model_id)
    if text.startswith("@"):
        author = " ".join(text[1:].split())
        return ParsedQuery(kind="author", value=author) if author else ParsedQuery()
    if text.startswith("#"):
        tag = " ".join(text[1:].split())
        return ParsedQuery(kind="tag", value=tag) if tag else ParsedQuery()
    return ParsedQuery(kind="text", value=text, words=tuple(text.casefold().split()))


def parse_cursor(cursor: Optional[str]) -> int:
    """The offset a cursor holds; 0 without one. `SourceInvalidRequest` for anything but digits."""
    if cursor is None or cursor == "":
        return 0
    if not _CURSOR.fullmatch(cursor):
        raise SourceInvalidRequest("Invalid OpenModelDB cursor")
    return int(cursor)


def _clean(values: Iterable[Any]) -> List[str]:
    return sorted({str(value).strip() for value in values or () if str(value).strip()})


def architecture_filter(types: Iterable[str], catalog: Catalog) -> Optional[FrozenSet[str]]:
    """The architecture keys `types` names (any case); None without a filter. An unknown key is `SourceInvalidRequest`."""
    chosen = _clean(types)
    if not chosen:
        return None
    known = {key.casefold(): key for key in catalog.architecture_keys()}
    keys = set()
    for value in chosen:
        key = known.get(value.casefold())
        if key is None:
            raise SourceInvalidRequest(
                f"Unknown OpenModelDB architecture {value[:40]!r}; use one of: {', '.join(sorted(known.values()))}"
            )
        keys.add(key)
    return frozenset(keys)


def scale_filter(base_models: Iterable[str]) -> Optional[FrozenSet[int]]:
    """The scales `base_models` names ("4", or "4x"); None without a filter."""
    chosen = _clean(base_models)
    if not chosen:
        return None
    scales = set()
    for value in chosen:
        match = _SCALE.fullmatch(value)
        if match is None or int(match.group(1)) <= 0:
            raise SourceInvalidRequest(f"Unknown OpenModelDB scale {value[:40]!r}; use a number such as 4")
        scales.add(int(match.group(1)))
    return frozenset(scales)


def matches(
    entry: Entry,
    parsed: ParsedQuery,
    architectures: Optional[FrozenSet[str]] = None,
    scales: Optional[FrozenSet[int]] = None,
) -> bool:
    """Whether a model passes the search box and the filters."""
    if architectures is not None and entry.architecture not in architectures:
        return False
    if scales is not None and entry.scale not in scales:
        return False
    if parsed.kind == "author":
        return parsed.value.casefold() in entry.authors
    if parsed.kind == "tag":
        return parsed.value.casefold() in entry.tags
    if parsed.kind == "text":
        return all(word in entry.text for word in parsed.words)
    return True


# The source -----------------------------------------------------------------------


def _again(error: SourceError) -> SourceError:
    """A new exception like `error` (same class, message and status): one is never raised twice."""
    if isinstance(error, SourceRateLimited):
        return SourceRateLimited(error.message, error.retry_after, error.status)
    return type(error)(error.message, error.status)


def _fresh(fetched_at: Any, now: float) -> bool:
    """`fetched_at` (epoch seconds) is less than `CATALOG_TTL_SECONDS` old, and not in the future."""
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)) or not math.isfinite(fetched_at):
        return False
    return 0 <= now - fetched_at < CATALOG_TTL_SECONDS


class OpenModelDBSource:
    """OpenModelDB behind the `Source` interface. `http_client` / `cache_store` default to the
    shared instances; `clock` gives epoch seconds (tests move it)."""

    id = SOURCE_ID
    label = LABEL

    def __init__(self, http_client: Any = None, cache_store: Any = None, clock: Callable[[], float] = time.time) -> None:
        self._http_client = http_client
        self._cache_store = cache_store
        self._clock = clock
        self._snapshot: Optional[Catalog] = None
        #: (when, error) of the last failed load, until a load succeeds.
        self._failure: Optional[Tuple[float, SourceError]] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

    def _client(self) -> Any:
        return self._http_client if self._http_client is not None else http_module.http

    def _store(self) -> Any:
        return self._cache_store if self._cache_store is not None else cache_module.cache

    @property
    def snapshot(self) -> Optional[Catalog]:
        """The catalogue in memory as it is (possibly stale); None before the first load."""
        return self._snapshot

    def _loop_lock(self) -> asyncio.Lock:
        """The load lock of the running event loop (an asyncio lock belongs to one loop)."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    # The catalogue ----------------------------------------------------------------

    async def catalog(self) -> Catalog:
        """The catalogue: the snapshot while it is fresh, else the cache rows or a new download.

        A failed refresh serves the previous snapshot (for `RETRY_SECONDS` before trying
        again); without one, the `SourceError` is raised (and raised again, without asking,
        for `FAILURE_HOLD_SECONDS`).
        """
        snapshot = self._snapshot
        if snapshot is not None and _fresh(snapshot.fetched_at, self._clock()):
            return snapshot
        async with self._loop_lock():
            snapshot = self._snapshot
            now = self._clock()
            if snapshot is not None and _fresh(snapshot.fetched_at, now):
                return snapshot
            if self._failure is not None:
                failed_at, error = self._failure
                waited = now - failed_at
                if snapshot is not None and 0 <= waited < RETRY_SECONDS:
                    return snapshot
                if snapshot is None and 0 <= waited < FAILURE_HOLD_SECONDS:
                    raise _again(error)
            try:
                loaded = await self._load(now)
            except SourceError as exc:
                # A copy: the raised one holds the frames of the request that failed.
                self._failure = (self._clock(), _again(exc))
                if snapshot is None:
                    raise
                logger.warning(
                    "[MODEL-BROWSER] OpenModelDB: could not refresh the catalogue (%s); "
                    "still using the one from %.1f h ago",
                    exc.message,
                    max(0.0, now - snapshot.fetched_at) / 3600,
                )
                return snapshot
            self._snapshot = loaded
            self._failure = None
            logger.info("[MODEL-BROWSER] OpenModelDB catalogue ready: %d models", len(loaded.models))
            return loaded

    async def _load(self, now: float) -> Catalog:
        models, tags, architectures = await asyncio.gather(
            self._read(MODELS_URL, now),
            self._read(TAGS_URL, now),
            self._read(ARCHITECTURES_URL, now),
            return_exceptions=True,
        )
        if isinstance(models, BaseException):
            raise models
        optional: List[Any] = []
        for name, result in (("tags.json", tags), ("architectures.json", architectures)):
            if isinstance(result, BaseException):
                if not isinstance(result, SourceError):
                    raise result
                logger.warning("[MODEL-BROWSER] OpenModelDB: no %s (%s); showing the keys as labels", name, result.message)
                optional.append(None)
            else:
                optional.append(result[0])
        body, fetched_at = models
        return await asyncio.to_thread(build_catalog, body, optional[0], optional[1], fetched_at)

    async def _read(self, url: str, now: float) -> Tuple[Any, float]:
        """(body, fetched_at) of one file: its cache row while fresh, else a download stored in the cache."""
        request = {"url": url, "params": []}
        cached = await asyncio.to_thread(self._cache_get, request)
        if isinstance(cached, dict) and "body" in cached and _fresh(cached.get("fetched_at"), now):
            return cached["body"], float(cached["fetched_at"])
        body = await self._client().get_json(SOURCE_ID, url)
        fetched_at = self._clock()
        await asyncio.to_thread(self._cache_set, request, {"body": body, "fetched_at": fetched_at})
        return body, fetched_at

    def _cache_get(self, request: Dict[str, Any]) -> Any:
        try:
            return self._store().get(SOURCE_ID, request, ttl_seconds=CATALOG_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - the cache is an optimisation
            logger.warning("[MODEL-BROWSER] Could not read the cache; asking OpenModelDB", exc_info=True)
            return None

    def _cache_set(self, request: Dict[str, Any], payload: Any) -> None:
        try:
            self._store().set(SOURCE_ID, request, payload, ttl_seconds=CATALOG_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("[MODEL-BROWSER] Could not write the cache", exc_info=True)

    async def find_sha256(self, sha256: str) -> Optional[Tuple[str, Mapping[str, Any], Mapping[str, Any], Catalog]]:
        """(model id, model, resource, catalogue) of the file with this SHA256 (any case); None when no model has it."""
        catalog = await self.catalog()
        found = catalog.by_sha256.get(str(sha256).strip().lower())
        if found is None:
            return None
        model_id, resource = found
        return model_id, catalog.models[model_id], resource, catalog

    # Source interface ------------------------------------------------------------

    async def info(self) -> SourceInfo:
        """Architectures and scales from the catalogue; empty lists when OpenModelDB is unreachable."""
        types: List[FilterOption] = []
        scales: List[FilterOption] = []
        try:
            catalog = await self.catalog()
        except SourceError as exc:
            logger.warning("[MODEL-BROWSER] OpenModelDB filter lists unavailable: %s", exc.message)
        else:
            types = [FilterOption(value=key, label=label) for key, label in catalog.architecture_options()]
            scales = [FilterOption(value=str(scale), label=f"{scale}x") for scale in catalog.scales()]
        return SourceInfo(
            id=SOURCE_ID,
            label=LABEL,
            enabled=True,
            types=types,
            base_models=scales,
            sorts=[FilterOption(value=key, label=label) for key, label in SORTS],
            periods=[],
            search_help=SEARCH_HELP,
            types_label="Architecture",
            base_models_label="Scale",
            base_model_label="Architecture",
        )

    async def search(self, query: SearchQuery, *, max_level: Optional[int] = None) -> SearchPage:
        """One page of the catalogue for `query`. `max_level` and `query.safe` change nothing:
        OpenModelDB has no NSFW content."""
        sort = query.sort or DEFAULT_SORT
        if sort not in _SORT_KEYS:
            raise SourceInvalidRequest(
                f"Unknown sort {str(sort)[:40]!r}; use one of: {', '.join(key for key, _ in SORTS)}"
            )
        offset = parse_cursor(query.cursor)
        parsed = parse_query(query.q)
        catalog = await self.catalog()
        if parsed.kind == "model":
            model_id = catalog.find(parsed.value)
            items = self._normalise([model_id], catalog) if model_id is not None and offset == 0 else []
            return SearchPage(source=SOURCE_ID, items=items, next_cursor=None)
        architectures = architecture_filter(query.types, catalog)
        scales = scale_filter(query.base_models)
        found = [entry.id for entry in catalog.orders[sort] if matches(entry, parsed, architectures, scales)]
        end = offset + query.limit
        return SearchPage(
            source=SOURCE_ID,
            items=self._normalise(found[offset:end], catalog),
            next_cursor=str(end) if end < len(found) else None,
        )

    async def detail(self, model_id: str, *, max_level: Optional[int] = None) -> ModelDetail:
        """One model of the catalogue (its id, or a pasted link); `SourceNotFound` when there is none."""
        text = str(model_id).strip()
        wanted = parse_model_url(text) or text
        if not is_model_id(wanted):
            raise SourceNotFound("OpenModelDB model ids look like 4x-UltraSharp")
        catalog = await self.catalog()
        found = catalog.find(wanted)
        if found is None:
            raise SourceNotFound(f"No OpenModelDB model {wanted!r}", 404)
        try:
            return await asyncio.to_thread(normalize_detail, found, catalog.models[found], catalog)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise SourceUnavailable(
                f"OpenModelDB sent a model this browser cannot read ({exc.__class__.__name__})"
            ) from None

    @staticmethod
    def _normalise(model_ids: Sequence[str], catalog: Catalog) -> List[SearchItem]:
        """Fresh items (the routes change them per user) for these ids; unreadable models are skipped."""
        items: List[SearchItem] = []
        for model_id in model_ids:
            try:
                items.append(normalize_item(model_id, catalog.models[model_id], catalog))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.warning(
                    "[MODEL-BROWSER] Skipping an OpenModelDB model this browser cannot read (%r): %s", model_id, exc
                )
        return items
