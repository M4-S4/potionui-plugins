import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.inputs import _encode
from potion_audit.pack import DEFAULT_PACK, load_pack
from potion_audit.run import RunRefused
from potion_audit.vp_scenario import SHOTS, VP, cleanup, load_matrix, run_scenario, select_engines

from conftest import PASSWORD, USER, FakeApi, bundle_bytes, envelope

H3 = "plugin:video-producer/MiniMax-H3-12GB"
H3_ID = "01M54HN72B0KY7H63BKQ16T253"
WAN13 = "plugin:video-producer/Wan2.1-T2V-1.3B-8GB"
FAST = "plugin:video-producer/MiniMax-H3-Fast-12GB"
ALL = ["plugin:video-producer/Wan2.1-T2V-1.3B-8GB", "plugin:video-producer/Wan2.2-TI2V-5B-8GB", "plugin:video-producer/Wan2.2-14B-Lightning-12GB", H3, FAST]


def clip_bytes(tmp_path: Path, name: str, seconds: float, fps: int = 24, value: int = 120) -> bytes:
    path = tmp_path / name
    frames = [np.full((64, 64, 3), (value + index) % 256, dtype=np.uint8) for index in range(round(seconds * fps))]
    _encode(frames, path, Fraction(fps), 64, 64, 30)
    return path.read_bytes()


