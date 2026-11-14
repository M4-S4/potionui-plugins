from html import escape

STYLE = """
:root { color-scheme: light dark; --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #d2d2d7; --ok: #1a7f37; --warn: #9a6700; --bad: #cf222e; }
@media (prefers-color-scheme: dark) { :root { --bg: #16171a; --fg: #ececec; --muted: #9a9aa0; --line: #33343a; --ok: #3fb950; --warn: #d29922; --bad: #f85149; } }
body { background: var(--bg); color: var(--fg); font: 14px/1.45 system-ui, sans-serif; margin: 0 auto; max-width: 1200px; padding: 16px; }
h1 { font-size: 22px; } h2 { font-size: 17px; margin-top: 28px; border-bottom: 1px solid var(--line); padding-bottom: 4px; }
table { border-collapse: collapse; width: 100%; display: block; overflow-x: auto; }
th, td { border-bottom: 1px solid var(--line); padding: 4px 8px; text-align: left; vertical-align: top; white-space: nowrap; }
th { color: var(--muted); font-weight: 600; }
.ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); } .muted { color: var(--muted); }
code { font-size: 12px; }
"""

VERDICT_CLASS = {
    "ready": "ok",
    "beyond_tier": "warn",
    "model_missing": "warn",
    "model_unresolved": "bad",
    "preset_not_installed": "bad",
    "cloud_excluded": "muted",
}

PACK_CLASS = {
    "ready": "ok",
    "input_pending": "warn",
    "beyond_tier": "warn",
    "model_missing": "warn",
    "model_unresolved": "bad",
    "preset_not_installed": "bad",
    "mode_missing": "bad",
    "plugin_inactive": "muted",
    "excluded": "muted",
}


def _gib(value) -> str:
    if value is None:
        return "?"
    return f"{value / 1024 ** 3:.1f} GiB"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _list(items: list[str], css: str) -> str:
    if not items:
        return '<p class="ok">None.</p>'
    return "<ul>" + "".join(f'<li class="{css}">{escape(item)}</li>' for item in items) + "</ul>"


def _cell_reason(cell: dict) -> str:
    parts = [cell["reason"]] if cell.get("reason") else []
    if cell.get("undeclared_fields"):
        parts.append("fields the form does not declare: " + ", ".join(cell["undeclared_fields"]))
    if cell.get("form_error"):
        parts.append("form not read: " + cell["form_error"])
    return "; ".join(parts)


