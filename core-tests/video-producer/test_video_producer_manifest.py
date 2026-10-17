import dataclasses
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
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
    "generation.after_complete": "video_producer.hooks.generation_hooks",
    "generation.failed": "video_producer.hooks.generation_hooks",
}
HANDLER_PATHS = {
    "plugin.lifecycle.boot": "hooks.lifecycle_hooks.on_boot",
    "plugin.lifecycle.ready": "hooks.lifecycle_hooks.on_ready",
    "plugin.lifecycle.disable": "hooks.lifecycle_hooks.on_disable",
    "notification_type.register": "hooks.notification_hooks.register_types",
    "generation.after_complete": "hooks.generation_hooks.on_after_complete",
    "generation.failed": "hooks.generation_hooks.on_failed",
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
    assert lifecycle.tracker.__name__ == "video_producer.backend.tracker"
    generation_hooks = sys.modules["video_producer.hooks.generation_hooks"]
    assert generation_hooks.generation.__name__ == "video_producer.backend.generation"


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
        ("GET", f"{base}/projects/{{project_id}}/takes"),
        ("POST", f"{base}/projects/{{project_id}}/takes/{{take_id}}/choose"),
        ("POST", f"{base}/projects/{{project_id}}/takes/{{take_id}}/flag"),
        ("DELETE", f"{base}/projects/{{project_id}}/takes/{{take_id}}"),
        ("POST", f"{base}/projects/{{project_id}}/takes/{{take_id}}/final"),
        ("POST", f"{base}/takes/{{take_id}}/cancel"),
        ("POST", f"{base}/takes/{{take_id}}/retry"),
        ("POST", f"{base}/projects/{{project_id}}/estimate"),
        ("POST", f"{base}/projects/{{project_id}}/generate"),
        ("GET", f"{base}/projects/{{project_id}}/queue"),
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


def test_the_generation_hooks_loaded_by_the_core_ignore_a_generation_of_no_take(loader, manifest, mock_db):
    _handler(loader, manifest, "plugin.lifecycle.boot")(
        HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={})
    )
    completed = HookContext(
        hook_name="generation.after_complete",
        plugin_id="system",
        data={"generation_id": "gen-1", "status": "completed", "duration": 3.0, "preset_id": WAN, "user_id": "user-1"},
    )
    failed = HookContext(
        hook_name="generation.failed",
        plugin_id="system",
        data={"generation_id": "gen-1", "error_code": "cuda_oom", "message": "Out of memory."},
    )

    assert _handler(loader, manifest, "generation.after_complete")(completed) is completed
    assert _handler(loader, manifest, "generation.failed")(failed) is failed


def test_on_boot_loaded_by_the_core_adds_the_take_columns(loader, manifest, mock_db):
    on_boot = _handler(loader, manifest, "plugin.lifecycle.boot")

    on_boot(HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={}))
    on_boot(HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={}))

    with mock_db.get_cursor() as cursor:
        cursor.execute("PRAGMA table_info(video_producer_takes)")
        columns = [row["name"] for row in cursor.fetchall()]
    for column in ("director_mode", "progress", "variant", "chosen", "units_reserved", "user_id", "request"):
        assert columns.count(column) == 1


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
    monkeypatch.setattr(bridge, "preset_model_hashes", lambda preset_id, names, modes=None: {name: set() for name in names})
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


@pytest.fixture
def scheduled(monkeypatch):
    import concurrent.futures

    import src.plugin_api.hooks as plugin_hooks

    jobs = []

    def run_on_app_loop(coro):
        jobs.append(coro)
        return concurrent.futures.Future()

    monkeypatch.setattr(plugin_hooks, "run_on_app_loop", run_on_app_loop)
    yield jobs
    tracker = sys.modules.get(f"{PACKAGE}.backend.tracker")
    if tracker is not None:
        tracker.TRACKER.stop()
    for job in jobs:
        job.close()


def _boot(loader, manifest):
    _handler(loader, manifest, "plugin.lifecycle.boot")(
        HookContext(hook_name="plugin.lifecycle.boot", plugin_id=PLUGIN_ID, data={})
    )


def _app(loader, manifest, caller):
    api = loader.load_plugin_module(manifest, "backend.api")
    app = FastAPI(redirect_slashes=False)
    app.include_router(api.router)
    app.dependency_overrides[get_current_active_user] = lambda: caller["user"]
    return app