class VpFakeApi(FakeApi):
    def __init__(self, tmp_path: Path):
        super().__init__()
        self.outputs = {"0.mp4": clip_bytes(tmp_path, "take.mp4", 1.0)}
        self.export_bytes = clip_bytes(tmp_path, "export.mp4", 15.0)
        self.projects = {}
        self.vp_takes = []
        self.orders = []
        self.puts = []
        self.deleted = []
        self.media_uploaded = []
        self.take_outcomes = []
        self.blocked_shots = set()

    def _handler(self):
        base = super()._handler()

        class Handler(base):
            def do_PUT(self):
                self._serve("PUT")

            def do_DELETE(self):
                self._serve("DELETE")

        return Handler

    def _new_take(self, project_id: str, shot_id: str, body: dict, kind: str = "render", parent: str | None = None) -> dict:
        take = {
            "id": f"T{len(self.vp_takes) + 1}",
            "project_id": project_id,
            "shot_id": shot_id,
            "generation_id": None,
            "quality": body.get("quality", "final"),
            "kind": kind,
            "parent_take_id": parent,
            "preset_id": body.get("preset_id"),
            "status": "queued",
            "variant": "A",
            "profile": None,
            "director_mode": None,
            "chain": None,
            "error_code": None,
            "error_message": None,
            "polls": 0,
        }
        doc = self.projects[project_id]["doc"]
        clip = next((item for item in doc["clips"] if item["id"] == shot_id), {})
        take["profile"] = (clip.get("engine") or {}).get("profile")
        if kind == "render":
            take["director_mode"] = "i2v" if clip.get("firstFromPrevious") else "t2v"
        if kind == "render" and clip.get("firstFromPrevious"):
            previous = doc["clips"][doc["clips"].index(clip) - 1]
            placed = previous.get("take")
            take["chain"] = {"previous": previous["id"], "state": "taken" if placed else "waiting", "source": {"shotId": previous["id"], "takeId": placed, "assetId": previous.get("assetId"), "at": None}}
        take["outcome"] = self.take_outcomes.pop(0) if self.take_outcomes else ("done", None)
        self.vp_takes.append(take)
        return take

    def _advance(self, take: dict) -> None:
        if take["status"] in ("done", "failed", "cancelled"):
            return
        take["polls"] += 1
        if take["polls"] < 2:
            return
        status, code = take["outcome"]
        take["generation_id"] = "G1"
        take["status"] = status
        self.final = "completed" if status == "done" else "failed"
        self.failure = {"error_code": code, "message": "CUDA driver error: device not ready"} if code else None
        if status == "done":
            take.update(file_path=f"storage/generations/G1/{take['id']}.mp4", url=f"/api/media/generations/G1/{take['id']}.mp4", file_id=7, width=64, height=64, duration_s=1.0, fps=24.0)
        else:
            take["error_code"] = code

    def _public(self, take: dict) -> dict:
        return {key: value for key, value in take.items() if key not in ("polls", "outcome")}

    def _stored_uploads(self) -> set[str]:
        return {f"{index + 1}-{name}" for index, name in enumerate(self.uploads)} - {path.rsplit("/", 1)[1] for path in self.deleted if path.startswith("/api/media/uploads/")}

    def route(self, method, path, query, body, headers):
        if path.startswith("/api/media/uploads/") and method in ("GET", "DELETE"):
            if headers.get("Authorization") != "Bearer fake-token-123":
                return 401, {"detail": "Not authenticated"}, "application/json"
            name = path[len("/api/media/uploads/"):]
            if method == "GET" and name.endswith("/info"):
                if name[: -len("/info")] in self._stored_uploads():
                    return 200, envelope({"filename": name[: -len("/info")], "size": 10}), "application/json"
                return 400, {"success": False, "error": "not_found", "message": "Uploaded file not found"}, "application/json"
            if method == "DELETE":
                if name not in self._stored_uploads():
                    return 404, {"success": False, "error": "not_found"}, "application/json"
                self.deleted.append(path)
                return 200, envelope({"filename": name, "deleted": True}), "application/json"
        if not path.startswith(VP) and not (path.startswith("/api/generations/history/") and method in ("DELETE", "GET") and path.count("/") == 4):
            return super().route(method, path, query, body, headers)
        if headers.get("Authorization") != "Bearer fake-token-123":
            return 401, {"detail": "Not authenticated"}, "application/json"
        if path.startswith("/api/generations/history/"):
            generation_id = path.rsplit("/", 1)[1]
            if method == "DELETE":
                self.deleted.append(path)
                return 200, envelope({"message": "Generation deleted successfully."}), "application/json"
            if any(item.endswith("/" + generation_id) for item in self.deleted):
                return 404, {"detail": "not found"}, "application/json"
            return super().route(method, path, query, body, headers)
        rest = path[len(VP):]
        payload = json.loads(body) if body else None
        if rest == "/health":
            return 200, envelope({"status": "ok", "plugin": "video-producer", "version": "0.1.0"}), "application/json"
        if rest == "/media/uploaded" and method == "POST":
            self.media_uploaded.append(payload["filename"])
            return 200, envelope({"media": {"kind": "library", "media_type": "image", "url": f"/api/media/uploads/{payload['filename']}", "filename": payload["filename"], "origin": {"kind": "library", "itemId": f"I{len(self.media_uploaded)}"}}}), "application/json"
        if rest == "/projects" and method == "POST":
            project_id = f"P{len(self.projects) + 1}"
            self.projects[project_id] = {"id": project_id, "name": payload["name"], "version": 1, "doc": payload["doc"]}
            return 201, envelope({"project": self.projects[project_id]}), "application/json"
        if rest == "/projects" and method == "GET":
            return 200, envelope({"projects": [{"id": item["id"], "name": item["name"]} for item in self.projects.values()]}), "application/json"
        parts = rest.strip("/").split("/")
        if parts[0] == "projects" and len(parts) >= 2:
            project = self.projects.get(parts[1])
            if project is None:
                return 404, {"success": False, "error": "project_not_found", "message": "The project does not exist."}, "application/json"
            tail = parts[2:]
            if not tail and method == "GET":
                return 200, envelope({"project": project}), "application/json"
            if not tail and method == "PUT":
                if payload["version"] != project["version"]:
                    return 409, {"success": False, "error": "version_conflict"}, "application/json"
                self.puts.append(payload)
                project.update(doc=payload["doc"], version=project["version"] + 1)
                return 200, envelope({"project": project}), "application/json"
            if not tail and method == "DELETE":
                del self.projects[parts[1]]
                self.deleted.append(path)
                return 200, envelope({"deleted": parts[1]}), "application/json"
            if tail == ["generate"]:
                self.orders.append(("generate", payload))
                if set(payload["shots"]) & self.blocked_shots:
                    return 409, {"success": False, "error": "blocked", "message": "The preset cannot start a shot from an image."}, "application/json"
                created = [self._new_take(parts[1], shot, payload) for shot in payload["shots"]]
                return 202, envelope({"takes": [self._public(take) for take in created]}), "application/json"
            if tail == ["final-pass"]:
                self.orders.append(("final-pass", payload))
                created = []
                for take_id in payload["takes"]:
                    source = next(take for take in self.vp_takes if take["id"] == take_id)
                    created.append(self._new_take(parts[1], source["shot_id"], {"quality": "final", "preset_id": "01KXRTXUPSCALE0000000000RU"}, "final", take_id))
                return 202, envelope({"takes": [self._public(take) for take in created]}), "application/json"
            if tail == ["takes"]:
                found = [take for take in self.vp_takes if take["project_id"] == parts[1]]
                for take in found:
                    self._advance(take)
                return 200, envelope({"takes": [self._public(take) for take in found]}), "application/json"
            if tail == ["looks"]:
                takes = [{"take_id": take["id"], "shot_id": take["shot_id"], "status": "done", "cards": [{"card": "card-lumi", "score": 0.72}], "identity": {"score": 0.81}} for take in self.vp_takes if take["project_id"] == parts[1] and take["status"] == "done"]
                return 200, envelope({"embedder": {"available": True}, "faces": {"available": True}, "identity": {"available": True}, "thresholds": {"seam": 0.7}, "seams": [{"before": SHOTS[0]["id"], "after": SHOTS[1]["id"], "score": 0.91}], "takes": takes, "chains": [], "queued": 0}), "application/json"
            if tail == ["exports", "video"]:
                self.orders.append(("export", payload))
                return 202, envelope({"job": {"id": "J1", "status": "queued"}}), "application/json"
        if rest == "/exports/J1":
            return 200, envelope({"job": {"id": "J1", "status": "done", "file": {"size": len(self.export_bytes)}}}), "application/json"
        if rest == "/exports/J1/file":
            return 200, self.export_bytes, "application/zip"
        if parts[0] == "takes" and parts[-1] == "cancel":
            return 200, envelope({}), "application/json"
        return 404, {"detail": f"no fake route for {method} {path}"}, "application/json"


