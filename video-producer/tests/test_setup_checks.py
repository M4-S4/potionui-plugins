import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from backend import core_bridge, presets, setup_checks
from backend.core_bridge import PresetState
from backend.setup_checks import (
    FfmpegReady,
    MiniMaxH3Ready,
    UpscalerReady,
    VideoEngineReady,
    VideoPresetsReady,
    admin_href,
)
from src.plugin_api import SetupCheck, SetupCheckContext, SetupCheckResult
from src.plugin_api.cloud import CLOUD_ENGINE

CONTEXT = SetupCheckContext(plugin_id="video-producer", settings={})

BACKENDS_HREF = "/admin?tab=backends"
PRESETS_HREF = "/admin?tab=presets"
README_HREF = "/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME"

ALL_CHECKS = (VideoEngineReady, VideoPresetsReady, UpscalerReady, FfmpegReady, MiniMaxH3Ready)


def _backend(backend_id, name, engine="native", driver="native.local", device="unestablished"):
    return {
        "id": backend_id,
        "name": name,
        "engine": engine,
        "driver": driver,
        "enabled": True,
        "is_default": False,
        "quick_actions": [],
        "execution_device": device,
        "max_concurrent_runs": None,
        "vram_total_gb": None,
        "vram_free_gb": None,
    }


def _cloud(backend_id, name):
    return _backend(backend_id, name, engine=CLOUD_ENGINE, driver="cloud.provider")


def _state(preset_id, name=None, loaded=True, installed=False, assigned=False):
    return PresetState(id=preset_id, name=name or preset_id, loaded=loaded, installed=installed, assigned=assigned)


def _raise(message):
    def raiser(*args, **kwargs):
        raise RuntimeError(message)

    return raiser


class Engines:
    def __init__(self, monkeypatch):
        self.backends = []
        self.video_models = {}
        self.asked = []
        monkeypatch.setattr(core_bridge, "enabled_backends", lambda: list(self.backends))
        monkeypatch.setattr(core_bridge, "enabled_cloud_video_models", self._count)

    def _count(self, backend_id):
        self.asked.append(backend_id)
        return self.video_models.get(backend_id, 0)


class Presets:
    def __init__(self, monkeypatch):
        self.states = {}
        self.asked = []
        monkeypatch.setattr(core_bridge, "preset_state", self._state)

    def _state(self, preset_id):
        self.asked.append(preset_id)
        return self.states.get(preset_id) or _state(preset_id, loaded=False)

    def set(self, preset_id, **fields):
        self.states[preset_id] = _state(preset_id, **fields)


class Models:
    def __init__(self, monkeypatch):
        self.hashes = {}
        self.present = set()
        self.hash_requests = []
        self.file_requests = []
        self.names = {}
        self.installed = set()
        self.name_requests = []
        monkeypatch.setattr(core_bridge, "preset_model_hashes", self._hashes)
        monkeypatch.setattr(core_bridge, "model_file_present", self._present)
        monkeypatch.setattr(core_bridge, "describe_preset", self._describe)
        monkeypatch.setattr(core_bridge, "preset_form_fields", self._fields)
        monkeypatch.setattr(core_bridge, "installed_model_for_file", self._installed)

    def _hashes(self, preset_id, field_names, modes=None):
        self.hash_requests.append((preset_id, list(field_names)))
        if modes is not None:
            return {name: {sha for mode in modes for sha in self.hashes.get((preset_id, mode, name), ())} for name in field_names}
        return {name: set(self.hashes.get((preset_id, name), ())) for name in field_names}

    def _present(self, sha256):
        self.file_requests.append(sha256)
        return sha256 in self.present

    def _describe(self, preset_id):
        modes = [mode for owner, mode, _ in self.names if owner == preset_id]
        return SimpleNamespace(modes=dict.fromkeys(modes)) if modes else None

    def _fields(self, preset_id, mode):
        return {
            role: {"type": "model", "recommendations": [{"sha256": None, "filename": name} for name in names]}
            for (owner, own_mode, role), names in self.names.items()
            if (owner, own_mode) == (preset_id, mode)
        }

    def _installed(self, filename):
        self.name_requests.append(filename)
        return f"id-{filename}" if filename in self.installed else None

    def name(self, preset_id, mode, **by_role):
        for role, names in by_role.items():
            self.names[(preset_id, mode, role)] = list(names)

    def recommend(self, preset_id, **by_role):
        for role, hashes in by_role.items():
            self.hashes[(preset_id, role)] = set(hashes)

    def recommend_in(self, preset_id, mode, **by_role):
        for role, hashes in by_role.items():
            self.hashes[(preset_id, mode, role)] = set(hashes)


