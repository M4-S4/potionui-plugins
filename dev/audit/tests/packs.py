import hashlib
from pathlib import Path

from conftest import MISSING_SHA, WAN_VAE_SHA, png_bytes

PACK_TEMPLATE = """schema = 1
id = "potion-test"
version = "0.1.0"
seed = 12345

[cases]
file = "{cases_file}"
sha256 = "{cases_sha}"

[bible]
bottle = "a violet potion bottle"
look = "candlelight"

[prompts.image]
positive = "{{bottle}}, {{look}}"

[prompts.t2v]
positive = "slow push-in on {{bottle}}"

[prompts.song]
positive = "[Verse]\\nla la"
form = {{style = "folk, {{look}}"}}

[negatives]
plain = "blurry"

[inputs.bottle]
file = "inputs/bottle.png"
kind = "image"
width = 64
height = 64
sha256 = "{bottle_sha}"
size_bytes = {bottle_size}
origin = {{}}
license = "test"

[inputs.bottle.make]
method = "generate"
preset = "core/SDXL"
mode = "txt2img"
case = "sdxl-fast"
prompt = "image"
output = {{format = "png"}}

[inputs.mask]
file = "inputs/mask.png"
kind = "image"
width = 64
height = 64
sha256 = ""
size_bytes = 0
origin = {{}}
license = "code"

[inputs.mask.make]
method = "transform"
op = "rect_mask"
from = "bottle"
params = {{left = 0.25, top = 0.25, right = 0.75, bottom = 0.5}}

[[cells]]
preset = "core/SDXL"
mode = "txt2img"
case = "sdxl-fast"
prompt = "image"
negative = "plain"
profiles = ["smoke", "full"]

[[cells]]
preset = "core/Wan"
mode = "video"
case = "wan-t2v"
fix = "the text encoder sha256 of the case is not on the instance"
prompt = "t2v"
profiles = ["smoke", "full"]
repeat_warm = true
drop = ["resolution"]
models = {{text_encoder = {{sha256 = "{missing_sha}", alternatives = ["{vae_sha}"]}}}}
form = {{expert_boundary_preset = "0.875"}}

[[cells]]
preset = "core/SDXL"
mode = "txt2img"
variant = "edit"
prompt = "image"
seed = 7
models_from = "sdxl-fast"
form = {{steps = 4}}
bind = {{source_image = "bottle", source_image_inpaint_mask = "mask:path", "references[0]" = "bottle"}}
profiles = ["full"]
sources = {{form = "test defaults"}}

[[cells]]
preset = "core/ModelTools"
mode = "*"
exclude = "writes into the model store"
{extra}"""


def write_pack(tmp_path: Path, case_file: Path, extra: str = "", bottle: bool = True, replace: dict | None = None) -> Path:
    root = tmp_path / "pack"
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    data = png_bytes(size=(64, 64))
    if bottle:
        (root / "inputs" / "bottle.png").write_bytes(data)
    text = PACK_TEMPLATE.format(
        cases_file=case_file.as_posix(),
        cases_sha=hashlib.sha256(case_file.read_bytes()).hexdigest(),
        bottle_sha=hashlib.sha256(data).hexdigest() if bottle else "",
        bottle_size=len(data) if bottle else 0,
        missing_sha=MISSING_SHA,
        vae_sha=WAN_VAE_SHA,
        extra=extra,
    )
    for old, new in (replace or {}).items():
        assert old in text
        text = text.replace(old, new)
    path = root / "pack.toml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
