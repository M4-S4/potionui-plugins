import dataclasses
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from src.features.chat.context_builder import ChatContextBuilder
from src.features.chat.modes.registry import ChatModeRegistry
from src.features.chat.tool_dispatcher import ToolCallDispatcher
from src.features.llm.tools.base import serialize_approval_preview
from src.features.llm.tools.executor import ToolExecutor
from src.features.llm.tools.registry import ToolRegistry
from src.features.notifications.types import NotificationTypeRegistry
from src.features.plans.guard import LimitGuard, PlanSettings
from src.features.plans.records import Plan, PlanLimit, PlanSubject
from src.features.plugins.setup import PluginSetup
from src.platform.plugins.limit_kinds import AdmissionRequest, LimitKindRegistry
from src.platform.plugins.loader import EXTRA_PLUGIN_DIRS_ENV, PluginLoader
from src.platform.plugins.registry import PluginRegistry
from src.plugin_api import HookContext, SetupCheck, get_current_active_user
from src.plugin_api.chat import ToolContext

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
MINIMAX_H3 = "01KX47H3MINIMAX000000000VA"
SETUP_LABELS = (
    "Enable a native backend or a cloud video model",
    "Install and assign at least one Video Director preset (Wan, MiniMax-H3, LTX or a cloud video preset)",
    "Install SeedVR2 for final takes",
    "Install ffmpeg for video delivery",
    "If a MiniMax-H3 preset is installed, install its five model files (DiT, text encoder, video VAE, audio VAE, "
    "and the latent upscaler of its Upscale mode)",
)


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
    assert len(created) == 8


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
        ("GET", f"{base}/projects/{{project_id}}/exports"),
        ("GET", f"{base}/projects/{{project_id}}/exports/{{fmt}}"),
        ("POST", f"{base}/projects/{{project_id}}/exports/video"),
        ("GET", f"{base}/exports/{{job_id}}"),
        ("GET", f"{base}/exports/{{job_id}}/file"),
        ("DELETE", f"{base}/exports/{{job_id}}"),
        ("POST", f"{base}/projects/{{project_id}}/shots/{{shot_id}}/seam-frame"),
        ("POST", f"{base}/projects/{{project_id}}/scenes/from-image"),
        ("GET", f"{base}/projects/{{project_id}}/scenes/jobs"),
        ("POST", f"{base}/projects/{{project_id}}/scenes/jobs/{{job_id}}/cancel"),
        ("POST", f"{base}/projects/{{project_id}}/scene-files"),
        ("GET", f"{base}/projects/{{project_id}}/scene-files/{{file_id}}"),
        ("POST", f"{base}/projects/{{project_id}}/captures"),
        ("POST", f"{base}/projects/{{project_id}}/renders"),
        ("POST", f"{base}/projects/{{project_id}}/renders/{{render_id}}/frames"),
        ("POST", f"{base}/projects/{{project_id}}/renders/{{render_id}}/finish"),
        ("DELETE", f"{base}/projects/{{project_id}}/renders/{{render_id}}"),
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


CHAT_MODE = "video-producer"
CHAT_TOOLS = {
    "vp_write_shot_prompt": ("WriteShotPromptTool", True),
    "vp_fix_conflicts": ("FixConflictsTool", True),
    "vp_split_synopsis": ("SplitSynopsisTool", True),
    "vp_check_continuity": ("CheckContinuityTool", False),
}


@pytest.fixture
def chat(manifest, tmp_path):
    tools, modes = ToolRegistry(), ChatModeRegistry()
    plugins = PluginRegistry(
        marketplace_dir=str(PLUGIN_ROOT.parent),
        local_dir=str(tmp_path / "local"),
        tool_registry=tools,
        chat_mode_registry=modes,
    )
    assert plugins._register_plugin_tools(manifest) is None
    assert plugins._register_plugin_chat_modes(manifest) is None
    return SimpleNamespace(tools=tools, modes=modes, plugins=plugins)


def test_the_manifest_declares_the_assistant_mode_and_its_four_tools(manifest):
    [mode] = manifest.chat_modes

    assert (mode["id"], mode["name"], mode["icon"]) == (CHAT_MODE, "Video Producer assistant", "film")
    assert mode["description"]
    assert mode["default_route_prefixes"] == [f"/plugins/{PLUGIN_ID}"]
    assert mode["tools"] == list(CHAT_TOOLS)
    assert mode["context_contributor"] == "backend.chat.context.build_context"
    assert mode["system_prompt_file"] is None and "{{TOOL_HINTS}}" in mode["system_prompt"]
    assert mode["admin_only"] is False
    assert [(tool["class"], tool["modes"]) for tool in manifest.tools] == [
        (f"backend.chat.tools:{class_name}", [CHAT_MODE]) for class_name, _ in CHAT_TOOLS.values()
    ]


def test_the_cores_registration_loads_the_four_tools_inside_the_plugin_package(chat):
    registered = {tool.name: tool for tool in chat.tools.get_all()}

    assert list(registered) == list(CHAT_TOOLS)
    assert all(name.startswith("vp_") for name in registered)
    for name, (class_name, approval) in CHAT_TOOLS.items():
        tool = registered[name]
        assert (type(tool).__name__, type(tool).__module__) == (class_name, f"{PACKAGE}.backend.chat.tools")
        assert tool.requires_approval is approval
        assert tool.modes == [CHAT_MODE]
        assert chat.tools.source_of(name) == PLUGIN_ID
        assert tool.hint and tool.description and tool.to_schema()["function"]["name"] == name


def test_the_tools_are_offered_only_in_the_assistant_mode(chat):
    mode = chat.modes.require(CHAT_MODE)

    assert [tool.name for tool in chat.tools.get_for_mode(mode)] == list(CHAT_TOOLS)
    assert chat.tools.get_for_mode(SimpleNamespace(id="generation", tool_names=[])) == []


def test_the_mode_loaded_by_the_core_resolves_its_prompt_and_its_context(chat):
    mode = chat.modes.require(CHAT_MODE)
    context = sys.modules[f"{PACKAGE}.backend.chat.context"]

    assert (mode.source, mode.icon, mode.default_route_prefixes, mode.admin_only) == (
        PLUGIN_ID,
        "film",
        [f"/plugins/{PLUGIN_ID}"],
        False,
    )
    assert mode.tool_names == list(CHAT_TOOLS)
    assert mode.context_contributor is context.build_context
    hints = "\n".join(f"- {tool.name}: {tool.hint}" for tool in chat.tools.get_for_mode(mode))
    prompt = chat.modes.resolve_system_prompt(mode, hints, list(CHAT_TOOLS))
    assert "{{TOOL_HINTS}}" not in prompt
    assert all(f"- {name}: " in prompt for name in CHAT_TOOLS)
    assert "prompt language" in prompt and "the user approves" in prompt
    assert mode.context_contributor({}, None, "user-1") == context.NOT_OPEN
    block = mode.context_contributor(
        {"video_producer": {"projectId": "p-1", "name": "Night ride", "projectVersion": 3, "promptLanguage": "fr"}}, None, "user-1"
    )
    assert block.splitlines()[:2] == [
        'VIDEO PRODUCER: project "Night ride" [p-1], saved version 3.',
        "Prompt language: fr. Write every shot instruction in French; never translate what the user wrote.",
    ]


