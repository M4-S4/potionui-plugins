import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CATEGORIES = ("image", "video", "audio", "3d", "utility")


@dataclass(frozen=True)
class FamilyPipes:
    family: str
    loader_name: str
    generator_name: str
    model_slots: Tuple[str, ...]
    has_loras: bool
    has_text_encoder_output: bool
    steps_default: int
    guidance_key: str
    guidance_default: float
    sampler_default: str
    sampler_choices: Tuple[str, ...]
    resolution_default: str


@dataclass(frozen=True)
class CloudMode:
    task: str
    category: str
    tab_block: str
    params: Tuple[Tuple[str, str], ...]
    media: str


IMAGE_PARAMS = (
    ("aspect_ratio", "aspect_ratio"),
    ("resolution", "resolution"),
    ("quality", "quality"),
    ("output_format", "output_format"),
    ("background", "background"),
)
VIDEO_PARAMS = (
    ("aspect_ratio", "aspect_ratio"),
    ("resolution", "resolution"),
    ("duration_s", "duration"),
    ("generate_audio", "generate_audio"),
)

CLOUD_MODES: Dict[str, CloudMode] = {
    "txt2img": CloudMode("txt2img", "image", "image", IMAGE_PARAMS, "none"),
    "edit": CloudMode("img_edit", "image", "image_edit", IMAGE_PARAMS + (("strength", "strength"),), "references"),
    "txt2video": CloudMode("txt2video", "video", "video", VIDEO_PARAMS, "none"),
    "img2video": CloudMode("img2video", "video", "img2video", VIDEO_PARAMS, "frames"),
}

CLOUD_REFERENCE_BLOCKS = {"references": "references_edit", "frames": "references_img2video"}

SHORT_DESCRIPTIONS = {
    "txt2img": "Generate an image from a text prompt.",
    "img2img": "Change an image, guided by a prompt.",
    "edit": "Change an existing image by instruction.",
    "inpaint": "Repaint a masked part of an image.",
    "txt2video": "Generate a video from a text prompt.",
    "txt2vid": "Generate a video from a text prompt.",
    "img2video": "Animate an image into a video.",
    "img2vid": "Animate an image into a video.",
    "upscale": "Make an image larger and sharper.",
}


def preset_yml(preset_id: str, name: str, category: str, engine: str, modes: List[str],
               driver: Optional[str] = None, formula_groups: str = "  groups: {}\n") -> str:
    driver_line = f'driver: "{driver}"\n' if driver else ""
    modes_yaml = "\n".join(f"  - {m}" for m in modes)
    quoted_name = json.dumps(name, ensure_ascii=False)
    return f"""########
## {name} preset configuration
## Authoring reference: docs/presets/tutorial.md
########
schema: 1
id: "{preset_id}"
name: {quoted_name}
category: "{category}"
version: "1.0.0"
engine: "{engine}"
{driver_line}tags: []

# Preset-wide constants. Reference them in pipeline.yml as {{{{ preset.vars.<name> }}}}.
vars:
  default_steps: 30

formulas:
{formula_groups}
modes:
{modes_yaml}
"""


def pipeline_yml(mode: str, engine: str) -> str:
    header = f"""# Pipeline for the '{mode}' mode.
#
# `pipeline` is an ordered list of pipes. Each pipe supports:
#   name          (required) the registered pipe name, e.g. "generator/sdxl"
#   id            (optional) a stable id other pipes reference in their `input`
#   enabled       a real YAML bool, or an exact "{{{{ expression }}}}" that evaluates
#                 to a bool - omitted means enabled
#   input         list of [name, provider_pipe_id, provider_output_var]
#   configuration pipe config; values may be Jinja2 templates rendered at run time
#
# Jinja context available here (pipeline.yml only - see "Template contexts" in
# docs/presets/pipelines.md): form.<field>, request.mode, request.form_name,
# generation.prompts.*, generation.profile, preset.id, preset.name, preset.vars,
# runtime.settings.*, paths.preset, plus the globals path(), icon() and
# get_speed_profile().
"""
    if engine == "comfyui":
        return header + f"""#
# Export the workflow as API-format JSON into files/workflows/, drop it next to
# this file, and map its node inputs via `field_mappings`
# ([source_template, "node_id.inputs.field", type]). See docs/presets/comfyui.md
# and content/plugins/marketplace/comfyui-backend for worked examples.
pipeline:
  - name: "comfyui"
    id: "comfyui"
    enabled: true
    configuration:
      host: "127.0.0.1"
      port: 8188
      workflow_file: "{{{{ paths.preset }}}}/modes/{mode}/files/workflows/{mode}.json"
      field_mappings: []
      timeout: 300

  - name: "gallery"
    id: "gallery"
    enabled: true
    input:
      - ["image", "comfyui", "image"]
"""
    return header + """#
# Replace the placeholder below with the real pipes for this model
# (e.g. checkpoint_loader -> prompt_encoder -> seed_generator -> generator -> gallery).
pipeline:
  - name: "gallery"
    id: "gallery"
    enabled: true
"""


