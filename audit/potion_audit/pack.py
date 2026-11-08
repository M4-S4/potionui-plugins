import copy
import hashlib
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .cases import ZERO_SHA, Case, CaseFileError, CaseSet, ModelRef, load_cases

PACK_SCHEMA = 1
PROFILES = ("smoke", "full")
INPUT_KINDS = ("image", "video", "audio")
MAKE_METHODS = ("generate", "transform")
TRANSFORM_OPS = ("rect_mask", "edges", "desaturate_video")
PLACEHOLDER = "PLACEHOLDER/"
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
TEMPLATE_FIELD = re.compile(r"\{([a-z0-9_]+)\}")
BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")
PATH_STEP = re.compile(r"([A-Za-z0-9_]+)((?:\[[0-9]+\])*)")
DEFAULT_PACK = Path(__file__).resolve().parent.parent / "pack" / "v1" / "pack.toml"
CELL_KEYS = {
    "preset", "mode", "variant", "case", "fix", "prompt", "negative", "seed", "form", "drop", "bind", "models",
    "drop_models", "models_from", "profiles", "repeat_warm", "requires_plugin", "checks", "sources", "exclude", "notes",
}
MAKE_KEYS = CELL_KEYS | {"method", "op", "from", "params", "output", "license"}
INPUT_KEYS = {"file", "kind", "width", "height", "seconds", "sha256", "size_bytes", "license", "origin", "make"}


class PackError(ValueError):
    pass


@dataclass(frozen=True)
class Binding:
    input_id: str
    as_path: bool


@dataclass(frozen=True)
class Cell:
    preset_ref: str
    preset_id: str
    preset_key: str
    mode: str
    variant: str | None
    case: str | None
    fix: str | None
    prompt: str | None
    negative: str | None
    seed: int | None
    form: dict
    drop: tuple[str, ...]
    bind: dict
    models: dict
    drop_models: tuple[str, ...]
    models_from: str | None
    profiles: tuple[str, ...]
    repeat_warm: bool
    requires_plugin: str | None
    checks: dict | None
    sources: dict
    exclude: str | None
    notes: str | None
    position: int

    @property
    def id(self) -> str:
        suffix = f"/{self.variant}" if self.variant else ""
        return f"{self.preset_ref}:{self.mode}{suffix}"

    @property
    def status(self) -> str:
        if self.exclude:
            return "excluded"
        if self.case is None:
            return "new"
        return "corrected" if self.fix else "case"


@dataclass(frozen=True)
class InputSpec:
    id: str
    file: str
    kind: str
    width: int | None
    height: int | None
    seconds: float | None
    sha256: str
    size_bytes: int
    license: str | None
    origin: dict
    make: dict
    position: int

    @property
    def pending(self) -> bool:
        return not self.sha256


@dataclass(frozen=True)
class Pack:
    path: Path
    sha256: str
    id: str
    version: str
    seed: int
    cases_sha256: str
    case_set: CaseSet
    bible: dict
    prompts: dict
    negatives: dict
    inputs: dict
    cells: tuple[Cell, ...]

    @property
    def root(self) -> Path:
        return self.path.parent

    def input_path(self, input_id: str) -> Path:
        return self.root / self.inputs[input_id].file

    def preset(self, ref: str) -> dict | None:
        return preset_by_ref(self.case_set, ref)

    def case(self, cell: Cell, name: str | None = None) -> Case | None:
        wanted = name or cell.case
        if wanted is None:
            return None
        for case in self.case_set.cases:
            if case.preset_id == cell.preset_id and case.name == wanted:
                return case
        return None


def preset_ref(preset: dict) -> str:
    return f"{preset['origin']}/{preset['key']}"


def preset_by_ref(case_set: CaseSet, ref: str) -> dict | None:
    for preset in case_set.presets:
        if preset_ref(preset) == ref or preset["id"] == ref:
            return preset
    return None


def _binding(value) -> Binding:
    text = str(value)
    input_id, _, kind = text.partition(":")
    if kind not in ("", "path"):
        raise PackError(f"binding {text!r}: the only suffix is ':path'")
    return Binding(input_id, kind == "path")


