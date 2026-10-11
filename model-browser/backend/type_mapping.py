"""The PotionUI model type a source's own model type maps to (PLAN.md §2, §9 phase 1).

`mb_type` on search items and details is this proposal; the download dialog lets the
user change it within the types they may download. A source type with no PotionUI
folder maps to None: the model is listed but not offered for download.
"""

from typing import Dict, Optional

#: CivitAI `type` -> PotionUI model type (`MODEL_TYPES` of `src.plugin_api.models`).
#: Everything else (Hypernetwork, AestheticGradient, MotionModule, Poses, Wildcards,
#: Workflows, ComfyWorkflows, CLIPVision, VisionLanguage, Other, and the types CivitAI
#: adds later) has no PotionUI type.
CIVITAI_TYPES: Dict[str, str] = {
    "Checkpoint": "checkpoint",
    "LORA": "lora",
    "LoCon": "lora",
    "DoRA": "lora",
    "TextualInversion": "embedding",
    "Controlnet": "controlnet",
    "Upscaler": "upscaler",
    "VAE": "vae",
    "Detection": "detection_bbox",
    "TextEncoder": "text_encoder",
    "CLIP": "text_encoder",
    "UNet": "unet",
    "LLM": "llm",
}

_CIVITAI_TYPES_FOLDED = {key.lower(): value for key, value in CIVITAI_TYPES.items()}


def civitai_mb_type(civitai_type: Optional[str]) -> Optional[str]:
    """The PotionUI type for a CivitAI model type (case-insensitive), or None when there is none."""
    if not isinstance(civitai_type, str):
        return None
    return CIVITAI_TYPES.get(civitai_type) or _CIVITAI_TYPES_FOLDED.get(civitai_type.strip().lower())
