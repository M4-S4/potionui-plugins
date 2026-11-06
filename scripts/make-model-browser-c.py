"""Generate model-browser-c, the Model Browser with the CivArchive source, from a git ref.

model-browser-c is published in its own repository (M4-S4/model-browser-c), never on the
PotionUI fork: the official marketplace keeps CivArchive out. Its source is the `civarchive`
branch of this repo (main + one commit that brings CivArchive back); this script turns the
`model-browser/` folder of that ref into the variant:

  * plugin id `model-browser-c`, name "Model Browser C", API prefix /api/plugins/model-browser-c
    and page route /plugins/model-browser-c (the core keeps page routes unique across every
    installed plugin, enabled or not, and a duplicate makes the whole plugin scan fail);
    tables, notification types, limit kinds and the enrichment provider id stay those of
    model-browser, so the two plugins are exclusive and an instance can switch from one to
    the other without losing rights, requests or plan limits;
  * README with a short "variant" paragraph and the minimum PotionUI version (it is
    installed in content/plugins/local/, so it does not ship with the core);
  * no PLAN.md (development notes), PotionUI's LICENSE (GPL-3.0) added;
  * variants/model-browser-c/ of the ref becomes .github/: README.github.md is the page GitHub
    shows for the repository (.github/README.md wins over the root README.md, which stays the
    plugin's help page inside PotionUI, where relative images would not load), next to its
    screenshots/.

Usage (from the repo root):
  python -I scripts/make-model-browser-c.py [--ref civarchive] --out <folder>
The output folder keeps its .git and .gitignore; everything else in it is replaced, then the frontend dist
is rebuilt (the plugin id changes the Permissions tab's default) from
content/plugins/local/model-browser-c of the marketplace worktree (git-ignored there).
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIR = "model-browser"
VARIANT_DIR = "variants/model-browser-c"
GITHUB_PAGES = {"README.github.md": ".github/README.md"}
NEW_ID = "model-browser-c"
NEW_NAME = "Model Browser C"
EXCLUDED = {"PLAN.md"}

VARIANT_NOTE = (
    "This is **Model Browser C**, the Model Browser with the CivArchive source. Use it instead of\n"
    "the Model Browser of the PotionUI marketplace, not next to it: both keep their data in the\n"
    "same tables and declare the same model fields, notifications and plan limits, so PotionUI\n"
    "refuses to enable the second one. Switching from one to the other keeps group rights,\n"
    "requests and plan limits; plugin settings are per plugin and have to be set again.\n"
    "\n"
    "The plugin needs PotionUI 0.0.16 or newer, or PotionUI's `master` branch from commit\n"
    "`3b3b78a2` (2026-10-14) on; it does not load on 0.0.15 or older. Install it by placing this\n"
    "folder in `content/plugins/local/model-browser-c`, then Admin → Plugins → Scan for Plugins,\n"
    "and enable it.\n"
)

RULES = [
    ("manifest.yml", r'^id: "model-browser"$', f'id: "{NEW_ID}"', 1),
    ("manifest.yml", r'^name: "Model Browser"$', f'name: "{NEW_NAME}"', 1),
    ("manifest.yml", r'(docs:\n  - path: "README.md"\n    title: )"Model Browser"', rf'\1"{NEW_NAME}"', 1),
    ("backend/__init__.py", r'^PLUGIN_ID = "model-browser"$', f'PLUGIN_ID = "{NEW_ID}"', 1),
    ("backend/api.py", r'prefix="/api/plugins/model-browser"', f'prefix="/api/plugins/{NEW_ID}"', 1),
    ("backend/settings.py", r'"model-browser has no setting', f'"{NEW_ID} has no setting', 1),
    ("backend/watcher.py", r"^PENDING_PROVIDER_ID = PLUGIN_ID$", 'PENDING_PROVIDER_ID = "model-browser"', 1),
    ("tests/test_settings.py", r'"model-browser"', f'"{NEW_ID}"', 5),
    ("tests/test_lifecycle.py", r'subject="model-browser"\):\n    return HookContext\(hook_name=hook, plugin_id="model-browser"',
     f'subject="{NEW_ID}"):\n    return HookContext(hook_name=hook, plugin_id="{NEW_ID}"', 1),
    ("tests/test_limits.py", r'"model-browser:"\) and len\(first\) == len\("model-browser:"\)',
     f'"{NEW_ID}:") and len(first) == len("{NEW_ID}:")', 1),
    ("tests/test_downloads.py", r'limit_ref_id\.startswith\("model-browser:"\)', f'limit_ref_id.startswith("{NEW_ID}:")', 1),
    ("frontend/src/PermissionsTab.svelte", r"pluginId = 'model-browser'", f"pluginId = '{NEW_ID}'", 1),
    ("README.md", r"\A# Model Browser\n", f"# {NEW_NAME}\n", 1),
    ("README.md", r"/plugins/model-browser(?![-\w])", f"/plugins/{NEW_ID}", 2),
    ("manifest.yml", r'route: "model-browser"$', f'route: "{NEW_ID}"', 2),
    ("backend/notifications.py", r'^PAGE_LINK = "/plugins/model-browser"$', f'PAGE_LINK = "/plugins/{NEW_ID}"', 1),
    ("README.md", r"(## Getting started\n\n)", r"\1" + VARIANT_NOTE.replace("\\", "\\\\") + "\n", 1),
]

TEST_RULES = [
    (r"/plugins/model-browser(?![-\w])", f"/plugins/{NEW_ID}"),
    (r'"plugin": "model-browser"', f'"plugin": "{NEW_ID}"'),
    (r"pluginId: 'model-browser'", f"pluginId: '{NEW_ID}'"),
]


def _archive(ref: str, prefix: str) -> dict:
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", "--format=tar", ref, prefix],
        check=True, capture_output=True,
    ).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                files[member.name[len(prefix) + 1:]] = tar.extractfile(member).read()
    return files


def export_tree(ref: str) -> dict:
    files = {path: data for path, data in _archive(ref, SOURCE_DIR).items() if path not in EXCLUDED}
    for path, data in _archive(ref, VARIANT_DIR).items():
        files[GITHUB_PAGES.get(path, f".github/{path}")] = data
    return files


def apply_rules(files: dict) -> None:
    for path, pattern, replacement, expected in RULES:
        text = files[path].decode("utf-8")
        text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count != expected:
            sys.exit(f"rule on {path} matched {count} times, expected {expected}: {pattern}")
        files[path] = text.encode("utf-8")
    touched = 0
    for path in sorted(files):
        if not (path.startswith("tests/") and path.endswith(".py")) and not path.endswith(".test.js"):
            continue
        text = files[path].decode("utf-8")
        new = text
        for pattern, replacement in TEST_RULES:
            new = re.sub(pattern, replacement, new)
        if new != text:
            files[path] = new.encode("utf-8")
            touched += 1
    print(f"renamed the plugin id in {len(RULES)} places and in {touched} test files")


def write_out(files: dict, out: Path, license_file: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.name in (".git", ".gitignore"):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for relative, data in files.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    shutil.copyfile(license_file, out / "LICENSE")
    print(f"wrote {len(files) + 1} files to {out}")


def robocopy(source: Path, target: Path) -> None:
    result = subprocess.run(["robocopy", str(source), str(target), "/MIR", "/XD", ".git", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"])
    if result.returncode >= 8:
        sys.exit(f"robocopy {source} -> {target} failed ({result.returncode})")


def build_dist(out: Path, plugins_root: Path) -> None:
    copy = plugins_root / "local" / NEW_ID
    robocopy(out, copy)
    subprocess.run(["node", "../../scripts/build-plugins.mjs", NEW_ID], cwd=plugins_root, check=True, shell=True)
    robocopy(copy / "frontend" / "dist", out / "frontend" / "dist")
    print(f"rebuilt {out / 'frontend' / 'dist'}")


def dotenv_value(key: str) -> str:
    value = os.environ.get(key)
    if value:
        return value
    for name in (".env.local", ".env"):
        path = REPO / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#") or "=" not in line:
                continue
            found, value = line.split("=", 1)
            if found.strip() == key:
                return value.strip().strip('"')
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="civarchive")
    parser.add_argument("--out", required=True)
    parser.add_argument("--license", default=str(REPO / "LICENSE"))
    parser.add_argument("--plugins-root")
    args = parser.parse_args()
    plugins_root = args.plugins_root
    if not plugins_root:
        source = dotenv_value("POTIONUI_SRC")
        if not source:
            sys.exit("give --plugins-root, or set POTIONUI_SRC to a PotionUI checkout in the environment or in .env.local")
        plugins_root = str(Path(source) / "content" / "plugins")
    if not (Path(plugins_root) / "package.json").is_file():
        sys.exit(f"{plugins_root} is not the content/plugins folder of a PotionUI checkout (no package.json)")
    if not Path(args.license).is_file():
        sys.exit(f"no license file at {args.license}")
    files = export_tree(args.ref)
    if "backend/sources/civarchive.py" not in files:
        sys.exit(f"{args.ref} has no CivArchive source")
    apply_rules(files)
    write_out(files, Path(args.out), Path(args.license))
    build_dist(Path(args.out), Path(plugins_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
