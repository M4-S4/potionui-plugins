import pytest

from backend import tables
from backend.tables import TABLE_NAMES, create_tables

_EXPECTED_COLUMNS = {
    "video_producer_projects": ["id", "user_id", "name", "doc", "version", "created_at", "updated_at"],
    "video_producer_versions": ["id", "project_id", "version", "doc", "label", "created_at", "source_version"],
    "video_producer_takes": [
        "id", "project_id", "shot_id", "generation_id", "quality", "kind", "parent_take_id", "preset_id", "mode",
        "backend_id", "seed", "resolution", "status", "file_path", "thumb_path", "width", "height", "duration_s",
        "fps", "error_code", "error_message", "created_at", "finished_at", "director_mode", "model_id", "progress", "step",
        "variant", "chosen", "flag", "profile", "prompt_text", "file_id", "units_reserved", "started_at", "user_id",
        "request", "label", "shot_revision", "priority", "chain", "chain_wait", "frame_role", "video_refs",
    ],
    "video_producer_jobs": [
        "id", "take_id", "generation_id", "limit_ref_id", "units_reserved", "started_at", "finished_at",
    ],
    "video_producer_calibration": ["preset_id", "backend_id", "resolution", "seconds", "duration_ms", "created_at"],
    "video_producer_looks": ["key", "user_id", "kind", "source", "model", "status", "frames", "error", "created_at", "updated_at"],
    "video_producer_export_jobs": [
        "id", "project_id", "user_id", "format", "resolution", "stems", "status", "progress", "step", "file_name", "file_size",
        "media_item_id", "media_url", "error_code", "error_message", "created_at", "started_at", "finished_at",
    ],
}

_EXPECTED_INDEXES = {
    "idx_video_producer_projects_user": ("video_producer_projects", ["user_id", "updated_at"]),
    "idx_video_producer_versions_project": ("video_producer_versions", ["project_id", "version"]),
    "idx_video_producer_takes_project": ("video_producer_takes", ["project_id", "shot_id"]),
    "idx_video_producer_takes_generation": ("video_producer_takes", ["generation_id"]),
    "idx_video_producer_jobs_take": ("video_producer_jobs", ["take_id"]),
    "idx_video_producer_jobs_generation": ("video_producer_jobs", ["generation_id"]),
    "idx_video_producer_calibration_key": ("video_producer_calibration", ["preset_id", "backend_id", "resolution"]),
    "idx_video_producer_looks_status": ("video_producer_looks", ["status", "updated_at"]),
    "idx_video_producer_export_jobs_project": ("video_producer_export_jobs", ["project_id", "created_at"]),
    "idx_video_producer_export_jobs_status": ("video_producer_export_jobs", ["status", "created_at"]),
}


def _schema(db):
    with db.get_cursor() as cursor:
        cursor.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name")
        return [tuple(row) for row in cursor.fetchall()]


def _table_names(db):
    with db.get_cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
        return {row["name"] for row in cursor.fetchall()}


def _columns(db, table):
    with db.get_cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table})")
        return [row["name"] for row in cursor.fetchall()]


def _indexes(db):
    found = {}
    with db.get_cursor() as cursor:
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'")
        for row in cursor.fetchall():
            found[row["name"]] = row["tbl_name"]
        for name in found:
            cursor.execute(f"PRAGMA index_info({name})")
            found[name] = (found[name], [column["name"] for column in cursor.fetchall()])
    return found


def test_table_names_are_the_seven_plugin_tables():
    assert len(TABLE_NAMES) == 7
    assert set(TABLE_NAMES) == set(_EXPECTED_COLUMNS)
    assert all(name.startswith("video_producer_") for name in TABLE_NAMES)


def test_create_tables_creates_exactly_the_plugin_tables(plugin_db):
    create_tables()

    assert _table_names(plugin_db) == set(TABLE_NAMES)


def test_tables_have_the_planned_columns(plugin_db):
    create_tables()

    assert {table: _columns(plugin_db, table) for table in TABLE_NAMES} == _EXPECTED_COLUMNS


def test_create_tables_creates_the_ten_indexes(plugin_db):
    create_tables()

    assert _indexes(plugin_db) == _EXPECTED_INDEXES