async def test_the_tools_loaded_by_the_core_write_and_check_a_stored_project(loader, manifest, mock_db, chat):
    _boot(loader, manifest)
    projects = sys.modules[f"{PACKAGE}.backend.projects"]
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    created = projects.create_project("user-1", starter)
    shot_id = created["doc"]["clips"][1]["id"]
    owner = ToolContext(user_id="user-1", mode_id=CHAT_MODE, session_metadata={"video_producer": {"projectId": created["id"]}})
    stranger = ToolContext(user_id="user-2", mode_id=CHAT_MODE, session_metadata={"video_producer": {"projectId": created["id"]}})
    write, check = chat.tools.get("vp_write_shot_prompt"), chat.tools.get("vp_check_continuity")

    preview = await write.execute(owner, shot_id=shot_id, text="Low angle on the gate")
    confirmed = await write.execute_confirmed(owner, shot_id=shot_id, text="Low angle on the gate")
    checked = await check.execute(owner)
    refused = await write.execute_confirmed(stranger, shot_id=shot_id, text="Not mine")

    assert preview.success and preview.preview.kind == "text_edit" and preview.preview.text_blocks[0]["text"] == "Low angle on the gate"
    written = json.loads(confirmed.data)
    stored = projects.get_project(created["id"])
    assert (written["project_id"], written["shot_id"], written["version"]) == (created["id"], shot_id, 2)
    assert next(prompt for prompt in stored["doc"]["prompts"] if prompt["id"] == written["prompt_id"])["text"] == "Low angle on the gate"
    assert json.loads(checked.data)["project_id"] == created["id"]
    assert (refused.success, refused.error.split(":")[0]) == (False, "project_not_found")
    assert projects.get_project(created["id"])["version"] == 2


def test_the_parameters_of_the_four_tools_are_valid_json_schemas_the_model_can_follow(chat):
    for tool in chat.tools.get_all():
        Draft202012Validator.check_schema(tool.parameters)
        function = tool.to_schema()["function"]
        assert function["name"] == tool.name and function["description"] == tool.description
        assert function["parameters"] == tool.parameters
        assert tool.parameters["type"] == "object" and set(tool.parameters["required"]) <= set(tool.parameters["properties"])
    assert chat.tools.get("vp_check_continuity").parameters["properties"] == {}


def test_every_tool_of_the_manifest_belongs_to_a_declared_mode_and_every_mode_tool_to_the_plugin(manifest, chat):
    [mode] = manifest.chat_modes
    owned = {tool.name for tool in chat.tools.get_all()}

    assert {mode_id for tool in manifest.tools for mode_id in tool["modes"]} == {mode["id"]}
    assert set(mode["tools"]) == owned
    assert len(owned) == len(manifest.tools) == 4
    assert all(chat.tools.source_of(name) == PLUGIN_ID for name in owned)


def test_the_context_contributor_named_by_the_manifest_is_importable_and_is_the_one_the_core_calls(manifest, chat):
    [mode] = manifest.chat_modes
    module_name, function_name = mode["context_contributor"].rsplit(".", 1)
    contributor = getattr(importlib.import_module(f"{PACKAGE}.{module_name}"), function_name)

    assert callable(contributor) and chat.modes.require(CHAT_MODE).context_contributor is contributor
    assert list(inspect.signature(contributor).parameters) == ["context_metadata", "session", "user_id"]
    assert isinstance(contributor(None, None, "user-1"), str) and contributor(None, None, "user-1")
    assert contributor({"video_producer": {"projectId": "p-1"}}, SimpleNamespace(mode=CHAT_MODE), "user-1").startswith("VIDEO PRODUCER: project")


