import ast
import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PLUGIN_TEST = SCRIPTS.parent / "video-producer" / "tests" / "test_public_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_public_hygiene", SCRIPTS / "check-public-hygiene.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
SOMEONE = "\\".join(("C:", "Users", "Someone", "x"))
BOB = "/".join(("C:", "Users", "Bob", ""))


def assignments(path):
    source = path.read_text(encoding="utf-8")
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = ast.get_source_segment(source, node)
    return found


class PatternsTest(unittest.TestCase):
    def test_the_patterns_are_those_of_the_video_producer_test(self):
        ours = assignments(SCRIPTS / "check-public-hygiene.py")
        theirs = assignments(PLUGIN_TEST)
        self.assertEqual([ours["NAME"], ours["PATTERNS"]], [theirs["NAME"], theirs["PATTERNS"]])

    def test_each_kind_of_private_text_is_found(self):
        samples = {
            SOMEONE: "account path",
            "/".join(("", "home", "someone", "src")): "account path",
            "/".join(("", "mnt", "c", "Users", "")): "host path from WSL or Docker Desktop",
            "/".join(("", "run", "desktop", "mnt", "host", "e")): "host path from WSL or Docker Desktop",
            "\\".join(("E:", "PotionUI", "storage")): "PotionUI data drive",
            "\\".join(("OneDrive", "Apps")): "OneDrive path",
            "/".join(("see rapports", "notes.md")): "internal notes",
            "/".join(("", ".secrets", "admin.env")): "secrets folder",
            ".".join(("someone@privaterelay", "appleid", "com")): "Apple relay address",
        }
        for sample, label in samples.items():
            with self.subTest(sample=sample):
                self.assertEqual([found for found, _ in CHECK.findings_in(sample)], [label])

    def test_a_name_or_a_placeholder_is_not_a_finding(self):
        for sample in (
            "another program (an antivirus, the indexer, OneDrive) held the file open",
            '("onedrive.live.com", "OneDrive"),',
            "<checkout>\\.wt\\pr-mb-1",
            "C:\\Users\\<name>\\Videos",
        ):
            with self.subTest(sample=sample):
                self.assertEqual(CHECK.findings_in(sample), [])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        (self.root / "scripts").mkdir()
        self.write(CHECK.ALLOW_FILE, f"fake.py\t{BOB}\n")
        self.write("fake.py", f'CLIP = "{BOB}Videos/clip.mp4"\n')
        self.write("notes.md", "another program (OneDrive) held the file open\n")
        self.git("add", ".")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def run_check(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = CHECK.main(list(argv), root=self.root)
        return code, out.getvalue()

    def test_a_clean_repository_with_its_allowed_fake_value_passes(self):
        self.assertEqual(self.run_check(), (0, "public hygiene: 3 files checked, nothing found\n"))

    def test_a_tracked_file_with_a_private_path_fails_naming_its_file_line_and_pattern(self):
        self.write("probe.md", f"first line\nsee {SOMEONE} here\n")
        self.git("add", "probe.md")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("probe.md:2: account path: " + SOMEONE.rsplit("\\", 1)[0] + "\n", out)

    def test_staged_reads_the_index_and_not_the_working_tree(self):
        self.write("probe.md", f"see {SOMEONE}\n")
        self.git("add", "probe.md")
        self.write("probe.md", "clean now\n")
        code, out = self.run_check("--staged")
        self.assertEqual(code, 1)
        self.assertIn("probe.md:1: account path", out)
        self.assertEqual(self.run_check(str(self.root / "probe.md"))[0], 0)

    def test_a_folder_covers_its_new_files_but_not_the_ignored_ones(self):
        self.write(".gitignore", "plugin/dist/\n")
        self.write("plugin/dist/page.js", f"{SOMEONE}\n")
        self.write("plugin/new.md", f"{SOMEONE}\n")
        code, out = self.run_check(str(self.root / "plugin"))
        self.assertEqual(code, 1)
        self.assertIn("plugin/new.md:1: account path", out)
        self.assertNotIn("dist", out)

    def test_an_allowed_text_no_longer_in_its_file_fails(self):
        self.write("fake.py", "CLIP = None\n")
        self.git("add", "fake.py")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("fake.py", out)
        self.assertIn("is no longer found in that file", out)


if __name__ == "__main__":
    unittest.main()
