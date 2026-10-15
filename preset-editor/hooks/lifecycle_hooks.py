import logging

from src.plugin_api import HookContext

if __name__.count(".") >= 2:
    from ..backend import paths
else:
    from backend import paths

logger = logging.getLogger("plugins.preset-editor")


def on_boot(context: HookContext) -> HookContext:
    try:
        roots = paths.roots()
        roots.ensure()
        removed = paths.clear_staging(roots)
        logger.info("[PRESET-EDITOR] Folders ready; %d stale staging entries removed", removed)
    except Exception:
        logger.exception("[PRESET-EDITOR] Could not prepare the plugin's folders")
    return context
