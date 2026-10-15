import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.features.models.attributes.editor import FIELD_TYPES, KEY_PATTERN, ModelAttributeDefinitionsEditor
from src.features.notifications.types import NotificationTypeRegistry
from src.features.plans.guard import LimitGuard, PlanSettings
from src.features.plans.records import Plan, PlanLimit, PlanSubject
from src.features.plugins.setup import PluginSetup
from src.features.providers.registry import ProviderRegistry
from src.platform.plugins.hooks import HookChain
from src.platform.plugins.limit_kinds import AdmissionRequest, LimitKindRegistry
from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader
from src.platform.plugins.registry import PluginRegistry
from src.plugin_api import HookContext, MarketplaceProviderBase, ProviderCapability, SetupCheck

PLUGIN_ID = "model-browser"
PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "content" / "plugins" / "marketplace" / PLUGIN_ID
PACKAGE = "model_browser"

HANDLER_MODULES = {
    "plugin.lifecycle.boot": "model_browser.hooks.lifecycle_hooks",
    "plugin.lifecycle.ready": "model_browser.hooks.lifecycle_hooks",
    "plugin.lifecycle.disable": "model_browser.hooks.lifecycle_hooks",
    "download.after_complete": "model_browser.hooks.download_hooks",
    "provider.register": "model_browser.hooks.provider_hooks",
    "notification_type.register": "model_browser.hooks.notification_hooks",
}
SETUP_CHECKS = {
    "backend.setup_checks:CivitaiProviderReady": "civitai",
    "backend.setup_checks:HuggingFaceProviderReady": "huggingface",
}


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


@pytest.fixture
def loader(monkeypatch, tmp_path):
    monkeypatch.delenv(EXTRA_PLUGIN_DIRS_ENV, raising=False)
    return PluginLoader(marketplace_dir=str(PLUGIN_ROOT.parent), local_dir=str(tmp_path / "local"))


@pytest.fixture
def manifest(loader):
    found = [m for m in loader.discover_plugins() if Path(m.plugin_dir).resolve() == PLUGIN_ROOT]
    assert len(found) == 1, f"PluginLoader did not discover {PLUGIN_ROOT}"
    assert found[0].validation_error is None, found[0].validation_error
    return found[0]


def test_manifest_identity_matches_the_backend(manifest):
    backend = _load("backend")

    assert (manifest.id, manifest.version) == (backend.PLUGIN_ID, backend.PLUGIN_VERSION)


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

    lifecycle = sys.modules["model_browser.hooks.lifecycle_hooks"]
    assert lifecycle.tables.__name__ == "model_browser.backend.tables"
    download = sys.modules["model_browser.hooks.download_hooks"]
    assert download.watcher.__name__ == "model_browser.backend.watcher"
    assert download.pending.__name__ == "model_browser.backend.pending"
    assert manifest.hooks["download.after_complete"] == "hooks.download_hooks.on_download_complete"


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


def test_provider_register_adds_the_two_providers_next_to_the_others(loader, manifest):
    register = _handler(loader, manifest, "provider.register")
    other = type("CivitaiProvider", (), {})
    context = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={"providers": {"civitai": other}})

    result = register(context)

    assert result is context
    providers = result.data["providers"]
    assert list(providers) == ["civitai", "model-browser", "openmodeldb"]
    assert providers["civitai"] is other
    for provider_id, module in (
        ("model-browser", "pending_provider"),
        ("openmodeldb", "openmodeldb_provider"),
    ):
        provider_class = providers[provider_id]
        assert issubclass(provider_class, MarketplaceProviderBase)
        assert provider_class.__module__ == f"model_browser.provider.{module}"
        assert provider_class().get_metadata().id == provider_id
    assert sys.modules["model_browser.provider.pending_provider"].pending.__name__ == "model_browser.backend.pending"
    openmodeldb_module = sys.modules["model_browser.provider.openmodeldb_provider"]
    assert openmodeldb_module.openmodeldb.__name__ == "model_browser.backend.sources.openmodeldb"
    assert openmodeldb_module.sources.__name__ == "model_browser.backend.sources"