def with_short_description(mode: str, form: str) -> str:
    text = SHORT_DESCRIPTIONS.get(mode, f"{mode.replace('_', ' ').capitalize()} with this preset.")
    head, sep, rest = form.partition("\n")
    return f'{head}{sep}short_description: "{text}"\n{rest}'


def form_yml(mode: str) -> str:
    return f'''name: "default"
fields:
  - type: "tabs"
    children:
      - type: "tab"
        label: "Main"
        children: "{{{{ paths.preset }}}}/modes/{mode}/tabs/main.yml"
'''


def tab_yml() -> str:
    return """fields:
  - name: "seed"
    type: "seed"
    label: "Seed"
    default: -1

  - name: "steps"
    type: "slider"
    label: "Steps"
    configuration:
      min: 1
      max: 100
      step: 1
    default: 30
"""


def cloud_formula_groups(modes: List[str]) -> str:
    groups = [("size", '{ label: "Size" }')]
    if any(CLOUD_MODES[mode].category == "image" for mode in modes):
        groups.append(("output", '{ label: "Output format" }'))
    groups += [("provider", '{ label: "Provider options" }'), ("models", '{ label: "Models", preselect: false }')]
    width = max(len(group_id) for group_id, _ in groups) + 1
    return "  groups:\n" + "".join(f"    {(group_id + ':').ljust(width)} {spec}\n" for group_id, spec in groups)


def cloud_form_yml(mode: CloudMode) -> str:
    references = ""
    block = CLOUD_REFERENCE_BLOCKS.get(mode.media)
    if block:
        references = f'''      - type: "tab"
        label: "References"
        configuration: {{icon: "image", icon_display: "icon_only"}}
        children: "{{{{ paths._shared }}}}/cloud/tabs/{block}.yml"
'''
    return f'''name: "custom"
fields:
  - type: "tabs"
    children:
      - type: "tab"
        label: "Generation"
        configuration: {{icon: "generation", icon_display: "icon_only"}}
        children: "{{{{ paths._shared }}}}/cloud/tabs/{mode.tab_block}.yml"
{references}      - type: "tab"
        label: "Provider options"
        configuration: {{icon: "settings", icon_display: "icon_only"}}
        children: "{{{{ paths._shared }}}}/cloud/tabs/provider_options.yml"
'''


def cloud_media_yaml(mode: CloudMode) -> Tuple[str, str]:
    if mode.media == "references":
        loaders = '''  - name: "media_loader"
    id: "media_loader"
    enabled: "{{ (form.references or []) | length > 0 }}"
    configuration:
      media:
        "@loop":
          items: "{{ form.references }}"
          template:
            type: "image"
            path: "{{ item.path | default(item) }}"

'''
        return loaders, '''      - ["images", "media_loader", "image"]
'''
    if mode.media == "frames":
        loaders = ""
        inputs = ""
        for frame in ("first_frame", "last_frame"):
            loaders += f'''  - name: "media_loader"
    id: "{frame}_loader"
    enabled: "{{{{ (form.{frame} or '') != '' }}}}"
    configuration:
      media:
        - type: "image"
          path: "{{{{ form.{frame} }}}}"

'''
            inputs += f'''      - ["{frame}", "{frame}_loader", "image"]
'''
        return loaders, inputs
    return "", ""


def cloud_pipeline_yml(name: str, mode: CloudMode) -> str:
    loaders, media_inputs = cloud_media_yaml(mode)
    params = "\n".join(f'        {param}: "{{{{ form.{field} }}}}"' for param, field in mode.params)
    return f'''pipeline:
  - name: "dynamic_prompts_renderer"
    id: "dynamic_prompts_renderer"
    enabled: true
    configuration:
      pairs: "{{{{ generation.prompts.pairs }}}}"
      quantity: "{{{{ form.count or 1 }}}}"

  - name: "seed_generator"
    id: "seed_generator"
    enabled: true
    configuration:
      seed: "{{{{ form.seed }}}}"
      quantity: "{{{{ form.count or 1 }}}}"

{loaders}  - name: "from_iotype"
    id: "from_iotype"
    enabled: true
    input:
      - ["seed", "seed_generator", "seed"]
    configuration:
      from: "seed"

  - name: "param_emitter"
    id: "param_emitter"
    enabled: true
    input:
      - ["seed", "from_iotype", "seed"]
    configuration:
      quantity: "{{{{ form.count or 1 }}}}"
      parameters:
        - ["positive_prompt", "{{{{ generation.prompts.positives }}}}"]
        - ["negative_prompt", "{{{{ generation.prompts.negatives }}}}"]

  - name: "cloud_generate"
    id: "cloud_generate"
    enabled: true
    input:
      - ["seed", "seed_generator", "seed"]
{media_inputs}    configuration:
      task: "{mode.task}"
      model: "{{{{ form.model }}}}"
      quantity: "{{{{ form.count or 1 }}}}"
      prompts: "{{{{ generation.prompts.pairs }}}}"
      params:
{params}
      options: "{{{{ form.provider_options }}}}"

  - name: "gallery"
    id: "gallery"
    enabled: true
    input:
      - ["image", "cloud_generate", "image"]
      - ["video", "cloud_generate", "video"]
      - ["seed", "cloud_generate", "seed"]
'''


