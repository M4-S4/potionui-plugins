import json
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from pathlib import Path

import av

from . import __version__
from .media import THUMB_SIDE, media_ssim, write_display_image, write_preview, write_thumbnail
from .pack import Pack, included
from .plan import cell_folder
from .reevaluate import REEVALUATED, load_run_json, ReevaluateError

REPORT_SCHEMA = 1
DURATION_TOLERANCE = 0.20
VRAM_TOLERANCE_MB = 512.0
PREVIEW_HEIGHT = 540
HISTORY_LINES = 80
HOME_PATTERNS = (re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/]+"), re.compile(r"/home/[^/]+"), re.compile(r"/Users/[^/]+"))
MARKUP = re.compile(r"<<[A-Z_]+:([^>]*)>>")
SAFE = re.compile(r"[^A-Za-z0-9._-]+")
VERDICT_CLASS = {"PASS": "ok", "FAIL": "bad", "OOM": "bad", "TIMEOUT": "bad", "REJECTED": "bad", "STOPPED": "warn"}
STATUS_CLASS = {
    "model_missing": "warn",
    "model_unresolved": "warn",
    "input_pending": "warn",
    "request_error": "bad",
    "preset_not_installed": "warn",
}

STYLE = """
:root { color-scheme: light; --bg: #fbfaf8; --card: #ffffff; --fg: #1f1d1a; --muted: #6b665e; --line: #e2ddd5; --ok: #1a7f37; --ok-bg: #e3f4e6; --bad: #c2261c; --bad-bg: #fbe5e3; --warn: #8a5a00; --warn-bg: #fbf0d9; --idle: #6b665e; --idle-bg: #efece7; --accent: #6b3fa0; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --bg: #141317; --card: #1c1b20; --fg: #ebe8e3; --muted: #a29d95; --line: #34323a; --ok: #4ac26b; --ok-bg: #16301f; --bad: #ff7b72; --bad-bg: #3a1b1a; --warn: #e3b341; --warn-bg: #352a12; --idle: #a29d95; --idle-bg: #26242b; --accent: #b58cf0; } }
:root[data-theme="dark"] { color-scheme: dark; --bg: #141317; --card: #1c1b20; --fg: #ebe8e3; --muted: #a29d95; --line: #34323a; --ok: #4ac26b; --ok-bg: #16301f; --bad: #ff7b72; --bad-bg: #3a1b1a; --warn: #e3b341; --warn-bg: #352a12; --idle: #a29d95; --idle-bg: #26242b; --accent: #b58cf0; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0 auto; max-width: 1280px; padding: 16px; }
h1 { font-size: 24px; margin: 8px 0 4px; } h2 { font-size: 18px; margin: 32px 0 10px; } h3 { font-size: 15px; margin: 18px 0 6px; }
a { color: var(--accent); }
.muted { color: var(--muted); } .small { font-size: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px 20px; margin: 0; }
.facts div { min-width: 0; } .facts dt { color: var(--muted); font-size: 12px; } .facts dd { margin: 0; overflow-wrap: anywhere; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12px; white-space: nowrap; }
table.matrix { width: max-content; min-width: 100%; }
table.matrix th:first-child, table.matrix td:first-child { position: sticky; left: 0; background: var(--card); z-index: 1; font-weight: 600; max-width: 170px; overflow-wrap: anywhere; box-shadow: 1px 0 0 var(--line); }
table.matrix .cell { width: 132px; }
.cell { display: block; text-decoration: none; color: inherit; border-radius: 8px; padding: 6px; margin-bottom: 4px; overflow-wrap: anywhere; }
.cell img { display: block; width: 116px; height: 72px; object-fit: cover; border-radius: 5px; margin-top: 4px; background: var(--idle-bg); }
.tag { display: inline-block; font-weight: 700; font-size: 12px; letter-spacing: .02em; }
.ok { background: var(--ok-bg); } .ok .tag, .tag.ok { color: var(--ok); }
.bad { background: var(--bad-bg); } .bad .tag, .tag.bad { color: var(--bad); }
.warn { background: var(--warn-bg); } .warn .tag, .tag.warn { color: var(--warn); }
.idle { background: var(--idle-bg); } .idle .tag, .tag.idle { color: var(--idle); }
.tag.ok, .tag.bad, .tag.warn, .tag.idle { background: none; }
.was { color: var(--muted); font-weight: 400; text-decoration: line-through; margin-left: 4px; }
details { background: var(--card); border: 1px solid var(--line); border-radius: 10px; margin: 8px 0; }
details > summary { cursor: pointer; padding: 10px 14px; overflow-wrap: anywhere; }
details > .body { padding: 0 14px 14px; }
details:target, details[open] { border-color: var(--accent); }
pre { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 8px; overflow-x: auto; font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
video, .media img { max-width: 100%; height: auto; border-radius: 6px; background: #000; }
audio { width: 100%; }
ul { padding-left: 20px; }
.legend span { margin-right: 12px; white-space: nowrap; }
@media (max-width: 640px) { body { padding: 12px 16px; font-size: 14px; } h1 { font-size: 20px; } table.matrix th:first-child, table.matrix td:first-child { max-width: 96px; font-size: 12px; } table.matrix .cell { width: 116px; } .cell img { width: 100px; height: 62px; } }
"""

SCRIPT = """
function openTarget() { var id = decodeURIComponent(location.hash.slice(1)); if (!id) return; var node = document.getElementById(id); if (node && node.tagName === 'DETAILS') { node.open = true; node.scrollIntoView(); } }
window.addEventListener('hashchange', openTarget); window.addEventListener('DOMContentLoaded', openTarget);
"""


class ReportError(ValueError):
    pass


def reduce_home(text):
    if not isinstance(text, str):
        return text
    for pattern in HOME_PATTERNS:
        text = pattern.sub("<home>", text)
    return text


