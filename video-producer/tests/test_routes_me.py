import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.plugin_api.limits as api_limits
from backend import core_bridge, director, presets, projects
from src.plugin_api import AccountType, FieldDescription, ModeDescription, PresetDescription, get_current_active_user
from src.plugin_api.cloud import CLOUD_ENGINE
from src.plugin_api.limits import LimitStatus

ME_URL = "/api/plugins/video-producer/me"
LOGGER = "plugins.video-producer"

DEFAULT_SETTINGS = {"draft_resolution": "832x480", "max_parallel_jobs": 2, "export_dir_quota_mb": 2048, "versions_kept": 50}
UNLIMITED = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}

WAN_DIRECTOR = {
    "family": "wan",
    "preset_modes": ["video"],
    "segment_routing": True,
    "modes": {"t2v": {}, "i2v": {}, "flf": {}, "director": {"max_segments": 8, "max_frames_per_segment": 81}},
    "limits": {"default_duration": 5, "default_fps": 16, "max_duration": 60},
}
OPENROUTER_DIRECTOR = {"family": "cloud", "preset_modes": ["txt2video", "img2video"], "model_field": "model"}


class Catalog:
    def __init__(self, monkeypatch):
        self.backends = []
        self.presets = []
        self.asked = []
        self.broken = set()
        self.fields = {}
        self.models = {}
        self.drivers = {}
        monkeypatch.setattr(core_bridge, "api_backends", SimpleNamespace(list_backends=self._backends))
        monkeypatch.setattr(core_bridge, "api_presets", SimpleNamespace(list_presets=self._presets))
        monkeypatch.setattr(core_bridge, "preset_form_fields", self._fields)
        monkeypatch.setattr(core_bridge, "cloud_video_models", self._models)
        monkeypatch.setattr(core_bridge, "preset_driver", self._driver)

    def _driver(self, preset_id):
        if "drivers" in self.broken:
            raise RuntimeError("AppContainer not initialized yet")
        return self.drivers.get(preset_id)

    def _fields(self, preset_id, mode):
        if "fields" in self.broken:
            raise RuntimeError("AppContainer not initialized yet")
        return self.fields.get((preset_id, mode))

    def _models(self, backend_id):
        if "models" in self.broken:
            raise RuntimeError("AppContainer not initialized yet")
        return list(self.models.get(backend_id, []))

    def _backends(self):
        if "backends" in self.broken:
            raise RuntimeError("AppContainer not initialized yet")
        return list(self.backends)

    def _presets(self, user):
        self.asked.append(user.id)
        if "presets" in self.broken:
            raise RuntimeError("AppContainer not initialized yet")
        return list(self.presets)


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    return Catalog(monkeypatch)


def _backend(backend_id, name, engine="native", driver="native.local", **reported):
    return {
        "id": backend_id,
        "name": name,
        "engine": engine,
        "driver": driver,
        "enabled": True,
        "priority": 0,
        "timeout_seconds": 300,
        "configured": True,
        "is_default": False,
        "quick_actions": [],
        "has_api_key": True,
        "execution_device": "unestablished",
        "max_concurrent_runs": None,
        "vram_total_gb": None,
        "vram_free_gb": None,
        **reported,
    }


def _field(type, required=False, multi=False):
    return FieldDescription(type=type, required=required, multi=multi)


def _mode(default_form="custom", **forms):
    return ModeDescription(default_form=default_form, forms=forms or {"custom": {}})


def _description(preset_id, name, engine="native", category="video", vars=None, modes=None, requires=None):
    return PresetDescription(
        id=preset_id,
        name=name,
        vars=vars or {},
        modes=modes or {},
        engine=engine,
        category=category,
        requires=requires,
    )


def _wan():
    fields = {"resolution": _field("resolution"), "text_encoder": _field("model", required=True), "fps": _field("slider")}
    return _description(
        presets.WAN,
        "Wan 2.1 / 2.2",
        vars={"default_frames": 81, "default_fps": 16, "video_director": WAN_DIRECTOR},
        modes={"video": _mode(custom=fields)},
        requires={"min_vram_gb": 12.0, "recommended_vram_gb": 16.0},
    )


def _openrouter_video():
    fields = {"aspect_ratio": _field("select"), "resolution": _field("select"), "model": _field("model", required=True)}
    return _description(
        presets.OPENROUTER_VIDEO,
        "OpenRouter Video",
        engine=CLOUD_ENGINE,
        vars={"video_director": OPENROUTER_DIRECTOR},
        modes={"txt2video": _mode(custom=fields), "img2video": _mode(custom=fields)},
    )


def _seedvr2():
    return _description(
        presets.SEEDVR2,
        "SeedVR2",
        category="utility",
        vars={"default_scale": 2, "promptless_modes": ["upscale", "video_upscale"]},
        modes={
            "upscale": _mode(custom={"input_image": _field("image", required=True)}),
            "video_upscale": _mode(custom={"input_video": _field("video", required=True), "scale": _field("slider")}),
        },
    )


def _flux():
    return _description(
        "01M0J6CPKRJZW0SVEXMZ90CM7K", "Flux1", category="image", modes={"txt2img": _mode(), "img2img": _mode()}
    )


def _video_tools():
    return _description(
        "01KXVIDEOTOOLS0000000000VT", "Video Tools", category="utility", modes={"interpolate": _mode()}
    )