def test_provider_register_creates_the_providers_map_and_never_raises(loader, manifest):
    register = _handler(loader, manifest, "provider.register")
    empty = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={})
    broken = HookContext(hook_name="provider.register", plugin_id=PLUGIN_ID, data={"providers": "not a map"})

    registered = register(empty).data["providers"]
    assert {provider_id: cls.__name__ for provider_id, cls in registered.items()} == {
        "model-browser": "PendingProvider",
        "openmodeldb": "OpenModelDBProvider",
    }
    assert register(broken) is broken
    assert broken.data["providers"] == "not a map"


async def test_the_core_provider_registry_discovers_and_initializes_the_provider(
    loader, manifest, mock_db, monkeypatch
):
    chain = HookChain()
    chain.register("provider.register", PLUGIN_ID, _handler(loader, manifest, "provider.register"))

    class Plugins:
        def get_enabled_plugins(self):
            return []

        def get_plugins_for_hook(self, hook):
            return [PLUGIN_ID]

        def execute_hook(self, hook, context=None, initial_data=None):
            final, results = chain.execute(hook, context=context, initial_data=initial_data)
            return final, all(result.success for result in results)

    registry = ProviderRegistry(registry=Plugins())
    monkeypatch.setattr(registry, "_get_provider_settings", lambda provider_id: {})

    assert [metadata.id for metadata in await registry.discover_providers()] == ["model-browser", "openmodeldb"]
    assert await registry.initialize_providers() == {"model-browser": True, "openmodeldb": True}
    assert all(registry.is_provider_initialized(provider_id) for provider_id in ("model-browser", "openmodeldb"))
    provider, openmodeldb = registry.get_provider("model-browser"), registry.get_provider("openmodeldb")
    assert registry.get_providers_with_capability(ProviderCapability.HASH_LOOKUP) == [provider, openmodeldb]
    assert (provider.provider_name, openmodeldb.provider_name) == ("Model Browser", "OpenModelDB")
    assert provider.get_model_page_url("civitai:122359", "135867") == (
        "https://civitai.com/models/122359?modelVersionId=135867"
    )
    assert openmodeldb.get_model_page_url("openmodeldb:4x-UltraSharp") == "https://openmodeldb.info/models/4x-UltraSharp"
    _load("backend.tables").create_tables()
    assert await registry.get_model_by_hash("model-browser", "0" * 64, raise_errors=True) is None
    assert await registry.get_model_by_hash("openmodeldb", "not-a-hash", raise_errors=True) is None


def test_notification_type_register_declares_the_plugins_types_on_the_cores_registry(loader, manifest):
    register = _handler(loader, manifest, "notification_type.register")
    registry = NotificationTypeRegistry()
    context = HookContext(hook_name="notification_type.register", plugin_id="system", data={"registry": registry})

    assert register(context) is context
    assert register(context) is context

    assert [spec.key for spec in registry.all()] == [
        "model-browser.request_received",
        "model-browser.request_approved",
        "model-browser.request_rejected",
        "model-browser.download_done",
        "model-browser.download_failed",
    ]
    assert [item.key for item in _load("backend.notifications").TYPES] == [spec.key for spec in registry.all()]
    for spec in registry.all():
        assert spec.label.startswith("Model Browser: ") and spec.description
        assert (spec.category, spec.default_enabled, spec.admin_only) == ("plugin", True, False)
    hooks_module = sys.modules["model_browser.hooks.notification_hooks"]
    assert hooks_module.core_bridge.__name__ == "model_browser.backend.core_bridge"


def test_notification_type_register_never_raises(loader, manifest):
    register = _handler(loader, manifest, "notification_type.register")
    empty = HookContext(hook_name="notification_type.register", plugin_id="system", data={})
    broken = HookContext(hook_name="notification_type.register", plugin_id="system", data={"registry": "not one"})

    assert register(empty) is empty
    assert register(broken) is broken


@pytest.fixture
def limit_kinds(manifest, tmp_path):
    kinds = LimitKindRegistry()
    plugins = PluginRegistry(
        marketplace_dir=str(PLUGIN_ROOT.parent), local_dir=str(tmp_path / "local"), limit_kind_registry=kinds
    )
    assert plugins._register_plugin_limit_kinds(manifest) is None
    return kinds


