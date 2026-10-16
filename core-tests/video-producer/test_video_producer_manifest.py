import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from src.features.notifications.types import NotificationTypeRegistry
from src.features.plans.guard import LimitGuard, PlanSettings
from src.features.plans.records import Plan, PlanLimit, PlanSubject
from src.features.plugins.setup import PluginSetup
from src.platform.plugins.limit_kinds import AdmissionRequest, LimitKindRegistry
from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader
from src.platform.plugins.registry import PluginRegistry
from src.plugin_api import HookContext, SetupCheck, get_current_active_user

PLUGIN_ID = "video-producer"
PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "content" / "plugins" / "marketplace" / PLUGIN_ID
PACKAGE = "video_producer"
KIND = "video-producer.gpu_minutes"

HANDLER_MODULES = {
    "plugin.lifecycle.boot": "video_producer.hooks.lifecycle_hooks",
    "plugin.lifecycle.ready": "video_producer.hooks.lifecycle_hooks",
    "plugin.lifecycle.disable": "video_producer.hooks.lifecycle_hooks",
    "notification_type.register": "video_producer.hooks.notification_hooks",
}
HANDLER_PATHS = {
    "plugin.lifecycle.boot": "hooks.lifecycle_hooks.on_boot",
    "plugin.lifecycle.ready": "hooks.lifecycle_hooks.on_ready",
    "plugin.lifecycle.disable": "hooks.lifecycle_hooks.on_disable",
    "notification_type.register": "hooks.notification_hooks.register_types",
}
SETUP_CHECKS = (
    "backend.setup_checks:VideoEngineReady",
    "backend.setup_checks:VideoPresetsReady",
    "backend.setup_checks:UpscalerReady",
    "backend.setup_checks:FfmpegReady",
    "backend.setup_checks:MiniMaxH3Ready",
)
SEEDVR2 = "01KXB7C553THYMSMKY1QSYESFM"
WAN = "01KX47WANVIDEO0000000000TV"


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


def _handler(loader, manifest, hook):
    handler = loader.load_hook_handler(manifest, manifest.hooks[hook])
    assert callable(handler), f"{hook}: {manifest.hooks[hook]} did not load (see the log above)"
    return handler


def test_manifest_identity_matches_the_backend(manifest):
    backend = _load("backend")

    assert (manifest.id, manifest.version) == (backend.PLUGIN_ID, backend.PLUGIN_VERSION)


def test_manifest_describes_a_full_stack_tool(manifest):
    assert manifest.name == "Video Producer"
    assert manifest.plugin_type == "full-stack"
    assert manifest.category == "tools"
    assert manifest.license == "GPL-3.0"
    assert manifest.description


def test_every_backend_hook_handler_loads_inside_the_plugin_package(loader, manifest):
    assert set(manifest.hooks) == set(HANDLER_MODULES)
    assert manifest.hooks == HANDLER_PATHS
    for hook, handler_path in manifest.hooks.items():
        handler = loader.load_hook_handler(manifest, handler_path)

        assert callable(handler), f"{hook}: {handler_path} did not load (see the log above)"
        assert handler.__module__ == HANDLER_MODULES[hook]

    lifecycle = sys.modules["video_producer.hooks.lifecycle_hooks"]
    assert lifecycle.tables.__name__ == "video_producer.backend.tables"
    notifications = sys.modules["video_producer.hooks.notification_hooks"]
    assert notifications.core_bridge.__name__ == "video_producer.backend.core_bridge"
    assert notifications.notifications.__name__ == "video_producer.backend.notifications"


def test_on_boot_loaded_by_the_core_creates_the_plugin_tables(loader, manifest, mock_db):
    on_boot = _handler(loader, manifest, "plugin.lifecycle.boot")
    context = HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={})

    assert on_boot(context) is context

    with mock_db.get_cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'video_producer_%'")
        created = {row["name"] for row in cursor.fetchall()}
    assert created == set(_load("backend.tables").TABLE_NAMES)
    assert len(created) == 5


def test_api_module_loads_and_exposes_the_router(loader, manifest):
    module_path = manifest.api_routes["module"].replace(".py", "").replace("/", ".")

    api = loader.load_plugin_module(manifest, module_path)

    assert api is not None, f"{manifest.api_routes['module']} did not load (see the log above)"
    assert api.router.prefix == f"/api/plugins/{PLUGIN_ID}"
    routes = {(method, route.path) for route in api.router.routes for method in route.methods}
    base = f"/api/plugins/{PLUGIN_ID}"
    assert routes == {
        ("GET", f"{base}/health"),
        ("GET", f"{base}/me"),
        ("PUT", f"{base}/me"),
        ("GET", f"{base}/projects"),
        ("POST", f"{base}/projects"),
        ("GET", f"{base}/projects/{{project_id}}"),
        ("PUT", f"{base}/projects/{{project_id}}"),
        ("DELETE", f"{base}/projects/{{project_id}}"),
        ("GET", f"{base}/projects/{{project_id}}/versions"),
        ("POST", f"{base}/projects/{{project_id}}/versions/{{version}}/restore"),
        ("POST", f"{base}/media/resolve"),
    }


