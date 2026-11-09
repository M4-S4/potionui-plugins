import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageFilter

from . import __version__
from .client import ApiClient, unwrap
from .coverage import ModelResolver, live_state
from .pack import InputSpec, Pack, PackError, build_cell_request, cell_checks, cell_models, file_sha, load_pack, make_cell, set_input_facts
from .run import RunRefused, ensure_idle, runner_info, submit_and_collect

CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".mp4": "video/mp4", ".wav": "audio/wav"}
MAKE_TIMEOUT = 1800.0


class Uploads:
    def __init__(self, client: ApiClient, record: Path):
        self.client = client
        self.record = record
        self.done = json.loads(record.read_text(encoding="utf-8")) if record.exists() else {}

    def media(self, pack: Pack, input_id: str, as_path: bool):
        spec = pack.inputs[input_id]
        if spec.pending:
            raise RunRefused(f"input {input_id} is not made yet")
        path = pack.input_path(input_id)
        sha = file_sha(path)
        if sha != spec.sha256:
            raise RunRefused(f"input {input_id}: {spec.file} does not match the sha256 in the pack, run pack verify")
        if sha not in self.done:
            data = unwrap(self.client.upload("/api/media/upload", path, CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"))) or {}
            if not data.get("path"):
                raise RunRefused(f"uploading {spec.file} gave no path")
            self.done[sha] = {key: data.get(key) for key in ("path", "relative_path", "url", "filename", "id", "width", "height", "duration_seconds", "fps", "size")}
            self.record.parent.mkdir(parents=True, exist_ok=True)
            self.record.write_text(json.dumps(self.done, indent=1) + "\n", encoding="utf-8", newline="\n")
        return media_item(self.done[sha], spec)


def media_item(data: dict, spec: InputSpec) -> dict:
    return {
        "path": data["path"],
        "relative_path": data.get("relative_path") or data["path"],
        "url": data.get("url"),
        "name": Path(spec.file).name,
        "type": spec.kind,
        "metadata": {key: data.get(key) for key in ("width", "height", "duration_seconds", "fps", "size")},
    }


def rect_mask(source: Path, target: Path, params: dict) -> None:
    with Image.open(source) as image:
        width, height = image.size
    box = tuple(round(float(params[key]) * size) for key, size in (("left", width), ("top", height), ("right", width), ("bottom", height)))
    mask = Image.new("L", (width, height), 0)
    mask.paste(255, box)
    mask.save(target, format="PNG", optimize=True)


def edges(source: Path, target: Path, params: dict) -> None:
    threshold = int(params.get("threshold", 32))
    with Image.open(source) as image:
        gray = image.convert("L").filter(ImageFilter.GaussianBlur(float(params.get("blur", 1.5))))
    found = gray.filter(ImageFilter.FIND_EDGES).point(lambda value: 255 if value >= threshold else 0)
    found.convert("RGB").save(target, format="PNG", optimize=True)


def _encode(frames, target: Path, rate: Fraction, width: int, height: int, crf: int) -> int:
    count = 0
    with av.open(str(target), "w", options={"movflags": "+faststart"}) as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.time_base = 1 / rate
        stream.codec_context.time_base = 1 / rate
        stream.options = {"crf": str(crf), "preset": "medium", "threads": "1"}
        for array in frames:
            frame = av.VideoFrame.from_ndarray(array, format="rgb24").reformat(format="yuv420p")
            frame.pts = count
            frame.time_base = stream.codec_context.time_base
            for packet in stream.encode(frame):
                container.mux(packet)
            count += 1
        for packet in stream.encode(None):
            container.mux(packet)
    return count


def _frames(source: Path, seconds: float | None, height: int | None):
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        rate = Fraction(stream.average_rate or stream.guessed_rate or 16)
        limit = round(seconds * rate) if seconds else None
        width = stream.codec_context.width
        out_height = stream.codec_context.height
        if height and out_height != height:
            width = int(round(width * height / out_height / 2)) * 2
            out_height = height
        frames = []
        for frame in container.decode(stream):
            if limit is not None and len(frames) >= limit:
                break
            frames.append(frame.reformat(width=width, height=out_height, format="rgb24").to_ndarray())
    return frames, rate, width, out_height


def desaturate_video(source: Path, target: Path, params: dict) -> None:
    frames, rate, width, height = _frames(source, None, None)
    gray = []
    for array in frames:
        luma = np.clip(array[..., 0] * 0.299 + array[..., 1] * 0.587 + array[..., 2] * 0.114, 0, 255).astype(np.uint8)
        gray.append(np.repeat(luma[..., None], 3, axis=2))
    _encode(gray, target, rate, width, height, int(params.get("crf", 20)))


def transform(pack: Pack, spec: InputSpec, target: Path) -> dict:
    op = spec.make.get("op")
    params = dict(spec.make.get("params") or {})
    parent = pack.inputs.get(spec.make.get("from"))
    if parent is None:
        raise PackError(f"input {spec.id}: make.from names no input")
    source = pack.input_path(parent.id)
    if parent.pending or file_sha(source) != parent.sha256:
        raise PackError(f"input {spec.id} needs {parent.id} made and verified first")
    if op == "rect_mask":
        rect_mask(source, target, params)
    elif op == "edges":
        edges(source, target, params)
    elif op == "desaturate_video":
        desaturate_video(source, target, params)
    else:
        raise PackError(f"input {spec.id}: unknown transform {op!r}")
    return {"method": "transform", "op": op, "made_at": datetime.now(UTC).isoformat(timespec="seconds"), "potion_audit": __version__, "from_sha256": parent.sha256}


def finish_output(spec: InputSpec, produced: Path, target: Path) -> None:
    output = dict(spec.make.get("output") or {})
    if spec.kind == "image":
        with Image.open(produced) as image:
            if spec.width and spec.height and image.size != (spec.width, spec.height):
                raise PackError(f"input {spec.id}: the generation is {image.size[0]}x{image.size[1]}, the pack expects {spec.width}x{spec.height}")
            picture = image.convert("RGB")
        if output.get("format", "jpeg") == "jpeg":
            picture.save(target, format="JPEG", quality=int(output.get("quality", 92)), subsampling=0, optimize=True)
        else:
            picture.save(target, format="PNG", optimize=True)
    elif spec.kind == "video":
        frames, rate, width, height = _frames(produced, spec.seconds, output.get("height"))
        if spec.seconds and len(frames) < round(spec.seconds * rate):
            raise PackError(f"input {spec.id}: the generation has {len(frames)} frames, {spec.seconds} s needs {round(spec.seconds * rate)}")
        _encode(frames, target, rate, width, height, int(output.get("crf", 20)))
    else:
        raise PackError(f"input {spec.id}: a generated {spec.kind} input is not supported")


def _produced(result: dict, case_dir: Path, kind: str) -> Path:
    for output in result.get("outputs") or ():
        if output.get("kind") == kind:
            return case_dir / output["file"]
    raise PackError(f"the generation gave no {kind} output")


def input_checks(pack: Pack, cell, spec: InputSpec) -> dict:
    checks = dict(cell_checks(pack, cell))
    if "resolution" in checks and spec.width and spec.height:
        checks["resolution"] = f"{spec.width}x{spec.height}"
    return checks


def already_made(pack: Pack, spec: InputSpec) -> bool:
    path = pack.root / spec.file
    return not spec.pending and path.is_file() and file_sha(path) == spec.sha256


def make_order(pack: Pack, only: str | None, transforms_only: bool) -> list[InputSpec]:
    specs = sorted(pack.inputs.values(), key=lambda spec: spec.position)
    generated = [spec for spec in specs if spec.make.get("method") == "generate"]
    transformed = [spec for spec in specs if spec.make.get("method") == "transform"]
    order = transformed if transforms_only else generated + transformed
    if only:
        order = [spec for spec in order if spec.id == only]
        if not order:
            raise PackError(f"no input {only!r} to make")
    return order


def make_inputs(pack: Pack, client: ApiClient | None, out_root: Path, run_id: str, *, only: str | None = None, transforms_only: bool = False, timeout: float | None = None, interval: float = 2.0, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> list[dict]:
    order = make_order(pack, only, transforms_only)
    if not only:
        skipped = [spec for spec in order if spec.make.get("method") == "generate" and already_made(pack, spec)]
        for spec in skipped:
            log(f"input {spec.id}: already made, sha256 {spec.sha256}, skipped")
        order = [spec for spec in order if spec not in skipped]
    needs_gpu = any(spec.make.get("method") == "generate" for spec in order)
    if needs_gpu and client is None:
        raise RunRefused("generated inputs need the instance")
    run_dir = out_root / run_id
    uploads = Uploads(client, run_dir / "uploads.json") if client else None
    live = live_state(client) if needs_gpu else None
    resolver = ModelResolver(client) if needs_gpu else None
    app_version = ((client.get_json("/openapi.json") or {}).get("info") or {}).get("version") if needs_gpu else None
    made = []
    for spec in order:
        target = pack.root / spec.file
        target.parent.mkdir(parents=True, exist_ok=True)
        if spec.make.get("method") == "generate":
            ensure_idle(client)
            cell = make_cell(spec, pack.case_set)
            model_ids = {}
            for ref in cell_models(pack, cell):
                found = resolver.resolve(ref, cell.preset_id)
                if not found["present"]:
                    raise RunRefused(f"input {spec.id}: model {ref.field} ({ref.filename or ref.sha256}) is not on the instance")
                model_ids[ref.field] = found["found"]["model_id"]
            current = load_current(pack)
            request = build_cell_request(current, cell, model_ids, live.presets.get(cell.preset_id) or {}, f"{run_id}-{spec.id}", lambda input_id, as_path: uploads.media(current, input_id, as_path))
            case_dir = run_dir / "inputs" / spec.id
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "request.json").write_text(json.dumps(request, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            head = {"schema": 1, "run_id": run_id, "input": spec.id, "pack": {"id": pack.id, "sha256": pack.sha256}, "runner": runner_info()}
            result = submit_and_collect(client, request, cell.preset_id, input_checks(pack, cell, spec), case_dir, head, f"input {spec.id}", timeout or MAKE_TIMEOUT, interval, clock, sleep, log)
            if result["verdict"] != "PASS":
                raise RunRefused(f"input {spec.id}: the generation ended with {result['verdict']}, see {case_dir / 'result.json'}")
            finish_output(spec, _produced(result, case_dir, spec.kind), target)
            origin = {
                "method": "generate",
                "preset": cell.preset_ref,
                "mode": cell.mode,
                "generation_id": result["generation_id"],
                "app_version": app_version,
                "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        else:
            origin = transform(load_current(pack), spec, target)
        facts = {"sha256": file_sha(target), "size_bytes": target.stat().st_size, "origin": origin}
        text = pack.path.read_text(encoding="utf-8")
        pack.path.write_text(set_input_facts(text, spec.id, facts), encoding="utf-8", newline="\n")
        log(f"input {spec.id}: {spec.file}, {facts['size_bytes']} bytes, sha256 {facts['sha256']}")
        made.append({"id": spec.id, **facts})
    return made


def load_current(pack: Pack) -> Pack:
    return load_pack(pack.path)