def test_every_index_name_carries_the_plugin_prefix(plugin_db):
    create_tables()

    assert len(_indexes(plugin_db)) == 10
    assert all(name.startswith("idx_video_producer_") for name in _indexes(plugin_db))


def test_create_tables_drops_the_scene_tables_of_the_retired_reframe_tool_and_keeps_the_projects(plugin_db):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute("INSERT INTO video_producer_projects (id, user_id, name, doc) VALUES ('p-1', 'user-1', 'Harbour', '{}')")
        cursor.execute("CREATE TABLE video_producer_scene_jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL)")
        cursor.execute("CREATE INDEX idx_video_producer_scene_jobs_project ON video_producer_scene_jobs (project_id)")
        cursor.execute("INSERT INTO video_producer_scene_jobs (id, project_id, status) VALUES ('j-1', 'p-1', 'done')")
        cursor.execute("CREATE TABLE video_producer_scene_files (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, stored_name TEXT NOT NULL)")
        cursor.execute("INSERT INTO video_producer_scene_files (id, project_id, stored_name) VALUES ('f-1', 'p-1', 'f-1.ply')")

    create_tables()

    assert _table_names(plugin_db) == set(TABLE_NAMES)
    assert _indexes(plugin_db) == _EXPECTED_INDEXES
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, name FROM video_producer_projects")
        assert [tuple(row) for row in cursor.fetchall()] == [("p-1", "Harbour")]

def test_a_second_create_tables_changes_nothing(plugin_db):
    create_tables()
    schema = _schema(plugin_db)

    create_tables()

    assert _schema(plugin_db) == schema


def test_create_tables_twice_keeps_the_rows(plugin_db):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute("INSERT INTO video_producer_projects (id, user_id, name, doc) VALUES ('p-1', 'user-1', 'Trailer', '{}')")
        cursor.execute(
            "INSERT INTO video_producer_calibration (preset_id, backend_id, resolution, seconds, duration_ms) "
            "VALUES ('preset', 'backend', '832x480', 5.0, 61000)"
        )

    create_tables()

    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, user_id, name, doc FROM video_producer_projects")
        assert [tuple(row) for row in cursor.fetchall()] == [("p-1", "user-1", "Trailer", "{}")]
        cursor.execute("SELECT preset_id, seconds, duration_ms FROM video_producer_calibration")
        assert [tuple(row) for row in cursor.fetchall()] == [("preset", 5.0, 61000)]


def test_a_new_project_starts_at_version_one_and_a_job_reserves_nothing_by_default(plugin_db):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute("INSERT INTO video_producer_projects (id, user_id, name, doc) VALUES ('p-1', 'user-1', 'Trailer', '{}')")
        cursor.execute("INSERT INTO video_producer_jobs (id, take_id) VALUES ('j-1', 't-1')")

    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT version, created_at, updated_at FROM video_producer_projects")
        project = cursor.fetchone()
        cursor.execute("SELECT units_reserved, started_at, finished_at FROM video_producer_jobs")
        job = cursor.fetchone()
    assert project["version"] == 1 and project["created_at"] and project["updated_at"]
    assert job["units_reserved"] == 0 and job["started_at"] and job["finished_at"] is None


def test_the_project_document_cannot_be_left_out(plugin_db):
    create_tables()

    with pytest.raises(Exception, match="NOT NULL"):
        with plugin_db.get_cursor() as cursor:
            cursor.execute("INSERT INTO video_producer_projects (id, user_id, name) VALUES ('p-1', 'user-1', 'Trailer')")


def test_a_missing_column_is_added_and_the_rows_are_kept(plugin_db, monkeypatch):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute("INSERT INTO video_producer_projects (id, user_id, name, doc) VALUES ('p-1', 'user-1', 'Trailer', '{}')")
    monkeypatch.setattr(
        tables,
        "_ADDED_COLUMNS",
        (
            ("video_producer_projects", "archived", "INTEGER NOT NULL DEFAULT 0"),
            ("video_producer_projects", "cover_path", "TEXT"),
        ),
    )

    create_tables()

    assert _columns(plugin_db, "video_producer_projects") == _EXPECTED_COLUMNS["video_producer_projects"] + [
        "archived",
        "cover_path",
    ]
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, name, archived, cover_path FROM video_producer_projects")
        assert [tuple(row) for row in cursor.fetchall()] == [("p-1", "Trailer", 0, None)]


