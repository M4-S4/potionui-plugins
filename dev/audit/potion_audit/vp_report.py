import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .vp_scenario import SHOTS

SAFE = re.compile(r"[^A-Za-z0-9._-]+")
DURATION_TOLERANCE = 0.20
VRAM_TOLERANCE_MB = 512.0
SHOT_CHECKS = ("chain_frame", "chain_start", "chain_mode", "chain_warning", "flf_start", "image_preset")
COLUMNS = (
    ("take", SHOTS[0]["id"], "Shot 1"),
    ("take", SHOTS[1]["id"], "Shot 2 chained"),
    ("take", SHOTS[2]["id"], "Shot 3 Ref2VA"),
    ("take", SHOTS[3]["id"], "Shot 4 first and last"),
    ("final_pass", None, "Final pass"),
    ("export", None, "Export"),
)
STATUS_LABELS = {"skipped": "not offered", "not_run": "not run", "left_out": "left out", "missing": "not recorded"}


class ReportError(ValueError):
    pass


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else None


def _relative(run_dir: Path, value) -> Path | None:
    if not value:
        return None
    return run_dir / Path(*str(value).replace("\\", "/").split("/"))


@dataclass
class VpStep:
    engine: str
    kind: str
    shot: str | None
    column: str
    status: str | None
    verdict: str | None
    reason: str | None
    record: dict
    result: dict | None = None
    folder: Path | None = None
    media: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.engine} · {self.column}"

    @property
    def slug(self) -> str:
        return "vp-" + SAFE.sub("_", f"{self.engine}--{self.column}").strip("_")

    @property
    def label(self) -> str:
        return self.verdict or STATUS_LABELS.get(self.status or "", self.status or "unknown")

    @property
    def offered(self) -> bool:
        return self.status != "skipped"

    @property
    def seconds(self):
        timing = (self.result or {}).get("timing") or {}
        if self.kind == "export":
            return timing.get("polled_seconds")
        found = timing.get("run_seconds")
        return found if found is not None else self.record.get("run_seconds")

    @property
    def peak_vram_mb(self):
        stats = (self.result or {}).get("generation_stats") or {}
        return stats.get("peak_vram_mb") if stats.get("derived") else None

    @property
    def checks(self) -> list[dict]:
        return list((self.result or {}).get("checks") or ())

    @property
    def shot_checks(self) -> list[dict]:
        return [check for check in self.checks if check.get("check") in SHOT_CHECKS]

    @property
    def not_offered_checks(self) -> list[dict]:
        return list((self.result or {}).get("not_offered") or ())

    @property
    def stats_preset(self) -> dict:
        return dict((self.result or {}).get("stats_preset") or self.record.get("stats_preset") or {})

    @property
    def stats_preset_id(self) -> str | None:
        return self.stats_preset.get("preset_id")

    @property
    def other_preset(self) -> str | None:
        found = self.stats_preset
        if not found.get("differs"):
            return None
        return str(found.get("name") or found.get("preset_id"))

    @property
    def video(self) -> Path | None:
        if self.folder is None:
            return None
        for output in (self.result or {}).get("outputs") or ():
            if output.get("kind") == "video":
                return self.folder / output["file"]
        return None


@dataclass
class Scenario:
    dir: Path
    data: dict
    steps: list[VpStep]
    notes: list[str] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        return str(self.data.get("run_id") or self.dir.name)

    @property
    def machine(self) -> str:
        return str(self.data.get("machine") or "unnamed")

    @property
    def app_version(self):
        return self.data.get("app_version")

    @property
    def pack(self) -> dict:
        return self.data.get("pack") or {}

    @property
    def engines(self) -> list[dict]:
        return list(self.data.get("engines") or ())

    def rows(self) -> list[tuple[str, list[VpStep]]]:
        found: dict[str, list[VpStep]] = {}
        for step in self.steps:
            found.setdefault(step.engine, []).append(step)
        return list(found.items())

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for step in self.steps:
            counts[step.label] = counts.get(step.label, 0) + 1
        return counts


def night_segments(night_dir: Path) -> list[Path]:
    data = _json(night_dir / "night.json") or {}
    found = []
    for segment in data.get("segments") or ():
        folder = night_dir.parent / str(segment.get("run_id"))
        if not (folder / "run.json").is_file():
            raise ReportError(f"{night_dir.name}/night.json names the segment {folder.name}, which holds no run.json beside it")
        found.append(folder)
    if not found:
        raise ReportError(f"{night_dir.name}/night.json lists no segment")
    return found


def split_dirs(dirs: list[Path]) -> tuple[list[Path], list[Path]]:
    matrix = []
    scenarios = []
    for path in dirs:
        if (path / "scenario.json").is_file():
            scenarios.append(path)
        elif (path / "night.json").is_file() and not (path / "run.json").is_file():
            matrix.extend(night_segments(path))
        elif (path / "plan.json").is_file() and not (path / "run.json").is_file():
            raise ReportError(f"{path.name} holds the plan of a dry run, not a scenario.json")
        else:
            matrix.append(path)
    return matrix, scenarios


def _matching(entry: dict, kind: str, shot: str | None) -> dict | None:
    for step in entry.get("steps") or ():
        if step.get("step") == kind and (shot is None or step.get("shot") == shot):
            return step
    return None


