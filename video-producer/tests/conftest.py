import importlib
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

for _key in list(sys.modules):
    if _key.split(".", 1)[0] in ("backend", "hooks"):
        del sys.modules[_key]

if str(PLUGIN_ROOT) in sys.path:
    sys.path.remove(str(PLUGIN_ROOT))
sys.path.insert(0, str(PLUGIN_ROOT))

importlib.invalidate_caches()
import backend  # noqa: E402,F401


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ffmpeg: needs ffmpeg and ffprobe on the PATH; skipped without them")


@pytest.fixture
def export_storage(monkeypatch, tmp_path):
    from backend import core_bridge

    root = tmp_path / "storage"
    root.mkdir()
    monkeypatch.setattr(core_bridge, "storage_directory", lambda: root)
    return root


@pytest.fixture(autouse=True)
def export_runner_reset():
    yield
    from backend.exports import jobs

    jobs.RUNNER.stop()
    jobs._PROCESSES.clear()


@pytest.fixture
def scratch_db(tmp_path):
    from src.plugin_api.storage import db

    Database = type(db)

    Database._instance = None
    test_db = Database()
    test_db.db_path = tmp_path / "test.sqlite"
    test_db.db_path.parent.mkdir(parents=True, exist_ok=True)
    test_db._initialized = True
    yield test_db
    Database._instance = None


@pytest.fixture
def plugin_db(scratch_db, monkeypatch):
    monkeypatch.setattr("src.platform.database.database.db", scratch_db)
    return scratch_db


@pytest.fixture
def project_db(plugin_db):
    from backend.tables import create_tables

    create_tables()
    return plugin_db


@pytest.fixture
def clock(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from backend import projects

    ticks = []

    def now():
        ticks.append(datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=len(ticks)))
        return ticks[-1].isoformat()

    monkeypatch.setattr(projects, "_now", now)
    return ticks


@pytest.fixture
def job_clock(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from backend.exports import jobs

    ticks = []

    def now():
        ticks.append(datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=len(ticks)))
        return ticks[-1].isoformat()

    monkeypatch.setattr(jobs, "now", now)
    return ticks


@pytest.fixture
def scheduled(monkeypatch):
    import concurrent.futures

    import src.plugin_api.hooks as plugin_hooks

    jobs = []

    def run_on_app_loop(coro):
        jobs.append(coro)
        return concurrent.futures.Future()

    monkeypatch.setattr(plugin_hooks, "run_on_app_loop", run_on_app_loop)
    yield jobs
    for job in jobs:
        job.close()


class SettingsStore(dict):
    def __init__(self):
        super().__init__()
        self.calls = []


@pytest.fixture
def store(monkeypatch):
    from backend import core_bridge

    values = SettingsStore()

    def get_plugin_setting(key, user_id=None):
        values.calls.append(("get", key, user_id))
        return values.get((key, user_id))

    def set_plugin_setting(key, value, user_id=None):
        values.calls.append(("set", key, value, user_id))
        values[(key, user_id)] = value

    monkeypatch.setattr(core_bridge, "get_plugin_setting", get_plugin_setting)
    monkeypatch.setattr(core_bridge, "set_plugin_setting", set_plugin_setting)
    return values


@pytest.fixture
def make_user():
    from src.plugin_api import AccountType, User

    def make(account_type=AccountType.USER, user_id="user-1"):
        return User(
            id=user_id,
            username=f"name-{user_id}",
            email=f"{user_id}@test.com",
            password_hash="hash",
            account_type=account_type,
        )

    return make


@pytest.fixture
def app(make_user):
    from fastapi import FastAPI

    from backend.api import router
    from src.plugin_api import get_current_active_user

    app = FastAPI(redirect_slashes=False)
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = make_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture
def no_container(monkeypatch):
    import src.plugin_api.limits as api_limits

    def limit_status(user_id, kind):
        raise RuntimeError("AppContainer not initialized yet")

    monkeypatch.setattr(api_limits, "limit_status", limit_status)


@pytest.fixture(autouse=True)
def tracker_reset():
    yield
    from backend import tracker

    tracker.TRACKER.stop()


@pytest.fixture(autouse=True)
def peak_cache_reset():
    yield
    from backend import soundtrack

    soundtrack._PEAKS.clear()
    soundtrack._RUNNING.clear()
    soundtrack._SLOTS.clear()