def plain(text) -> str:
    return MARKUP.sub(lambda found: found.group(1).rsplit(":", 1)[0] if ":" in found.group(1) else found.group(1), str(text or ""))


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else None


@dataclass
class Entry:
    cell: str
    preset: str
    mode: str
    warm: bool
    status: str | None
    reason: str | None
    verdict: str | None
    estimate_seconds: float | None
    run_dir: Path | None
    order: int
    result: dict | None = None
    reevaluated: dict | None = None
    request: dict | None = None
    run_report: dict | None = None
    media: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.cell}{' warm' if self.warm else ''}"

    @property
    def slug(self) -> str:
        return "c-" + SAFE.sub("_", self.key).strip("_")

    @property
    def column(self) -> str:
        prefix = self.preset + ":"
        return self.cell[len(prefix):] if self.cell.startswith(prefix) else self.mode

    @property
    def folder(self) -> Path | None:
        return self.run_dir / "cells" / cell_folder(self.cell, self.warm) if self.run_dir else None

    @property
    def shown_verdict(self) -> str | None:
        if self.reevaluated and self.reevaluated.get("verdict"):
            return self.reevaluated["verdict"]
        return self.verdict

    @property
    def previous_verdict(self) -> str | None:
        if self.reevaluated and self.reevaluated.get("changed"):
            return (self.reevaluated.get("previous") or {}).get("verdict")
        return None

    @property
    def run_seconds(self):
        return ((self.result or {}).get("timing") or {}).get("run_seconds")

    @property
    def peak_vram_mb(self):
        return ((self.result or {}).get("generation_stats") or {}).get("peak_vram_mb")

    @property
    def seed(self):
        return ((self.request or {}).get("form_data") or {}).get("seed")


@dataclass
class RunSet:
    dirs: list[Path]
    runs: list[dict]
    entries: list[Entry]
    preflight: dict | None
    instance: dict | None
    probes: list[dict]
    notes: list[str]

    @property
    def first(self) -> dict:
        return self.runs[0]

    @property
    def pack(self) -> dict:
        return self.first.get("pack") or {}

    @property
    def machine(self) -> str:
        return str(self.first.get("machine") or "unnamed")

    @property
    def mode(self) -> str | None:
        found = next((run.get("mode") for run in self.runs if run.get("mode")), None)
        return found or ((self.preflight or {}).get("target") or {}).get("mode")

    @property
    def started_at(self):
        return min((run.get("started_at") for run in self.runs if run.get("started_at")), default=None)

    @property
    def ended_at(self):
        return max((run.get("ended_at") for run in self.runs if run.get("ended_at")), default=None)

    def gpu(self) -> dict:
        return (self.instance or {}).get("gpu_profile") or ((self.preflight or {}).get("hardware") or {}).get("gpu_profile") or {}

    def stats(self) -> dict:
        return (self.instance or {}).get("stats") or ((self.preflight or {}).get("hardware") or {}).get("stats") or {}

    def probe(self, kind: str) -> dict | None:
        return next((probe for probe in self.probes if probe.get("probe") == kind), None)


def _probe_files(run_dir: Path) -> list[Path]:
    return sorted(path for path in run_dir.glob("*.json") if "probe" in path.name)


def _load_entries(dirs: list[Path], runs: list[dict]) -> list[Entry]:
    merged: dict[str, Entry] = {}
    order = 0
    for run_dir, run in zip(dirs, runs):
        for raw in run.get("cells") or ():
            order += 1
            entry = Entry(
                cell=raw["cell"],
                preset=raw.get("preset") or raw["cell"].split(":", 1)[0],
                mode=raw.get("mode") or "",
                warm=bool(raw.get("warm_repeat")),
                status=raw.get("status"),
                reason=raw.get("reason"),
                verdict=raw.get("verdict"),
                estimate_seconds=raw.get("estimate_seconds"),
                run_dir=run_dir,
                order=order,
            )
            known = merged.get(entry.key)
            if known is None:
                merged[entry.key] = entry
            elif entry.verdict or known.status == "not_run" or not known.verdict:
                entry.order = known.order
                merged[entry.key] = entry
    entries = sorted(merged.values(), key=lambda item: item.order)
    for entry in entries:
        folder = entry.folder
        if folder is None or not folder.is_dir():
            continue
        entry.result = _json(folder / "result.json")
        entry.reevaluated = _json(folder / REEVALUATED)
        entry.request = _json(folder / "request.json")
        entry.run_report = _json(folder / "run_report.json")
    return entries


def load_set(dirs: list[Path], preflight: Path | None = None, probes: list[Path] | None = None, notes: list[str] | None = None) -> RunSet:
    if not dirs:
        raise ReportError("give at least one run folder")
    try:
        runs = [load_run_json(run_dir) for run_dir in dirs]
    except ReevaluateError as error:
        raise ReportError(str(error)) from error
    packs = {(run.get("pack") or {}).get("sha256") for run in runs}
    machines = {run.get("machine") for run in runs}
    if len(packs) > 1:
        raise ReportError("the run folders ran different packs: give the segments of one run, or use --compare or merge")
    if len(machines) > 1:
        raise ReportError(f"the run folders come from different machines ({', '.join(sorted(str(name) for name in machines))}): use merge")
    preflight_data = _json(preflight) if preflight else next((data for data in (_json(run_dir / "preflight.json") for run_dir in dirs) if data), None)
    instance = next((data for data in (_json(run_dir / "instance.json") for run_dir in dirs) if data), None)
    probe_paths = list(probes or ()) + [path for run_dir in dirs for path in _probe_files(run_dir)]
    probe_data = []
    for path in probe_paths:
        data = _json(path)
        if isinstance(data, dict) and data.get("probe"):
            probe_data.append(data)
    return RunSet(dirs=list(dirs), runs=runs, entries=_load_entries(list(dirs), runs), preflight=preflight_data, instance=instance, probes=probe_data, notes=list(notes or ()))


