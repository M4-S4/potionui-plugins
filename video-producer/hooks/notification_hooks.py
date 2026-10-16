import logging

if __name__.count(".") >= 2:
    from ..backend import core_bridge, notifications
    from ..backend.core_bridge import HookContext
else:
    from backend import core_bridge, notifications
    from backend.core_bridge import HookContext

logger = logging.getLogger("plugins.video-producer")


def register_types(context: HookContext) -> HookContext:
    """Declare the take_done and take_failed notification types."""
    try:
        registry = context.data.get("registry") if isinstance(context.data, dict) else None
        if registry is None:
            logger.warning("[VIDEO-PRODUCER] notification_type.register carried no registry: no notification type declared")
            return context
        added = core_bridge.register_notification_types(registry, notifications.TYPES)
        logger.info("[VIDEO-PRODUCER] Notification types declared: %s", ", ".join(added) or "none new")
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not declare the plugin's notification types")
    return context