def family_pipeline_yml(mode: str, fp: FamilyPipes) -> str:
    loras_config = ""
    if fp.has_loras:
        loras_config = """
      loras:
        "@loop":
          items: "{{ form.loras }}"
          template:
            file_path: "{{ item.model }}"
            weight: "{{ item.strength }}\""""
    slot_lines = "\n".join(
        f'      {slot}: {{ file_path: "{{{{ form.{slot} }}}}", name: "{{{{ form.{slot} }}}}" }}'
        for slot in fp.model_slots
    )
    te_input = (
        f'\n    - ["text_encoder", "{fp.loader_name}", "text_encoder"]'
        if fp.has_text_encoder_output else ""
    )
    param_lines = "\n".join(f'        - ["model", "{{{{ form.{slot} }}}}"]' for slot in fp.model_slots)
    return f"""# Pipeline for the '{mode}' mode - the standard native chain (see
# docs/presets/pipelines.md#the-standard-native-chain), wired to the real
# {fp.loader_name} / {fp.generator_name} pipes discovered from the pipe catalog.
#
# model_loader/{fp.family} -> prompt_encoder -> seed_generator -> dynamic_prompts_renderer
#   -> from_iotype -> param_emitter -> generator/{fp.family} -> gallery
pipeline:
  - name: "{fp.loader_name}"
    enabled: true
    configuration:
{slot_lines}{loras_config}

  - name: "prompt_encoder"
    input:{te_input}
    enabled: true
    configuration:
      p_prompt:
        input: "{{{{ generation.prompts.first.positive }}}}"
        output: "{{{{ generation.prompts.first.positive }}}}"
      n_prompt:
        input: "{{{{ generation.prompts.first.negative }}}}"
        output: "{{{{ generation.prompts.first.negative }}}}"
      pairs: "{{{{ generation.prompts.pairs }}}}"
      quantity: "{{{{ form.quantity }}}}"
      guidance_scale: "{{{{ form.{fp.guidance_key} }}}}"

  - name: "seed_generator"
    enabled: true
    configuration:
      seed: "{{{{ form.seed }}}}"
      quantity: "{{{{ form.quantity }}}}"

  - name: "dynamic_prompts_renderer"
    id: "dynamic_prompts_renderer"
    enabled: true
    configuration:
      pairs: "{{{{ generation.prompts.pairs }}}}"
      quantity: "{{{{ form.quantity }}}}"

  - name: "from_iotype"
    id: "from_iotype"
    enabled: true
    input:
      - ["seed", "seed_generator", "seed"]
    configuration:
      from: "seed"

  - name: "param_emitter"
    id: "param_emitter"
    enabled: true
    input:
      - ["seed", "from_iotype", "seed"]
    configuration:
      quantity: "{{{{ form.quantity }}}}"
      parameters:
{param_lines}
        - ["positive_prompt", "{{{{ generation.prompts.positives }}}}"]
        - ["negative_prompt", "{{{{ generation.prompts.negatives }}}}"]
        - ["{fp.guidance_key}", "{{{{ form.{fp.guidance_key} }}}}"]
        - ["steps", "{{{{ form.steps }}}}"]
        - ["sampler", "{{{{ form.sampler }}}}"]
        - ["resolution", "{{{{ form.resolution }}}}"]

  - name: "{fp.generator_name}"
    input:
      - ["model", "{fp.loader_name}", "model"]
      - ["conditioning", "prompt_encoder", "conditioning"]
      - ["seed", "seed_generator", "seed"]
    enabled: true
    configuration:
      steps: "{{{{ form.steps }}}}"
      {fp.guidance_key}: "{{{{ form.{fp.guidance_key} }}}}"
      sampler: "{{{{ form.sampler }}}}"
      resolution: "{{{{ form.resolution }}}}"
      quantity: "{{{{ form.quantity }}}}"

  - name: "gallery"
    input:
      - ["image", "{fp.generator_name}", "image"]
      - ["seed", "seed_generator", "seed"]
    enabled: true
"""