@pytest.fixture
def vp_api(tmp_path):
    api = VpFakeApi(tmp_path)
    api.thread.start()
    yield api
    api.server.shutdown()
    api.server.server_close()


@pytest.fixture
def vp_config(tmp_path, vp_api):
    path = tmp_path / "audit.toml"
    path.write_text(f'[target]\nurl = "{vp_api.url}"\nmode = "dedicated"\n\n[run]\noutput_dir = "out"\nmachine = "test-box"\n', encoding="utf-8")
    return path


def matrix_file(tmp_path: Path, verdicts: dict[str, str]) -> Path:
    cells = [{"cell": cell, "warm_repeat": False, "verdict": verdict, "run_seconds": 100 + index} for index, (cell, verdict) in enumerate(verdicts.items())]
    path = tmp_path / "matrix" / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_id": "matrix", "cells": cells}), encoding="utf-8")
    return path


def all_passed(**changes: str) -> dict[str, str]:
    verdicts = {f"{ref}:video": "PASS" for ref in ALL}
    verdicts[f"{H3}:refs"] = "PASS"
    verdicts["core/SeedVR2:video_upscale"] = "OOM"
    verdicts["plugin:nvidia-rtx-upscale/RTX-Upscale:video_upscale"] = "PASS"
    verdicts.update(changes)
    return verdicts


def logged_in(api) -> ApiClient:
    client = ApiClient(api.url)
    client.login(USER, PASSWORD)
    return client


def quiet(line: str) -> None:
    return None


def no_sleep(seconds: float) -> None:
    return None