async def test_the_core_folds_the_contributors_block_into_the_users_turn_and_nothing_else(chat):
    builder = ChatContextBuilder(SimpleNamespace(chat_mode_registry=chat.modes))
    history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}, {"role": "user", "content": "Check the cuts"}]
    page = {"projectId": "p-1", "name": "Night ride", "projectVersion": 4, "promptLanguage": "fr", "shots": [{"id": "s1", "label": "Arrival", "start": 0, "dur": 4}]}

    await builder.inject_contributor_block(history, SimpleNamespace(mode=CHAT_MODE), {"video_producer": page}, "user-1")

    assert history[:2] == [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
    assert history[2]["content"].startswith('Check the cuts\n\n<context>\nVIDEO PRODUCER: project "Night ride" [p-1], saved version 4.')
    assert history[2]["content"].endswith("</context>")
    assert '1. [s1] "Arrival" 0–4 s' in history[2]["content"] and len(history) == 3


async def test_a_turn_without_the_page_context_still_gets_a_block_that_says_so(chat):
    builder = ChatContextBuilder(SimpleNamespace(chat_mode_registry=chat.modes))
    history = [{"role": "user", "content": "Write the prompt of shot 1"}]

    await builder.inject_contributor_block(history, SimpleNamespace(mode=CHAT_MODE), None, "user-1")

    assert "the page is not open" in history[0]["content"]


async def test_the_core_runs_the_three_writing_tools_for_approval_and_the_check_straight_away(loader, manifest, mock_db, chat):
    _boot(loader, manifest)
    projects = sys.modules[f"{PACKAGE}.backend.projects"]
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    created = projects.create_project("user-1", starter)
    shot_id = created["doc"]["clips"][0]["id"]
    owner = ToolContext(user_id="user-1", mode_id=CHAT_MODE, session_metadata={"video_producer": {"projectId": created["id"]}})
    executor = ToolExecutor(chat.tools, SimpleNamespace())
    calls = {
        "vp_write_shot_prompt": {"shot_id": shot_id, "text": "Low angle on the gate"},
        "vp_fix_conflicts": {"rewrites": [{"shot_id": shot_id, "text": "Low angle on the gate"}]},
        "vp_split_synopsis": {"shots": [{"label": "Gate", "prompt": "Low angle on the gate", "duration_s": 4}]},
        "vp_check_continuity": {},
    }

    outcome = {name: await executor._execute_tool(name, owner, arguments) for name, arguments in calls.items()}

    assert {name: pending for name, (result, pending) in outcome.items()} == {name: approval for name, (_, approval) in CHAT_TOOLS.items()}
    assert all(result.success for result, _ in outcome.values())
    assert projects.get_project(created["id"])["version"] == 1
    kinds = {name: result.preview.kind if result.preview else None for name, (result, _) in outcome.items()}
    assert kinds == {"vp_write_shot_prompt": "text_edit", "vp_fix_conflicts": "text_edit", "vp_split_synopsis": "timeline", "vp_check_continuity": None}
    for name in ("vp_write_shot_prompt", "vp_fix_conflicts", "vp_split_synopsis"):
        card = serialize_approval_preview(outcome[name][0].preview)
        assert json.loads(json.dumps(card)) == card
        assert card["action"] and card["target"] and card["summary"] and (card["text_blocks"] or card["rows"])

    refused = await executor.execute_tool_confirmed("vp_check_continuity", owner, {})
    assert not refused.success and "does not require approval" in refused.error
    applied = await executor.execute_tool_confirmed("vp_write_shot_prompt", owner, calls["vp_write_shot_prompt"])
    assert applied.success and json.loads(applied.data)["version"] == 2
    outside, _ = await executor._execute_tool("vp_write_shot_prompt", owner, calls["vp_write_shot_prompt"], allowed_tools=["vp_check_continuity"])
    assert not outside.success and "not enabled for this session" in outside.error


async def test_the_core_reports_the_plugins_error_codes_untouched_for_a_model_that_misuses_the_tools(loader, manifest, mock_db, chat):
    _boot(loader, manifest)
    projects = sys.modules[f"{PACKAGE}.backend.projects"]
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    created = projects.create_project("user-1", starter)
    owner = ToolContext(user_id="user-1", mode_id=CHAT_MODE, session_metadata={"video_producer": {"projectId": created["id"]}})
    nowhere = ToolContext(user_id="user-1", mode_id=CHAT_MODE, session_metadata={})
    executor = ToolExecutor(chat.tools, SimpleNamespace())

    misuse = {
        ("vp_write_shot_prompt", "shot_id"): (owner, {"shot_id": 3, "text": "x"}, "invalid_arguments"),
        ("vp_write_shot_prompt", "shot"): (owner, {"shot_id": "nope", "text": "x"}, "shot_not_found"),
        ("vp_fix_conflicts", "empty"): (owner, {"rewrites": []}, "invalid_arguments"),
        ("vp_split_synopsis", "duration"): (owner, {"shots": [{"label": "A", "prompt": "x", "duration_s": 99}]}, "invalid_arguments"),
        ("vp_check_continuity", "page"): (nowhere, {}, "project_not_found"),
        ("vp_split_synopsis", "page"): (nowhere, {"shots": [{"label": "A", "prompt": "x", "duration_s": 4}]}, "project_not_found"),
    }

    for (name, _), (context, arguments, code) in misuse.items():
        result, pending = await executor._execute_tool(name, context, arguments)
        assert (result.success, pending, result.data, result.error.split(":", 1)[0]) == (False, False, "", code)
    confirmed = await executor.execute_tool_confirmed("vp_fix_conflicts", nowhere, {"rewrites": [{"shot_id": "a", "text": "x"}]})
    assert (confirmed.success, confirmed.error.split(":", 1)[0]) == (False, "project_not_found")
    assert projects.get_project(created["id"])["version"] == 1


async def _stale_after_an_edit(chat, tool_name, arguments, edit):
    projects = sys.modules[f"{PACKAGE}.backend.projects"]
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    created = projects.create_project("user-1", starter)
    shot_id = created["doc"]["clips"][0]["id"]
    owner = ToolContext(user_id="user-1", mode_id=CHAT_MODE, session_metadata={"video_producer": {"projectId": created["id"]}})
    executor = ToolExecutor(chat.tools, SimpleNamespace())
    dispatcher = ToolCallDispatcher(SimpleNamespace(tool_executor=executor))
    arguments = arguments(shot_id)
    result, _ = await executor._execute_tool(tool_name, owner, arguments)
    execution = {"tool_name": tool_name, "arguments": arguments, "preview": serialize_approval_preview(result.preview)}

    before = await dispatcher._is_stale(execution, owner)
    doc = projects.get_project(created["id"])["doc"]
    edit(doc, shot_id)
    projects.save_project(created["id"], doc, 1)
    return before, await dispatcher._is_stale(execution, owner)


def _retype_prompt(doc, shot_id):
    next(prompt for prompt in doc["prompts"] if prompt["shotId"] == shot_id)["text"] = "Typed by the user while the card was open"


async def test_the_core_flags_a_fix_as_stale_when_a_prompt_changed_after_its_preview(loader, manifest, mock_db, chat):
    _boot(loader, manifest)

    before, after = await _stale_after_an_edit(
        chat, "vp_fix_conflicts", lambda shot_id: {"rewrites": [{"shot_id": shot_id, "text": "Steady wide shot"}]}, _retype_prompt
    )

    assert (before, after) == (False, True)


async def test_the_core_flags_a_write_as_stale_when_the_prompt_changed_after_its_preview(loader, manifest, mock_db, chat):
    _boot(loader, manifest)

    before, after = await _stale_after_an_edit(
        chat, "vp_write_shot_prompt", lambda shot_id: {"shot_id": shot_id, "text": "Steady wide shot"}, _retype_prompt
    )

    assert (before, after) == (False, True)


def test_disabling_the_plugin_takes_its_mode_and_its_tools_away_from_the_core(chat):
    assert chat.modes.get(CHAT_MODE) is not None and len(chat.tools.get_all()) == 4

    chat.plugins._unregister_chat_extensions(PLUGIN_ID)

    assert chat.modes.get(CHAT_MODE) is None
    assert chat.tools.get_all() == [] and chat.tools.get("vp_write_shot_prompt") is None


def test_the_mode_cannot_be_registered_twice_and_leaves_the_first_one_in_place(manifest, chat):
    assert "already registered" in (chat.plugins._register_plugin_chat_modes(manifest) or "")

    assert chat.modes.require(CHAT_MODE).source == PLUGIN_ID and len(chat.modes.get_all()) == 1


def test_notification_type_register_declares_the_plugins_types_on_the_cores_registry(loader, manifest):
    register = _handler(loader, manifest, "notification_type.register")
    registry = NotificationTypeRegistry()
    context = HookContext(hook_name="notification_type.register", plugin_id="system", data={"registry": registry})

    assert register(context) is context
    assert register(context) is context

    assert [spec.key for spec in registry.all()] == [
        "video-producer.take_done",
        "video-producer.take_failed",
        "video-producer.export_done",
        "video-producer.export_failed",
    ]
    assert [item.key for item in _load("backend.notifications").TYPES] == [spec.key for spec in registry.all()]
    for spec in registry.all():
        assert spec.label.startswith("Video Producer: ") and spec.description
        assert (spec.category, spec.default_enabled, spec.admin_only) == ("plugin", True, False)


def test_the_export_notification_types_reach_the_cores_registry(loader, manifest):
    register = _handler(loader, manifest, "notification_type.register")
    registry = NotificationTypeRegistry()

    register(HookContext(hook_name="notification_type.register", plugin_id="system", data={"registry": registry}))

    for key, label in (
        ("video-producer.export_done", "Video Producer: export ready"),
        ("video-producer.export_failed", "Video Producer: export failed"),
    ):
        spec = registry.get(key)
        assert (spec.label, spec.category, spec.default_enabled, spec.admin_only) == (label, "plugin", True, False)
        assert spec.description
    notifications = _load("backend.notifications")
    assert (notifications.EXPORT_DONE, notifications.EXPORT_FAILED) == ("video-producer.export_done", "video-producer.export_failed")


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
    assert tuple(step["label"] for step in manifest.setup) == SETUP_LABELS
    for step in manifest.setup:
        check_class = loader.load_class(manifest, step["check"])

        assert check_class is not None, f"{step['check']} did not load (see the log above)"
        assert issubclass(check_class, SetupCheck)
        assert check_class.__module__ == "video_producer.backend.setup_checks"
        assert check_class.__name__ == step["check"].split(":")[1]
        assert step["label"]
        assert isinstance(check_class(), SetupCheck)


def test_the_ffmpeg_setup_check_loads_through_the_core_and_reads_the_hosts_ffmpeg(loader, manifest, monkeypatch):
    step = next(step for step in manifest.setup if step["check"] == "backend.setup_checks:FfmpegReady")
    check_class = loader.load_class(manifest, step["check"])
    bridge = sys.modules["video_producer.backend.core_bridge"]

    assert step["label"] == "Install ffmpeg for video delivery"
    assert check_class.__module__ == "video_producer.backend.setup_checks" and issubclass(check_class, SetupCheck)
    monkeypatch.setattr(bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe")
    assert check_class().evaluate(SimpleNamespace()).done is True
    monkeypatch.setattr(bridge, "find_ffmpeg", lambda: None)
    monkeypatch.setattr(bridge, "find_ffprobe", lambda: None)
    missing = check_class().evaluate(SimpleNamespace())
    assert missing.done is False and "ffmpeg" in missing.description and missing.action_label == "Read the guide"


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
    monkeypatch.setattr(bridge, "find_ffprobe", lambda: ffmpeg and ffmpeg.replace("ffmpeg", "ffprobe"))


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


def test_the_core_setup_report_shows_every_step_still_to_do_with_its_link(loader, manifest, monkeypatch):
    bridge = _bridge(loader, manifest)
    states = {
        WAN: bridge.PresetState(id=WAN, name="Wan", loaded=True, installed=True, assigned=False),
        SEEDVR2: bridge.PresetState(id=SEEDVR2, name="SeedVR2", loaded=True, installed=False, assigned=False),
        MINIMAX_H3: bridge.PresetState(id=MINIMAX_H3, name="MiniMax-H3", loaded=True, installed=True, assigned=False),
    }
    _fake_host(monkeypatch, bridge, backends=[], states=states, ffmpeg=None)
    monkeypatch.setattr(bridge, "preset_model_hashes", lambda preset_id, names, modes=None: {name: {f"{name}-sha"} for name in names})
    monkeypatch.setattr(bridge, "describe_preset", lambda preset_id: None)

    report = _setup(loader, manifest).report(manifest)

    assert (report.complete, report.remaining) == (False, 5)
    assert [step.label for step in report.steps] == list(SETUP_LABELS)
    assert [step.status for step in report.steps] == ["todo"] * 5
    assert [(step.action.kind, step.action.label, step.action.href) for step in report.steps] == [
        ("link", "Open backends", "/admin?tab=backends"),
        ("link", "Assign presets", f"/admin?tab=presets&id={WAN}"),
        ("link", "Open SeedVR2", f"/admin?tab=presets&id={SEEDVR2}"),
        ("link", "Read the guide", report.guide.href),
        ("link", "Open MiniMax-H3", f"/admin?tab=presets&id={MINIMAX_H3}"),
    ]
    assert report.steps[4].description.startswith("MiniMax-H3 is missing its DiT, text encoder, video VAE, audio VAE and latent upscaler.")


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


def test_the_export_routes_loaded_by_the_core_answer_a_file_and_refuse_a_video_without_ffmpeg(loader, manifest, mock_db, monkeypatch):
    _boot(loader, manifest)
    app = _app(loader, manifest, {"user": _user("user-1")})
    bridge = sys.modules[f"{PACKAGE}.backend.core_bridge"]
    monkeypatch.setattr(bridge, "find_ffmpeg", lambda: None)
    starter = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "starter_doc.json").read_text(encoding="utf-8"))
    base = f"/api/plugins/{PLUGIN_ID}"

    with TestClient(app) as client:
        project_id = client.post(f"{base}/projects", json={"doc": {**starter, "name": "Aube sur le port"}}).json()["data"]["project"]["id"]
        edl = client.get(f"{base}/projects/{project_id}/exports/edl", params={"media": "name"})
        srt = client.get(f"{base}/projects/{project_id}/exports/srt")
        refused = client.post(f"{base}/projects/{project_id}/exports/video", json={"format": "web"})
        listed = client.get(f"{base}/projects/{project_id}/exports")

    assert edl.status_code == 200 and edl.headers["content-type"] == "text/plain; charset=utf-8"
    assert edl.headers["content-disposition"].startswith('attachment; filename="Aube_sur_le_port.edl"')
    assert edl.text.startswith("TITLE: AUBE SUR LE PORT\r\nFCM: NON-DROP FRAME\r\n")
    assert srt.status_code == 200 and srt.headers["content-type"] == "application/x-subrip"
    assert refused.status_code == 409 and refused.json()["detail"]["error"] == "ffmpeg_unavailable"
    assert listed.json() == {"success": True, "data": {"jobs": []}}


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
WAN_1_3B_8GB = "01M57QPEMDPKHHW83YSEYBN0WZ"
WAN_5B_8GB = "01M57QPEMDPKHHW83YSEYBN0X0"
WAN_LIGHTNING_12GB = "01M57QPEMDPKHHW83YSEYBN0X1"
MINIMAX_H3_FAST = "01KX47H3FASTH30000000000VA"
COMFY_DIT = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
WAN2GP_DIT = "MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors"
WAN2GP_SHA256 = "30ff400f974b11a1ef13d216c5d9f6439a9c10322a3988b0374a39672ce286f0"
FASTH3_DIT = "fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
UMT5 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN21_VAE = "wan_2.1_vae.safetensors"
WAN22_VAE = "wan2.2_vae.safetensors"
WAN_1_3B_DIT = "wan2.1_t2v_1.3B_fp16.safetensors"
WAN_5B_DIT = "wan2.2_ti2v_5B_fp16.safetensors"
WAN_14B_HIGH_DIT = "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"
WAN_14B_LOW_DIT = "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"
LIGHTNING_HIGH_LORA = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors"
LIGHTNING_LOW_LORA = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"
WAN_HIDDEN_TABS = ("I2V Models", "SVI Pro")
H3_DEFAULTS = {"resolution": "832x480", "quantity": 1, "sampler": "res_multistep", "scheduler": "simple", "keyframe_pixel_budget": "1"}
WAN_DEFAULTS = {"seed": -1, "sampler": "unipc", "schedule": "shift", "steps": 30}