def add_pack_cells(run_set: RunSet, pack: Pack) -> int:
    if pack.sha256 != run_set.pack.get("sha256"):
        return 0
    known = {entry.cell for entry in run_set.entries}
    profile = run_set.first.get("profile") or "full"
    order = max((entry.order for entry in run_set.entries), default=0)
    added = 0
    planned = {cell.id for cell in included(pack.cells, profile)}
    for cell in pack.cells:
        if cell.id in known:
            continue
        if cell.exclude:
            status, reason = "excluded", cell.exclude
        elif cell.id in planned:
            status, reason = "not_in_run", f"in the {profile} profile, left out of this run"
        else:
            continue
        order += 1
        added += 1
        run_set.entries.append(Entry(cell=cell.id, preset=cell.preset_ref, mode=cell.mode, warm=False, status=status, reason=reason, verdict=None, estimate_seconds=None, run_dir=None, order=order))
    return added


def _fresh(source: Path, target: Path) -> bool:
    return target.is_file() and target.stat().st_mtime >= source.stat().st_mtime


def _href(target: Path, out_dir: Path) -> str:
    return urllib.parse.quote(Path(os.path.relpath(target, out_dir)).as_posix())


def prepare_media(run_set: RunSet, out_dir: Path, log=print) -> None:
    media_root = out_dir / "media"
    for entry in run_set.entries:
        outputs = (entry.result or {}).get("outputs") or []
        for output in outputs:
            source = entry.folder / output["file"]
            item = {"file": output["file"], "kind": output.get("kind"), "original": None, "display": None, "thumb": None, "error": None}
            entry.media.append(item)
            if not source.is_file():
                item["error"] = "the output file is not in the run folder"
                continue
            item["original"] = _href(source, out_dir)
            stem = media_root / entry.slug / Path(output["file"]).stem
            try:
                if output.get("kind") == "video":
                    display = stem.with_suffix(".mp4")
                    if not _fresh(source, display):
                        write_preview(source, display, PREVIEW_HEIGHT)
                    item["display"] = _href(display, out_dir)
                elif output.get("kind") == "image":
                    display = stem.with_suffix(".webp")
                    if not _fresh(source, display):
                        write_display_image(source, display)
                    item["display"] = _href(display, out_dir)
                if output.get("kind") in {"video", "image"}:
                    thumb = stem.with_name(stem.name + ".thumb.jpg")
                    if not _fresh(source, thumb):
                        write_thumbnail(source, thumb, output["kind"], THUMB_SIDE)
                    item["thumb"] = _href(thumb, out_dir)
            except (av.error.FFmpegError, OSError, ValueError, RuntimeError) as error:
                item["error"] = f"{type(error).__name__}: {error}"
                log(f"{entry.key}: media {output['file']}: {item['error']}")


def _storage_key(run_set: RunSet) -> dict:
    found = {}
    linux = run_set.probe("linux")
    for path in (linux or {}).get("paths") or ():
        systems = ((path.get("findmnt") or {}).get("filesystems") or [{}])[0]
        found[f"container {path.get('path')}"] = f"{systems.get('fstype') or path.get('fs_type')} on {reduce_home(systems.get('source'))}"
    windows = run_set.probe("windows")
    for volume in (windows or {}).get("volumes") or ():
        found[f"volume {volume.get('drive')}:"] = f"{volume.get('file_system')} {_gb(volume.get('size_bytes'))}"
    for disk in (windows or {}).get("physical_disks") or ():
        found[f"disk {disk.get('device_id')}"] = f"{disk.get('model')} {disk.get('bus_type')} {disk.get('media_type')}"
    return found


def _change(after, before) -> float | None:
    if after is None or before is None or not before:
        return None
    return round((after - before) / before, 3)


def _first_media(entry: Entry) -> dict | None:
    outputs = (entry.result or {}).get("outputs") or []
    return outputs[0] if outputs else None


def _ssim(current: Entry, previous: Entry) -> dict:
    first = _first_media(current)
    second = _first_media(previous)
    if not first or not second:
        return {"value": None, "reason": "no output on one side"}
    if first.get("kind") not in {"image", "video"} or first.get("kind") != second.get("kind"):
        return {"value": None, "reason": "not two pictures or two videos"}
    if current.seed is None or current.seed != previous.seed:
        return {"value": None, "reason": f"seeds differ ({current.seed} and {previous.seed})"}
    if (first.get("width"), first.get("height")) != (second.get("width"), second.get("height")):
        return {"value": None, "reason": "sizes differ"}
    a = current.folder / first["file"]
    b = previous.folder / second["file"]
    if not a.is_file() or not b.is_file():
        return {"value": None, "reason": "an output file is missing"}
    try:
        return {"value": media_ssim(a, b, first["kind"]), "reason": None}
    except (av.error.FFmpegError, OSError, ValueError) as error:
        return {"value": None, "reason": f"{type(error).__name__}: {error}"}


