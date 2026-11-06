import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SCHEMA = 1
ZERO_SHA = "0" * 64
CORE_PRESETS = "content/presets/marketplace/"
PLUGINS = "content/plugins/marketplace/"
CORE_RECIPES = "content/recipes/marketplace/"
IGNORED_FIELD_TOKENS = {"model"}


class CaseFileError(ValueError):
    pass


@dataclass(frozen=True)
class ModelRef:
    field: str
    sha256: str
    size_bytes: int | None
    filename: str | None
    source: str

    @property
    def resolved(self) -> bool:
        return self.sha256 != ZERO_SHA


@dataclass(frozen=True)
class Case:
    preset_key: str
    preset_id: str
    name: str
    mode: str
    kind: str | None
    seed: int | None
    tags: tuple[str, ...]
    form: dict
    models: tuple[ModelRef, ...]
    checks: dict


@dataclass(frozen=True)
class CaseSet:
    path: Path
    sha256: str
    source: dict
    presets: tuple[dict, ...]
    recipes: tuple[dict, ...]
    cases: tuple[Case, ...]

    def preset(self, key: str) -> dict | None:
        for preset in self.presets:
            if preset["key"] == key or preset["id"] == key:
                return preset
        return None


def load_cases(path: Path) -> CaseSet:
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CaseFileError(f"{path} is not JSON: {error}") from error
    if data.get("schema") != SCHEMA:
        raise CaseFileError(f"{path} has schema {data.get('schema')!r}, expected {SCHEMA}")
    cases = tuple(
        Case(
            preset_key=item["preset_key"],
            preset_id=item["preset_id"],
            name=item["name"],
            mode=item["mode"],
            kind=item.get("kind"),
            seed=item.get("seed"),
            tags=tuple(item.get("tags") or ()),
            form=dict(item.get("form") or {}),
            models=tuple(ModelRef(**model) for model in item.get("models") or ()),
            checks=dict(item.get("checks") or {}),
        )
        for item in data["cases"]
    )
    return CaseSet(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        source=data["source"],
        presets=tuple(data["presets"]),
        recipes=tuple(data["recipes"]),
        cases=cases,
    )


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


def _recipe_entry(path: str, recipe: dict) -> dict:
    artifacts = []
    for artifact in recipe.get("artifacts") or ():
        checksum = artifact.get("checksum") or {}
        sha = checksum.get("value") if checksum.get("algorithm", "sha256") == "sha256" else None
        artifacts.append(
            {
                "id": artifact.get("id"),
                "filename": artifact.get("filename"),
                "model_type": artifact.get("model_type") or artifact.get("kind"),
                "sha256": sha.lower() if sha else None,
                "size_bytes": artifact.get("size_bytes"),
            }
        )
    return {
        "id": recipe.get("id"),
        "path": path,
        "version": recipe.get("version"),
        "preset_ids": [entry.get("preset_id") for entry in recipe.get("presets") or () if entry.get("preset_id")],
        "artifacts": artifacts,
    }


def _candidates(preset_id: str, recipes: list[dict]) -> list[tuple[dict, str]]:
    return [
        (artifact, f"recipe:{recipe['id']}/{artifact['id']}")
        for recipe in recipes
        if preset_id in recipe["preset_ids"]
        for artifact in recipe["artifacts"]
    ]


def _unique(matches: list[tuple[dict, str]]) -> tuple[dict, str] | None:
    by_key = {artifact["sha256"] or artifact["filename"]: (artifact, source) for artifact, source in matches}
    return next(iter(by_key.values())) if len(by_key) == 1 else None


def _resolve_zero(field: str, preset_id: str, recipes: list[dict], model_fields: dict) -> tuple[dict, str] | None:
    candidates = _candidates(preset_id, recipes)
    declared = model_fields.get(field) or {}
    recommended = set(declared.get("recommended") or ())
    if recommended:
        found = _unique([(artifact, source) for artifact, source in candidates if artifact["sha256"] in recommended])
        if found:
            return found
    wanted = _tokens(field) - IGNORED_FIELD_TOKENS
    if wanted:
        found = _unique(
            [
                (artifact, source)
                for artifact, source in candidates
                if wanted <= _tokens(artifact["id"] or "") | _tokens(artifact["filename"] or "")
            ]
        )
        if found:
            return found
    if declared.get("model_type"):
        return _unique([(artifact, source) for artifact, source in candidates if artifact["model_type"] == declared["model_type"]])
    return None


def model_fields_of(documents: list) -> dict:
    fields = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "model" and isinstance(node.get("name"), str):
                configuration = node.get("configuration") or {}
                entry = fields.setdefault(node["name"], {"model_type": configuration.get("model_type"), "recommended": set()})
                for item in configuration.get("recommendations") or ():
                    if isinstance(item, dict) and item.get("sha256"):
                        entry["recommended"].add(str(item["sha256"]).lower())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for document in documents:
        walk(document)
    return {name: {"model_type": entry["model_type"], "recommended": sorted(entry["recommended"])} for name, entry in fields.items()}


