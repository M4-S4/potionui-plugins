import json
import os
import re
import shutil
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
from .vp_report import COLUMNS, ReportError, Scenario, VpStep, scenario_json

REPORT_SCHEMA = 1
DURATION_TOLERANCE = 0.20
VRAM_TOLERANCE_MB = 512.0
PREVIEW_HEIGHT = 540
HISTORY_LINES = 80
SSIM_FLAG = 0.9
ORIGINAL_COPY_LIMIT = 64 * 2 ** 20
WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):[\\/]")
DRVFS_OPTION = re.compile(r"(?:^|[;,])path=([A-Za-z]):[\\/]")
HOST_MOUNT = re.compile(r"/mnt/host/([A-Za-z])(?:/|$)")
GIT_BASH_PATH = re.compile(r"\b[A-Za-z]:/Program Files/Git/")
AUDIO = (".wav", ".mp3", ".flac", ".ogg", ".m4a")
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

LIGHT = "color-scheme: light; --bg: #f6f5f2; --card: #ffffff; --soft: #efece7; --fg: #1f1d1a; --muted: #625d55; --line: #e0dbd2; --ok: #16692c; --ok-bg: #e2f2e5; --bad: #a8261b; --bad-bg: #fbe4e1; --warn: #774d00; --warn-bg: #faefd6; --idle: #625d55; --idle-bg: #ece9e3; --accent: #6b3fa0; --shadow: 0 1px 2px rgba(31, 29, 26, .06);"
DARK = "color-scheme: dark; --bg: #131216; --card: #1c1b20; --soft: #26242b; --fg: #ebe8e3; --muted: #a8a39b; --line: #34323a; --ok: #5ccf7c; --ok-bg: #15301e; --bad: #ff8a80; --bad-bg: #3b1a19; --warn: #e8bb4f; --warn-bg: #352a12; --idle: #a8a39b; --idle-bg: #26242b; --accent: #bf9cf4; --shadow: none;"

STYLE = (
    f":root {{ {LIGHT} --mono: ui-monospace, \"Cascadia Mono\", Consolas, \"SF Mono\", Menlo, monospace; }}\n"
    f"@media (prefers-color-scheme: dark) {{ :root:not([data-theme=\"light\"]) {{ {DARK} }} }}\n"
    f":root[data-theme=\"dark\"] {{ {DARK} }}\n"
    + """
* { box-sizing: border-box; }
html { scroll-padding-top: 60px; }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; }
.page { max-width: 1280px; margin: 0 auto; padding: 0 16px 64px; }
header.top { padding: 28px 0 14px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -.01em; }
.subtitle { color: var(--muted); margin: 0; overflow-wrap: anywhere; }
nav.toc { position: sticky; top: 0; z-index: 5; display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; margin: 0 -16px; padding: 8px 16px; background: var(--bg); border-bottom: 1px solid var(--line); }
nav.toc::-webkit-scrollbar { display: none; }
nav.toc a { white-space: nowrap; text-decoration: none; color: var(--fg); font-size: 13px; font-weight: 600; padding: 5px 11px; border-radius: 999px; }
nav.toc a:hover { background: var(--soft); }
a { color: var(--accent); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
section.block { margin-top: 40px; }
h2 { font-size: 21px; line-height: 1.25; margin: 0 0 14px; padding-bottom: 8px; border-bottom: 2px solid var(--line); }
h3 { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin: 22px 0 8px; }
.muted { color: var(--muted); } .small { font-size: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; box-shadow: var(--shadow); }
.card > h3:first-child { margin-top: 0; }
.facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px 24px; margin: 0; }
.facts div { min-width: 0; } .facts dt { color: var(--muted); font-size: 12px; } .facts dd { margin: 0; overflow-wrap: anywhere; }
.headline { font-size: 18px; font-weight: 650; margin: 0 0 14px; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.tile { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; min-width: 0; box-shadow: var(--shadow); }
.tile.t-ok { border-top: 4px solid var(--ok); } .tile.t-bad { border-top: 4px solid var(--bad); } .tile.t-warn { border-top: 4px solid var(--warn); }
.tile.wide { grid-column: 1 / -1; }
.tile.wide ul { columns: 2 22em; column-gap: 28px; }
.tile.wide li { break-inside: avoid; }
.card > ul { margin: 0; }
.tile .label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
.tile .big { font-size: 30px; font-weight: 700; line-height: 1.2; margin: 4px 0; font-variant-numeric: tabular-nums; }
.tile .big small { font-size: 15px; font-weight: 500; color: var(--muted); }
.tile p { margin: 4px 0 0; font-size: 13px; }
.tile ul { margin: 6px 0 0; padding-left: 18px; font-size: 13px; }
.tile li { overflow-wrap: anywhere; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 7px 10px; text-align: left; vertical-align: top; }
tbody tr:last-child td { border-bottom: none; }
th { color: var(--muted); font-weight: 600; font-size: 12px; white-space: nowrap; background: var(--soft); }
.num { text-align: right; font-family: var(--mono); font-size: 13px; font-variant-numeric: tabular-nums; white-space: nowrap; }
th.num { font-family: inherit; font-size: 12px; }
table.matrix { width: max-content; min-width: 100%; }
table.matrix th:first-child, table.matrix td:first-child { position: sticky; left: 0; z-index: 1; background: var(--card); font-weight: 600; max-width: 180px; overflow-wrap: anywhere; box-shadow: 1px 0 0 var(--line); }
table.matrix th:first-child { background: var(--soft); }
table.matrix td { padding: 6px; }
table.matrix .cell { width: 136px; }
.cell { display: block; text-decoration: none; color: inherit; border-radius: 8px; padding: 6px 7px; margin-bottom: 4px; overflow-wrap: anywhere; }
.cell .nums { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.cell .mode { font-size: 12px; font-weight: 600; margin-bottom: 3px; overflow-wrap: anywhere; }
table.matrix.by-preset { width: 100%; }
table.matrix.by-preset td:first-child { width: 180px; }
.modes { display: flex; flex-wrap: wrap; gap: 6px; }
.modes .cell { margin: 0; }
.num .reason { font-family: inherit; font-size: 12px; color: var(--muted); white-space: normal; }
.pair-card { max-width: 1000px; }
.cell img { display: block; width: 120px; height: 74px; object-fit: cover; border-radius: 5px; margin-top: 5px; background: var(--idle-bg); }
.tag { display: inline-block; font-weight: 700; font-size: 11.5px; line-height: 1.5; letter-spacing: .03em; padding: 0 7px; border: 1px solid currentColor; border-radius: 999px; white-space: nowrap; }
.ok { background: var(--ok-bg); } .ok .tag, .tag.ok { color: var(--ok); }
.bad { background: var(--bad-bg); } .bad .tag, .tag.bad { color: var(--bad); }
.warn { background: var(--warn-bg); } .warn .tag, .tag.warn { color: var(--warn); }
.idle { background: var(--idle-bg); } .idle .tag, .tag.idle { color: var(--idle); }
.off { background: none; border: 1px dashed var(--line); } .off .tag, .tag.off { color: var(--muted); border-style: dashed; }
.tag.ok, .tag.bad, .tag.warn, .tag.idle, .tag.off { background: var(--card); }
.tile .tag, .group h3 .tag { margin: 2px 2px 0 0; }
.check { display: block; margin-top: 3px; font-size: 12px; overflow-wrap: anywhere; }
.was { color: var(--muted); font-weight: 400; text-decoration: line-through; margin-left: 4px; font-size: 12px; }
.note { margin: 8px 0; padding: 6px 10px; border-left: 3px solid currentColor; border-radius: 0 6px 6px 0; font-size: 13px; overflow-wrap: anywhere; }
.note.ok { color: var(--ok); } .note.bad { color: var(--bad); } .note.warn { color: var(--warn); } .note.idle { color: var(--idle); }
.omitted { font-size: 13px; color: var(--muted); margin: 10px 0 0; }
.group { margin-top: 26px; }
.group h3 { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; text-transform: none; letter-spacing: 0; font-size: 16px; color: var(--fg); margin: 0 0 8px; }
details { background: var(--card); border: 1px solid var(--line); border-radius: 10px; margin: 6px 0; }
details > summary { cursor: pointer; list-style: none; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; padding: 8px 12px; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "\\25B8"; color: var(--muted); width: 1em; }
details[open] > summary::before { content: "\\25BE"; }
summary .name { font-weight: 600; flex: 1 1 14em; min-width: 0; overflow-wrap: anywhere; }
summary .nums { font-family: var(--mono); font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
summary .nums span { display: inline-block; min-width: 8ch; text-align: right; }
summary .why { font-size: 12px; color: var(--muted); flex-basis: 100%; padding-left: 1.6em; }
details > .body { padding: 2px 16px 16px; border-top: 1px solid var(--line); }
details:target, details[open] { border-color: var(--accent); }
pre { background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; overflow-x: auto; font: 12px/1.45 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
video, .media img, figure img { display: block; max-width: 100%; height: auto; border-radius: 6px; background: #000; }
.media { margin-top: 12px; } .media p { margin: 4px 0 12px; }
audio { width: 100%; }
.pairs { display: grid; gap: 14px; }
.pair-card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
.pair-card > p { margin: 0 0 8px; font-weight: 600; overflow-wrap: anywhere; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
figure { margin: 0; min-width: 0; } figure video { width: 100%; } figcaption { font-size: 12px; color: var(--muted); margin-top: 4px; }
ul { padding-left: 20px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
a.totop { position: fixed; right: 16px; bottom: 16px; z-index: 6; text-decoration: none; font-size: 13px; font-weight: 600; color: var(--fg); background: var(--card); border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; box-shadow: 0 2px 10px rgba(0, 0, 0, .18); }
footer { margin-top: 40px; }
@media (max-width: 720px) { .pair { grid-template-columns: 1fr; } }
@media (max-width: 640px) { body { font-size: 14px; } h1 { font-size: 22px; } h2 { font-size: 18px; } .tile .big { font-size: 26px; } table.matrix th:first-child, table.matrix td:first-child { max-width: 100px; font-size: 12px; } table.matrix .cell { width: 118px; } table.matrix.by-preset td:first-child { width: 92px; } .cell img { width: 102px; height: 64px; } summary .nums span { min-width: 0; } details > .body { padding: 2px 12px 12px; } }
"""
)

