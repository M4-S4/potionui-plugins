import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

import src.features.providers.registry as provider_registry
from src.features.models.provider_info import ProviderInfoFetcher
from src.plugin_api import HookContext

PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "content" / "plugins" / "marketplace" / "model-browser"
PACKAGE = "model_browser"
OPENMODELDB_FIXTURES = PLUGIN_ROOT / "tests" / "fixtures" / "openmodeldb"

SHA = "0d9bd1b873a7863e128b4672e3e245838858f71469a3cec58123c16c06f83bd7"
DOWNLOAD_URL = "https://civitai.com/api/download/models/135867?fileId=99264"
SAFE_IMAGE = "https://image.civitai.com/xG1/safe-1/original=true/"
SAFE_VIDEO = "https://image.civitai.com/xG1/safe-2/original=true/"
NSFW_IMAGE = "https://image.civitai.com/xG1/nsfw-1/original=true/"
NOMOS_URL = "https://github.com/Phhofm/models/raw/main/4xNomos8kSC/4xNomos8kSC.pth"
NOMOS_IMAGES = ["https://openmodeldb.info/thumbs/79385d8f832b948a9ce1d339.jpg"]


@pytest.fixture(autouse=True)
def plugin_modules_removed_afterwards():
    modules, path = set(sys.modules), list(sys.path)
    try:
        yield
    finally:
        for name in set(sys.modules) - modules:
            if name.split(".")[0] == PACKAGE:
                del sys.modules[name]
        sys.path[:] = path


