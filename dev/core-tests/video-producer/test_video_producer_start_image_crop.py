import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.features.forms.binding import bind_form
from src.features.generation.orchestrator import _prepare_director_form_data
from src.features.presets.loader import PresetTemplateLoader
from src.features.presets.processor import PresetProcessor
from src.pipelines.pipes.generator.video_minimax_h3.conditioning import fit_keyframe_to_canvas
from src.platform.templating.processor import TemplateProcessor

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = [REPO_ROOT / "content" / "plugins" / kind / "video-producer" for kind in ("local", "marketplace")]
PLUGIN_ROOT = next((root for root in PLUGIN_ROOTS if (root / "manifest.yml").is_file()), PLUGIN_ROOTS[0])
PACKAGE = "video_producer_start_image_crop_under_test"
SHARED_PRESETS = REPO_ROOT / "content" / "presets" / "_shared"
RED = (205, 35, 35)


def _plugin_module(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


director = _plugin_module("backend.director")
core_bridge = _plugin_module("backend.core_bridge")
framefit = _plugin_module("backend.framefit")
presets = _plugin_module("backend.presets")


@pytest.fixture(scope="module")
def templates():
    loader = PresetTemplateLoader([str(PLUGIN_ROOT / "presets")], shared_path=str(SHARED_PRESETS))
    return {template.id: template for template in loader.load_presets()}


def _square(path):
    image = Image.new("RGB", (1024, 1024), (244, 244, 238))
    ImageDraw.Draw(image).ellipse([256, 256, 768, 768], fill=RED)
    image.save(path)
    return path


def _disc_ratio(image):
    pixels = np.asarray(image.convert("RGB")).astype(int)
    mask = (np.abs(pixels - np.array(RED)) <= 45).all(axis=-1)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    return (cols.max() - cols.min() + 1) / (rows.max() - rows.min() + 1)


def _rendered(template, storage, value, resolution):
    document = director._document("A slow push-in on a red disc.", 24, 2.0, resolution)
    request = {"preset_id": template.id, "mode": "video", "prompts": [{"positive": "A slow push-in on a red disc.", "negative": ""}], "form_data": {"video_director": document, "resolution": resolution}}
    request = core_bridge.bind_director_media(request, "first", {"value": value, "media_type": "image"}, promote=True)
    form = {**request["form_data"], "model": "/models/h3.safetensors", "text_encoder": "/models/te.safetensors", "video_vae": "/models/vae.safetensors", "audio_vae": "/models/audio.safetensors"}
    bound = bind_form(template, "video", form_name=None, raw_form_data=form, user_id=None, storage_dir=str(storage))
    values = {**dict(bound.values), "video_director": form["video_director"]}
    settings = Mock()
    settings.get_file_storage_directory.return_value = str(storage)
    prepared = _prepare_director_form_data(template, "video", values, None, settings, prompt_pair=("A slow push-in on a red disc.", ""))
    processor = PresetProcessor(template_processor=TemplateProcessor(settings=Mock()), settings=Mock(), preset_template_loader=Mock())
    pipes = processor.process(template, {"prompts": request["prompts"], "mode": "video", "form_data": prepared})
    generator = next(pipe for pipe in pipes if pipe["name"] == "generator/video_minimax_h3" and pipe.get("id") == "generator_stage1")
    keyframes = next(pipe for pipe in pipes if pipe["name"] == "media_loader" and pipe.get("id") == "keyframes")
    return generator["config"], [item["path"] for item in keyframes["config"]["media"]]


@pytest.mark.parametrize("preset_id", ["01M54HN72B0KY7H63BKQ16T253", "01M54HN72PABVRE54YNQA2Q7ZT"])
@pytest.mark.parametrize("resolution", ["832x480", "1344x768", "480x832", "768x1344", "640x640"])
def test_a_start_image_cropped_by_video_producer_reaches_minimax_h3_as_its_anchor_and_is_scaled_not_stretched(templates, tmp_path, preset_id, resolution):
    assert preset_id in presets.MINIMAX_H3_12GB_PRESETS
    storage = tmp_path / "storage"
    (storage / "uploads").mkdir(parents=True)
    source = _square(storage / "uploads" / "square.png")
    ratio = framefit.ratio_of(resolution)
    box = framefit.crop_box(1024, 1024, ratio)
    cropped = framefit.crop_file(source, box, storage / "uploads", "square.png") if box is not None else source

    config, paths = _rendered(templates[preset_id], storage, f"uploads/{cropped.name}", resolution)

    assert (config["resolution"], config["keyframe_anchors"]) == (resolution, ["first"])
    assert [Path(path) for path in paths] == [cropped]
    width, height = (int(side) for side in resolution.split("x"))
    with Image.open(paths[0]) as picture:
        sent = picture.convert("RGB")
    fitted = fit_keyframe_to_canvas(sent, height, width, is_geometry_anchor=True)
    assert fitted.size == (width, height)
    assert fitted.tobytes() == sent.resize((width, height), Image.Resampling.LANCZOS).tobytes()
    assert _disc_ratio(fitted) == pytest.approx(1.0, abs=0.02)
