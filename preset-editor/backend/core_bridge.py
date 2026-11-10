import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.plugin_api import User, get_container
from src.plugin_api.presets import lint_preset_dir, preset_install_state, preset_operations, preset_template


def preset_loader():
    return get_container().preset_template_loader


def file_repository():
    return get_container().file_preset_repository


def collaborators():
    return get_container().preset_collaborators


def preset_roots() -> List[Path]:
    return [Path(root) for root in preset_loader().all_preset_roots()]


def find_preset(preset_id: str):
    return preset_template(preset_id)


def catalog() -> List[Dict[str, Any]]:
    return file_repository().list_all_presets()


def is_installed(preset_id: str) -> bool:
    return preset_install_state(preset_id).installed


def install_preset(preset_id: str, user: User) -> Dict[str, Any]:
    return preset_operations.install_preset(collaborators(), preset_id, user)


def uninstall_preset(preset_id: str, user: User) -> Any:
    return preset_operations.uninstall_preset(collaborators(), preset_id, user)


def reload_presets() -> None:
    preset_loader().reload()


def load_errors() -> Dict[Path, List[str]]:
    recorded = getattr(preset_loader(), "load_errors", None) or {}
    return {Path(key).resolve(): list(messages) for key, messages in recorded.items()}


def lint(path: Path) -> Tuple[List[str], List[str]]:
    return lint_preset_dir(str(path))


async def reload_presets_async() -> None:
    await asyncio.to_thread(reload_presets)


async def lint_async(path: Path) -> Tuple[List[str], List[str]]:
    return await asyncio.to_thread(lint, path)