SCRIPT = """
function openTarget() { var id = decodeURIComponent(location.hash.slice(1)); if (!id) return; var node = document.getElementById(id); if (!node) return; for (var parent = node; parent; parent = parent.parentElement) { if (parent.tagName === 'DETAILS') parent.open = true; } node.scrollIntoView(); }
window.addEventListener('hashchange', openTarget); window.addEventListener('DOMContentLoaded', openTarget);
"""


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
        return self.generation_stats.get("peak_vram_mb")

    @property
    def generation_stats(self) -> dict:
        rederived = (self.reevaluated or {}).get("generation_stats") or {}
        if rederived and not rederived.get("kept"):
            return rederived
        return (self.result or {}).get("generation_stats") or {}

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
    nights: list[dict] = field(default_factory=list)

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


def _night_records(dirs: list[Path]) -> list[dict]:
    found = {}
    for run_dir in dirs:
        for path in sorted(run_dir.parent.glob("*/night.json")):
            data = _json(path)
            if isinstance(data, dict) and run_dir.name in {str(segment.get("run_id")) for segment in data.get("segments") or ()}:
                found[str(path)] = data
    return list(found.values())


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
    return RunSet(dirs=list(dirs), runs=runs, entries=_load_entries(list(dirs), runs), preflight=preflight_data, instance=instance, probes=probe_data, notes=list(notes or ()), nights=_night_records(list(dirs)))


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


def _origin(folder: Path, root: Path | None) -> str:
    if root is None:
        return folder.name
    try:
        return Path(os.path.relpath(folder, root)).as_posix()
    except ValueError:
        return folder.name