def family_form_yml(mode: str, fp: FamilyPipes) -> str:
    tabs = ['''      - type: "tab"
        label: "Generation"
        children: "{{ paths.preset }}/modes/''' + mode + '''/tabs/generation.yml"''']
    if fp.has_loras:
        tabs.append('''      - type: "tab"
        label: "LoRA"
        children: "{{ paths.preset }}/modes/''' + mode + '''/tabs/lora.yml"''')
    tabs.append('''      - type: "tab"
        label: "Advanced"
        audience: "advanced"
        children: "{{ paths.preset }}/modes/''' + mode + '''/tabs/advanced.yml"''')
    tabs_yaml = "\n".join(tabs)
    return f'''name: "custom"
fields:
  - type: "tabs"
    children:
{tabs_yaml}
'''


def family_generation_tab_yml(fp: FamilyPipes) -> str:
    model_fields = "\n\n".join(
        f'''  - name: "{slot}"
    type: "model"
    label: "{slot.replace('_', ' ').title()}"
    required: true
    configuration:
      model_type: "{slot}"
      placeholder: "Select a {fp.family} {slot.replace('_', ' ')}..."'''
        for slot in fp.model_slots
    )
    return f'''fields:
  - type: "row"
    children:
      - name: "seed"
        type: "seed"
        label: "Seed"
        default: -1
        width: "3/5"
      - name: "quantity"
        type: "stepper"
        label: "Quantity"
        default: 1
        configuration: {{min: 1, max: 10, step: 1}}
        width: "2/5"

  - name: "resolution"
    type: "resolution"
    label: "Resolution"
    configuration:
      files:
        - {{ path: "{{{{ paths._shared }}}}/resolutions/sdxl.yml", group: "Standard" }}
    default: "{fp.resolution_default}"

{model_fields}
'''


def family_lora_tab_yml() -> str:
    return '''fields:
  - name: "loras"
    type: "lora_picker"
    default: []
    label: "LoRAs"
    configuration:
      model_type: "lora"
      max_items: 6
'''


def family_advanced_tab_yml(fp: FamilyPipes) -> str:
    choices_yaml = "\n".join(
        f'        - {{ label: "{c.title()}", value: "{c}" }}' for c in fp.sampler_choices
    )
    return f'''fields:
  - name: "steps"
    type: "slider"
    label: "Steps"
    default: {fp.steps_default}
    configuration: {{min: 1, max: 150, step: 1}}

  - name: "sampler"
    type: "select"
    label: "Sampler"
    default: "{fp.sampler_default}"
    configuration:
      options:
{choices_yaml}

  - name: "{fp.guidance_key}"
    type: "slider"
    label: "{fp.guidance_key.upper() if fp.guidance_key == "cfg" else fp.guidance_key.title()}"
    default: {fp.guidance_default}
    configuration: {{min: 0, max: 30, step: 0.1}}
'''


def description_md(name: str) -> str:
    return f"# {name}\n\nDescribe what this preset generates and how to use it.\n"


def mode_files(mode: str, engine: str, family: Optional[FamilyPipes] = None) -> Dict[str, str]:
    base = f"modes/{mode}"
    if engine == "cloud":
        cloud_mode = CLOUD_MODES[mode]
        return {
            f"{base}/pipeline.yml": cloud_pipeline_yml(mode, cloud_mode),
            f"{base}/form.yml": with_short_description(mode, cloud_form_yml(cloud_mode)),
        }
    if family is not None and engine != "comfyui":
        produced = {
            f"{base}/pipeline.yml": family_pipeline_yml(mode, family),
            f"{base}/form.yml": with_short_description(mode, family_form_yml(mode, family)),
            f"{base}/tabs/generation.yml": family_generation_tab_yml(family),
        }
        if family.has_loras:
            produced[f"{base}/tabs/lora.yml"] = family_lora_tab_yml()
        produced[f"{base}/tabs/advanced.yml"] = family_advanced_tab_yml(family)
        return produced
    return {
        f"{base}/pipeline.yml": pipeline_yml(mode, engine),
        f"{base}/form.yml": with_short_description(mode, form_yml(mode)),
        f"{base}/tabs/main.yml": tab_yml(),
    }


def preset_files(*, preset_id: str, name: str, category: str, engine: str, modes: List[str],
                 driver: Optional[str] = None, family: Optional[FamilyPipes] = None) -> Dict[str, str]:
    formula_groups = cloud_formula_groups(modes) if engine == "cloud" else "  groups: {}\n"
    produced = {
        "preset.yml": preset_yml(preset_id, name, category, engine, modes, driver, formula_groups),
        "description.md": description_md(name),
    }
    for mode in modes:
        produced.update(mode_files(mode, engine, family))
    return produced


def write_files(target: Path, produced: Dict[str, str]) -> List[Path]:
    written = []
    for relative, content in produced.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
