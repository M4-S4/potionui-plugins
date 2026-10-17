import logging
from typing import Any, Dict

if __name__.count(".") >= 2:
    from ..backend import generation
    from ..backend.core_bridge import HookContext
else:
    from backend import generation
    from backend.core_bridge import HookContext

logger = logging.getLogger("plugins.video-producer")


def _data(context: HookContext) -> Dict[str, Any]:
    return context.data if isinstance(context.data, dict) else {}


def on_after_complete(context: HookContext) -> HookContext:
    """End the take of a generation that completed or was cancelled, as the tracker would."""
    data = _data(context)
    try:
        generation.settle_from_hook(data.get("generation_id"), str(data.get("status") or ""), duration=data.get("duration"))
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not settle the take of generation %s", data.get("generation_id"))
    return context


def on_failed(context: HookContext) -> HookContext:
    """End the take of a generation that failed with the core's error code and user message."""
    data = _data(context)
    try:
        generation.settle_from_hook(
            data.get("generation_id"), "failed", error_code=data.get("error_code"), message=data.get("message")
        )
    except Exception:
        logger.exception("[VIDEO-PRODUCER] Could not settle the take of generation %s", data.get("generation_id"))
    return context