@pytest.fixture
def engines(monkeypatch):
    return Engines(monkeypatch)


@pytest.fixture
def preset_states(monkeypatch):
    return Presets(monkeypatch)


@pytest.fixture
def models(monkeypatch):
    return Models(monkeypatch)


@pytest.mark.parametrize("check", ALL_CHECKS)
def test_every_check_builds_without_arguments_and_is_a_setup_check(check):
    assert isinstance(check(), SetupCheck)


def test_the_module_helpers_build_admin_links():
    assert admin_href(tab="presets") == "/admin?tab=presets"
    assert admin_href(tab="presets", id="01ABC") == "/admin?tab=presets&id=01ABC"
    assert admin_href(tab="backends", backend="a b", view="catalog") == "/admin?tab=backends&backend=a+b&view=catalog"
    assert (setup_checks.BACKENDS_HREF, setup_checks.PRESETS_HREF, setup_checks.README_HREF) == (
        BACKENDS_HREF,
        PRESETS_HREF,
        README_HREF,
    )


def test_a_native_local_backend_is_an_engine(engines):
    engines.backends = [_backend("b-1", "This machine")]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=True, description="Takes can run on This machine."
    )
    assert engines.asked == []


@pytest.mark.parametrize("device", ["this_host_gpu", "remote", "unestablished"])
def test_a_native_backend_on_a_gpu_a_worker_or_not_yet_running_is_an_engine(engines, device):
    engines.backends = [_backend("b-1", "This machine", device=device)]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(done=True, description="Takes can run on This machine.")


def test_a_native_local_backend_without_a_gpu_is_not_an_engine(engines):
    engines.backends = [_backend("b-1", "This machine", device="no_gpu")]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Takes cannot run on This machine: no GPU is configured. "
            "Give a native backend a GPU, enable a native remote worker, "
            "or add a cloud backend and turn on a video model in its catalog."
        ),
        action_label="Open backends",
        action_href=BACKENDS_HREF,
    )
    assert engines.asked == []


def test_every_native_backend_without_a_gpu_is_named_and_none_is_an_engine(engines):
    engines.backends = [_backend("b-1", "This machine", device="no_gpu"), _backend("b-2", "Spare", device="no_gpu")]

    result = VideoEngineReady().evaluate(CONTEXT)

    assert result.done is False
    assert result.description.startswith("Takes cannot run on This machine, Spare: no GPU is configured. ")


def test_a_native_backend_without_a_gpu_is_left_out_when_another_engine_exists(engines):
    engines.backends = [_backend("b-1", "This machine", device="no_gpu"), _backend("b-2", "Render box", driver="native.remote", device="remote")]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(done=True, description="Takes can run on Render box.")


def test_a_native_backend_without_a_gpu_does_not_hide_a_cloud_video_model(engines):
    engines.backends = [_backend("b-1", "This machine", device="no_gpu"), _cloud("c-1", "OpenRouter")]
    engines.video_models = {"c-1": 2}

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(done=True, description="Takes can run on OpenRouter (2 video models).")


def test_a_native_backend_without_a_gpu_and_a_cloud_backend_without_video_model_ask_for_the_catalog_and_say_why(engines):
    engines.backends = [_backend("b-1", "This machine", device="no_gpu"), _cloud("c-1", "OpenRouter")]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Takes cannot run on This machine: no GPU is configured. "
            "No video model is turned on in OpenRouter. Turn one on in the backend's catalog, or enable a native backend."
        ),
        action_label="Open catalog",
        action_href="/admin?tab=backends&backend=c-1&view=catalog",
    )


def test_a_backend_that_reports_no_execution_device_still_counts_as_an_engine(engines):
    backend = _backend("b-1", "This machine")
    del backend["execution_device"]
    engines.backends = [backend]

    assert VideoEngineReady().evaluate(CONTEXT).done is True


def test_a_native_remote_worker_is_an_engine(engines):
    engines.backends = [_backend("b-1", "Render box", driver="native.remote")]

    result = VideoEngineReady().evaluate(CONTEXT)

    assert (result.done, result.description) == (True, "Takes can run on Render box.")
    assert result.action_label is None and result.action_href is None


def test_a_cloud_backend_with_one_video_model_is_an_engine(engines):
    engines.backends = [_cloud("c-1", "OpenRouter")]
    engines.video_models = {"c-1": 1}

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=True, description="Takes can run on OpenRouter (1 video model)."
    )
    assert engines.asked == ["c-1"]


