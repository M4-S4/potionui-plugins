from typing import Tuple

_COLUMNS = {
    "video_producer_projects": """
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        doc TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """,
    "video_producer_versions": """
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        doc TEXT NOT NULL,
        label TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """,
    "video_producer_takes": """
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        shot_id TEXT NOT NULL,
        generation_id TEXT,
        quality TEXT NOT NULL,
        kind TEXT NOT NULL,
        parent_take_id TEXT,
        preset_id TEXT,
        mode TEXT,
        backend_id TEXT,
        seed INTEGER,
        resolution TEXT,
        status TEXT NOT NULL,
        file_path TEXT,
        thumb_path TEXT,
        width INTEGER,
        height INTEGER,
        duration_s REAL,
        fps REAL,
        error_code TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP
    """,
    "video_producer_jobs": """
        id TEXT PRIMARY KEY,
        take_id TEXT NOT NULL,
        generation_id TEXT,
        limit_ref_id TEXT,
        units_reserved REAL NOT NULL DEFAULT 0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP
    """,
    "video_producer_calibration": """
        preset_id TEXT NOT NULL,
        backend_id TEXT NOT NULL,
        resolution TEXT NOT NULL,
        seconds REAL NOT NULL,
        duration_ms INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """,
}

TABLE_NAMES = tuple(_COLUMNS)

_ADDED_COLUMNS: Tuple[Tuple[str, str, str], ...] = (("video_producer_versions", "source_version", "INTEGER"),)

_INDEXES = (
    ("idx_video_producer_projects_user", "video_producer_projects", "user_id, updated_at"),
    ("idx_video_producer_versions_project", "video_producer_versions", "project_id, version"),
    ("idx_video_producer_takes_project", "video_producer_takes", "project_id, shot_id"),
    ("idx_video_producer_takes_generation", "video_producer_takes", "generation_id"),
    ("idx_video_producer_jobs_take", "video_producer_jobs", "take_id"),
    ("idx_video_producer_jobs_generation", "video_producer_jobs", "generation_id"),
    ("idx_video_producer_calibration_key", "video_producer_calibration", "preset_id, backend_id, resolution"),
)


def create_tables() -> None:
    """Create the plugin's tables, columns and indexes; safe to run on every boot."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        for name, columns in _COLUMNS.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns})")
        for table, column, column_type in _ADDED_COLUMNS:
            cursor.execute(f"PRAGMA table_info({table})")
            if column not in {row["name"] for row in cursor.fetchall()}:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        for index, table, columns in _INDEXES:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({columns})")
