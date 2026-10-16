from typing import Any, Dict

from . import core_bridge

GPU_MINUTES = "video-producer.gpu_minutes"


def gpu_minutes_status(user_id: str) -> Dict[str, Any]:
    """The user's GPU-minute quota: limit, used, remaining, exempt and resets_at."""
    return core_bridge.limit_status(user_id, GPU_MINUTES)