@dataclasses.dataclass(frozen=True)
class Shipped:
    name: str
    folder: str
    source_id: str
    source_folder: str
    min_vram_gb: int
    recommended_vram_gb: int
    ram_gb: Optional[int]
    family_tag: str
    fps_var: str
    fps: int
    frames: int
    description_mentions: Tuple[str, ...]
    changed_fields: Dict[str, Set[str]]
    defaults: Dict[str, Any]
    recommended: Dict[str, List[str]]
    hidden_tabs: Tuple[str, ...] = ()
    own_resolutions: Optional[Tuple[str, ...]] = None
    speed_options: Tuple[str, ...] = ()
    reacted: Dict[str, Any] = dataclasses.field(default_factory=dict)
    draft: Tuple[str, ...] = ()
    final: Tuple[str, ...] = ()
    modes: Tuple[str, ...] = ("video",)

    @property
    def is_wan(self):
        return self.family_tag == "wan"

    @property
    def requires(self):
        ram = {} if self.ram_gb is None else {"min_ram_gb": self.ram_gb}
        return {"min_vram_gb": self.min_vram_gb, "recommended_vram_gb": self.recommended_vram_gb, **ram}

    @property
    def profile(self):
        return f"{self.min_vram_gb} GB" + ("" if self.ram_gb is None else f" · {self.ram_gb} GB RAM")

    @property
    def ram_tags(self):
        return [] if self.ram_gb is None else [f"ram-{self.ram_gb}gb"]

    @property
    def leading_tags(self):
        return [f"{self.min_vram_gb}gb", "low-vram", *self.ram_tags, self.family_tag][:3]

    @property
    def profiles(self):
        return ["FL2VA"] if self.is_wan else ["FL2VA", *(["Ref2VA"] if "refs" in self.modes else []), "Hybrid AV"]

    @property
    def director_modes(self):
        return ["t2v"] if self.is_wan else ["t2v", "i2v", "flf", "director"]

    @property
    def max_duration(self):
        return 5 if self.is_wan else 15


