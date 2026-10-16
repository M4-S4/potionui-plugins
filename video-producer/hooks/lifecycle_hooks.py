import logging

if __name__.count(".") >= 2:
    from ..backend import PLUGIN_ID, tables
    from ..backend.core_bridge import HookContext
else:
    from backend import PLUGIN_ID, tables
    from backend.core_bridge import HookContext

logger = logging.getLogger("plugins.video-producer")


def on_boot(context: HookContext) -> HookContext:
    """Create the plugin's tables on every process start."""
    try:
        tables.create_tables()
        logger.info("[VIDEO-PRODUCER] Tables ready: %s", ", ".join(tables.TABLE_NAMES))
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not create the plugin's tables")
    return context


def on_ready(context: HookContext) -> HookContext:
    """Runs once the application loop is up."""
    return context


def on_disable(context: HookContext) -> HookContext:
    """React only when Video Producer itself is disabled."""
    if context.get("plugin_id") != PLUGIN_ID:
        return context
    logger.info("[VIDEO-PRODUCER] Disabled")
    return context