def _cell(raw: dict, case_set: CaseSet, position: int, keys: set[str]) -> Cell:
    unknown = sorted(set(raw) - keys)
    if unknown:
        raise PackError(f"cell {raw.get('preset')}:{raw.get('mode')} has unknown keys: {', '.join(unknown)}")
    ref = str(raw.get("preset") or "")
    preset = preset_by_ref(case_set, ref)
    if preset is None:
        raise PackError(f"cell {ref}:{raw.get('mode')}: no preset {ref!r} in {case_set.path.name}")
    profiles = tuple(raw.get("profiles") or ())
    return Cell(
        preset_ref=preset_ref(preset),
        preset_id=preset["id"],
        preset_key=preset["key"],
        mode=str(raw.get("mode") or ""),
        variant=raw.get("variant"),
        case=raw.get("case"),
        fix=raw.get("fix"),
        prompt=raw.get("prompt"),
        negative=raw.get("negative"),
        seed=raw.get("seed"),
        form=dict(raw.get("form") or {}),
        drop=tuple(raw.get("drop") or ()),
        bind={path: _binding(value) for path, value in (raw.get("bind") or {}).items()},
        models=dict(raw.get("models") or {}),
        drop_models=tuple(raw.get("drop_models") or ()),
        models_from=raw.get("models_from"),
        profiles=profiles,
        repeat_warm=bool(raw.get("repeat_warm")),
        requires_plugin=raw.get("requires_plugin"),
        checks=dict(raw["checks"]) if "checks" in raw else None,
        sources=dict(raw.get("sources") or {}),
        exclude=raw.get("exclude"),
        notes=raw.get("notes"),
        position=position,
    )


def make_cell(spec: InputSpec, case_set: CaseSet) -> Cell:
    if spec.make.get("method") != "generate":
        raise PackError(f"input {spec.id} is not generated")
    raw = {key: value for key, value in spec.make.items() if key in CELL_KEYS}
    raw.setdefault("profiles", [])
    return _cell(raw, case_set, spec.position, CELL_KEYS)


def load_pack(path: Path) -> Pack:
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError:
        raise PackError(f"{path} does not exist") from None
    try:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise PackError(f"{path} is not valid TOML: {error}") from error
    if data.get("schema") != PACK_SCHEMA:
        raise PackError(f"{path} has schema {data.get('schema')!r}, expected {PACK_SCHEMA}")
    cases = data.get("cases") or {}
    if not cases.get("file"):
        raise PackError("[cases] file is missing")
    cases_path = (path.parent / cases["file"]).resolve()
    try:
        case_set = load_cases(cases_path)
    except FileNotFoundError:
        raise PackError(f"the case file {cases_path.name} does not exist") from None
    except CaseFileError as error:
        raise PackError(str(error)) from error
    inputs = {}
    for position, (input_id, entry) in enumerate((data.get("inputs") or {}).items()):
        unknown = sorted(set(entry) - INPUT_KEYS)
        if unknown:
            raise PackError(f"input {input_id} has unknown keys: {', '.join(unknown)}")
        inputs[input_id] = InputSpec(
            id=input_id,
            file=str(entry.get("file") or ""),
            kind=str(entry.get("kind") or ""),
            width=entry.get("width"),
            height=entry.get("height"),
            seconds=entry.get("seconds"),
            sha256=str(entry.get("sha256") or "").lower(),
            size_bytes=int(entry.get("size_bytes") or 0),
            license=entry.get("license"),
            origin=dict(entry.get("origin") or {}),
            make=dict(entry.get("make") or {}),
            position=position,
        )
    cells = tuple(_cell(raw, case_set, position, CELL_KEYS) for position, raw in enumerate(data.get("cells") or ()))
    return Pack(
        path=path.resolve(),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        id=str(data.get("id") or ""),
        version=str(data.get("version") or ""),
        seed=int(data.get("seed", 12345)),
        cases_sha256=str(cases.get("sha256") or "").lower(),
        case_set=case_set,
        bible=dict(data.get("bible") or {}),
        prompts=dict(data.get("prompts") or {}),
        negatives=dict(data.get("negatives") or {}),
        inputs=inputs,
        cells=cells,
    )


def expand(pack: Pack, text: str) -> str:
    def replace(match):
        key = match.group(1)
        if key not in pack.bible:
            raise PackError(f"the template {text[:40]!r} names {{{key}}}, which the bible does not define")
        return str(pack.bible[key])

    return TEMPLATE_FIELD.sub(replace, text)


