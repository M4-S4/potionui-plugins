import logging

if __name__.count(".") >= 2:
    from ..backend import PLUGIN_ID, scene3d, tables, tracker
    from ..backend.core_bridge import HookContext
    from ..backend.exports import jobs
else:
    from backend import PLUGIN_ID, scene3d, tables, tracker
    from backend.core_bridge import HookContext
    from backend.exports import jobs

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
    """Start following the takes in flight, resume the export queue and clear what a stop left of the scenes once the application loop is up."""
    try:
        if tracker.TRACKER.start():
            logger.info("[VIDEO-PRODUCER] Take tracker started")
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not start the take tracker")
    try:
        failed = jobs.recover()
        if failed:
            logger.info("[VIDEO-PRODUCER] %s export(s) interrupted by the last stop marked failed", failed)
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not resume the export queue")
    try:
        failed = scene3d.recover()
        if failed:
            logger.info("[VIDEO-PRODUCER] %s splat job(s) interrupted by the last stop marked failed", failed)
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not clear the scenes the last stop left")
    return context


def on_disable(context: HookContext) -> HookContext:
    """Stop the take tracker and the export runner when Video Producer itself is disabled."""
    if context.get("plugin_id") != PLUGIN_ID:
        return context
    tracker.TRACKER.stop()
    jobs.RUNNER.stop()
    logger.info("[VIDEO-PRODUCER] Disabled")
    return context