def _quota(monkeypatch, **status):
    asked = []

    def limit_status(user_id, kind):
        asked.append((user_id, kind))
        return LimitStatus(kind=kind, **status)

    monkeypatch.setattr(api_limits, "limit_status", limit_status)
    return asked


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def test_me_without_a_saved_locale_or_settings_reports_the_defaults(client, store, no_container, monkeypatch):
    from backend import core_bridge

    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "locale": None,
            "last_project_id": None,
            "is_admin": False,
            "limits": {"gpu_minutes": UNLIMITED},
            "settings": DEFAULT_SETTINGS,
            "plugin": {"id": "video-producer", "version": "0.1.0"},
            "engines": [],
            "presets": [],
            "measured": {},
            "keyframe_presets": [],
            "features": {"upscaler": False, "guided": False},
            "upscale_targets": ["hd720", "fhd1080", "qhd1440", "uhd2160"],
            "ffmpeg": False,
        },
    }


@pytest.mark.parametrize("account_type, is_admin", [(AccountType.USER, False), (AccountType.ADMIN, True)])
def test_me_tells_whether_the_user_is_an_admin(app, client, make_user, store, no_container, account_type, is_admin):
    _as(app, make_user(account_type))

    assert client.get(ME_URL).json()["data"]["is_admin"] is is_admin


def test_me_names_the_plugin_and_its_version(client, store, no_container):
    assert client.get(ME_URL).json()["data"]["plugin"] == {"id": "video-producer", "version": "0.1.0"}


def test_me_asks_for_the_quota_of_the_signed_in_user(app, client, make_user, store, monkeypatch):
    asked = _quota(monkeypatch)
    _as(app, make_user(user_id="user-7"))

    client.get(ME_URL)

    assert asked == [("user-7", "video-producer.gpu_minutes")]


def test_me_reports_no_quota_for_a_user_without_a_limit(client, store, monkeypatch):
    _quota(monkeypatch)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == UNLIMITED


def test_me_reports_no_remaining_minutes_for_an_exempt_admin(app, client, make_user, store, monkeypatch):
    _quota(monkeypatch, limit=600, exempt=True)
    _as(app, make_user(AccountType.ADMIN))

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == {
        "limit": 600,
        "used": None,
        "remaining": None,
        "exempt": True,
        "resets_at": None,
    }


def test_me_reports_the_quota_used_remaining_and_reset_of_a_limited_user(client, store, monkeypatch):
    _quota(monkeypatch, limit=600, used=125.5, resets_at=datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"] == {
        "limit": 600,
        "used": 125.5,
        "remaining": 474.5,
        "exempt": False,
        "resets_at": "2026-11-01T00:00:00+00:00",
    }


def test_me_tells_the_reset_in_utc_whatever_the_offset(client, store, monkeypatch):
    local = datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=2)))
    _quota(monkeypatch, limit=10, used=1, resets_at=local)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"]["resets_at"] == "2026-10-31T22:00:00+00:00"


def test_me_reports_no_remaining_minutes_once_the_quota_is_used_up(client, store, monkeypatch):
    _quota(monkeypatch, limit=60, used=75)

    assert client.get(ME_URL).json()["data"]["limits"]["gpu_minutes"]["remaining"] == 0.0


def test_me_types_the_admin_settings_from_their_stored_strings(client, store, no_container):
    store.update(
        {
            ("draft_resolution", None): "1280x720",
            ("max_parallel_jobs", None): "4",
            ("export_dir_quota_mb", None): "512",
            ("versions_kept", None): "12",
        }
    )

    assert client.get(ME_URL).json()["data"]["settings"] == {
        "draft_resolution": "1280x720",
        "max_parallel_jobs": 4,
        "export_dir_quota_mb": 512,
        "versions_kept": 12,
    }


def test_me_falls_back_to_the_default_of_a_setting_that_cannot_be_read(client, store, no_container):
    store.update(
        {
            ("draft_resolution", None): "640x480",
            ("max_parallel_jobs", None): "many",
            ("export_dir_quota_mb", None): "not a number",
            ("versions_kept", None): "forever",
        }
    )

    assert client.get(ME_URL).json()["data"]["settings"] == DEFAULT_SETTINGS


def test_me_reads_the_settings_of_the_admin_and_the_locale_of_the_user(client, store, no_container):
    store.update({("locale", "user-1"): "fr", ("locale", None): "en", ("max_parallel_jobs", "user-1"): "9"})

    data = client.get(ME_URL).json()["data"]

    assert data["locale"] == "fr"
    assert data["settings"]["max_parallel_jobs"] == 2


def test_me_ignores_a_stored_locale_it_does_not_support(client, store, no_container):
    store[("locale", "user-1")] = "de"

    assert client.get(ME_URL).json()["data"]["locale"] is None


@pytest.mark.parametrize("locale", ["en", "fr"])
def test_put_me_saves_the_locale_for_the_user_only(client, store, no_container, locale):
    response = client.put(ME_URL, json={"locale": locale})

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"locale": locale, "last_project_id": None}}
    assert store == {("locale", "user-1"): locale}
    assert client.get(ME_URL).json()["data"]["locale"] == locale


def test_put_me_keeps_the_last_locale_and_ignores_other_keys(client, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})
    response = client.put(ME_URL, json={"locale": "en", "theme": "dark"})

    assert response.json() == {"success": True, "data": {"locale": "en", "last_project_id": None}}
    assert store == {("locale", "user-1"): "en"}


