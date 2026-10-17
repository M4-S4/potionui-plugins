from .core_bridge import NotificationTypeSpec

TAKE_DONE = "video-producer.take_done"
TAKE_FAILED = "video-producer.take_failed"
EXPORT_DONE = "video-producer.export_done"
EXPORT_FAILED = "video-producer.export_failed"

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
    NotificationTypeSpec(
        key=EXPORT_DONE,
        label="Video Producer: export ready",
        description="A video you exported from Video Producer is ready to download.",
        category="plugin",
        default_enabled=True,
        admin_only=False,
    ),
    NotificationTypeSpec(
        key=EXPORT_FAILED,
        label="Video Producer: export failed",
        description="A video you exported from Video Producer could not be made.",
        category="plugin",
        default_enabled=True,
        admin_only=False,
    ),
)