WAN_ID = "01KX47WANVIDEO0000000000TV"
H3_ID = "01KX47H3MINIMAX000000000VA"
LTX25_ID = "01KX47LTX25VIDEO00000000TV"
SEEDVR2_ID = "01KXB7C553THYMSMKY1QSYESFM"
RTX_ID = "01KXRTXUPSCALE0000000000RU"
VIDEO_TOOLS_ID = "01KXVIDEOTOOLS0000000000VT"
OPENROUTER_ID = "01M3SV8HJTGT3JPPH2BA5MP6PR"

WAN_RESOLUTIONS = (
    "832x480", "480x832", "960x544", "544x960", "640x480", "480x640", "1280x720", "720x1280", "512x512",
    "1024x1024", "720x720", "960x960", "576x720", "832x1040", "720x576", "1040x832", "480x720", "768x1152",
    "720x480", "1152x768",
)
H3_RESOLUTIONS = (
    "1344x768", "768x1344", "1536x672", "1152x768", "768x1152", "1024x768", "768x1024", "960x768", "768x960",
    "768x768", "960x544", "544x960", "832x480", "480x832", "640x480", "480x640", "640x640", "736x416", "416x736",
    "608x352", "352x608", "512x384", "384x512",
)
UPSCALE_TARGET_OPTIONS = ("x1_5", "x2", "hd720", "fhd1080", "qhd1440", "uhd2160")

WAN_VARS = {
    "default_frames": 81,
    "default_fps": 16,
    "video_director": {
        "family": "wan",
        "preset_modes": ["video"],
        "segment_routing": True,
        "modes": {"t2v": {}, "i2v": {}, "flf": {}, "director": {"max_segments": 8, "max_frames_per_segment": 81}},
        "limits": {"default_duration": 5, "default_fps": 16, "max_duration": 60},
    },
}
H3_VARS = {
    "fps": 24,
    "default_frames": 124,
    "video_director": {
        "family": "minimax_h3",
        "preset_modes": ["video", "refs"],
        "segment_routing": True,
        "modes": {"t2v": {}, "i2v": {}, "flf": {}, "director": {"keyframes": "anywhere", "audio": True, "fps_locked": True}},
        "limits": {"default_duration": 5, "default_fps": 24, "max_duration": 15},
        "preset_mode_overrides": {"refs": {"references": "per_shot", "reference_fields": ["references"]}},
    },
}
LTX25_VARS = {
    "default_frames": 49,
    "default_fps": 25,
    "video_director": {
        "preset_modes": ["video"],
        "modes": {"t2v": {}, "i2v": {}, "flf": {}, "director": {"audio": True, "ic_lora": True, "max_keyframes": 8}},
        "limits": {"default_duration": 5, "default_fps": 25, "max_duration": 40, "max_frames": 1001},
    },
}
OPENROUTER_VARS = {
    "video_director": {
        "family": "cloud",
        "model_field": "model",
        "preset_modes": ["txt2video", "img2video"],
        "segment_routing": True,
        "modes": {"t2v": {}, "director": {"keyframes": "first_only", "fps_locked": True}},
        "limits": {"default_duration": 5, "default_fps": 24, "max_duration": 10},
        "preset_mode_overrides": {"img2video": {"modes": {"t2v": None, "i2v": {}, "flf": {}}}},
    }
}
SEEDVR2_VARS = {"default_scale": 2.0, "promptless_modes": ["upscale", "video_upscale"]}


def _plain(type, default=None, options=(), required=False):
    return {
        "type": type,
        "required": required,
        "default": default,
        "options": [{"value": value, "label": value.upper()} for value in options],
        "recommendations": [],
    }


def _model(name, required=True, sha256="", filename=None):
    sha256 = f"{name}-sha" if sha256 == "" else sha256
    recommendations = [] if sha256 is None and filename is None else [{"sha256": sha256, "filename": filename}]
    return {"type": "model", "required": required, "default": None, "options": [], "recommendations": recommendations}


