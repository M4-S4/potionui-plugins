import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .cases import CaseFileError, import_from_core, load_cases, write_case_set
from .check import collect, write_preflight
from .client import ApiClient, ApiError, ApiUnreachable
from .config import ConfigError, credentials, load_config
from .coverage import ModelResolver, coverage, live_state
from .inputs import make_inputs
from .matrix import run_passed, run_profile
from .media import probe_image, probe_video, video_encoders, write_preview
from .pack import DEFAULT_PACK, PROFILES, PackError, load_pack, used_by, verify
from .plan import dry_run
from .reevaluate import ReevaluateError, reevaluate_run
from .report import ReportError, add_pack_cells, compare_sets, group_by_machine, load_set, write_merge, write_report
from .run import RunRefused, execute, select_case
from .vp_report import compare_scenarios, load_one_scenario, load_scenario, split_dirs
from .vp_scenario import add_vp_parser, vp_command

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_BLOCKED = 2
EXIT_STOPPED = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="potion-audit", description="Audit the default presets of a PotionUI instance over its API.")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="read-only preflight: version, hardware, presets, models, queue, disk")
    check.add_argument("--config", type=Path, default=Path("audit.toml"))
    check.add_argument("--out", type=Path, help="folder for preflight.json and preflight.html (default: <output_dir>/preflight)")
    check.add_argument("--pack", type=Path, nargs="?", const=DEFAULT_PACK, help="also report the coverage of a pack, cell by cell (default pack: pack/v1/pack.toml)")

    run = commands.add_parser("run", help="run cases on the instance's GPU")
    run.add_argument("--config", type=Path, default=Path("audit.toml"))
    run.add_argument("--only", help="<preset>:<mode> of the case file, or with --pack a cell id or a preset of the pack")
    run.add_argument("--pack", type=Path, nargs="?", const=DEFAULT_PACK, help="the cells of a pack profile: planned with --dry-run, run with --confirm-gpu")
    run.add_argument("--profile", choices=PROFILES, default="smoke")
    run.add_argument("--beyond-tier", action="store_true", help="plan the presets whose min_vram_gb is above the GPU")
    run.add_argument("--prompt", help="positive prompt in place of the case's own")
    run.add_argument("--timeout", type=float, help="seconds before the generation is cancelled")
    run.add_argument("--interval", type=float, default=2.0, help="seconds between two status polls")
    run.add_argument("--run-id", help="name of the run folder (default: <date>-<machine>)")
    run.add_argument("--dry-run", action="store_true", help="check the queue, look the models up and write the requests, without submitting them")
    run.add_argument("--confirm-gpu", action="store_true", help="required unless --dry-run: the operator agreed to use the GPU")
    run.add_argument("--keep-bundle", action="store_true", help="keep each export bundle next to the outputs taken from it")

    report = commands.add_parser("report", help="write index.html for one run, made of one or more segment folders, and a Video Producer scenario")
    report.add_argument("runs", type=Path, nargs="+", help="run folders, the segments of one run in order, a night folder with night.json, and a scenario folder with scenario.json")
    report.add_argument("--out", type=Path, help="report folder (default: <first run folder>/report)")
    report.add_argument("--compare", type=Path, nargs="+", help="run folders of an earlier run of the same pack, or the folder of an earlier scenario of the same pack")
    report.add_argument("--pack", type=Path, default=DEFAULT_PACK, help="pack whose excluded and left out cells are listed when its sha256 is the run's")
    report.add_argument("--preflight", type=Path, help="preflight.json to read the hardware from when the run has no instance.json")
    report.add_argument("--probe", type=Path, action="append", default=[], help="a probe JSON of the host or the container (repeatable)")
    report.add_argument("--note", action="append", default=[], help="a bias factor to print on the machine card (repeatable)")
    report.add_argument("--no-media", action="store_true", help="no thumbnails and no reduced copies")

    reevaluate = commands.add_parser("reevaluate", help="check the outputs and run reports of a run again with the current checks, without GPU or network")
    reevaluate.add_argument("runs", type=Path, nargs="+")
    reevaluate.add_argument("--pack", type=Path, default=DEFAULT_PACK)

    merge = commands.add_parser("merge", help="one page with a column per machine")
    merge.add_argument("runs", type=Path, nargs="+", help="run folders, night folders and scenario folders of several machines; the segments of one machine are put together, its scenario goes in its column")
    merge.add_argument("--out", type=Path, required=True)

    cases = commands.add_parser("cases", help="case files")
    cases_commands = cases.add_subparsers(dest="cases_command", required=True)
    importer = cases_commands.add_parser("import", help="build a case file from a core checkout (needs the cases group)")
    importer.add_argument("--core", type=Path, required=True, help="a git checkout of the core")
    importer.add_argument("--ref", required=True, help="commit to read, without checking it out")
    importer.add_argument("--label", default="core")
    importer.add_argument("--out", type=Path, required=True)

    pack = commands.add_parser("pack", help="the potion pack: prompts, frozen inputs and cells")
    pack_commands = pack.add_subparsers(dest="pack_command", required=True)
    verifier = pack_commands.add_parser("verify", help="check the inputs' sha256 and size, prompts, bindings, cases and coverage")
    verifier.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    verifier.add_argument("--allow-pending", action="store_true", help="accept inputs not made yet")
    verifier.add_argument("--json", action="store_true", help="print the problems as JSON")
    maker = pack_commands.add_parser("make-inputs", help="make the frozen inputs: generations on the instance, then transforms")
    maker.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    maker.add_argument("--config", type=Path, default=Path("audit.toml"))
    maker.add_argument("--only", help="make this input only")
    maker.add_argument("--transforms-only", action="store_true", help="redo the transforms from the inputs already made, without the instance")
    maker.add_argument("--run-id", help="name of the run folder (default: <date>-<machine>-inputs)")
    maker.add_argument("--timeout", type=float, help="seconds before a generation is cancelled")
    maker.add_argument("--interval", type=float, default=2.0)
    maker.add_argument("--confirm-gpu", action="store_true", help="required for generated inputs: the operator agreed to use the GPU")

    media = commands.add_parser("media", help="read media files with PyAV and Pillow")
    media_commands = media.add_subparsers(dest="media_command", required=True)
    probe = media_commands.add_parser("probe", help="metadata, decoded frames and black check of a video or an image")
    probe.add_argument("file", type=Path)
    probe.add_argument("--preview", type=Path, help="also write a reduced H.264 copy here")
    probe.add_argument("--max-height", type=int, default=360)
    media_commands.add_parser("encoders", help="video encoders of the bundled FFmpeg")
    add_vp_parser(commands)
    return parser


