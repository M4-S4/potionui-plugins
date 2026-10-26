from typing import Any, Callable, Dict

from src.plugin_api import plugin_settings
from src.plugin_api.llm import LLMConfig, OpenAIClient, OpenAIRequest

PLUGIN_ID = "deepseek-provider"
PLUGIN_VERSION = "0.1.0"
DEFAULT_THINKING = "auto"
DEFAULT_REASONING_EFFORT = "high"


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
        if settings.get("thinking", DEFAULT_THINKING) == "off" or uses_tools(request):
            return {"thinking": {"type": "disabled"}}
        return {
            "thinking": {"type": "enabled"},
            "reasoning_effort": settings.get("reasoning_effort", DEFAULT_REASONING_EFFORT),
        }

    def adapt_request(self, request: OpenAIRequest, config: LLMConfig) -> OpenAIRequest:
        payload = request.payload
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        payload.pop("reasoning_effort", None)
        payload.update(self._thinking(request))
        return request
