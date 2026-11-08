import json
import tomllib
from fractions import Fraction

import numpy as np
import pytest
from PIL import Image, JpegImagePlugin

from potion_audit.cli import main
from potion_audit.client import ApiClient
from potion_audit.inputs import Uploads, _encode, desaturate_video, edges, finish_output, make_inputs, rect_mask
from potion_audit.media import probe_video
from potion_audit.pack import PackError, file_sha, load_pack, verify
from potion_audit.run import RunRefused

from conftest import PASSWORD, USER, png_bytes
from packs import write_pack


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def logged_in(fake_api) -> ApiClient:
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    return client


def colour_video(path, frames=20, rate=10, size=(64, 48)):
    width, height = size
    arrays = []
    for index in range(frames):
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[..., 0] = 40 + index * 5
        array[..., 1] = 120
        array[..., 2] = 200
        arrays.append(array)
    _encode(arrays, path, Fraction(rate), width, height, 20)
    return path


def test_a_rectangle_mask_is_white_inside_the_box_only(tmp_path):
    source = tmp_path / "bottle.png"
    source.write_bytes(png_bytes(size=(100, 80)))
    target = tmp_path / "mask.png"
    rect_mask(source, target, {"left": 0.25, "top": 0.5, "right": 0.75, "bottom": 1.0})
    mask = np.asarray(Image.open(target))
    assert mask.shape == (80, 100)
    assert mask[60, 50] == 255
    assert mask[10, 50] == 0
    assert mask[60, 10] == 0


def test_an_edge_map_is_black_and_white_with_edges_on_shapes(tmp_path):
    image = Image.new("RGB", (64, 64), (0, 0, 0))
    image.paste((255, 255, 255), (16, 16, 48, 48))
    source = tmp_path / "square.png"
    image.save(source)
    target = tmp_path / "edges.png"
    edges(source, target, {"blur": 0.5, "threshold": 32})
    values = np.asarray(Image.open(target).convert("L"))
    assert set(np.unique(values)) <= {0, 255}
    assert values[16, 32] == 255
    assert values[32, 32] == 0


def test_a_desaturated_video_keeps_size_rate_and_frames(tmp_path):
    source = colour_video(tmp_path / "clip.mp4")
    target = tmp_path / "gray.mp4"
    desaturate_video(source, target, {"crf": 18})
    before = probe_video(source)
    after = probe_video(target)
    assert (after["width"], after["height"], after["fps"], after["decoded_frames"]) == (before["width"], before["height"], before["fps"], before["decoded_frames"])
    import av

    with av.open(str(target)) as container:
        frame = next(container.decode(video=0)).to_ndarray(format="rgb24").astype(int)
    assert abs(frame[..., 0] - frame[..., 2]).max() <= 8


