"""`provider.register` handler of the model-browser plugin (PLAN.md §7.3, §8.4).

Registers the plugin's two marketplace providers:
- `model-browser` (`provider/pending_provider.py`) enriches the models this plugin
  downloaded, from what it recorded when it queued them (any source);
- `openmodeldb` (`provider/openmodeldb_provider.py`) looks a SHA256 up in OpenModelDB's
  catalogue, so the core can enrich upscalers already on disk, whoever downloaded them.
The core's provider registry instantiates each class and calls `initialize` itself.

Like the lifecycle handlers: synchronous, never raises, returns the context it was given;
a provider that fails to register is logged and the next one is still registered (the
`openmodeldb` one cannot keep `model-browser` out). The providers are imported inside the
handler, through the plugin's package when PotionUI's loader imported this module as
`model_browser.hooks.provider_hooks`, and as the top-level `provider` package in the
plugin's tests.
"""

import importlib
import logging

from src.plugin_api import HookContext

logger = logging.getLogger("plugins.model-browser")

#: (module under `provider/`, class) of each provider, in registration order.
PROVIDERS = (
    ("pending_provider", "PendingProvider"),
    ("openmodeldb_provider", "OpenModelDBProvider"),
)


def _provider_module(name: str):
    if __name__.count(".") >= 2:
        return importlib.import_module(f"..provider.{name}", __package__)
    return importlib.import_module(f"provider.{name}")


def register_providers(context: HookContext) -> HookContext:
    """Add `PendingProvider` and `OpenModelDBProvider` to `context.data["providers"]`, next to the other plugins' providers."""
    for module_name, class_name in PROVIDERS:
        try:
            module = _provider_module(module_name)
            providers = context.data.get("providers")
            if providers is None:
                providers = context.data["providers"] = {}
            providers[module.PROVIDER_ID] = getattr(module, class_name)
            logger.info("[MODEL-BROWSER] Registered the %s marketplace provider", module.PROVIDER_ID)
        except Exception:
            logger.exception("[MODEL-BROWSER] Could not register the %s marketplace provider", class_name)
    return context