def test_the_locale_of_a_user_is_not_seen_by_another_one(app, client, make_user, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})
    _as(app, make_user(user_id="user-2"))

    assert client.get(ME_URL).json()["data"]["locale"] is None
    assert client.put(ME_URL, json={"locale": "en"}).status_code == 200
    assert store == {("locale", "user-1"): "fr", ("locale", "user-2"): "en"}


@pytest.mark.parametrize(
    "body",
    [
        {"locale": "de"},
        {"locale": "FR"},
        {"locale": " fr"},
        {"locale": ""},
        {"locale": None},
        {"locale": 0},
        {"locale": 3},
        {"locale": True},
        {"locale": ["fr"]},
        {"locale": {"code": "fr"}},
        {"locale": "de", "last_project_id": None},
        {},
        {"language": "fr"},
        ["fr"],
        "fr",
        3,
        None,
    ],
    ids=repr,
)
def test_put_me_refuses_an_unsupported_locale(client, store, body):
    response = client.put(ME_URL, json=body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["success"] is False
    assert detail["error"] == "invalid_locale"
    assert "en" in detail["message"] and "fr" in detail["message"]
    assert store == {}


def test_put_me_refuses_a_body_that_is_not_json(client, store):
    response = client.put(ME_URL, content="locale=fr", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert store == {}


def test_a_refused_locale_leaves_the_saved_one_alone(client, store, no_container):
    client.put(ME_URL, json={"locale": "fr"})

    assert client.put(ME_URL, json={"locale": "de"}).status_code == 422
    assert client.get(ME_URL).json()["data"]["locale"] == "fr"


@pytest.mark.parametrize("method", ["get", "put"])
def test_me_needs_a_signed_in_user(app, store, method):
    app.dependency_overrides.clear()
    options = {"json": {"locale": "fr"}} if method == "put" else {}

    with TestClient(app) as anonymous:
        response = getattr(anonymous, method)(ME_URL, **options)

    assert response.status_code == 401
    assert store == {}


def test_the_locale_goes_through_the_plugin_repository_with_the_user_id(client, no_container, monkeypatch):
    calls = []

    class Repository:
        def get_plugin_setting(self, plugin_id, setting_key, user_id=None):
            calls.append(("get", plugin_id, setting_key, user_id))
            return SimpleNamespace(setting_value="fr") if setting_key == "locale" else None

        def set_plugin_setting(self, plugin_id, setting_key, setting_value, user_id=None, is_secret=False):
            calls.append(("set", plugin_id, setting_key, setting_value, user_id))

    monkeypatch.setattr(core_bridge, "PluginRepository", Repository)

    assert client.put(ME_URL, json={"locale": "en"}).status_code == 200
    assert client.get(ME_URL).json()["data"]["locale"] == "fr"

    assert calls[0] == ("set", "video-producer", "locale", "en", "user-1")
    assert ("get", "video-producer", "locale", "user-1") in calls
    assert ("get", "video-producer", "draft_resolution", None) in calls


def test_me_lists_the_native_and_cloud_engines_with_their_kind_in_priority_order(client, store, no_container, catalog):
    catalog.backends = [
        _backend(
            "b-local",
            "This machine",
            is_default=True,
            execution_device="this_host_gpu",
            max_concurrent_runs=1,
            vram_total_gb=24.0,
            vram_free_gb=20.5,
        ),
        _backend("b-remote", "Render box", driver="native.remote", execution_device="remote", max_concurrent_runs=2),
        _backend("b-cloud", "OpenRouter", engine=CLOUD_ENGINE, driver="cloud.openrouter", is_default=True),
    ]

    assert client.get(ME_URL).json()["data"]["engines"] == [
        {
            "id": "b-local",
            "name": "This machine",
            "engine": "native",
            "driver": "native.local",
            "execution_device": "this_host_gpu",
            "max_concurrent_runs": 1,
            "vram_total_gb": 24.0,
            "vram_free_gb": 20.5,
            "is_default": True,
            "kind": "local",
        },
        {
            "id": "b-remote",
            "name": "Render box",
            "engine": "native",
            "driver": "native.remote",
            "execution_device": "remote",
            "max_concurrent_runs": 2,
            "vram_total_gb": None,
            "vram_free_gb": None,
            "is_default": False,
            "kind": "remote",
        },
        {
            "id": "b-cloud",
            "name": "OpenRouter",
            "engine": "cloud",
            "driver": "cloud.openrouter",
            "execution_device": "unestablished",
            "max_concurrent_runs": None,
            "vram_total_gb": None,
            "vram_free_gb": None,
            "is_default": True,
            "kind": "cloud",
            "models": [],
        },
    ]


@pytest.mark.parametrize(
    "engine, driver",
    [("comfyui", "comfyui"), ("comfyui", "comfyui.remote"), ("native", "native.experimental"), ("acme", "acme.local")],
)
def test_me_never_lists_comfyui_or_an_engine_takes_cannot_run_on(client, store, no_container, catalog, engine, driver):
    catalog.backends = [_backend("b-other", "Other", engine=engine, driver=driver), _backend("b-local", "This machine")]

    assert [listed["id"] for listed in client.get(ME_URL).json()["data"]["engines"]] == ["b-local"]


def test_me_lists_no_engine_and_logs_when_the_backends_cannot_be_read(client, store, no_container, catalog, caplog):
    catalog.broken.add("backends")
    catalog.presets = [_wan()]

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        data = client.get(ME_URL).json()["data"]

    assert data["engines"] == []
    assert [preset["id"] for preset in data["presets"]] == [presets.WAN]
    assert "Could not list the backends" in caplog.text


def test_me_describes_a_video_director_preset_with_its_modes_fields_and_director(client, store, no_container, catalog):
    catalog.presets = [_wan()]

    assert client.get(ME_URL).json()["data"]["presets"] == [
        {
            "id": presets.WAN,
            "name": "Wan 2.1 / 2.2",
            "engine": "native",
            "category": "video",
            "requires": {"min_vram_gb": 12.0, "recommended_vram_gb": 16.0},
            "profile": None,
            "modes": {
                "video": {
                    "default_form": "custom",
                    "fields": {
                        "resolution": {"type": "resolution", "required": False, "multi": False},
                        "text_encoder": {"type": "model", "required": True, "multi": False},
                        "fps": {"type": "slider", "required": False, "multi": False},
                    },
                    "options": [],
                }
            },
            "video_director": WAN_DIRECTOR,
            "upscaler": False,
            "resolutions": [],
            "fps": 16,
            "fps_locked": False,
            "limits": {"default_duration": 5, "default_fps": 16, "max_duration": 60},
            "director_modes": ["t2v", "i2v", "flf", "director"],
            "audio_mux": False,
            "profiles": ["FL2VA"],
            "driver": None,
            "backend_id": None,
        }
    ]


def test_me_gives_the_sizes_each_listed_preset_was_measured_at_by_backend(client, store, no_container, catalog, project_db):
    from backend import takes

    catalog.presets = [_wan()]
    for preset_id, backend_id, resolution in (
        (presets.WAN, "b-gpu", "832x480"),
        (presets.WAN, "b-gpu", "832x480"),
        (presets.WAN, "b-gpu", "1280x720"),
        (presets.WAN, "b-other", "960x544"),
        (presets.SEEDVR2, "b-gpu", "1920x1080"),
    ):
        takes.add_calibration(preset_id, backend_id, resolution, 5.0, 50000)

    assert client.get(ME_URL).json()["data"]["measured"] == {presets.WAN: {"b-gpu": ["1280x720", "832x480"], "b-other": ["960x544"]}}


def test_me_reports_no_measured_size_and_logs_when_they_cannot_be_read(client, store, no_container, catalog, monkeypatch, caplog):
    from backend import takes

    catalog.presets = [_wan()]

    def broken(preset_ids):
        raise RuntimeError("no table")

    monkeypatch.setattr(takes, "measured_sizes", broken)

    with caplog.at_level(logging.WARNING):
        data = client.get(ME_URL).json()["data"]

    assert data["measured"] == {}
    assert [preset["id"] for preset in data["presets"]] == [presets.WAN]
    assert "Could not read the measured sizes" in caplog.text


def test_me_lists_the_cloud_video_presets_too(client, store, no_container, catalog):
    catalog.presets = [_openrouter_video()]

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert (preset["engine"], preset["requires"], preset["upscaler"]) == ("cloud", None, False)
    assert list(preset["modes"]) == ["txt2video", "img2video"]
    assert preset["video_director"] == OPENROUTER_DIRECTOR


def test_me_marks_seedvr2_as_the_upscaler_without_a_director(client, store, no_container, catalog):
    catalog.presets = [_seedvr2()]

    assert client.get(ME_URL).json()["data"]["presets"] == [
        {
            "id": presets.SEEDVR2,
            "name": "SeedVR2",
            "engine": "native",
            "category": "utility",
            "requires": None,
            "profile": None,
            "modes": {
                "upscale": {
                    "default_form": "custom",
                    "fields": {"input_image": {"type": "image", "required": True, "multi": False}},
                },
                "video_upscale": {
                    "default_form": "custom",
                    "fields": {
                        "input_video": {"type": "video", "required": True, "multi": False},
                        "scale": {"type": "slider", "required": False, "multi": False},
                    },
                },
            },
            "video_director": None,
            "upscaler": True,
            "resolutions": [],
            "fps": None,
            "fps_locked": False,
            "limits": {},
            "director_modes": [],
            "audio_mux": False,
            "profiles": [],
            "driver": None,
            "backend_id": None,
        }
    ]


def test_me_leaves_out_the_presets_the_video_director_does_not_drive(client, store, no_container, catalog):
    named_video = _description("01VIDEOMODEONLY00000000000", "Video modes only", modes={"video": _mode(), "txt2video": _mode()})
    catalog.presets = [_flux(), _wan(), _video_tools(), named_video, _seedvr2(), _openrouter_video()]

    listed = client.get(ME_URL).json()["data"]["presets"]

    assert [(preset["id"], preset["upscaler"]) for preset in listed] == [
        (presets.WAN, False),
        (presets.SEEDVR2, True),
        (presets.OPENROUTER_VIDEO, False),
    ]


def test_me_lists_the_presets_of_the_signed_in_user(app, client, make_user, store, no_container, catalog):
    _as(app, make_user(user_id="user-9"))

    client.get(ME_URL)

    assert catalog.asked and set(catalog.asked) == {"user-9"}


def test_me_lists_no_preset_and_logs_when_the_presets_cannot_be_read(client, store, no_container, catalog, caplog):
    catalog.broken.add("presets")
    catalog.backends = [_backend("b-local", "This machine")]

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        data = client.get(ME_URL).json()["data"]

    assert data["presets"] == []
    assert [engine["id"] for engine in data["engines"]] == ["b-local"]
    assert "Could not list the presets of user user-1" in caplog.text


def test_me_gives_the_fields_of_the_default_form_or_else_of_the_first_one(client, store, no_container, catalog):
    quick = {"prompt_strength": _field("slider")}
    full = {"resolution": _field("resolution"), "references": _field("media", multi=True)}
    catalog.presets = [
        _description(
            "01FORMS0000000000000000000",
            "Forms",
            vars={"video_director": {}},
            modes={
                "video": _mode(default_form="full", quick=quick, full=full),
                "refs": _mode(default_form=None, full=full, quick=quick),
                "empty": ModeDescription(default_form=None, forms={}),
            },
        )
    ]

    modes = client.get(ME_URL).json()["data"]["presets"][0]["modes"]

    assert modes["video"] == {
        "default_form": "full",
        "fields": {
            "resolution": {"type": "resolution", "required": False, "multi": False},
            "references": {"type": "media", "required": False, "multi": True},
        },
    }
    assert modes["refs"] == {"default_form": None, "fields": modes["video"]["fields"]}
    assert modes["empty"] == {"default_form": None, "fields": {}}


def _doc():
    return json.loads((Path(__file__).resolve().parent / "fixtures" / "empty_doc.json").read_text(encoding="utf-8"))


@pytest.fixture
def owned(project_db, store):
    return projects.create_project("user-1", _doc())["id"]


def test_the_last_project_goes_there_and_back(client, store, no_container, owned):
    response = client.put(ME_URL, json={"last_project_id": owned})

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"locale": None, "last_project_id": owned}}
    assert store == {("last_project_id", "user-1"): owned}
    assert client.get(ME_URL).json()["data"]["last_project_id"] == owned