def render(preflight: dict) -> str:
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>Potion audit preflight</title><style>{STYLE}</style></head><body>",
        "<h1>Potion audit preflight</h1>",
        f"<p class=\"muted\">{escape(preflight.get('generated_at', ''))} · machine {escape(preflight.get('machine', ''))} · "
        f"target {escape(preflight['target']['url'])} ({escape(preflight['target']['mode'])})</p>",
        "<h2>Blocking</h2>",
        _list(preflight.get("blocking", []), "bad"),
        "<h2>Warnings</h2>",
        _list(preflight.get("warnings", []), "warn"),
    ]
    summary = preflight.get("summary")
    if summary:
        parts.append("<h2>Summary</h2>")
        parts.append(
            _table(
                ["Presets", "Without cases", "Cases", "Ready", "Models", "Present", "Missing", "Missing size", "No sha256"],
                [[
                    str(summary["presets"]),
                    str(summary["presets_without_cases"]),
                    str(summary["cases"]),
                    str(summary["cases_ready"]),
                    str(summary["models"]),
                    str(summary["models_present"]),
                    str(summary["models_missing"]),
                    _gib(summary["missing_bytes"]) + (f" + {summary['missing_unknown_size']} unknown" if summary["missing_unknown_size"] else ""),
                    str(summary["models_unresolved"]),
                ]],
            )
        )
        verdicts = ", ".join(f"{escape(name)} {count}" for name, count in sorted(summary["verdicts"].items()))
        parts.append(f"<p>Case verdicts: {verdicts}.</p>")
    instance = preflight.get("instance")
    if instance:
        parts.append("<h2>Instance</h2>")
        settings = ", ".join(f"{escape(key)} = {escape(str(value))}" for key, value in instance["settings"].items())
        parts.append(f"<p>Application {escape(str(instance['app_version']))}. Settings: {settings}.</p>")
        parts.append(
            _table(
                ["Plugin", "Version", "Enabled", "Source"],
                [[escape(str(p["id"])), escape(str(p["version"])), escape(str(p["enabled"])), escape(str(p["source"]))] for p in instance["plugins"]],
            )
        )
    hardware = preflight.get("hardware")
    if hardware:
        gpu = hardware.get("gpu_profile") or {}
        parts.append("<h2>Hardware</h2>")
        parts.append(
            f"<p>GPU {escape(str(gpu.get('name')))}, {escape(str(gpu.get('vram_gb')))} GB, "
            f"{escape(str(gpu.get('generation_label')))}, compute {escape(str(gpu.get('compute_capability')))}.</p>"
        )
        ram = (hardware.get("stats") or {}).get("ram") or {}
        cpu = (hardware.get("stats") or {}).get("cpu") or {}
        parts.append(f"<p>RAM {escape(str(ram.get('total')))} MB, CPU {escape(str(cpu.get('core_count')))} cores.</p>")
    disk = preflight.get("disk")
    if disk:
        parts.append("<h2>Disk space exposed by the API</h2>")
        parts.append(
            _table(
                ["Location", "Total", "Free", "Free %"],
                [[escape(name), _gib(usage["total"]), _gib(usage["free"]), escape(str(usage["free_percent"]))] for name, usage in disk.items()],
            )
        )
    queue = preflight.get("queue")
    if queue:
        parts.append(f"<h2>Global queue</h2><p>{queue['running']} running, {queue['pending']} pending.</p>")
    presets = preflight.get("presets")
    if presets:
        parts.append("<h2>Presets</h2>")
        rows = []
        for preset in presets:
            version_css = "ok" if preset["version_match"] else "bad"
            rows.append([
                escape(preset["key"]),
                escape(preset["origin"]),
                escape(str(preset["engine"])),
                "yes" if preset["installed"] else '<span class="bad">no</span>',
                f'<span class="{version_css}">{escape(str(preset["installed_version"]))}</span> / {escape(str(preset["expected_version"]))}',
                "yes" if preset["assigned_to_me"] else "no",
                escape(str(preset["min_vram_gb"])),
                escape(preset["tier"]),
                str(preset["case_count"]),
            ])
        parts.append(_table(["Preset", "Origin", "Engine", "Installed", "Version (instance / cases)", "Assigned to audit user", "Min VRAM", "Tier", "Cases"], rows))
    cases = preflight.get("cases")
    if cases:
        parts.append("<h2>Cases</h2>")
        rows = []
        for case in cases:
            css = VERDICT_CLASS.get(case["verdict"], "")
            rows.append([
                escape(case["preset_key"]),
                escape(str(case["name"])),
                escape(case["mode"]),
                escape(", ".join(case["tags"])),
                f"{case['models_present']}/{case['models_total']}",
                _gib(case["missing_bytes"]) if case["missing_bytes"] else "",
                f'<span class="{css}">{escape(case["verdict"])}</span>',
            ])
        parts.append(_table(["Preset", "Case", "Mode", "Tags", "Models present", "Missing size", "Verdict"], rows))
    models = preflight.get("models")
    if models:
        for title, wanted in (("Missing models", False), ("Models without a sha256 to look up", None)):
            selected = [model for model in models if model["present"] is wanted]
            parts.append(f"<h2>{title} ({len(selected)})</h2>")
            parts.append(
                _table(
                    ["File", "sha256", "Size", "Fields", "Source", "Used by"],
                    [[
                        escape(str(model["filename"])),
                        f"<code>{escape((model['sha256'] or '')[:16])}</code>",
                        _gib(model["expected_size_bytes"]),
                        escape(", ".join(model["fields"])),
                        escape(model["source"]),
                        escape(", ".join(model["used_by"])),
                    ] for model in selected],
                )
            )
    pack = preflight.get("pack")
    if pack:
        counts = ", ".join(f"{escape(name)} {count}" for name, count in sorted(pack["summary"].items()))
        parts.append(f"<h2>Pack {escape(pack['id'])} {escape(pack['version'])}</h2>")
        parts.append(f"<p>Cells: {counts}. Pack <code>{escape(pack['sha256'])}</code>, cases {escape(pack['cases']['file'])} <code>{escape(pack['cases']['sha256'])}</code>.</p>")
        rows = []
        for cell in pack["cells"]:
            css = PACK_CLASS.get(cell["status"], "")
            rows.append([
                escape(cell["id"]),
                escape(cell["source"]),
                escape(str(cell["case"] or "")),
                escape(", ".join(cell["profiles"])) + (" + warm" if cell["repeat_warm"] else ""),
                escape(", ".join(cell["inputs"])),
                f'<span class="{css}">{escape(cell["status"])}</span>',
                escape(_cell_reason(cell)),
            ])
        for cell in pack["uncovered"]:
            rows.append([escape(f"{cell['name']}:{cell['mode']}"), "", "", "", "", '<span class="bad">no_case</span>', escape(cell["reason"])])
        parts.append(_table(["Cell", "Source", "Case", "Profiles", "Inputs", "Status", "Reason"], rows))
    runner = preflight.get("runner") or {}
    parts.append(
        f"<h2>Runner</h2><p class=\"muted\">potion-audit {escape(str(runner.get('potion_audit')))}, Python {escape(str(runner.get('python')))}, "
        f"uv.lock <code>{escape(str(runner.get('uv_lock_sha256')))}</code>, cases {escape(str(preflight['cases_source'].get('file')))} "
        f"<code>{escape(str(preflight['cases_source'].get('sha256')))}</code>.</p>"
    )
    parts.append("</body></html>\n")
    return "\n".join(parts)