def test_the_router_loaded_by_the_core_answers_a_signed_in_user(loader, manifest):
    api = loader.load_plugin_module(manifest, "backend.api")
    app = FastAPI(redirect_slashes=False)
    app.include_router(api.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="user-1")

    with TestClient(app) as client:
        response = client.get(f"/api/plugins/{PLUGIN_ID}/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok", "plugin": PLUGIN_ID, "version": manifest.version},
    }


def test_the_project_modules_load_inside_the_plugin_package(loader, manifest):
    loader.load_plugin_module(manifest, "backend.api")

    for name in ("projects", "routes_projects", "routes_media"):
        assert sys.modules[f"{PACKAGE}.backend.{name}"].__name__ == f"{PACKAGE}.backend.{name}"
    projects = sys.modules[f"{PACKAGE}.backend.projects"]
    Draft202012Validator.check_schema(projects.DOC_SCHEMA)
    assert projects.settings is sys.modules[f"{PACKAGE}.backend.settings"]
    assert projects.generate_ulid is sys.modules[f"{PACKAGE}.backend.core_bridge"].generate_ulid
    assert sys.modules[f"{PACKAGE}.backend.routes_media"].MediaRefError is sys.modules[f"{PACKAGE}.backend.core_bridge"].MediaRefError


def test_on_boot_loaded_by_the_core_adds_the_source_version_column(loader, manifest, mock_db):
    on_boot = _handler(loader, manifest, "plugin.lifecycle.boot")

    on_boot(HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={}))
    on_boot(HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={}))

    with mock_db.get_cursor() as cursor:
        cursor.execute("PRAGMA table_info(video_producer_versions)")
        columns = [row["name"] for row in cursor.fetchall()]
    assert columns.count("source_version") == 1


def test_the_router_loaded_by_the_core_stores_versions_and_restores_a_project(loader, manifest, mock_db):
    _handler(loader, manifest, "plugin.lifecycle.boot")(
        HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={})
    )
    api = loader.load_plugin_module(manifest, "backend.api")
    app = FastAPI(redirect_slashes=False)
    app.include_router(api.router)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="user-1", account_type="USER")
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    base = f"/api/plugins/{PLUGIN_ID}/projects"

    with TestClient(app) as client:
        created = client.post(base, json={"doc": starter})
        project_id = created.json()["data"]["project"]["id"]
        saved = client.put(f"{base}/{project_id}", json={"doc": {**starter, "name": "Edited"}, "version": 1})
        restored = client.post(f"{base}/{project_id}/versions/1/restore")
        versions = client.get(f"{base}/{project_id}/versions")
        listed = client.get(base)

    assert created.status_code == 201
    assert saved.json()["data"]["project"]["version"] == 2
    assert restored.json()["data"]["project"]["version"] == 3
    assert [(item["version"], item["source_version"]) for item in versions.json()["data"]["versions"]] == [
        (3, 1),
        (2, None),
        (1, None),
    ]
    assert [(item["id"], item["version"], item["shots"]) for item in listed.json()["data"]["projects"]] == [
        (project_id, 3, 5)
    ]


def test_sidebar_entry_opens_the_page_for_every_user(manifest):
    assert [item["route"] for item in manifest.sidebar_items] == [page["route"] for page in manifest.pages]
    assert all(item.get("require_role") is None for item in manifest.sidebar_items)


def test_the_page_is_the_built_component(manifest):
    [page] = manifest.pages

    assert (page["route"], page["component"], page["label"]) == ("video-producer", "VideoProducerPage.js", "Video Producer")
    assert page.get("require_role") is None
    assert (PLUGIN_ROOT / "frontend" / "dist" / page["component"]).is_file()
    [item] = manifest.sidebar_items
    assert item["label"] == "Video Producer" and item["icon"]


def test_docs_files_exist_and_the_admin_readme_comes_first(manifest):
    for doc in manifest.docs:
        assert (PLUGIN_ROOT / doc["path"]).is_file(), doc["path"]

    assert [(doc["path"], doc["audience"]) for doc in manifest.docs] == [
        ("README.md", "admin"),
        ("docs/user-guide.md", "user"),
        ("docs/user-guide.fr.md", "user"),
    ]
    assert all(doc["title"] for doc in manifest.docs)


