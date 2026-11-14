import io
import json
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from potion_audit.cases import build_case_set, load_cases, write_case_set

USER = "auditor"
PASSWORD = "not-a-real-password"
TOKEN = "fake-token-123"
SDXL_ID = "01FAKESDXL"
WAN_ID = "01FAKEWAN"
SDXL_SHA = "a" * 64
WAN_DIT_SHA = "b" * 64
WAN_VAE_SHA = "c" * 64
MISSING_SHA = "d" * 64


def envelope(data):
    return {"success": True, "data": data, "message": None, "error": None}


def png_bytes(color=(200, 40, 40), size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def bundle_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("generation.json", json.dumps({"schema": "potionui.generation"}))
        for name, data in files.items():
            archive.writestr(f"outputs/{name}", data)
    return buffer.getvalue()


def multipart_filename(body: bytes) -> str:
    head = body.split(b"\r\n\r\n", 1)[0].decode("utf-8", "replace")
    marker = 'filename="'
    start = head.index(marker) + len(marker)
    return head[start:head.index('"', start)]


class FakeApi:
    def __init__(self):
        self.requests = []
        self.queue = {"pending": [], "running": []}
        self.models = {SDXL_SHA: "M-SDXL", WAN_DIT_SHA: "M-WAN-DIT", WAN_VAE_SHA: "M-WAN-VAE"}
        self.statuses = []
        self.started = []
        self.final = "completed"
        self.failure = None
        self.outputs = {"0.png": png_bytes()}
        self.stats_before = {"timing": {"total_runs": 3, "cold_runs": 2, "warm_runs": 1, "avg_cold_duration_ms": 30000.0, "avg_warm_duration_ms": 10000.0, "avg_model_load_ms": 8000.0},
                             "resources": {"total_runs": 3, "peak_vram_mb": 7000.0, "avg_vram_mb": 6000.0, "peak_ram_mb": 20000.0, "avg_ram_mb": 15000.0, "avg_cpu_percent": 100.0}}
        self.stats_after = {"timing": {"total_runs": 4, "cold_runs": 3, "warm_runs": 1, "avg_cold_duration_ms": 32000.0, "avg_warm_duration_ms": 10000.0, "avg_model_load_ms": 9000.0},
                            "resources": {"total_runs": 4, "peak_vram_mb": 7400.0, "avg_vram_mb": 6350.0, "peak_ram_mb": 20000.0, "avg_ram_mb": 15500.0, "avg_cpu_percent": 110.0}}
        self.disk_free = 50
        self.finished = False
        self.uploads = []
        self.keys = {}
        self.outcomes = []
        self.health = "healthy"
        self.history = [{"at": "2026-01-01T00:00:00+00:00", "step": "Loading model x", "message": "<<PIPE:Loading model>>"}]
        self.named_models = {}
        self.vram_gb = 12.0
        self.sdxl_modes = ["txt2img"]
        self.sdxl_vars = {}
        self.forms = {}
        self.plugins = [{"id": "video-producer", "version": "0.1.0", "enabled": True, "state": "enabled", "source": "marketplace"}]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def methods(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.requests]

    def _stats(self) -> dict:
        return self.stats_after if self.finished else self.stats_before

    def route(self, method: str, path: str, query: dict, body: bytes, headers) -> tuple[int, object, str]:
        if path == "/api/auth/login":
            form = urllib.parse.parse_qs(body.decode())
            if form.get("username") == [USER] and form.get("password") == [PASSWORD]:
                return 200, {"access_token": TOKEN, "token_type": "bearer"}, "application/json"
            return 401, {"detail": "Incorrect username or password"}, "application/json"
        if path == "/health":
            return 200, {"status": self.health, "service": "potionui-api"}, "application/json"
        if path == "/openapi.json":
            return 200, {"info": {"version": "9.9.9"}}, "application/json"
        if headers.get("Authorization") != f"Bearer {TOKEN}":
            return 401, {"detail": "Not authenticated"}, "application/json"
        if path == "/api/auth/me":
            return 200, envelope({"username": USER, "account_type": "ADMIN"}), "application/json"
        if path == "/api/plugins":
            return 200, envelope(self.plugins), "application/json"
        if path == "/api/media/upload" and method == "POST":
            filename = multipart_filename(body)
            self.uploads.append(filename)
            stored = f"{len(self.uploads)}-{filename}"
            return 200, envelope({"path": f"storage/uploads/{stored}", "relative_path": f"uploads/{stored}", "url": f"/api/media/uploads/{stored}", "filename": stored, "size": len(body), "width": 64, "height": 64, "duration_seconds": None, "fps": None, "id": f"U{len(self.uploads)}"}), "application/json"
        if path == "/api/settings":
            return 200, envelope({"profiling_enabled": False, "model_cache_scope": "preset", "s3_secret_key": "should-not-be-copied"}), "application/json"
        if path == "/api/system/gpu-profile":
            return 200, {"name": "Fake GPU", "vram_gb": self.vram_gb, "generation_label": "fake", "compute_capability": "8.9"}, "application/json"
        if path == "/api/system/stats":
            return 200, envelope({"gpu": {"available": True, "vram_used": 2000 + 100 * len(self.started)}, "ram": {"used": 9000, "total": 64000}, "cpu": {"core_count": 8}}), "application/json"
        if path == "/api/system/backends":
            return 200, envelope([{"id": "native", "name": "Local", "engine": "native", "kind": "local", "status": "online"}, {"id": "cloud-1", "name": "Cloud", "engine": "cloud", "kind": "cloud", "status": "online"}]), "application/json"
        if path == "/api/backends/native/system-info":
            return 200, envelope({"disk_usage": {"models": {"total": 1000, "used": 1000 - self.disk_free, "free": self.disk_free}}}), "application/json"
        if path == "/api/backends/native/optimizations":
            return 200, envelope({"attention": "sdpa"}), "application/json"
        if path == "/api/admin/generations/queue":
            return 200, envelope(self.queue), "application/json"
        if path == "/api/presets":
            listed = [
                {"id": SDXL_ID, "name": "SDXL", "version": "1.0.1", "installed": True, "assignment_count": 1, "group_count": 0, "requires": {"min_vram_gb": 8}, "modes": self.sdxl_modes, "vars": self.sdxl_vars, "engine": "native"},
                {"id": WAN_ID, "name": "Wan", "version": "2.0.0", "installed": True, "assignment_count": 0, "group_count": 0, "requires": {"min_vram_gb": 16}, "modes": ["video"], "vars": {"video_director": {"preset_modes": ["video"], "limits": {"default_duration": 5, "default_fps": 16}}}, "engine": "native"},
            ]
            return 200, envelope(listed if query.get("include_uninstalled") == ["true"] else listed[:1]), "application/json"
        if path == f"/api/presets/{SDXL_ID}":
            return 200, envelope({"id": SDXL_ID, "vars": {}}), "application/json"
        if path == f"/api/presets/{WAN_ID}":
            return 200, envelope({"id": WAN_ID, "vars": {"video_director": {"preset_modes": ["video"], "limits": {"default_duration": 5, "default_fps": 16}}}}), "application/json"
        if path.startswith("/api/presets/") and path.endswith("/form"):
            key = (path.split("/")[3], (query.get("mode") or [""])[0])
            if key in self.forms:
                return 200, envelope({"preset_id": key[0], "form_schema": self.forms[key]}), "application/json"
            return 500, {"detail": f"Mode '{key[1]}' not found"}, "application/json"
        if path.startswith("/api/presets/") and path.endswith("/models"):
            search = (query.get("search") or [""])[0]
            found = [{"id": model_id, "filename": name, "model_type": "lora", "file_size": 10, "sha256": "e" * 64, "is_available": True} for name, model_id in self.named_models.items() if search in name]
            return 200, envelope({"models": found, "total": len(found)}), "application/json"
        if path.startswith("/api/models/hash/"):
            sha = path.rsplit("/", 1)[1]
            if sha in self.models:
                return 200, envelope({"model": {"id": self.models[sha], "filename": f"{sha[:4]}.safetensors", "model_type": "diffusion_model", "file_size": 123, "is_available": True}}), "application/json"
            return 200, {"success": False, "data": None, "message": "not found", "error": "model_not_found"}, "application/json"
        if path.startswith("/api/stats/presets/"):
            kind = path.rsplit("/", 1)[1]
            return 200, envelope({"items": [{"preset_id": SDXL_ID, **self._stats()[kind]}]}), "application/json"
        if path == "/api/generations/start" and method == "POST":
            request = json.loads(body)
            key = request.get("idempotency_key")
            if key in self.keys and self.keys[key] != request:
                return 409, {"success": False, "error": "idempotency_key_conflict", "message": "This idempotency key was already used for a different request", "code": None}, "application/json"
            if key:
                self.keys[key] = request
            if self.outcomes:
                self.final, self.failure = self.outcomes.pop(0)
            self.started.append(request)
            return 200, envelope({"generation_id": "G1", "status": {"id": "G1", "status": "pending"}}), "application/json"
        if path == "/api/generations/G1/status":
            if self.statuses:
                return 200, envelope(self.statuses.pop(0)), "application/json"
            self.finished = True
            return 200, envelope({"id": "G1", "status": self.final, "progress": 1.0, "current_step_num": 4, "total_steps": 4}), "application/json"
        if path == "/api/generations/G1/cancel" and method == "POST":
            return 200, envelope({}), "application/json"
        if path == "/api/admin/generations/G1":
            return 200, envelope({"generation": {}, "run_report": {"pipe_timers": {"0": {"started_at": "2026-01-01T00:00:00+00:00", "ended_at": "2026-01-01T00:00:02.500000+00:00"}}, "status_history": self.history}}), "application/json"
        if path == "/api/generations/history/G1":
            return 200, envelope({"id": "G1", "run_seconds": 12, "queued_seconds": 0, "duration_ms": 12000, "has_profile": False}), "application/json"
        if path == "/api/generations/history/G1/export-bundle":
            return 200, bundle_bytes(self.outputs), "application/zip"
        if path == "/api/generations/G1/failure":
            if self.failure:
                return 200, envelope(self.failure), "application/json"
            return 404, {"detail": {"error": "failure_not_found"}}, "application/json"
        return 404, {"detail": f"no fake route for {method} {path}"}, "application/json"

    def _handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _serve(self, method):
                parsed = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                api.requests.append((method, parsed.path, body))
                status, payload, content_type = api.route(method, parsed.path, urllib.parse.parse_qs(parsed.query), body, self.headers)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                if content_type == "application/zip":
                    self.send_header("Content-Disposition", 'attachment; filename="bundle-G1.zip"')
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._serve("GET")

            def do_POST(self):
                self._serve("POST")

        return Handler


@pytest.fixture
def fake_api():
    api = FakeApi()
    api.thread.start()
    yield api
    api.server.shutdown()
    api.server.server_close()


def sample_case_set_data() -> dict:
    presets = [
        {
            "key": "SDXL",
            "path": "content/presets/marketplace/SDXL",
            "origin": "core",
            "preset": {"id": SDXL_ID, "name": "SDXL", "version": "1.0.1", "engine": "native", "category": "image", "requires": {"min_vram_gb": 8}},
            "modes": ["txt2img"],
            "tests": {
                "cases": [
                    {"name": "sdxl-slow", "mode": "txt2img", "seed": 1, "tags": [], "form": {"prompt": "slow", "steps": 30}, "models": {"model": {"sha256": SDXL_SHA}}, "checks": {"min_outputs": 1}},
                    {"name": "sdxl-fast", "mode": "txt2img", "seed": 999, "tags": ["fast"], "form": {"prompt": "a purple potion", "steps": 4, "resolution": "64x64"}, "models": {"model": {"sha256": SDXL_SHA}}, "checks": {"min_outputs": 1, "resolution": "64x64", "not_black": True}},
                ]
            },
            "tests_blob": "1" * 40,
            "model_fields": {"model": {"model_type": "checkpoint", "recommended": [SDXL_SHA]}},
        },
        {
            "key": "Wan",
            "path": "content/presets/marketplace/Wan",
            "origin": "core",
            "preset": {"id": WAN_ID, "name": "Wan", "version": "2.0.0", "engine": "native", "category": "video", "requires": {"min_vram_gb": 16}},
            "modes": ["video"],
            "tests": {
                "cases": [
                    {"name": "wan-t2v", "mode": "video", "kind": "video", "seed": 12345, "tags": ["fast"], "form": {"prompt": "a bottle on an oak bench", "resolution": "832x480"}, "models": {"t2v_high_noise_model": {"sha256": "0" * 64}, "vae": {"sha256": WAN_VAE_SHA}, "text_encoder": {"sha256": MISSING_SHA}}, "checks": {"min_outputs": 1}},
                ]
            },
            "tests_blob": "2" * 40,
            "model_fields": {"t2v_high_noise_model": {"model_type": "diffusion_model", "recommended": [WAN_DIT_SHA]}, "vae": {"model_type": "vae", "recommended": []}, "text_encoder": {"model_type": "text_encoder", "recommended": []}},
        },
        {
            "key": "ModelTools",
            "path": "content/presets/marketplace/ModelTools",
            "origin": "core",
            "preset": {"id": "01FAKETOOLS", "name": "Model Tools", "version": "1.0.0"},
            "modes": ["convert"],
            "tests": None,
            "tests_blob": None,
            "model_fields": {},
        },
    ]
    recipes = [
        {
            "path": "content/recipes/marketplace/wan-starter.yml",
            "recipe": {
                "id": "wan-starter",
                "version": 1,
                "presets": [{"preset_id": WAN_ID}],
                "artifacts": [
                    {"id": "wan-dit-high", "filename": "wan_t2v_high_noise.safetensors", "model_type": "diffusion_model", "size_bytes": 5000, "checksum": {"algorithm": "sha256", "value": WAN_DIT_SHA}},
                    {"id": "wan-vae", "filename": "wan_vae.safetensors", "model_type": "vae", "size_bytes": 200, "checksum": {"algorithm": "sha256", "value": WAN_VAE_SHA}},
                    {"id": "wan-te", "filename": "umt5.safetensors", "model_type": "text_encoder", "size_bytes": 7000, "checksum": {"algorithm": "sha256", "value": MISSING_SHA}},
                ],
            },
        }
    ]
    return build_case_set("f" * 40, "fake core", presets, recipes)


@pytest.fixture
def case_file(tmp_path: Path) -> Path:
    path = tmp_path / "cases.json"
    write_case_set(sample_case_set_data(), path)
    return path


@pytest.fixture
def case_set(case_file: Path):
    return load_cases(case_file)


@pytest.fixture
def config_file(tmp_path: Path, fake_api: FakeApi, case_file: Path) -> Path:
    path = tmp_path / "audit.toml"
    path.write_text(
        "\n".join(
            [
                "[target]",
                f'url = "{fake_api.url}"',
                'mode = "dedicated"',
                "",
                "[run]",
                'output_dir = "out"',
                'machine = "test-box"',
                f'cases = "{case_file.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def credentials_env(monkeypatch):
    monkeypatch.setenv("POTION_AUDIT_USER", USER)
    monkeypatch.setenv("POTION_AUDIT_PASSWORD", PASSWORD)
