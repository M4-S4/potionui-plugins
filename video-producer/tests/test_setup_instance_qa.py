import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from backend import core_bridge, presets
from backend.core_bridge import PresetState
from src.plugin_api import SetupCheckContext

CONTEXT = SetupCheckContext(plugin_id="video-producer", settings={})
MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yml"

H3_DIT = ["minimax_h3_fl2va_pruned_fp8_scaled.safetensors", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"]
H3_TEXT = ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"]
H3_VIDEO_VAE = ["minimax_h3_video_vae_fp16.safetensors"]
H3_AUDIO_VAE = ["minimax_h3_audio_vae_fp32.safetensors"]
H3_UPSCALER = ["minimax_h3_latent_upscaler_3d_bf16.safetensors"]
RANK8 = "MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors"
FAST_DIT = ["fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors"]
VAE_INT8 = ["minimax_h3_video_vae_int8_convrot.safetensors"]

RECOMMENDED = {
    presets.MINIMAX_H3: {
        "video": {"model": H3_DIT, "text_encoder": H3_TEXT, "video_vae": H3_VIDEO_VAE, "audio_vae": H3_AUDIO_VAE},
        "upscale": {"model": H3_DIT, "text_encoder": H3_TEXT, "video_vae": H3_VIDEO_VAE, "audio_vae": H3_AUDIO_VAE, "upscale_model": H3_UPSCALER},
    },
    presets.MINIMAX_H3_FAST: {
        "video": {"model": FAST_DIT, "text_encoder": H3_TEXT, "video_vae": H3_VIDEO_VAE, "audio_vae": H3_AUDIO_VAE},
    },
    presets.MINIMAX_H3_12GB: {
        "video": {"model": H3_DIT[1:] + [RANK8], "text_encoder": H3_TEXT, "video_vae": VAE_INT8, "audio_vae": H3_AUDIO_VAE},
        "upscale": {"model": H3_DIT[1:] + [RANK8], "text_encoder": H3_TEXT, "video_vae": VAE_INT8, "audio_vae": H3_AUDIO_VAE, "upscale_model": H3_UPSCALER},
    },
    presets.MINIMAX_H3_FAST_12GB: {
        "video": {"model": FAST_DIT, "text_encoder": H3_TEXT[:1], "video_vae": VAE_INT8, "audio_vae": H3_AUDIO_VAE},
    },
}

INSTANCE_DISK = {RANK8, FAST_DIT[0], H3_TEXT[0], H3_VIDEO_VAE[0], VAE_INT8[0], H3_AUDIO_VAE[0], H3_UPSCALER[0]}
NAMES = {
    presets.WAN: "Wan 2.1 / 2.2",
    presets.MINIMAX_H3: "MiniMax-H3",
    presets.MINIMAX_H3_FAST: "MiniMax-H3-Fast",
    presets.MINIMAX_H3_12GB: "MiniMax-H3 (12 GB)",
    presets.MINIMAX_H3_FAST_12GB: "MiniMax-H3-Fast (12 GB)",
    presets.SEEDVR2: "SeedVR2",
}
INSTALLED = (presets.WAN, presets.MINIMAX_H3, presets.MINIMAX_H3_FAST, presets.MINIMAX_H3_12GB, presets.MINIMAX_H3_FAST_12GB, presets.SEEDVR2)


class Instance:
    """The state this instance reported: a native backend whose 12 GB GPU was read, five video presets and SeedVR2 installed and assigned, a writable file storage directory, ffmpeg with ffprobe, and the DiT of the 12 GB variant on disk but none of the DiTs the full MiniMax-H3 preset recommends."""

    def __init__(self, monkeypatch, storage):
        self.disk = set(INSTANCE_DISK)
        self.installed = set(INSTALLED)
        self.assigned = set(INSTALLED)
        self.backends = [{"id": "native", "name": "Local Generation", "engine": "native", "driver": "native.local", "execution_device": "this_host_gpu", "vram_total_gb": 12.0, "vram_free_gb": 11.2}]
        self.ffmpeg = "/usr/bin/ffmpeg"
        self.ffprobe = "/usr/bin/ffprobe"
        self.storage = storage
        monkeypatch.setattr(core_bridge, "enabled_backends", lambda: list(self.backends))
        monkeypatch.setattr(core_bridge, "storage_directory", lambda: self.storage)
        monkeypatch.setattr(core_bridge, "enabled_cloud_video_models", lambda backend_id: 0)
        monkeypatch.setattr(core_bridge, "preset_state", self._state)
        monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: self.ffmpeg)
        monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: self.ffprobe)
        monkeypatch.setattr(core_bridge, "preset_model_hashes", self._hashes)
        monkeypatch.setattr(core_bridge, "model_file_present", lambda sha: sha.removeprefix("sha:") in self.disk)
        monkeypatch.setattr(core_bridge, "installed_model_for_file", lambda name: f"id:{name}" if name in self.disk else None)
        monkeypatch.setattr(core_bridge, "describe_preset", self._describe)
        monkeypatch.setattr(core_bridge, "preset_form_fields", self._fields)

    def _state(self, preset_id):
        return PresetState(
            id=preset_id,
            name=NAMES.get(preset_id, preset_id),
            loaded=preset_id in NAMES,
            installed=preset_id in self.installed,
            assigned=preset_id in self.assigned,
        )

    def _hashes(self, preset_id, field_names, modes=None):
        out = {name: set() for name in field_names}
        for mode, roles in RECOMMENDED.get(preset_id, {}).items():
            if modes is not None and mode not in modes:
                continue
            for name in field_names:
                out[name].update(f"sha:{file}" for file in roles.get(name, ()))
        return out

    def _describe(self, preset_id):
        modes = RECOMMENDED.get(preset_id)
        return SimpleNamespace(modes=dict.fromkeys(modes)) if modes else None

    def _fields(self, preset_id, mode):
        roles = RECOMMENDED.get(preset_id, {}).get(mode)
        if roles is None:
            return None
        return {
            role: {"type": "model", "recommendations": [{"sha256": f"sha:{file}", "filename": file} for file in files]}
            for role, files in roles.items()
        }