def _check(args) -> int:
    config = load_config(args.config)
    case_set = load_cases(config.cases_file)
    pack = load_pack(args.pack) if args.pack else None
    username, password = credentials(config.target, os.environ)
    client = ApiClient(config.target.url, config.target.timeout_seconds)
    preflight = collect(client, config, case_set, username, password)
    if pack is not None and client.authenticated and not any(item.startswith(("login_failed", "not_admin", "api_unreachable")) for item in preflight["blocking"]):
        preflight["pack"] = coverage(pack, ModelResolver(client), live_state(client))
    json_path, html_path = write_preflight(preflight, args.out or config.output_dir / "preflight")
    summary = preflight.get("summary") or {}
    print(f"preflight: {json_path}")
    print(f"preflight: {html_path}")
    if summary:
        print(
            f"{summary['cases_ready']}/{summary['cases']} cases ready, {summary['models_missing']} of {summary['models']} models missing "
            f"({summary['missing_bytes'] / 1024 ** 3:.1f} GiB known, {summary['missing_unknown_size']} of unknown size)"
        )
    if preflight.get("pack"):
        counts = ", ".join(f"{name} {count}" for name, count in sorted(preflight["pack"]["summary"].items()))
        print(f"pack {pack.id}: {counts}")
    for item in preflight["warnings"]:
        print(f"warning: {item}")
    for item in preflight["blocking"]:
        print(f"blocking: {item}", file=sys.stderr)
    return EXIT_BLOCKED if preflight["blocking"] else EXIT_OK


