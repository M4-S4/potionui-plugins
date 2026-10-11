"""Admin setup steps of the model-browser plugin (manifest `setup:`, PLAN.md §2, §8.1, §8.3).

Browsing needs no credential, but downloads that need a login are authenticated by the
CivitAI and Hugging Face provider plugins, which own the API key / token (`provider_id` on
the core download queue). Each check is done when that provider is initialised in the
core's provider registry.

The core loads these classes from the manifest reference `backend.setup_checks:<Class>`
with `PluginLoader.load_class`, i.e. as `model_browser.backend.setup_checks`, and calls
`evaluate` on every visit to Admin -> Plugins: one in-memory read of the registry, no
network, no database.
"""

import logging

from src.plugin_api import SetupCheck, SetupCheckContext, SetupCheckResult

logger = logging.getLogger("plugins.model-browser")


class _ProviderReady(SetupCheck):
    """Done when the provider `provider_id`, contributed by the plugin `plugin_id`, is initialised."""

    provider_id = ""
    plugin_id = ""
    name = ""
    #: What the provider plugin's settings hold: "API key", "token".
    credential = ""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        action_label = f"Open the {self.name} provider"
        action_href = f"/admin?tab=plugins&id={self.plugin_id}"
        try:
            from src.plugin_api import get_provider_registry

            ready = bool(get_provider_registry().is_provider_initialized(self.provider_id))
        except Exception as exc:
            logger.warning("[MODEL-BROWSER] Setup check: could not read the provider registry: %s", exc)
            return SetupCheckResult(
                done=False,
                description=f"Could not check the {self.name} provider; see the server log.",
                action_label=action_label,
                action_href=action_href,
            )
        if ready:
            return SetupCheckResult(done=True, description=f"The {self.name} provider is enabled.")
        return SetupCheckResult(
            done=False,
            description=(
                f"Enable and configure the {self.name} provider plugin ({self.credential}) so downloads "
                "that need a login work; browsing works without it."
            ),
            action_label=action_label,
            action_href=action_href,
        )


class CivitaiProviderReady(_ProviderReady):
    provider_id = "civitai"
    plugin_id = "civitai-provider"
    name = "CivitAI"
    credential = "API key"


class HuggingFaceProviderReady(_ProviderReady):
    provider_id = "huggingface"
    plugin_id = "huggingface-provider"
    name = "Hugging Face"
    credential = "token"