def test_the_admin_settings_match_what_the_backend_parses(manifest):
    backend_settings = _load("backend.settings")
    specs = {spec["name"]: spec for spec in manifest.settings}

    assert list(specs) == ["draft_resolution", "max_parallel_jobs", "export_dir_quota_mb", "versions_kept"]
    assert [specs[name]["type"] for name in specs] == ["select", "number", "number", "number"]
    assert {name: spec["default"] for name, spec in specs.items()} == {
        "draft_resolution": "832x480",
        "max_parallel_jobs": 2,
        "export_dir_quota_mb": 2048,
        "versions_kept": 50,
    }
    assert {name: backend_settings.parse_setting(name, spec["default"]) for name, spec in specs.items()} == (
        backend_settings.DEFAULTS
    )
    assert [(option["value"], option["label"]) for option in specs["draft_resolution"]["options"]] == [
        ("832x480", "832×480"),
        ("960x544", "960×544"),
        ("1280x720", "1280×720"),
    ]
    assert tuple(option["value"] for option in specs["draft_resolution"]["options"]) == backend_settings.DRAFT_RESOLUTIONS
    assert all(spec["label"] for spec in specs.values())


def test_the_plugin_contributes_no_chat_mode_nor_tool_yet(manifest):
    assert manifest.chat_modes == []
    assert manifest.tools == []


def test_notification_type_register_declares_the_plugins_types_on_the_cores_registry(loader, manifest):
    register = _handler(loader, manifest, "notification_type.register")
    registry = NotificationTypeRegistry()
    context = HookContext(hook_name="notification_type.register", plugin_id="system", data={"registry": registry})

    assert register(context) is context
    assert register(context) is context

    assert [spec.key for spec in registry.all()] == ["video-producer.take_done", "video-producer.take_failed"]
    assert [item.key for item in _load("backend.notifications").TYPES] == [spec.key for spec in registry.all()]
    for spec in registry.all():
        assert spec.label.startswith("Video Producer: ") and spec.description
        assert (spec.category, spec.default_enabled, spec.admin_only) == ("plugin", True, False)


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


def test_the_gpu_minutes_limit_kind_loads_through_the_cores_registration(limit_kinds):
    limits = _load("backend.limits")

    assert [kind.key for kind in limit_kinds.all()] == [KIND]
    kind = limit_kinds.get(limits.GPU_MINUTES)
    assert kind.key == KIND
    assert kind.label == "Video Producer GPU minutes per month"
    assert kind.short_label == "Video Producer GPU minutes"
    assert kind.description
    assert (kind.value_type, kind.window, kind.unit) == ("count", "month", "min per month")
    assert (kind.enforce_at, kind.ledger, kind.source) == (("submit",), False, PLUGIN_ID)
    assert kind.applies.__module__ == "video_producer.backend.limit_handlers"
    assert kind.applies.__name__ == "never_applies"
    assert kind.measure.__module__ == "video_producer.backend.limit_handlers"
    assert kind.measure.__name__ == "ledger_total"
    assert kind.incoming is None


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


def test_the_core_never_enforces_nor_records_the_gpu_minutes_kind(limit_kinds):
    plan = Plan(id="tiny", name="Tiny", limits=(PlanLimit(KIND, 0),))
    subject = PlanSubject(
        user_id="user-1", username="user", email="u@test.com", account_type="USER",
        override_plan_id="tiny", groups=(), default_plan_id=None,
    )
    events = _Ledger(totals={("user-1", KIND): 7.5})
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
    assert guard.resolution("user-1").value(KIND) == 0
    measured = guard.measure(limit_kinds.get(KIND), "user-1", "UTC")
    assert measured.used == 7.5
    assert measured.resets_at is not None and measured.resets_at.day == 1
    assert events.totals_asked[-1][:2] == ("user-1", KIND)


def test_setup_checks_load_the_way_the_core_loads_them(loader, manifest):
    assert [(step["kind"], step["check"]) for step in manifest.setup] == [("check", ref) for ref in SETUP_CHECKS]
    for step in manifest.setup:
        check_class = loader.load_class(manifest, step["check"])

        assert check_class is not None, f"{step['check']} did not load (see the log above)"
        assert issubclass(check_class, SetupCheck)
        assert check_class.__module__ == "video_producer.backend.setup_checks"
        assert check_class.__name__ == step["check"].split(":")[1]
        assert step["label"]
        assert isinstance(check_class(), SetupCheck)


def _setup(loader, manifest):
    return PluginSetup(
        plugin_registry=SimpleNamespace(loader=loader, get_enabled_plugins=lambda: [manifest]),
        plugin_repository=SimpleNamespace(get_plugin_settings=lambda plugin_id: []),
        backend_registry=SimpleNamespace(get_registered_config_types=lambda: {}),
        catalog_repository=None,
        preset_loader=None,
        preset_db_repo=None,
        group_repo=None,
    )