def compare_sets(current: RunSet, previous: RunSet) -> dict:
    mine = current.pack
    theirs = previous.pack
    if mine.get("id") != theirs.get("id") or mine.get("sha256") != theirs.get("sha256"):
        raise ReportError(
            f"compare needs two runs of the same pack: this run has {mine.get('id')} {str(mine.get('sha256'))[:12]}, "
            f"the other {theirs.get('id')} {str(theirs.get('sha256'))[:12]}"
        )
    before = {entry.key: entry for entry in previous.entries}
    rows = []
    for entry in current.entries:
        old = before.get(entry.key)
        if old is None:
            rows.append({"cell": entry.key, "slug": entry.slug, "verdict": entry.shown_verdict or entry.status, "previous_verdict": None, "verdict_changed": True, "note": "not in the other run"})
            continue
        now_verdict = entry.shown_verdict or entry.status
        then_verdict = old.shown_verdict or old.status
        duration = _change(entry.run_seconds, old.run_seconds)
        vram = None if entry.peak_vram_mb is None or old.peak_vram_mb is None else round(entry.peak_vram_mb - old.peak_vram_mb, 1)
        rows.append(
            {
                "cell": entry.key,
                "slug": entry.slug,
                "verdict": now_verdict,
                "previous_verdict": then_verdict,
                "verdict_changed": now_verdict != then_verdict,
                "run_seconds": entry.run_seconds,
                "previous_run_seconds": old.run_seconds,
                "duration_change": duration,
                "duration_flag": duration is not None and abs(duration) > DURATION_TOLERANCE,
                "peak_vram_mb": entry.peak_vram_mb,
                "previous_peak_vram_mb": old.peak_vram_mb,
                "vram_change_mb": vram,
                "vram_flag": vram is not None and abs(vram) > VRAM_TOLERANCE_MB,
                "ssim": _ssim(entry, old) if entry.result and old.result else {"value": None, "reason": "no output on one side"},
            }
        )
    missing = [key for key in before if key not in {entry.key for entry in current.entries}]
    mine_storage = _storage_key(current)
    theirs_storage = _storage_key(previous)
    storage = [
        {"where": where, "before": theirs_storage.get(where), "now": mine_storage.get(where)}
        for where in sorted(set(mine_storage) | set(theirs_storage))
        if mine_storage.get(where) != theirs_storage.get(where)
    ]
    hardware = []
    for label, now, then in (("GPU", current.gpu().get("name"), previous.gpu().get("name")), ("VRAM GB", current.gpu().get("vram_gb"), previous.gpu().get("vram_gb")), ("machine", current.machine, previous.machine)):
        if now != then:
            hardware.append(f"{label}: {then} then, {now} now")
    return {
        "previous": {"runs": [run.get("run_id") for run in previous.runs], "started_at": previous.started_at, "app_version": previous.first.get("app_version")},
        "rows": rows,
        "only_in_previous": missing,
        "storage_changes": storage,
        "storage_probed": bool(mine_storage) and bool(theirs_storage),
        "hardware_changes": hardware,
    }


def _gb(value, unit: float = 1e9) -> str:
    return "?" if value is None else f"{value / unit:.1f} GB"


def _seconds(value) -> str:
    return "" if value is None else f"{value:.0f} s" if value >= 10 else f"{value:.1f} s"


def _vram(value) -> str:
    if value is None:
        return ""
    return f"{value:.0f} MiB" if value < 1024 else f"{value / 1024:.1f} GiB"


def _klass(entry: Entry) -> str:
    verdict = entry.shown_verdict
    if verdict:
        return VERDICT_CLASS.get(verdict, "warn")
    return STATUS_CLASS.get(entry.status or "", "idle")


def _label(entry: Entry) -> str:
    return entry.shown_verdict or (entry.status or "unknown")


def _table(headers: list[str], rows: list[list[str]], css: str = "") -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table class="{css}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _facts(pairs: list[tuple[str, str]]) -> str:
    return '<dl class="facts">' + "".join(f"<div><dt>{escape(name)}</dt><dd>{value}</dd></div>" for name, value in pairs) + "</dl>"


def bias_factors(run_set: RunSet) -> list[str]:
    found = []
    mode = run_set.mode
    if mode == "shared":
        found.append("shared instance: the global queue was checked before each cell, but work outside the queue (a test suite, another container) is seen neither by the API nor by nvidia-smi")
    elif mode is None:
        found.append("the instance mode (dedicated or shared) was not recorded")
    windows = run_set.probe("windows")
    session = (windows or {}).get("session") or {}
    if session.get("lock_screen_up"):
        found.append("the Windows lock screen was up when the host was probed")
    if session.get("remote") or session.get("remote_session"):
        found.append("a Remote Desktop session was open when the host was probed: it changes the timings")
    linux = run_set.probe("linux")
    if (linux or {}).get("gpu_compute_processes"):
        found.append(f"{linux['gpu_compute_processes']} GPU compute processes were running when the container was probed")
    stopped = [run for run in run_set.runs if run.get("stopped")]
    for run in stopped:
        found.append(f"segment {run.get('run_id')}: {run['stopped']}")
    if len(run_set.runs) > 1:
        found.append(f"the run is made of {len(run_set.runs)} segments: the first cell of each segment loads its models cold")
    if run_set.instance is None and run_set.preflight is not None:
        found.append(f"hardware facts come from a preflight taken at {run_set.preflight.get('generated_at')}, not from the run")
    found.extend(run_set.notes)
    return found


