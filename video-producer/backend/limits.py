from typing import Any, Dict

from . import core_bridge

GPU_MINUTES = "video-producer.gpu_minutes"

STORAGE = "storage_bytes"

UPLOAD_FILE_SIZE = "upload_file_size"


def gpu_minutes_status(user_id: str) -> Dict[str, Any]:
    """The user's GPU-minute quota: limit, used, remaining, exempt and resets_at."""
    return core_bridge.limit_status(user_id, GPU_MINUTES)


def storage_status(user_id: str) -> Dict[str, Any]:
    """The user's storage plan as the core measures it (generations and library uploads): limit, used, remaining, exempt."""
    return core_bridge.limit_status(user_id, STORAGE)


def upload_size_status(user_id: str) -> Dict[str, Any]:
    """The largest single file the user's plan lets them upload, in remaining; None when nothing limits it."""
    return core_bridge.limit_status(user_id, UPLOAD_FILE_SIZE)
