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
from .media import probe_image, probe_video, video_encoders, write_preview
from .run import RunRefused, execute, select_case

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

    run = commands.add_parser("run", help="run cases on the instance's GPU")
    run.add_argument("--config", type=Path, default=Path("audit.toml"))
    run.add_argument("--only", required=True, help="<preset>:<mode>, the preset as its folder name or id")
    run.add_argument("--prompt", help="positive prompt in place of the case's own")
    run.add_argument("--timeout", type=float, help="seconds before the generation is cancelled")
    run.add_argument("--interval", type=float, default=2.0, help="seconds between two status polls")
    run.add_argument("--run-id", help="name of the run folder (default: <date>-<machine>)")
    run.add_argument("--dry-run", action="store_true", help="check the queue, look the models up and write the request, without submitting it")
    run.add_argument("--confirm-gpu", action="store_true", help="required unless --dry-run: the operator agreed to use the GPU")

    cases = commands.add_parser("cases", help="case files")
    cases_commands = cases.add_subparsers(dest="cases_command", required=True)
    importer = cases_commands.add_parser("import", help="build a case file from a core checkout (needs the cases group)")
    importer.add_argument("--core", type=Path, required=True, help="a git checkout of the core")
    importer.add_argument("--ref", required=True, help="commit to read, without checking it out")
    importer.add_argument("--label", default="core")
    importer.add_argument("--out", type=Path, required=True)

    media = commands.add_parser("media", help="read media files with PyAV and Pillow")
    media_commands = media.add_subparsers(dest="media_command", required=True)
    probe = media_commands.add_parser("probe", help="metadata, decoded frames and black check of a video or an image")
    probe.add_argument("file", type=Path)
    probe.add_argument("--preview", type=Path, help="also write a reduced H.264 copy here")
    probe.add_argument("--max-height", type=int, default=360)
    media_commands.add_parser("encoders", help="video encoders of the bundled FFmpeg")
    return parser


def _check(args) -> int:
    config = load_config(args.config)
    case_set = load_cases(config.cases_file)
    username, password = credentials(config.target, os.environ)
    client = ApiClient(config.target.url, config.target.timeout_seconds)
    preflight = collect(client, config, case_set, username, password)
    json_path, html_path = write_preflight(preflight, args.out or config.output_dir / "preflight")
    summary = preflight.get("summary") or {}
    print(f"preflight: {json_path}")
    print(f"preflight: {html_path}")
    if summary:
        print(
            f"{summary['cases_ready']}/{summary['cases']} cases ready, {summary['models_missing']} of {summary['models']} models missing "
            f"({summary['missing_bytes'] / 1024 ** 3:.1f} GiB known, {summary['missing_unknown_size']} of unknown size)"
        )
    for item in preflight["warnings"]:
        print(f"warning: {item}")
    for item in preflight["blocking"]:
        print(f"blocking: {item}", file=sys.stderr)
    return EXIT_BLOCKED if preflight["blocking"] else EXIT_OK


def _run(args) -> int:
    if not args.confirm_gpu and not args.dry_run:
        print("run uses the GPU of the instance: pass --confirm-gpu once the operator has agreed", file=sys.stderr)
        return EXIT_BLOCKED
    config = load_config(args.config)
    case_set = load_cases(config.cases_file)
    case = select_case(case_set, args.only)
    username, password = credentials(config.target, os.environ)
    client = ApiClient(config.target.url, config.target.timeout_seconds)
    client.login(username, password)
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{config.machine}"
    try:
        result = execute(client, case_set, case, config.output_dir, run_id, dry_run=args.dry_run, prompt=args.prompt, timeout=args.timeout, interval=args.interval)
    except KeyboardInterrupt:
        print("stopped: the generation was cancelled", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK if result["verdict"] in {"PASS", "DRY_RUN"} else EXIT_FAIL


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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"check": _check, "run": _run, "cases": _cases, "media": _media}
    try:
        return handlers[args.command](args)
    except (ConfigError, CaseFileError, RunRefused) as error:
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
