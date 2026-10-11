"""manifest.yml, read and loaded by PotionUI's own `PluginLoader`, the way the app does it.

Catches what would otherwise only show up as a plugin in the ERROR state in
Admin -> Plugins: a manifest key the schema rejects, a handler path that does
not resolve, or a relative import that only works in the test layout. The
`provider.register` handler, the `setup:` checks and the `model_metadata_fields`
also go through the core code that consumes them (provider registry, setup
report, attribute definitions), with fakes for the core's other services.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import PLUGIN_ID, PLUGIN_VERSION

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

#: Module each backend hook handler must load as inside the app.
HANDLER_MODULES = {
    "plugin.lifecycle.boot": "model_browser.hooks.lifecycle_hooks",
    "plugin.lifecycle.ready": "model_browser.hooks.lifecycle_hooks",
    "plugin.lifecycle.disable": "model_browser.hooks.lifecycle_hooks",
    "provider.register": "model_browser.hooks.provider_hooks",
}
#: `setup:` check references, in order, and the provider each one waits for.
SETUP_CHECKS = {
    "backend.setup_checks:CivitaiProviderReady": "civitai",
    "backend.setup_checks:HuggingFaceProviderReady": "huggingface",
}


@pytest.fixture
def loader(monkeypatch, tmp_path):
    from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader

    monkeypatch.delenv(EXTRA_PLUGIN_DIRS_ENV, raising=False)
    return PluginLoader(marketplace_dir=str(tmp_path / "marketplace"), local_dir=str(PLUGIN_ROOT.parent))


@pytest.fixture
def manifest(loader):
    found = [m for m in loader.discover_plugins() if Path(m.plugin_dir).resolve() == PLUGIN_ROOT]
    assert len(found) == 1, f"PluginLoader did not discover {PLUGIN_ROOT}"
    assert found[0].validation_error is None, found[0].validation_error
    return found[0]


def test_manifest_identity_matches_the_backend(manifest):
    assert (manifest.id, manifest.version) == (PLUGIN_ID, PLUGIN_VERSION)


def _handler(loader, manifest, hook):
    handler = loader.load_hook_handler(manifest, manifest.hooks[hook])
    assert callable(handler), f"{hook}: {manifest.hooks[hook]} did not load (see the log above)"
    return handler


def test_every_backend_hook_handler_loads_inside_the_plugin_package(loader, manifest):
    assert set(manifest.hooks) == set(HANDLER_MODULES)
    for hook, handler_path in manifest.hooks.items():
        handler = loader.load_hook_handler(manifest, handler_path)

        assert callable(handler), f"{hook}: {handler_path} did not load (see the log above)"
        assert handler.__module__ == HANDLER_MODULES[hook]

    # The handlers reach the backend through the plugin's package, never a top-level `backend`.
    lifecycle = sys.modules["model_browser.hooks.lifecycle_hooks"]
    assert lifecycle.tables.__name__ == "model_browser.backend.tables"


def test_api_module_loads_and_exposes_the_router(loader, manifest):
    module_path = manifest.api_routes["module"].replace(".py", "").replace("/", ".")

    api = loader.load_plugin_module(manifest, module_path)

    assert api is not None, f"{manifest.api_routes['module']} did not load (see the log above)"
    assert api.router.prefix == f"/api/plugins/{PLUGIN_ID}"


def test_sidebar_entry_opens_the_page_for_every_user(manifest):
    assert [item["route"] for item in manifest.sidebar_items] == [page["route"] for page in manifest.pages]
    assert all(item.get("require_role") is None for item in manifest.sidebar_items)


def test_docs_files_exist(manifest):
    for doc in manifest.docs:
        assert (PLUGIN_ROOT / doc["path"]).is_file(), doc["path"]


# provider.register --------------------------------------------------------------


def test_provider_register_adds_the_model_browser_provider_next_to_the_others(loader, manifest):
    from src.plugin_api import HookContext, MarketplaceProviderBase

    register = _handler(loader, manifest, "provider.register")
    other = type("CivitaiProvider", (), {})
    context = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={"providers": {"civitai": other}})

    result = register(context)

    assert result is context
    providers = result.data["providers"]
    assert providers["civitai"] is other
    provider_class = providers["model-browser"]
    assert issubclass(provider_class, MarketplaceProviderBase)
    assert provider_class.__module__ == "model_browser.provider.pending_provider"
    assert provider_class().get_metadata().id == "model-browser"
    # The provider reaches the backend through the plugin's package, never a top-level `backend`.
    provider_module = sys.modules["model_browser.provider.pending_provider"]
    assert provider_module.pending.__name__ == "model_browser.backend.pending"


def test_provider_register_creates_the_providers_map_and_never_raises(loader, manifest):
    from src.plugin_api import HookContext

    register = _handler(loader, manifest, "provider.register")
    empty = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={})
    broken = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={"providers": "not a map"})

    assert register(empty).data["providers"]["model-browser"].__name__ == "PendingProvider"
    assert register(broken) is broken
    assert broken.data["providers"] == "not a map"


async def test_the_core_provider_registry_discovers_and_initializes_the_provider(
    loader, manifest, plugin_db, monkeypatch
):
    from backend.tables import create_tables
    from src.features.providers.registry import ProviderRegistry
    from src.platform.plugins.hooks import HookChain
    from src.plugin_api import ProviderCapability

    chain = HookChain()
    chain.register("provider.register", PLUGIN_ID, _handler(loader, manifest, "provider.register"))

    class Plugins:
        """The part of PluginRegistry that ProviderRegistry.discover_providers uses."""

        def get_enabled_plugins(self):
            return []

        def get_plugins_for_hook(self, hook):
            return [PLUGIN_ID]

        def execute_hook(self, hook, context=None, initial_data=None):
            final, results = chain.execute(hook, context=context, initial_data=initial_data)
            return final, all(result.success for result in results)

    registry = ProviderRegistry(registry=Plugins())
    # Settings would be read from the `model-browser-provider` plugin, which does not exist.
    monkeypatch.setattr(registry, "_get_provider_settings", lambda provider_id: {})

    assert [metadata.id for metadata in await registry.discover_providers()] == ["model-browser"]
    assert await registry.initialize_providers() == {"model-browser": True}
    assert registry.is_provider_initialized("model-browser")
    provider = registry.get_provider("model-browser")
    assert registry.get_providers_with_capability(ProviderCapability.HASH_LOOKUP) == [provider]
    # What the model page's "Mirrors" section and run_provider_fetch call.
    assert provider.provider_name == "Model Browser"
    assert provider.get_model_page_url("civitai:122359", "135867") == (
        "https://civitai.com/models/122359?modelVersionId=135867"
    )
    create_tables()
    assert await registry.get_model_by_hash("model-browser", "0" * 64, raise_errors=True) is None


# setup: ---------------------------------------------------------------------------


def test_setup_checks_load_the_way_the_core_loads_them(loader, manifest):
    from src.plugin_api import SetupCheck

    assert [(step["kind"], step["check"]) for step in manifest.setup] == [("check", ref) for ref in SETUP_CHECKS]
    for step in manifest.setup:
        check_class = loader.load_class(manifest, step["check"])

        assert check_class is not None, f"{step['check']} did not load (see the log above)"
        assert issubclass(check_class, SetupCheck)
        assert check_class.__module__ == "model_browser.backend.setup_checks"
        assert check_class.provider_id == SETUP_CHECKS[step["check"]]
        assert step["label"]


def test_the_core_setup_report_runs_the_checks(loader, manifest, monkeypatch):
    import src.plugin_api
    from src.features.plugins.setup import PluginSetup

    registry = SimpleNamespace(is_provider_initialized=lambda provider_id: provider_id == "civitai")
    monkeypatch.setattr(src.plugin_api, "get_provider_registry", lambda: registry)
    setup = PluginSetup(
        plugin_registry=SimpleNamespace(loader=loader, get_enabled_plugins=lambda: [manifest]),
        plugin_repository=SimpleNamespace(get_plugin_settings=lambda plugin_id: []),
        backend_registry=SimpleNamespace(get_registered_config_types=lambda: {}),
        catalog_repository=None,
        preset_loader=None,
        preset_db_repo=None,
        group_repo=None,
    )

    report = setup.report(manifest)

    assert (report.plugin_id, report.complete, report.remaining) == (PLUGIN_ID, False, 1)
    civitai, huggingface = report.steps
    assert (civitai.kind, civitai.status, civitai.action) == ("check", "done", None)
    assert civitai.label == manifest.setup[0]["label"]
    assert (huggingface.kind, huggingface.status) == ("check", "todo")
    assert huggingface.label == manifest.setup[1]["label"]
    assert "(token)" in huggingface.description
    assert (huggingface.action.kind, huggingface.action.label, huggingface.action.href) == (
        "link", "Open the Hugging Face provider", "/admin?tab=plugins&id=huggingface-provider",
    )
    assert report.guide.title == "Model Browser"


# model_metadata_fields --------------------------------------------------------------


def test_model_metadata_fields_are_text_attributes_for_every_model_type(manifest):
    from src.features.models.attributes.editor import FIELD_TYPES, KEY_PATTERN, ModelAttributeDefinitionsEditor

    fields = manifest.model_metadata_fields
    assert [field["key"] for field in fields] == ["mb_base_model", "mb_license"]
    for field in fields:
        assert field["field_type"] == "text" and field["field_type"] in FIELD_TYPES
        assert KEY_PATTERN.match(field["key"])
        assert field["label"] and field["description"]
        assert (field["model_types"], field["per_user"], field["admin_only"]) == ([], False, False)

    created = []
    definitions = SimpleNamespace(get_by_key=lambda key: None, create=created.append, update=created.append)
    editor = ModelAttributeDefinitionsEditor(definitions, None)

    assert editor.upsert_from_plugin(PLUGIN_ID, fields) is None
    assert [(d.key, d.label, d.field_type, d.source, d.system) for d in created] == [
        ("mb_base_model", "Base model", "text", PLUGIN_ID, False),
        ("mb_license", "License", "text", PLUGIN_ID, False),
    ]


def test_the_provider_gives_a_value_for_every_model_metadata_field(manifest):
    from backend.pending import PendingRow
    from backend.schema import File, License, ModelDetail, Version
    from provider.pending_provider import build_model_info

    model = ModelDetail(
        source="civitai",
        id="1",
        name="A LoRA",
        type="LORA",
        license=License(summary="CreativeML OpenRAIL-M"),
        source_url="https://civitai.com/models/1",
        versions=[
            Version(
                id="2",
                name="v1",
                base_model="Illustrious",
                files=[File(id="3", name="a.safetensors", download_url="https://civitai.com/api/download/models/2")],
            )
        ],
    )
    row = PendingRow(
        sha256="0" * 64, source="civitai", source_model_id="1", file_name="a.safetensors", requested_by="u",
        assign_to="none", info={"model": model.model_dump(mode="json"), "version_id": "2", "file_id": "3", "mb_type": "lora"},
    )

    extra = build_model_info(row).extra_data

    assert {field["key"]: extra.get(field["key"]) for field in manifest.model_metadata_fields} == {
        "mb_base_model": "Illustrious",
        "mb_license": "CreativeML OpenRAIL-M",
    }