def test_the_locale_and_the_last_project_are_saved_together(client, store, no_container, owned):
    response = client.put(ME_URL, json={"locale": "fr", "last_project_id": owned})

    assert response.json()["data"] == {"locale": "fr", "last_project_id": owned}
    assert store == {("locale", "user-1"): "fr", ("last_project_id", "user-1"): owned}


def test_saving_the_locale_alone_keeps_the_last_project(client, store, no_container, owned):
    client.put(ME_URL, json={"last_project_id": owned})

    response = client.put(ME_URL, json={"locale": "en"})

    assert response.json()["data"] == {"locale": "en", "last_project_id": owned}
    assert store[("last_project_id", "user-1")] == owned


def test_saving_the_last_project_alone_keeps_the_locale(client, store, no_container, owned):
    client.put(ME_URL, json={"locale": "fr"})

    response = client.put(ME_URL, json={"last_project_id": owned})

    assert response.json()["data"] == {"locale": "fr", "last_project_id": owned}
    assert store[("locale", "user-1")] == "fr"


def test_null_forgets_the_last_project(client, store, no_container, owned):
    client.put(ME_URL, json={"last_project_id": owned})

    response = client.put(ME_URL, json={"last_project_id": None})

    assert response.status_code == 200
    assert response.json()["data"] == {"locale": None, "last_project_id": None}
    assert store[("last_project_id", "user-1")] is None
    assert client.get(ME_URL).json()["data"]["last_project_id"] is None


