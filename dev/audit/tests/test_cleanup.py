import json
from datetime import UTC, datetime, timedelta

import pytest

from potion_audit.cleanup import attribute, candidate, matrix_cleanup, run_span
from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.inputs import creation
from potion_audit.matrix import run_profile
from potion_audit.pack import load_pack
from potion_audit.run import RunRefused

from conftest import PASSWORD, USER

from packs import write_pack

OLD = "2026-01-01T00:00:00+00:00"
T0 = datetime(2026, 11, 14, 20, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def logged_in(fake_api) -> ApiClient:
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def quiet(line: str) -> None:
    return None


def made_pack(tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    assert main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")]) == 0
    return load_pack(path)


def segment(fake_api, pack, tmp_path, run_id):
    clock = FakeClock()
    run_profile(logged_in(fake_api), pack, "full", tmp_path / "out", run_id, beyond_tier=True, clock=clock, sleep=clock.sleep, log=quiet)
    return tmp_path / "out" / run_id


def recorded(run_dir):
    return json.loads((run_dir / "uploads.json").read_text(encoding="utf-8"))


def files_of(plan):
    return [(item["filename"], item["attributed"], item["on_instance"]) for item in plan["files"]]


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def old_run(run_dir, start: float, end: float, strip_created: bool = True) -> None:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run.pop("library_start")
    run.pop("library_end")
    run.update(started_at=at(start), ended_at=at(end))
    (run_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")
    if strip_created:
        uploads = recorded(run_dir)
        for item in uploads.values():
            item.pop("created")
            item.pop("created_proof")
        (run_dir / "uploads.json").write_text(json.dumps(uploads), encoding="utf-8")


def test_a_run_records_whether_each_upload_was_created_or_reused_and_the_library_around_it(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    first = segment(fake_api, pack, tmp_path, "seg-1")
    assert [(item["filename"], item["created"]) for item in recorded(first).values()] == [("1-bottle.png", True), ("2-mask.png", True)]
    run = json.loads((first / "run.json").read_text(encoding="utf-8"))
    assert (run["library_start"]["total"], run["library_start"]["id"]) == (0, None)
    assert (run["library_end"]["total"], run["library_end"]["id"]) == (2, "01F0002")
    fake_api.dedupe = True
    second = segment(fake_api, pack, tmp_path, "seg-2")
    assert [(item["filename"], item["created"]) for item in recorded(second).values()] == [("1-bottle.png", False), ("2-mask.png", False)]
    assert next(iter(recorded(second).values()))["created_proof"].startswith("the library of the account did not grow")


def test_an_unreadable_library_leaves_the_creation_unknown(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    fake_api.library_readable = False
    run_dir = segment(fake_api, pack, tmp_path, "seg-3")
    assert [item["created"] for item in recorded(run_dir).values()] == [None, None]
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert (run["library_start"], run["library_end"]) == (None, None)


def test_the_creation_proof_needs_one_more_file_and_this_one_on_top():
    def mark(total, newest):
        return {"total": total, "id": newest, "created_at": OLD}

    assert creation(mark(5, "A"), mark(6, "B"), "B")[0] is True
    assert creation(mark(5, "A"), mark(5, "A"), "Z")[0] is False
    assert creation(mark(5, "A"), mark(7, "B"), "B")[0] is None
    assert creation(mark(5, "A"), mark(6, "C"), "B")[0] is None
    assert creation(None, mark(6, "B"), "B")[0] is None


def test_cleanup_lists_then_deletes_the_generations_and_the_files_the_run_created(fake_api, config_file, credentials_env, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-4")
    fake_api.add_file("someone.png", "someone.png")
    lines = []
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, lines.append)
    assert [(item["id"], item["on_instance"]) for item in plan["generations"]] == [("G1", True)]
    assert files_of(plan) == [("1-bottle.png", True, True), ("2-mask.png", True, True)]
    assert abs(plan["clock"]["server_offset_seconds"]) < 2 and plan["clock"]["margin_seconds"] >= 2
    assert lines[-1] == "1 generations and 2 files of seg-4 to delete: pass --confirm to delete them; not attributed and kept: 0 generations, 0 files; already gone: 0 generations, 0 files"
    assert lines[0] == "seg-4 ran with this account on this instance"
    assert not [method for method, _ in fake_api.methods() if method == "DELETE"]
    assert not (run_dir / "cleanup.json").exists()
    assert main(["cleanup", str(run_dir.parent / "seg-4"), "--config", str(config_file), "--confirm"]) == 0
    assert fake_api.deleted == ["/api/generations/history/G1", "/api/media/uploads/1-bottle.png", "/api/media/uploads/2-mask.png"]
    assert [row["filename"] for row in fake_api.listed()] == ["someone.png"]
    trace = json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))
    assert trace["run_id"] == "seg-4" and trace["generations"][0]["exists_after"] is False
    assert [(item["filename"], item["deleted"], item["exists_after"]) for item in trace["files"]] == [("1-bottle.png", True, False), ("2-mask.png", True, False)]


def test_a_file_reused_by_a_segment_is_kept_unless_another_segment_created_it(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    first = segment(fake_api, pack, tmp_path, "seg-5")
    fake_api.dedupe = True
    second = segment(fake_api, pack, tmp_path, "seg-6")
    alone = matrix_cleanup(logged_in(fake_api), [second], False, quiet)
    assert files_of(alone) == [("1-bottle.png", False, True), ("2-mask.png", False, True)]
    both = matrix_cleanup(logged_in(fake_api), [first, second], False, quiet)
    assert files_of(both) == [("1-bottle.png", True, True), ("2-mask.png", True, True)]
    assert both["files"][0]["runs"] == ["seg-5", "seg-6"]
    matrix_cleanup(logged_in(fake_api), [second], True, quiet)
    assert [path for path in fake_api.deleted if "/media/" in path] == []


def test_without_created_the_library_marks_of_the_run_decide(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    fake_api.dedupe = True
    fake_api.add_file("old-bottle.png", "bottle.png", OLD, (pack.root / "inputs" / "bottle.png").read_bytes(), "OLD1")
    run_dir = segment(fake_api, pack, tmp_path, "seg-7")
    uploads = recorded(run_dir)
    for item in uploads.values():
        item.pop("created")
        item.pop("created_proof")
    (run_dir / "uploads.json").write_text(json.dumps(uploads), encoding="utf-8")
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    assert files_of(plan) == [("old-bottle.png", False, True), ("2-mask.png", True, True)]
    assert plan["files"][0]["proof"] == "created at 2026-01-01T00:00:00+00:00, outside the library files seg-7 saw appear"
    assert "after the newest library file at the start of seg-7" in plan["files"][1]["proof"]
    assert fake_api.deleted == ["/api/generations/history/G1", "/api/media/uploads/2-mask.png"]
    matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    assert (run_dir / "cleanup.json").is_file() and (run_dir / "cleanup-2.json").is_file()
    again = json.loads((run_dir / "cleanup-2.json").read_text(encoding="utf-8"))
    assert [(item["on_instance"], item["attributed"]) for item in again["generations"]] == [(False, None)]
    assert (again["state"], again["counts"]["generations"]) == ("done", {"deleted": 0, "not_deleted": 0, "not_tried": 0})


def test_a_run_made_before_the_marks_attributes_by_its_window_less_the_clock_margin(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-8")
    old_run(run_dir, 0, 600)
    rows = {row["filename"]: row for row in fake_api.library}
    rows["1-bottle.png"]["created_at"] = at(1)
    rows["2-mask.png"]["created_at"] = at(300)
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    margin = plan["clock"]["margin_seconds"]
    assert files_of(plan) == [("1-bottle.png", False, True), ("2-mask.png", True, True)]
    assert plan["files"][0]["proof"] == f"created at {at(1)}, outside seg-8 less {margin} s at each end"
    assert plan["files"][1]["proof"].startswith(f"created at {at(300)}, during seg-8")


def test_a_reuse_recorded_by_a_run_is_not_undone_by_its_window_or_its_project():
    span = {"run": "vp-1", "window": (T0, T0 + timedelta(seconds=600)), "marks": None}
    rows = {"a.png": {"id": "L1", "filename": "a.png", "original_filename": "lumi.jpg", "created_at": at(100)}}
    item = candidate("a.png", "upload", span, upload_id="L1", created=False)
    item["evidence"] += candidate("a.png", "project_asset", span, upload_id="L1")["evidence"]
    found = attribute(item, rows, 2.0)
    assert found["attributed"] is False
    assert found["proof"] == "uploads.json of vp-1 records that the server answered a file it already held"
    assert attribute(candidate("a.png", "project_asset", span, upload_id="L1"), rows, 2.0)["attributed"] is True


def test_the_library_marks_override_a_window_that_a_clock_drift_would_widen():
    marks = ((T0, "B5"), (T0 + timedelta(seconds=600), "C9"))
    span = {"run": "vp-2", "window": (T0 - timedelta(seconds=300), T0 + timedelta(seconds=600)), "marks": marks}
    before = {"a.png": {"id": "B4", "filename": "a.png", "original_filename": None, "created_at": at(-10)}}
    during = {"a.png": {"id": "B6", "filename": "a.png", "original_filename": None, "created_at": at(10)}}
    after = {"a.png": {"id": "D1", "filename": "a.png", "original_filename": None, "created_at": at(900)}}
    assert attribute(candidate("a.png", "chain_frame", span, upload_id="B4"), before, 2.0)["attributed"] is False
    assert attribute(candidate("a.png", "chain_frame", span, upload_id="B6"), during, 2.0)["attributed"] is True
    assert attribute(candidate("a.png", "chain_frame", span, upload_id="D1"), after, 2.0)["attributed"] is False
    empty = {"run": "vp-3", "window": None, "marks": (None, (T0 + timedelta(seconds=600), "C9"))}
    assert attribute(candidate("a.png", "chain_frame", empty, upload_id="B6"), during, None)["attributed"] is True


def test_a_window_proof_needs_a_recorded_id_and_a_readable_clock():
    span = {"run": "vp-4", "window": (T0, T0 + timedelta(seconds=600)), "marks": None}
    rows = {"a.png": {"id": "L1", "filename": "a.png", "original_filename": None, "created_at": at(100)}}
    found = attribute(candidate("a.png", "chain_frame", span), rows, 2.0)
    assert (found["attributed"], found["proof"]) == (False, "the runs recorded no library id for it")
    found = attribute(candidate("a.png", "upload", span, created=True), rows, 2.0)
    assert (found["attributed"], found["proof"]) == (False, "the runs recorded no library id for it")
    found = attribute(candidate("a.png", "chain_frame", span, upload_id="L1"), rows, None)
    assert (found["attributed"], found["proof"]) == (False, "vp-4 recorded no library marks, and the clock of the server could not be read")


def test_marks_that_cannot_be_read_back_leave_the_window():
    record = {"started_at": at(0), "ended_at": at(60), "library_start": {"total": 1, "id": "A1", "created_at": "not a time"}, "library_end": {"total": 2, "id": "A2", "created_at": at(50)}}
    assert run_span("r", record)["marks"] is None
    record["library_start"] = {"total": 0, "id": None, "created_at": None}
    assert run_span("r", record)["marks"] == (None, (T0 + timedelta(seconds=50), "A2"))


def test_a_recorded_id_that_does_not_match_the_library_keeps_the_file(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-9")
    uploads = recorded(run_dir)
    next(iter(uploads.values()))["id"] = "SOMEONE"
    (run_dir / "uploads.json").write_text(json.dumps(uploads), encoding="utf-8")
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    assert files_of(plan) == [("1-bottle.png", False, True), ("2-mask.png", True, True)]


def test_an_error_while_deleting_is_recorded_and_the_trace_is_written(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-10")
    route = fake_api.route

    def failing(method, path, query, body, headers):
        if method == "DELETE" and path == "/api/media/uploads/1-bottle.png":
            return 503, {"detail": "the instance is restarting"}, "application/json"
        return route(method, path, query, body, headers)

    fake_api.route = failing
    lines = []
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], True, lines.append)
    assert "HTTP 503" in plan["files"][0]["error"] and plan["files"][0]["exists_after"] is None
    assert plan["files"][1]["deleted"] is True
    assert "1 of 1 generations and 1 of 2 files deleted; not deleted: 0 generations, 1 files; not tried: 0" in lines[-1]
    assert plan["failed"] is True
    trace = json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))
    assert "HTTP 503" in trace["files"][0]["error"]


def test_cleanup_refuses_a_folder_that_is_not_a_matrix_run(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    with pytest.raises(RunRefused, match="holds no run.json"):
        matrix_cleanup(logged_in(fake_api), [tmp_path], False, quiet)
    run_dir = segment(fake_api, pack, tmp_path, "seg-11")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    (run_dir / "run.json").write_text(json.dumps({**run, "dry_run": True}), encoding="utf-8")
    with pytest.raises(RunRefused, match="dry run"):
        matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)


def test_a_start_mark_without_an_id_is_an_empty_library_only_when_the_total_is_nought():
    record = {"started_at": at(0), "ended_at": at(60), "library_start": {"total": 4, "id": None, "created_at": None}, "library_end": {"total": 5, "id": "A2", "created_at": at(50)}}
    assert run_span("r", record)["marks"] is None
    record["library_start"]["total"] = 0
    assert run_span("r", record)["marks"] == (None, (T0 + timedelta(seconds=50), "A2"))


def test_the_clock_margin_has_a_floor_of_a_minute(fake_api):
    from potion_audit.cleanup import clock_margin

    found = clock_margin(logged_in(fake_api))
    assert abs(found["server_offset_seconds"]) < 2 and found["margin_seconds"] == 60.0 and found["measured"] == "when the cleanup runs"


def test_a_generation_whose_record_does_not_match_the_run_is_kept(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-12")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    fake_api.record_extra = {"created_at": run["started_at"], "preset_id": "01SOMEOTHERPRESET"}
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    assert plan["generations"][0]["attributed"] is False
    assert plan["generations"][0]["proof"].startswith("its preset is 01SOMEOTHERPRESET, the run recorded ")
    fake_api.record_extra = {"created_at": run["started_at"], "mode": "img2img"}
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    assert [item["proof"] for item in plan["generations"]] == ["its mode is img2img, the run recorded txt2img"]
    fake_api.record_extra = {"created_at": "2026-01-01T00:00:00+00:00"}
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    assert plan["generations"][0]["proof"] == "created at 2026-01-01T00:00:00+00:00, more than 60.0 s outside the run"
    fake_api.record_extra = {"created_at": run["started_at"]}
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    assert plan["generations"][0]["attributed"] is True and "during the run" in plan["generations"][0]["proof"]
    assert "/api/generations/history/G1" not in fake_api.deleted


def test_a_matrix_cleanup_takes_a_night_folder_and_refuses_a_run_with_no_end(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    first = segment(fake_api, pack, tmp_path, "night-1")
    second = segment(fake_api, pack, tmp_path, "night-2")
    night = tmp_path / "out" / "night"
    night.mkdir()
    (night / "night.json").write_text(json.dumps({"run_id": "night", "segments": [{"run_id": "night-1"}, {"run_id": "night-2"}]}), encoding="utf-8")
    plan = matrix_cleanup(logged_in(fake_api), [night], False, quiet)
    assert plan["segments"] == ["night-1", "night-2"]
    run = json.loads((second / "run.json").read_text(encoding="utf-8"))
    run["ended_at"] = None
    (second / "run.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(RunRefused, match="night-2 recorded no end"):
        matrix_cleanup(logged_in(fake_api), [night], True, quiet)
    assert fake_api.deleted == [] and not (first / "cleanup.json").exists()


def test_a_matrix_cleanup_stops_when_the_instance_cannot_be_reached(fake_api, config_file, credentials_env, tmp_path, case_file):
    from potion_audit.client import ApiUnreachable

    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-13")
    client = logged_in(fake_api)
    deleted = []

    def gone(path, missing_ok=False):
        deleted.append(path)
        raise ApiUnreachable(f"DELETE {path}: connection refused")

    client.delete_json = gone
    plan = matrix_cleanup(client, [run_dir], True, quiet)
    assert deleted == ["/api/generations/history/G1"]
    assert plan["failed"] is True and plan["counts"]["files"] == {"deleted": 0, "not_deleted": 0, "not_tried": 2}
    assert plan["stopped"].startswith("not tried: the cleanup stopped after DELETE /api/generations/history/G1: connection refused")


def test_a_matrix_run_refuses_to_start_in_a_folder_already_cleaned(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-14")
    matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    with pytest.raises(RunRefused, match="holds the trace of a cleanup"):
        segment(fake_api, pack, tmp_path, "seg-14")


def test_the_fake_server_reuses_the_newest_file_with_the_same_bytes(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    data = (pack.root / "inputs" / "bottle.png").read_bytes()
    fake_api.dedupe = True
    fake_api.add_file("older.png", "bottle.png", "2026-01-01T00:00:00+00:00", data, "01A")
    fake_api.add_file("newer.png", "bottle.png", "2026-02-01T00:00:00+00:00", data, "01B")
    run_dir = segment(fake_api, pack, tmp_path, "seg-15")
    assert next(iter(recorded(run_dir).values()))["filename"] == "newer.png"


def test_a_matrix_cleanup_keeps_a_file_that_a_video_producer_project_points_to(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-16")
    bottle = next(row for row in fake_api.library if row["filename"] == "1-bottle.png")
    fake_api.vp_projects["P5"] = {"id": "P5", "name": "my film", "version": 3, "doc": {"assets": [{"id": "a1", "origin": {"kind": "library", "itemId": bottle["id"]}}]}}
    lines = []
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], True, lines.append)
    assert files_of(plan) == [("1-bottle.png", False, True), ("2-mask.png", True, True)]
    assert plan["files"][0]["proof"] == "the document of the Video Producer project P5 points to it"
    assert "/api/media/uploads/1-bottle.png" not in fake_api.deleted and "/api/media/uploads/2-mask.png" in fake_api.deleted
    trace = json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))
    assert trace["files"][0]["proof"] == "the document of the Video Producer project P5 points to it"


def test_a_matrix_cleanup_keeps_every_file_when_the_video_producer_projects_cannot_be_read(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-17")
    fake_api.vp_readable = False
    lines = []
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], True, lines.append)
    assert files_of(plan) == [("1-bottle.png", False, True), ("2-mask.png", False, True)]
    assert plan["files"][0]["proof"].startswith("the Video Producer projects of the account could not be read (GET /api/plugins/video-producer/projects answered HTTP 503")
    assert any(line.startswith("the Video Producer projects of the account could not be read") and line.endswith(", so the files of the run are kept") for line in lines)
    assert [path for path in fake_api.deleted if "/media/" in path] == []


def test_a_trace_that_cannot_be_written_stops_the_deletions_and_names_its_part_file(fake_api, config_file, credentials_env, tmp_path, case_file, monkeypatch, capsys):
    import pathlib

    import potion_audit.cleanup as cleanup_module

    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-18")
    monkeypatch.setattr(cleanup_module, "TRACE_PAUSE_SECONDS", 0)
    replace = pathlib.Path.replace
    calls = []

    def held(self, target):
        if pathlib.Path(target).name == "cleanup.json":
            calls.append(1)
            if len(calls) > 1:
                raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return replace(self, target)

    monkeypatch.setattr(pathlib.Path, "replace", held)
    assert main(["cleanup", str(run_dir), "--config", str(config_file), "--confirm"]) == 1
    assert fake_api.deleted == ["/api/generations/history/G1"]
    out = capsys.readouterr().out
    assert f"the trace cleanup.json could not be written after 3 attempts" in out and "cleanup.json.part holds the latest state written" in out
    assert len(calls) == 1 + 3 + 3
    assert json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))["state"] == "deleting"
    last = json.loads((run_dir / "cleanup.json.part").read_text(encoding="utf-8"))
    assert last["state"] == "stopped" and last["generations"][0]["exists_after"] is False


def test_a_trace_that_cannot_be_written_at_all_deletes_nothing(fake_api, tmp_path, case_file, monkeypatch):
    import pathlib

    import potion_audit.cleanup as cleanup_module

    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-19")
    monkeypatch.setattr(cleanup_module, "TRACE_PAUSE_SECONDS", 0)

    def held(self, target):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(pathlib.Path, "replace", held)
    with pytest.raises(RunRefused, match="nothing was deleted: the trace cleanup.json could not be written"):
        matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    assert fake_api.deleted == []