def wan_fields():
    return {
        "speed_profile": _plain("select", "balanced", ("balanced", "fast", "custom")),
        "seed": _plain("seed", -1),
        "resolution": _plain("resolution", "832x480", WAN_RESOLUTIONS),
        "fps": _plain("slider", 16),
        "text_encoder": _model("text_encoder"),
        "vae": _model("vae"),
        "t2v_high_noise_model": _model("t2v_high_noise_model", required=False),
        "t2v_low_noise_model": _model("t2v_low_noise_model", required=False),
        "i2v_high_noise_model": _model("i2v_high_noise_model", required=False),
        "i2v_low_noise_model": _model("i2v_low_noise_model", required=False),
    }


def h3_video_fields():
    return {
        "speed_profile": _plain("select", "turbo", ("quality", "turbo", "custom")),
        "seed": _plain("seed", -1),
        "quantity": _plain("stepper", 1),
        "resolution": _plain("resolution", "1344x768", H3_RESOLUTIONS),
        "model": _model("model", sha256="fl2va-sha"),
        "text_encoder": _model("h3_text_encoder"),
        "video_vae": _model("video_vae"),
        "audio_vae": _model("audio_vae"),
        "upscale_model": _model("upscale_model", required=False),
    }


def ltx25_fields():
    return {
        "speed_profile": _plain("select", "balanced", ("balanced", "distilled", "quality", "custom")),
        "seed": _plain("seed", -1),
        "resolution": _plain("resolution", "768x512", WAN_RESOLUTIONS),
        "fps": _plain("slider", 25),
        "generate_audio": _plain("checkbox", False),
        "steps": _plain("slider", 24),
        "cfg": _plain("slider", 4.0),
        "sampler": _plain("select", "euler_ancestral", ("euler_ancestral", "euler")),
        "model": _model("model", sha256="ltx25-sha", filename="ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"),
        "text_encoder": _model("gemma4_text_encoder"),
        "video_vae": _model("ltx25_video_vae"),
        "audio_vae": _model("ltx25_audio_vae", required=False),
    }


def h3_refs_fields():
    fields = h3_video_fields()
    fields.pop("upscale_model")
    fields["model"] = _model("model", sha256="ref2va-sha")
    fields["duration"] = _plain("slider", 5)
    fields["references"] = _plain("media")
    fields["reference_image_budget"] = _plain("select", "0", ("0", "1", "2"))
    return fields


def h3_upscale_fields():
    return {
        "input_video": _plain("video", required=True),
        "seed": _plain("seed", -1),
        "quantity": _plain("stepper", 1),
        "target_size": _plain("select", "hd", ("hd", "2k", "1.5x", "2x")),
        "model": _model("model", sha256=None),
        "text_encoder": _model("h3_text_encoder", sha256=None),
        "video_vae": _model("video_vae", sha256=None),
        "audio_vae": _model("audio_vae", sha256=None),
        "upscale_model": _model("upscale_model"),
    }


def seedvr2_video_fields():
    return {
        "restoration_intent": _plain("select", "faithful", ("faithful", "heavy")),
        "resolution_target": _plain("select", "fhd1080", UPSCALE_TARGET_OPTIONS),
        "input_video": _plain("video", required=True),
        "seed": _plain("seed", -1),
        "diffusion_model": _model("diffusion_model", sha256=None),
        "vae": _model("seedvr2_vae", sha256=None),
        "prompt_embedding": _model("prompt_embedding", sha256=None),
    }


def rtx_video_fields(target=True):
    fields = {
        "intent": _plain("select", "upscale", ("upscale", "upscale_highbitrate", "denoise", "deblur")),
        "quality": _plain("select", "ultra", ("low", "medium", "high", "ultra")),
        "input_video": _plain("video", required=True),
        "keep_audio": _plain("checkbox", True),
        "scale": _plain("slider", 2.0),
    }
    if target:
        fields["target_short_side"] = _plain("number", 0)
    return fields


def rife_fields(target=True):
    fields = {
        "input_video": _plain("video", required=True),
        "model": _model("vfi", sha256=None, filename="flownet_v4.25.pth"),
        "factor": _plain("select", 2),
        "keep_audio": _plain("checkbox", True),
        "scene_detection": _plain("checkbox", True),
        "flow_scale": _plain("select", 1.0),
    }
    if target:
        fields["target_fps"] = _plain("select", 0)
    return fields


def frame_generation_fields(target=True):
    fields = {
        "input_video": _plain("video", required=True),
        "factor": _plain("select", 2),
        "mode": _plain("select", "medium", ("low", "medium", "high")),
        "keep_audio": _plain("checkbox", True),
        "scene_detection": _plain("checkbox", True),
    }
    if target:
        fields["target_fps"] = _plain("select", 0)
    return fields