def _bridge(loader, manifest):
    for step in manifest.setup:
        assert loader.load_class(manifest, step["check"]) is not None
    return sys.modules["video_producer.backend.core_bridge"]


def _fake_host(monkeypatch, bridge, *, backends, states, ffmpeg):
    monkeypatch.setattr(bridge, "enabled_backends", lambda: backends)
    monkeypatch.setattr(bridge, "enabled_cloud_video_models", lambda backend_id: 0)
    monkeypatch.setattr(
        bridge,
        "preset_state",
        lambda preset_id: states.get(preset_id)
        or bridge.PresetState(id=preset_id, name=preset_id, loaded=False, installed=False, assigned=False),
    )
    monkeypatch.setattr(bridge, "preset_model_hashes", lambda preset_id, names: {name: set() for name in names})
    monkeypatch.setattr(bridge, "model_file_present", lambda sha256: False)
    monkeypatch.setattr(bridge, "find_ffmpeg", lambda: ffmpeg)


def test_the_core_setup_report_runs_the_checks(loader, manifest, monkeypatch):
    bridge = _bridge(loader, manifest)
    local = {"id": "b-1", "name": "This machine", "engine": "native", "driver": "native.local"}
    wan = bridge.PresetState(id=WAN, name="Wan", loaded=True, installed=True, assigned=False)
    _fake_host(monkeypatch, bridge, backends=[local], states={WAN: wan}, ffmpeg="/usr/bin/ffmpeg")

    report = _setup(loader, manifest).report(manifest)

    assert (report.plugin_id, report.complete, report.remaining) == (PLUGIN_ID, False, 2)
    assert [step.id for step in report.steps] == [f"{index}-check" for index in range(5)]
    assert [step.label for step in report.steps] == [step["label"] for step in manifest.setup]
    engine, presets, upscaler, ffmpeg, minimax = report.steps
    assert (engine.status, engine.action) == ("done", None)
    assert engine.description == "Takes can run on This machine."
    assert (presets.status, presets.action.kind, presets.action.label) == ("todo", "link", "Assign presets")
    assert presets.action.href == f"/admin?tab=presets&id={WAN}"
    assert "Installed but assigned to no one: Wan." in presets.description
    assert (upscaler.status, upscaler.action.label, upscaler.action.href) == ("todo", "Open presets", "/admin?tab=presets")
    assert (ffmpeg.status, ffmpeg.action, ffmpeg.description) == ("done", None, "ffmpeg is available.")
    assert (minimax.status, minimax.action) == ("done", None)


def test_the_core_setup_report_is_complete_when_everything_is_ready(loader, manifest, monkeypatch):
    bridge = _bridge(loader, manifest)
    local = {"id": "b-1", "name": "This machine", "engine": "native", "driver": "native.local"}
    states = {
        WAN: bridge.PresetState(id=WAN, name="Wan", loaded=True, installed=True, assigned=True),
        SEEDVR2: bridge.PresetState(id=SEEDVR2, name="SeedVR2", loaded=True, installed=True, assigned=True),
    }
    _fake_host(monkeypatch, bridge, backends=[local], states=states, ffmpeg="/usr/bin/ffmpeg")

    report = _setup(loader, manifest).report(manifest)

    assert (report.complete, report.remaining) == (True, 0)
    assert [step.status for step in report.steps] == ["done"] * 5
    assert all(step.action is None for step in report.steps)


def test_the_core_setup_report_shows_a_check_that_cannot_read_the_host_as_still_to_do(loader, manifest, monkeypatch):
    bridge = _bridge(loader, manifest)

    def broken(*args, **kwargs):
        raise RuntimeError("AppContainer not initialized yet")

    for name in ("enabled_backends", "preset_state", "find_ffmpeg"):
        monkeypatch.setattr(bridge, name, broken)

    report = _setup(loader, manifest).report(manifest)

    assert (report.complete, report.remaining) == (False, 5)
    assert [step.status for step in report.steps] == ["todo"] * 5
    assert all(step.description.startswith("Could not check ") for step in report.steps)
    assert all(step.action.kind == "link" and step.action.href.startswith("/admin?tab=") for step in report.steps)


def test_the_setup_guide_points_at_the_admin_readme_the_ffmpeg_step_links_to(loader, manifest, monkeypatch):
    bridge = _bridge(loader, manifest)
    _fake_host(monkeypatch, bridge, backends=[], states={}, ffmpeg=None)

    report = _setup(loader, manifest).report(manifest)

    assert report.guide.title == "Video Producer: administration"
    ffmpeg = report.steps[3]
    assert (ffmpeg.status, ffmpeg.action.label) == ("todo", "Read the guide")
    assert ffmpeg.action.href == report.guide.href
    assert [step.kind for step in report.steps] == ["check"] * 5