def _machine_card(run_set: RunSet) -> str:
    gpu = run_set.gpu()
    stats = run_set.stats()
    windows = run_set.probe("windows")
    linux = run_set.probe("linux")
    driver = ((windows or {}).get("gpu") or {}).get("driver")
    ram = (stats.get("ram") or {}).get("total")
    cpu = (stats.get("cpu") or {}).get("core_count")
    if windows:
        os_text = f"{(windows.get('os') or {}).get('caption')} {(windows.get('os') or {}).get('version')}"
        if linux:
            os_text += f" · container kernel {linux.get('kernel')}"
    elif linux:
        os_text = f"Linux kernel {linux.get('kernel')}"
    else:
        os_text = "not probed"
    plugins = (run_set.instance or {}).get("plugins") or ((run_set.preflight or {}).get("instance") or {}).get("plugins") or []
    enabled = [f"{plugin.get('id')} {plugin.get('version')}" for plugin in plugins if plugin.get("enabled")]
    runner = run_set.first.get("runner") or {}
    pack = run_set.pack
    cases = run_set.first.get("cases") or {}
    pairs = [
        ("GPU", escape(f"{gpu.get('name') or 'unknown'} · {gpu.get('vram_gb') or '?'} GB · compute {gpu.get('compute_capability') or '?'}")),
        ("Driver", escape(driver or "not probed")),
        ("RAM", escape(f"{ram / 1024:.0f} GiB" if ram else "unknown") + (escape(f" · {cpu} CPU cores") if cpu else "")),
        ("Host OS", escape(os_text)),
        ("Application", escape(str(run_set.first.get("app_version") or "unknown"))),
        ("Plugins enabled", escape(", ".join(enabled) or "none recorded")),
        ("Pack", escape(f"{pack.get('id')} {pack.get('version')} · sha256 {str(pack.get('sha256'))[:12]}") + "<br>" + escape(f"cases {cases.get('file')} · sha256 {str(cases.get('sha256'))[:12]}")),
        ("Runner", escape(f"potion-audit {runner.get('potion_audit')} · Python {runner.get('python')} · {runner.get('platform')}") + "<br>" + escape(f"uv.lock {str(runner.get('uv_lock_sha256'))[:12]} · {reduce_home(runner.get('executable'))}")),
        ("Mode", escape(run_set.mode or "not recorded")),
        ("Profile", escape(str(run_set.first.get("profile") or "unknown"))),
    ]
    biases = bias_factors(run_set)
    bias_html = "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in biases) + "</ul>" if biases else '<p class="muted">None noted.</p>'
    return f'<div class="card">{_facts(pairs)}<h3>Bias factors</h3>{bias_html}</div>'


def _storage(run_set: RunSet) -> str:
    parts = []
    linux = run_set.probe("linux")
    windows = run_set.probe("windows")
    if linux:
        rows = []
        for path in linux.get("paths") or ():
            systems = ((path.get("findmnt") or {}).get("filesystems") or [{}])[0]
            total = path.get("total_bytes")
            free = path.get("free_bytes")
            rows.append([escape(str(path.get("path"))), escape(str(systems.get("fstype") or path.get("fs_type"))), escape(reduce_home(str(systems.get("source") or ""))), escape(_gb(total)), escape(_gb(free) + (f" ({100 * free / total:.0f} %)" if total and free is not None else ""))])
        parts.append(f"<h3>Container mounts <span class=\"muted small\">probed {escape(str(linux.get('generated_at')))}</span></h3>")
        parts.append(_table(["Path", "File system", "Source", "Total", "Free"], rows))
        read = linux.get("read_test")
        if read:
            parts.append(f"<p>Direct read of a model file: {escape(str(read.get('mib_per_second')))} MiB/s over {escape(_gb(read.get('read_bytes'), 2 ** 30).replace('GB', 'GiB'))} ({'direct I/O' if read.get('direct_io') else 'cached'}).</p>")
    if windows:
        disks = [[escape(str(disk.get("model"))), escape(str(disk.get("bus_type"))), escape(str(disk.get("media_type"))), escape(_gb(disk.get("size_bytes"))), escape(str(disk.get("firmware"))), escape(str(disk.get("health")))] for disk in windows.get("physical_disks") or ()]
        parts.append(f"<h3>Host disks <span class=\"muted small\">probed {escape(str(windows.get('generated_at')))}</span></h3>")
        parts.append(_table(["Model", "Bus", "Media", "Size", "Firmware", "Health"], disks))
        volumes = [[escape(f"{volume.get('drive')}:"), escape(str(volume.get("label") or "")), escape(str(volume.get("file_system"))), escape(_gb(volume.get("size_bytes"))), escape(_gb(volume.get("free_bytes")) + f" ({volume.get('free_percent')} %)")] for volume in windows.get("volumes") or ()]
        parts.append(_table(["Volume", "Label", "File system", "Size", "Free"], volumes))
        vhdx = [[escape(reduce_home(str(disk.get("path")))), escape(_gb(disk.get("size_bytes"))), escape(str(disk.get("drive")))] for disk in ((windows.get("docker_desktop") or {}).get("disks") or [])] + [[escape(reduce_home(str((distro.get("vhdx") or {}).get("path")))), escape(_gb((distro.get("vhdx") or {}).get("size_bytes"))), escape(str((distro.get("vhdx") or {}).get("drive")))] for distro in ((windows.get("wsl") or {}).get("distros") or []) if distro.get("vhdx")]
        if vhdx:
            parts.append(_table(["Virtual disk", "Size", "Drive"], vhdx))
    api_disk = {}
    for backend in (run_set.instance or {}).get("local_backends") or (((run_set.preflight or {}).get("hardware") or {}).get("local_backends") or []):
        for name, usage in ((backend.get("system_info") or {}).get("disk_usage") or {}).items():
            api_disk[f"{backend.get('id')}:{name}"] = usage
    if api_disk:
        rows = [[escape(name), escape(_gb(usage.get("total"))), escape(_gb(usage.get("free")) + (f" ({100 * usage['free'] / usage['total']:.0f} %)" if usage.get("total") and usage.get("free") is not None else ""))] for name, usage in api_disk.items()]
        parts.append("<h3>Space the API reports</h3>")
        parts.append(_table(["Location", "Total", "Free"], rows))
    if not linux and not windows:
        parts.insert(0, '<p class="muted">Not probed: this run has no probe file. Run the probes of <code>probe/</code> and pass their JSON with <code>--probe</code>.</p>')
    return "".join(parts)