def test_the_limit_kinds_load_through_the_cores_registration(limit_kinds):
    limits = _load("backend.limits")

    downloads, volume = limit_kinds.get(limits.DOWNLOADS), limit_kinds.get(limits.DOWNLOAD_BYTES)
    assert [kind.key for kind in limit_kinds.all()] == list(limits.KINDS)
    assert (downloads.label, downloads.value_type, downloads.window) == ("Model downloads per month", "count", "month")
    assert (volume.label, volume.value_type, volume.window) == ("Downloaded model bytes per month", "bytes", "month")
    for kind in (downloads, volume):
        assert kind.label == limits.LABELS[kind.key]
        assert (kind.enforce_at, kind.ledger, kind.source) == (("submit",), False, PLUGIN_ID)
        assert kind.applies.__module__ == "model_browser.backend.limit_handlers"
        assert kind.measure.__module__ == "model_browser.backend.limit_handlers"


def test_the_core_never_enforces_nor_records_the_plugin_limit_kinds(limit_kinds):
    plan = Plan(
        id="tiny", name="Tiny", limits=(PlanLimit("model-browser.downloads", 0), PlanLimit("model-browser.download_bytes", 0))
    )
    subject = PlanSubject(user_id="user-1", username="user", email="u@test.com", account_type="USER",
                          override_plan_id="tiny", groups=(), default_plan_id=None)
    events = _Ledger(totals={("user-1", "model-browser.downloads"): 3.0})
    guard = LimitGuard(
        registry=limit_kinds,
        plans=SimpleNamespace(subject=lambda user_id: subject, list_plans=lambda: [plan]),
        events=events,
        usage=None,
        settings=SimpleNamespace(read=lambda: PlanSettings(exempt_admins=True, day_timezone="UTC", contact_line="")),
    )

    guard.check(AdmissionRequest(point="submit", user_id="user-1"))
    guard.check(AdmissionRequest(point="upload", user_id="user-1", incoming_bytes=10))
    guard.admit(AdmissionRequest(point="submit", user_id="user-1", ref_id="generation-1"))

    assert events.recorded == []
    assert guard.resolution("user-1").value("model-browser.downloads") == 0
    measured = guard.measure(limit_kinds.get("model-browser.downloads"), "user-1", "UTC")
    assert measured.used == 3.0
    assert measured.resets_at is not None and measured.resets_at.day == 1
    assert events.totals_asked[-1][:2] == ("user-1", "model-browser.downloads")


class _Ledger:
    def __init__(self, totals):
        self.totals = totals
        self.totals_asked = []
        self.recorded = []

    def total(self, user_id, kind, since, until):
        self.totals_asked.append((user_id, kind, since, until))
        return self.totals.get((user_id, kind), 0.0)

    def record(self, user_id, kind, units, ref_id, at):
        self.recorded.append((user_id, kind, units, ref_id))
        return "event"

    def refund(self, ref_id, at):
        return 0

    def prune(self, before):
        return 0


def test_setup_checks_load_the_way_the_core_loads_them(loader, manifest):
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


def test_model_metadata_fields_are_text_attributes_for_every_model_type(manifest):
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
    schema = _load("backend.schema")
    model = schema.ModelDetail(
        source="civitai",
        id="1",
        name="A LoRA",
        type="LORA",
        license=schema.License(summary="CreativeML OpenRAIL-M"),
        source_url="https://civitai.com/models/1",
        versions=[
            schema.Version(
                id="2",
                name="v1",
                base_model="Illustrious",
                files=[schema.File(id="3", name="a.safetensors", download_url="https://civitai.com/api/download/models/2")],
            )
        ],
    )
    row = _load("backend.pending").PendingRow(
        sha256="0" * 64, source="civitai", source_model_id="1", file_name="a.safetensors", requested_by="u",
        assign_to="none", info={"model": model.model_dump(mode="json"), "version_id": "2", "file_id": "3", "mb_type": "lora"},
    )

    extra = _load("provider.pending_provider").build_model_info(row).extra_data

    assert {field["key"]: extra.get(field["key"]) for field in manifest.model_metadata_fields} == {
        "mb_base_model": "Illustrious",
        "mb_license": "CreativeML OpenRAIL-M",
    }
