"""`provider.register` handler of the model-browser plugin (PLAN.md §7.3).

Registers the `model-browser` marketplace provider (`provider/pending_provider.py`), which
enriches the models this plugin downloaded from what it recorded when it queued them. The
core's provider registry instantiates the class and calls `initialize` itself.

Like the lifecycle handlers: synchronous, never raises, returns the context it was given.
The provider is imported inside the handler, through the plugin's package when PotionUI's
loader imported this module as `model_browser.hooks.provider_hooks`, and as the top-level
`provider` package in the plugin's tests.
"""

import logging

from src.plugin_api import HookContext

logger = logging.getLogger("plugins.model-browser")


def register_providers(context: HookContext) -> HookContext:
    """Add `PendingProvider` to `context.data["providers"]`, next to the other plugins' providers."""
    try:
        if __name__.count(".") >= 2:
            from ..provider.pending_provider import PROVIDER_ID, PendingProvider
        else:
            from provider.pending_provider import PROVIDER_ID, PendingProvider

        providers = context.data.get("providers")
        if providers is None:
            providers = context.data["providers"] = {}
        providers[PROVIDER_ID] = PendingProvider
        logger.info("[MODEL-BROWSER] Registered the %s marketplace provider", PROVIDER_ID)
    except Exception:
        logger.exception("[MODEL-BROWSER] Could not register the model-browser marketplace provider")
    return context