def _cell_html(entry: Entry) -> str:
    klass = _klass(entry)
    was = f'<span class="was">{escape(entry.previous_verdict)}</span>' if entry.previous_verdict else ""
    lines = [f'<span class="tag">{"warm " if entry.warm else ""}{escape(_label(entry))}</span>{was}']
    numbers = " · ".join(value for value in (_seconds(entry.run_seconds), _vram(entry.peak_vram_mb)) if value)
    if numbers:
        lines.append(f'<div class="small">{escape(numbers)}</div>')
    elif entry.reason and not entry.verdict:
        lines.append(f'<div class="small muted">{escape(entry.reason[:70])}{"…" if len(entry.reason) > 70 else ""}</div>')
    thumb = next((item["thumb"] for item in entry.media if item.get("thumb")), None)
    if thumb:
        lines.append(f'<img src="{thumb}" alt="" loading="lazy" width="116" height="72">')
    title = escape(entry.reason or entry.key, quote=True)
    return f'<a class="cell {klass}" href="#{entry.slug}" title="{title}">{"".join(lines)}</a>'


def _matrix(run_set: RunSet) -> str:
    presets = []
    columns = []
    grid: dict[tuple[str, str], list[Entry]] = {}
    for entry in run_set.entries:
        if entry.preset not in presets:
            presets.append(entry.preset)
        if entry.column not in columns:
            columns.append(entry.column)
        grid.setdefault((entry.preset, entry.column), []).append(entry)
    head = "<th>Preset</th>" + "".join(f"<th>{escape(column)}</th>" for column in columns)
    rows = []
    for preset in presets:
        cells = "".join(f"<td>{''.join(_cell_html(entry) for entry in grid.get((preset, column), []))}</td>" for column in columns)
        rows.append(f"<tr><td>{escape(preset)}</td>{cells}</tr>")
    return f'<div class="scroll"><table class="matrix"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _media_html(entry: Entry) -> str:
    parts = []
    for item in entry.media:
        original = f' · <a href="{item["original"]}">original {escape(item["file"])}</a>' if item.get("original") else ""
        if item.get("error"):
            parts.append(f'<p class="tag bad">{escape(item["file"])}: {escape(item["error"])}</p>')
        if item["kind"] == "video" and item.get("display"):
            poster = f' poster="{item["thumb"]}"' if item.get("thumb") else ""
            parts.append(f'<video controls preload="none" playsinline{poster} src="{item["display"]}"></video><p class="small">reduced H.264 copy{original}</p>')
        elif item["kind"] == "image" and item.get("display"):
            parts.append(f'<img src="{item["display"]}" alt="{escape(item["file"], quote=True)}" loading="lazy"><p class="small">reduced copy{original}</p>')
        elif item.get("original") and item["file"].lower().endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a")):
            parts.append(f'<audio controls preload="none" src="{item["original"]}"></audio><p class="small">{original[3:]}</p>')
        elif item.get("original"):
            parts.append(f'<p class="small">{original[3:]}</p>')
    return f'<div class="media">{"".join(parts)}</div>' if parts else ""


def _history(run_report: dict) -> str:
    history = run_report.get("status_history") or []
    if not history:
        return ""
    start = None
    lines = []
    for item in history[:HISTORY_LINES]:
        at = item.get("at")
        offset = ""
        if at:
            moment = datetime.fromisoformat(at)
            start = start or moment
            offset = f"{(moment - start).total_seconds():7.1f} s  "
        lines.append(f"{offset}{plain(item.get('message'))} · {plain(item.get('step'))}")
    more = len(history) - HISTORY_LINES
    if more > 0:
        lines.append(f"… {more} more lines in run_report.json")
    return "<h3>Run report</h3><pre>" + escape("\n".join(lines)) + "</pre>"


def _detail(entry: Entry) -> str:
    result = entry.result or {}
    parts = []
    if entry.reason:
        parts.append(f"<p><strong>{escape(entry.status or '')}</strong>: {escape(entry.reason)}</p>")
    if entry.reevaluated:
        record = entry.reevaluated
        previous = record.get("previous") or {}
        text = f"Re-evaluated on {record.get('reevaluated_at')} with checks version {record.get('checks_version')}: {previous.get('verdict')} (checks version {previous.get('checks_version')}) → {record.get('verdict')}"
        parts.append(f'<p class="tag {"warn" if record.get("changed") else "idle"}">{escape(text)}</p>')
        if record.get("kept"):
            parts.append(f'<p class="small muted">{escape(record["kept"])}</p>')
    parts.append(_media_html(entry))
    if result:
        stats = result.get("generation_stats") or {}
        timing = result.get("timing") or {}
        memory = result.get("memory") or {}
        load_ms = stats.get("model_load_ms")
        duration_ms = stats.get("duration_ms")
        compute = (duration_ms - load_ms) / 1000 if duration_ms is not None and load_ms is not None else None
        facts = [
            ("Generation", escape(str(result.get("generation_id")))),
            ("Submitted", escape(str(result.get("submitted_at")))),
            ("Seed", escape(str(entry.seed))),
            ("Run time", escape(_seconds(timing.get("run_seconds")) or "?") + (escape(f" (estimated {_seconds(entry.estimate_seconds)})") if entry.estimate_seconds else "")),
            ("Model load", escape(_seconds(load_ms / 1000) if load_ms is not None else "not derived") + (" · cold start" if stats.get("cold_start") else " · warm" if stats.get("cold_start") is False else "")),
            ("Compute", escape(_seconds(compute) or "not derived")),
            ("Per step (polled)", escape(_seconds(timing.get("seconds_per_step_polled")) or "?")),
            ("Peak VRAM (preset stats)", escape(_vram(stats.get("peak_vram_mb")) or "not derived")),
            ("Peak VRAM (whole device, sampled)", escape(_vram(memory.get("peak_vram_used_mb_sampled")) or "?")),
            ("Peak RAM (whole host, sampled)", escape(_vram(memory.get("peak_ram_used_mb_sampled")) or "?")),
        ]
        parts.append(_facts(facts))
        if not stats.get("derived") and stats.get("reason"):
            parts.append(f'<p class="small muted">Statistics not derived: {escape(stats["reason"])}</p>')
        failure = result.get("failure")
        if failure:
            parts.append(f'<h3>Failure</h3><pre>{escape(json.dumps(failure, indent=1, ensure_ascii=False))}</pre>')
        checks = (entry.reevaluated or {}).get("checks") or result.get("checks") or []
        if checks:
            rows = [[f'<span class="tag {"ok" if check.get("ok") else "bad"}">{"ok" if check.get("ok") else "failed"}</span>', escape(str(check.get("check"))), escape(json.dumps(check.get("expected"), ensure_ascii=False)), escape(json.dumps(check.get("actual"), ensure_ascii=False))] for check in checks]
            parts.append("<h3>Checks</h3>" + _table(["", "Check", "Expected", "Actual"], rows))
        pipes = timing.get("pipe_seconds") or {}
        if pipes:
            parts.append("<h3>Pipe times</h3><pre>" + escape("  ".join(f"{pipe}: {seconds:.1f} s" for pipe, seconds in pipes.items())) + "</pre>")
    if entry.request:
        prompts = (entry.request.get("prompts") or [{}])[0]
        form = {key: value for key, value in (entry.request.get("form_data") or {}).items()}
        parts.append("<h3>Prompt</h3><pre>" + escape(str(prompts.get("positive") or "")) + "</pre>")
        if prompts.get("negative"):
            parts.append("<h3>Negative prompt</h3><pre>" + escape(str(prompts["negative"])) + "</pre>")
        parts.append("<h3>Settings</h3><pre>" + escape(json.dumps(form, indent=1, ensure_ascii=False)) + "</pre>")
    if entry.run_report:
        parts.append(_history(entry.run_report))
    summary = f'<span class="tag {_klass(entry)}">{escape(_label(entry))}</span>'
    if entry.previous_verdict:
        summary += f'<span class="was">{escape(entry.previous_verdict)}</span>'
    summary += f" {escape(entry.key)}"
    return f'<details id="{entry.slug}"><summary>{summary}</summary><div class="body">{"".join(parts)}</div></details>'