def seedvr2_image_fields():
    return {
        "input_image": _plain("image", required=True),
        "diffusion_model": _model("diffusion_model", sha256=None, filename="seedvr2_ema_3b_fp16.safetensors"),
        "vae": _model("seedvr2_vae", sha256=None, filename="ema_vae_fp16.safetensors"),
        "prompt_embedding": _model("prompt_embedding", sha256=None, filename="pos_emb.pt"),
    }


def cloud_fields():
    return {
        "seed": _plain("seed", -1),
        "aspect_ratio": _plain("select"),
        "resolution": _plain("select"),
        "generate_audio": _plain("checkbox", False),
        "model": _model("model", sha256=None),
        "provider_options": _plain("cloud_options"),
    }


def _param(name, values, default):
    return {
        "name": name,
        "kind": "enum",
        "values": list(values),
        "minimum": None,
        "maximum": None,
        "step": None,
        "default": default,
        "tasks": [],
    }


def cloud_model(model_id="cm-veo", tasks=("img2video", "txt2video"), last_frame=True, durations=(4, 6, 8)):
    inputs = [{"role": "first_frame", "tasks": ["img2video"]}] if "img2video" in tasks else []
    if last_frame and inputs:
        inputs.append({"role": "last_frame", "tasks": ["img2video"]})
    return {
        "id": model_id,
        "name": "Veo 3",
        "provider_model_id": "google/veo-3",
        "tasks": sorted(tasks),
        "typical_seconds": 90,
        "max_seconds": 600,
        "backend_id": "b-cloud",
        "params": [
            _param("duration_s", durations, durations[-1]),
            _param("resolution", ("720p", "1080p"), "720p"),
            _param("aspect_ratio", ("16:9", "9:16"), "16:9"),
        ],
        "inputs": inputs,
    }


BRIDGED = (
    "get_user",
    "list_presets",
    "describe_preset",
    "preset_form_fields",
    "installed_model_id",
    "installed_model_for_file",
    "resolve_media",
    "submit_generation",
    "preview_memory",
    "cancel_generation",
    "generation_state",
    "list_generation_files",
    "record_limit_event",
    "refund_limit_event",
    "limit_status",
    "estimate_cloud_cost",
    "cloud_model",
    "cloud_video_models",
    "notify",
    "run_on_app_loop",
    "image_embedder",
    "embed_images",
    "face_detector",
    "detect_faces",
    "face_identifier",
    "identify_faces",
    "generation_active",
    "module_available",
    "package_version",
)