def test_the_project_of_another_user_cannot_be_the_last_one(client, store, no_container, project_db):
    theirs = projects.create_project("user-2", _doc())["id"]

    response = client.put(ME_URL, json={"last_project_id": theirs})

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert (detail["success"], detail["error"]) == (False, "project_not_found")
    assert store == {}


def test_even_an_admin_keeps_only_their_own_project_as_the_last_one(app, client, make_user, store, no_container, owned):
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    assert client.put(ME_URL, json={"last_project_id": owned}).status_code == 404
    assert store == {}


@pytest.mark.parametrize("project_id", ["01UNKNOWNPROJECT0000000000", ""])
def test_an_unknown_project_cannot_be_the_last_one(client, store, no_container, project_db, project_id):
    response = client.put(ME_URL, json={"last_project_id": project_id})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"
    assert store == {}


@pytest.mark.parametrize("project_id", [3, True, ["p"], {"id": "p"}], ids=repr)
def test_a_last_project_id_that_is_not_text_or_null_is_refused(client, store, no_container, project_id):
    response = client.put(ME_URL, json={"last_project_id": project_id})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"
    assert store == {}


def test_a_refused_last_project_leaves_the_locale_unsaved(client, store, no_container, project_db):
    response = client.put(ME_URL, json={"locale": "fr", "last_project_id": "01UNKNOWNPROJECT0000000000"})

    assert response.status_code == 404
    assert store == {}


def test_a_refused_locale_leaves_the_last_project_unsaved(client, store, no_container, owned):
    response = client.put(ME_URL, json={"locale": "de", "last_project_id": owned})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_locale"
    assert store == {}


def test_me_forgets_a_last_project_that_was_deleted(client, store, no_container, owned):
    client.put(ME_URL, json={"last_project_id": owned})
    projects.delete_project(owned)

    assert client.get(ME_URL).json()["data"]["last_project_id"] is None


def test_me_reports_no_last_project_stored_for_another_user(client, store, no_container, project_db):
    store[("last_project_id", "user-1")] = projects.create_project("user-2", _doc())["id"]

    assert client.get(ME_URL).json()["data"]["last_project_id"] is None


