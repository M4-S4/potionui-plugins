import logging
from typing import Dict, List, Sequence, Set
from urllib.parse import urlencode

from . import PLUGIN_ID, core_bridge, presets
from .core_bridge import CLOUD_ENGINE, NATIVE_DRIVERS, PresetState, SetupCheck, SetupCheckContext, SetupCheckResult

logger = logging.getLogger("plugins.video-producer")

H3_MODEL_ROLES = (
    ("model", "DiT"),
    ("text_encoder", "text encoder"),
    ("video_vae", "video VAE"),
    ("audio_vae", "audio VAE"),
)


def admin_href(**params: str) -> str:
    """A link to an Admin page with these query parameters."""
    return "/admin?" + urlencode(params)


BACKENDS_HREF = admin_href(tab="backends")
PRESETS_HREF = admin_href(tab="presets")
README_HREF = admin_href(tab="docs", doc=f"plugin/{PLUGIN_ID}/README")


def _names(states: Sequence[PresetState]) -> str:
    return ", ".join(state.name for state in states)


def _join(words: Sequence[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _unchecked(what: str, action_label: str, action_href: str) -> SetupCheckResult:
    return SetupCheckResult(
        done=False,
        description=f"Could not check {what}; see the server log.",
        action_label=action_label,
        action_href=action_href,
    )


class VideoEngineReady(SetupCheck):
    """A native backend is enabled, or a cloud backend has a video model turned on."""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        try:
            backends = core_bridge.enabled_backends()
            native = [backend for backend in backends if backend["driver"] in NATIVE_DRIVERS]
            cloud = [
                (backend, core_bridge.enabled_cloud_video_models(backend["id"]))
                for backend in backends
                if backend["engine"] == CLOUD_ENGINE
            ]
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Setup check: could not read the backends: %s", exc)
            return _unchecked("the backends", "Open backends", BACKENDS_HREF)
        with_video = [(backend, count) for backend, count in cloud if count > 0]
        if native or with_video:
            engines = [backend["name"] for backend in native] + [
                f"{backend['name']} ({count} video model{'s' if count != 1 else ''})" for backend, count in with_video
            ]
            return SetupCheckResult(done=True, description=f"Takes can run on {', '.join(engines)}.")
        if cloud:
            return SetupCheckResult(
                done=False,
                description=(
                    f"No video model is turned on in {', '.join(backend['name'] for backend, _ in cloud)}. "
                    "Turn one on in the backend's catalog, or enable a native backend."
                ),
                action_label="Open catalog",
                action_href=admin_href(tab="backends", backend=cloud[0][0]["id"], view="catalog"),
            )
        return SetupCheckResult(
            done=False,
            description=(
                "Enable the native backend of this machine or a native remote worker, "
                "or add a cloud backend and turn on a video model in its catalog."
            ),
            action_label="Open backends",
            action_href=BACKENDS_HREF,
        )


class VideoPresetsReady(SetupCheck):
    """At least one Video Director preset is installed and assigned to someone."""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        try:
            states = [core_bridge.preset_state(preset_id) for preset_id in presets.VIDEO_DIRECTOR_PRESETS]
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Setup check: could not read the presets: %s", exc)
            return _unchecked("the presets", "Open presets", PRESETS_HREF)
        loaded = [state for state in states if state.loaded]
        installed = [state for state in loaded if state.installed]
        assigned = [state for state in installed if state.assigned]
        if assigned:
            return SetupCheckResult(
                done=True,
                description=(
                    f"Installed and assigned: {_names(assigned)}. A user sees only the presets assigned to them "
                    "or to one of their groups, which this check cannot verify user by user."
                ),
            )
        if installed:
            return SetupCheckResult(
                done=False,
                description=(
                    f"Installed but assigned to no one: {_names(installed)}. "
                    "Assign one to the users or groups who will use Video Producer."
                ),
                action_label="Assign presets",
                action_href=admin_href(tab="presets", id=installed[0].id),
            )
        if loaded:
            return SetupCheckResult(
                done=False,
                description=(
                    f"Install a Video Director preset ({_names(loaded)}), then assign it. "
                    "Cloud video presets come with their provider plugins."
                ),
                action_label="Open presets",
                action_href=admin_href(tab="presets", id=loaded[0].id),
            )
        return SetupCheckResult(
            done=False,
            description="No Video Director preset is available. Enable a plugin that ships one, such as a cloud provider.",
            action_label="Open presets",
            action_href=PRESETS_HREF,
        )


class UpscalerReady(SetupCheck):
    """SeedVR2 is installed, so draft takes can be upscaled into final takes."""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        try:
            state = core_bridge.preset_state(presets.SEEDVR2)
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Setup check: could not read the SeedVR2 preset: %s", exc)
            return _unchecked("the SeedVR2 preset", "Open presets", PRESETS_HREF)
        if not state.loaded:
            return SetupCheckResult(
                done=False,
                description="The SeedVR2 preset is not available on this instance; final takes need it.",
                action_label="Open presets",
                action_href=PRESETS_HREF,
            )
        if state.installed and state.assigned:
            return SetupCheckResult(done=True, description=f"{state.name} is installed and assigned.")
        if state.installed:
            return SetupCheckResult(
                done=True,
                description=f"{state.name} is installed. Assign it to the users or groups who make final takes.",
            )
        return SetupCheckResult(
            done=False,
            description=(
                f"Final takes are upscaled with {state.name}. Install it, "
                "then assign it to the users or groups who make final takes."
            ),
            action_label=f"Open {state.name}",
            action_href=admin_href(tab="presets", id=state.id),
        )


class FfmpegReady(SetupCheck):
    """ffmpeg is on the server's PATH."""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        try:
            found = core_bridge.find_ffmpeg()
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Setup check: could not look for ffmpeg: %s", exc)
            return _unchecked("ffmpeg", "Read the guide", README_HREF)
        if found:
            return SetupCheckResult(done=True, description="ffmpeg is available.")
        return SetupCheckResult(
            done=False,
            description=(
                "Video Producer joins takes and exports the cut with ffmpeg. "
                "Install ffmpeg on the server so it is on the PATH, then restart PotionUI."
            ),
            action_label="Read the guide",
            action_href=README_HREF,
        )


class MiniMaxH3Ready(SetupCheck):
    """Every installed MiniMax-H3 preset has a recommended file on disk for each of its four models."""

    def evaluate(self, context: SetupCheckContext) -> SetupCheckResult:
        try:
            installed = [
                state
                for state in (core_bridge.preset_state(preset_id) for preset_id in presets.MINIMAX_H3_PRESETS)
                if state.installed
            ]
            missing = {state: labels for state in installed if (labels := self._missing(state))}
        except Exception as exc:
            logger.warning("[VIDEO-PRODUCER] Setup check: could not read the MiniMax-H3 model files: %s", exc)
            return _unchecked("the MiniMax-H3 model files", "Open presets", PRESETS_HREF)
        if not installed:
            return SetupCheckResult(done=True, description="No MiniMax-H3 preset is installed; nothing to check.")
        if not missing:
            return SetupCheckResult(
                done=True,
                description=f"The DiT, text encoder, video VAE and audio VAE files are on disk for {_names(installed)}.",
            )
        first = next(iter(missing))
        details = " ".join(f"{state.name} is missing its {_join(labels)}." for state, labels in missing.items())
        return SetupCheckResult(
            done=False,
            description=(
                f"{details} Download one of the files its model pickers recommend; "
                "the check recognises those files by their SHA-256, not other quantizations."
            ),
            action_label=f"Open {first.name}",
            action_href=admin_href(tab="presets", id=first.id),
        )

    @staticmethod
    def _missing(state: PresetState) -> List[str]:
        hashes: Dict[str, Set[str]] = core_bridge.preset_model_hashes(state.id, [field for field, _ in H3_MODEL_ROLES])
        return [
            label
            for field, label in H3_MODEL_ROLES
            if hashes.get(field) and not any(core_bridge.model_file_present(sha256) for sha256 in sorted(hashes[field]))
        ]