def _load(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


@pytest.fixture(autouse=True)
def default_settings(plugin_modules_removed_afterwards, monkeypatch):
    settings = _load("backend.settings")
    values = dict(settings.DEFAULTS)
    monkeypatch.setattr(settings, "get_setting", lambda key: values[key])
    return values


class _Editor:
    def __init__(self):
        self.metadata, self.previews = {}, []

    def notify_metadata_changed(self, model_id, fields):
        pass

    def update_model_metadata(self, model_id, values):
        self.metadata = values

    def list_model_previews(self, model_id):
        return list(self.previews)

    def add_model_preview(self, model_id, preview):
        self.previews.append(preview)


def _fetcher(monkeypatch, provider, provider_id, on_disk, stored, fetched, media):
    async def get_model_by_hash(asked_provider_id, sha256, raise_errors=False):
        assert asked_provider_id == provider_id
        return await provider.get_model_by_hash(sha256)

    async def fetch_media_bytes(self, url):
        fetched.append(url)
        return media

    repository = SimpleNamespace(
        get_by_id=lambda model_id, include_providers=False: on_disk if model_id == on_disk.id else None,
        upsert_provider=lambda model_id, row: stored.__setitem__("provider", row),
        update_description=lambda model_id, text: stored.__setitem__("description", text),
    )
    plugins = SimpleNamespace(
        execute_hook=lambda hook, initial_data=None: (HookContext(hook_name=hook, plugin_id="system", data=initial_data or {}), True)
    )
    monkeypatch.setattr(provider_registry, "get_provider_registry", lambda: SimpleNamespace(get_model_by_hash=get_model_by_hash))
    monkeypatch.setattr(ProviderInfoFetcher, "_fetch_media_bytes", fetch_media_bytes)
    editor = _Editor()
    fetcher = ProviderInfoFetcher(repository, plugins, metadata_editor=editor, storage_driver=SimpleNamespace(put_bytes=lambda key, data: None))
    return fetcher, editor


class _NoCache:
    def get(self, source, request, *, ttl_seconds=None):
        return None

    def set(self, source, request, payload, *, ttl_seconds=None):
        pass


async def _openmodeldb_site(url, params):
    fixture = OPENMODELDB_FIXTURES / urlsplit(url).path.rsplit("/", 1)[-1]
    if not fixture.is_file():
        return 404, {"Content-Type": "text/html"}, b"<!doctype html><title>Not found</title>"
    return 200, {"Content-Type": "application/json", "Cache-Control": "max-age=600"}, fixture.read_bytes()


async def test_the_core_fetcher_enriches_an_upscaler_already_on_disk(monkeypatch):
    openmodeldb_provider = _load("provider.openmodeldb_provider")
    source = _load("backend.sources.openmodeldb").OpenModelDBSource(
        http_client=_load("backend.http").SourceHttp(fetch=_openmodeldb_site, limits={"openmodeldb": (0.0, 2)}),
        cache_store=_NoCache(),
    )
    provider = openmodeldb_provider.OpenModelDBProvider(source=source)
    nomos_sha = json.loads((OPENMODELDB_FIXTURES / "models.json").read_text(encoding="utf-8"))["4x-Nomos8kSC"]["resources"][0]["sha256"]
    stored, fetched = {}, []
    on_disk = SimpleNamespace(id="model-7", sha256=nomos_sha, description=None, model_metadata={}, is_directory=False)
    fetcher, editor = _fetcher(
        monkeypatch, provider, openmodeldb_provider.PROVIDER_ID, on_disk, stored, fetched, (b"\xff\xd8\xff\xe0", "image/jpeg")
    )

    assert await fetcher.run_provider_fetch(openmodeldb_provider.PROVIDER_ID, ["model-7"]) == {"successful": 1, "failed": 0}

    row = stored["provider"]
    assert (row.model_id, row.provider, row.provider_model_id, row.provider_version_id) == (
        "model-7", "openmodeldb", "openmodeldb:4x-Nomos8kSC", None,
    )
    assert (row.name, row.nsfw, row.download_url) == ("Nomos8kSC", False, NOMOS_URL)
    assert stored["description"].startswith("Architecture: ESRGAN · Scale: 4x")
    assert editor.metadata == {}
    assert fetched == NOMOS_IMAGES
    assert [preview["type"] for preview in editor.previews] == ["image"]


def _lora(schema):
    version = schema.Version(
        id="135867",
        name="v1.0",
        base_model="SDXL 1.0",
        trigger_words=["add detail", "detailed"],
        created_at="2023-08-07T14:55:02.627Z",
        images=[
            schema.Image(url=SAFE_IMAGE, nsfw=False, nsfw_level=1, width=832, height=1216, id="11"),
            schema.Image(url=NSFW_IMAGE, nsfw=True, nsfw_level=8, id="12"),
            schema.Image(url=None, blurhash="UBF$:LxuIUIo", nsfw=True, nsfw_level=16, id="13"),
            schema.Image(url=SAFE_VIDEO, nsfw=False, nsfw_level=2, kind="video", id="14"),
        ],
        files=[
            schema.File(
                id="99264",
                name="add-detail-xl.safetensors",
                size_bytes=228_455_604,
                sha256=SHA.upper(),
                format="SafeTensor",
                primary=True,
                download_url=DOWNLOAD_URL,
                auth_provider_id="civitai",
            )
        ],
    )
    return schema.ModelDetail(
        source="civitai",
        id="122359",
        name="Detail Tweaker XL",
        type="LORA",
        mb_type="lora",
        creator="nocrypt",
        description_html="<p>Adds <strong>detail</strong>.</p><p>Weight&nbsp;0.5 to 1.5</p>",
        tags=["concept", "detailed"],
        license=schema.License(summary="Commercial use allowed, credit required", commercial_use=["Image", "Sell"]),
        source_url="https://civitai.red/models/122359",
        nsfw=False,
        versions=[version],
    )


async def test_the_core_fetcher_stores_the_answer_and_fetches_only_the_safe_previews(mock_db, monkeypatch):
    pending_provider = _load("provider.pending_provider")
    pending = _load("backend.pending")
    _load("backend.tables").create_tables()
    pending.insert(
        pending.PendingRow(
            sha256=SHA,
            source="civitai",
            source_model_id="122359",
            source_version_id="135867",
            file_name="add-detail-xl.safetensors",
            requested_by="user-1",
            assign_to="user:user-1",
            info={
                "model": _lora(_load("backend.schema")).model_dump(mode="json"),
                "version_id": "135867",
                "file_id": "99264",
                "mb_type": "lora",
            },
            status="assigned",
            model_id="model-1",
        )
    )
    stored, fetched = {}, []
    model = SimpleNamespace(id="model-1", sha256=SHA, description=None, model_metadata={}, is_directory=False)
    fetcher, editor = _fetcher(
        monkeypatch,
        pending_provider.PendingProvider(),
        pending_provider.PROVIDER_ID,
        model,
        stored,
        fetched,
        (b"\x89PNG\r\n\x1a\n", "image/png"),
    )

    assert await fetcher.run_provider_fetch(pending_provider.PROVIDER_ID, ["model-1"]) == {"successful": 1, "failed": 0}

    row = stored["provider"]
    assert (row.model_id, row.provider, row.provider_model_id, row.provider_version_id) == (
        "model-1", "model-browser", "civitai:122359", "135867",
    )
    assert (row.name, row.tags, row.nsfw, row.download_url) == ("Detail Tweaker XL", ["concept", "detailed"], False, DOWNLOAD_URL)
    assert stored["description"] == "Adds detail. Weight 0.5 to 1.5"
    assert editor.metadata == {"triggers": ["add detail", "detailed"]}
    assert fetched == [SAFE_IMAGE, SAFE_VIDEO]
    assert [preview["type"] for preview in editor.previews] == ["image", "image"]