def test_a_generated_video_is_cut_to_the_seconds_of_the_input(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    spec = pack.inputs["bottle"].__class__(**{**pack.inputs["bottle"].__dict__, "kind": "video", "seconds": 1.0, "width": 64, "height": 48, "make": {"method": "generate", "output": {"crf": 20}}})
    produced = colour_video(tmp_path / "produced.mp4", frames=20, rate=10)
    target = tmp_path / "clip.mp4"
    finish_output(spec, produced, target)
    assert probe_video(target)["decoded_frames"] == 10
    short = spec.__class__(**{**spec.__dict__, "seconds": 5.0})
    with pytest.raises(PackError, match="5.0 s needs 50"):
        finish_output(short, produced, tmp_path / "too-short.mp4")


def test_a_generated_image_of_the_wrong_size_is_refused(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    produced = tmp_path / "out.png"
    produced.write_bytes(png_bytes(size=(32, 32)))
    with pytest.raises(PackError, match="the pack expects 64x64"):
        finish_output(pack.inputs["bottle"], produced, tmp_path / "bottle.jpg")


def test_a_generated_image_is_saved_as_jpeg_at_quality_92_without_chroma_subsampling(tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    spec = pack.inputs["bottle"].__class__(**{**pack.inputs["bottle"].__dict__, "make": {"method": "generate", "output": {"format": "jpeg", "quality": 92}}})
    produced = tmp_path / "out.png"
    produced.write_bytes(png_bytes(size=(64, 64)))
    target = tmp_path / "bottle.jpg"
    finish_output(spec, produced, target)
    reference = tmp_path / "reference.jpg"
    Image.open(produced).convert("RGB").save(reference, format="JPEG", quality=92, subsampling=0, optimize=True)
    with Image.open(target) as image:
        assert (image.format, image.size) == ("JPEG", (64, 64))
        assert JpegImagePlugin.get_sampling(image) == 0
    assert target.read_bytes() == reference.read_bytes()


def test_an_input_is_uploaded_once_per_sha_and_run(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    record = tmp_path / "run" / "uploads.json"
    uploads = Uploads(logged_in(fake_api), record)
    first = uploads.media(pack, "bottle", False)
    second = uploads.media(pack, "bottle", True)
    again = Uploads(logged_in(fake_api), record).media(pack, "bottle", False)
    assert fake_api.uploads == ["bottle.png"]
    assert first == second == again
    assert first["path"] == "storage/uploads/1-bottle.png"
    assert first["relative_path"] == "uploads/1-bottle.png"
    assert (first["type"], first["name"]) == ("image", "bottle.png")


def test_an_input_that_does_not_match_its_sha_is_not_uploaded(fake_api, tmp_path, case_file):
    pack = load_pack(write_pack(tmp_path, case_file))
    pack.input_path("bottle").write_bytes(png_bytes(color=(1, 2, 3), size=(64, 64)))
    with pytest.raises(RunRefused, match="does not match"):
        Uploads(logged_in(fake_api), tmp_path / "uploads.json").media(pack, "bottle", False)
    with pytest.raises(RunRefused, match="not made yet"):
        Uploads(logged_in(fake_api), tmp_path / "uploads.json").media(pack, "mask", False)
    assert fake_api.uploads == []


def test_make_inputs_is_refused_without_confirm_gpu(fake_api, config_file, credentials_env, tmp_path, case_file, capsys):
    path = write_pack(tmp_path, case_file)
    code = main(["pack", "make-inputs", "--pack", str(path), "--config", str(config_file)])
    assert code == 2
    assert fake_api.requests == []
    assert "--confirm-gpu" in capsys.readouterr().err


def test_the_transforms_run_without_the_instance_and_record_their_facts(tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    code = main(["pack", "make-inputs", "--pack", str(path), "--transforms-only", "--config", str(tmp_path / "none.toml")])
    assert code == 0
    data = tomllib.loads(path.read_text(encoding="utf-8"))["inputs"]["mask"]
    assert data["sha256"] == file_sha(tmp_path / "pack" / "inputs" / "mask.png")
    assert data["size_bytes"] == (tmp_path / "pack" / "inputs" / "mask.png").stat().st_size
    assert data["origin"]["op"] == "rect_mask"
    assert data["origin"]["from_sha256"] == tomllib.loads(path.read_text(encoding="utf-8"))["inputs"]["bottle"]["sha256"]
    assert [problem for problem in verify(load_pack(path)) if problem.severity == "error"] == []


def test_make_inputs_generates_then_transforms_and_writes_the_pack(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, bottle=False)
    fake_api.outputs = {"0.png": png_bytes(color=(90, 20, 160), size=(64, 64))}
    clock = FakeClock()
    lines = []
    made = make_inputs(load_pack(path), logged_in(fake_api), tmp_path / "out", "inputs-1", clock=clock, sleep=clock.sleep, log=lines.append)
    assert [item["id"] for item in made] == ["bottle", "mask"]
    assert len(fake_api.started) == 1
    request = fake_api.started[0]
    assert request["prompts"][0]["positive"] == "a violet potion bottle, candlelight"
    assert request["form_data"]["model"] == "model:M-SDXL"
    data = tomllib.loads(path.read_text(encoding="utf-8"))["inputs"]
    assert data["bottle"]["origin"]["generation_id"] == "G1"
    assert data["bottle"]["origin"]["app_version"] == "9.9.9"
    assert data["bottle"]["sha256"] == file_sha(tmp_path / "pack" / "inputs" / "bottle.png")
    assert data["mask"]["origin"]["from_sha256"] == data["bottle"]["sha256"]
    assert [problem for problem in verify(load_pack(path)) if problem.severity == "error"] == []
    assert (tmp_path / "out" / "inputs-1" / "inputs" / "bottle" / "result.json").exists()


def test_a_generation_bound_to_another_input_uploads_it_first(fake_api, tmp_path, case_file):
    extra = '''
[inputs.bottle-gold]
file = "inputs/bottle-gold.png"
kind = "image"
width = 64
height = 64
sha256 = ""
size_bytes = 0
origin = {}
license = "test"

[inputs.bottle-gold.make]
method = "generate"
preset = "core/SDXL"
mode = "txt2img"
models_from = "sdxl-fast"
prompt = "image"
seed = 3
bind = {source_image = "bottle"}
output = {format = "png"}
sources = {form = "test"}
'''
    path = write_pack(tmp_path, case_file, replace={"[[cells]]\npreset = \"core/SDXL\"\nmode = \"txt2img\"\ncase = \"sdxl-fast\"": extra.strip() + "\n\n[[cells]]\npreset = \"core/SDXL\"\nmode = \"txt2img\"\ncase = \"sdxl-fast\""})
    clock = FakeClock()
    made = make_inputs(load_pack(path), logged_in(fake_api), tmp_path / "out", "inputs-2", only="bottle-gold", clock=clock, sleep=clock.sleep, log=lambda line: None)
    assert [item["id"] for item in made] == ["bottle-gold"]
    assert fake_api.uploads == ["bottle.png"]
    source = fake_api.started[0]["form_data"]["source_image"]
    assert source["path"] == "storage/uploads/1-bottle.png"
    assert fake_api.started[0]["form_data"]["seed"] == 3


def test_a_failed_generation_leaves_the_pack_unchanged(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, bottle=False)
    before = path.read_text(encoding="utf-8")
    fake_api.final = "failed"
    clock = FakeClock()
    with pytest.raises(RunRefused, match="ended with FAIL"):
        make_inputs(load_pack(path), logged_in(fake_api), tmp_path / "out", "inputs-3", clock=clock, sleep=clock.sleep, log=lambda line: None)
    assert path.read_text(encoding="utf-8") == before


def test_a_busy_queue_stops_make_inputs_before_submitting(fake_api, tmp_path, case_file):
    path = write_pack(tmp_path, case_file, bottle=False)
    fake_api.queue = {"pending": [], "running": [{"id": "X"}]}
    with pytest.raises(RunRefused, match="queue is busy"):
        make_inputs(load_pack(path), logged_in(fake_api), tmp_path / "out", "inputs-4", log=lambda line: None)
    assert fake_api.started == []


def test_a_profile_dry_run_writes_the_plan_and_submits_nothing(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    code = main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "full", "--dry-run", "--run-id", "plan-1"])
    assert code == 0
    assert fake_api.started == [] and fake_api.uploads == []
    assert all(method == "GET" for method, route in fake_api.methods() if route != "/api/auth/login")
    plan = json.loads((tmp_path / "out" / "plan-1" / "plan.json").read_text(encoding="utf-8"))
    rows = [(entry["cell"], entry["warm_repeat"], entry["status"], entry["estimate_seconds"]) for entry in plan["cells"]]
    assert rows == [
        ("core/SDXL:txt2img", False, "ready", 30.0),
        ("core/SDXL:txt2img/edit", False, "input_pending", 10.0),
        ("core/Wan:video", False, "beyond_tier", None),
        ("core/Wan:video", True, "beyond_tier", None),
    ]
    assert plan["summary"]["planned"] == 2
    assert plan["summary"]["estimated_seconds"] == 40.0
    request = json.loads((tmp_path / "out" / "plan-1" / "cells" / "core-SDXL--txt2img-edit" / "request.json").read_text(encoding="utf-8"))
    assert request["form_data"]["source_image"] == "input:bottle"


def test_a_dry_run_plans_beyond_tier_cells_when_asked(fake_api, config_file, credentials_env, tmp_path, case_file):
    path = write_pack(tmp_path, case_file)
    code = main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "smoke", "--dry-run", "--run-id", "plan-2", "--beyond-tier"])
    assert code == 0
    plan = json.loads((tmp_path / "out" / "plan-2" / "plan.json").read_text(encoding="utf-8"))
    assert [(entry["cell"], entry["status"]) for entry in plan["cells"]] == [("core/SDXL:txt2img", "ready"), ("core/Wan:video", "ready_beyond_tier")]
    wan = json.loads((tmp_path / "out" / "plan-2" / "cells" / "core-Wan--video" / "request.json").read_text(encoding="utf-8"))
    assert wan["form_data"]["video_director"]["mode"] == "t2v"


def test_a_pack_profile_is_refused_without_dry_run(fake_api, config_file, credentials_env, tmp_path, case_file, capsys):
    path = write_pack(tmp_path, case_file)
    code = main(["run", "--config", str(config_file), "--pack", str(path), "--profile", "smoke", "--confirm-gpu"])
    assert code == 2
    assert fake_api.requests == []
    assert "--dry-run" in capsys.readouterr().err