SHIPPED_PRESETS = {
    WAN_1_3B_8GB: Shipped(
        name="Wan 2.1 T2V 1.3B (8 GB)",
        folder="Wan2.1-T2V-1.3B-8GB",
        source_id=WAN,
        source_folder="Wan",
        min_vram_gb=8,
        recommended_vram_gb=12,
        ram_gb=32,
        family_tag="wan",
        fps_var="default_fps",
        fps=16,
        frames=81,
        description_mentions=("8 GB of VRAM",),
        changed_fields={
            "speed_profile": {"configuration"},
            "resolution": {"configuration"},
            "text_encoder": {"configuration"},
            "vae": {"configuration"},
            "t2v_high_noise_model": {"configuration"},
            "t2v_low_noise_model": {"configuration"},
            "cfg": {"default", "reactions"},
        },
        defaults={**WAN_DEFAULTS, "speed_profile": "balanced", "resolution": "832x480", "fps": 16, "cfg": 6.0, "t2v_loras_high": [], "t2v_loras_low": []},
        recommended={"text_encoder": [UMT5], "vae": [WAN21_VAE], "t2v_high_noise_model": [WAN_1_3B_DIT], "t2v_low_noise_model": []},
        hidden_tabs=WAN_HIDDEN_TABS,
        own_resolutions=("832x480", "480x832", "640x480", "480x640"),
        speed_options=("balanced", "custom"),
        draft=("832x480", "480x832"),
        final=("832x480", "480x832"),
    ),
    WAN_5B_8GB: Shipped(
        name="Wan 2.2 TI2V 5B (8 GB)",
        folder="Wan2.2-TI2V-5B-8GB",
        source_id=WAN,
        source_folder="Wan",
        min_vram_gb=8,
        recommended_vram_gb=12,
        ram_gb=32,
        family_tag="wan",
        fps_var="default_fps",
        fps=24,
        frames=121,
        description_mentions=("8 GB of VRAM",),
        changed_fields={
            "speed_profile": {"configuration"},
            "resolution": {"configuration"},
            "fps": {"default"},
            "text_encoder": {"configuration"},
            "vae": {"configuration"},
            "t2v_high_noise_model": {"configuration"},
            "t2v_low_noise_model": {"configuration"},
        },
        defaults={**WAN_DEFAULTS, "speed_profile": "balanced", "resolution": "832x480", "fps": 24, "cfg": 5.0, "t2v_loras_high": [], "t2v_loras_low": []},
        recommended={"text_encoder": [UMT5], "vae": [WAN22_VAE], "t2v_high_noise_model": [WAN_5B_DIT], "t2v_low_noise_model": []},
        hidden_tabs=WAN_HIDDEN_TABS,
        own_resolutions=("832x480", "480x832"),
        speed_options=("balanced", "custom"),
        draft=("832x480", "480x832"),
        final=("832x480", "480x832"),
    ),
    WAN_LIGHTNING_12GB: Shipped(
        name="Wan 2.2 14B Lightning (12 GB)",
        folder="Wan2.2-14B-Lightning-12GB",
        source_id=WAN,
        source_folder="Wan",
        min_vram_gb=12,
        recommended_vram_gb=16,
        ram_gb=64,
        family_tag="wan",
        fps_var="default_fps",
        fps=16,
        frames=81,
        description_mentions=("12 GB of VRAM",),
        changed_fields={
            "speed_profile": {"configuration", "default"},
            "text_encoder": {"configuration"},
            "vae": {"configuration"},
            "t2v_high_noise_model": {"configuration"},
            "t2v_low_noise_model": {"configuration"},
            "t2v_loras_high": {"default"},
            "t2v_loras_low": {"default"},
        },
        defaults={
            **WAN_DEFAULTS,
            "speed_profile": "fast",
            "resolution": "832x480",
            "fps": 16,
            "cfg": 5.0,
            "t2v_loras_high": [{"model": f"models/loras/{LIGHTNING_HIGH_LORA}", "strength": 1.0}],
            "t2v_loras_low": [{"model": f"models/loras/{LIGHTNING_LOW_LORA}", "strength": 1.0}],
        },
        recommended={
            "text_encoder": [UMT5],
            "vae": [WAN21_VAE],
            "t2v_high_noise_model": [WAN_14B_HIGH_DIT],
            "t2v_low_noise_model": [WAN_14B_LOW_DIT],
        },
        hidden_tabs=WAN_HIDDEN_TABS,
        speed_options=("fast", "custom"),
        reacted={"steps": 6, "cfg": 1.0},
        draft=("832x480", "480x832"),
        final=("1280x720", "720x1280"),
    ),
    H3_12GB: Shipped(
        name="MiniMax-H3 (12 GB)",
        folder="MiniMax-H3-12GB",
        source_id=MINIMAX_H3,
        source_folder="MiniMax-H3",
        min_vram_gb=12,
        recommended_vram_gb=12,
        ram_gb=64,
        family_tag="minimax",
        fps_var="fps",
        fps=24,
        frames=124,
        description_mentions=("12 GB", "64 GB"),
        changed_fields={
            "speed_profile": {"default"},
            "resolution": {"default", "configuration"},
            "model": {"configuration"},
            "text_encoder": {"configuration"},
            "video_vae": {"configuration"},
            "keyframe_pixel_budget": {"default"},
            "steps": {"default"},
            "sampler": {"default", "ai_hint"},
        },
        defaults={**H3_DEFAULTS, "speed_profile": "custom", "steps": 20},
        recommended={"model": [COMFY_DIT, WAN2GP_DIT], "text_encoder": [TEXT_ENCODER], "video_vae": [VIDEO_VAE], "audio_vae": [AUDIO_VAE]},
        modes=("video", "refs"),
    ),
    H3_FAST_12GB: Shipped(
        name="MiniMax-H3-Fast (12 GB)",
        folder="MiniMax-H3-Fast-12GB",
        source_id=MINIMAX_H3_FAST,
        source_folder="MiniMax-H3-Fast",
        min_vram_gb=12,
        recommended_vram_gb=12,
        ram_gb=64,
        family_tag="minimax",
        fps_var="fps",
        fps=24,
        frames=124,
        description_mentions=("12 GB", "64 GB"),
        changed_fields={
            "resolution": {"default", "configuration"},
            "model": {"configuration"},
            "text_encoder": {"configuration"},
            "video_vae": {"configuration", "ai_hint"},
            "keyframe_pixel_budget": {"default"},
        },
        defaults={**H3_DEFAULTS, "speed_profile": "distilled", "steps": 8},
        recommended={"model": [FASTH3_DIT], "text_encoder": [TEXT_ENCODER], "video_vae": [VIDEO_VAE], "audio_vae": [AUDIO_VAE]},
    ),
}
H3_PRESETS = {preset_id: shipped for preset_id, shipped in SHIPPED_PRESETS.items() if not shipped.is_wan}
WAN_PRESETS = {preset_id: shipped for preset_id, shipped in SHIPPED_PRESETS.items() if shipped.is_wan}


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
def core_presets():
    roots = sorted({CORE_PRESETS / shipped.source_folder for shipped in SHIPPED_PRESETS.values()})
    loader, loaded = _preset_loader(roots)
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