def load_scenario(run_dir: Path) -> Scenario:
    data = _json(run_dir / "scenario.json")
    if not isinstance(data, dict) or data.get("kind") != "vp-scenario":
        raise ReportError(f"{run_dir.name}/scenario.json is not the record of a Video Producer scenario")
    steps = []
    for entry in data.get("engines") or ():
        engine = str(entry.get("key") or entry.get("engine"))
        for kind, shot, column in COLUMNS:
            record = _matching(entry, kind, shot)
            if not entry.get("selected"):
                steps.append(VpStep(engine, kind, shot, column, "left_out", None, entry.get("reason"), {}))
                continue
            if record is None:
                steps.append(VpStep(engine, kind, shot, column, "missing", None, entry.get("reason") or "the scenario has no such step for this engine", {}))
                continue
            step = VpStep(engine, kind, shot, column, record.get("status"), record.get("verdict"), record.get("reason"), record)
            path = _relative(run_dir, record.get("result"))
            if path is not None:
                step.result = _json(path)
                step.folder = path.parent
            steps.append(step)
    return Scenario(dir=run_dir, data=data, steps=steps)


def load_one_scenario(dirs: list[Path]) -> Scenario | None:
    if not dirs:
        return None
    if len(dirs) > 1:
        raise ReportError(f"a report holds one scenario, {len(dirs)} were given ({', '.join(path.name for path in dirs)}): use --compare or merge")
    return load_scenario(dirs[0])


def _change(after, before) -> float | None:
    if after is None or before is None or not before:
        return None
    return round((after - before) / before, 3)


def compare_scenarios(current: Scenario, previous: Scenario) -> dict:
    mine = current.pack
    theirs = previous.pack
    if mine.get("id") != theirs.get("id") or mine.get("sha256") != theirs.get("sha256"):
        raise ReportError(
            f"compare needs two scenarios of the same pack: this one has {mine.get('id')} {str(mine.get('sha256'))[:12]}, "
            f"the other {theirs.get('id')} {str(theirs.get('sha256'))[:12]}"
        )
    before = {step.key: step for step in previous.steps}
    rows = []
    for step in current.steps:
        old = before.get(step.key)
        if old is None:
            continue
        duration = _change(step.seconds, old.seconds)
        vram = None if step.peak_vram_mb is None or old.peak_vram_mb is None else round(step.peak_vram_mb - old.peak_vram_mb, 1)
        preset_changed = step.stats_preset_id is not None and old.stats_preset_id is not None and step.stats_preset_id != old.stats_preset_id
        rows.append(
            {
                "step": step.key,
                "slug": step.slug,
                "verdict": step.label,
                "previous_verdict": old.label,
                "verdict_changed": step.label != old.label,
                "seconds": step.seconds,
                "previous_seconds": old.seconds,
                "duration_change": duration,
                "duration_flag": duration is not None and abs(duration) > DURATION_TOLERANCE,
                "peak_vram_mb": step.peak_vram_mb,
                "previous_peak_vram_mb": old.peak_vram_mb,
                "vram_change_mb": vram,
                "vram_flag": vram is not None and abs(vram) > VRAM_TOLERANCE_MB,
                "stats_preset": step.stats_preset.get("name") or step.stats_preset_id,
                "previous_stats_preset": old.stats_preset.get("name") or old.stats_preset_id,
                "preset_changed": preset_changed,
            }
        )
    keys = {step.key for step in current.steps}
    settings = []
    now_settings = current.data.get("settings") or {}
    then_settings = previous.data.get("settings") or {}
    for name in sorted(set(now_settings) | set(then_settings)):
        if now_settings.get(name) != then_settings.get(name):
            settings.append(f"{name}: {then_settings.get(name)} then, {now_settings.get(name)} now")
    for label, now, then in (("machine", current.machine, previous.machine), ("application", current.app_version, previous.app_version), ("plugin", (current.data.get("plugin") or {}).get("version"), (previous.data.get("plugin") or {}).get("version"))):
        if now != then:
            settings.append(f"{label}: {then} then, {now} now")
    return {
        "previous": {"run_id": previous.run_id, "started_at": previous.data.get("started_at"), "app_version": previous.app_version},
        "rows": rows,
        "only_in_previous": [key for key in before if key not in keys],
        "only_in_this_run": [step.key for step in current.steps if step.key not in before],
        "changes": settings,
    }


def scenario_json(scenario: Scenario) -> dict:
    return {
        "run_id": scenario.run_id,
        "machine": scenario.machine,
        "app_version": scenario.app_version,
        "plugin": scenario.data.get("plugin"),
        "pack": scenario.pack,
        "settings": scenario.data.get("settings"),
        "stopped": scenario.data.get("stopped"),
        "steps": [
            {
                "engine": step.engine,
                "step": step.column,
                "status": step.status,
                "verdict": step.verdict,
                "reason": step.reason,
                "seconds": step.seconds,
                "peak_vram_mb": step.peak_vram_mb,
                "shot_checks": step.shot_checks,
                "not_offered": step.not_offered_checks,
                "stats_preset": step.stats_preset or None,
            }
            for step in scenario.steps
        ],
    }