def test_a_cloud_backend_with_several_video_models_says_how_many(engines):
    engines.backends = [_cloud("c-1", "Gemini")]
    engines.video_models = {"c-1": 3}

    assert VideoEngineReady().evaluate(CONTEXT).description == "Takes can run on Gemini (3 video models)."


def test_native_and_cloud_engines_are_listed_together_native_first(engines):
    engines.backends = [_cloud("c-1", "OpenRouter"), _backend("b-1", "This machine"), _cloud("c-2", "Gemini")]
    engines.video_models = {"c-1": 2, "c-2": 0}

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=True, description="Takes can run on This machine, OpenRouter (2 video models)."
    )


def test_a_cloud_backend_without_video_model_is_left_out_when_a_native_engine_exists(engines):
    engines.backends = [_backend("b-1", "This machine"), _cloud("c-1", "Gemini")]

    assert VideoEngineReady().evaluate(CONTEXT).description == "Takes can run on This machine."


def test_cloud_backends_without_video_model_ask_to_turn_one_on_in_the_first_catalog(engines):
    engines.backends = [_cloud("c-1", "OpenRouter"), _cloud("c-2", "Gemini")]

    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "No video model is turned on in OpenRouter, Gemini. "
            "Turn one on in the backend's catalog, or enable a native backend."
        ),
        action_label="Open catalog",
        action_href="/admin?tab=backends&backend=c-1&view=catalog",
    )


def test_without_any_backend_the_check_asks_to_enable_one(engines):
    assert VideoEngineReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Enable the native backend of this machine or a native remote worker, "
            "or add a cloud backend and turn on a video model in its catalog."
        ),
        action_label="Open backends",
        action_href=BACKENDS_HREF,
    )


def test_a_backend_that_is_neither_native_nor_cloud_is_not_an_engine(engines):
    engines.backends = [_backend("b-1", "Comfy", engine="comfyui", driver="comfyui.remote")]

    result = VideoEngineReady().evaluate(CONTEXT)

    assert result.done is False
    assert (result.action_label, result.action_href) == ("Open backends", BACKENDS_HREF)


@pytest.mark.parametrize("where", ["backends", "models"])
def test_an_error_reading_the_backends_is_a_step_still_to_do(engines, monkeypatch, caplog, where):
    engines.backends = [_cloud("c-1", "OpenRouter")]
    broken = "enabled_backends" if where == "backends" else "enabled_cloud_video_models"
    monkeypatch.setattr(core_bridge, broken, _raise("registry is down"))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = VideoEngineReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=False,
        description="Could not check the backends; see the server log.",
        action_label="Open backends",
        action_href=BACKENDS_HREF,
    )
    assert "registry is down" in caplog.text


def test_the_presets_are_asked_one_by_one_in_the_declared_order(preset_states):
    VideoPresetsReady().evaluate(CONTEXT)

    assert preset_states.asked == list(presets.VIDEO_DIRECTOR_PRESETS)


def test_installed_and_assigned_presets_are_done_and_named(preset_states):
    preset_states.set(presets.WAN, name="Wan", installed=True, assigned=True)
    preset_states.set(presets.LTX_2, name="LTX 2", installed=True, assigned=True)

    result = VideoPresetsReady().evaluate(CONTEXT)

    assert result.done is True
    assert result.description.startswith("Installed and assigned: Wan, LTX 2. ")
    assert "cannot verify user by user" in result.description
    assert result.action_label is None and result.action_href is None


def test_only_the_assigned_presets_are_named_when_others_are_not_ready(preset_states):
    preset_states.set(presets.WAN, name="Wan", installed=True, assigned=True)
    preset_states.set(presets.LTX_2, name="LTX 2", installed=True)
    preset_states.set(presets.GEMINI_VIDEO, name="Gemini Video")

    assert VideoPresetsReady().evaluate(CONTEXT).description.startswith("Installed and assigned: Wan. ")


def test_installed_presets_assigned_to_no_one_ask_to_assign_the_first(preset_states):
    preset_states.set(presets.LTX_2, name="LTX 2", installed=True)
    preset_states.set(presets.WAN, name="Wan", installed=True)

    assert VideoPresetsReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Installed but assigned to no one: Wan, LTX 2. "
            "Assign one to the users or groups who will use Video Producer."
        ),
        action_label="Assign presets",
        action_href=f"/admin?tab=presets&id={presets.WAN}",
    )