def _compare_html(comparison: dict) -> str:
    previous = comparison["previous"]
    parts = [f"<p>Against {escape(', '.join(str(run) for run in previous['runs']))} (application {escape(str(previous['app_version']))}, started {escape(str(previous['started_at']))}). Durations are flagged beyond ±{DURATION_TOLERANCE:.0%}, peak VRAM beyond ±{VRAM_TOLERANCE_MB:.0f} MiB. SSIM compares outputs of the same seed and size (1.0 is identical).</p>"]
    for line in comparison["hardware_changes"]:
        parts.append(f'<p class="tag warn">Hardware changed: {escape(line)}</p>')
    rows = []
    for row in comparison["rows"]:
        interesting = row.get("verdict_changed") or row.get("duration_flag") or row.get("vram_flag") or ((row.get("ssim") or {}).get("value") is not None and row["ssim"]["value"] < 0.9)
        if not interesting:
            continue
        ssim = row.get("ssim") or {}
        duration = row.get("duration_change")
        rows.append([
            f'<a href="#{row["slug"]}">{escape(row["cell"])}</a>',
            escape(f"{row.get('previous_verdict')} → {row.get('verdict')}") if row.get("verdict_changed") else escape(str(row.get("verdict"))),
            escape(f"{_seconds(row.get('previous_run_seconds'))} → {_seconds(row.get('run_seconds'))}" + (f" ({duration:+.0%})" if duration is not None else "")),
            escape(f"{row['vram_change_mb']:+.0f} MiB" if row.get("vram_change_mb") is not None else ""),
            escape(f"{ssim['value']:.3f}" if ssim.get("value") is not None else str(ssim.get("reason") or "")),
        ])
    parts.append(_table(["Cell", "Verdict", "Run time", "Peak VRAM", "SSIM"], rows) if rows else '<p class="muted">No verdict changed, no duration beyond the tolerance, no VRAM change beyond the tolerance, no SSIM under 0.9.</p>')
    if comparison["only_in_previous"]:
        parts.append(f"<p>Only in the other run: {escape(', '.join(comparison['only_in_previous']))}</p>")
    if not comparison["storage_probed"]:
        parts.append('<p class="muted">Disks and mounts: not compared, one of the runs has no probe file.</p>')
    elif comparison["storage_changes"]:
        rows = [[escape(item["where"]), escape(str(item["before"])), escape(str(item["now"]))] for item in comparison["storage_changes"]]
        parts.append("<h3>Disk or mount changes</h3>" + _table(["Where", "Before", "Now"], rows))
    else:
        parts.append("<p>Disks and mounts: no change.</p>")
    return "".join(parts)


def _counts(run_set: RunSet) -> str:
    verdicts = {}
    statuses = {}
    for entry in run_set.entries:
        if entry.shown_verdict:
            verdicts[entry.shown_verdict] = verdicts.get(entry.shown_verdict, 0) + 1
        else:
            statuses[entry.status or "unknown"] = statuses.get(entry.status or "unknown", 0) + 1
    changed = sum(1 for entry in run_set.entries if entry.previous_verdict)
    text = " · ".join(f'<span class="tag {VERDICT_CLASS.get(name, "warn")}">{escape(name)} {count}</span>' for name, count in sorted(verdicts.items()))
    rest = " · ".join(f"{escape(name)} {count}" for name, count in sorted(statuses.items()))
    extra = f" · {changed} verdicts changed by a re-evaluation" if changed else ""
    return f'<p class="legend">{text}{extra}</p><p class="small muted">Not run: {rest or "none"}</p>'


