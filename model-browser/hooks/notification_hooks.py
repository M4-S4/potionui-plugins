"""`notification_type.register` handler of the model-browser plugin (PLAN.md §4.4).

The core fires this hook once, while it builds the application, with its notification type
registry in `context.data["registry"]`. Declaring the plugin's types there
(`backend/notifications.py::TYPES`) lists them in every user's notification preferences,
where each one can be turned off. A plugin enabled later, without a restart, is not asked:
its notifications are still delivered (the core sends a type it does not know), they only
miss from the preferences until the next start.

Like the other handlers: synchronous, never raises, returns the context it was given.
"""

import logging

from src.plugin_api import HookContext

# Imported as `model_browser.hooks.notification_hooks` by PotionUI's loader and as the
# top-level `hooks.notification_hooks` by the tests (see lifecycle_hooks.py).
if __name__.count(".") >= 2:
    from ..backend import core_bridge, notifications
else:
    from backend import core_bridge, notifications

logger = logging.getLogger("plugins.model-browser")


def register_types(context: HookContext) -> HookContext:
    """Declare `notifications.TYPES` on the registry the hook carries; keys already there are left alone."""
    try:
        registry = context.data.get("registry") if isinstance(context.data, dict) else None
        if registry is None:
            logger.warning("[MODEL-BROWSER] notification_type.register carried no registry: no notification type declared")
            return context
        added = core_bridge.register_notification_types(registry, notifications.TYPES)
        logger.info("[MODEL-BROWSER] Notification types declared: %s", ", ".join(added) or "none new")
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not declare the plugin's notification types")
    return context
