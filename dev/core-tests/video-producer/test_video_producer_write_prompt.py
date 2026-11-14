import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.features.prompt_enhancement.collaborators import PromptEnhancementCollaborators
from src.plugin_api import AccountType
from src.plugin_api import prompts as api_prompts

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / "video-producer" for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "video_producer_write_prompt_under_test"
GUIDE = "Camera motion as natural English: push in, pull out, pan left."
REFS_GUIDE = "Reference mode uses a SIX-SECTION prompt."


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


core_bridge = _plugin_module("backend.core_bridge")
prompt_writer = _plugin_module("backend.prompt_writer")


class Repository:
    def __init__(self, configs):
        self.configs = {config.id: config for config in configs}

    def get_configuration(self, config_id):
        return self.configs.get(config_id)

    def get_default_configuration(self):
        return next(iter(self.configs.values()), None)

    def get_user_llm_assignments(self, user_id):
        return list(self.configs)


class Llm:
    def __init__(self, configs, reply):
        self.repository = Repository(configs)
        self.reply = reply
        self.calls = []

    async def complete(self, config_id, messages, system=None, settings=None, tools=()):
        self.calls.append({"config_id": config_id, "messages": messages, "system": system})
        return SimpleNamespace(text=self.reply, message=SimpleNamespace(reasoning=lambda: ()), usage=None)


def _config(config_id, name, vision):
    return SimpleNamespace(id=config_id, name=name, supports_vision=vision, enabled=True, model="m")


@pytest.fixture
def core(monkeypatch, tmp_path):
    def install(configs, reply="[Shot 1] The fisherman (<Subject 1>) lifts his lantern."):
        llm = Llm(configs, reply)
        preset = SimpleNamespace(id="MiniMax-H3-12GB", name="MiniMax-H3 (12 GB)", llm={"guide": GUIDE, "modes": {"refs": {"guide": REFS_GUIDE}}}, short_description=None, description=None)
        collaborators = PromptEnhancementCollaborators(llm_service=llm, preset_collaborators=SimpleNamespace(file_repo=SimpleNamespace(find_preset_by_id=lambda preset_id: preset), db_repo=None))
        container = SimpleNamespace(
            prompt_enhancement_manager=collaborators,
            user_repository=SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(account_type=AccountType.ADMIN)),
            settings=SimpleNamespace(get_file_storage_directory=lambda: str(tmp_path)),
        )
        monkeypatch.setattr(api_prompts, "get_container", lambda: container)
        return llm

    (tmp_path / "uploads").mkdir()
    for name in ("start", "end"):
        Image.new("RGB", (64, 36), (40, 80, 120)).save(tmp_path / "uploads" / f"{name}.png")
    return install


def test_the_core_status_carries_every_field_the_plugin_reads(core):
    core([_config("llm-1", "Qwen3-VL", True)])
    ready = prompt_writer.status(SimpleNamespace(id="user-1"))
    core([])
    none = prompt_writer.status(SimpleNamespace(id="user-1"))

    assert ready == {"available": True, "vision": True, "name": "Qwen3-VL", "code": None, "message": None}
    assert none["available"] is False
    assert none["code"] == "no_llm"
    assert none["message"]


def test_the_core_writes_from_the_plugin_instruction_with_the_guide_of_the_shot_mode_and_its_key_frames(core):
    llm = core([_config("llm-1", "Qwen3-VL", True)])
    instruction = prompt_writer.instruction("he lifts the lantern", current="", seconds=4.0, characters=["the old fisherman"], place=None, images=["first", "last"])
    media = [{"value": "uploads/start.png", "media_type": "image"}, {"value": "uploads/end.png", "media_type": "image"}]

    written = asyncio.run(core_bridge.write_prompt_for_preset("user-1", instruction, preset_id="MiniMax-H3-12GB", mode="refs", form_data={}, media=media))

    assert prompt_writer.cleaned(written["text"], ["the fisherman"]) == "The fisherman lifts his lantern."
    assert written["llm_id"] == "llm-1"
    (call,) = llm.calls
    (message,) = call["messages"]
    text = message.parts[0].text
    assert REFS_GUIDE in text
    assert GUIDE not in text
    assert "he lifts the lantern" in text
    assert "no section label and no [Shot] marker" in text
    assert "write no tag in angle brackets at all" in text
    assert len(message.parts) == 3


def test_the_core_refuses_images_for_a_model_that_cannot_see_with_the_code_the_page_translates(core):
    core([_config("llm-1", "Llama", False)])

    with pytest.raises(core_bridge.PromptWriteRefused) as refused:
        asyncio.run(core_bridge.write_prompt_for_preset("user-1", "x", media=[{"value": "uploads/start.png", "media_type": "image"}]))

    assert refused.value.code == "vision_not_supported"
    assert prompt_writer.status(SimpleNamespace(id="user-1"))["vision"] is False


def test_the_plugin_bounds_its_instruction_by_the_limit_the_core_cuts_at():
    from src.features.prompt_enhancement import operations

    assert prompt_writer.MAX_INSTRUCTION_CHARS == operations.MAX_INSTRUCTION_CHARS
