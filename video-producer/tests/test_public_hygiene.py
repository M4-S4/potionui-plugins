import os
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
SKIPPED_DIRS = {"node_modules", "__pycache__", ".pytest_cache"}
SKIPPED_TREES = {("frontend", "dist")}
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
ALLOWED = {("tests/test_exports_hardening.py", "/".join(("C:", "Users", "Bob", "")))}


def _text_files():
    for folder, dirs, files in os.walk(PLUGIN):
        relative = Path(folder).relative_to(PLUGIN)
        dirs[:] = sorted(
            name for name in dirs if name not in SKIPPED_DIRS and (relative / name).parts not in SKIPPED_TREES
        )
        for name in sorted(files):
            data = (Path(folder) / name).read_bytes()
            if b"\0" not in data:
                yield (relative / name).as_posix(), data.decode("utf-8", errors="replace")


def _findings(line):
    return [(label, match.group(0)) for label, pattern in COMPILED for match in pattern.finditer(line)]


def _sweep():
    findings = []
    used = set()
    for relative, text in _text_files():
        allowed = [entry for entry in ALLOWED if entry[0] == relative]
        for number, line in enumerate(text.split("\n"), start=1):
            for entry in allowed:
                if entry[1] in line:
                    used.add(entry)
                    line = line.replace(entry[1], " " * len(entry[1]))
            findings.extend(f"{relative}:{number}: {label}: {found}" for label, found in _findings(line))
    return findings, used


def test_no_text_file_of_the_plugin_holds_a_private_path_an_internal_note_or_a_relay_address():
    findings, _ = _sweep()
    assert findings == [], "\n".join(findings)


def test_every_allowed_fake_value_is_still_in_its_file():
    _, used = _sweep()
    assert sorted(ALLOWED - used) == []


@pytest.mark.parametrize(
    ("sample", "label"),
    [
        ("\\".join(("C:", "Users", "Someone", "x")), "account path"),
        ("/".join(("d:", "users", "someone", "Videos")), "account path"),
        ("\\\\".join(("C:", "Users", "Someone", "x")), "account path"),
        ("/".join(("", "home", "someone", "src")), "account path"),
        ("/".join(("", "Users", "someone", "src")), "account path"),
        ("/".join(("", "mnt", "c", "Users", "")), "host path from WSL or Docker Desktop"),
        ("/".join(("", "run", "desktop", "mnt", "host", "e")), "host path from WSL or Docker Desktop"),
        ("\\".join(("E:", "PotionUI", "storage")), "PotionUI data drive"),
        ("/".join(("E:", "PotionUI", "outputs")), "PotionUI data drive"),
        ("\\".join(("OneDrive", "Apps")), "OneDrive path"),
        ("/".join(("OneDrive", "Apps")), "OneDrive path"),
        ("/".join(("see rapports", "notes.md")), "internal notes"),
        ("/".join(("", ".secrets", "admin.env")), "secrets folder"),
        (".".join(("someone@privaterelay", "appleid", "com")), "Apple relay address"),
    ],
)
def test_each_pattern_finds_its_kind_of_private_text(sample, label):
    assert [found for found, _ in _findings(sample)] == [label]


@pytest.mark.parametrize(
    "sample",
    [
        "another program (an antivirus, the indexer, OneDrive) held the file open",
        "https://onedrive.live.com/download",
        "<checkout>\\.wt\\pr-mb-1",
        "C:\\Users\\<name>\\Videos",
        "%USERPROFILE%\\Videos",
        "/srv/a&b/clip.mp4",
        "the reports/ folder",
        "https://example.com/users/42",
    ],
)
def test_a_name_a_placeholder_or_a_neutral_path_is_not_a_finding(sample):
    assert _findings(sample) == []