def _copy(source: Path, target: Path) -> None:
    if not _fresh(source, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _prepare_output(source: Path, kind: str | None, stem: Path, out_dir: Path, log, key: str) -> dict:
    item = {"file": source.name, "kind": kind, "origin": None, "display": None, "thumb": None, "copy": None, "error": None}
    if not source.is_file():
        item["error"] = "the output file is not in the run folder"
        return item
    try:
        if kind == "video":
            display = stem.with_suffix(".mp4")
            if not _fresh(source, display):
                write_preview(source, display, PREVIEW_HEIGHT)
            item["display"] = _href(display, out_dir)
        elif kind == "image":
            display = stem.with_suffix(".webp")
            if not _fresh(source, display):
                write_display_image(source, display)
            item["display"] = _href(display, out_dir)
        if kind in {"video", "image"}:
            thumb = stem.with_name(stem.name + ".thumb.jpg")
            if not _fresh(source, thumb):
                write_thumbnail(source, thumb, kind, THUMB_SIDE)
            item["thumb"] = _href(thumb, out_dir)
    except (av.error.FFmpegError, OSError, ValueError, RuntimeError) as error:
        item["error"] = f"{type(error).__name__}: {error}"
        log(f"{key}: media {source.name}: {item['error']}")
    if item["display"] is None:
        size = source.stat().st_size
        if size <= ORIGINAL_COPY_LIMIT:
            target = stem.parent / source.name
            _copy(source, target)
            item["copy"] = _href(target, out_dir)
        else:
            item["error"] = item["error"] or f"the original ({_gb(size)}) is larger than the {ORIGINAL_COPY_LIMIT // 2 ** 20} MiB a report copies"
    return item


def _prepare_entry(entry: Entry, out_dir: Path, media_root: Path, log) -> None:
    entry.media = []
    for output in (entry.result or {}).get("outputs") or ():
        source = entry.folder / output["file"]
        item = _prepare_output(source, output.get("kind"), media_root / entry.slug / Path(output["file"]).stem, out_dir, log, entry.key)
        item["origin"] = _origin(source.parent, entry.run_dir.parent if entry.run_dir else None)
        entry.media.append(item)


def prepare_media(run_set: RunSet, out_dir: Path, log=print) -> None:
    for entry in run_set.entries:
        _prepare_entry(entry, out_dir, out_dir / "media", log)


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def windows_name(windows: dict | None) -> str:
    info = (windows or {}).get("os") or {}
    build = _int(info.get("build")) or _int(str(info.get("version") or "").rsplit(".", 1)[-1])
    name = info.get("name") or ("Windows" if build is None else "Windows 11" if build >= 22000 else "Windows 10")
    text = " ".join(str(part) for part in (name, info.get("display_version")) if part)
    return f"{text} · build {build}" if build is not None else text


def _drive(text) -> str | None:
    if not isinstance(text, str):
        return None
    found = WINDOWS_DRIVE.match(text) or DRVFS_OPTION.search(text) or HOST_MOUNT.search(text)
    return found.group(1).upper() if found else None


def _short_path(path) -> str:
    parts = [part for part in re.split(r"[\\/]+", str(path or "")) if part]
    return "\\".join(parts[-2:]) if parts else ""


def virtual_disks(windows: dict | None) -> list[dict]:
    found: dict[str, dict] = {}
    windows = windows or {}
    sources = [(disk, "Docker Desktop") for disk in (windows.get("docker_desktop") or {}).get("disks") or ()]
    sources += [(distro.get("vhdx"), f"WSL distribution {distro.get('name')}") for distro in (windows.get("wsl") or {}).get("distros") or () if distro.get("vhdx")]
    for disk, role in sources:
        key = str(disk.get("path")).lower()
        known = found.get(key)
        if known is None:
            found[key] = {"path": disk.get("path"), "size_bytes": disk.get("size_bytes"), "drive": _drive(str(disk.get("drive") or "") + ":\\") or _drive(disk.get("path")), "roles": [role]}
        elif role not in known["roles"]:
            known["roles"].append(role)
    return list(found.values())


def _api_paths(run_set: RunSet) -> list[str]:
    found = []

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and WINDOWS_DRIVE.match(value):
            found.append(value)

    for backend in (run_set.instance or {}).get("local_backends") or (((run_set.preflight or {}).get("hardware") or {}).get("local_backends") or []):
        walk(backend.get("system_info") or {})
    return found


def storage_use(run_set: RunSet) -> dict:
    windows = run_set.probe("windows") or {}
    linux = run_set.probe("linux")
    uses: dict[str, list[str]] = {}

    def add(drive, why):
        if drive and why not in uses.setdefault(drive, []):
            uses[drive].append(why)

    for path in (linux or {}).get("paths") or ():
        for system in (path.get("findmnt") or {}).get("filesystems") or ():
            add(_drive(system.get("source")) or _drive(system.get("options")), f"container mount {path.get('path')}")
    disks = virtual_disks(windows)
    for disk in disks:
        for role in disk["roles"]:
            add(disk["drive"], f"virtual disk of {role}")
    for path in _api_paths(run_set):
        add(_drive(path), "storage path the API declares")
    volumes = list(windows.get("volumes") or ())
    kept = [volume for volume in volumes if str(volume.get("drive") or "").upper() in uses]
    by_drive = {}
    for partition in windows.get("partitions") or ():
        if partition.get("drive"):
            by_drive.setdefault(str(partition["drive"]).upper(), set()).add(str(partition.get("disk")))
    numbers: dict[str, set[str]] = {}
    unlinked = []
    for volume in kept:
        drive = str(volume.get("drive")).upper()
        linked = {str(number) for number in volume["disk_numbers"]} if volume.get("disk_numbers") is not None else by_drive.get(drive)
        if linked:
            numbers[drive] = linked
        else:
            unlinked.append(drive)
    physical = list(windows.get("physical_disks") or ())
    used_numbers = set().union(*numbers.values()) if numbers else set()
    kept_disks = [disk for disk in physical if str(disk.get("device_id")) in used_numbers]
    return {
        "uses": uses,
        "volumes": kept,
        "disk_numbers": numbers,
        "disks": kept_disks,
        "virtual_disks": disks,
        "omitted_volumes": len(volumes) - len(kept),
        "total_volumes": len(volumes),
        "omitted_disks": len(physical) - len(kept_disks),
        "total_disks": len(physical),
        "unlinked": unlinked,
        "mounts_probed": bool((linux or {}).get("paths")),
    }


def _storage_key(run_set: RunSet) -> dict:
    found = {}
    linux = run_set.probe("linux")
    for path in (linux or {}).get("paths") or ():
        systems = ((path.get("findmnt") or {}).get("filesystems") or [{}])[0]
        found[f"container {path.get('path')}"] = f"{systems.get('fstype') or path.get('fs_type')} on {reduce_home(systems.get('source'))}"
    if run_set.probe("windows"):
        use = storage_use(run_set)
        for volume in use["volumes"]:
            found[f"volume {volume.get('drive')}:"] = f"{volume.get('file_system')} {_gb(volume.get('size_bytes'))}"
        for disk in use["disks"]:
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
    only_here = []
    for entry in current.entries:
        old = before.get(entry.key)
        if old is None:
            only_here.append(entry.key)
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
        if now != then and now is not None and then is not None:
            hardware.append(f"{label}: {then} then, {now} now")
    return {
        "previous": {"runs": [run.get("run_id") for run in previous.runs], "started_at": previous.started_at, "app_version": previous.first.get("app_version")},
        "rows": rows,
        "only_in_previous": missing,
        "only_in_this_run": only_here,
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
    return "< 0.1 GiB" if value < 102.4 else f"{value / 1024:.1f} GiB"


def _mib(value) -> str:
    return "" if value is None else f"{value:,.0f} MiB".replace(",", " ")


def _clock(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"


def _moment(text):
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


def _when(text) -> str:
    moment = _moment(text)
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%MZ") if moment and moment.tzinfo else str(text)


def _peak_text(value, stats: dict) -> str:
    if value is not None:
        return _mib(value)
    if stats.get("derived") and stats.get("peak_vram_source"):
        return f"not derivable: {stats['peak_vram_source']}"
    return "not derived"


def _klass(entry: Entry) -> str:
    verdict = entry.shown_verdict
    if verdict:
        return VERDICT_CLASS.get(verdict, "warn")
    return STATUS_CLASS.get(entry.status or "", "idle")


def _label(entry: Entry) -> str:
    return entry.shown_verdict or (entry.status or "unknown")


def _table(headers: list[str], rows: list[list[str]], css: str = "", numeric: tuple[int, ...] = ()) -> str:
    def attr(index: int) -> str:
        return ' class="num"' if index in numeric else ""

    head = "".join(f"<th{attr(index)}>{escape(header)}</th>" for index, header in enumerate(headers))
    body = "".join("<tr>" + "".join(f"<td{attr(index)}>{cell}</td>" for index, cell in enumerate(row)) + "</tr>" for row in rows)
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
        os_text = windows_name(windows)
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
        ("Runner", escape(f"potion-audit {runner.get('potion_audit')} · Python {runner.get('python')} · {runner.get('platform')}") + "<br>" + escape(f"uv.lock {str(runner.get('uv_lock_sha256'))[:12]}")),
        ("Mode", escape(run_set.mode or "not recorded")),
        ("Profile", escape(str(run_set.first.get("profile") or "unknown"))),
    ]
    biases = bias_factors(run_set)
    bias_html = "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in biases) + "</ul>" if biases else '<p class="muted">None noted.</p>'
    return f'<div class="card">{_facts(pairs)}</div><h3>Bias factors</h3><div class="card">{bias_html}</div>'


def _free(free, total) -> str:
    return _gb(free) + (f" ({100 * free / total:.0f} %)" if total and free is not None else "")


def _mounts_html(linux: dict) -> str:
    parts = [f"<h3>Container mounts <span class=\"muted small\">probed {escape(_when(linux.get('generated_at')))}</span></h3>"]
    rows = []
    for path in linux.get("paths") or ():
        systems = ((path.get("findmnt") or {}).get("filesystems") or [{}])[0]
        rows.append([escape(str(path.get("path"))), escape(str(systems.get("fstype") or path.get("fs_type"))), escape(reduce_home(str(systems.get("source") or ""))), escape(_gb(path.get("total_bytes"))), escape(_free(path.get("free_bytes"), path.get("total_bytes")))])
    if rows:
        parts.append(_table(["Path", "File system", "Source", "Total", "Free"], rows, numeric=(3, 4)))
    else:
        notes = [str(note) for note in linux.get("notes") or ()]
        parts.append('<p class="note warn">The container probe recorded no mount: none of the paths it was given exists in the container.</p>')
        if notes:
            parts.append('<ul class="small">' + "".join(f"<li>{escape(reduce_home(note))}</li>" for note in notes) + "</ul>")
        if any(GIT_BASH_PATH.search(note) for note in notes):
            parts.append('<p class="small muted">A path written <code>C:/Program Files/Git/…</code> is a container path that Git Bash rewrote before <code>docker exec</code> passed it on: run the probe again with <code>MSYS_NO_PATHCONV=1</code>.</p>')
    read = linux.get("read_test")
    if read:
        parts.append(f"<p>Direct read of a model file: {escape(str(read.get('mib_per_second')))} MiB/s over {escape(_gb(read.get('read_bytes'), 2 ** 30).replace('GB', 'GiB'))} ({'direct I/O' if read.get('direct_io') else 'cached'}).</p>")
    return "".join(parts)


def _host_storage_html(run_set: RunSet, windows: dict) -> str:
    use = storage_use(run_set)
    physical = {str(disk.get("device_id")): disk for disk in use["disks"]}
    parts = [f"<h3>Host storage the instance uses <span class=\"muted small\">probed {escape(_when(windows.get('generated_at')))}</span></h3>"]
    volume_rows = []
    for volume in use["volumes"]:
        drive = str(volume.get("drive")).upper()
        disks = ", ".join(str(physical[number].get("model")) for number in sorted(use["disk_numbers"].get(drive, ())) if number in physical) or "not linked"
        volume_rows.append([escape(f"{drive}:"), escape(str(volume.get("label") or "")), escape(str(volume.get("file_system"))), escape("; ".join(use["uses"].get(drive, ()))), escape(disks), escape(_gb(volume.get("size_bytes"))), escape(_free(volume.get("free_bytes"), volume.get("size_bytes")))])
    if volume_rows:
        parts.append(_table(["Volume", "Label", "File system", "Used for", "Disk", "Size", "Free"], volume_rows, numeric=(5, 6)))
    else:
        parts.append('<p class="muted">No volume of the host is known to hold anything the instance uses.</p>')
    if use["disks"]:
        rows = [[escape(str(disk.get("model"))), escape(str(disk.get("bus_type"))), escape(str(disk.get("media_type"))), escape(str(disk.get("health"))), escape(_gb(disk.get("size_bytes")))] for disk in use["disks"]]
        parts.append(_table(["Physical disk", "Bus", "Media", "Health", "Size"], rows, numeric=(4,)))
    if use["virtual_disks"]:
        rows = [[escape(_short_path(reduce_home(str(disk.get("path"))))), escape(" · ".join(disk["roles"])), escape(f"{disk['drive']}:" if disk.get("drive") else "?"), escape(_gb(disk.get("size_bytes")))] for disk in use["virtual_disks"]]
        parts.append(_table(["Virtual disk", "Used by", "Volume", "Size"], rows, numeric=(3,)))
    omitted = []
    if use["omitted_disks"]:
        omitted.append(f"{use['omitted_disks']} of {use['total_disks']} physical disks")
    if use["omitted_volumes"]:
        omitted.append(f"{use['omitted_volumes']} of {use['total_volumes']} volumes")
    lines = []
    if omitted:
        lines.append(f"Not listed: {' and '.join(omitted)} of the host, which hold nothing the instance uses (no container mount, no virtual disk of Docker Desktop or WSL, no storage path the API declares).")
    if not use["mounts_probed"]:
        lines.append("The container probe recorded no mount, so a volume that only holds a folder mounted into the container is not recognised.")
    if use["unlinked"]:
        lines.append(f"The host probe does not link {', '.join(drive + ':' for drive in use['unlinked'])} to a physical disk, so its disk is not listed.")
    if lines:
        parts.append('<p class="omitted">' + escape(" ".join(lines)) + "</p>")
    return "".join(parts)


def _storage(run_set: RunSet) -> str:
    parts = []
    linux = run_set.probe("linux")
    windows = run_set.probe("windows")
    if linux:
        parts.append(_mounts_html(linux))
    if windows:
        parts.append(_host_storage_html(run_set, windows))
    api_disk = {}
    for backend in (run_set.instance or {}).get("local_backends") or (((run_set.preflight or {}).get("hardware") or {}).get("local_backends") or []):
        for name, usage in ((backend.get("system_info") or {}).get("disk_usage") or {}).items():
            api_disk[f"{backend.get('id')}:{name}"] = usage
    if api_disk:
        rows = [[escape(name), escape(_gb(usage.get("total"))), escape(_free(usage.get("free"), usage.get("total")))] for name, usage in api_disk.items()]
        parts.append("<h3>Space the API reports</h3>")
        parts.append(_table(["Location", "Total", "Free"], rows, numeric=(1, 2)))
    if not linux and not windows:
        parts.insert(0, '<p class="muted">Not probed: this run has no probe file. Run the probes of <code>probe/</code> and pass their JSON with <code>--probe</code>.</p>')
    return "".join(parts)


def _cell_html(entry: Entry) -> str:
    klass = _klass(entry)
    was = f'<span class="was">{escape(entry.previous_verdict)}</span>' if entry.previous_verdict else ""
    lines = [f'<div class="mode">{escape(entry.column)}{" · warm" if entry.warm else ""}</div><span class="tag">{escape(_label(entry))}</span>{was}']
    numbers = " · ".join(value for value in (_seconds(entry.run_seconds), _vram(entry.peak_vram_mb)) if value)
    if numbers:
        lines.append(f'<div class="small nums">{escape(numbers)}</div>')
    elif entry.reason and not entry.verdict:
        lines.append(f'<div class="small muted">{escape(entry.reason[:70])}{"…" if len(entry.reason) > 70 else ""}</div>')
    thumb = next((item["thumb"] for item in entry.media if item.get("thumb")), None)
    if thumb:
        lines.append(f'<img src="{thumb}" alt="" loading="lazy" width="116" height="72">')
    title = escape(entry.reason or entry.key, quote=True)
    return f'<a class="cell {klass}" href="#{entry.slug}" title="{title}">{"".join(lines)}</a>'


def _matrix(run_set: RunSet) -> str:
    presets: dict[str, list[Entry]] = {}
    for entry in run_set.entries:
        presets.setdefault(entry.preset, []).append(entry)
    rows = "".join(f'<tr><td>{escape(preset)}</td><td><div class="modes">{"".join(_cell_html(entry) for entry in entries)}</div></td></tr>' for preset, entries in presets.items())
    return f'<div class="scroll"><table class="matrix by-preset"><thead><tr><th>Preset</th><th>Modes</th></tr></thead><tbody>{rows}</tbody></table></div>'


def _where(item: dict) -> str:
    return f"original {item['file']}" + (f", kept in the run folder {item['origin']}" if item.get("origin") else "")


def _item_html(item: dict) -> str:
    parts = []
    if item.get("error"):
        parts.append(f'<p class="note bad">{escape(item["file"])}: {escape(item["error"])}</p>')
    poster = f' poster="{item["thumb"]}"' if item.get("thumb") else ""
    if item.get("display") and item.get("kind") == "video":
        parts.append(f'<video controls preload="none" playsinline{poster} src="{item["display"]}"></video><p class="small muted">{escape("Reduced H.264 copy of the " + _where(item))}.</p>')
    elif item.get("display"):
        parts.append(f'<img src="{item["display"]}" alt="{escape(item["file"], quote=True)}" loading="lazy"><p class="small muted">{escape("Reduced copy of the " + _where(item))}.</p>')
    elif item.get("copy") and item["file"].lower().endswith(AUDIO):
        parts.append(f'<audio controls preload="none" src="{item["copy"]}"></audio><p class="small muted">Copy of the original <a href="{item["copy"]}">{escape(item["file"])}</a>.</p>')
    elif item.get("copy") and item.get("kind") == "video":
        parts.append(f'<video controls preload="none" playsinline{poster} src="{item["copy"]}"></video><p class="small muted">Copy of the original <a href="{item["copy"]}">{escape(item["file"])}</a>.</p>')
    elif item.get("copy"):
        parts.append(f'<p class="small">Copy of the original: <a href="{item["copy"]}">{escape(item["file"])}</a></p>')
    else:
        parts.append(f'<p class="small muted">{escape(_where(item)[0].upper() + _where(item)[1:])}.</p>')
    return "".join(parts)


def _media_html(entry: Entry) -> str:
    parts = [_item_html(item) for item in entry.media]
    return f'<div class="media">{"".join(parts)}</div>' if parts else ""


def _figure(entry: Entry | None, caption: str) -> str:
    item = next((item for item in (entry.media if entry else ()) if item.get("display") or item.get("copy")), None)
    if item is None:
        body = '<p class="small muted">No copy of the output in this report.</p>'
    elif item.get("kind") == "video":
        poster = f' poster="{item["thumb"]}"' if item.get("thumb") else ""
        body = f'<video controls preload="none" playsinline{poster} src="{item.get("display") or item.get("copy")}"></video>'
    else:
        body = f'<img src="{item.get("display") or item.get("copy")}" alt="{escape(item["file"], quote=True)}" loading="lazy">'
    return f"<figure>{body}<figcaption>{escape(caption)}</figcaption></figure>"


def ssim_rows(comparison: dict) -> list[dict]:
    return [row for row in comparison["rows"] if (row.get("ssim") or {}).get("value") is not None and row["ssim"]["value"] < SSIM_FLAG]


def prepare_pair_media(comparison: dict, previous: RunSet, out_dir: Path, log=print) -> None:
    flagged = {row["cell"] for row in ssim_rows(comparison)}
    for entry in previous.entries:
        if entry.key in flagged:
            _prepare_entry(entry, out_dir, out_dir / "media" / "previous", log)


def _pairs_html(comparison: dict, run_set: RunSet, previous: RunSet | None) -> str:
    rows = ssim_rows(comparison)
    if not rows:
        return ""
    now = {entry.key: entry for entry in run_set.entries}
    then = {entry.key: entry for entry in previous.entries} if previous else {}
    before = ", ".join(str(run) for run in comparison["previous"]["runs"])
    cards = []
    for row in rows:
        cards.append(
            f'<div class="pair-card"><p><a href="#{row["slug"]}">{escape(row["cell"])}</a> <span class="muted">· SSIM <span class="num">{row["ssim"]["value"]:.3f}</span></span></p>'
            f'<div class="pair">{_figure(then.get(row["cell"]), "Before: " + before)}{_figure(now.get(row["cell"]), "This run")}</div></div>'
        )
    return f'<h3>Outputs that changed <span class="muted small">SSIM under {SSIM_FLAG}</span></h3><div class="pairs">{"".join(cards)}</div>'


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
        parts.append(f'<p class="note {"warn" if record.get("changed") else "idle"}">{escape(text)}</p>')
        if record.get("kept"):
            parts.append(f'<p class="small muted">{escape(record["kept"])}</p>')
    parts.append(_media_html(entry))
    if result:
        stats = entry.generation_stats
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
            ("Peak VRAM (core record of the generation)", escape(_peak_text(stats.get("peak_vram_mb"), stats))),
            ("Peak VRAM (whole device, sampled)", escape(_mib(memory.get("peak_vram_used_mb_sampled")) or "?")),
            ("Peak RAM (whole host, sampled)", escape(_mib(memory.get("peak_ram_used_mb_sampled")) or "?")),
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
    was = f'<span class="was">{escape(entry.previous_verdict)}</span>' if entry.previous_verdict else ""
    summary = _summary_line(f'<span class="tag {_klass(entry)}">{escape(_label(entry))}</span>{was}', entry.key, entry.run_seconds, entry.peak_vram_mb, None if entry.verdict else entry.reason)
    return f'<details id="{entry.slug}"><summary>{summary}</summary><div class="body">{"".join(parts)}</div></details>'


def _summary_line(tag: str, name: str, seconds, vram, why: str | None) -> str:
    line = f'{tag}<span class="name">{escape(name)}</span>'
    if seconds is not None or vram is not None:
        line += f'<span class="nums"><span>{escape(_seconds(seconds))}</span> <span>{escape(_vram(vram))}</span></span>'
    if why:
        line += f'<span class="why">{escape(why[:140])}{"…" if len(why) > 140 else ""}</span>'
    return line


def _grouped(items: list, key, tag, detail) -> str:
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    parts = []
    for name, members in groups.items():
        counts: dict[tuple[str, str], int] = {}
        for member in members:
            found = tag(member)
            counts[found] = counts.get(found, 0) + 1
        tags = "".join(f'<span class="tag {klass}">{escape(label)} {count}</span>' for (label, klass), count in counts.items())
        parts.append(f'<section class="group"><h3>{escape(name)} {tags}</h3>{"".join(detail(member) for member in members)}</section>')
    return "".join(parts)


def _compare_html(comparison: dict, run_set: RunSet | None = None, previous: RunSet | None = None) -> str:
    previous_run = comparison["previous"]
    parts = [f"<p>Against {escape(', '.join(str(run) for run in previous_run['runs']))} (application {escape(str(previous_run['app_version']))}, started {escape(_when(previous_run['started_at']))}). Durations are flagged beyond ±{DURATION_TOLERANCE:.0%}, peak VRAM beyond ±{VRAM_TOLERANCE_MB:.0f} MiB. SSIM compares outputs of the same seed and size (1.0 is identical).</p>"]
    for line in comparison["hardware_changes"]:
        parts.append(f'<p class="note warn">Hardware changed: {escape(line)}</p>')
    rows = []
    for row in comparison["rows"]:
        interesting = row.get("verdict_changed") or row.get("duration_flag") or row.get("vram_flag") or ((row.get("ssim") or {}).get("value") is not None and row["ssim"]["value"] < SSIM_FLAG)
        if not interesting:
            continue
        ssim = row.get("ssim") or {}
        duration = row.get("duration_change")
        verdict = f'<span class="tag {VERDICT_CLASS.get(str(row.get("verdict")), "idle")}">{escape(str(row.get("verdict")))}</span>'
        if row.get("verdict_changed"):
            verdict = f'<span class="was">{escape(str(row.get("previous_verdict")))}</span> → {verdict}'
        rows.append([
            f'<a href="#{row["slug"]}">{escape(row["cell"])}</a>',
            verdict,
            escape(f"{_seconds(row.get('previous_run_seconds'))} → {_seconds(row.get('run_seconds'))}"),
            escape(f"{duration:+.0%}" if duration is not None else ""),
            escape(f"{row['vram_change_mb']:+,.0f} MiB".replace(",", " ") if row.get("vram_change_mb") is not None else ""),
            escape(f"{ssim['value']:.3f}") if ssim.get("value") is not None else f'<span class="reason">{escape(str(ssim.get("reason") or ""))}</span>',
        ])
    parts.append(_table(["Cell", "Verdict", "Run time", "Change", "Peak VRAM", "SSIM"], rows, numeric=(2, 3, 4, 5)) if rows else '<p class="muted">No verdict changed, no duration beyond the tolerance, no VRAM change beyond the tolerance, no SSIM under 0.9.</p>')
    if run_set is not None:
        parts.append(_pairs_html(comparison, run_set, previous))
    if comparison["only_in_this_run"]:
        parts.append(f"<p>Only in this run: {escape(', '.join(comparison['only_in_this_run']))}</p>")
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


def _verdict_tags(counts: dict[str, int], classes: dict[str, str]) -> str:
    return "".join(f'<span class="tag {classes.get(name, "warn")}">{escape(name)} {count}</span>' for name, count in counts.items())


def _is_verdict(value) -> bool:
    return isinstance(value, str) and value.isupper()


def changes(rows: list[dict]) -> dict[str, list[dict]]:
    found = {"fixed": [], "regressed": [], "newly run": [], "no longer run": []}
    for row in rows:
        if not row.get("verdict_changed"):
            continue
        now, then = row.get("verdict"), row.get("previous_verdict")
        if then == "PASS":
            found["regressed" if _is_verdict(now) else "no longer run"].append(row)
        elif now == "PASS":
            found["fixed" if _is_verdict(then) else "newly run"].append(row)
    return found


def _links(rows: list[dict], key: str) -> str:
    return "<ul>" + "".join(f'<li><a href="#{row["slug"]}">{escape(str(row[key]))}</a> <span class="muted">{escape(str(row.get("previous_verdict")))} → {escape(str(row.get("verdict")))}</span></li>' for row in rows) + "</ul>" if rows else ""


def _summary(run_set: RunSet | None, comparison: dict | None, scenario: Scenario | None, scenario_comparison: dict | None) -> str:
    tiles = []
    sentences = []
    starts = []
    ends = []
    measured = 0.0
    if run_set is not None:
        verdicts: dict[str, int] = {}
        statuses: dict[str, int] = {}
        for entry in run_set.entries:
            if entry.shown_verdict:
                verdicts[entry.shown_verdict] = verdicts.get(entry.shown_verdict, 0) + 1
            else:
                statuses[entry.status or "unknown"] = statuses.get(entry.status or "unknown", 0) + 1
            measured += entry.run_seconds or 0
        ran = sum(verdicts.values())
        passed = verdicts.get("PASS", 0)
        others = {name: count for name, count in sorted(verdicts.items()) if name != "PASS"}
        not_run = sum(statuses.values())
        reevaluated = sum(1 for entry in run_set.entries if entry.previous_verdict)
        body = f'<div class="big">{passed}<small> of {ran} cells passed</small></div>'
        if others:
            body += f'<div class="legend">{_verdict_tags(others, VERDICT_CLASS)}</div>'
        body += f"<p>Not run: {not_run}" + (f" ({escape(' · '.join(f'{name} {count}' for name, count in sorted(statuses.items())))})" if statuses else "") + "</p>"
        if reevaluated:
            body += f"<p>{reevaluated} verdicts changed by a re-evaluation.</p>"
        tiles.append(f'<div class="tile {"t-bad" if others else "t-ok"}"><div class="label">Matrix</div>{body}</div>')
        sentences.append(f"{passed} of {ran} cells passed" + (" · " + " · ".join(f"{count} {name}" for name, count in others.items()) if others else ""))
        starts.append(run_set.started_at)
        ends.append(run_set.ended_at)
    if scenario is not None:
        counts = scenario.counts()
        offered = sum(count for name, count in counts.items() if name in VERDICT_CLASS)
        passed = counts.get("PASS", 0)
        others = {name: count for name, count in sorted(counts.items()) if name != "PASS"}
        bad = {name: count for name, count in others.items() if name in VERDICT_CLASS}
        classes = {name: VERDICT_CLASS.get(name, "off" if name == "not offered" else "idle") for name in counts}
        body = f'<div class="big">{passed}<small> of {offered} steps passed</small></div>'
        if others:
            body += f'<div class="legend">{_verdict_tags(others, classes)}</div>'
        body += f"<p>{escape(scenario.run_id)} · {len(scenario.rows())} engines</p>"
        tiles.append(f'<div class="tile {"t-bad" if bad else "t-ok"}"><div class="label">Video Producer scenario</div>{body}</div>')
        sentences.append(f"{passed} of {offered} scenario steps passed")
        starts.append(scenario.data.get("started_at"))
        ends.append(scenario.data.get("ended_at"))
        measured += sum(step.seconds or 0 for step in scenario.steps)
    moments = [_moment(value) for value in starts if value]
    finishes = [_moment(value) for value in ends if value]
    begin = min((moment for moment in moments if moment), default=None)
    finish = max((moment for moment in finishes if moment), default=None)
    span = (finish - begin).total_seconds() if begin and finish else None
    body = f'<div class="big">{escape(_clock(span))}</div>'
    if begin and finish:
        body += f"<p>From {escape(_when(begin.isoformat()))} to {escape(_when(finish.isoformat()))}</p>"
    body += f"<p>{escape(_clock(measured))} of measured run time</p>"
    tiles.append(f'<div class="tile"><div class="label">Duration</div>{body}</div>')
    if run_set is not None:
        restarts = [item for night in run_set.nights for item in night.get("restarts") or ()]
        stopped = [run for run in run_set.runs if run.get("stopped")]
        if run_set.nights:
            body = f'<div class="big">{len(restarts)}</div>'
            body += "<ul>" + "".join(f"<li>{escape(_when(item.get('at')))} after the {escape(str(item.get('cell')))} cell</li>" for item in restarts) + "</ul>" if restarts else "<p>None.</p>"
        else:
            body = '<div class="big"><small>not recorded</small></div><p>No night record lists these segments.</p>'
        body += f"<p>{len(run_set.runs)} segments" + (f", {len(stopped)} stopped early" if stopped else "") + "</p>"
        tiles.append(f'<div class="tile {"t-warn" if restarts else ""}"><div class="label">Restarts</div>{body}</div>')
    if comparison is not None or scenario_comparison is not None:
        found = {"fixed": [], "regressed": [], "newly run": [], "no longer run": []}
        against = []
        body = ""
        for compared, key in ((comparison, "cell"), (scenario_comparison, "step")):
            if compared is None:
                continue
            for name, rows in changes(compared["rows"]).items():
                found[name] += [dict(row, name=row[key]) for row in rows]
        if comparison is not None:
            against.append(", ".join(str(run) for run in comparison["previous"]["runs"]))
        if scenario_comparison is not None:
            against.append(f"scenario {scenario_comparison['previous']['run_id']}")
        body += f'<div class="big">{len(found["fixed"])}<small> fixed</small> · {len(found["regressed"])}<small> regressed</small></div>'
        for name in ("regressed", "fixed", "no longer run", "newly run"):
            if found[name]:
                body += f"<p><strong>{escape(name.capitalize())}</strong></p>" + _links(found[name], "name")
        if comparison is not None:
            rows = comparison["rows"]
            flags = [
                (len(ssim_rows(comparison)), f"SSIM under {SSIM_FLAG}"),
                (sum(1 for row in rows if row.get("duration_flag")), f"run time beyond ±{DURATION_TOLERANCE:.0%}"),
                (sum(1 for row in rows if row.get("vram_flag")), f"peak VRAM beyond ±{VRAM_TOLERANCE_MB:.0f} MiB"),
            ]
            body += "<p>Cells with " + escape(" · ".join(f"{label}: {count}" for count, label in flags)) + '. <a href="#compare">See the comparison</a>.</p>'
        regressed = len(found["regressed"])
        tiles.append(f'<div class="tile wide {"t-bad" if regressed else "t-ok"}"><div class="label">Against {escape(" and ".join(against))}</div>{body}</div>')
        sentences.append(f"{regressed} regressed and {len(found['fixed'])} fixed against the previous run" if regressed else f"no regression against the previous run, {len(found['fixed'])} fixed")
    headline = f'<p class="headline">{escape("; ".join(sentences))}.</p>' if sentences else ""
    return headline + f'<div class="summary">{"".join(tiles)}</div>'


def _page(title: str, subtitle: str, body: str, nav: list[tuple[str, str]] = ()) -> str:
    links = "".join(f'<a href="#{anchor}">{escape(label)}</a>' for anchor, label in nav)
    toc = f'<nav class="toc" aria-label="Sections">{links}</nav>' if links else ""
    top = '<a class="totop" href="#top">↑ Top</a>' if links else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style><script>{SCRIPT}</script></head><body><div class=\"page\">"
        f'<header class="top" id="top"><h1>{escape(title)}</h1><p class="subtitle">{subtitle}</p></header>{toc}<main>{body}</main>'
        f'<footer><p class="small muted">Written by potion-audit {escape(__version__)} on {escape(datetime.now(UTC).isoformat(timespec="seconds"))}.</p></footer>'
        f"{top}</div></body></html>\n"
    )


def _block(anchor: str, title: str, content: str) -> str:
    return f'<section class="block"><h2 id="{anchor}">{escape(title)}</h2>{content}</section>'


def same_machine(run_set: RunSet, scenario: Scenario) -> None:
    if run_set.machine != scenario.machine:
        raise ReportError(f"the matrix ran on {run_set.machine} and the scenario on {scenario.machine}: use merge")
    version = run_set.first.get("app_version")
    if version != scenario.app_version:
        raise ReportError(f"the matrix ran application {version} and the scenario application {scenario.app_version}: give a matrix and a scenario of the same version")


def prepare_scenario_media(scenario: Scenario, out_dir: Path, log=print) -> None:
    media_root = out_dir / "media" / "vp"
    for step in scenario.steps:
        source = step.video
        if source is None:
            continue
        item = _prepare_output(source, "video", media_root / step.slug / source.stem, out_dir, log, step.key)
        if item["error"] == "the output file is not in the run folder":
            item["error"] = "the video is not in the run folder"
        item["origin"] = _origin(source.parent, scenario.dir.parent)
        step.media = item


def _step_klass(step: VpStep) -> str:
    if step.status == "skipped":
        return "off"
    if step.verdict:
        return VERDICT_CLASS.get(step.verdict, "warn")
    return STATUS_CLASS.get(step.status or "", "idle")


def _actual(value, limit: int = 60) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _check_lines(step: VpStep) -> str:
    lines = [f'<span class="check"><span class="tag {"ok" if check.get("ok") else "bad"}">{escape(str(check.get("check")))}</span> {escape(_actual(check.get("actual")))}</span>' for check in step.shot_checks]
    lines += [f'<span class="check" title="{escape(str(check.get("reason") or ""), quote=True)}"><span class="tag off">{escape(str(check.get("check")))}</span> not offered</span>' for check in step.not_offered_checks]
    return "".join(lines)


def _step_numbers(step: VpStep) -> str:
    return " · ".join(value for value in (_seconds(step.seconds), _vram(step.peak_vram_mb)) if value)


def _step_cell(step: VpStep, link: bool = True) -> str:
    lines = [f'<span class="tag">{escape(step.label)}</span>']
    numbers = _step_numbers(step)
    if numbers:
        lines.append(f'<div class="small">{escape(numbers)}</div>')
    elif step.reason and not step.verdict:
        lines.append(f'<div class="small muted">{escape(step.reason[:70])}{"…" if len(step.reason) > 70 else ""}</div>')
    if step.other_preset:
        lines.append(f'<div class="small">on {escape(step.other_preset)}</div>')
    lines.append(_check_lines(step))
    if link and step.media.get("thumb"):
        lines.append(f'<img src="{step.media["thumb"]}" alt="" loading="lazy" width="116" height="72">')
    title = escape(step.reason or step.key, quote=True)
    if not link:
        return f'<div class="cell {_step_klass(step)}" title="{title}">{"".join(lines)}</div>'
    return f'<a class="cell {_step_klass(step)}" href="#{step.slug}" title="{title}">{"".join(lines)}</a>'


def _scenario_table(scenario: Scenario) -> str:
    head = "<th>Engine</th>" + "".join(f"<th>{escape(label)}</th>" for _, _, label in COLUMNS)
    rows = []
    for engine, steps in scenario.rows():
        by_column = {step.column: step for step in steps}
        cells = "".join(f"<td>{_step_cell(by_column[label]) if label in by_column else ''}</td>" for _, _, label in COLUMNS)
        rows.append(f"<tr><td>{escape(engine)}</td>{cells}</tr>")
    return f'<div class="scroll"><table class="matrix"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _scenario_counts(scenario: Scenario) -> str:
    counts = scenario.counts()
    order = sorted(counts, key=lambda name: (name not in VERDICT_CLASS, name))
    parts = []
    for name in order:
        klass = VERDICT_CLASS.get(name, "off" if name == "not offered" else "idle")
        parts.append(f'<span class="tag {klass}">{escape(name)} {counts[name]}</span>')
    return f'<div class="legend">{"".join(parts)}</div>'


def _scenario_facts(scenario: Scenario) -> str:
    data = scenario.data
    plugin = data.get("plugin") or {}
    pack = scenario.pack
    cases = data.get("cases") or {}
    settings = data.get("settings") or {}
    final = data.get("final_pass") or {}
    runner = data.get("runner") or {}
    pairs = [
        ("Run", escape(f"{scenario.run_id} · {_when(data.get('started_at'))} to {_when(data.get('ended_at'))}")),
        ("Machine", escape(scenario.machine)),
        ("Application", escape(str(scenario.app_version or "unknown"))),
        ("Plugin", escape(f"{plugin.get('id')} {plugin.get('version')}")),
        ("Pack", escape(f"{pack.get('id')} {pack.get('version')} · sha256 {str(pack.get('sha256'))[:12]}") + "<br>" + escape(f"cases {cases.get('file')} · sha256 {str(cases.get('sha256'))[:12]}")),
        ("Settings", escape(", ".join(f"{name} {value}" for name, value in settings.items()) or "not recorded")),
        ("Final pass", escape(f"{final.get('upscaler')} · {final.get('cell')}" + ("" if final.get("allowed", True) else f" · not run: {final.get('reason')}"))),
        ("Matrix read", escape(", ".join(str(item) for item in data.get("matrix") or ()) or "none, engines named with --engines")),
        ("Runner", escape(f"potion-audit {runner.get('potion_audit')} · Python {runner.get('python')} · {runner.get('platform')}")),
    ]
    notes = []
    if data.get("stopped"):
        notes.append(str(data["stopped"]))
    if data.get("dry_run"):
        notes.append("this record is a dry run")
    notes.extend(scenario.notes)
    note_html = "<h3>Bias factors</h3><ul>" + "".join(f"<li>{escape(item)}</li>" for item in notes) + "</ul>" if notes else ""
    return f'<div class="card">{_facts(pairs)}{note_html}</div>'


def _looks_text(looks: dict | None) -> tuple[str, str]:
    if not looks:
        return "not read", "not read"
    if looks.get("error"):
        return escape(str(looks["error"])), ""
    seams = " · ".join(f"{item.get('previous_id')} → {item.get('shot_id')} {item.get('score')}" for item in looks.get("seams") or ()) or "none"
    lumi = []
    for item in looks.get("lumi") or ():
        identity = (item.get("identity") or {}).get("score")
        cards = ", ".join(f"{card.get('label') or card.get('card_id')} {card.get('score') if card.get('score') is not None else card.get('status')}" for card in item.get("cards") or ())
        lumi.append(f"identity {identity} · {cards}")
    return escape(seams), escape(" | ".join(lumi) or "no take of shot 3")


def _scenario_measures(scenario: Scenario) -> str:
    rows = []
    for entry in scenario.engines:
        if not entry.get("selected"):
            continue
        measures = entry.get("measures") or {}
        seam = measures.get("seam") or {}
        code = f"mean abs diff {seam.get('mean_abs_diff')} · PSNR {seam.get('psnr_db')} dB · {seam.get('size')}" if seam.get("measured") else (seam.get("reason") or "not measured")
        seams, lumi = _looks_text(measures.get("looks"))
        rows.append([escape(str(entry.get("key"))), escape(code), seams, lumi])
    if not rows:
        return ""
    return "<h3>Measures</h3>" + _table(["Engine", "Seam 1 → 2, by code", "Seam scores of the plugin", "Shot 3 against the Lumi card"], rows)


def _scenario_section(scenario: Scenario, comparison: dict | None) -> str:
    parts = [
        _scenario_counts(scenario),
        _scenario_facts(scenario),
        '<p class="small muted">Engines in rows, the steps of the scenario in columns. A cell gives its verdict, the run time (the polled time for the export), the peak VRAM when the preset statistics derived it, the preset the take ran on when it is not the engine (its statistics are read on that preset), the checks of the chained shot and of the shot with a first and a last image as recorded, and a thumbnail. A check marked not offered is one the engine cannot pass by design, such as the chaining checks of a text-to-video engine. A dashed cell is a step the engine does not offer: no refs mode, so no Ref2VA profile, or no last image, so no first and last frame shot.</p>',
        _scenario_table(scenario),
        _scenario_measures(scenario),
    ]
    if comparison is not None:
        parts += ["<h3>Compared with the previous scenario</h3>", _scenario_compare_html(comparison)]
    return "".join(parts)


def _scenario_compare_html(comparison: dict) -> str:
    previous = comparison["previous"]
    parts = [f"<p>Against the scenario {escape(str(previous['run_id']))} (application {escape(str(previous['app_version']))}, started {escape(_when(previous['started_at']))}). Durations are flagged beyond ±{DURATION_TOLERANCE:.0%}, peak VRAM beyond ±{VRAM_TOLERANCE_MB:.0f} MiB.</p>"]
    for line in comparison["changes"]:
        parts.append(f'<p class="note warn">Changed: {escape(line)}</p>')
    rows = []
    for row in comparison["rows"]:
        if not (row.get("verdict_changed") or row.get("duration_flag") or row.get("vram_flag") or row.get("preset_changed")):
            continue
        duration = row.get("duration_change")
        rows.append([
            f'<a href="#{row["slug"]}">{escape(row["step"])}</a>',
            escape(f"{row.get('previous_verdict')} → {row.get('verdict')}") if row.get("verdict_changed") else escape(str(row.get("verdict"))),
            escape(f"{_seconds(row.get('previous_seconds'))} → {_seconds(row.get('seconds'))}" + (f" ({duration:+.0%})" if duration is not None else "")),
            escape(f"{row['vram_change_mb']:+.0f} MiB" if row.get("vram_change_mb") is not None else ""),
            escape(f"{row.get('previous_stats_preset')} → {row.get('stats_preset')}") if row.get("preset_changed") else "",
        ])
    parts.append(_table(["Step", "Verdict", "Time", "Peak VRAM", "Preset of the statistics"], rows, numeric=(2, 3)) if rows else '<p class="muted">No verdict changed, no duration beyond the tolerance, no VRAM change beyond the tolerance, no take on another preset.</p>')
    if comparison["only_in_this_run"]:
        parts.append(f"<p>Only in this scenario: {escape(', '.join(comparison['only_in_this_run']))}</p>")
    if comparison["only_in_previous"]:
        parts.append(f"<p>Only in the other scenario: {escape(', '.join(comparison['only_in_previous']))}</p>")
    return "".join(parts)


def _step_media(step: VpStep) -> str:
    return f'<div class="media">{_item_html(step.media)}</div>' if step.media else ""


def _preset_text(found: dict) -> str:
    if not found:
        return "not recorded"
    name = found.get("name") or found.get("preset_id")
    text = f"{name} ({found.get('preset_id')}), from {found.get('source')}" if name != found.get("preset_id") else f"{name}, from {found.get('source')}"
    return text + (", not the preset the audit ordered" if found.get("differs") else "")


def _step_detail(step: VpStep) -> str:
    result = step.result or {}
    record = step.record
    parts = []
    if step.reason:
        parts.append(f"<p><strong>{escape(step.label)}</strong>: {escape(step.reason)}</p>")
    parts.append(_step_media(step))
    if result:
        take = result.get("take") or {}
        stats = result.get("generation_stats") or {}
        timing = result.get("timing") or {}
        memory = result.get("memory") or {}
        if step.kind == "export":
            job = result.get("job") or {}
            output = next(iter(result.get("outputs") or ()), {})
            facts = [
                ("Export job", escape(str(job.get("id")))),
                ("Format", escape(f"{job.get('format')} · {job.get('resolution')}")),
                ("Polled time", escape(_seconds(timing.get("polled_seconds")) or "?")),
                ("File", escape(f"{output.get('width')}x{output.get('height')} · {output.get('fps')} fps · {output.get('decoded_frames')} frames · {output.get('duration_seconds')} s" if output else "none")),
            ]
        else:
            facts = [
                ("Take", escape(str(take.get("id") or record.get("take_id")))),
                ("Generation", escape(str(result.get("generation_id")))),
                ("Profile", escape(str(take.get("profile")))),
                ("Director mode", escape(str(take.get("director_mode") or record.get("director_mode")))),
                ("Statistics read on", escape(_preset_text(step.stats_preset))),
                ("Run time", escape(_seconds(timing.get("run_seconds")) or "?")),
                ("Per step (polled)", escape(_seconds(timing.get("seconds_per_step_polled")) or "?")),
                ("Steps (polled)", escape(str(timing.get("total_steps_polled") or "?"))),
                ("Peak VRAM (core record of the generation)", escape(_peak_text(step.peak_vram_mb, stats))),
                ("Peak VRAM (whole device, sampled)", escape(_mib(memory.get("peak_vram_used_mb_sampled")) or "?")),
            ]
            if step.kind == "final_pass":
                facts.append(("Upscaler", escape(str(record.get("upscaler")))))
        parts.append(_facts(facts))
        if step.kind != "export" and not stats.get("derived") and stats.get("reason"):
            parts.append(f'<p class="small muted">Statistics not derived: {escape(stats["reason"])}</p>')
        for name in ("failure", "blocked"):
            if result.get(name):
                parts.append(f"<h3>{name.capitalize()}</h3><pre>{escape(json.dumps(result[name], indent=1, ensure_ascii=False))}</pre>")
        for check in step.not_offered_checks:
            parts.append(f'<p class="small"><span class="tag off">{escape(str(check.get("check")))}</span> not offered: {escape(str(check.get("reason")))}</p>')
        if step.checks:
            rows = [[f'<span class="tag {"ok" if check.get("ok") else "bad"}">{"ok" if check.get("ok") else "failed"}</span>', escape(str(check.get("check"))), escape(json.dumps(check.get("expected"), ensure_ascii=False)), escape(json.dumps(check.get("actual"), ensure_ascii=False))] for check in step.checks]
            parts.append("<h3>Checks</h3>" + _table(["", "Check", "Expected", "Actual"], rows))
    elif record.get("result"):
        parts.append('<p class="small muted">The result.json of this step is not in the run folder.</p>')
    summary = _summary_line(f'<span class="tag {_step_klass(step)}">{escape(step.label)}</span>', step.column, step.seconds, step.peak_vram_mb, None if step.verdict else step.reason)
    return f'<details id="{step.slug}"><summary>{summary}</summary><div class="body">{"".join(parts)}</div></details>'


def render_report(run_set: RunSet | None, comparison: dict | None = None, scenario: Scenario | None = None, scenario_comparison: dict | None = None, previous: RunSet | None = None) -> str:
    if run_set is None and scenario is None:
        raise ReportError("give a matrix run or a scenario")
    if run_set is not None and scenario is not None:
        same_machine(run_set, scenario)
    subtitles = []
    nav = [("summary", "Summary")]
    summary = _summary(run_set, comparison, scenario, scenario_comparison)
    body = [_block("summary", "Summary", summary)]
    if run_set is not None:
        pack = run_set.pack
        subtitles.append(f"{run_set.machine} · {pack.get('id')} {pack.get('version')} · {run_set.first.get('profile')} profile · {_when(run_set.started_at)} to {_when(run_set.ended_at)} · runs {', '.join(str(run.get('run_id')) for run in run_set.runs)}")
        body += [_block("machine", "Machine", _machine_card(run_set)), _block("storage", "Storage", _storage(run_set))]
        nav += [("machine", "Machine"), ("storage", "Storage")]
        if comparison is not None:
            body.append(_block("compare", "Compared with the previous run", _compare_html(comparison, run_set, previous)))
            nav.append(("compare", "Comparison"))
        body.append(_block("matrix", "Matrix", '<p class="small muted">One row per preset, one card per mode. A card gives its verdict (or why it did not run), the run time and the peak VRAM of the preset statistics; click it for the details.</p>' + _matrix(run_set)))
        nav.append(("matrix", "Matrix"))
    if scenario is not None:
        if run_set is None:
            subtitles.append(f"{scenario.machine} · {scenario.pack.get('id')} {scenario.pack.get('version')}")
        subtitles.append(f"scenario {scenario.run_id}")
        body.append(_block("vp", "Video Producer scenario", _scenario_section(scenario, scenario_comparison)))
        nav.append(("vp", "Scenario"))
    if run_set is not None:
        cells = _grouped(run_set.entries, lambda entry: entry.preset, lambda entry: (_label(entry), _klass(entry)), _detail)
        body.append(_block("cells", "Cells", f'<p class="small muted">{len(run_set.entries)} cells, grouped by preset. Each line gives the verdict, the run time and the peak VRAM; open it for the details.</p>' + cells))
        nav.append(("cells", "Cells"))
    if scenario is not None:
        steps = _grouped(scenario.steps, lambda step: step.engine, lambda step: (step.label, _step_klass(step)), _step_detail)
        body.append(_block("vp-steps", "Scenario steps", f'<p class="small muted">{len(scenario.steps)} steps, grouped by engine.</p>' + steps))
        nav.append(("vp-steps", "Steps"))
    return _page("Potion audit report", escape(" · ".join(subtitles)), "".join(body), nav)


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


def write_report(run_set: RunSet | None, out_dir: Path, comparison: dict | None = None, media: bool = True, log=print, scenario: Scenario | None = None, scenario_comparison: dict | None = None, previous: RunSet | None = None) -> Path:
    if run_set is None and scenario is None:
        raise ReportError("give a matrix run or a scenario")
    if run_set is not None and scenario is not None:
        same_machine(run_set, scenario)
    out_dir.mkdir(parents=True, exist_ok=True)
    if media and run_set is not None:
        prepare_media(run_set, out_dir, log)
        if comparison is not None and previous is not None:
            prepare_pair_media(comparison, previous, out_dir, log)
    if media and scenario is not None:
        prepare_scenario_media(scenario, out_dir, log)
    page = render_report(run_set, comparison, scenario, scenario_comparison, previous)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8", newline="\n")
    data = {
        "schema": REPORT_SCHEMA,
        "runs": [run.get("run_id") for run in run_set.runs] if run_set else [],
        "machine": run_set.machine if run_set else scenario.machine,
        "pack": run_set.pack if run_set else scenario.pack,
        "mode": run_set.mode if run_set else None,
        "bias_factors": bias_factors(run_set) if run_set else [],
        "cells": [_entry_json(entry) for entry in run_set.entries] if run_set else [],
        "compare": comparison,
        "scenario": scenario_json(scenario) if scenario else None,
        "scenario_compare": scenario_comparison,
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


def render_merge(sets: list[RunSet], scenarios: dict[str, Scenario] | None = None) -> str:
    scenarios = scenarios or {}
    packs = {(run_set.pack.get("id"), run_set.pack.get("sha256")) for run_set in sets}
    if len(packs) > 1:
        raise ReportError("merge needs runs of the same pack: " + ", ".join(f"{run_set.machine} ran {run_set.pack.get('id')} {str(run_set.pack.get('sha256'))[:12]}" for run_set in sets))
    scenario_packs = {(scenario.pack.get("id"), scenario.pack.get("sha256")) for scenario in scenarios.values()}
    if len(scenario_packs) > 1:
        raise ReportError("merge needs scenarios of the same pack: " + ", ".join(f"{scenario.machine} ran {scenario.pack.get('id')} {str(scenario.pack.get('sha256'))[:12]}" for scenario in scenarios.values()))
    by_name = {run_set.machine: run_set for run_set in sets}
    tables = {run_set.machine: {entry.key: entry for entry in run_set.entries} for run_set in sets}
    machines = [run_set.machine for run_set in sets] + [name for name in scenarios if name not in by_name]
    keys = []
    for run_set in sets:
        for entry in run_set.entries:
            if entry.key not in keys:
                keys.append(entry.key)
    head_rows = []
    for name in machines:
        run_set = by_name.get(name)
        scenario = scenarios.get(name)
        runs = [str(run.get("run_id")) for run in run_set.runs] if run_set else []
        if scenario is not None:
            runs.append(f"scenario {scenario.run_id}")
        if run_set is None:
            head_rows.append([escape(name), "not recorded", escape(str(scenario.app_version)), "not recorded", "not probed", escape(", ".join(runs))])
            continue
        gpu = run_set.gpu()
        linux = run_set.probe("linux")
        models = next((path for path in (linux or {}).get("paths") or () if "model" in str(path.get("path"))), None)
        disk = "not probed"
        if models:
            systems = ((models.get("findmnt") or {}).get("filesystems") or [{}])[0]
            disk = f"{systems.get('fstype') or models.get('fs_type')}" + (f", {linux['read_test']['mib_per_second']} MiB/s" if (linux.get("read_test") or {}).get("mib_per_second") else "")
        version = run_set.first.get("app_version")
        if scenario is not None and scenario.app_version != version:
            version = f"{version} (scenario {scenario.app_version})"
        head_rows.append([escape(name), escape(f"{gpu.get('name') or 'unknown'} {gpu.get('vram_gb') or '?'} GB"), escape(str(version)), escape(run_set.mode or "not recorded"), escape(disk), escape(", ".join(runs))])
    rows = []
    for key in keys:
        cells = []
        for name in machines:
            entry = tables.get(name, {}).get(key)
            if entry is None:
                cells.append('<span class="muted">absent</span>')
                continue
            numbers = " · ".join(value for value in (_seconds(entry.run_seconds), _vram(entry.peak_vram_mb)) if value)
            was = f'<span class="was">{escape(entry.previous_verdict)}</span>' if entry.previous_verdict else ""
            cells.append(f'<div class="cell {_klass(entry)}" title="{escape(entry.reason or "", quote=True)}"><span class="tag">{escape(_label(entry))}</span>{was}<div class="small">{escape(numbers)}</div></div>')
        rows.append([escape(key)] + cells)
    body = [
        "<h2>Machines</h2>",
        _table(["Machine", "GPU", "Application", "Mode", "Models disk", "Runs"], head_rows),
    ]
    if sets:
        body += ["<h2>Matrix</h2>", _table(["Cell"] + machines, rows, "matrix")]
    if scenarios:
        step_tables = {name: {step.key: step for step in scenario.steps} for name, scenario in scenarios.items()}
        step_keys = []
        for scenario in scenarios.values():
            for step in scenario.steps:
                if step.key not in step_keys:
                    step_keys.append(step.key)
        scenario_rows = []
        for key in step_keys:
            cells = []
            for name in machines:
                step = step_tables.get(name, {}).get(key)
                cells.append(_step_cell(step, link=False) if step else '<span class="muted">absent</span>')
            scenario_rows.append([escape(key)] + cells)
        body += ["<h2>Video Producer scenario</h2>", '<p class="small muted">One row per engine and step, one column per machine. A dashed cell is a step the engine does not offer.</p>', _table(["Step"] + machines, scenario_rows, "matrix")]
    pack = sets[0].pack if sets else next(iter(scenarios.values())).pack
    return _page("Potion audit, several machines", escape(f"{pack.get('id')} {pack.get('version')} · sha256 {str(pack.get('sha256'))[:12]} · {len(machines)} machines"), "".join(body))


def write_merge(sets: list[RunSet], out_dir: Path, scenarios: dict[str, Scenario] | None = None) -> Path:
    page = render_merge(sets, scenarios)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8", newline="\n")
    return index
