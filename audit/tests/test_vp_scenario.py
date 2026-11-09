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
from potion_audit.vp_scenario import LIGHTNING_I2V_ID, SHOT_SECONDS, SHOTS, VP, cleanup, load_matrix, run_scenario, select_engines

from conftest import PASSWORD, USER, FakeApi, bundle_bytes, envelope

H3 = "plugin:video-producer/MiniMax-H3-12GB"
H3_ID = "01M54HN72B0KY7H63BKQ16T253"
WAN13 = "plugin:video-producer/Wan2.1-T2V-1.3B-8GB"
WAN13_ID = "01M57QPEMDPKHHW83YSEYBN0WZ"
FIVE = "plugin:video-producer/Wan2.2-TI2V-5B-8GB"
LIGHTNING = "plugin:video-producer/Wan2.2-14B-Lightning-12GB"
LIGHTNING_ID = "01M57QPEMDPKHHW83YSEYBN0X1"
I2V_ID = LIGHTNING_I2V_ID
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
        self.export_bytes = clip_bytes(tmp_path, "export.mp4", SHOT_SECONDS * len(SHOTS))
        self.projects = {}
        self.vp_takes = []
        self.orders = []
        self.estimates = []
        self.puts = []
        self.deleted = []
        self.media_uploaded = []
        self.take_outcomes = []
        self.blocked_shots = set()
        self.text_only = {WAN13_ID}
        self.companions = {LIGHTNING_ID: I2V_ID}
        self.names = {I2V_ID: "Wan 2.2 14B Lightning I2V (12 GB)", LIGHTNING_ID: "Wan 2.2 14B Lightning (12 GB)"}
        self.vram = {I2V_ID: 9000.0}
        self.runs = {}
        self.record_preset = True

    def _frames(self, doc: dict, shot_id: str) -> set[str]:
        return {frame.get("role") for frame in doc.get("frames") or () if frame.get("shotId") == shot_id and frame.get("assetId")}

    def _plan(self, doc: dict, clip: dict, preset_id: str) -> tuple[str, str, list[dict]]:
        roles = self._frames(doc, clip["id"])
        chained = bool(clip.get("firstFromPrevious"))
        if preset_id in self.text_only:
            warnings = [{"code": "chain_text_only", "message": "The preset generates from text only.", "data": {"shot_id": clip["id"]}}] if chained else []
            return "t2v", preset_id, warnings
        mode = "flf" if "last" in roles and ("first" in roles or chained) else "i2v" if chained or "first" in roles else "t2v"
        return mode, self.companions.get(preset_id, preset_id) if mode != "t2v" else preset_id, []

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
            take["director_mode"], take["preset_id"], _ = self._plan(doc, clip, body.get("preset_id"))
        if kind == "render" and clip.get("firstFromPrevious") and take["director_mode"] != "t2v":
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
            self.runs[take["preset_id"]] = self.runs.get(take["preset_id"], 0) + 1
            self.last_preset = take["preset_id"]
            take.update(file_path=f"storage/generations/G1/{take['id']}.mp4", url=f"/api/media/generations/G1/{take['id']}.mp4", file_id=7, width=64, height=64, duration_s=1.0, fps=24.0)
        else:
            take["error_code"] = code

    def _public(self, take: dict) -> dict:
        return {key: value for key, value in take.items() if key not in ("polls", "outcome")}

    def _stored_uploads(self) -> set[str]:
        return {f"{index + 1}-{name}" for index, name in enumerate(self.uploads)} - {path.rsplit("/", 1)[1] for path in self.deleted if path.startswith("/api/media/uploads/")}

    def _preset_items(self, kind: str) -> list[dict]:
        items = []
        for preset_id, runs in self.runs.items():
            vram = self.vram.get(preset_id, 6000.0)
            if kind == "timing":
                items.append({"preset_id": preset_id, "preset_name": self.names.get(preset_id, preset_id), "total_runs": runs, "cold_runs": runs, "warm_runs": 0, "avg_cold_duration_ms": 20000.0, "avg_warm_duration_ms": None, "avg_model_load_ms": 4000.0})
            else:
                items.append({"preset_id": preset_id, "preset_name": self.names.get(preset_id, preset_id), "total_runs": runs, "peak_vram_mb": vram, "avg_vram_mb": vram, "avg_ram_mb": 15000.0, "avg_cpu_percent": 90.0})
        return items

    def route(self, method, path, query, body, headers):
        if path.startswith("/api/stats/presets/"):
            status, payload, kind = super().route(method, path, query, body, headers)
            if status == 200:
                payload["data"]["items"] += self._preset_items(path.rsplit("/", 1)[1])
            return status, payload, kind
        if path == "/api/generations/history/G1" and method == "GET" and not any(item.endswith("/G1") for item in self.deleted):
            status, payload, kind = super().route(method, path, query, body, headers)
            if status == 200 and self.record_preset and getattr(self, "last_preset", None):
                payload["data"]["preset_id"] = self.last_preset
            return status, payload, kind
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
            if not payload.get("id"):
                return 422, {"success": False, "error": "invalid_request", "message": "The request body needs the id the upload answered."}, "application/json"
            self.media_uploaded.append(payload["filename"])
            return 200, envelope({"media": {"kind": "library", "media_type": "image", "url": f"/api/media/uploads/{payload['filename']}", "filename": payload["filename"], "origin": {"kind": "library", "itemId": payload["id"]}}}), "application/json"
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
            if tail == ["estimate"]:
                self.estimates.append(payload)
                doc = project["doc"]
                shots = []
                warnings = []
                for shot_id in payload["shots"]:
                    clip = next(item for item in doc["clips"] if item["id"] == shot_id)
                    mode, preset_id, found = self._plan(doc, clip, payload.get("preset_id"))
                    shots.append({"shot_id": shot_id, "director_mode": mode, "preset_id": preset_id})
                    warnings += found
                warnings.append({"code": "time_unknown", "message": "No take of this preset was measured at this resolution yet."})
                return 200, envelope({"shots": shots, "blocks": [], "warnings": warnings, "vram": {}, "time": {"seconds": None}}), "application/json"
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
        ("take", "s4-gold", "planned"),
        ("final_pass", "s1-workshop", "not_run"),
        ("export", None, "planned"),
    ]
    assert "--upscaler rtx" in h3["steps"][4]["reason"]
    assert h3["steps"][3]["frames"] == ["bottle", "bottle-gold"] and h3["steps"][3]["checks"] == ["profile", "flf_start"]
    assert h3["steps"][1]["chained_on"] == "s1-workshop"
    assert h3["steps"][0]["estimate_basis"].startswith("run seconds of plugin:video-producer/MiniMax-H3-12GB:video")
    assert h3["steps"][2]["estimate_basis"].startswith("run seconds of plugin:video-producer/MiniMax-H3-12GB:refs")
    assert h3["estimate_seconds"] == sum(step["estimate_seconds"] for step in h3["steps"][:4])
    fast = engines["MiniMax-H3-Fast-12GB"]
    assert fast["steps"][2]["status"] == "skipped"
    wan = engines["Wan2.1-T2V-1.3B-8GB"]
    assert (wan["steps"][1]["checks"], wan["steps"][1]["not_offered"]) == (["profile", "chain_mode", "chain_warning"], ["chain_frame", "chain_start"])
    assert wan["steps"][3]["status"] == "skipped" and "text-to-video model" in wan["steps"][3]["reason"]
    five = engines["Wan2.2-TI2V-5B-8GB"]
    assert five["steps"][1]["checks"] == ["profile", "chain_frame", "chain_start"]
    assert five["steps"][3]["status"] == "skipped" and "first image only" in five["steps"][3]["reason"]
    lightning = engines["Wan2.2-14B-Lightning-12GB"]
    assert lightning["steps"][1]["checks"] == ["profile", "chain_frame", "chain_start", "image_preset"]
    assert lightning["steps"][3]["checks"] == ["profile", "flf_start", "image_preset"]
    assert lightning["project"]["options"] is None
    assert plan["summary"]["engines"] == 5
    assert plan["summary"]["generations"] == 14
    doc = json.loads((tmp_path / "out" / "vp-dry" / "projects" / "MiniMax-H3-12GB.json").read_text(encoding="utf-8"))
    assert doc["name"] == "potion-audit vp-dry MiniMax-H3-12GB"
    assert [clip["firstFromPrevious"] for clip in doc["clips"]] == [False, True, False, False]
    assert [clip["engine"]["profile"] for clip in doc["clips"]] == ["FL2VA", "FL2VA", "Ref2VA", "FL2VA"]
    assert doc["clips"][2]["cast"]["characters"] == ["card-lumi"]
    assert doc["bible"]["characters"][0]["references"] == ["ref-lumi"]
    assert [(reference["id"], reference["assetId"]) for reference in doc["references"]] == [("ref-lumi", "asset-lumi"), ("ref-bottle", "asset-bottle")]
    assert [(asset["id"], asset["src"]) for asset in doc["assets"]] == [("asset-lumi", "input:lumi"), ("asset-bottle", "input:bottle"), ("frame-bottle", "input:bottle"), ("frame-bottle-gold", "input:bottle-gold")]
    assert [(frame["shotId"], frame["role"], frame["assetId"], frame["time"]) for frame in doc["frames"]] == [("s4-gold", "first", "frame-bottle", 15.0), ("s4-gold", "last", "frame-bottle-gold", 19.96)]
    assert "options" not in doc["engine"]
    assert "Lumi" in doc["prompts"][2]["text"] and "{" not in doc["prompts"][2]["text"]