def _video_form(preset, mode="video"):
    [form] = preset.modes[mode].forms
    return _flatten(form.fields, {}, [])


def _all_fields(fields):
    found = []
    for field in fields:
        found.append(field)
        if isinstance(field.children, list):
            found += _all_fields(field.children)
    return found


def _video_fields(preset):
    [form] = preset.modes["video"].forms
    return _all_fields(form.fields)


def _option_files(preset, field):
    from src.features.presets.children_paths import resolve_children_path

    return [
        (resolve_children_path(entry["path"], Path(preset.path), SHARED_PRESETS).resolve(), entry["group"])
        for entry in field.configuration["files"]
    ]


def _recommendations(field):
    return (field.configuration or {}).get("recommendations") or []


def test_the_manifest_declares_the_presets_folder(manifest):
    assert manifest.presets == [{"path": "presets"}]


def test_the_shipped_presets_load_through_the_cores_loader(shipped_presets):
    assert {preset_id: preset.name for preset_id, preset in shipped_presets.items()} == {
        preset_id: shipped.name for preset_id, shipped in SHIPPED_PRESETS.items()
    }
    for preset_id, shipped in SHIPPED_PRESETS.items():
        preset = shipped_presets[preset_id]
        assert preset.origin == {"kind": "plugin", "plugin_id": PLUGIN_ID, "path": shipped.folder}
        assert (preset.engine, preset.category, list(preset.modes)) == ("native", "video", list(shipped.modes))
        assert preset.requires == shipped.requires, preset_id
        assert preset.tags[:3] == shipped.leading_tags, preset_id
        assert [tag for tag in preset.tags if tag.startswith("ram-")] == shipped.ram_tags, preset_id
        assert preset.vars["video_producer"] == {"profile": shipped.profile}, preset_id
        assert (preset.vars[shipped.fps_var], preset.vars["default_frames"]) == (shipped.fps, shipped.frames), preset_id
        for text in shipped.description_mentions:
            assert text in preset.description, (preset_id, text)


def test_the_backend_knows_the_shipped_presets_and_reads_their_profile(shipped_presets):
    presets = _load("backend.presets")
    catalog = _load("backend.catalog")

    assert (presets.WAN21_T2V_1_3B_8GB, presets.WAN22_TI2V_5B_8GB, presets.WAN22_14B_LIGHTNING_12GB) == (
        WAN_1_3B_8GB,
        WAN_5B_8GB,
        WAN_LIGHTNING_12GB,
    )
    assert set(presets.WAN_TIER_PRESETS) == set(WAN_PRESETS)
    for preset_id, shipped in SHIPPED_PRESETS.items():
        preset = shipped_presets[preset_id]
        assert preset_id in presets.VIDEO_DIRECTOR_PRESETS
        assert (preset_id in presets.WAN_TIER_PRESETS, preset_id in presets.MINIMAX_H3_PRESETS) == (shipped.is_wan, not shipped.is_wan)
        assert catalog.memory_profile(preset.vars) == shipped.profile
        assert catalog.main_mode(preset.vars, list(preset.modes)) == "video"
        assert catalog.profiles(preset_id, preset.vars, list(preset.modes)) == shipped.profiles
        assert catalog.director_modes(preset.vars) == shipped.director_modes
        assert catalog.preset_limits(preset.vars)["max_duration"] == shipped.max_duration
        assert catalog.preset_fps(preset.vars) == shipped.fps


def test_the_shipped_h3_presets_keep_the_director_and_prompt_help_of_the_core_presets(shipped_presets, core_presets):
    for preset_id, shipped in H3_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_presets[shipped.source_id]
        assert preset.vars["video_director"] == source.vars["video_director"]
        assert preset.vars["prompt"]["segment_templates"] == source.vars["prompt"]["segment_templates"][:1]
        assert preset.configuration == source.configuration
        guides = {mode: guide for mode, guide in source.llm.get("modes", {}).items() if mode in shipped.modes}
        assert preset.llm == {**{key: value for key, value in source.llm.items() if key != "modes"}, **({"modes": guides} if guides else {})}
        assert preset.prompt_syntax == {mode: source.prompt_syntax[mode] for mode in shipped.modes}
        assert preset.prompt_resources == {mode: entries for mode, entries in (source.prompt_resources or {}).items() if mode in shipped.modes}
        assert preset.formulas["groups"] == {name: group for name, group in source.formulas["groups"].items() if name != "memory"}


def test_the_shipped_wan_presets_keep_the_prompt_help_of_the_core_preset_and_generate_from_text_only(shipped_presets, core_presets):
    own_vars = ("video_director", "video_producer", "default_fps", "default_frames")
    for preset_id, shipped in WAN_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_presets[shipped.source_id]
        director = preset.vars["video_director"]
        limits = {"default_duration": 5, "default_fps": shipped.fps, "max_duration": 5}
        assert director == {**source.vars["video_director"], "modes": {"t2v": {}}, "limits": limits}, preset_id
        assert {key for key, value in director.items() if value != source.vars["video_director"].get(key)} == {"modes", "limits"}, preset_id
        assert set(preset.vars) == set(own_vars), preset_id
        assert {key: value for key, value in preset.vars.items() if key not in own_vars} == {
            key: value for key, value in source.vars.items() if key not in own_vars
        }
        assert preset.configuration == source.configuration, preset_id
        assert preset.llm == source.llm, preset_id
        assert preset.prompt_syntax == source.prompt_syntax, preset_id
        assert preset.formulas == source.formulas, preset_id
        assert preset.formulas["groups"] == source.formulas["groups"], preset_id
        assert preset.negative_prompt == source.negative_prompt, preset_id


def test_the_shipped_presets_run_the_core_pipelines_unchanged(shipped_presets, core_presets):
    for preset_id, shipped in SHIPPED_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_presets[shipped.source_id]
        for mode in shipped.modes:
            assert preset.modes[mode].pipes == source.modes[mode].pipes, (preset_id, mode)
            copy = yaml.safe_load((PLUGIN_ROOT / "presets" / shipped.folder / "modes" / mode / "pipeline.yml").read_text(encoding="utf-8"))
            original = yaml.safe_load((Path(source.path) / "modes" / mode / "pipeline.yml").read_text(encoding="utf-8"))
            assert copy == original, (preset_id, mode)