def test_an_added_column_is_not_added_twice(plugin_db, monkeypatch):
    monkeypatch.setattr(tables, "_ADDED_COLUMNS", (("video_producer_takes", "note", "TEXT"),))

    create_tables()
    create_tables()

    assert _columns(plugin_db, "video_producer_takes").count("note") == 1


def test_a_takes_table_from_an_older_version_gets_the_new_column_and_keeps_its_rows(plugin_db, monkeypatch):
    with plugin_db.get_cursor() as cursor:
        cursor.execute(
            "CREATE TABLE video_producer_takes (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, shot_id TEXT NOT NULL, "
            "generation_id TEXT, quality TEXT NOT NULL, kind TEXT NOT NULL, parent_take_id TEXT, preset_id TEXT, "
            "mode TEXT, backend_id TEXT, resolution TEXT, status TEXT NOT NULL, file_path TEXT, thumb_path TEXT, "
            "width INTEGER, height INTEGER, duration_s REAL, fps REAL, error_code TEXT, error_message TEXT, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMP)"
        )
        cursor.execute(
            "INSERT INTO video_producer_takes (id, project_id, shot_id, quality, kind, status) "
            "VALUES ('t-1', 'p-1', 's-1', 'draft', 'video', 'done')"
        )
    monkeypatch.setattr(tables, "_ADDED_COLUMNS", (("video_producer_takes", "seed", "INTEGER"),))

    create_tables()
    create_tables()

    assert "seed" in _columns(plugin_db, "video_producer_takes")
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, status, seed FROM video_producer_takes")
        assert [tuple(row) for row in cursor.fetchall()] == [("t-1", "done", None)]
    assert set(_indexes(plugin_db)) == set(_EXPECTED_INDEXES)


def test_the_versions_table_adds_the_source_version_column():
    assert ("video_producer_versions", "source_version", "INTEGER") in tables._ADDED_COLUMNS


def test_a_new_take_is_not_chosen_and_reserves_nothing_by_default(plugin_db):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO video_producer_takes (id, project_id, shot_id, quality, kind, status) "
            "VALUES ('t-1', 'p-1', 's-1', 'draft', 'render', 'queued')"
        )
        cursor.execute("SELECT chosen, units_reserved, progress, user_id, request FROM video_producer_takes")
        assert tuple(cursor.fetchone()) == (0, 0, None, None, None)


def test_a_takes_table_from_step_three_gets_every_take_column_and_keeps_its_rows(plugin_db):
    create_tables()
    with plugin_db.get_cursor() as cursor:
        cursor.execute("DROP TABLE video_producer_takes")
        cursor.execute(f"CREATE TABLE video_producer_takes ({tables._COLUMNS['video_producer_takes']})")
        cursor.execute(
            "INSERT INTO video_producer_takes (id, project_id, shot_id, quality, kind, status, seed) "
            "VALUES ('t-1', 'p-1', 's-1', 'draft', 'render', 'done', 7)"
        )

    create_tables()

    assert _columns(plugin_db, "video_producer_takes") == _EXPECTED_COLUMNS["video_producer_takes"]
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, seed, chosen, units_reserved, variant FROM video_producer_takes")
        assert [tuple(row) for row in cursor.fetchall()] == [("t-1", 7, 0, 0, None)]


def test_a_versions_table_from_an_older_version_gets_the_source_version_and_keeps_its_rows(plugin_db):
    with plugin_db.get_cursor() as cursor:
        cursor.execute(
            "CREATE TABLE video_producer_versions (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
            "version INTEGER NOT NULL, doc TEXT NOT NULL, label TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor.execute(
            "INSERT INTO video_producer_versions (id, project_id, version, doc, label) VALUES ('v-1', 'p-1', 1, '{}', 'First')"
        )

    create_tables()
    create_tables()

    assert _columns(plugin_db, "video_producer_versions") == _EXPECTED_COLUMNS["video_producer_versions"]
    with plugin_db.get_cursor() as cursor:
        cursor.execute("SELECT id, version, label, source_version FROM video_producer_versions")
        assert [tuple(row) for row in cursor.fetchall()] == [("v-1", 1, "First", None)]