def _page(title: str, subtitle: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style><script>{SCRIPT}</script></head><body>"
        f"<h1>{escape(title)}</h1><p class=\"muted\">{subtitle}</p>{body}"
        f'<p class="small muted">Written by potion-audit {escape(__version__)} on {escape(datetime.now(UTC).isoformat(timespec="seconds"))}.</p></body></html>\n'
    )


def render_report(run_set: RunSet, comparison: dict | None = None) -> str:
    pack = run_set.pack
    subtitle = escape(f"{run_set.machine} · {pack.get('id')} {pack.get('version')} · {run_set.first.get('profile')} profile · {run_set.started_at} to {run_set.ended_at} · runs {', '.join(str(run.get('run_id')) for run in run_set.runs)}")
    body = [
        _counts(run_set),
        "<h2>Machine</h2>",
        _machine_card(run_set),
        "<h2>Storage</h2>",
        _storage(run_set),
    ]
    if comparison is not None:
        body += ["<h2>Compared with the previous run</h2>", _compare_html(comparison)]
    body += [
        "<h2>Matrix</h2>",
        '<p class="small muted">Presets in rows, modes in columns. A cell gives its verdict (or why it did not run), the run time and the peak VRAM of the preset statistics; click it for the details.</p>',
        _matrix(run_set),
        "<h2>Cells</h2>",
        "".join(_detail(entry) for entry in run_set.entries),
    ]
    return _page("Potion audit report", subtitle, "".join(body))


def _entry_json(entry: Entry) -> dict:
    return {
        "cell": entry.cell,
        "warm_repeat": entry.warm,
        "status": entry.status,
        "reason": entry.reason,
        "verdict": entry.shown_verdict,
        "previous_verdict": entry.previous_verdict,
        "run_seconds": entry.run_seconds,
        "peak_vram_mb": entry.peak_vram_mb,
        "run": entry.run_dir.name if entry.run_dir else None,
    }


def write_report(run_set: RunSet, out_dir: Path, comparison: dict | None = None, media: bool = True, log=print) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if media:
        prepare_media(run_set, out_dir, log)
    index = out_dir / "index.html"
    index.write_text(render_report(run_set, comparison), encoding="utf-8", newline="\n")
    data = {
        "schema": REPORT_SCHEMA,
        "runs": [run.get("run_id") for run in run_set.runs],
        "machine": run_set.machine,
        "pack": run_set.pack,
        "mode": run_set.mode,
        "bias_factors": bias_factors(run_set),
        "cells": [_entry_json(entry) for entry in run_set.entries],
        "compare": comparison,
    }
    (out_dir / "report.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return index


def group_by_machine(dirs: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for run_dir in dirs:
        try:
            run = load_run_json(run_dir)
        except ReevaluateError as error:
            raise ReportError(str(error)) from error
        groups.setdefault(str(run.get("machine") or "unnamed"), []).append(run_dir)
    return groups


def render_merge(sets: list[RunSet]) -> str:
    packs = {(run_set.pack.get("id"), run_set.pack.get("sha256")) for run_set in sets}
    if len(packs) > 1:
        raise ReportError("merge needs runs of the same pack: " + ", ".join(f"{run_set.machine} ran {run_set.pack.get('id')} {str(run_set.pack.get('sha256'))[:12]}" for run_set in sets))
    keys = []
    by_machine = []
    for run_set in sets:
        table = {entry.key: entry for entry in run_set.entries}
        by_machine.append(table)
        for entry in run_set.entries:
            if entry.key not in keys:
                keys.append(entry.key)
    head_rows = []
    for run_set in sets:
        gpu = run_set.gpu()
        linux = run_set.probe("linux")
        models = next((path for path in (linux or {}).get("paths") or () if "model" in str(path.get("path"))), None)
        disk = "not probed"
        if models:
            systems = ((models.get("findmnt") or {}).get("filesystems") or [{}])[0]
            disk = f"{systems.get('fstype') or models.get('fs_type')}" + (f", {linux['read_test']['mib_per_second']} MiB/s" if (linux.get("read_test") or {}).get("mib_per_second") else "")
        head_rows.append([escape(run_set.machine), escape(f"{gpu.get('name') or 'unknown'} {gpu.get('vram_gb') or '?'} GB"), escape(str(run_set.first.get("app_version"))), escape(run_set.mode or "not recorded"), escape(disk), escape(", ".join(str(run.get("run_id")) for run in run_set.runs))])
    rows = []
    for key in keys:
        cells = []
        for table in by_machine:
            entry = table.get(key)
            if entry is None:
                cells.append('<span class="muted">absent</span>')
                continue
            numbers = " · ".join(value for value in (_seconds(entry.run_seconds), _vram(entry.peak_vram_mb)) if value)
            was = f'<span class="was">{escape(entry.previous_verdict)}</span>' if entry.previous_verdict else ""
            cells.append(f'<div class="cell {_klass(entry)}" title="{escape(entry.reason or "", quote=True)}"><span class="tag">{escape(_label(entry))}</span>{was}<div class="small">{escape(numbers)}</div></div>')
        rows.append([escape(key)] + cells)
    pack = sets[0].pack
    body = [
        "<h2>Machines</h2>",
        _table(["Machine", "GPU", "Application", "Mode", "Models disk", "Runs"], head_rows),
        "<h2>Matrix</h2>",
        _table(["Cell"] + [run_set.machine for run_set in sets], rows, "matrix"),
    ]
    return _page("Potion audit, several machines", escape(f"{pack.get('id')} {pack.get('version')} · sha256 {str(pack.get('sha256'))[:12]} · {len(sets)} machines"), "".join(body))


def write_merge(sets: list[RunSet], out_dir: Path) -> Path:
    page = render_merge(sets)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8", newline="\n")
    return index