def test_available_presets_that_are_not_installed_ask_to_install_the_first(preset_states):
    preset_states.set(presets.OPENROUTER_VIDEO, name="OpenRouter Video")
    preset_states.set(presets.GEMINI_VIDEO, name="Gemini Video")

    assert VideoPresetsReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Install a Video Director preset (OpenRouter Video, Gemini Video), then assign it. "
            "Cloud video presets come with their provider plugins."
        ),
        action_label="Open presets",
        action_href=f"/admin?tab=presets&id={presets.OPENROUTER_VIDEO}",
    )


def test_a_preset_that_is_not_loaded_does_not_count_even_when_flagged_installed(preset_states):
    preset_states.set(presets.WAN, name="Wan", loaded=False, installed=True, assigned=True)

    assert VideoPresetsReady().evaluate(CONTEXT).done is False


def test_without_any_loaded_preset_the_check_says_none_is_available(preset_states):
    assert VideoPresetsReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description="No Video Director preset is available. Enable a plugin that ships one, such as a cloud provider.",
        action_label="Open presets",
        action_href=PRESETS_HREF,
    )


def test_an_error_reading_the_presets_is_a_step_still_to_do(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge, "preset_state", _raise("catalog is down"))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = VideoPresetsReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=False,
        description="Could not check the presets; see the server log.",
        action_label="Open presets",
        action_href=PRESETS_HREF,
    )
    assert "catalog is down" in caplog.text


def test_the_upscaler_check_looks_at_seedvr2_then_rtx_upscale(preset_states):
    UpscalerReady().evaluate(CONTEXT)

    assert preset_states.asked == [presets.SEEDVR2, presets.RTX_UPSCALE]


@pytest.mark.parametrize(
    "seedvr2, module, description",
    [
        (True, True, "SeedVR2 is installed and assigned. RTX Upscale is ready as well, for fast final takes."),
        (True, False, "SeedVR2 is installed and assigned. RTX Upscale also needs the nvidia-vfx package on the server."),
        (False, True, "Final takes are upscaled with RTX Upscale. SeedVR2, which restores and adds detail, is not installed."),
    ],
)
def test_an_assigned_rtx_upscale_is_named_and_counts_without_seedvr2(preset_states, monkeypatch, seedvr2, module, description):
    monkeypatch.setattr(core_bridge, "module_available", lambda name: module and name == "nvvfx")
    preset_states.set(presets.RTX_UPSCALE, name="RTX Upscale", installed=True, assigned=True)
    if seedvr2:
        preset_states.set(presets.SEEDVR2, name="SeedVR2", installed=True, assigned=True)

    assert UpscalerReady().evaluate(CONTEXT) == SetupCheckResult(done=True, description=description)


def test_an_rtx_upscale_without_nvidia_vfx_does_not_replace_seedvr2(preset_states, monkeypatch):
    monkeypatch.setattr(core_bridge, "module_available", lambda name: False)
    preset_states.set(presets.RTX_UPSCALE, name="RTX Upscale", installed=True, assigned=True)

    result = UpscalerReady().evaluate(CONTEXT)

    assert result.done is False
    assert result.description.endswith("RTX Upscale also needs the nvidia-vfx package on the server.")


def test_an_installed_and_assigned_upscaler_is_done(preset_states):
    preset_states.set(presets.SEEDVR2, name="SeedVR2", installed=True, assigned=True)

    assert UpscalerReady().evaluate(CONTEXT) == SetupCheckResult(done=True, description="SeedVR2 is installed and assigned.")


def test_an_installed_upscaler_is_done_but_asks_to_assign_it(preset_states):
    preset_states.set(presets.SEEDVR2, name="SeedVR2", installed=True)

    result = UpscalerReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=True,
        description="SeedVR2 is installed. Assign it to the users or groups who make final takes.",
    )


def test_an_upscaler_that_is_not_installed_asks_to_install_it(preset_states):
    preset_states.set(presets.SEEDVR2, name="SeedVR2")

    assert UpscalerReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Final takes are upscaled with SeedVR2. Install it, "
            "then assign it to the users or groups who make final takes."
        ),
        action_label="Open SeedVR2",
        action_href=f"/admin?tab=presets&id={presets.SEEDVR2}",
    )


def test_an_upscaler_preset_that_is_not_loaded_is_reported_as_unavailable(preset_states):
    assert UpscalerReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description="The SeedVR2 preset is not available on this instance; final takes need it.",
        action_label="Open presets",
        action_href=PRESETS_HREF,
    )


def test_an_error_reading_the_upscaler_is_a_step_still_to_do(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge, "preset_state", _raise("db is locked"))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = UpscalerReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=False,
        description="Could not check the SeedVR2 preset; see the server log.",
        action_label="Open presets",
        action_href=PRESETS_HREF,
    )
    assert "db is locked" in caplog.text