def _run(args) -> int:
    if not args.confirm_gpu and not args.dry_run:
        print("run uses the GPU of the instance: pass --confirm-gpu once the operator has agreed", file=sys.stderr)
        return EXIT_BLOCKED
    if not args.pack and not args.only:
        print("run needs --only <preset>:<mode>, or --pack to plan a profile", file=sys.stderr)
        return EXIT_BLOCKED
    config = load_config(args.config)
    username, password = credentials(config.target, os.environ)
    client = ApiClient(config.target.url, config.target.timeout_seconds)
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{config.machine}"
    if args.pack:
        pack = load_pack(args.pack)
        client.login(username, password)
        if args.dry_run:
            plan = dry_run(client, pack, args.profile, config.output_dir, run_id, beyond_tier=args.beyond_tier, only=args.only)
            return EXIT_FAIL if plan["summary"]["statuses"].get("request_error") else EXIT_OK
        try:
            run = run_profile(client, pack, args.profile, config.output_dir, run_id, beyond_tier=args.beyond_tier, only=args.only, machine=config.machine, mode=config.target.mode, host_probe=config.probe_file if config.probe_source == "file" else None, keep_bundle=args.keep_bundle, timeout=args.timeout, interval=args.interval)
        except KeyboardInterrupt:
            print("stopped: the running generation was cancelled, see run.json", file=sys.stderr)
            return EXIT_STOPPED
        return EXIT_OK if run_passed(run) else EXIT_FAIL
    case_set = load_cases(config.cases_file)
    case = select_case(case_set, args.only)
    client.login(username, password)
    try:
        result = execute(client, case_set, case, config.output_dir, run_id, dry_run=args.dry_run, prompt=args.prompt, timeout=args.timeout, interval=args.interval, keep_bundle=args.keep_bundle)
    except KeyboardInterrupt:
        print("stopped: the generation was cancelled", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK if result["verdict"] in {"PASS", "DRY_RUN"} else EXIT_FAIL


def _pack(args) -> int:
    pack = load_pack(args.pack)
    if args.pack_command == "verify":
        problems = verify(pack, allow_pending=args.allow_pending)
        errors = [problem for problem in problems if problem.severity == "error"]
        if args.json:
            print(json.dumps([problem.__dict__ for problem in problems], indent=1))
        else:
            for problem in problems:
                print(f"{problem.severity}: {problem.where}: {problem.message}")
            usage = used_by(pack)
            unused = [input_id for input_id, users in usage.items() if not users]
            for input_id in unused:
                print(f"warning: input {input_id}: no cell uses it")
            active = [cell for cell in pack.cells if not cell.exclude and cell.mode != "*"]
            print(f"pack {pack.id} {pack.version}: {len(pack.cells)} cells ({len(active)} active), {len(pack.inputs)} inputs, {len(errors)} errors")
        return EXIT_FAIL if errors else EXIT_OK
    errors = [problem for problem in verify(pack, allow_pending=True) if problem.severity == "error"]
    if errors:
        for problem in errors:
            print(f"error: {problem.where}: {problem.message}", file=sys.stderr)
        print("make-inputs refuses a pack that pack verify --allow-pending rejects", file=sys.stderr)
        return EXIT_BLOCKED
    if not args.transforms_only and not args.confirm_gpu:
        print("make-inputs generates on the instance's GPU: pass --confirm-gpu once the operator has agreed, or --transforms-only", file=sys.stderr)
        return EXIT_BLOCKED
    client = None
    out_root = Path(".")
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-inputs"
    if not args.transforms_only:
        config = load_config(args.config)
        username, password = credentials(config.target, os.environ)
        client = ApiClient(config.target.url, config.target.timeout_seconds)
        client.login(username, password)
        out_root = config.output_dir
        run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{config.machine}-inputs"
    elif args.config.exists():
        out_root = load_config(args.config).output_dir
    try:
        make_inputs(pack, client, out_root, run_id, only=args.only, transforms_only=args.transforms_only, timeout=args.timeout, interval=args.interval)
    except KeyboardInterrupt:
        print("stopped: the generation was cancelled", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK


def _cases(args) -> int:
    data = import_from_core(args.core, args.ref, args.label)
    write_case_set(data, args.out)
    print(f"{len(data['presets'])} presets, {len(data['cases'])} cases, {len(data['recipes'])} recipes from {data['source']['ref']}")
    unresolved = [f"{case['preset_key']}/{case['name']}:{model['field']}" for case in data["cases"] for model in case["models"] if model["source"].startswith("unresolved")]
    for item in unresolved:
        print(f"unresolved: {item}")
    return EXIT_OK


def _media(args) -> int:
    if args.media_command == "encoders":
        print("\n".join(video_encoders()))
        return EXIT_OK
    suffix = args.file.suffix.lower()
    info = probe_image(args.file) if suffix in {".png", ".jpg", ".jpeg", ".webp"} else probe_video(args.file)
    if args.preview:
        info["preview"] = write_preview(args.file, args.preview, args.max_height)
    print(json.dumps(info, indent=1))
    return EXIT_OK


def _report(args) -> int:
    matrix_dirs, scenario_dirs = split_dirs(args.runs)
    run_set = load_set(matrix_dirs, args.preflight, args.probe, args.note) if matrix_dirs else None
    scenario = load_one_scenario(scenario_dirs)
    if scenario is not None and run_set is None:
        scenario.notes = list(args.note)
    if run_set is not None and args.pack and args.pack.is_file():
        add_pack_cells(run_set, load_pack(args.pack))
    comparison = None
    scenario_comparison = None
    if args.compare:
        old_matrix, old_scenarios = split_dirs(args.compare)
        if old_matrix:
            if run_set is None:
                raise ReportError("--compare gives matrix runs, but the report has no matrix run")
            comparison = compare_sets(run_set, load_set(old_matrix))
        if old_scenarios:
            if scenario is None:
                raise ReportError("--compare gives a scenario, but the report has no scenario")
            scenario_comparison = compare_scenarios(scenario, load_one_scenario(old_scenarios))
    index = write_report(run_set, args.out or args.runs[0] / "report", comparison, media=not args.no_media, scenario=scenario, scenario_comparison=scenario_comparison)
    print(f"report: {index}")
    if comparison is not None:
        changed = [row["cell"] for row in comparison["rows"] if row.get("verdict_changed")]
        print(f"compare: {len(changed)} verdicts changed, {sum(1 for row in comparison['rows'] if row.get('duration_flag'))} durations beyond 20 %")
    if scenario_comparison is not None:
        changed = [row["step"] for row in scenario_comparison["rows"] if row.get("verdict_changed")]
        print(f"compare scenario: {len(changed)} verdicts changed, {sum(1 for row in scenario_comparison['rows'] if row.get('duration_flag'))} durations beyond 20 %, {sum(1 for row in scenario_comparison['rows'] if row.get('preset_changed'))} takes on another preset")
    return EXIT_OK


def _reevaluate(args) -> int:
    pack = load_pack(args.pack)
    for run_dir in args.runs:
        reevaluate_run(run_dir, pack)
    return EXIT_OK


def _merge(args) -> int:
    matrix_dirs, scenario_dirs = split_dirs(args.runs)
    sets = [load_set(dirs) for dirs in group_by_machine(matrix_dirs).values()]
    scenarios = {}
    for run_dir in scenario_dirs:
        scenario = load_scenario(run_dir)
        if scenario.machine in scenarios:
            raise ReportError(f"two scenarios of {scenario.machine} ({scenarios[scenario.machine].run_id} and {scenario.run_id}): merge takes one per machine")
        scenarios[scenario.machine] = scenario
    print(f"merge: {write_merge(sets, args.out, scenarios)}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"check": _check, "run": _run, "cases": _cases, "pack": _pack, "media": _media, "report": _report, "reevaluate": _reevaluate, "merge": _merge, "vp": vp_command}
    try:
        return handlers[args.command](args)
    except (ConfigError, CaseFileError, RunRefused, PackError, ReportError, ReevaluateError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    except ApiUnreachable as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    except ApiError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