def _user(user_id):
    return SimpleNamespace(id=user_id, account_type="USER")


def test_on_ready_loaded_by_the_core_schedules_the_take_tracker_on_the_application_loop(loader, manifest, scheduled):
    on_ready = _handler(loader, manifest, "plugin.lifecycle.ready")
    on_disable = _handler(loader, manifest, "plugin.lifecycle.disable")
    ready = HookContext(hook_name="plugin.lifecycle.ready", plugin_id=PLUGIN_ID, data={})
    tracker = sys.modules[f"{PACKAGE}.backend.tracker"]

    assert on_ready(ready) is ready
    assert on_ready(ready) is ready

    assert [job.__qualname__ for job in scheduled] == ["Tracker.run"]
    assert tracker.TRACKER.running is True
    assert (tracker.BUSY_INTERVAL, tracker.IDLE_INTERVAL) == (2.0, 10.0)

    other = HookContext(hook_name="plugin.lifecycle.disable", plugin_id="system", data={"plugin_id": "civitai-provider"})
    assert on_disable(other) is other
    assert tracker.TRACKER.running is True

    own = HookContext(hook_name="plugin.lifecycle.disable", plugin_id="system", data={"plugin_id": PLUGIN_ID})
    assert on_disable(own) is own
    assert tracker.TRACKER.running is False


def test_on_ready_loaded_by_the_core_survives_an_application_loop_that_is_not_there(loader, manifest, monkeypatch):
    import src.plugin_api.hooks as plugin_hooks

    def run_on_app_loop(coro):
        raise RuntimeError("Application event loop is not available")

    monkeypatch.setattr(plugin_hooks, "run_on_app_loop", run_on_app_loop)
    on_ready = _handler(loader, manifest, "plugin.lifecycle.ready")
    ready = HookContext(hook_name="plugin.lifecycle.ready", plugin_id=PLUGIN_ID, data={})

    assert on_ready(ready) is ready
    assert sys.modules[f"{PACKAGE}.backend.tracker"].TRACKER.running is False


