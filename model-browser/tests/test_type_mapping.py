"""`backend.type_mapping`: CivitAI types to PotionUI model types, checked against the core's list."""

import pytest

from backend.type_mapping import CIVITAI_TYPES, civitai_mb_type
from src.plugin_api.models import MODEL_TYPES

from .civitai_fakes import body


def test_every_mapped_type_is_a_potionui_model_type():
    assert set(CIVITAI_TYPES.values()) <= set(MODEL_TYPES)


@pytest.mark.parametrize(
    "civitai_type, expected",
    [
        ("Checkpoint", "checkpoint"),
        ("LORA", "lora"),
        ("LoCon", "lora"),
        ("DoRA", "lora"),
        ("TextualInversion", "embedding"),
        ("Controlnet", "controlnet"),
        ("Upscaler", "upscaler"),
        ("VAE", "vae"),
        ("Detection", "detection_bbox"),
        ("TextEncoder", "text_encoder"),
        ("CLIP", "text_encoder"),
        ("UNet", "unet"),
        ("LLM", "llm"),
        ("lora", "lora"),
        (" Checkpoint ", "checkpoint"),
    ],
)
def test_mapped_types(civitai_type, expected):
    assert civitai_mb_type(civitai_type) == expected


@pytest.mark.parametrize(
    "civitai_type",
    ["Hypernetwork", "AestheticGradient", "MotionModule", "Poses", "Wildcards", "Workflows", "Other", "Unknown", "", None, 3],
)
def test_types_without_a_potionui_folder_map_to_none(civitai_type):
    assert civitai_mb_type(civitai_type) is None


def test_every_mapped_type_is_a_live_civitai_type():
    assert set(CIVITAI_TYPES) <= set(body("enums")["ModelType"])