def test_ffmpeg_and_ffprobe_on_the_path_is_done(monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe")

    result = FfmpegReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(done=True, description="ffmpeg is available.")


@pytest.mark.parametrize("found", [None, ""])
def test_missing_ffmpeg_points_at_the_guide(monkeypatch, found):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: found)
    monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe")

    assert FfmpegReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Video Producer joins takes and exports the cut with ffmpeg, and reads media with ffprobe; ffmpeg is missing. "
            "Install ffmpeg with ffprobe on the server so both are on the PATH, then restart PotionUI."
        ),
        action_label="Read the guide",
        action_href=README_HREF,
    )


def test_ffmpeg_without_ffprobe_is_still_a_step_to_do(monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: None)

    result = FfmpegReady().evaluate(CONTEXT)

    assert result.done is False and "ffprobe is missing" in result.description


def test_an_error_looking_for_ffmpeg_is_a_step_still_to_do(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", _raise("which failed"))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = FfmpegReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=False,
        description="Could not check ffmpeg; see the server log.",
        action_label="Read the guide",
        action_href=README_HREF,
    )
    assert "which failed" in caplog.text


def test_the_h3_check_looks_at_the_five_minimax_presets(preset_states, models):
    MiniMaxH3Ready().evaluate(CONTEXT)

    assert preset_states.asked == list(presets.MINIMAX_H3_PRESETS)
    assert len(presets.MINIMAX_H3_PRESETS) == 5


def test_both_checks_cover_the_12_gb_presets_the_plugin_ships():
    shipped = (presets.MINIMAX_H3_12GB, presets.MINIMAX_H3_FAST_12GB)

    assert presets.MINIMAX_H3_PRESETS[-2:] == shipped
    assert all(preset_id in presets.VIDEO_DIRECTOR_PRESETS for preset_id in shipped)
    assert len(set(presets.VIDEO_DIRECTOR_PRESETS)) == len(presets.VIDEO_DIRECTOR_PRESETS)


def test_installed_and_assigned_12_gb_presets_satisfy_the_presets_check(preset_states):
    preset_states.set(presets.MINIMAX_H3_12GB, name="MiniMax-H3 (12 GB)", installed=True, assigned=True)

    result = VideoPresetsReady().evaluate(CONTEXT)

    assert result.done is True
    assert result.description.startswith("Installed and assigned: MiniMax-H3 (12 GB). ")


def test_without_an_installed_h3_preset_there_is_nothing_to_check(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=False)

    assert MiniMaxH3Ready().evaluate(CONTEXT) == SetupCheckResult(
        done=True, description="No MiniMax-H3 preset is installed; nothing to check."
    )
    assert models.hash_requests == [] and models.file_requests == []


def test_an_installed_h3_preset_with_its_five_files_is_done(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"a" * 64}, text_encoder={"b" * 64}, video_vae={"c" * 64}, audio_vae={"d" * 64})
    models.recommend_in(presets.MINIMAX_H3, "upscale", upscale_model={"e" * 64})
    models.present = {"a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64}

    assert MiniMaxH3Ready().evaluate(CONTEXT) == SetupCheckResult(
        done=True,
        description=(
            "The DiT, text encoder, video VAE and audio VAE files, and the latent upscaler of the Upscale mode, "
            "are on disk for MiniMax-H3."
        ),
    )
    assert models.hash_requests == [
        (presets.MINIMAX_H3, ["model", "text_encoder", "video_vae", "audio_vae"]),
        (presets.MINIMAX_H3, ["upscale_model"]),
    ]


def test_a_missing_latent_upscaler_of_the_upscale_mode_is_reported(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"a" * 64})
    models.recommend_in(presets.MINIMAX_H3, "upscale", upscale_model={"e" * 64})
    models.present = {"a" * 64}

    result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result.done is False
    assert result.description.startswith("MiniMax-H3 is missing its latent upscaler. ")


def test_a_variant_without_an_upscale_mode_is_not_asked_for_the_latent_upscaler(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=False)
    preset_states.set(presets.MINIMAX_H3_FAST, name="MiniMax-H3-Fast", installed=True)
    models.recommend(presets.MINIMAX_H3_FAST, model={"a" * 64}, upscale_model={"e" * 64})
    models.present = {"a" * 64}

    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True