def test_the_shipped_forms_change_only_the_tier_defaults_models_and_files_of_the_core_forms(shipped_presets, core_presets):
    for preset_id, shipped in SHIPPED_PRESETS.items():
        preset, source = shipped_presets[preset_id], core_presets[shipped.source_id]
        named, skeleton = _video_form(preset)
        source_named, source_skeleton = _video_form(source)
        assert skeleton == source_skeleton, preset_id
        assert [field.label for field in _video_fields(preset) if field.visible is False] == list(shipped.hidden_tabs), preset_id
        for name, field in named.items():
            changed = shipped.changed_fields.get(name, set())
            assert field == dataclasses.replace(source_named[name], **{attr: getattr(field, attr) for attr in changed}), (preset_id, name)
        for mine, theirs in zip(_video_fields(preset), _video_fields(source)):
            if not mine.name:
                hidden = {"visible": False} if mine.type == "tab" and mine.label in shipped.hidden_tabs else {}
                assert dataclasses.replace(mine, children=None) == dataclasses.replace(theirs, children=None, **hidden), (preset_id, mine.label)
        assert {name: named[name].default for name in shipped.defaults} == shipped.defaults, preset_id
        if not shipped.is_wan:
            assert preset.speed_profiles[named["speed_profile"].default]["steps"] == named["steps"].default, preset_id
        if shipped.own_resolutions is None:
            assert _option_files(preset, named["resolution"]) == _option_files(source, source_named["resolution"]), preset_id
        else:
            files = _option_files(preset, named["resolution"])
            offered = [item["value"] for path, _ in files for item in yaml.safe_load(path.read_text(encoding="utf-8"))]
            assert all(Path(preset.path).resolve() in path.parents for path, _ in files), preset_id
            assert offered == list(shipped.own_resolutions), preset_id
        for name in shipped.recommended:
            mine = {key: value for key, value in named[name].configuration.items() if key not in ("recommendations", "placeholder")}
            theirs = {key: value for key, value in source_named[name].configuration.items() if key not in ("recommendations", "placeholder")}
            assert mine == theirs, (preset_id, name)
            assert all(len(item["sha256"]) == 64 for item in _recommendations(named[name])), (preset_id, name)
        assert {name: [item["name"] for item in _recommendations(named[name])] for name in shipped.recommended} == shipped.recommended, preset_id


COMFY_REF2VA_DIT = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
WAN2GP_REF2VA_DIT = "MiniMax-H3-Ref2VA-pruned_rank8_int8_convrot.safetensors"
WAN2GP_REF2VA_SHA256 = "e09db861c48d13560222948b4e38082bc21b1b7d4ddcaed9c865bf9c3233898c"
REFS_CHANGED_FIELDS = {
    "speed_profile": {"default"},
    "resolution": {"default", "configuration"},
    "model": {"configuration"},
    "text_encoder": {"configuration"},
    "video_vae": {"configuration"},
    "reference_pixel_budget": {"default"},
    "steps": {"default"},
    "sampler": {"default", "ai_hint"},
}
REFS_RECOMMENDED = {"model": [COMFY_REF2VA_DIT, WAN2GP_REF2VA_DIT], "text_encoder": [TEXT_ENCODER], "video_vae": [VIDEO_VAE], "audio_vae": [AUDIO_VAE]}


def test_the_12_gb_refs_form_changes_only_the_tier_defaults_models_and_files_of_the_core_refs_form(shipped_presets, core_presets):
    preset, source = shipped_presets[H3_12GB], core_presets[MINIMAX_H3]
    named, skeleton = _video_form(preset, "refs")
    source_named, source_skeleton = _video_form(source, "refs")

    assert skeleton == source_skeleton
    for name, field in named.items():
        changed = REFS_CHANGED_FIELDS.get(name, set())
        assert field == dataclasses.replace(source_named[name], **{attr: getattr(field, attr) for attr in changed}), name
    assert {name: named[name].default for name in ("resolution", "speed_profile", "steps", "sampler", "scheduler", "reference_pixel_budget", "quantity")} == {
        "resolution": "832x480",
        "speed_profile": "custom",
        "steps": 20,
        "sampler": "res_multistep",
        "scheduler": "simple",
        "reference_pixel_budget": "1",
        "quantity": 1,
    }
    assert preset.speed_profiles[named["speed_profile"].default]["steps"] == named["steps"].default
    assert _option_files(preset, named["resolution"]) == _option_files(source, source_named["resolution"])
    assert named["steps"] == _video_form(preset)[0]["steps"] and named["sampler"] == _video_form(preset)[0]["sampler"]
    assert {name: [item["name"] for item in _recommendations(named[name])] for name in REFS_RECOMMENDED} == REFS_RECOMMENDED
    for name in REFS_RECOMMENDED:
        mine = {key: value for key, value in named[name].configuration.items() if key not in ("recommendations", "placeholder")}
        theirs = {key: value for key, value in source_named[name].configuration.items() if key not in ("recommendations", "placeholder")}
        assert mine == theirs, name
    known = {item["name"]: item for field in [*source_named.values(), *_video_form(preset)[0].values()] for item in _recommendations(field)}
    for name in REFS_RECOMMENDED:
        for item in _recommendations(named[name]):
            assert len(item["sha256"]) == 64, item["name"]
            if item["name"] in known:
                assert {key: item[key] for key in ("link", "size", "sha256")} == {key: known[item["name"]][key] for key in ("link", "size", "sha256")}
    assert next(item for item in _recommendations(named["model"]) if item["name"] == WAN2GP_REF2VA_DIT)["sha256"] == WAN2GP_REF2VA_SHA256


def test_the_plugin_runs_ref2va_on_the_12_gb_preset_with_its_refs_models(shipped_presets):
    bridge = _load("backend.core_bridge")
    models = _load("backend.models")
    preset = shipped_presets[H3_12GB]
    [form] = preset.modes["refs"].forms
    fields = {}
    bridge._describe_fields(form.fields, {"preset": preset.path, "_shared": str(SHARED_PRESETS)}, fields)

    assert models.model_fields(fields, "refs") == (["model", "text_encoder", "video_vae", "audio_vae"], [])
    assert fields["resolution"]["default"] == "832x480"
    assert {"sha256": WAN2GP_REF2VA_SHA256, "filename": WAN2GP_REF2VA_DIT} in fields["model"]["recommendations"]
    assert fields["references"]["type"] == "media"


def test_the_shipped_recommendations_the_core_forms_already_make_are_copied_unchanged(shipped_presets, core_presets):
    for preset_id, shipped in SHIPPED_PRESETS.items():
        named, _ = _video_form(shipped_presets[preset_id])
        source_named, _ = _video_form(core_presets[shipped.source_id])
        known = {item["name"]: item for field in source_named.values() for item in _recommendations(field)}
        for name in shipped.recommended:
            for item in _recommendations(named[name]):
                if item["name"] in known:
                    keys = ("link", "size", "sha256")
                    assert {key: item[key] for key in keys} == {key: known[item["name"]][key] for key in keys}, (preset_id, item["name"])