def test_a_run_creates_the_project_chains_the_second_shot_and_sends_the_references(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    matrix = load_matrix([matrix_file(tmp_path, all_passed())])
    engines = select_engines(pack, matrix, ["MiniMax-H3-12GB"])
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-1", engines, matrix, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    assert scenario["stopped"] is None
    assert len(vp_api.uploads) == 3 and vp_api.media_uploaded == ["1-lumi.jpg", "2-bottle.jpg", "3-bottle-gold.jpg"]
    project = vp_api.projects["P1"]
    assert project["name"] == "potion-audit vp-1 MiniMax-H3-12GB"
    assert [asset["origin"] for asset in project["doc"]["assets"][:2]] == [{"kind": "library", "itemId": "U1"}, {"kind": "library", "itemId": "U2"}]
    assert [(kind, body.get("shots") or body.get("takes") or body.get("format")) for kind, body in vp_api.orders] == [("generate", ["s1-workshop"]), ("generate", ["s2-bottle"]), ("generate", ["s3-lumi"]), ("generate", ["s4-gold"]), ("final-pass", ["T1"]), ("export", "web")]
    assert [body["shots"] for body in vp_api.estimates] == [["s1-workshop"], ["s2-bottle"], ["s3-lumi"], ["s4-gold"]]
    assert vp_api.orders[4][1] == {"takes": ["T1"], "method": "upscale", "target": "fhd1080", "upscaler": "rtx"}
    assert vp_api.puts[0]["doc"]["clips"][0]["take"] == "T1"
    second = next(take for take in vp_api.vp_takes if take["shot_id"] == "s2-bottle")
    assert second["chain"]["state"] == "taken" and second["chain"]["source"]["takeId"] == "T1"
    assert vp_api.puts[-1]["doc"]["clips"][0]["take"] == "T5"
    assert [asset["origin"] for asset in project["doc"]["assets"] if asset["id"].startswith("frame-")] == [{"kind": "library", "itemId": "U2"}, {"kind": "library", "itemId": "U3"}]
    entry = scenario["engines"][3]
    assert [(step["step"], step.get("verdict")) for step in entry["steps"]] == [("take", "PASS"), ("take", "PASS"), ("take", "PASS"), ("take", "PASS"), ("final_pass", "PASS"), ("export", "PASS")]
    run_dir = tmp_path / "out" / "vp-1"
    result = json.loads((run_dir / entry["steps"][1]["result"]).read_text(encoding="utf-8"))
    assert result["cell"] == "vp:plugin:video-producer/MiniMax-H3-12GB:s2-bottle"
    assert {check["check"]: check["ok"] for check in result["checks"]} == {"min_outputs": True, "not_black": True, "generation_step": True, "profile": True, "chain_frame": True, "chain_start": True}
    third = json.loads((run_dir / entry["steps"][2]["result"]).read_text(encoding="utf-8"))
    assert {check["check"]: check["actual"] for check in third["checks"]}["profile"] == "Ref2VA"
    fourth = json.loads((run_dir / entry["steps"][3]["result"]).read_text(encoding="utf-8"))
    assert {check["check"]: check["ok"] for check in fourth["checks"]} == {"min_outputs": True, "not_black": True, "generation_step": True, "profile": True, "flf_start": True}
    assert fourth["take"]["director_mode"] == "flf"
    assert fourth["stats_preset"]["preset_id"] == H3_ID and fourth["stats_preset"]["differs"] is False
    assert [warning["code"] for warning in fourth["estimate"]["warnings"]] == ["time_unknown"]
    exported = json.loads((run_dir / entry["steps"][5]["result"]).read_text(encoding="utf-8"))
    assert {check["check"]: check["ok"] for check in exported["checks"]} == {"duration": True, "fps": True, "frames": True, "not_black": True}
    assert entry["measures"]["seam"]["measured"] is True
    assert entry["measures"]["looks"]["lumi"][0]["identity"] == {"score": 0.81}
    saved = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    assert saved["summary"]["verdicts"] == {"PASS": 6}
    assert [engine["key"] for engine in saved["engines"] if engine["selected"]] == ["MiniMax-H3-12GB"]


def test_an_engine_without_ref2va_skips_the_third_shot_and_a_blocked_chain_is_recorded(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    vp_api.blocked_shots = {"s2-bottle"}
    engines = select_engines(pack, None, ["MiniMax-H3-Fast-12GB"])
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-2", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    steps = scenario["engines"][4]["steps"]
    assert [(step["step"], step["status"], step.get("verdict")) for step in steps] == [("take", "ran", "PASS"), ("take", "ran", "BLOCKED"), ("take", "skipped", None), ("take", "ran", "PASS"), ("final_pass", "ran", "PASS"), ("export", "ran", "PASS")]
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
    assert [(step["step"], step["status"], step.get("verdict")) for step in first["steps"]] == [("take", "ran", "OOM"), ("take", "not_run", None), ("take", "not_run", None), ("take", "not_run", None), ("final_pass", "not_run", None), ("export", "not_run", None)]
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
    assert vp_api.deleted == [f"{VP}/projects/P1", "/api/generations/history/G1", "/api/media/uploads/1-lumi.jpg", "/api/media/uploads/2-bottle.jpg", "/api/media/uploads/3-bottle-gold.jpg"]
    assert set(vp_api.projects) == {"P9"}
    done = json.loads((run_dir / "cleanup.json").read_text(encoding="utf-8"))
    assert done["generations"][0]["exists_after"] is False
    assert [(item["filename"], item["existed"], item["deleted"], item["exists_after"]) for item in done["uploads"]] == [("1-lumi.jpg", True, True, False), ("2-bottle.jpg", True, True, False), ("3-bottle-gold.jpg", True, True, False)]


def test_cleanup_without_confirm_lists_the_uploads_of_the_run_and_skips_those_already_gone(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    engines = select_engines(pack, None, ["Wan2.2-TI2V-5B-8GB"])
    run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-5", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    run_dir = tmp_path / "out" / "vp-5"
    lines = []
    plan = cleanup(logged_in(vp_api), run_dir, False, lines.append)
    assert [item["filename"] for item in plan["uploads"]] == ["1-lumi.jpg", "2-bottle.jpg", "3-bottle-gold.jpg"]
    assert "upload 1-lumi.jpg" in lines and lines[-1].endswith("3 uploads of vp-5: pass --confirm to delete them")
    assert not [method for method, _ in vp_api.methods() if method == "DELETE"]
    vp_api.deleted.append("/api/media/uploads/1-lumi.jpg")
    plan = cleanup(logged_in(vp_api), run_dir, True, quiet)
    assert [(item["filename"], item["existed"], item["deleted"]) for item in plan["uploads"]] == [("1-lumi.jpg", False, False), ("2-bottle.jpg", True, True), ("3-bottle-gold.jpg", True, True)]
    assert vp_api.deleted.count("/api/media/uploads/1-lumi.jpg") == 1


def steps_of(scenario: dict, ref: str) -> dict:
    entry = next(item for item in scenario["engines"] if item["engine"] == ref)
    return {step["shot"] if step["step"] == "take" else step["step"]: step for step in entry["steps"]}


def result_of(run_dir: Path, step: dict) -> dict:
    return json.loads((run_dir / step["result"]).read_text(encoding="utf-8"))


def test_the_wan_engines_meet_the_expectations_of_their_chaining_and_the_flf_shot(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    engines = select_engines(pack, None, ["Wan2.1-T2V-1.3B-8GB", "Wan2.2-TI2V-5B-8GB", "Wan2.2-14B-Lightning-12GB"])
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-wan", engines, None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    run_dir = tmp_path / "out" / "vp-wan"
    small = steps_of(scenario, WAN13)
    assert small["s2-bottle"]["verdict"] == "PASS" and small["s2-bottle"]["director_mode"] == "t2v"
    chained = result_of(run_dir, small["s2-bottle"])
    assert {check["check"]: check["ok"] for check in chained["checks"]} == {"min_outputs": True, "not_black": True, "profile": True, "chain_mode": True, "chain_warning": True}
    assert [item["check"] for item in chained["not_offered"]] == ["chain_frame", "chain_start"]
    assert "generates from text only" in chained["not_offered"][0]["reason"]
    assert next(check for check in chained["checks"] if check["check"] == "chain_warning")["actual"] == ["chain_text_only", "time_unknown"]
    assert small["s4-gold"]["status"] == "skipped" and "text-to-video model" in small["s4-gold"]["reason"]
    five = steps_of(scenario, FIVE)
    assert five["s2-bottle"]["verdict"] == "PASS" and five["s2-bottle"]["director_mode"] == "i2v"
    assert {check["check"] for check in result_of(run_dir, five["s2-bottle"])["checks"]} >= {"chain_frame", "chain_start"}
    assert five["s4-gold"]["status"] == "skipped" and "first image only" in five["s4-gold"]["reason"]
    lightning = steps_of(scenario, LIGHTNING)
    assert [lightning[shot]["preset_id"] for shot in ("s1-workshop", "s2-bottle", "s4-gold")] == [LIGHTNING_ID, I2V_ID, I2V_ID]
    second = result_of(run_dir, lightning["s2-bottle"])
    assert {check["check"]: check["ok"] for check in second["checks"]}["image_preset"] is True
    assert second["stats_preset"] == {"preset_id": I2V_ID, "source": "the generation record", "name": "Wan 2.2 14B Lightning I2V (12 GB)", "ordered_preset_id": LIGHTNING_ID, "record_preset_id": I2V_ID, "take_preset_id": I2V_ID, "differs": True}
    assert second["generation_stats"]["derived"] is True and second["generation_stats"]["peak_vram_mb"] == 9000.0
    assert lightning["s2-bottle"]["stats_preset"] == {"preset_id": I2V_ID, "name": "Wan 2.2 14B Lightning I2V (12 GB)", "source": "the generation record", "differs": True}
    assert lightning["s2-bottle"]["peak_vram_mb"] == 9000.0
    first = result_of(run_dir, lightning["s1-workshop"])
    assert first["stats_preset"]["differs"] is False and first["generation_stats"]["peak_vram_mb"] == 6000.0
    gold = result_of(run_dir, lightning["s4-gold"])
    assert {check["check"]: check["ok"] for check in gold["checks"]} == {"min_outputs": True, "not_black": True, "generation_step": True, "profile": True, "flf_start": True, "image_preset": True}
    assert gold["generation_stats"]["derived"] is True and gold["stats_preset"]["preset_id"] == I2V_ID
    assert scenario["summary"]["verdicts"] == {"PASS": 13}


def test_a_5b_chained_shot_started_from_its_text_fails_its_chaining_checks(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    vp_api.text_only.add("01M57QPEMDPKHHW83YSEYBN0X0")
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-5b", select_engines(pack, None, ["Wan2.2-TI2V-5B-8GB"]), None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    step = steps_of(scenario, FIVE)["s2-bottle"]
    assert step["verdict"] == "FAIL"
    result = result_of(tmp_path / "out" / "vp-5b", step)
    assert {check["check"]: check["ok"] for check in result["checks"]} == {"min_outputs": True, "not_black": True, "profile": True, "chain_frame": False, "chain_start": False}
    assert "not_offered" not in result


def test_lightning_without_its_companion_fails_the_image_preset_and_the_stats_fall_back_to_the_take(vp_api, tmp_path):
    pack = load_pack(DEFAULT_PACK)
    vp_api.companions = {}
    vp_api.record_preset = False
    scenario = run_scenario(logged_in(vp_api), pack, tmp_path / "out", "vp-alone", select_engines(pack, None, ["Wan2.2-14B-Lightning-12GB"]), None, upscaler="rtx", interval=0.01, sleep=no_sleep, log=quiet)
    run_dir = tmp_path / "out" / "vp-alone"
    steps = steps_of(scenario, LIGHTNING)
    second = result_of(run_dir, steps["s2-bottle"])
    assert {check["check"]: check["ok"] for check in second["checks"]}["image_preset"] is False
    assert second["stats_preset"]["source"] == "the take" and second["stats_preset"]["preset_id"] == LIGHTNING_ID and second["stats_preset"]["differs"] is False
    assert steps["s4-gold"]["verdict"] == "FAIL"


def test_companion_steps_go_to_the_engine_options_of_the_companion_only(vp_api, vp_config, credentials_env, tmp_path):
    code = main(["vp", "run", "--config", str(vp_config), "--engines", "Wan2.2-14B-Lightning-12GB,MiniMax-H3-Fast-12GB", "--companion-steps", "4", "--dry-run", "--run-id", "vp-steps"])
    assert code == 0
    run_dir = tmp_path / "out" / "vp-steps"
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["settings"]["companion_steps"] == 4
    lightning = json.loads((run_dir / "projects" / "Wan2.2-14B-Lightning-12GB.json").read_text(encoding="utf-8"))
    assert lightning["engine"]["options"] == {I2V_ID: {"speed_profile": "custom", "steps": 4, "cfg": 1.0}}
    fast = json.loads((run_dir / "projects" / "MiniMax-H3-Fast-12GB.json").read_text(encoding="utf-8"))
    assert "options" not in fast["engine"]
    assert main(["vp", "run", "--config", str(vp_config), "--engines", "Wan2.2-14B-Lightning-12GB", "--companion-steps", "0", "--dry-run"]) == 2


def test_the_frames_of_the_flf_shot_are_frozen_inputs_of_the_pack():
    pack = load_pack(DEFAULT_PACK)
    shot = next(item for item in SHOTS if item["frames"])
    for input_id in shot["frames"]:
        spec = pack.inputs[input_id]
        assert spec.kind == "image" and len(spec.sha256) == 64 and pack.input_path(input_id).is_file()
