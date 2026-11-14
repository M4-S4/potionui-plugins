import json

import pytest

from potion_audit.cleanup import matrix_cleanup
from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.inputs import creation
from potion_audit.matrix import run_profile
from potion_audit.pack import load_pack
from potion_audit.run import RunRefused

from conftest import PASSWORD, USER
from packs import write_pack

OLD = "2026-01-01T00:00:00+00:00"


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


def test_a_run_records_whether_each_upload_was_created_or_reused(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    first = segment(fake_api, pack, tmp_path, "seg-1")
    assert [(item["filename"], item["created"]) for item in recorded(first).values()] == [("1-bottle.png", True), ("2-mask.png", True)]
    fake_api.dedupe = True
    second = segment(fake_api, pack, tmp_path, "seg-2")
    assert [(item["filename"], item["created"]) for item in recorded(second).values()] == [("1-bottle.png", False), ("2-mask.png", False)]
    assert next(iter(recorded(second).values()))["created_proof"].startswith("the library of the account did not grow")


def test_an_unreadable_library_leaves_the_creation_unknown(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    fake_api.library_readable = False
    run_dir = segment(fake_api, pack, tmp_path, "seg-3")
    assert [item["created"] for item in recorded(run_dir).values()] == [None, None]


def test_the_creation_proof_needs_one_more_file_and_this_one_on_top():
    assert creation((5, "A"), (6, "B"), "B")[0] is True
    assert creation((5, "A"), (5, "A"), "Z")[0] is False
    assert creation((5, "A"), (7, "B"), "B")[0] is None
    assert creation((5, "A"), (6, "C"), "B")[0] is None
    assert creation(None, (6, "B"), "B")[0] is None


def test_cleanup_lists_then_deletes_the_generations_and_the_files_the_run_created(fake_api, config_file, credentials_env, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-4")
    fake_api.add_file("someone.png", "someone.png")
    lines = []
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, lines.append)
    assert [(item["id"], item["on_instance"]) for item in plan["generations"]] == [("G1", True)]
    assert files_of(plan) == [("1-bottle.png", True, True), ("2-mask.png", True, True)]
    assert lines[-1].startswith("1 of 1 generations and 2 files of seg-4 to delete: pass --confirm")
    assert not [method for method, _ in fake_api.methods() if method == "DELETE"]
    assert not (run_dir / "cleanup.json").exists()
    assert main(["cleanup", str(run_dir), "--config", str(config_file), "--confirm"]) == 0
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


def test_a_run_made_before_the_records_deletes_only_what_the_instance_dates_inside_it(fake_api, tmp_path, case_file):
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
    assert plan["files"][0]["proof"] == f"created at {OLD}, outside seg-7"
    assert "during seg-7" in plan["files"][1]["proof"]
    assert fake_api.deleted == ["/api/generations/history/G1", "/api/media/uploads/2-mask.png"]
    matrix_cleanup(logged_in(fake_api), [run_dir], True, quiet)
    assert (run_dir / "cleanup.json").is_file() and (run_dir / "cleanup-2.json").is_file()
    again = json.loads((run_dir / "cleanup-2.json").read_text(encoding="utf-8"))
    assert [(item["on_instance"], item.get("exists_after")) for item in again["generations"]] == [(False, False)]


def test_a_recorded_id_that_does_not_match_the_library_keeps_the_file(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    run_dir = segment(fake_api, pack, tmp_path, "seg-8")
    uploads = recorded(run_dir)
    next(iter(uploads.values()))["id"] = "SOMEONE"
    (run_dir / "uploads.json").write_text(json.dumps(uploads), encoding="utf-8")
    plan = matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
    assert files_of(plan) == [("1-bottle.png", False, True), ("2-mask.png", True, True)]


def test_cleanup_refuses_a_folder_that_is_not_a_matrix_run(fake_api, tmp_path, case_file):
    pack = made_pack(tmp_path, case_file)
    with pytest.raises(RunRefused, match="holds no run.json"):
        matrix_cleanup(logged_in(fake_api), [tmp_path], False, quiet)
    run_dir = segment(fake_api, pack, tmp_path, "seg-9")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    (run_dir / "run.json").write_text(json.dumps({**run, "dry_run": True}), encoding="utf-8")
    with pytest.raises(RunRefused, match="dry run"):
        matrix_cleanup(logged_in(fake_api), [run_dir], False, quiet)
