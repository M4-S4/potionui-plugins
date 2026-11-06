import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALLOW_FILE = "scripts/public-hygiene-allow.txt"
NAME = r"[^\\/\s\"'`<>{}$%|*?:;,()\[\]]+"
PATTERNS = (
    ("account path", rf"(?<![A-Za-z])[A-Za-z]:[\\/]+(?i:users)[\\/]+{NAME}|/(?:home|Users)/{NAME}/"),
    ("host path from WSL or Docker Desktop", r"/mnt/[A-Za-z]/(?i:users)/|/run/desktop/mnt/host(?=/)"),
    ("PotionUI data drive", r"(?<![A-Za-z])[Ee]:[\\/]+(?i:potionui)"),
    ("OneDrive path", r"(?i:onedrive)[\\/]"),
    ("internal notes", r"(?<![\w-])rapports[\\/]"),
    ("secrets folder", r"\.secrets[\\/]"),
    ("Apple relay address", r"(?i:privaterelay\.appleid\.com)"),
)
COMPILED = tuple((label, re.compile(pattern)) for label, pattern in PATTERNS)


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def names(output: bytes) -> list[str]:
    return [name for name in output.decode("utf-8").split("\0") if name]


def read_allowlist(root: Path) -> list[tuple[str, str]]:
    path = root / ALLOW_FILE
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), start=1):
        line = line.rstrip("\r")
        if not line:
            continue
        file, tab, text = line.partition("\t")
        if not (file and tab and text):
            raise SystemExit(f"{ALLOW_FILE}:{number}: expected <path><TAB><exact text>")
        entries.append((file, text))
    return entries


def from_disk(root: Path, name: str) -> bytes | None:
    path = root / name
    return path.read_bytes() if path.is_file() else None


def collect(root: Path, staged: bool, paths: list[str]) -> list[tuple[str, bytes | None]]:
    if staged:
        listed = names(git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"))
        return [(name, git(root, "cat-file", "blob", f":{name}")) for name in listed]
    if not paths:
        return [(name, from_disk(root, name)) for name in names(git(root, "ls-files", "-z"))]
    files = []
    for given in paths:
        path = Path(given).resolve()
        try:
            relative = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = None
        if path.is_dir():
            if relative is None:
                raise SystemExit(f"{given}: a folder outside the repository")
            listed = names(git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", relative))
            files.extend((name, from_disk(root, name)) for name in listed)
        elif path.is_file():
            files.append((relative or given, path.read_bytes()))
        else:
            raise SystemExit(f"{given}: no such file or folder")
    return files


def findings_in(line: str) -> list[tuple[str, str]]:
    return [(label, match.group(0)) for label, pattern in COMPILED for match in pattern.finditer(line)]


def check(files: list[tuple[str, bytes | None]], entries: list[tuple[str, str]], every_entry: bool):
    findings = []
    used = set()
    listed = set()
    for name, data in files:
        listed.add(name)
        if data is None or b"\0" in data:
            continue
        allowed = [entry for entry in entries if entry[0] == name]
        own = [text for _, text in entries] if name == ALLOW_FILE else []
        for number, line in enumerate(data.decode("utf-8", errors="replace").split("\n"), start=1):
            for entry in allowed:
                if entry[1] in line:
                    used.add(entry)
                    line = line.replace(entry[1], " " * len(entry[1]))
            for text in own:
                line = line.replace(text, " " * len(text))
            findings.extend(f"{name}:{number}: {label}: {found}" for label, found in findings_in(line))
    stale = [
        f"{ALLOW_FILE}: {file}: {text!r} is no longer found in that file"
        for file, text in entries
        if (file, text) not in used and (every_entry or file in listed)
    ]
    return findings, stale, len(listed)


def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if args.staged and args.paths:
        parser.error("--staged reads the index: give no path with it")
    files = collect(root, args.staged, args.paths)
    findings, stale, count = check(files, read_allowlist(root), not args.staged and not args.paths)
    for line in findings + stale:
        print(line)
    if findings or stale:
        print(f"public hygiene: {len(findings)} findings, {len(stale)} stale allowlist entries, {count} files checked")
        return 1
    print(f"public hygiene: {count} files checked, nothing found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