def test_engines_come_from_the_matrix_or_from_the_option(tmp_path):
    pack = load_pack(DEFAULT_PACK)
    matrix = load_matrix([matrix_file(tmp_path, all_passed(**{f"{WAN13}:video": "FAIL"}))])
    engines = {engine["engine"]: engine for engine in select_engines(pack, matrix, None)}
    assert [ref for ref, engine in engines.items() if engine["selected"]] == [ref for ref in ALL if ref != WAN13]
    assert "FAIL" in engines[WAN13]["reason"]
    assert [ref for ref, engine in engines.items() if engine["ref2va"]] == [H3]
    assert "no refs mode" in engines[FAST]["ref2va_reason"]
    chosen = select_engines(pack, matrix, ["MiniMax-H3-12GB", WAN13])
    assert [(engine["key"], engine["selected"]) for engine in chosen if engine["selected"] or engine["engine"] == WAN13] == [("Wan2.1-T2V-1.3B-8GB", False), ("MiniMax-H3-12GB", True)]
    assert [engine["key"] for engine in select_engines(pack, None, ["wan2.2-ti2v-5b-8gb"]) if engine["selected"]] == ["Wan2.2-TI2V-5B-8GB"]
    with pytest.raises(RunRefused, match="--engines"):
        select_engines(pack, matrix, ["SDXL"])
    with pytest.raises(RunRefused, match="needs a matrix"):
        select_engines(pack, None, None)


def test_a_night_folder_reads_its_segments(tmp_path):
    for index, cell in enumerate(("a:video", "b:video"), start=1):
        folder = tmp_path / f"night-{index}"
        folder.mkdir()
        (folder / "run.json").write_text(json.dumps({"cells": [{"cell": cell, "verdict": "PASS", "run_seconds": 10 * index}, {"cell": cell, "warm_repeat": True, "verdict": "PASS", "run_seconds": 5}]}), encoding="utf-8")
    night = tmp_path / "night"
    night.mkdir()
    (night / "night.json").write_text(json.dumps({"segments": [{"run_id": "night-1"}, {"run_id": "night-2"}]}), encoding="utf-8")
    matrix = load_matrix([night])
    assert matrix["files"] == ["night-1/run.json", "night-2/run.json"]
    assert matrix["cells"]["b:video"] == {"verdicts": ["PASS", "PASS"], "cold_seconds": 20.0, "warm_seconds": 5.0}


def test_run_is_refused_without_confirm_gpu(vp_api, vp_config, credentials_env, tmp_path):
    code = main(["vp", "run", "--config", str(vp_config), "--engines", "MiniMax-H3-12GB"])
    assert code == 2
    assert vp_api.requests == []


def test_dry_run_builds_the_documents_and_the_generations_without_writing_on_the_instance(vp_api, vp_config, credentials_env, tmp_path):
    path = matrix_file(tmp_path, all_passed())
    code = main(["vp", "run", "--config", str(vp_config), "--matrix", str(path), "--dry-run", "--run-id", "vp-dry"])
    assert code == 0
    assert {method for method, path in vp_api.methods() if path != "/api/auth/login"} == {"GET"}
    assert vp_api.projects == {}
    plan = json.loads((tmp_path / "out" / "vp-dry" / "plan.json").read_text(encoding="utf-8"))
    assert plan["dry_run"] is True
    assert plan["plugin"]["version"] == "0.1.0"
    engines = {entry["key"]: entry for entry in plan["engines"]}
    h3 = engines["MiniMax-H3-12GB"]
    assert [(step["step"], step.get("shot"), step["status"]) for step in h3["steps"]] == [
        ("take", "s1-workshop", "planned"),
        ("take", "s2-bottle", "planned"),
        ("take", "s3-lumi", "planned"),
        ("final_pass", "s1-workshop", "not_run"),
        ("export", None, "planned"),
    ]
    assert "--upscaler rtx" in h3["steps"][3]["reason"]
    assert h3["steps"][1]["chained_on"] == "s1-workshop"
    assert h3["steps"][0]["estimate_basis"].startswith("run seconds of plugin:video-producer/MiniMax-H3-12GB:video")
    assert h3["steps"][2]["estimate_basis"].startswith("run seconds of plugin:video-producer/MiniMax-H3-12GB:refs")
    assert h3["estimate_seconds"] == sum(step["estimate_seconds"] for step in h3["steps"][:3])
    fast = engines["MiniMax-H3-Fast-12GB"]
    assert fast["steps"][2]["status"] == "skipped"
    assert plan["summary"]["engines"] == 5
    assert plan["summary"]["generations"] == 11
    doc = json.loads((tmp_path / "out" / "vp-dry" / "projects" / "MiniMax-H3-12GB.json").read_text(encoding="utf-8"))
    assert doc["name"] == "potion-audit vp-dry MiniMax-H3-12GB"
    assert [clip["firstFromPrevious"] for clip in doc["clips"]] == [False, True, False]
    assert [clip["engine"]["profile"] for clip in doc["clips"]] == ["FL2VA", "FL2VA", "Ref2VA"]
    assert doc["clips"][2]["cast"]["characters"] == ["card-lumi"]
    assert doc["bible"]["characters"][0]["references"] == ["ref-lumi"]
    assert [(reference["id"], reference["assetId"]) for reference in doc["references"]] == [("ref-lumi", "asset-lumi"), ("ref-bottle", "asset-bottle")]
    assert [asset["src"] for asset in doc["assets"]] == ["input:lumi", "input:bottle"]
    assert "Lumi" in doc["prompts"][2]["text"] and "{" not in doc["prompts"][2]["text"]