@pytest.mark.parametrize(
    "role, label",
    [
        ("model", "DiT"),
        ("text_encoder", "text encoder"),
        ("video_vae", "video VAE"),
        ("audio_vae", "audio VAE"),
    ],
)
def test_a_missing_file_is_reported_by_the_role_it_plays(preset_states, models, role, label):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    roles = ("model", "text_encoder", "video_vae", "audio_vae")
    models.recommend(presets.MINIMAX_H3, **{name: {f"{name}-hash"} for name in roles})
    models.present = {f"{name}-hash" for name in roles if name != role}

    result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result.done is False
    assert result.description.startswith(f"MiniMax-H3 is missing its {label}. ")
    assert "SHA-256" in result.description
    assert result.action_label == "Open MiniMax-H3"
    assert result.action_href == f"/admin?tab=presets&id={presets.MINIMAX_H3}"


@pytest.mark.parametrize(
    "missing, sentence",
    [
        (("model", "audio_vae"), "its DiT and audio VAE"),
        (("model", "text_encoder", "video_vae"), "its DiT, text encoder and video VAE"),
        (("model", "text_encoder", "video_vae", "audio_vae"), "its DiT, text encoder, video VAE and audio VAE"),
    ],
)
def test_several_missing_files_are_listed_in_one_sentence(preset_states, models, missing, sentence):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    roles = ("model", "text_encoder", "video_vae", "audio_vae")
    models.recommend(presets.MINIMAX_H3, **{name: {f"{name}-hash"} for name in roles})
    models.present = {f"{name}-hash" for name in roles if name not in missing}

    assert MiniMaxH3Ready().evaluate(CONTEXT).description.startswith(f"MiniMax-H3 is missing {sentence}. ")


def test_every_installed_preset_with_a_missing_file_is_named_and_the_first_is_opened(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    preset_states.set(presets.MINIMAX_H3_FAST, name="MiniMax-H3 Fast", installed=True)
    preset_states.set(presets.MINIMAX_H3_VDN, name="MiniMax-H3 VDN", installed=True)
    for preset_id in presets.MINIMAX_H3_PRESETS:
        models.recommend(preset_id, model={f"{preset_id}-dit"}, text_encoder={f"{preset_id}-te"})
    models.present = {f"{presets.MINIMAX_H3_FAST}-dit", f"{presets.MINIMAX_H3_FAST}-te"}

    result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result.done is False
    assert "MiniMax-H3 is missing its DiT and text encoder." in result.description
    assert "MiniMax-H3 VDN is missing its DiT and text encoder." in result.description
    assert "MiniMax-H3 Fast is missing" not in result.description
    assert (result.action_label, result.action_href) == ("Open MiniMax-H3", f"/admin?tab=presets&id={presets.MINIMAX_H3}")


def test_a_preset_that_is_not_installed_is_not_checked_for_files(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=False)
    preset_states.set(presets.MINIMAX_H3_FAST, name="MiniMax-H3 Fast", installed=True)
    models.recommend(presets.MINIMAX_H3_FAST, model={"a" * 64})
    models.present = {"a" * 64}

    result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result.done is True
    assert [preset_id for preset_id, _ in models.hash_requests] == [presets.MINIMAX_H3_FAST, presets.MINIMAX_H3_FAST]
    assert result.description.endswith("are on disk for MiniMax-H3 Fast.")


def test_any_one_recommended_file_of_a_role_is_enough(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"a" * 64, "b" * 64, "c" * 64})
    models.present = {"c" * 64}

    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True


def test_a_role_without_recommended_files_is_not_reported_missing(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)

    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True
    assert models.file_requests == []


def test_the_files_of_a_role_are_looked_up_in_sorted_order_until_one_is_found(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"c" * 64, "a" * 64, "b" * 64})
    models.present = {"b" * 64}

    MiniMaxH3Ready().evaluate(CONTEXT)

    assert models.file_requests == ["a" * 64, "b" * 64]


COMFY_DIT = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
WAN2GP_DIT = "MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors"


def test_the_wan2gp_dit_found_by_its_file_name_passes_when_the_catalog_has_no_sha256_for_it(preset_states, models):
    preset_states.set(presets.MINIMAX_H3_12GB, name="MiniMax-H3 (12 GB)", installed=True)
    models.recommend(presets.MINIMAX_H3_12GB, model={"a" * 64, "b" * 64}, text_encoder={"c" * 64}, video_vae={"d" * 64}, audio_vae={"e" * 64})
    models.name(presets.MINIMAX_H3_12GB, "video", model=[COMFY_DIT, WAN2GP_DIT], text_encoder=["te.safetensors"])
    models.present = {"c" * 64, "d" * 64, "e" * 64}
    models.installed = {WAN2GP_DIT}

    result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result.done is True
    assert result.description.endswith("are on disk for MiniMax-H3 (12 GB).")
    assert models.name_requests == [COMFY_DIT, WAN2GP_DIT]


