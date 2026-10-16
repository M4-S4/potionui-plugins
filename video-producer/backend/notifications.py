from .core_bridge import NotificationTypeSpec

TAKE_DONE = "video-producer.take_done"
TAKE_FAILED = "video-producer.take_failed"

TYPES = (
    NotificationTypeSpec(
        key=TAKE_DONE,
        label="Video Producer: take ready",
        description="A draft or final take you started in Video Producer is ready.",
        category="plugin",
        default_enabled=True,
        admin_only=False,
    ),
    NotificationTypeSpec(
        key=TAKE_FAILED,
        label="Video Producer: take failed",
        description="A draft or final take you started in Video Producer failed.",
        category="plugin",
        default_enabled=True,
        admin_only=False,
    ),
)
