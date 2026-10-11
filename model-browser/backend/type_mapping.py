"""The PotionUI model type a source's own model type maps to (PLAN.md §2, §8.3, §9).

`mb_type` on search items and details is this proposal; the download dialog lets the
user change it within the types they may download. A source type with no PotionUI
folder maps to None: the model is listed but not offered for download.

- CivitAI has a fixed `type` enum: `civitai_mb_type` maps it.
- Hugging Face has none: `huggingface_mb_type` guesses from the repo's tags, its
  `pipeline_tag`, its file names and its id.
"""

from typing import Dict, FrozenSet, Iterable, Optional

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


# Hugging Face ----------------------------------------------------------------------

#: File extensions of model weights in a Hugging Face repo (`.sft` is a short `.safetensors`).
WEIGHT_EXTENSIONS = (".safetensors", ".sft", ".gguf", ".ckpt", ".pt", ".pth", ".bin", ".onnx")
#: Weight files that make a text-to-image repo a single-file checkpoint when one sits at the root.
_CHECKPOINT_EXTENSIONS = (".safetensors", ".sft", ".ckpt", ".pt", ".pth", ".bin")
#: Matched in the tags and the repo id (lower case, `_` read as `-`): an upscaler (ESRGAN family).
UPSCALER_HINTS = ("esrgan", "upscal", "super-resolution")
#: Pipeline tags whose models answer with text, labels or embeddings (LLMs, classifiers, ASR):
#: their `lora` / `gguf` tags are LLM adapters and quantisations, not PotionUI assets.
HF_TEXT_OUTPUT_TASKS: FrozenSet[str] = frozenset({
    "any-to-any",
    "audio-classification",
    "audio-text-to-text",
    "automatic-speech-recognition",
    "conversational",
    "document-question-answering",
    "feature-extraction",
    "fill-mask",
    "graph-ml",
    "image-classification",
    "image-feature-extraction",
    "image-text-to-text",
    "image-to-text",
    "multiple-choice",
    "question-answering",
    "reinforcement-learning",
    "robotics",
    "sentence-similarity",
    "summarization",
    "table-question-answering",
    "table-to-text",
    "tabular-classification",
    "tabular-regression",
    "tabular-to-text",
    "text-classification",
    "text-generation",
    "text-ranking",
    "text-retrieval",
    "text2text-generation",
    "time-series-forecasting",
    "token-classification",
    "translation",
    "video-classification",
    "video-text-to-text",
    "visual-document-retrieval",
    "visual-question-answering",
    "zero-shot-classification",
    "zero-shot-image-classification",
    "zero-shot-object-detection",
})
#: Every type `huggingface_mb_type` can answer (checked against the core's `MODEL_TYPES` in the tests).
HUGGINGFACE_MB_TYPES = frozenset({"lora", "controlnet", "vae", "upscaler", "diffusion_model", "checkpoint"})


def _has_upscaler_hint(tags: Iterable[str], repo_id: Optional[str]) -> bool:
    texts = [*tags, repo_id or ""]
    for text in texts:
        folded = text.lower().replace("_", "-")
        if any(hint in folded for hint in UPSCALER_HINTS):
            return True
    return False


def huggingface_mb_type(
    tags: Optional[Iterable[str]],
    pipeline_tag: Optional[str],
    filenames: Optional[Iterable[str]],
    repo_id: Optional[str] = None,
) -> Optional[str]:
    """The PotionUI type for a Hugging Face repo, or None when nothing in it is a PotionUI asset.

    In order: a `lora` tag -> lora, `controlnet` -> controlnet, `vae` -> vae, an upscaler
    hint (`esrgan`, `upscal`, `super-resolution` in a tag or the repo id) -> upscaler,
    `gguf` -> diffusion_model, a `text-to-image` repo with a weight file at its root ->
    checkpoint. A repo whose `pipeline_tag` is a text-output task (`text-generation`,
    `image-text-to-text`, ...) is None whatever its tags: its LoRAs and GGUF files are
    for language models. `filenames` are the repo's file paths (`siblings` or the tree).
    """
    tag_list = [tag for tag in tags or () if isinstance(tag, str)]
    tag_set = {tag.strip().lower() for tag in tag_list}
    pipeline = pipeline_tag.strip().lower() if isinstance(pipeline_tag, str) else ""
    if pipeline in HF_TEXT_OUTPUT_TASKS:
        return None
    if "lora" in tag_set:
        return "lora"
    if "controlnet" in tag_set:
        return "controlnet"
    if "vae" in tag_set:
        return "vae"
    if _has_upscaler_hint(tag_list, repo_id if isinstance(repo_id, str) else None):
        return "upscaler"
    if "gguf" in tag_set:
        return "diffusion_model"
    if pipeline == "text-to-image":
        for name in filenames or ():
            if isinstance(name, str) and "/" not in name and name.lower().endswith(_CHECKPOINT_EXTENSIONS):
                return "checkpoint"
    return None