def prompt_entry(pack: Pack, key: str) -> tuple[str, dict]:
    if key not in pack.prompts:
        raise PackError(f"no prompt {key!r} in the pack")
    entry = pack.prompts[key]
    extra = {name: expand(pack, value) if isinstance(value, str) else value for name, value in (entry.get("form") or {}).items()}
    return expand(pack, str(entry.get("positive") or "")), extra


def cell_models(pack: Pack, cell: Cell) -> list[ModelRef]:
    case = pack.case(cell)
    refs = {ref.field: ref for ref in case.models} if case else {}
    if cell.models_from:
        source = pack.case(cell, cell.models_from)
        if source is None:
            raise PackError(f"{cell.id}: models_from names no case {cell.models_from!r} of {cell.preset_ref}")
        for ref in source.models:
            refs.setdefault(ref.field, ref)
    for field in cell.drop_models:
        refs.pop(field, None)
    for field, value in cell.models.items():
        if isinstance(value, dict) and value.get("sha256"):
            refs[field] = ModelRef(field, str(value["sha256"]).lower(), None, value.get("filename"), "pack", tuple(str(item).lower() for item in value.get("alternatives") or ()))
        elif isinstance(value, dict):
            refs[field] = ModelRef(field, ZERO_SHA, None, str(value.get("filename") or ""), "pack: file name")
        else:
            refs[field] = ModelRef(field, str(value).lower(), None, None, "pack")
    return list(refs.values())


def _steps(path: str) -> list:
    steps = []
    for part in path.split("."):
        match = PATH_STEP.fullmatch(part)
        if not match:
            raise PackError(f"binding path {path!r} is not <field>[<index>].<key>")
        steps.append(match.group(1))
        steps.extend(int(index) for index in re.findall(r"\[([0-9]+)\]", match.group(2)))
    return steps


def _place(form: dict, path: str, value, as_path: bool) -> None:
    steps = _steps(path)
    node = form
    for step, following in zip(steps, steps[1:]):
        if isinstance(step, int):
            while len(node) <= step:
                node.append({} if isinstance(following, str) else [])
            node = node[step]
        else:
            if not isinstance(node.get(step), (dict, list)):
                node[step] = [] if isinstance(following, int) else {}
            node = node[step]
    last = steps[-1]
    if isinstance(last, int):
        while len(node) <= last:
            node.append(None)
        current = node[last]
    else:
        current = node.get(last)
    if as_path or not isinstance(value, dict):
        placed = value["path"] if isinstance(value, dict) else value
    elif isinstance(current, dict):
        placed = {**current, **{key: value[key] for key in ("path", "relative_path") if key in value}}
    else:
        placed = value
    if isinstance(last, int):
        node[last] = placed
    else:
        node[last] = placed


