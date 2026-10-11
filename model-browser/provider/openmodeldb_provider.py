"""The `openmodeldb` marketplace provider (PLAN.md §8.4).

It answers `get_model_by_hash` from OpenModelDB's catalogue, so the core can enrich the
upscalers already on disk whoever downloaded them: Models page -> fetch info with the
`openmodeldb` provider (`run_provider_fetch`), or a recipe looking a checksum up
(`get_model_by_hash_any`). The catalogue is the one the `openmodeldb` source keeps
(`backend/sources/openmodeldb.py`): downloaded at most every 6 hours, shared with the Model
Browser page, its sha256 index answers without any other request. The plugin's own
downloads are still enriched by the `model-browser` provider, from what was recorded when
they were queued (`provider/pending_provider.py`).

For a known SHA256, `ProviderModelInfo` holds what `pending_provider.build_model_info`
fills: the name, the description (plain text: the facts line, then the description, at
most 4000 characters), the tag names, no trigger words, never NSFW, the download URL of
that file when the worker can fetch it as it is (never for an ONNX export, which PotionUI
cannot load), the version's previews (the model's own thumbnail, then the gallery's `SR` /
`url` images, dead hosts left out; https on a public host, at most 6), `model_type`
"upscaler", the base model ("ESRGAN 4x"), `provider_model_id` "openmodeldb:<id>" and
`extra_data` (licence, source page, architecture, scale, and the values of the plugin's
`mb_base_model` / `mb_license` attributes). An unknown hash answers
None; a catalogue that cannot be loaded raises `ProviderConnectionError`, so the core
retries and reports it rather than recording "not found".

`get_model_page_url("openmodeldb:<id>")` is the model's OpenModelDB page, for the
"Mirrors" section: string work only. No credentials: OpenModelDB's files are public, so
this provider claims no download URL and adds no header.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from src.plugin_api import (
    MarketplaceProviderBase,
    ProviderCapability,
    ProviderConnectionError,
    ProviderMetadata,
    ProviderModelInfo,
)

from .pending_provider import DESCRIPTION_LIMIT, preview_urls

# PotionUI's loader imports this module as `model_browser.provider.openmodeldb_provider`
# (through `hooks/provider_hooks.py`); the tests import it as the top-level
# `provider.openmodeldb_provider`. Never a bare `import backend` inside the app.
if __name__.count(".") >= 2:
    from ..backend import PLUGIN_VERSION, sources
    from ..backend.http import SourceError
    from ..backend.security import html_to_text
    from ..backend.sources import openmodeldb
else:
    from backend import PLUGIN_VERSION, sources
    from backend.http import SourceError
    from backend.security import html_to_text
    from backend.sources import openmodeldb

logger = logging.getLogger("plugins.model-browser")

PROVIDER_ID = "openmodeldb"
#: Previews handed to the core at most.
MAX_MEDIA_URLS = 6

_SHA256 = re.compile(r"[0-9a-f]{64}")


class OpenModelDBProvider(MarketplaceProviderBase):
    """Upscaler details from OpenModelDB's catalogue, by file hash.

    `source` is the `OpenModelDBSource` to read; the registry's one (shared with the page)
    when left out, as when the core creates the provider.
    """

    def __init__(self, source: Any = None) -> None:
        self._source = source

    def _catalog_source(self) -> Any:
        if self._source is not None:
            return self._source
        try:
            return sources.get_source(openmodeldb.SOURCE_ID)
        except sources.UnknownSource:
            raise ProviderConnectionError("The OpenModelDB source of the Model Browser is not available") from None

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id=PROVIDER_ID,
            name="OpenModelDB",
            description=(
                "Upscaler details from the OpenModelDB catalogue, matched by file hash: description, "
                "tags, previews, licence and a link to the model's page."
            ),
            website=openmodeldb.SITE,
            capabilities=[
                ProviderCapability.HASH_LOOKUP,
                ProviderCapability.MODEL_INFO,
                ProviderCapability.MEDIA_DOWNLOAD,
            ],
            version=PLUGIN_VERSION,
        )

    async def initialize(self, settings: Dict[str, Any]) -> bool:
        """Nothing to set up: no key, no session (the catalogue loads on first use). Always ready."""
        return True

    async def shutdown(self) -> None:
        return None

    async def test_connection(self) -> bool:
        """Whether the catalogue can be loaded (from memory, the cache or openmodeldb.info)."""
        try:
            await self._catalog_source().catalog()
        except Exception as exc:  # noqa: BLE001 - a test answers, it never raises
            logger.info("[MODEL-BROWSER] OpenModelDB connection test failed: %s", exc)
            return False
        return True

    def get_settings_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def get_download_headers(self) -> Dict[str, str]:
        return {}

    def matches_download_url(self, url: str) -> bool:
        # OpenModelDB's files are public: no download needs this provider.
        return False

    async def get_model_by_hash(self, sha256: str) -> Optional[ProviderModelInfo]:
        """The catalogue's model with a file of this SHA256; None when no model has one.

        Raises `ProviderConnectionError` when the catalogue cannot be loaded.
        """
        key = sha256.strip().lower() if isinstance(sha256, str) else ""
        if not _SHA256.fullmatch(key):
            return None
        try:
            found = await self._catalog_source().find_sha256(key)
        except SourceError as exc:
            logger.warning("[MODEL-BROWSER] OpenModelDB catalogue unavailable for a hash lookup: %s", exc.message)
            raise ProviderConnectionError(f"Could not load the OpenModelDB catalogue: {exc.message}") from exc
        if found is None:
            return None
        model_id, raw, resource, catalog = found
        try:
            return await asyncio.to_thread(build_model_info, model_id, raw, resource, catalog)
        except Exception:
            logger.exception("[MODEL-BROWSER] Could not build the OpenModelDB details of %s", model_id)
            return None

    def get_model_page_url(
        self, provider_model_id: Optional[str], provider_version_id: Optional[str] = None
    ) -> Optional[str]:
        return model_page_url(provider_model_id, provider_version_id)


def build_model_info(
    model_id: str, raw: Mapping[str, Any], resource: Mapping[str, Any], catalog: "openmodeldb.Catalog"
) -> ProviderModelInfo:
    """The `ProviderModelInfo` of the catalogue model `model_id`, for its file `resource`."""
    name = raw.get("name")
    license = openmodeldb.license_from(raw)
    license_id = None if license.summary == openmodeldb.NO_LICENSE else license.summary
    base_model = openmodeldb.base_model_of(raw, catalog)
    architecture = raw.get("architecture") if isinstance(raw.get("architecture"), str) else None
    # Without the closing notes (other downloads, compatibility): the file is already on disk.
    description = openmodeldb.description_html(model_id, raw, catalog, notes=False)
    images = openmodeldb.version_images(raw)
    return ProviderModelInfo(
        provider_id=PROVIDER_ID,
        provider_model_id=f"{PROVIDER_ID}:{model_id}",
        provider_version_id=None,
        name=name.strip() if isinstance(name, str) and name.strip() else model_id,
        description=html_to_text(description, limit=DESCRIPTION_LIMIT) or None,
        tags=openmodeldb.tag_names(raw, catalog),
        trigger_words=[],
        nsfw=False,
        download_url=openmodeldb.file_url(resource),
        # Every OpenModelDB image is level 1: the admin's level never leaves one out.
        media_urls=preview_urls(images, max_level=openmodeldb.IMAGE_LEVEL, hide_poi=False)[:MAX_MEDIA_URLS],
        model_type=openmodeldb.MB_TYPE,
        base_model=base_model,
        created_at=_date(openmodeldb.date_of(raw)),
        extra_data={
            "source": openmodeldb.SOURCE_ID,
            "source_url": openmodeldb.model_page_url(model_id),
            "license": license_id,
            "license_url": license.url,
            "architecture": catalog.architecture_label(architecture.strip() if architecture else None),
            "scale": openmodeldb.scale_of(raw),
            # The values of the plugin's model attributes (manifest `model_metadata_fields`).
            "mb_base_model": base_model,
            "mb_license": license_id,
        },
    )


def model_page_url(provider_model_id: Any, provider_version_id: Any = None) -> Optional[str]:
    """`https://openmodeldb.info/models/<id>` for `"openmodeldb:<id>"`; None for anything else. Never raises."""
    if not isinstance(provider_model_id, str):
        return None
    source, separator, model_id = provider_model_id.partition(":")
    if not separator or source != PROVIDER_ID or not openmodeldb.is_model_id(model_id):
        return None
    return openmodeldb.model_page_url(model_id)


def _date(value: Optional[str]) -> Optional[datetime]:
    """A catalogue date ("2023-05-10") as midnight UTC; None when there is none."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