def test_a_role_recommended_by_file_name_only_is_missing_until_one_of_its_files_is_installed(preset_states, models):
    preset_states.set(presets.MINIMAX_H3_FAST_12GB, name="MiniMax-H3-Fast (12 GB)", installed=True)
    models.name(presets.MINIMAX_H3_FAST_12GB, "video", video_vae=["vae_int8.safetensors"])

    assert MiniMaxH3Ready().evaluate(CONTEXT).description.startswith("MiniMax-H3-Fast (12 GB) is missing its video VAE. ")

    models.installed = {"vae_int8.safetensors"}
    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True


def test_the_latent_upscaler_is_looked_up_by_name_in_the_upscale_mode_only(preset_states, models):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.name(presets.MINIMAX_H3, "video", upscale_model=["video_upscaler.safetensors"])

    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True

    models.name(presets.MINIMAX_H3, "upscale", upscale_model=["upscaler.safetensors"])
    assert MiniMaxH3Ready().evaluate(CONTEXT).description.startswith("MiniMax-H3 is missing its latent upscaler. ")
    assert "video_upscaler.safetensors" not in models.name_requests


def test_the_file_names_are_not_read_when_every_role_is_found_by_its_sha256(preset_states, models, monkeypatch):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    roles = ("model", "text_encoder", "video_vae", "audio_vae")
    models.recommend(presets.MINIMAX_H3, **{name: {f"{name}-hash"} for name in roles})
    models.recommend_in(presets.MINIMAX_H3, "upscale", upscale_model={"upscale-hash"})
    models.present = {f"{name}-hash" for name in (*roles, "upscale")}
    monkeypatch.setattr(core_bridge, "describe_preset", _raise("not needed"))

    assert MiniMaxH3Ready().evaluate(CONTEXT).done is True
    assert models.name_requests == []


@pytest.mark.parametrize("where", ["state", "hashes", "file", "describe", "fields", "name"])
def test_an_error_reading_the_h3_files_is_a_step_still_to_do(preset_states, models, monkeypatch, caplog, where):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"a" * 64})
    models.name(presets.MINIMAX_H3, "video", model=[COMFY_DIT])
    target = {
        "state": "preset_state",
        "hashes": "preset_model_hashes",
        "file": "model_file_present",
        "describe": "describe_preset",
        "fields": "preset_form_fields",
        "name": "installed_model_for_file",
    }[where]
    monkeypatch.setattr(core_bridge, target, _raise("models are down"))

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = MiniMaxH3Ready().evaluate(CONTEXT)

    assert result == SetupCheckResult(
        done=False,
        description="Could not check the MiniMax-H3 model files; see the server log.",
        action_label="Open presets",
        action_href=PRESETS_HREF,
    )
    assert "models are down" in caplog.text


@pytest.mark.parametrize("check", ALL_CHECKS)
def test_a_check_ignores_the_plugin_settings(check, engines, preset_states, models, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)
    other = SetupCheckContext(plugin_id="video-producer", settings={"draft_resolution": "1280x720"})

    assert check().evaluate(other) == check().evaluate(CONTEXT)


MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yml"

SETUP = (
    (VideoEngineReady, "Enable a native backend or a cloud video model"),
    (
        VideoPresetsReady,
        "Install and assign at least one Video Director preset (Wan, MiniMax-H3, LTX or a cloud video preset)",
    ),
    (UpscalerReady, "Install SeedVR2 for final takes"),
    (FfmpegReady, "Install ffmpeg for video delivery"),
    (
        MiniMaxH3Ready,
        "If a MiniMax-H3 preset is installed, install its five model files (DiT, text encoder, video VAE, "
        "audio VAE, and the latent upscaler of its Upscale mode)",
    ),
)

H3_ROLES = ("model", "text_encoder", "video_vae", "audio_vae")


def _manifest_setup():
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["setup"]


def test_the_manifest_declares_exactly_the_five_checks_these_tests_cover():
    assert [(step["kind"], step["check"], step["label"]) for step in _manifest_setup()] == [
        ("check", f"backend.setup_checks:{check.__name__}", label) for check, label in SETUP
    ]
    assert tuple(check for check, _ in SETUP) == ALL_CHECKS


