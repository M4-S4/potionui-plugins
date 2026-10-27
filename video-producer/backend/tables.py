from typing import Tuple

from .takes import migrate_labels

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
    "video_producer_looks": """
        key TEXT PRIMARY KEY,
        user_id TEXT,
        kind TEXT NOT NULL,
        source TEXT,
        model TEXT,
        status TEXT NOT NULL,
        frames TEXT,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    """,
    "video_producer_export_jobs": """
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        format TEXT NOT NULL,
        resolution TEXT NOT NULL,
        stems INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        progress REAL NOT NULL DEFAULT 0,
        step TEXT,
        file_name TEXT,
        file_size INTEGER,
        media_item_id TEXT,
        media_url TEXT,
        error_code TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    """,
}

TABLE_NAMES = tuple(_COLUMNS)

_RETIRED_TABLES = ("video_producer_scene_jobs", "video_producer_scene_files")

_ADDED_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("video_producer_versions", "source_version", "INTEGER"),
    ("video_producer_takes", "director_mode", "TEXT"),
    ("video_producer_takes", "model_id", "TEXT"),
    ("video_producer_takes", "progress", "REAL"),
    ("video_producer_takes", "step", "TEXT"),
    ("video_producer_takes", "variant", "TEXT"),
    ("video_producer_takes", "chosen", "INTEGER NOT NULL DEFAULT 0"),
    ("video_producer_takes", "flag", "TEXT"),
    ("video_producer_takes", "profile", "TEXT"),
    ("video_producer_takes", "prompt_text", "TEXT"),
    ("video_producer_takes", "file_id", "TEXT"),
    ("video_producer_takes", "units_reserved", "REAL NOT NULL DEFAULT 0"),
    ("video_producer_takes", "started_at", "TIMESTAMP"),
    ("video_producer_takes", "user_id", "TEXT"),
    ("video_producer_takes", "request", "TEXT"),
    ("video_producer_takes", "label", "TEXT"),
    ("video_producer_takes", "shot_revision", "INTEGER"),
    ("video_producer_takes", "priority", "INTEGER NOT NULL DEFAULT 0"),
    ("video_producer_takes", "chain", "TEXT"),
    ("video_producer_takes", "chain_wait", "INTEGER NOT NULL DEFAULT 0"),
    ("video_producer_takes", "frame_role", "TEXT"),
    ("video_producer_takes", "video_refs", "TEXT"),
    ("video_producer_export_jobs", "stems", "INTEGER NOT NULL DEFAULT 0"),
)

_INDEXES = (
    ("idx_video_producer_projects_user", "video_producer_projects", "user_id, updated_at"),
    ("idx_video_producer_versions_project", "video_producer_versions", "project_id, version"),
    ("idx_video_producer_takes_project", "video_producer_takes", "project_id, shot_id"),
    ("idx_video_producer_takes_generation", "video_producer_takes", "generation_id"),
    ("idx_video_producer_jobs_take", "video_producer_jobs", "take_id"),
    ("idx_video_producer_jobs_generation", "video_producer_jobs", "generation_id"),
    ("idx_video_producer_calibration_key", "video_producer_calibration", "preset_id, backend_id, resolution"),
    ("idx_video_producer_looks_status", "video_producer_looks", "status, updated_at"),
    ("idx_video_producer_export_jobs_project", "video_producer_export_jobs", "project_id, created_at"),
    ("idx_video_producer_export_jobs_status", "video_producer_export_jobs", "status, created_at"),
)


def create_tables() -> None:
    """Create the plugin's tables, columns and indexes, drop the retired tables, and label the takes stored before labels; safe to run on every boot."""
    from src.plugin_api import db

    with db.get_cursor() as cursor:
        for name, columns in _COLUMNS.items():
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns})")
        for name in _RETIRED_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {name}")
        for table, column, column_type in _ADDED_COLUMNS:
            cursor.execute(f"PRAGMA table_info({table})")
            if column not in {row["name"] for row in cursor.fetchall()}:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        for index, table, columns in _INDEXES:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({columns})")
        cursor.execute("PRAGMA table_info(video_producer_takes)")
        labelled = "label" in {row["name"] for row in cursor.fetchall()}
    if labelled:
        migrate_labels()