def test_the_last_project_of_a_user_is_not_seen_by_another_one(app, client, make_user, store, no_container, owned):
    client.put(ME_URL, json={"last_project_id": owned})
    _as(app, make_user(user_id="user-2"))

    assert client.get(ME_URL).json()["data"]["last_project_id"] is None


VEO = {
    "id": "cm-veo",
    "name": "Veo 3",
    "provider_model_id": "google/veo-3",
    "tasks": ["img2video", "txt2video"],
    "typical_seconds": 90,
    "max_seconds": 600,
}

H3_VIDEO_DIRECTOR = {
    "family": "minimax_h3",
    "preset_modes": ["video", "refs"],
    "modes": {"t2v": {}, "i2v": {}, "flf": {}, "director": {"fps_locked": True}},
    "limits": {"default_duration": 5, "default_fps": 24, "max_duration": 15},
}

CLOUD_DIRECTOR = {
    **OPENROUTER_DIRECTOR,
    "modes": {"t2v": {}, "director": {"fps_locked": True}},
    "limits": {"default_duration": 5, "default_fps": 24, "max_duration": 10},
    "preset_mode_overrides": {"img2video": {"modes": {"t2v": None, "i2v": {}, "flf": {}}}},
}


def _option(value, label=None):
    return {"value": value, "label": label or value}


def _h3(modes=("video", "refs", "upscale")):
    return _description(
        presets.MINIMAX_H3, "MiniMax-H3", vars={"fps": 24, "video_director": H3_VIDEO_DIRECTOR}, modes={mode: _mode() for mode in modes}
    )


def test_me_lists_the_video_models_of_each_cloud_engine_only(client, store, no_container, catalog):
    catalog.backends = [
        _backend("b-local", "This machine"),
        _backend("b-cloud", "OpenRouter", engine=CLOUD_ENGINE, driver="cloud.openrouter"),
    ]
    catalog.models = {"b-cloud": [VEO], "b-local": [VEO]}

    local, cloud = client.get(ME_URL).json()["data"]["engines"]

    assert "models" not in local
    assert cloud["models"] == [VEO]


def test_me_lists_no_cloud_model_and_logs_when_the_catalog_cannot_be_read(client, store, no_container, catalog, caplog):
    catalog.backends = [_backend("b-cloud", "OpenRouter", engine=CLOUD_ENGINE, driver="cloud.openrouter")]
    catalog.broken.add("models")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        (engine,) = client.get(ME_URL).json()["data"]["engines"]

    assert engine["models"] == []
    assert "Could not list the video models of cloud backend b-cloud" in caplog.text


def test_me_gives_the_sizes_of_the_main_mode_resolution_field(client, store, no_container, catalog):
    catalog.presets = [_wan()]
    catalog.fields[(presets.WAN, "video")] = {
        "resolution": {"type": "resolution", "options": [_option("832x480", "SD Landscape"), _option("1280x720"), _option("auto")]},
        "fps": {"type": "slider", "options": []},
    }

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert preset["resolutions"] == [{"value": "832x480", "label": "SD Landscape"}, {"value": "1280x720", "label": "1280x720"}]
    assert preset["fps_locked"] is False


def test_me_lists_no_size_and_logs_when_the_fields_cannot_be_read(client, store, no_container, catalog, caplog):
    catalog.presets = [_wan()]
    catalog.broken.add("fields")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert preset["resolutions"] == [] and preset["fps"] == 16
    assert f"Could not read the fields of preset {presets.WAN} mode video" in caplog.text


def test_me_gives_h3_its_three_profiles_and_its_locked_frame_rate(client, store, no_container, catalog):
    catalog.presets = [_h3()]
    catalog.fields[(presets.MINIMAX_H3, "video")] = {"resolution": {"type": "resolution", "options": [_option("1344x768")]}}

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert preset["profiles"] == ["FL2VA", "Ref2VA", "Hybrid AV"]
    assert (preset["fps"], preset["fps_locked"]) == (24, True)
    assert preset["resolutions"] == [{"value": "1344x768", "label": "1344x768"}]
    assert preset["limits"] == {"default_duration": 5, "default_fps": 24, "max_duration": 15}


def _spec(type, **details):
    return {"type": type, "required": False, "default": None, "options": [], "recommendations": [], "label": None, "group": [], "audience": "simple", "hidden": False, "gate": None, "limits": {}, "reactions": [], "bound": False, **details}


