import pytest
import yaml

from backend import core_bridge, scaffold

FAMILY = scaffold.FamilyPipes(
    family="z_image",
    loader_name="model_loader/z_image",
    generator_name="generator/z_image",
    model_slots=("diffusion_model", "text_encoder", "vae"),
    has_loras=True,
    has_text_encoder_output=True,
    steps_default=8,
    guidance_key="guidance",
    guidance_default=1.0,
    sampler_default="euler",
    sampler_choices=("euler",),
    resolution_default="1024x1024",
)

CASES = [
    ("native", ["txt2img", "img2img"], None, None),
    ("comfyui", ["txt2img"], None, None),
    ("cloud", ["txt2img", "edit", "txt2video", "img2video"], "cloud.openrouter", None),
    ("native", ["txt2img", "img2img"], None, FAMILY),
]


def _files(engine, modes, driver, family, name="Skeleton"):
    return scaffold.preset_files(
        preset_id="skeleton-test", name=name, category="image", engine=engine, modes=modes, driver=driver, family=family
    )


@pytest.mark.parametrize("engine, modes, driver, family", CASES)
def test_every_skeleton_lints_without_errors(tmp_path, engine, modes, driver, family):
    scaffold.write_files(tmp_path / "preset", _files(engine, modes, driver, family))

    errors, warnings = core_bridge.lint(tmp_path / "preset")

    assert errors == []
    assert all("no tests.yml" in warning or "placeholder" in warning.lower() for warning in warnings), warnings


def test_the_manifest_and_the_description_carry_the_request():
    produced = _files("native", ["txt2img"], None, None, name='My "quoted" preset')

    manifest = yaml.safe_load(produced["preset.yml"])
    assert (manifest["id"], manifest["name"], manifest["category"], manifest["engine"], manifest["modes"]) == (
        "skeleton-test", 'My "quoted" preset', "image", "native", ["txt2img"],
    )
    assert "driver" not in manifest and manifest["formulas"] == {"groups": {}}
    assert produced["description.md"].startswith('# My "quoted" preset')


def test_native_and_comfyui_modes_get_a_tab_and_cloud_modes_get_shared_tabs():
    native = set(scaffold.mode_files("txt2img", "native"))
    assert native == {"modes/txt2img/pipeline.yml", "modes/txt2img/form.yml", "modes/txt2img/tabs/main.yml"}
    comfy = scaffold.mode_files("edit", "comfyui")
    assert '"comfyui"' in comfy["modes/edit/pipeline.yml"] and "files/workflows/edit.json" in comfy["modes/edit/pipeline.yml"]
    cloud = scaffold.mode_files("img2video", "cloud")
    assert set(cloud) == {"modes/img2video/pipeline.yml", "modes/img2video/form.yml"}
    assert "references_img2video.yml" in cloud["modes/img2video/form.yml"]
    assert 'task: "img2video"' in cloud["modes/img2video/pipeline.yml"] and "first_frame_loader" in cloud["modes/img2video/pipeline.yml"]


def test_a_family_mode_wires_the_loader_and_generator_and_its_tabs():
    produced = scaffold.mode_files("txt2img", "native", FAMILY)

    assert set(produced) == {
        "modes/txt2img/pipeline.yml", "modes/txt2img/form.yml", "modes/txt2img/tabs/generation.yml",
        "modes/txt2img/tabs/lora.yml", "modes/txt2img/tabs/advanced.yml",
    }
    pipeline = yaml.safe_load(produced["modes/txt2img/pipeline.yml"].replace("{{", "'{{").replace("}}", "}}'") if False else produced["modes/txt2img/pipeline.yml"])
    names = [pipe["name"] for pipe in pipeline["pipeline"]]
    assert names == [
        "model_loader/z_image", "prompt_encoder", "seed_generator", "dynamic_prompts_renderer", "from_iotype",
        "param_emitter", "generator/z_image", "gallery",
    ]
    assert pipeline["pipeline"][1]["input"] == [["text_encoder", "model_loader/z_image", "text_encoder"]]
    assert sorted(pipeline["pipeline"][0]["configuration"]) == ["diffusion_model", "loras", "text_encoder", "vae"]
    generation = yaml.safe_load(produced["modes/txt2img/tabs/generation.yml"])
    assert [field["name"] for field in generation["fields"][2:]] == ["diffusion_model", "text_encoder", "vae"]
    advanced = yaml.safe_load(produced["modes/txt2img/tabs/advanced.yml"])
    assert [(field["name"], field["default"]) for field in advanced["fields"]] == [("steps", 8), ("sampler", "euler"), ("guidance", 1.0)]


def test_a_family_without_loras_or_text_encoder_output_skips_them():
    lean = scaffold.FamilyPipes(**{**FAMILY.__dict__, "has_loras": False, "has_text_encoder_output": False, "guidance_key": "cfg", "sampler_choices": ("euler", "dpmpp_2m")})

    produced = scaffold.mode_files("txt2img", "native", lean)

    assert "modes/txt2img/tabs/lora.yml" not in produced
    assert "loras" not in produced["modes/txt2img/pipeline.yml"]
    assert "text_encoder\"]" not in produced["modes/txt2img/pipeline.yml"]
    assert 'label: "CFG"' in produced["modes/txt2img/tabs/advanced.yml"]
    assert 'value: "dpmpp_2m"' in produced["modes/txt2img/tabs/advanced.yml"]


def test_short_descriptions_fall_back_to_the_mode_name():
    assert scaffold.with_short_description("txt2img", 'name: "x"\nfields: []\n').splitlines()[1] == 'short_description: "Generate an image from a text prompt."'
    assert scaffold.with_short_description("my_mode", 'name: "x"\n').splitlines()[1] == 'short_description: "My mode with this preset."'


def test_cloud_formula_groups_add_the_output_group_only_for_image_modes():
    assert "output:" in scaffold.cloud_formula_groups(["txt2img"])
    assert "output:" not in scaffold.cloud_formula_groups(["txt2video"])