class FakeCore:
    model_spec = staticmethod(cloud_model)

    def __init__(self, monkeypatch, make_user):
        from backend import core_bridge

        self.bridge = core_bridge
        self.make_user = make_user
        self.users = {}
        self.descriptions = {}
        self.fields = {}
        self.missing = set()
        self.media = {}
        self.submitted = []
        self.refusal = None
        self.states = {}
        self.files = {}
        self.cancelled = []
        self.recorded = []
        self.refunded = []
        self.quota = {"limit": 600, "used": 0, "remaining": 600.0, "exempt": False, "resets_at": None}
        self.quotas = {}
        self.memory = {
            "estimate": {"checkpoint_estimate_gb": 18.5},
            "device": {"kind": "local", "free_gb": 22.0, "total_gb": 24.0},
            "budget": {"configured_gb": None},
            "backend": {"id": "b-local", "name": "This machine", "engine": "native", "driver": "native.local"},
        }
        self.previewed = []
        self.cost = {"known": True, "total_usd": "1.20", "message": None, "shots": []}
        self.costed = []
        self.models = {}
        self.backend_models = {}
        self.notified = []
        self.scheduled = []
        self.counter = 0
        self.busy = False
        self.embedder = {"model": "google/siglip-base-patch16-224", "slug": "local-google-siglip-base-patch16-224", "device": "cpu", "available": True, "loaded": False}
        self.faces = {"model": "face_detection_yunet_2023mar.onnx", "available": False}
        self.face_boxes = {}
        self.identity = {"model": "glintr100.onnx", "path": "/models/face_recognition/auraface/glintr100.onnx", "available": False}
        self.identities = {}
        self.embedded = []
        self.modules = set()
        self.versions = {}
        for user_id in ("user-1", "user-2"):
            self.add_user(user_id)
        self.add_user("admin-1", admin=True)
        for name in BRIDGED:
            monkeypatch.setattr(core_bridge, name, getattr(self, name))

    def close(self):
        for coroutine in self.scheduled:
            coroutine.close()

    def add_user(self, user_id, admin=False):
        from src.plugin_api import AccountType

        self.users[user_id] = self.make_user(AccountType.ADMIN if admin else AccountType.USER, user_id=user_id)
        return self.users[user_id]

    def add_preset(self, preset_id, name, modes, engine="native", category="video", variables=None):
        from src.plugin_api import FieldDescription, ModeDescription, PresetDescription

        described = {
            mode: ModeDescription(
                default_form="custom",
                forms={
                    "custom": {key: FieldDescription(type=spec["type"], required=spec["required"]) for key, spec in fields.items()}
                },
            )
            for mode, fields in modes.items()
        }
        self.descriptions[preset_id] = PresetDescription(
            id=preset_id, name=name, vars=variables or {}, modes=described, engine=engine, category=category
        )
        for mode, fields in modes.items():
            self.fields[(preset_id, mode)] = fields
        return self.descriptions[preset_id]

    def use_wan(self):
        return self.add_preset(WAN_ID, "Wan 2.1 / 2.2", {"video": wan_fields()}, variables=WAN_VARS)

    def use_h3(self):
        return self.add_preset(
            H3_ID,
            "MiniMax-H3",
            {"video": h3_video_fields(), "refs": h3_refs_fields(), "upscale": h3_upscale_fields()},
            variables=H3_VARS,
        )

    def use_ltx25(self):
        return self.add_preset(LTX25_ID, "LTX-2.5", {"video": ltx25_fields()}, variables=LTX25_VARS)

    def use_h3_variant(self, preset_id, name):
        director = {**H3_VARS["video_director"], "preset_modes": ["video"]}
        director.pop("preset_mode_overrides")
        return self.add_preset(preset_id, name, {"video": h3_video_fields()}, variables={**H3_VARS, "video_director": director})

    def use_seedvr2(self):
        return self.add_preset(
            SEEDVR2_ID,
            "SeedVR2",
            {"upscale": seedvr2_image_fields(), "video_upscale": seedvr2_video_fields()},
            category="utility",
            variables=SEEDVR2_VARS,
        )

    def use_rtx(self, target=True, installed=True):
        if installed:
            self.modules.add("nvvfx")
        return self.add_preset(RTX_ID, "RTX Upscale", {"upscale": {}, "video_upscale": rtx_video_fields(target)}, category="utility")

    def module_available(self, name):
        return name in self.modules

    def package_version(self, name):
        return self.versions.get(name)

    def use_video_tools(self, target=True):
        return self.add_preset(VIDEO_TOOLS_ID, "Video Tools", {"interpolate": rife_fields(target)}, category="utility")

    def use_frame_generation(self, version="0.2.0.0", target=True):
        self.modules.add("nvvfx")
        self.versions["nvidia-vfx"] = version
        return self.add_preset(
            RTX_ID,
            "RTX Upscale",
            {"upscale": {}, "video_upscale": rtx_video_fields(), "interpolate": frame_generation_fields(target)},
            category="utility",
        )

    def use_openrouter(self, model=None):
        model = model or cloud_model()
        self.models[model["id"]] = model
        return self.add_preset(
            OPENROUTER_ID,
            "OpenRouter Video",
            {"txt2video": cloud_fields(), "img2video": cloud_fields()},
            engine="cloud",
            variables=OPENROUTER_VARS,
        )

    def get_user(self, user_id):
        return self.users.get(user_id)

    def list_presets(self, user):
        return list(self.descriptions.values())

    def describe_preset(self, preset_id):
        return self.descriptions.get(preset_id)

    def preset_form_fields(self, preset_id, mode):
        return self.fields.get((preset_id, mode))

    def installed_model_id(self, sha256):
        return None if sha256 in self.missing else f"id-{sha256}"

    def installed_model_for_file(self, filename):
        return None if filename in self.missing else f"id-{filename}"

    def add_media(self, ref, value, media_type="image", origin=None):
        self.media[tuple(sorted(ref.items()))] = {
            "value": value,
            "media_type": media_type,
            "original_filename": value.rsplit("/", 1)[-1],
            "origin": origin,
        }

    def resolve_media(self, user, ref):
        found = self.media.get(tuple(sorted(ref.items())))
        if found is None:
            raise self.bridge.MediaRefError("not_found", "The referenced media is not available")
        return dict(found)

    async def submit_generation(self, user, request):
        if self.refusal is not None:
            raise self.refusal
        self.counter += 1
        generation_id = f"gen-{self.counter}"
        self.submitted.append((user.id, request))
        self.states[generation_id] = {"id": generation_id, "status": "pending", "progress": None, "backend_id": None}
        return {"generation_id": generation_id, "status": "pending", "queue_position": 1}

    async def preview_memory(self, user, request):
        self.previewed.append((user.id, request))
        if isinstance(self.memory, Exception):
            raise self.memory
        return dict(self.memory)

    async def cancel_generation(self, user, generation_id):
        self.cancelled.append((user.id, generation_id))
        if generation_id in self.states:
            self.states[generation_id]["status"] = "cancelled"
        return True

    def generation_state(self, user, generation_id):
        if generation_id not in self.states:
            raise self.bridge.GenerationNotFoundException(f"Generation {generation_id} not found")
        return dict(self.states[generation_id])

    def list_generation_files(self, user, generation_id):
        if generation_id not in self.states:
            raise self.bridge.GenerationNotFoundException(f"Generation {generation_id} not found")
        return [dict(item) for item in self.files.get(generation_id, [])]

    def complete(self, generation_id, duration_ms=60000, width=832, height=480, seconds=4.0, fps=16.0, thumbnail=True):
        self.states[generation_id] = {
            "id": generation_id,
            "status": "completed",
            "progress": 1.0,
            "backend_id": "b-local",
            "started_at": "2026-10-17T10:00:00+00:00",
            "duration_ms": duration_ms,
        }
        self.files[generation_id] = [
            {"id": "file-0", "file_type": "IMAGE", "file_path": f"generations/2026-10-17/{generation_id}/0.png"},
            {
                "id": f"file-{generation_id}",
                "file_type": "VIDEO",
                "mime_type": "video/mp4",
                "file_path": f"generations/2026-10-17/{generation_id}/1.mp4",
                "thumbnail_medium": f"generations/2026-10-17/{generation_id}/thumb.webp" if thumbnail else None,
                "width": width,
                "height": height,
                "duration_seconds": seconds,
                "fps": fps,
            },
        ]

    def fail(self, generation_id, code="cuda_oom", message="The GPU ran out of memory.", **stored):
        self.states[generation_id] = {
            "id": generation_id,
            "status": "failed",
            "error_code": code,
            "error_user_message": message,
            "message": "raw",
            "backend_id": "b-local",
            **stored,
        }

    def record_limit_event(self, user_id, kind, units, ref_id):
        self.recorded.append((user_id, kind, units, ref_id))
        return True

    def refund_limit_event(self, ref_id):
        self.refunded.append(ref_id)
        return 1

    def limit_status(self, user_id, kind):
        if kind == "video-producer.gpu_minutes":
            return dict(self.quota)
        return dict(self.quotas.get(kind, {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}))

    def estimate_cloud_cost(self, user, model_id, shots):
        from src.plugin_api import AccountType

        if user.account_type != AccountType.ADMIN:
            raise PermissionError("Only an administrator can see what a cloud run costs")
        self.costed.append((model_id, shots))
        if isinstance(self.cost, Exception):
            raise self.cost
        return dict(self.cost)

    def cloud_model(self, model_id):
        return self.models.get(model_id)

    def cloud_video_models(self, backend_id):
        return list(self.backend_models.get(backend_id, []))

    def notify(self, **kwargs):
        self.notified.append(kwargs)

    def image_embedder(self):
        return dict(self.embedder)

    def embed_images(self, paths):
        from PIL import Image

        self.embedded.append([str(path) for path in paths])
        if not self.embedder["available"]:
            raise FileNotFoundError("The weights of the image embedder are not on this server")
        vectors = []
        for path in paths:
            with Image.open(path) as image:
                r, g, b = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
            values = [r + 1.0, g + 1.0, b + 1.0, 8.0]
            norm = sum(v * v for v in values) ** 0.5
            vectors.append([v / norm for v in values])
        return vectors

    def face_detector(self):
        return dict(self.faces)

    def detect_faces(self, paths):
        from PIL import Image

        if not self.faces["available"]:
            raise FileNotFoundError("face_detection_yunet_2023mar.onnx is not in a detection_bbox folder of the model roots")
        found = []
        for path in paths:
            with Image.open(path) as image:
                color = image.convert("RGB").getpixel((0, 0))
            found.append([dict(box) for box in self.face_boxes.get(color, [])])
        return found

    def face_identifier(self):
        return dict(self.identity)

    def identify_faces(self, faces):
        from PIL import Image

        if not self.identity["available"]:
            raise FileNotFoundError("glintr100.onnx is not at /models/face_recognition/auraface/glintr100.onnx")
        vectors = []
        for path, landmarks in faces:
            with Image.open(path) as image:
                color = image.convert("RGB").getpixel(tuple(round(value) for value in landmarks[2]))
            vectors.append(list(self.identities.get(color, [1.0, 0.0])))
        return vectors

    def generation_active(self):
        return self.busy

    def run_on_app_loop(self, coroutine):
        import concurrent.futures

        self.scheduled.append(coroutine)
        return concurrent.futures.Future()