def _h3_files(models, present):
    models.recommend(presets.MINIMAX_H3, **{role: {f"{role}-sha"} for role in H3_ROLES})
    models.recommend_in(presets.MINIMAX_H3, "upscale", upscale_model={"upscale_model-sha"})
    models.present = {f"{role}-sha" for role in (*H3_ROLES, "upscale_model") if role in present}


def _arrange(state, check, engines, preset_states, models, monkeypatch):
    if state == "unchecked":
        broken = {
            VideoEngineReady: "enabled_backends",
            VideoPresetsReady: "preset_state",
            UpscalerReady: "preset_state",
            FfmpegReady: "find_ffmpeg",
            MiniMaxH3Ready: "preset_model_hashes",
        }[check]
        preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
        monkeypatch.setattr(core_bridge, broken, _raise("the host is down"))
        return
    done = state == "done"
    if check is VideoEngineReady:
        engines.backends = [_backend("b-1", "This machine")] if done else []
    elif check is VideoPresetsReady:
        preset_states.set(presets.WAN, name="Wan 2.1 / 2.2", installed=True, assigned=done)
    elif check is UpscalerReady:
        preset_states.set(presets.SEEDVR2, name="SeedVR2", installed=done, assigned=done)
    elif check is FfmpegReady:
        monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg" if state != "todo" else None)
        monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe" if done else None)
    else:
        preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
        _h3_files(models, H3_ROLES + (("upscale_model",) if done else ()))


SETUP_STATES = [
    (VideoEngineReady, "done", "Takes can run on This machine.", None, None),
    (VideoEngineReady, "todo", "Enable the native backend of this machine", "Open backends", BACKENDS_HREF),
    (VideoEngineReady, "unchecked", "Could not check the backends; see the server log.", "Open backends", BACKENDS_HREF),
    (VideoPresetsReady, "done", "Installed and assigned: Wan 2.1 / 2.2.", None, None),
    (
        VideoPresetsReady,
        "todo",
        "Installed but assigned to no one: Wan 2.1 / 2.2.",
        "Assign presets",
        f"{PRESETS_HREF}&id={presets.WAN}",
    ),
    (VideoPresetsReady, "unchecked", "Could not check the presets; see the server log.", "Open presets", PRESETS_HREF),
    (UpscalerReady, "done", "SeedVR2 is installed and assigned.", None, None),
    (
        UpscalerReady,
        "todo",
        "Final takes are upscaled with SeedVR2.",
        "Open SeedVR2",
        f"{PRESETS_HREF}&id={presets.SEEDVR2}",
    ),
    (UpscalerReady, "unchecked", "Could not check the SeedVR2 preset; see the server log.", "Open presets", PRESETS_HREF),
    (FfmpegReady, "done", "ffmpeg is available.", None, None),
    (FfmpegReady, "todo", "ffmpeg is missing.", "Read the guide", README_HREF),
    (FfmpegReady, "todo-ffprobe", "ffprobe is missing.", "Read the guide", README_HREF),
    (FfmpegReady, "unchecked", "Could not check ffmpeg; see the server log.", "Read the guide", README_HREF),
    (MiniMaxH3Ready, "done", "are on disk for MiniMax-H3.", None, None),
    (
        MiniMaxH3Ready,
        "todo",
        "MiniMax-H3 is missing its latent upscaler.",
        "Open MiniMax-H3",
        f"{PRESETS_HREF}&id={presets.MINIMAX_H3}",
    ),
    (
        MiniMaxH3Ready,
        "unchecked",
        "Could not check the MiniMax-H3 model files; see the server log.",
        "Open presets",
        PRESETS_HREF,
    ),
]


@pytest.mark.parametrize(
    "check, state, text, action_label, action_href",
    SETUP_STATES,
    ids=[f"{check.__name__}-{state}" for check, state, *_ in SETUP_STATES],
)
def test_each_manifest_check_is_done_to_do_or_not_checkable_with_its_text_and_link(
    check, state, text, action_label, action_href, engines, preset_states, models, monkeypatch, caplog
):
    _arrange(state, check, engines, preset_states, models, monkeypatch)

    with caplog.at_level(logging.WARNING, logger="plugins.video-producer"):
        result = check().evaluate(CONTEXT)

    assert result.done is (state == "done")
    assert text in result.description
    assert (result.action_label, result.action_href) == (action_label, action_href)
    assert ("the host is down" in caplog.text) is (state == "unchecked")


def test_every_check_of_the_manifest_has_its_three_states_covered():
    covered = {(check, state.split("-")[0]) for check, state, *_ in SETUP_STATES}

    assert covered == {(check, state) for check in ALL_CHECKS for state in ("done", "todo", "unchecked")}
