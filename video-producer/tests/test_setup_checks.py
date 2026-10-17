import logging

import pytest

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


def _backend(backend_id, name, engine="native", driver="native.local"):
    return {
        "id": backend_id,
        "name": name,
        "engine": engine,
        "driver": driver,
        "enabled": True,
        "is_default": False,
        "quick_actions": [],
        "execution_device": "unestablished",
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
        monkeypatch.setattr(core_bridge, "preset_model_hashes", self._hashes)
        monkeypatch.setattr(core_bridge, "model_file_present", self._present)

    def _hashes(self, preset_id, field_names, modes=None):
        self.hash_requests.append((preset_id, list(field_names)))
        if modes is not None:
            return {name: {sha for mode in modes for sha in self.hashes.get((preset_id, mode, name), ())} for name in field_names}
        return {name: set(self.hashes.get((preset_id, name), ())) for name in field_names}

    def _present(self, sha256):
        self.file_requests.append(sha256)
        return sha256 in self.present

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


def test_the_upscaler_check_looks_at_seedvr2_only(preset_states):
    UpscalerReady().evaluate(CONTEXT)

    assert preset_states.asked == [presets.SEEDVR2]


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


def test_ffmpeg_on_the_path_is_done(monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    result = FfmpegReady().evaluate(CONTEXT)

    assert result == SetupCheckResult(done=True, description="ffmpeg is available.")
    assert "/usr/bin" not in result.description


@pytest.mark.parametrize("found", [None, ""])
def test_missing_ffmpeg_points_at_the_guide(monkeypatch, found):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: found)

    assert FfmpegReady().evaluate(CONTEXT) == SetupCheckResult(
        done=False,
        description=(
            "Video Producer joins takes and exports the cut with ffmpeg. "
            "Install ffmpeg on the server so it is on the PATH, then restart PotionUI."
        ),
        action_label="Read the guide",
        action_href=README_HREF,
    )


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


def test_the_h3_check_looks_at_the_three_minimax_presets(preset_states, models):
    MiniMaxH3Ready().evaluate(CONTEXT)

    assert preset_states.asked == list(presets.MINIMAX_H3_PRESETS)
    assert len(presets.MINIMAX_H3_PRESETS) == 3


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


@pytest.mark.parametrize("where", ["state", "hashes", "file"])
def test_an_error_reading_the_h3_files_is_a_step_still_to_do(preset_states, models, monkeypatch, caplog, where):
    preset_states.set(presets.MINIMAX_H3, name="MiniMax-H3", installed=True)
    models.recommend(presets.MINIMAX_H3, model={"a" * 64})
    target = {"state": "preset_state", "hashes": "preset_model_hashes", "file": "model_file_present"}[where]
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