def test_me_lists_the_options_a_project_may_set_in_each_mode_the_director_runs(client, store, no_container, catalog):
    catalog.presets = [_h3()]
    speed = [{"label": "Quality (24 steps)", "value": "quality"}, {"label": "Turbo", "value": "turbo"}]
    reaction = {"when": {"field": "speed_profile", "equals": "turbo"}, "then": {"set_value": 4}}
    catalog.fields[(presets.MINIMAX_H3, "video")] = {
        "speed_profile": _spec("select", label="Speed", default="quality", options=speed),
        "seed": _spec("seed", default=-1),
        "quantity": _spec("stepper", default=1),
        "resolution": _spec("resolution", options=[_option("1344x768")]),
        "steps": _spec("slider", label="Steps", default=24, group=["Advanced", "Sampling"], audience="advanced", limits={"min": 2, "max": 100, "step": 1}, reactions=[reaction]),
        "model": _spec("model", required=True, recommendations=[{"sha256": "abc", "filename": "dit.safetensors"}, {"sha256": "def", "filename": None}]),
        "hidden_tab_model": _spec("model", hidden=True),
        "media": _spec("image"),
    }
    catalog.fields[(presets.MINIMAX_H3, "refs")] = {"steps": _spec("slider", default=20), "references": _spec("media")}
    catalog.fields[(presets.MINIMAX_H3, "upscale")] = {"steps": _spec("slider", default=10)}

    modes = client.get(ME_URL).json()["data"]["presets"][0]["modes"]

    assert [option["name"] for option in modes["video"]["options"]] == ["speed_profile", "seed", "steps", "model"]
    assert modes["video"]["options"][0] == {
        "name": "speed_profile",
        "type": "select",
        "label": "Speed",
        "group": [],
        "audience": "simple",
        "gate": None,
        "default": "quality",
        "required": False,
        "limits": {},
        "reactions": [],
        "options": speed,
    }
    assert modes["video"]["options"][2]["reactions"] == [reaction]
    assert (modes["video"]["options"][2]["group"], modes["video"]["options"][2]["limits"]) == (["Advanced", "Sampling"], {"min": 2, "max": 100, "step": 1})
    assert modes["video"]["options"][3]["recommended"] == ["dit.safetensors"]
    assert [option["name"] for option in modes["refs"]["options"]] == ["steps"]
    assert "options" not in modes["upscale"]


def test_me_leaves_the_model_of_a_cloud_preset_to_the_production_bar(client, store, no_container, catalog):
    catalog.presets = [_openrouter_video()]
    for mode in ("txt2video", "img2video"):
        catalog.fields[(presets.OPENROUTER_VIDEO, mode)] = {
            "seed": _spec("seed", default=-1),
            "model": _spec("model", required=True),
            "aspect_ratio": _spec("select"),
            "generate_audio": _spec("checkbox", bound=True),
        }

    modes = client.get(ME_URL).json()["data"]["presets"][0]["modes"]

    assert [option["name"] for option in modes["txt2video"]["options"]] == ["seed"]
    assert [option["name"] for option in modes["img2video"]["options"]] == ["seed"]


def test_me_offers_ref2va_only_with_the_h3_refs_mode(client, store, no_container, catalog):
    catalog.presets = [_h3(modes=("video",))]

    assert client.get(ME_URL).json()["data"]["presets"][0]["profiles"] == ["FL2VA", "Hybrid AV"]


def test_me_gives_a_cloud_preset_the_modes_of_all_its_preset_modes(client, store, no_container, catalog):
    catalog.presets = [
        _description(
            presets.OPENROUTER_VIDEO,
            "OpenRouter Video",
            engine=CLOUD_ENGINE,
            vars={"video_director": CLOUD_DIRECTOR},
            modes={"txt2video": _mode(), "img2video": _mode()},
        )
    ]

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert preset["director_modes"] == ["t2v", "director", "i2v", "flf"]
    assert (preset["fps"], preset["fps_locked"], preset["profiles"]) == (24, True, ["FL2VA"])


def test_me_turns_the_upscaler_feature_on_with_seedvr2(client, store, no_container, catalog):
    catalog.presets = [_wan()]
    assert client.get(ME_URL).json()["data"]["features"] == {"upscaler": False, "guided": False}

    catalog.presets = [_wan(), _seedvr2()]
    data = client.get(ME_URL).json()["data"]

    assert data["features"] == {"upscaler": True, "guided": False}
    assert data["upscale_targets"] == ["hd720", "fhd1080", "qhd1440", "uhd2160"]


def test_me_turns_the_guided_feature_on_with_ltx_2_5_and_its_layout_to_render_ic_lora(client, store, no_container, catalog, monkeypatch):
    ltx = _description(
        presets.LTX_2_5,
        "LTX-2.5",
        vars={"video_director": {"preset_modes": ["video"], "modes": {"t2v": {}, "director": {"ic_lora": True}}}},
        modes={"video": _mode()},
    )
    catalog.presets = [_wan(), ltx]
    monkeypatch.setattr(core_bridge, "installed_model_for_file", lambda filename: None)
    assert client.get(ME_URL).json()["data"]["features"]["guided"] is False

    monkeypatch.setattr(core_bridge, "installed_model_for_file", lambda filename: "lora-1" if filename == director.GUIDE_LORA else None)
    assert client.get(ME_URL).json()["data"]["features"] == {"upscaler": False, "guided": True}

    catalog.presets = [_wan()]
    assert client.get(ME_URL).json()["data"]["features"]["guided"] is False


def _cloud_preset(preset_id=presets.OPENROUTER_VIDEO, name="OpenRouter Video"):
    return _description(
        preset_id, name, engine=CLOUD_ENGINE, vars={"video_director": CLOUD_DIRECTOR}, modes={"txt2video": _mode(), "img2video": _mode()}
    )


def test_me_ties_each_cloud_preset_to_the_first_cloud_backend_with_its_driver(client, store, no_container, catalog):
    catalog.backends = [
        _backend("b-local", "This machine", driver="cloud.openrouter"),
        _backend("b-google", "Gemini", engine=CLOUD_ENGINE, driver="cloud.google"),
        _backend("b-router", "OpenRouter", engine=CLOUD_ENGINE, driver="cloud.openrouter"),
        _backend("b-router-2", "OpenRouter spare", engine=CLOUD_ENGINE, driver="cloud.openrouter"),
    ]
    catalog.presets = [_wan(), _cloud_preset(), _cloud_preset(presets.GEMINI_VIDEO, "Gemini Video")]
    catalog.drivers = {presets.OPENROUTER_VIDEO: "cloud.openrouter", presets.GEMINI_VIDEO: "cloud.google"}

    listed = client.get(ME_URL).json()["data"]["presets"]

    assert [(preset["id"], preset["driver"], preset["backend_id"]) for preset in listed] == [
        (presets.WAN, None, None),
        (presets.OPENROUTER_VIDEO, "cloud.openrouter", "b-router"),
        (presets.GEMINI_VIDEO, "cloud.google", "b-google"),
    ]


