import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.features.llm.clients.openai import OpenAIClient
from src.features.llm.gateway import LLMGateway
from src.platform.plugins.llm_providers import LLMProviderRegistry
from src.platform.plugins.registry import PluginRegistry

PLUGIN_ID = "deepseek-provider"
PACKAGE = "deepseek_provider"
REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "content" / "plugins" / "marketplace" / PLUGIN_ID


@pytest.fixture(autouse=True)
def plugin_modules_removed_afterwards():
    modules, path = set(sys.modules), list(sys.path)
    try:
        yield
    finally:
        for name in set(sys.modules) - modules:
            if name.split(".")[0] in (PACKAGE, "backend"):
                del sys.modules[name]
        sys.path[:] = path


@pytest.fixture
def providers():
    return LLMProviderRegistry()


@pytest.fixture
def registry(tmp_path, providers):
    marketplace = tmp_path / "marketplace"
    shutil.copytree(PLUGIN_ROOT, marketplace / PLUGIN_ID, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (tmp_path / "local").mkdir()
    return PluginRegistry(str(marketplace), str(tmp_path / "local"), llm_provider_registry=providers)


def test_enabling_the_plugin_adds_deepseek_to_the_configuration_types(registry, providers):
    assert registry.enable_plugin(PLUGIN_ID)

    types = LLMGateway(SimpleNamespace(), provider_registry=providers).provider_types()

    assert types[-1] == {
        "type": "deepseek",
        "label": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "supports_model_listing": True,
    }
    client = providers.get("deepseek").client
    assert isinstance(client, OpenAIClient)
    assert type(client).__module__ == f"{PACKAGE}.backend.client"


def test_disabling_the_plugin_takes_the_type_away(registry, providers):
    assert registry.enable_plugin(PLUGIN_ID)

    registry.disable_plugin(PLUGIN_ID)

    assert providers.get("deepseek") is None


def test_the_manifest_version_matches_the_backend(registry):
    manifest = next(m for m in registry.loader.discover_plugins() if m.id == PLUGIN_ID)
    backend = registry.loader.load_plugin_module(manifest, "backend.client")

    assert manifest.validation_error is None
    assert (manifest.id, manifest.version) == (backend.PLUGIN_ID, backend.PLUGIN_VERSION)