def build_case_set(ref: str, label: str, presets: list[dict], recipes: list[dict]) -> dict:
    recipe_entries = [_recipe_entry(item["path"], item["recipe"]) for item in recipes]
    by_sha = {}
    for recipe in recipe_entries:
        for artifact in recipe["artifacts"]:
            if artifact["sha256"]:
                by_sha.setdefault(artifact["sha256"], artifact)
    preset_entries = []
    cases = []
    for item in sorted(presets, key=lambda entry: (entry["origin"], entry["key"])):
        preset = item["preset"]
        preset_id = str(preset.get("id"))
        requires = preset.get("requires") or {}
        tests = item.get("tests") or {}
        model_fields = item.get("model_fields") or {}
        preset_cases = []
        for case in tests.get("cases") or ():
            models = []
            for field, ref_data in (case.get("models") or {}).items():
                sha = str((ref_data or {}).get("sha256") or ZERO_SHA).lower()
                source = "tests.yml"
                artifact = by_sha.get(sha)
                if sha == ZERO_SHA:
                    resolved = _resolve_zero(field, preset_id, recipe_entries, model_fields)
                    if resolved and resolved[0]["sha256"]:
                        artifact, source = resolved
                        sha = artifact["sha256"]
                    elif resolved:
                        artifact, source = resolved[0], "unresolved, " + resolved[1] + " has no sha256"
                    else:
                        source = "unresolved"
                models.append(
                    {
                        "field": field,
                        "sha256": sha,
                        "size_bytes": artifact["size_bytes"] if artifact else None,
                        "filename": artifact["filename"] if artifact else None,
                        "source": source,
                    }
                )
            preset_cases.append(
                {
                    "preset_key": item["key"],
                    "preset_id": preset_id,
                    "name": case.get("name"),
                    "mode": case.get("mode", "txt2img"),
                    "kind": case.get("kind"),
                    "seed": case.get("seed"),
                    "tags": list(case.get("tags") or ()),
                    "form": case.get("form") or {},
                    "models": models,
                    "checks": case.get("checks") or {},
                    "undeclared_model_fields": sorted(
                        field for field in (case.get("models") or {}) if model_fields and field not in model_fields
                    ),
                }
            )
        cases.extend(preset_cases)
        preset_entries.append(
            {
                "key": item["key"],
                "path": item["path"],
                "origin": item["origin"],
                "id": preset_id,
                "name": preset.get("name"),
                "version": None if preset.get("version") is None else str(preset.get("version")),
                "engine": preset.get("engine", "native"),
                "category": preset.get("category"),
                "min_vram_gb": requires.get("min_vram_gb"),
                "modes": sorted(item.get("modes") or ()),
                "tests_blob": item.get("tests_blob"),
                "case_count": len(preset_cases),
            }
        )
    return {
        "schema": SCHEMA,
        "source": {"label": label, "ref": ref},
        "presets": preset_entries,
        "recipes": sorted(recipe_entries, key=lambda entry: entry["path"]),
        "cases": cases,
    }


def _git(core: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(core), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def _preset_dirs(paths: list[str]) -> dict[str, tuple[str, str]]:
    found = {}
    for path in paths:
        if not path.endswith("/preset.yml"):
            continue
        folder = path[: -len("/preset.yml")]
        if folder.startswith(CORE_PRESETS) and folder.count("/") == CORE_PRESETS.count("/"):
            found[folder] = ("core", folder.rsplit("/", 1)[1])
        elif folder.startswith(PLUGINS):
            parts = folder[len(PLUGINS):].split("/")
            if len(parts) == 3 and parts[1] == "presets":
                found[folder] = (f"plugin:{parts[0]}", parts[2])
    return found


def _recipe_paths(paths: list[str]) -> list[str]:
    selected = []
    for path in paths:
        if not path.endswith(".yml"):
            continue
        if path.startswith(CORE_RECIPES) and path.count("/") == CORE_RECIPES.count("/"):
            selected.append(path)
        elif path.startswith(PLUGINS):
            parts = path[len(PLUGINS):].split("/")
            if len(parts) == 3 and parts[1] == "recipes":
                selected.append(path)
    return selected


def import_from_core(core: Path, ref: str, label: str) -> dict:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise CaseFileError("importing cases needs PyYAML: run with `uv run --locked --group cases`") from error
    sha = _git(core, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    paths = _git(core, "ls-tree", "-r", "--name-only", sha, "--", CORE_PRESETS, PLUGINS, CORE_RECIPES).splitlines()
    presets = []
    for folder, (origin, key) in sorted(_preset_dirs(paths).items()):
        modes = {path[len(folder) + 7:].split("/", 1)[0] for path in paths if path.startswith(folder + "/modes/")}
        tests_path = folder + "/tests.yml"
        tests = None
        tests_blob = None
        if tests_path in paths:
            tests = yaml.safe_load(_git(core, "show", f"{sha}:{tests_path}"))
            tests_blob = _git(core, "rev-parse", f"{sha}:{tests_path}").strip()
        form_documents = [
            yaml.safe_load(_git(core, "show", f"{sha}:{path}"))
            for path in paths
            if path.startswith(folder + "/") and path.endswith(".yml") and path != tests_path
        ]
        presets.append(
            {
                "key": key,
                "path": folder,
                "origin": origin,
                "preset": yaml.safe_load(_git(core, "show", f"{sha}:{folder}/preset.yml")) or {},
                "modes": sorted(modes),
                "tests": tests,
                "tests_blob": tests_blob,
                "model_fields": model_fields_of(form_documents),
            }
        )
    recipes = [
        {"path": path, "recipe": yaml.safe_load(_git(core, "show", f"{sha}:{path}")) or {}}
        for path in _recipe_paths(paths)
    ]
    return build_case_set(sha, label, presets, recipes)


def write_case_set(data: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