@pytest.fixture
def instance(monkeypatch, tmp_path):
    return Instance(monkeypatch, tmp_path)


def _checks():
    steps = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["setup"]
    out = []
    for step in steps:
        module, _, name = step["check"].partition(":")
        out.append((step["label"], getattr(importlib.import_module(module), name)()))
    return out


def _run():
    return [(label, check.evaluate(CONTEXT)) for label, check in _checks()]


def test_the_instance_replica_reports_five_steps_done_and_the_full_h3_dit_to_do(instance):
    report = _run()

    assert [result.done for _, result in report] == [True, True, True, True, True, False]
    assert report[0][1].description == "Takes can run on Local Generation."
    assert report[1][1].description.startswith(
        "Installed and assigned: Wan 2.1 / 2.2, MiniMax-H3, MiniMax-H3-Fast, MiniMax-H3 (12 GB), MiniMax-H3-Fast (12 GB)."
    )
    assert report[2][1].description == (
        "SeedVR2 is installed and assigned. No interpolator is ready: takes slower than the film repeat frames in the export "
        "until Video Tools with RIFE 4.25 is installed."
    )
    assert report[3][1].description == f"Work files are written in {instance.storage / 'video_producer'}."
    assert report[4][1].description == "ffmpeg is available."
    last = report[5][1]
    assert last.description.startswith("MiniMax-H3 is missing its DiT. Download one of the files its model pickers recommend;")
    assert "12 GB" not in last.description and "Fast" not in last.description
    assert (last.action_label, last.action_href) == ("Open MiniMax-H3", f"/admin?tab=presets&id={presets.MINIMAX_H3}")


