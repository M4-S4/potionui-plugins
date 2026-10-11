"""The `model-browser` marketplace provider (PLAN.md §7.3, §7.4 step 7).

It answers `get_model_by_hash` only for the files this plugin downloaded: the
`model_browser_pending` row of that SHA256 (`backend/pending.py`) holds the normalised
detail of the model cut down to the chosen version and file, which `build_model_info`
turns into a `ProviderModelInfo`. Any other hash, a failed download and an unreadable
row answer None, so the core records "not found" and moves on.

The core's `ProviderInfoFetcher.run_provider_fetch("model-browser", ...)` then stores the
provider row (name, description, tags, nsfw, download URL), fills the model's description
and trigger words when they are empty, and downloads `media_urls` as its previews when it
has none. Those previews are shown to everyone the model is assigned to, so `media_urls`
never holds an NSFW image: an image is left out when the source normalisation flagged it,
when its level is above the admin's current `nsfw_max_level` (PLAN.md §5.2), or, with
`hide_poi`, when it depicts a real person. The core fetches those URLs from the server, so
only https URLs on a named public host are kept.

`get_model_page_url` backs the "Mirrors" section of a model's admin page: a string built
from `"<source>:<id>"`, with no database read and no network call.

No credentials: downloads are authenticated by the `civitai` / `huggingface` providers
through the queue's `provider_id`, so this provider claims no download URL and adds no
header.
"""

import ipaddress
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypeVar
from urllib.parse import urlsplit

from pydantic import ValidationError

from src.plugin_api import (
    MarketplaceProviderBase,
    ProviderCapability,
    ProviderConnectionError,
    ProviderMetadata,
    ProviderModelInfo,
)

# PotionUI's loader imports this module as `model_browser.provider.pending_provider`
# (through `hooks/provider_hooks.py`); the tests import it as the top-level
# `provider.pending_provider`. Never a bare `import backend` inside the app.
if __name__.count(".") >= 2:
    from ..backend import PLUGIN_VERSION, pending
    from ..backend import settings as plugin_settings
    from ..backend.schema import Image, ModelDetail
    from ..backend.security import html_to_text
    from ..backend.sources import openmodeldb
else:
    from backend import PLUGIN_VERSION, pending
    from backend import settings as plugin_settings
    from backend.schema import Image, ModelDetail
    from backend.security import html_to_text
    from backend.sources import openmodeldb

logger = logging.getLogger("plugins.model-browser")

PROVIDER_ID = "model-browser"
#: Longest plain-text description handed to the core, ellipsis included.
DESCRIPTION_LIMIT = 4000

_SHA256 = re.compile(r"[0-9a-f]{64}")
_CIVITAI_ID = re.compile(r"[0-9]{1,18}")
# A Hugging Face repo id, as `backend/sources/huggingface.py::is_repo_id` accepts it.
_HF_NAME = r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]{0,94}[A-Za-z0-9_])?"
_HF_REPO_ID = re.compile(rf"(?:{_HF_NAME}/)?{_HF_NAME}")

_T = TypeVar("_T")