def test_a_run_creates_the_project_chains_the_second_shot_and_sends_the_references(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    matrix = load_matrix([matrix_file(tmp_path, all_passed())])
    engines = select_engines(pack, matrix, ["MiniMax-H3-12GB"])
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-1", engines, matrix, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    assert scenario["stopped"] is None
    assert len(vp_api.uploads) == 2 and vp_api.media_uploaded == ["1-lumi.jpg", "2-bottle.jpg"]
    project = vp_api.projects["P1"]
    assert project["name"] == "potion-audit vp-1 MiniMax-H3-12GB"
    assert [asset["origin"] for asset in project["doc"]["assets"][:2]] == [{"kind": "library", "itemId": "I1"}, {"kind": "library", "itemId": "I2"}]
    assert [(kind, body.get("shots") or body.get("takes") or body.get("format")) for kind, body in vp_api.orders] == [("generate", ["s1-workshop"]), ("generate", ["s2-bottle"]), ("generate", ["s3-lumi"]), ("final-pass", ["T1"]), ("export", "web")]
    assert vp_api.orders[3][1] == {"takes": ["T1"], "method": "upscale", "target": "fhd1080", "upscaler": "rtx"}
    assert vp_api.puts[0]["doc"]["clips"][0]["take"] == "T1"
    second = next(take for take in vp_api.vp_takes if take["shot_id"] == "s2-bottle")
    assert second["chain"]["state"] == "taken" and second["chain"]["source"]["takeId"] == "T1"
    assert vp_api.puts[-1]["doc"]["clips"][0]["take"] == "T4"
    entry = scenario["engines"][3]
    assert [(step["step"], step.get("verdict")) for step in entry["steps"]] == [("take", "PASS"), ("take", "PASS"), ("take", "PASS"), ("final_pass", "PASS"), ("export", "PASS")]
    run_dir = tmp_path / "out" / "vp-1"
    result = json.loads((run_dir / entry["steps"][1]["result"]).read_text(encoding="utf-8"))
    assert result["cell"] == "vp:plugin:video-producer/MiniMax-H3-12GB:s2-bottle"
    assert {check["check"]: check["ok"] for check in result["checks"]} == {"min_outputs": True, "not_black": True, "generation_step": True, "profile": True, "chain_frame": True, "chain_start": True}
    third = json.loads((run_dir / entry["steps"][2]["result"]).read_text(encoding="utf-8"))
    assert {check["check"]: check["actual"] for check in third["checks"]}["profile"] == "Ref2VA"
    exported = json.loads((run_dir / entry["steps"][4]["result"]).read_text(encoding="utf-8"))
    assert {check["check"]: check["ok"] for check in exported["checks"]} == {"duration": True, "fps": True, "frames": True, "not_black": True}
    assert entry["measures"]["seam"]["measured"] is True
    assert entry["measures"]["looks"]["lumi"][0]["identity"] == {"score": 0.81}
    saved = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    assert saved["summary"]["verdicts"] == {"PASS": 5}
    assert [engine["key"] for engine in saved["engines"] if engine["selected"]] == ["MiniMax-H3-12GB"]


def test_an_engine_without_ref2va_skips_the_third_shot_and_a_blocked_chain_is_recorded(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    vp_api.blocked_shots = {"s2-bottle"}
    engines = select_engines(pack, None, ["MiniMax-H3-Fast-12GB"])
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-2", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    steps = scenario["engines"][4]["steps"]
    assert [(step["step"], step["status"], step.get("verdict")) for step in steps] == [("take", "ran", "PASS"), ("take", "ran", "BLOCKED"), ("take", "skipped", None), ("final_pass", "ran", "PASS"), ("export", "ran", "PASS")]
    assert "cannot start a shot from an image" in steps[1]["reason"]
    assert scenario["engines"][4]["measures"]["seam"] is None


def test_the_first_oom_stops_the_scenario(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    vp_api.take_outcomes = [("failed", "cuda_oom")]
    matrix = load_matrix([matrix_file(tmp_path, all_passed())])
    engines = select_engines(pack, matrix, None)
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-3", engines, matrix, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    assert scenario["stopped"].startswith("stopped after an OOM")
    assert [kind for kind, _ in vp_api.orders] == ["generate"]
    first = scenario["engines"][0]
    assert [(step["step"], step["status"], step.get("verdict")) for step in first["steps"]] == [("take", "ran", "OOM"), ("take", "not_run", None), ("take", "not_run", None), ("final_pass", "not_run", None), ("export", "not_run", None)]
    assert all(entry["project"] is None for entry in scenario["engines"][1:])
    assert len(vp_api.projects) == 1
    result = json.loads((tmp_path / "out" / "vp-3" / first["steps"][0]["result"]).read_text(encoding="utf-8"))
    assert result["failure"]["error_code"] == "cuda_oom"


def test_cleanup_lists_then_deletes_the_marked_projects_and_generations(vp_api, vp_config, credentials_env, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    engines = select_engines(pack, None, ["Wan2.2-TI2V-5B-8GB"])
    run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-4", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    vp_api.projects["P9"] = {"id": "P9", "name": "someone else's film", "version": 1, "doc": {}}
    run_dir = tmp_path / "out" / "vp-4"
    plan = cleanup(logged_in(vp_api), run_dir, False, quiet)
    assert [item["id"] for item in plan["projects"]] == ["P1"]
    assert [item["id"] for item in plan["generations"]] == ["G1"]
    assert vp_api.deleted == []
    code = main(["vp", "cleanup", str(run_dir), "--config", str(vp_config), "--confirm"])
    assert code == 0
    assert vp_api.deleted == [f"{VP}/projects/P1", "/api/generations/history/G1", "/api/media/uploads/1-lumi.jpg", "/api/media/uploads/2-bottle.jpg"]
    assert set(vp_api.projects) == {"P9"}
    done = json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))
    assert done["generations"][0]["exists_after"] is False
    assert [(item["filename"], item["existed"], item["deleted"], item["exists_after"]) for item in done["uploads"]] == [("1-lumi.jpg", True, True, False), ("2-bottle.jpg", True, True, False)]


def test_cleanup_without_confirm_lists_the_uploads_of_the_run_and_skips_those_already_gone(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    engines = select_engines(pack, None, ["Wan2.2-TI2V-5B-8GB"])
    run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-5", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    run_dir = tmp_path / "out" / "vp-5"
    lines = []
    plan = cleanup(logged_in(vp_api), run_dir, False, lines.append)
    assert [item["filename"] for item in plan["uploads"]] == ["1-lumi.jpg", "2-bottle.jpg"]
    assert "upload 1-lumi.jpg" in lines and lines[-1].endswith("2 uploads of vp-5: pass --confirm to delete them")
    assert not [method for method, _ in vp_api.methods() if method == "DELETE"]
    vp_api.deleted.append("/api/media/uploads/1-lumi.jpg")
    plan = cleanup(logged_in(vp_api), run_dir, True, quiet)
    assert [(item["filename"], item["existed"], item["deleted"]) for item in plan["uploads"]] == [("1-lumi.jpg", False, False), ("2-bottle.jpg", True, True)]
    assert vp_api.deleted.count("/api/media/uploads/1-lumi.jpg") == 1