def test_the_wan_forms_bind_to_the_defaults_and_the_speed_profile_they_declare(shipped_presets):
    from src.features.forms.binding import bind_form

    for preset_id, shipped in WAN_PRESETS.items():
        preset = shipped_presets[preset_id]
        values = bind_form(preset, "video", None, {"text_encoder": "text-encoder", "vae": "vae"}).values
        named, _ = _video_form(preset)
        expected = {**shipped.defaults, **shipped.reacted}
        assert {name: values[name] for name in expected} == expected, preset_id
        assert [option["value"] for option in named["speed_profile"].configuration["options"]] == list(shipped.speed_options), preset_id
        assert list(preset.speed_profiles) == list(shipped.speed_options), preset_id
        assert preset.speed_profiles[values["speed_profile"]] == {"steps": values["steps"], "guidance": values["cfg"], "sampler": values["sampler"]}, preset_id


@pytest.mark.parametrize("aspect, draft, final", [(16 / 9, "832x480", "1344x768"), (9 / 16, "480x832", "768x1344")])
def test_the_plugin_drafts_the_shipped_presets_at_832x480_and_finishes_them_at_the_released_canvas(shipped_presets, aspect, draft, final):
    bridge = _load("backend.core_bridge")
    models = _load("backend.models")
    director = _load("backend.director")

    for preset_id in H3_PRESETS:
        preset = shipped_presets[preset_id]
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


@pytest.mark.parametrize("aspect, side", [(16 / 9, 0), (9 / 16, 1)])
def test_the_plugin_drafts_the_wan_presets_at_832x480_and_finishes_them_at_the_largest_size_they_offer(shipped_presets, aspect, side):
    bridge = _load("backend.core_bridge")
    models = _load("backend.models")
    director = _load("backend.director")

    for preset_id, shipped in WAN_PRESETS.items():
        preset = shipped_presets[preset_id]
        [form] = preset.modes["video"].forms
        fields = {}
        bridge._describe_fields(form.fields, {"preset": preset.path, "_shared": str(SHARED_PRESETS)}, fields)
        options = models.resolution_options(fields)
        values = [option["value"] for option in options]

        if shipped.own_resolutions is not None:
            assert values == list(shipped.own_resolutions), preset_id
        else:
            assert {"832x480", "480x832", "960x544", "544x960", "1280x720", "720x1280"} <= set(values), preset_id
        assert fields["resolution"]["default"] == shipped.defaults["resolution"], preset_id
        assert director.draft_resolution(options, "832x480", aspect) == shipped.draft[side], preset_id
        assert director.final_resolution(options, aspect) == shipped.final[side], preset_id
        assert models.model_fields(fields) == (["text_encoder", "vae", "t2v_high_noise_model"], ["t2v_low_noise_model"]), preset_id


def test_every_export_seam_and_scene_route_loaded_by_the_core_depends_on_the_signed_in_user(loader, manifest):
    api = loader.load_plugin_module(manifest, "backend.api")

    def depends_on_user(dependant):
        return any(item.call is get_current_active_user or depends_on_user(item) for item in dependant.dependencies)

    scene_parts = ("/scenes/", "/scene-files", "/captures", "/renders")
    guarded = [
        route
        for route in api.router.routes
        if "/exports" in route.path or route.path.endswith("/seam-frame") or any(part in route.path for part in scene_parts)
    ]

    assert len(guarded) == 17
    assert all(depends_on_user(route.dependant) for route in guarded)


def test_the_ready_hook_loaded_by_the_core_fails_the_export_a_stopped_server_left_running_and_resumes_the_queue(loader, manifest, mock_db, scheduled, monkeypatch):
    _boot(loader, manifest)
    on_ready = _handler(loader, manifest, "plugin.lifecycle.ready")
    on_disable = _handler(loader, manifest, "plugin.lifecycle.disable")
    jobs = _load("backend.exports.jobs")
    bridge = sys.modules[f"{PACKAGE}.backend.core_bridge"]
    notified = []
    monkeypatch.setattr(bridge, "notify", lambda **fields: notified.append(fields))
    monkeypatch.setattr(bridge, "storage_directory", lambda: Path("storage-that-does-not-exist"))
    interrupted = jobs.create_job("p-1", "user-1", "web", "1080p")
    jobs.claim_next()
    waiting = jobs.create_job("p-2", "user-1", "social", "720p")

    on_ready(HookContext(hook_name="plugin.lifecycle.ready", plugin_id=PLUGIN_ID, data={}))

    assert (jobs.get_job(interrupted["id"])["status"], jobs.get_job(interrupted["id"])["error_code"]) == ("failed", "ffmpeg_failed")
    assert jobs.get_job(waiting["id"])["status"] == "queued"
    assert sorted(job.__qualname__ for job in scheduled) == ["Runner.run", "Tracker.run"]
    assert [fields["notification_type"] for fields in notified] == ["video-producer.export_failed"]
    assert jobs.RUNNER.active is True
    on_disable(HookContext(hook_name="plugin.lifecycle.disable", plugin_id="system", data={"plugin_id": PLUGIN_ID}))
    assert jobs.RUNNER.active is False


def test_the_golden_exports_come_back_byte_for_byte_through_the_routes_loaded_by_the_core(loader, manifest, mock_db, monkeypatch):
    _boot(loader, manifest)
    caller = {"user": _user("user-1")}
    app = _app(loader, manifest, caller)
    bridge = sys.modules[f"{PACKAGE}.backend.core_bridge"]
    takes = sys.modules[f"{PACKAGE}.backend.takes"]
    folder = PLUGIN_ROOT / "tests" / "fixtures" / "exports"
    reference = json.loads((folder / "reference-project.json").read_text(encoding="utf-8"))
    uploads = {upload["item_id"]: upload for upload in reference["uploads"]}
    base = f"/api/plugins/{PLUGIN_ID}"

    def resolve_media(user, ref):
        upload = uploads[ref["item_id"]]
        return {"value": upload["value"], "media_type": upload["media_type"], "original_filename": upload["original_filename"], "origin": None}

    monkeypatch.setattr(bridge, "resolve_media", resolve_media)
    monkeypatch.setattr(bridge, "media_file_path", lambda kind, value: f"/srv/storage/{value}")
    with TestClient(app) as client:
        project_id = client.post(f"{base}/projects", json={"doc": reference["doc"]}).json()["data"]["project"]["id"]
        for take in reference["takes"]:
            takes.create_take({**{key: take[key] for key in ("shot_id", "generation_id", "file_id", "file_path", "status", "quality", "kind", "chosen")}, "project_id": project_id, "user_id": "user-1"})
        answers = {fmt: client.get(f"{base}/projects/{project_id}/exports/{fmt}", params={"media": "name"}) for fmt in ("fcpxml", "otio", "edl", "srt")}
        caller["user"] = _user("user-2")
        foreign = {fmt: client.get(f"{base}/projects/{project_id}/exports/{fmt}") for fmt in ("fcpxml", "srt")}

    for fmt, answer in answers.items():
        assert answer.status_code == 200 and answer.content == (folder / f"reference.{fmt}").read_bytes(), fmt
    assert {answer.status_code for answer in foreign.values()} == {404}
