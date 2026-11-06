import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MODES = ("dedicated", "shared")
PROBE_SOURCES = ("local", "file", "none")
DEFAULT_CASES = Path(__file__).resolve().parent.parent / "cases" / "d7ff033de.json"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    url: str
    mode: str
    user_env: str
    password_env: str
    timeout_seconds: float


@dataclass(frozen=True)
class Config:
    path: Path
    target: Target
    output_dir: Path
    machine: str
    cases_file: Path
    probe_source: str
    probe_file: Path | None
    container: str | None


def _resolve(base: Path, value: str) -> Path:
    path = Path(os.path.expanduser(value))
    return path if path.is_absolute() else (base / path).resolve()


def _require(table: Mapping, key: str, section: str):
    if key not in table:
        raise ConfigError(f"[{section}] {key} is missing")
    return table[key]


def load_config(path: Path) -> Config:
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist: copy audit.example.toml to audit.toml") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    base = path.resolve().parent
    target = data.get("target") or {}
    run = data.get("run") or {}
    probe = data.get("probe") or {}
    url = str(_require(target, "url", "target")).rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"[target] url must start with http:// or https://, got {url!r}")
    mode = str(target.get("mode", "shared"))
    if mode not in MODES:
        raise ConfigError(f"[target] mode must be one of {', '.join(MODES)}, got {mode!r}")
    source = str(probe.get("source", "none"))
    if source not in PROBE_SOURCES:
        raise ConfigError(f"[probe] source must be one of {', '.join(PROBE_SOURCES)}, got {source!r}")
    probe_file = probe.get("file")
    if source == "file" and not probe_file:
        raise ConfigError("[probe] file is required when source = \"file\"")
    cases = run.get("cases")
    return Config(
        path=path.resolve(),
        target=Target(
            url=url,
            mode=mode,
            user_env=str(target.get("user_env", "POTION_AUDIT_USER")),
            password_env=str(target.get("password_env", "POTION_AUDIT_PASSWORD")),
            timeout_seconds=float(target.get("timeout_seconds", 60)),
        ),
        output_dir=_resolve(base, str(_require(run, "output_dir", "run"))),
        machine=str(run.get("machine", "unnamed")),
        cases_file=_resolve(base, str(cases)) if cases else DEFAULT_CASES,
        probe_source=source,
        probe_file=_resolve(base, str(probe_file)) if probe_file else None,
        container=str(probe["container"]) if probe.get("container") else None,
    )


def credentials(target: Target, environ: Mapping[str, str]) -> tuple[str, str]:
    missing = [name for name in (target.user_env, target.password_env) if not environ.get(name)]
    if missing:
        raise ConfigError(f"credentials missing from the environment: {', '.join(missing)}")
    return environ[target.user_env], environ[target.password_env]
