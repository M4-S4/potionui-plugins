from typing import Any, Callable, Dict

from src.plugin_api import plugin_settings
from src.plugin_api.llm import LLMConfig, OpenAIClient, OpenAIRequest

PLUGIN_ID = "deepseek-provider"
PLUGIN_VERSION = "0.1.0"


def uses_tools(request: OpenAIRequest) -> bool:
    return bool(request.payload.get("tools")) or any(
        message.get("role") == "tool" or message.get("tool_calls") for message in request.messages
    )


class DeepSeekClient(OpenAIClient):
    display_name = "DeepSeek"

    def __init__(self, settings: Callable[[], Dict[str, Any]] = lambda: plugin_settings(PLUGIN_ID)):
        self._settings = settings

    def _thinking(self, request: OpenAIRequest) -> Dict[str, Any]:
        settings = self._settings()
        if settings["thinking"] == "off" or uses_tools(request):
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": settings["reasoning_effort"]}

    def adapt_request(self, request: OpenAIRequest, config: LLMConfig) -> OpenAIRequest:
        thinking = self._thinking(request)
        for params in (request.payload, request.sampling_params):
            if "max_completion_tokens" in params:
                params["max_tokens"] = params.pop("max_completion_tokens")
            params.pop("reasoning_effort", None)
            params.update(thinking)
        return request