def test_the_dit_of_the_12_gb_variant_on_disk_is_not_a_dit_of_the_full_preset(instance):
    instance.disk.discard(RANK8)

    last = _run()[5][1]

    assert last.done is False
    assert "MiniMax-H3 is missing its DiT." in last.description
    assert "MiniMax-H3 (12 GB) is missing its DiT." in last.description


def test_a_recommended_dit_on_disk_completes_the_last_step_and_the_whole_setup(instance):
    instance.disk.add(H3_DIT[0])

    report = _run()

    assert [result.done for _, result in report] == [True] * 6
    assert report[5][1].action_label is None and report[5][1].action_href is None


@pytest.mark.parametrize(
    "gone, label",
    [
        (H3_TEXT[0], "text encoder"),
        (H3_VIDEO_VAE[0], "video VAE"),
        (H3_AUDIO_VAE[0], "audio VAE"),
        (H3_UPSCALER[0], "latent upscaler"),
    ],
)
def test_each_other_missing_h3_file_is_reported_by_its_role_on_top_of_the_dit(instance, gone, label):
    instance.disk.discard(gone)

    last = _run()[5][1]

    assert last.done is False
    assert f"MiniMax-H3 is missing its DiT and {label}." in last.description


@pytest.mark.parametrize(
    "mutate, index, fragment, href",
    [
        (lambda i: setattr(i, "backends", []), 0, "Enable the native backend of this machine", "/admin?tab=backends"),
        (lambda i: i.backends[0].update(execution_device="this_host_gpu", vram_total_gb=None), 0, "Takes cannot run on Local Generation: no GPU could be read for it", "/admin?tab=backends"),
        (lambda i: i.backends[0].update(execution_device="unestablished"), 0, "Takes cannot run on Local Generation: it is not running.", "/admin?tab=backends"),
        (lambda i: setattr(i, "assigned", set()), 1, "Installed but assigned to no one", f"/admin?tab=presets&id={presets.WAN}"),
        (lambda i: setattr(i, "installed", {presets.WAN, presets.MINIMAX_H3}), 2, "Final takes are upscaled with SeedVR2", f"/admin?tab=presets&id={presets.SEEDVR2}"),
        (lambda i: ((i.storage / "blocker").write_text("x", encoding="utf-8"), setattr(i, "storage", i.storage / "blocker")), 3, "Video Producer cannot write in", "/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME"),
        (lambda i: setattr(i, "ffmpeg", None), 4, "ffmpeg is missing", "/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME"),
        (lambda i: setattr(i, "ffprobe", None), 4, "ffprobe is missing", "/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME"),
    ],
    ids=["no-engine", "gpu-unread", "not-running", "no-assignment", "no-seedvr2", "no-workdir", "no-ffmpeg", "no-ffprobe"],
)
def test_each_step_turns_to_do_alone_with_its_text_and_link(instance, mutate, index, fragment, href):
    mutate(instance)

    report = _run()

    assert fragment in report[index][1].description
    assert report[index][1].action_href == href
    assert report[index][1].done is False
    done_elsewhere = [result.done for position, (_, result) in enumerate(report) if position not in (index, 5)]
    if index != 1:
        assert all(done_elsewhere)


@pytest.mark.parametrize("broken", ["enabled_backends", "preset_state", "storage_directory", "find_ffmpeg", "preset_model_hashes"])
def test_a_core_error_makes_the_dependent_steps_to_do_with_a_link_and_never_raises(instance, monkeypatch, broken):
    def raiser(*args, **kwargs):
        raise RuntimeError("core unavailable")

    monkeypatch.setattr(core_bridge, broken, raiser)

    report = _run()

    unverifiable = [result for _, result in report if result.description.startswith("Could not check")]
    assert unverifiable
    assert all(result.done is False and result.action_href and result.action_label for result in unverifiable)
