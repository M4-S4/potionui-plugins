import importlib
import importlib.util
import math
import sys
from pathlib import Path

import pytest
from PIL import Image

from src.pipelines.pipes.generator.video_minimax_h3 import conditioning, geometry
from src.platform.runtime.native.text_encoders import qwen3, qwen3_vl_vision

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / "video-producer" for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "video_producer_encoder_under_test"


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


encoder = _plugin_module("backend.encoder")
FACTOR = qwen3_vl_vision.VISION_PATCH_SIZE * qwen3_vl_vision.VISION_SPATIAL_MERGE_SIZE
OUTPUTS = [(832, 480), (960, 544), (1344, 768), (480, 832)]
BUDGETS = [None, 1, 2, 4]


def _core_limit(budget, output):
    if not budget:
        return qwen3_vl_vision.H3_VISION_MAX_PIXELS
    return max(int(budget * output[0] * output[1]), qwen3_vl_vision.H3_VISION_MIN_PIXELS)


def _core_image_tokens(picture, limit):
    width, height = conditioning.pad_reference_to_aspect_range(Image.new("RGB", picture)).size
    h_bar, w_bar = qwen3_vl_vision._smart_resize_grid(height, width, factor=FACTOR, min_pixels=qwen3_vl_vision.H3_VISION_MIN_PIXELS, max_pixels=limit)
    return (h_bar // FACTOR) * (w_bar // FACTOR)


def _core_video_tokens(frames, size, limit):
    width, height = size
    canvas_height, canvas_width = geometry.resolve_canvas_size(width, height)
    canvas_height, canvas_width = conditioning._snap_size_within_aspect_range(canvas_height, canvas_width, height, width, geometry.CANVAS_MULTIPLE)
    indices, blocks = qwen3._sample_reference_video_frames(
        frames, fps=qwen3.MINIMAX_H3_VIDEO_FPS, sample_fps=qwen3.MINIMAX_H3_VIDEO_SAMPLE_FPS, temporal_patch=qwen3_vl_vision.VISION_TEMPORAL_PATCH_SIZE
    )
    h_bar, w_bar = qwen3_vl_vision._smart_resize_grid(canvas_height, canvas_width, factor=FACTOR, min_pixels=qwen3_vl_vision.H3_VISION_MIN_PIXELS, max_pixels=limit)
    assert len(blocks) == math.ceil(len(indices) / qwen3_vl_vision.VISION_TEMPORAL_PATCH_SIZE)
    return len(blocks) * (h_bar // FACTOR) * (w_bar // FACTOR)


def test_the_plugin_reads_the_encoder_bounds_and_the_video_rate_the_core_uses():
    assert encoder.TILE == FACTOR
    assert (encoder.MIN_PIXELS, encoder.MAX_PIXELS) == (qwen3_vl_vision.H3_VISION_MIN_PIXELS, qwen3_vl_vision.H3_VISION_MAX_PIXELS)
    assert (encoder.FPS, encoder.SAMPLE_FPS, encoder.TEMPORAL_PATCH) == (qwen3.MINIMAX_H3_VIDEO_FPS, qwen3.MINIMAX_H3_VIDEO_SAMPLE_FPS, qwen3_vl_vision.VISION_TEMPORAL_PATCH_SIZE)
    assert (encoder.CANVAS_SHORT_EDGE, encoder.CANVAS_MAX_PIXELS, encoder.MAX_RATIO) == (geometry.CANVAS_SHORT_EDGE, geometry.CANVAS_MAX_PIXELS, geometry.MAX_ASPECT_RATIO)


@pytest.mark.parametrize("output", OUTPUTS)
@pytest.mark.parametrize("budget", BUDGETS)
@pytest.mark.parametrize("picture", [(1024, 1024), (1344, 768), (1920, 1080), (4000, 500), (300, 2000), (200, 200), (3000, 4000)])
def test_the_plugin_counts_the_vision_tokens_of_a_reference_picture_as_the_core_makes_them(picture, budget, output):
    limit = encoder.max_pixels(budget, output)

    assert limit == _core_limit(budget, output)
    assert encoder.image_tokens(picture, limit) == _core_image_tokens(picture, limit)


@pytest.mark.parametrize("output", OUTPUTS)
@pytest.mark.parametrize("budget", BUDGETS)
@pytest.mark.parametrize("frames", [1, 17, 56, 72, 120])
def test_the_plugin_counts_the_vision_tokens_of_a_reference_video_as_the_core_makes_them(frames, budget, output):
    limit = encoder.max_pixels(budget, output)

    assert encoder.video_tokens(frames, output, limit) == _core_video_tokens(frames, output, limit)