@pytest.fixture
def core(monkeypatch, make_user, project_db, store):
    fake = FakeCore(monkeypatch, make_user)
    yield fake
    fake.close()


_SHAPES = {
    "clips": {
        "assetId": None,
        "start": 0,
        "dur": 4,
        "srcIn": 0,
        "label": "",
        "stage": "todo",
        "take": None,
        "fadeIn": 0,
        "fadeOut": 0,
        "exposure": 0,
        "contrast": 100,
        "saturation": 100,
        "temperature": 0,
        "preset": "Original",
        "flag": None,
    },
    "prompts": {"shotId": None, "start": 0, "dur": 4, "strength": 75, "text": ""},
    "frames": {"shotId": None, "time": 0, "assetId": None, "role": "Transition", "strength": 75},
    "references": {"name": "", "space": "identite", "type": "image", "assetId": None, "role": "Identité", "scope": None},
    "assets": {
        "kind": "image",
        "name": "",
        "src": None,
        "origin": None,
        "srcDur": None,
        "width": None,
        "height": None,
        "fps": None,
        "res": None,
        "generated": False,
        "quality": None,
        "resultId": None,
        "role": None,
    },
}


@pytest.fixture
def make_doc():
    import json

    def make(clips=(), prompts=(), frames=(), references=(), assets=(), direction=None, aspect="16:9", language="en"):
        doc = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "empty_doc.json").read_text(encoding="utf-8"))
        doc["aspect"] = aspect
        doc["promptLanguage"] = language
        doc["direction"] = {**doc["direction"], **(direction or {})}
        parts = {"clips": clips, "prompts": prompts, "frames": frames, "references": references, "assets": assets}
        for kind, items in parts.items():
            doc[kind] = [{**_SHAPES[kind], **item} for item in items]
        return doc

    return make


@pytest.fixture
def make_project(project_db, make_doc):
    from backend import projects

    def make(user_id="user-1", doc=None, **parts):
        return projects.create_project(user_id, doc if doc is not None else make_doc(**parts))

    return make


class MediaStore:
    def __init__(self):
        self.saved = []
        self.items = {}

    async def save_user_media(self, user, path):
        from pathlib import Path

        source = Path(path)
        self.saved.append({"user_id": user.id, "name": source.name, "data": source.read_bytes()})
        value = f"uploads/{len(self.saved):04d}-{source.name}"
        self.items[value] = f"item-{len(self.saved)}"
        return {"value": value, "media_type": "image", "original_filename": source.name, "origin": None}

    def upload_item(self, user_id, value):
        item = self.items.get(value)
        return None if item is None else {"item_id": item, "filename": value.rsplit("/", 1)[-1], "width": 832, "height": 468}


@pytest.fixture
def media_store(monkeypatch):
    from backend import core_bridge

    store = MediaStore()
    monkeypatch.setattr(core_bridge, "save_user_media", store.save_user_media)
    monkeypatch.setattr(core_bridge, "upload_item", store.upload_item)
    return store