def test_the_generation_hooks_loaded_by_the_core_end_the_take_of_their_generation(loader, manifest, mock_db, monkeypatch):
    _boot(loader, manifest)
    after_complete = _handler(loader, manifest, "generation.after_complete")
    on_failed = _handler(loader, manifest, "generation.failed")
    bridge = sys.modules[f"{PACKAGE}.backend.core_bridge"]
    takes = sys.modules[f"{PACKAGE}.backend.takes"]
    refunded, notified = [], []
    monkeypatch.setattr(bridge, "refund_limit_event", lambda ref_id: refunded.append(ref_id) or 1)
    monkeypatch.setattr(bridge, "notify", lambda **fields: notified.append(fields))
    base = {"project_id": "p-1", "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "units_reserved": 1.5}
    failing = takes.create_take({**base, "generation_id": "gen-1", "status": "running"})
    cancelling = takes.create_take({**base, "generation_id": "gen-2"})

    def failed(code, message):
        data = {"generation_id": "gen-1", "error_code": code, "message": message}
        on_failed(HookContext(hook_name="generation.failed", plugin_id="system", data=data))

    def completed(generation_id, status):
        data = {"generation_id": generation_id, "status": status}
        after_complete(HookContext(hook_name="generation.after_complete", plugin_id="system", data=data))

    failed("cuda_oom", "Out of memory.")
    failed("other", "Again.")
    completed("gen-2", "cancelled")
    completed("unknown", "completed")

    current = takes.get_take(failing["id"])
    assert (current["status"], current["error_code"], current["error_message"]) == ("failed", "cuda_oom", "Out of memory.")
    assert takes.get_take(cancelling["id"])["status"] == "cancelled"
    assert sorted(refunded) == sorted(f"video-producer:{take['id']}" for take in (failing, cancelling))
    assert [fields["notification_type"] for fields in notified] == ["video-producer.take_failed"]


def test_the_takes_routes_loaded_by_the_core_list_choose_flag_and_delete_a_take(loader, manifest, mock_db):
    _boot(loader, manifest)
    caller = {"user": _user("user-1")}
    app = _app(loader, manifest, caller)
    takes = sys.modules[f"{PACKAGE}.backend.takes"]
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    base = f"/api/plugins/{PLUGIN_ID}"

    with TestClient(app) as client:
        project_id = client.post(f"{base}/projects", json={"doc": starter}).json()["data"]["project"]["id"]
        take = takes.create_take(
            {
                "project_id": project_id,
                "shot_id": "s1",
                "user_id": "user-1",
                "quality": "draft",
                "kind": "render",
                "status": "done",
                "generation_id": "gen-1",
                "file_path": "generations/x/1.mp4",
                "request": {"form_data": {}},
            }
        )
        listed = client.get(f"{base}/projects/{project_id}/takes").json()["data"]["takes"]
        queue = client.get(f"{base}/projects/{project_id}/queue").json()["data"]
        chosen = client.post(f"{base}/projects/{project_id}/takes/{take['id']}/choose", json={"chosen": True})
        flagged = client.post(f"{base}/projects/{project_id}/takes/{take['id']}/flag", json={"flag": "keep"})
        caller["user"] = _user("user-2")
        foreign = client.get(f"{base}/projects/{project_id}/takes")
        foreign_cancel = client.post(f"{base}/takes/{take['id']}/cancel")
        caller["user"] = _user("user-1")
        deleted = client.delete(f"{base}/projects/{project_id}/takes/{take['id']}")

    assert [(item["id"], item["url"], item["status"]) for item in listed] == [
        (take["id"], "/api/media/generations/gen-1/1.mp4", "done")
    ]
    assert "request" not in listed[0] and "user_id" not in listed[0]
    assert queue == {"takes": [], "slots": {"in_flight": 0, "max": 2}}
    assert (chosen.status_code, chosen.json()["data"]["take"]["chosen"]) == (200, True)
    assert (flagged.status_code, flagged.json()["data"]["take"]["flag"]) == (200, "keep")
    assert (foreign.status_code, foreign_cancel.status_code) == (404, 404)
    assert deleted.json() == {"success": True, "data": {"deleted": take["id"]}}
    assert takes.get_take(take["id"]) is None


def test_the_estimate_and_generate_routes_loaded_by_the_core_block_without_a_preset_instead_of_failing(loader, manifest, mock_db):
    _boot(loader, manifest)
    app = _app(loader, manifest, {"user": _user("user-1")})
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    base = f"/api/plugins/{PLUGIN_ID}"
    order = {"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": WAN}

    with TestClient(app) as client:
        project_id = client.post(f"{base}/projects", json={"doc": starter}).json()["data"]["project"]["id"]
        estimated = client.post(f"{base}/projects/{project_id}/estimate", json=order)
        generated = client.post(f"{base}/projects/{project_id}/generate", json=order)
        malformed = client.post(f"{base}/projects/{project_id}/estimate", json={**order, "variants": 0})

    assert estimated.status_code == 200
    assert [block["code"] for block in estimated.json()["data"]["blocks"]] == ["no_preset"]
    assert estimated.json()["data"]["vram"]["unknown"] is True
    assert generated.status_code == 409 and generated.json()["detail"]["error"] == "blocked"
    assert malformed.status_code == 422


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_PRESETS = REPO_ROOT / "content" / "presets" / "marketplace"
SHARED_PRESETS = REPO_ROOT / "content" / "presets" / "_shared"
H3_12GB = "01M54HN72B0KY7H63BKQ16T253"
H3_FAST_12GB = "01M54HN72PABVRE54YNQA2Q7ZT"
COMFY_DIT = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
WAN2GP_DIT = "MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors"
WAN2GP_SHA256 = "30ff400f974b11a1ef13d216c5d9f6439a9c10322a3988b0374a39672ce286f0"
FASTH3_DIT = "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
SHIPPED_PRESETS = {
    H3_12GB: ("MiniMax-H3 (12 GB)", "MiniMax-H3-12GB", "01KX47H3MINIMAX000000000VA"),
    H3_FAST_12GB: ("MiniMax-H3-Fast (12 GB)", "MiniMax-H3-Fast-12GB", "01KX47H3FASTH30000000000VA"),
}
CHANGED_FIELDS = {
    H3_12GB: {
        "speed_profile": {"default"},
        "resolution": {"default", "configuration"},
        "model": {"configuration"},
        "text_encoder": {"configuration"},
        "video_vae": {"configuration"},
        "keyframe_pixel_budget": {"default"},
        "steps": {"default"},
        "sampler": {"default", "ai_hint"},
    },
    H3_FAST_12GB: {
        "resolution": {"default", "configuration"},
        "model": {"configuration"},
        "text_encoder": {"configuration"},
        "video_vae": {"configuration", "ai_hint"},
        "keyframe_pixel_budget": {"default"},
    },
}
PROFILE_DEFAULTS = {
    H3_12GB: {"speed_profile": "custom", "steps": 20},
    H3_FAST_12GB: {"speed_profile": "distilled", "steps": 8},
}
RECOMMENDED = {
    H3_12GB: {"model": [COMFY_DIT, WAN2GP_DIT], "text_encoder": [TEXT_ENCODER], "video_vae": [VIDEO_VAE], "audio_vae": [AUDIO_VAE]},
    H3_FAST_12GB: {"model": [FASTH3_DIT], "text_encoder": [TEXT_ENCODER], "video_vae": [VIDEO_VAE], "audio_vae": [AUDIO_VAE]},
}


def _preset_loader(roots, manifests=()):
    from src.features.presets.loader import PresetTemplateLoader

    registry = SimpleNamespace(get_enabled_plugins=lambda: list(manifests))
    loader = PresetTemplateLoader([str(root) for root in roots], plugin_registry=registry, shared_path=str(SHARED_PRESETS))
    return loader, {preset.id: preset for preset in loader.load_presets()}


@pytest.fixture
def shipped_presets(manifest):
    loader, loaded = _preset_loader([], [manifest])
    assert loader.load_errors == {}
    return loaded


@pytest.fixture(scope="module")
def core_h3_presets():
    loader, loaded = _preset_loader([CORE_PRESETS / "MiniMax-H3", CORE_PRESETS / "MiniMax-H3-Fast"])
    assert loader.load_errors == {}
    return loaded


def _flatten(fields, named, skeleton):
    for field in fields:
        skeleton.append((field.type, field.name, field.label, field.audience))
        if field.name:
            named[field.name] = field
        if isinstance(field.children, list):
            _flatten(field.children, named, skeleton)
    return named, skeleton


def _video_form(preset):
    [form] = preset.modes["video"].forms
    return _flatten(form.fields, {}, [])


def _option_files(preset, field):
    from src.features.presets.children_paths import resolve_children_path

    return [
        (resolve_children_path(entry["path"], Path(preset.path), SHARED_PRESETS).resolve(), entry["group"])
        for entry in field.configuration["files"]
    ]


def test_the_manifest_declares_the_presets_folder(manifest):
    assert manifest.presets == [{"path": "presets"}]


def test_the_shipped_presets_load_through_the_cores_loader(shipped_presets):
    assert {preset_id: preset.name for preset_id, preset in shipped_presets.items()} == {
        preset_id: name for preset_id, (name, _, _) in SHIPPED_PRESETS.items()
    }
    for preset_id, (_, folder, _) in SHIPPED_PRESETS.items():
        preset = shipped_presets[preset_id]
        assert preset.origin == {"kind": "plugin", "plugin_id": PLUGIN_ID, "path": folder}
        assert (preset.engine, preset.category, list(preset.modes)) == ("native", "video", ["video"])
        assert preset.requires == {"min_vram_gb": 12, "recommended_vram_gb": 12}
        assert preset.tags[:2] == ["12gb", "low-vram"]
        assert preset.vars["video_producer"] == {"profile": "12 GB"}
        assert (preset.vars["fps"], preset.vars["default_frames"]) == (24, 124)
        assert "12 GB" in preset.description and "64 GB" in preset.description


def test_the_backend_knows_the_shipped_presets_and_reads_their_profile(shipped_presets):
    presets = _load("backend.presets")
    catalog = _load("backend.catalog")

    for preset_id, preset in shipped_presets.items():
        assert preset_id in presets.MINIMAX_H3_PRESETS and preset_id in presets.VIDEO_DIRECTOR_PRESETS
        assert catalog.memory_profile(preset.vars) == "12 GB"
        assert catalog.main_mode(preset.vars, list(preset.modes)) == "video"
        assert catalog.profiles(preset_id, preset.vars, list(preset.modes)) == ["FL2VA", "Hybrid AV"]


def test_the_shipped_presets_keep_the_director_and_prompt_help_of_the_core_presets(shipped_presets, core_h3_presets):
    for preset_id, (_, _, source_id) in SHIPPED_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_h3_presets[source_id]
        assert preset.vars["video_director"] == source.vars["video_director"]
        assert preset.vars["prompt"]["segment_templates"] == source.vars["prompt"]["segment_templates"][:1]
        assert preset.configuration == source.configuration
        assert preset.llm == {key: value for key, value in source.llm.items() if key != "modes"}
        assert preset.prompt_syntax == {"video": source.prompt_syntax["video"]}
        assert preset.formulas["groups"] == {name: group for name, group in source.formulas["groups"].items() if name != "memory"}


def test_the_shipped_presets_run_the_core_pipelines_unchanged(shipped_presets, core_h3_presets):
    for preset_id, (_, folder, source_id) in SHIPPED_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_h3_presets[source_id]
        assert preset.modes["video"].pipes == source.modes["video"].pipes
        copy = yaml.safe_load((PLUGIN_ROOT / "presets" / folder / "modes" / "video" / "pipeline.yml").read_text(encoding="utf-8"))
        original = yaml.safe_load((Path(source.path) / "modes" / "video" / "pipeline.yml").read_text(encoding="utf-8"))
        assert copy == original


def test_the_shipped_forms_change_only_the_12_gb_defaults_and_files_of_the_core_forms(shipped_presets, core_h3_presets):
    for preset_id, (_, _, source_id) in SHIPPED_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_h3_presets[source_id]
        named, skeleton = _video_form(preset)
        source_named, source_skeleton = _video_form(source)
        assert skeleton == source_skeleton
        for name, field in named.items():
            changed = CHANGED_FIELDS[preset_id].get(name, set())
            assert field == dataclasses.replace(source_named[name], **{attr: getattr(field, attr) for attr in changed}), name
        assert {name: named[name].default for name in ("resolution", "quantity", "sampler", "scheduler", "keyframe_pixel_budget")} == {
            "resolution": "832x480",
            "quantity": 1,
            "sampler": "res_multistep",
            "scheduler": "simple",
            "keyframe_pixel_budget": "1",
        }
        assert {name: named[name].default for name in PROFILE_DEFAULTS[preset_id]} == PROFILE_DEFAULTS[preset_id]
        assert preset.speed_profiles[named["speed_profile"].default]["steps"] == named["steps"].default
        assert _option_files(preset, named["resolution"]) == _option_files(source, source_named["resolution"])
        for name in RECOMMENDED[preset_id]:
            mine = {key: value for key, value in named[name].configuration.items() if key not in ("recommendations", "placeholder")}
            theirs = {key: value for key, value in source_named[name].configuration.items() if key not in ("recommendations", "placeholder")}
            assert mine == theirs, name
            assert all(len(item["sha256"]) == 64 for item in named[name].configuration["recommendations"]), name
        assert {
            name: [item["name"] for item in named[name].configuration["recommendations"]] for name in RECOMMENDED[preset_id]
        } == RECOMMENDED[preset_id]


@pytest.mark.parametrize("aspect, draft, final", [(16 / 9, "832x480", "1344x768"), (9 / 16, "480x832", "768x1344")])
def test_the_plugin_drafts_the_shipped_presets_at_832x480_and_finishes_them_at_the_released_canvas(shipped_presets, aspect, draft, final):
    bridge = _load("backend.core_bridge")
    models = _load("backend.models")
    director = _load("backend.director")

    for preset in shipped_presets.values():
        [form] = preset.modes["video"].forms
        fields = {}
        bridge._describe_fields(form.fields, {"preset": preset.path, "_shared": str(SHARED_PRESETS)}, fields)
        options = models.resolution_options(fields)
        values = [option["value"] for option in options]

        assert {"832x480", "480x832", "960x544", "544x960", "1344x768"} <= set(values)
        assert fields["resolution"]["default"] == "832x480"
        assert director.draft_resolution(options, "832x480", aspect) == draft
        assert director.final_resolution(options, aspect) == final
        assert models.model_fields(fields) == (["model", "text_encoder", "video_vae", "audio_vae"], [])
        if preset.id == H3_12GB:
            assert {"sha256": WAN2GP_SHA256, "filename": WAN2GP_DIT} in fields["model"]["recommendations"]