def test_me_gives_no_backend_to_a_cloud_preset_no_enabled_backend_runs(client, store, no_container, catalog):
    catalog.backends = [_backend("b-google", "Gemini", engine=CLOUD_ENGINE, driver="cloud.google")]
    catalog.presets = [_cloud_preset()]
    catalog.drivers = {presets.OPENROUTER_VIDEO: "cloud.openrouter"}

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert (preset["driver"], preset["backend_id"]) == ("cloud.openrouter", None)


def test_me_gives_a_native_preset_a_driver_but_never_a_backend(client, store, no_container, catalog):
    catalog.backends = [_backend("b-local", "This machine")]
    catalog.presets = [_wan()]
    catalog.drivers = {presets.WAN: "native.local"}

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert (preset["driver"], preset["backend_id"]) == ("native.local", None)


def test_me_logs_a_driver_or_backends_it_cannot_read_and_ties_nothing(client, store, no_container, catalog, caplog):
    catalog.presets = [_cloud_preset()]
    catalog.drivers = {presets.OPENROUTER_VIDEO: "cloud.openrouter"}
    catalog.broken.add("backends")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        (preset,) = client.get(ME_URL).json()["data"]["presets"]
    assert (preset["driver"], preset["backend_id"]) == ("cloud.openrouter", None)
    assert "no cloud preset is tied to one" in caplog.text

    catalog.broken = {"drivers"}
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        (preset,) = client.get(ME_URL).json()["data"]["presets"]
    assert (preset["driver"], preset["backend_id"]) == (None, None)
    assert f"Could not read the driver of preset {presets.OPENROUTER_VIDEO}" in caplog.text


@pytest.mark.parametrize("preset_id", [presets.MINIMAX_H3_FAST, presets.MINIMAX_H3_VDN])
def test_me_derives_the_profiles_and_modes_of_an_h3_variant_from_its_own_modes(client, store, no_container, catalog, preset_id):
    catalog.presets = [
        _description(preset_id, "Variant", vars={"fps": 24, "video_director": {**H3_VIDEO_DIRECTOR, "preset_modes": ["video"]}}, modes={"video": _mode()})
    ]

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert preset["profiles"] == ["FL2VA", "Hybrid AV"]
    assert list(preset["modes"]) == ["video"]
    assert preset["upscaler"] is False


SIZES_12GB = ("1344x768", "768x1344", "960x544", "544x960", "832x480", "480x832")


@pytest.mark.parametrize(
    "preset_id, name, director",
    [
        (presets.MINIMAX_H3_12GB, "MiniMax-H3 (12 GB)", H3_VIDEO_DIRECTOR),
        (presets.MINIMAX_H3_FAST_12GB, "MiniMax-H3-Fast (12 GB)", {**H3_VIDEO_DIRECTOR, "preset_modes": ["video"]}),
    ],
)
def test_me_lists_a_12_gb_preset_with_its_memory_profile(client, store, no_container, catalog, preset_id, name, director):
    catalog.presets = [
        _description(
            preset_id,
            name,
            vars={"fps": 24, "default_frames": 124, "video_director": director, "video_producer": {"profile": "12 GB"}},
            modes={"video": _mode()},
            requires={"min_vram_gb": 12, "recommended_vram_gb": 12},
        )
    ]
    catalog.fields[(preset_id, "video")] = {
        "resolution": {"type": "resolution", "default": "832x480", "options": [_option(value) for value in SIZES_12GB]}
    }

    (preset,) = client.get(ME_URL).json()["data"]["presets"]

    assert (preset["id"], preset["name"], preset["profile"]) == (preset_id, name, "12 GB")
    assert preset["requires"] == {"min_vram_gb": 12, "recommended_vram_gb": 12}
    assert preset["profiles"] == ["FL2VA", "Hybrid AV"]
    assert (list(preset["modes"]), preset["fps"], preset["fps_locked"], preset["upscaler"]) == (["video"], 24, True, False)
    assert [option["value"] for option in preset["resolutions"]] == list(SIZES_12GB)


@pytest.mark.parametrize(
    "variables, profile",
    [
        ({}, None),
        ({"video_producer": None}, None),
        ({"video_producer": "12 GB"}, None),
        ({"video_producer": {"profile": 12}}, None),
        ({"video_producer": {"profile": "   "}}, None),
        ({"video_producer": {"profile": " 16 GB "}}, "16 GB"),
    ],
)
def test_me_reads_the_memory_profile_only_from_a_text_video_producer_profile(client, store, no_container, catalog, variables, profile):
    catalog.presets = [_description(presets.MINIMAX_H3, "MiniMax-H3", vars={"fps": 24, "video_director": H3_VIDEO_DIRECTOR, **variables}, modes={"video": _mode()})]

    assert client.get(ME_URL).json()["data"]["presets"][0]["profile"] == profile