def placeholders(node, trail: str = "") -> list[str]:
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.extend(placeholders(value, f"{trail}.{key}" if trail else key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(placeholders(value, f"{trail}[{index}]"))
    elif isinstance(node, str) and node.startswith(PLACEHOLDER):
        found.append(trail)
    return found


def director_document(form: dict, prompt: str, negative: str, limits: dict) -> dict:
    settings = {"duration": float(form.get("duration") or limits.get("default_duration") or 5.0)}
    fps = form.get("fps") or limits.get("default_fps")
    if fps:
        settings["fps"] = fps
    if isinstance(form.get("seed"), int):
        settings["seed"] = form["seed"]
    return {
        "schema_version": 1,
        "mode": "t2v",
        "settings": settings,
        "segments": [{"id": "shot-1", "prompt": prompt, "negative_prompt": negative}],
        "media": [],
    }


def merged_form(pack: Pack, cell: Cell) -> tuple[dict, str, str]:
    case = pack.case(cell)
    form = copy.deepcopy(case.form) if case else {}
    for key in cell.drop:
        form.pop(key, None)
    case_prompt = str(form.pop("prompt", "") or "")
    form.pop("negative_prompt", None)
    prompt = case_prompt
    if cell.prompt:
        prompt, extra = prompt_entry(pack, cell.prompt)
        form.update(extra)
    negative = ""
    if cell.negative:
        if cell.negative not in pack.negatives:
            raise PackError(f"{cell.id}: no negative prompt {cell.negative!r} in the pack")
        negative = expand(pack, str(pack.negatives[cell.negative]))
    form.update(copy.deepcopy(cell.form))
    if cell.seed is not None:
        form["seed"] = cell.seed
    elif case is not None and case.seed is not None:
        form["seed"] = pack.seed
    return form, prompt, negative


def build_cell_request(pack: Pack, cell: Cell, model_ids: dict[str, str], preset_detail: dict, run_id: str, media: Callable[[str, bool], object]) -> dict:
    form, prompt, negative = merged_form(pack, cell)
    for field, value in model_ids.items():
        form[field] = value if value.startswith("model:") else f"model:{value}"
    for path, binding in cell.bind.items():
        if binding.input_id not in pack.inputs:
            raise PackError(f"{cell.id}: binding {path} names no input {binding.input_id!r}")
        _place(form, path, media(binding.input_id, binding.as_path), binding.as_path)
    director = (preset_detail.get("vars") or {}).get("video_director") or {}
    director_modes = director.get("preset_modes") or (["video"] if director else [])
    document = form.get("video_director")
    if isinstance(document, dict):
        for segment in document.get("segments") or ():
            segment["prompt"] = prompt
            segment["negative_prompt"] = negative
    elif director and cell.mode in director_modes:
        if not prompt:
            raise PackError(f"{cell.id} needs a prompt to build its Video Director document")
        form["video_director"] = director_document(form, prompt, negative, director.get("limits") or {})
    left = placeholders(form)
    if left:
        raise PackError(f"{cell.id}: {', '.join(left)} still hold a PLACEHOLDER value: bind them to an input")
    return {
        "preset_id": cell.preset_id,
        "mode": cell.mode,
        "prompts": [{"positive": prompt, "negative": negative}],
        "form_data": form,
        "idempotency_key": SAFE_KEY.sub("_", f"potion-audit-{run_id}-{cell.id}")[:200],
    }


def cell_checks(pack: Pack, cell: Cell) -> dict:
    if cell.checks is not None:
        return cell.checks
    case = pack.case(cell)
    return dict(case.checks) if case else {"min_outputs": 1}


def included(cells, profile: str) -> list[Cell]:
    return [cell for cell in cells if not cell.exclude and profile in cell.profiles]


def run_order(cells: list[Cell], profile: str) -> list[tuple[Cell, bool]]:
    groups = {}
    for cell in sorted(cells, key=lambda item: item.position):
        groups.setdefault(cell.preset_ref, []).append(cell)
    order = []
    for group in groups.values():
        for cell in group:
            order.append((cell, False))
            if profile == "full" and cell.repeat_warm:
                order.append((cell, True))
    return order


def estimate(timing: dict | None, warm: bool) -> float | None:
    if not timing:
        return None
    cold = timing.get("avg_cold_duration_ms")
    hot = timing.get("avg_warm_duration_ms")
    value = (hot if hot is not None else cold) if warm else (cold if cold is not None else hot)
    return round(value / 1000.0, 1) if value is not None else None


def dry_media(input_id: str, as_path: bool) -> str:
    return f"input:{input_id}"


@dataclass(frozen=True)
class Problem:
    severity: str
    where: str
    message: str


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_inputs(pack: Pack, allow_pending: bool, problems: list[Problem]) -> None:
    for spec in pack.inputs.values():
        where = f"input {spec.id}"
        if spec.kind not in INPUT_KINDS:
            problems.append(Problem("error", where, f"kind must be one of {', '.join(INPUT_KINDS)}, got {spec.kind!r}"))
        if not spec.file or Path(spec.file).is_absolute() or ".." in Path(spec.file).parts:
            problems.append(Problem("error", where, "file must be a path inside the pack folder"))
            continue
        method = spec.make.get("method")
        if method not in MAKE_METHODS:
            problems.append(Problem("error", where, f"make.method must be one of {', '.join(MAKE_METHODS)}"))
        else:
            unknown = sorted(set(spec.make) - MAKE_KEYS)
            if unknown:
                problems.append(Problem("error", where, f"make has unknown keys: {', '.join(unknown)}"))
        if method == "transform":
            if spec.make.get("op") not in TRANSFORM_OPS:
                problems.append(Problem("error", where, f"make.op must be one of {', '.join(TRANSFORM_OPS)}"))
            source = spec.make.get("from")
            if source not in pack.inputs:
                problems.append(Problem("error", where, f"make.from names no input {source!r}"))
            elif pack.inputs[source].position >= spec.position:
                problems.append(Problem("error", where, f"make.from {source} must come before {spec.id}"))
        if method == "generate":
            try:
                cell = make_cell(spec, pack.case_set)
                for path, binding in cell.bind.items():
                    if binding.input_id not in pack.inputs:
                        problems.append(Problem("error", where, f"make.bind {path} names no input {binding.input_id!r}"))
                    elif pack.inputs[binding.input_id].position >= spec.position:
                        problems.append(Problem("error", where, f"make.bind {binding.input_id} must come before {spec.id}"))
                _verify_cell(pack, cell, problems, where)
            except PackError as error:
                problems.append(Problem("error", where, str(error)))
        path = pack.root / spec.file
        if spec.pending:
            problems.append(Problem("pending" if allow_pending else "error", where, "not made yet: no sha256 (run pack make-inputs)"))
            continue
        if not SHA_PATTERN.fullmatch(spec.sha256):
            problems.append(Problem("error", where, "sha256 is not 64 lowercase hex digits"))
            continue
        if not path.is_file():
            problems.append(Problem("error", where, f"{spec.file} is missing"))
            continue
        size = path.stat().st_size
        if size != spec.size_bytes:
            problems.append(Problem("error", where, f"{spec.file} is {size} bytes, the pack says {spec.size_bytes}"))
        actual = file_sha(path)
        if actual != spec.sha256:
            problems.append(Problem("error", where, f"{spec.file} has sha256 {actual}, the pack says {spec.sha256}"))


def _verify_cell(pack: Pack, cell: Cell, problems: list[Problem], where: str) -> None:
    preset = pack.preset(cell.preset_ref) or {}
    if cell.mode not in preset.get("modes", ()):
        problems.append(Problem("error", where, f"{cell.preset_ref} has no mode {cell.mode!r}"))
    case = pack.case(cell)
    if cell.case is not None:
        if case is None:
            problems.append(Problem("error", where, f"no case {cell.case!r} for {cell.preset_ref} in {pack.case_set.path.name}"))
            return
        if case.mode != cell.mode:
            problems.append(Problem("error", where, f"case {cell.case} is a {case.mode} case, the cell is {cell.mode}"))
        if case.form.get("negative_prompt") and not cell.negative and cell.prompt:
            problems.append(Problem("error", where, f"case {cell.case} has a negative prompt: name one of [negatives]"))
    for profile in cell.profiles:
        if profile not in PROFILES:
            problems.append(Problem("error", where, f"profile {profile!r} is not one of {', '.join(PROFILES)}"))
    if cell.prompt and cell.prompt not in pack.prompts:
        problems.append(Problem("error", where, f"no prompt {cell.prompt!r} in the pack"))
    if cell.negative and cell.negative not in pack.negatives:
        problems.append(Problem("error", where, f"no negative prompt {cell.negative!r} in the pack"))
    if not cell.prompt and not (case and case.form.get("prompt")) and cell.status == "new" and cell.sources.get("prompt") != "none":
        problems.append(Problem("warning", where, "no prompt: say sources.prompt = \"none\" when the mode takes none"))
    for path, binding in cell.bind.items():
        if binding.input_id not in pack.inputs:
            problems.append(Problem("error", where, f"binding {path} names no input {binding.input_id!r}"))
    for field, value in cell.models.items():
        if isinstance(value, dict):
            shas = [value["sha256"], *(value.get("alternatives") or ())] if value.get("sha256") else []
            if not value.get("filename") and not shas:
                problems.append(Problem("error", where, f"model {field}: a table needs a sha256 or a filename"))
            for sha in shas:
                if not SHA_PATTERN.fullmatch(str(sha).lower()) or str(sha) == ZERO_SHA:
                    problems.append(Problem("error", where, f"model {field}: {sha!r} is not a sha256"))
        elif not SHA_PATTERN.fullmatch(str(value).lower()) or str(value) == ZERO_SHA:
            problems.append(Problem("error", where, f"model {field}: {value!r} is not a sha256"))
    if cell.status == "new" and not cell.sources:
        problems.append(Problem("error", where, "a new case must say where its settings come from (sources)"))
    try:
        cell_models(pack, cell)
        build_cell_request(pack, cell, {}, {}, "verify", dry_media)
    except PackError as error:
        problems.append(Problem("error", where, str(error)))


def verify(pack: Pack, allow_pending: bool = False) -> list[Problem]:
    problems = []
    if pack.cases_sha256 != pack.case_set.sha256:
        problems.append(Problem("error", "cases", f"{pack.case_set.path.name} has sha256 {pack.case_set.sha256}, the pack says {pack.cases_sha256 or 'nothing'}"))
    for key in ("id", "version"):
        if not getattr(pack, key):
            problems.append(Problem("error", "pack", f"{key} is missing"))
    for key, entry in pack.prompts.items():
        try:
            prompt_entry(pack, key)
        except PackError as error:
            problems.append(Problem("error", f"prompt {key}", str(error)))
        if not isinstance(entry, dict) or "positive" not in entry:
            problems.append(Problem("error", f"prompt {key}", "a prompt is a table with a positive text"))
    _verify_inputs(pack, allow_pending, problems)
    seen = set()
    smoke = {}
    covered = set()
    excluded_presets = set()
    for cell in pack.cells:
        where = f"cell {cell.id}"
        if cell.id in seen:
            problems.append(Problem("error", where, "defined twice"))
        seen.add(cell.id)
        if cell.mode == "*":
            if not cell.exclude:
                problems.append(Problem("error", where, "mode \"*\" is only for a whole-preset exclusion"))
            excluded_presets.add(cell.preset_ref)
            continue
        covered.add((cell.preset_ref, cell.mode))
        if cell.exclude:
            if cell.profiles:
                problems.append(Problem("error", where, "an excluded cell belongs to no profile"))
            continue
        if not cell.profiles:
            problems.append(Problem("error", where, "a cell belongs to smoke, full or both"))
        if "smoke" in cell.profiles:
            smoke.setdefault(cell.preset_ref, []).append(cell.id)
        _verify_cell(pack, cell, problems, where)
    for preset in pack.case_set.presets:
        ref = preset_ref(preset)
        if ref in excluded_presets:
            continue
        for mode in preset["modes"]:
            if (ref, mode) not in covered:
                problems.append(Problem("error", f"preset {ref}", f"mode {mode} has no cell"))
        active = [cell for cell in pack.cells if cell.preset_ref == ref and not cell.exclude]
        if active and ref not in smoke and not all(cell.requires_plugin for cell in active):
            problems.append(Problem("warning", f"preset {ref}", "no smoke cell"))
    for ref, ids in smoke.items():
        if len(ids) > 1:
            problems.append(Problem("error", f"preset {ref}", f"more than one smoke cell: {', '.join(ids)}"))
    return problems


def used_by(pack: Pack) -> dict[str, list[str]]:
    usage = {input_id: [] for input_id in pack.inputs}
    for cell in pack.cells:
        for binding in cell.bind.values():
            if binding.input_id in usage and cell.id not in usage[binding.input_id]:
                usage[binding.input_id].append(cell.id)
    for spec in pack.inputs.values():
        sources = [binding.input_id for binding in (_binding(value) for value in (spec.make.get("bind") or {}).values())]
        if spec.make.get("from"):
            sources.append(spec.make["from"])
        for source in sources:
            if source in usage:
                usage[source].append(f"input {spec.id}")
    return usage


def toml_key(key: str) -> str:
    return key if BARE_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=True)


def toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{toml_key(key)} = {toml_value(item)}" for key, item in value.items()) + "}" if value else "{}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise PackError(f"cannot write {type(value).__name__} as TOML")


def set_input_facts(text: str, input_id: str, facts: dict) -> str:
    lines = text.split("\n")
    header = f"[inputs.{input_id}]"
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        raise PackError(f"the pack has no {header} table") from None
    end = next((index for index in range(start + 1, len(lines)) if lines[index].lstrip().startswith("[")), len(lines))
    pending = dict(facts)
    for index in range(start + 1, end):
        key = lines[index].split("=", 1)[0].strip()
        if key in pending:
            lines[index] = f"{key} = {toml_value(pending.pop(key))}"
    insert_at = start + 1
    for key, value in pending.items():
        lines.insert(insert_at, f"{key} = {toml_value(value)}")
        insert_at += 1
    return "\n".join(lines)