class PendingProvider(MarketplaceProviderBase):
    """Metadata for the models the plugin downloaded, read from its `model_browser_pending` table."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id=PROVIDER_ID,
            name="Model Browser",
            description=(
                "Details of the models downloaded with the Model Browser: description, tags, "
                "trigger words, safe previews and a link to the source page."
            ),
            website="https://github.com/PotionUI/PotionUI",
            capabilities=[
                ProviderCapability.HASH_LOOKUP,
                ProviderCapability.MODEL_INFO,
                ProviderCapability.MEDIA_DOWNLOAD,
            ],
            version=PLUGIN_VERSION,
        )

    async def initialize(self, settings: Dict[str, Any]) -> bool:
        """Nothing to set up: no key, no session. Always ready."""
        return True

    async def shutdown(self) -> None:
        return None

    async def test_connection(self) -> bool:
        return True

    def get_settings_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def get_download_headers(self) -> Dict[str, str]:
        return {}

    def matches_download_url(self, url: str) -> bool:
        # The queue's `provider_id` (civitai / huggingface) authenticates the plugin's downloads.
        return False

    async def get_model_by_hash(self, sha256: str) -> Optional[ProviderModelInfo]:
        """What the plugin recorded for this file when it queued it; None for any other file.

        A database failure raises `ProviderConnectionError`, so the core retries and reports
        it instead of recording "not found".
        """
        key = sha256.strip().lower() if isinstance(sha256, str) else ""
        if not _SHA256.fullmatch(key):
            return None
        try:
            row = pending.get(key)
        except Exception as exc:
            logger.warning("[MODEL-BROWSER] Could not read the pending row of %s: %s", key[:12], exc)
            raise ProviderConnectionError(f"Could not read the model-browser downloads table: {exc}") from exc
        if row is None or row.status == "failed":
            return None
        max_level, hide_poi = preview_policy()
        try:
            return build_model_info(row, max_level=max_level, hide_poi=hide_poi)
        except Exception:
            logger.exception("[MODEL-BROWSER] Could not build the provider info of %s", key[:12])
            return None

    def get_model_page_url(
        self, provider_model_id: Optional[str], provider_version_id: Optional[str] = None
    ) -> Optional[str]:
        return model_page_url(provider_model_id, provider_version_id)


def build_model_info(
    row: pending.PendingRow,
    *,
    max_level: int = plugin_settings.DEFAULTS["nsfw_max_level"],
    hide_poi: bool = plugin_settings.DEFAULTS["hide_poi"],
) -> Optional[ProviderModelInfo]:
    """The `ProviderModelInfo` of one pending row; None when its `info` has no valid `model`.

    `info` is `{"model": ModelDetail as JSON, "version_id", "file_id", "mb_type"}`, the model's
    `versions` holding the chosen version and its `files` the chosen file. The version and the
    file are picked by id, falling back to the first one. A model without a version still
    gives its model-level fields. `max_level` and `hide_poi` are the admin's settings that
    decide which previews may be shown to everyone (`preview_policy()`).
    """
    info = row.info if isinstance(row.info, dict) else {}
    raw_model = info.get("model")
    if not isinstance(raw_model, dict):
        logger.warning("[MODEL-BROWSER] Pending row %s has no model details", row.sha256[:12])
        return None
    try:
        model = ModelDetail.model_validate(raw_model)
    except ValidationError as exc:
        logger.warning(
            "[MODEL-BROWSER] Pending row %s has unreadable model details (%d errors)",
            row.sha256[:12],
            exc.error_count(),
        )
        return None

    version = _pick(model.versions, info.get("version_id"))
    file = _pick(version.files, info.get("file_id")) if version is not None else None
    source = row.source or model.source
    mb_type = info.get("mb_type")
    license_summary = (model.license.summary or None) if model.license is not None else None
    license_url = (model.license.url or None) if model.license is not None else None
    base_model = version.base_model if version is not None else None

    return ProviderModelInfo(
        provider_id=PROVIDER_ID,
        provider_model_id=f"{source}:{model.id}",
        provider_version_id=version.id if version is not None else None,
        name=model.name,
        description=html_to_text(model.description_html, limit=DESCRIPTION_LIMIT) or None,
        tags=list(model.tags),
        trigger_words=list(version.trigger_words) if version is not None else [],
        nsfw=model.nsfw or (version is not None and version.nsfw),
        download_url=file.download_url if file is not None else None,
        media_urls=preview_urls(version.images, max_level=max_level, hide_poi=hide_poi) if version is not None else [],
        model_type=mb_type if isinstance(mb_type, str) and mb_type else model.mb_type,
        base_model=base_model,
        created_at=_parse_datetime(version.created_at) if version is not None else None,
        extra_data={
            "source": source,
            "source_url": model.source_url,
            "license": license_summary,
            "license_url": license_url,
            # The values of the plugin's model attributes (manifest `model_metadata_fields`).
            "mb_base_model": base_model,
            "mb_license": license_summary,
        },
    )


def preview_urls(images: Sequence[Image], *, max_level: int, hide_poi: bool) -> List[str]:
    """The urls of the images anyone may see as previews, in order, without duplicates.

    Left out: an image the source normalisation marked NSFW, one whose level is above
    `max_level` (the admin may have made it stricter since the download), one depicting a
    real person when `hide_poi` is on, one without a url, and any url that is not https on a
    named public host (the core fetches these from the server).
    """
    urls: List[str] = []
    for image in images:
        if image.nsfw or not image.url:
            continue
        if image.nsfw_level is not None and image.nsfw_level > max_level:
            continue
        if hide_poi and image.poi:
            continue
        if image.url in urls or not _is_public_https_url(image.url):
            continue
        urls.append(image.url)
    return urls


def preview_policy() -> Tuple[int, bool]:
    """The admin's current `nsfw_max_level` and `hide_poi`; their defaults when they cannot be read."""
    try:
        return int(plugin_settings.get_setting("nsfw_max_level")), bool(plugin_settings.get_setting("hide_poi"))
    except Exception as exc:
        logger.debug("[MODEL-BROWSER] Plugin settings unreadable, using the defaults: %s", exc)
        return int(plugin_settings.DEFAULTS["nsfw_max_level"]), bool(plugin_settings.DEFAULTS["hide_poi"])


def model_page_url(provider_model_id: Any, provider_version_id: Any = None) -> Optional[str]:
    """The source's web page for `"<source>:<id>"`, or None for an unknown source or a malformed id.

    CivitAI: `https://civitai.com/models/{id}`, with `?modelVersionId={version}` when a
    numeric version is given. Hugging Face: `https://huggingface.co/{repo id}`. OpenModelDB:
    `https://openmodeldb.info/models/{id}`. Never raises.
    """
    if not isinstance(provider_model_id, str):
        return None
    source, separator, model_id = provider_model_id.partition(":")
    if not separator:
        return None
    if source == "civitai":
        if not _CIVITAI_ID.fullmatch(model_id):
            return None
        url = f"https://civitai.com/models/{model_id}"
        version = _id_text(provider_version_id)
        if version is not None and _CIVITAI_ID.fullmatch(version):
            url += f"?modelVersionId={version}"
        return url
    if source == "huggingface":
        if ".." in model_id or not _HF_REPO_ID.fullmatch(model_id):
            return None
        return f"https://huggingface.co/{model_id}"
    if source == openmodeldb.SOURCE_ID:
        return openmodeldb.model_page_url(model_id) if openmodeldb.is_model_id(model_id) else None
    return None


def _pick(items: Sequence[_T], wanted: Any) -> Optional[_T]:
    """The item whose `id` is `wanted`, else the first one; None for an empty list."""
    if wanted is not None:
        for item in items:
            if item.id == str(wanted):
                return item
    return items[0] if items else None


def _id_text(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """An ISO 8601 date (`Z` accepted) as an aware datetime, UTC when it has no offset; None otherwise."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _is_public_https_url(url: str) -> bool:
    """https on the default port, no credentials, and a host that is a public name (no IP, no local name)."""
    if any(ord(char) <= 0x20 or ord(char) == 0x7F or char == "\\" for char in url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or port not in (None, 443) or "@" in parts.netloc:
        return False
    if not host or host.endswith(".") or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not host.rsplit(".", 1)[-1].isdigit()
