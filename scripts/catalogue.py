import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "plugins.json"
REPOSITORY = "M4-S4/potionui-plugins"
ENTRY_KEYS = {"id", "name", "version", "description", "license", "source", "requires", "release"}
TEXT_KEYS = ("id", "name", "version", "description", "license")
SHA256 = re.compile(r"[0-9a-f]{64}")
MANIFEST_FIELD = re.compile(r"^(id|name|version|license):[ \t]*(.*?)[ \t]*$", re.M)


def manifest_fields(text):
    fields = {}
    for match in MANIFEST_FIELD.finditer(text):
        value = match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields.setdefault(match.group(1), value)
    return fields


def read_manifest(plugin_id):
    path = ROOT / plugin_id / "manifest.yml"
    if not path.is_file():
        return None
    return manifest_fields(path.read_text(encoding="utf-8"))


def plugin_folders():
    return sorted(path.name for path in ROOT.iterdir() if (path / "manifest.yml").is_file())


def load():
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))


def save(catalogue):
    CATALOGUE.write_bytes((json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def release_problems(release, archive_name, where):
    if not isinstance(release, dict) or set(release) != {"archive", "sha256"}:
        return [f"{where}: release is not an object with exactly the keys archive and sha256"]
    if (release["archive"] is None) != (release["sha256"] is None):
        return [f"{where}: release archive and sha256 are not both null or both set"]
    if release["archive"] is None:
        return []
    found = []
    if not isinstance(release["archive"], str) or not release["archive"].startswith("https://"):
        found.append(f"{where}: release archive is not an https URL")
    elif not release["archive"].endswith("/" + archive_name):
        found.append(f"{where}: release archive does not end with /{archive_name}")
    if not isinstance(release["sha256"], str) or not SHA256.fullmatch(release["sha256"]):
        found.append(f"{where}: release sha256 is not 64 lowercase hex digits")
    return found


def requires_problems(requires, where):
    if (
        isinstance(requires, dict)
        and set(requires) == {"core", "plugin_api"}
        and isinstance(requires["core"], str)
        and requires["core"].strip()
        and (requires["plugin_api"] is None or isinstance(requires["plugin_api"], str))
    ):
        return []
    return [f"{where}: requires is not an object with a core ref and a plugin_api version or null"]


def entry_problems(entry, where):
    found = [f"{where}: {key} is not a non-empty string" for key in TEXT_KEYS if not isinstance(entry[key], str) or not entry[key].strip()]
    if found:
        return found
    plugin_id = entry["id"]
    manifest = read_manifest(plugin_id)
    if manifest is None:
        found.append(f"{where}: no folder {plugin_id}/ with a manifest.yml")
    else:
        for key in ("id", "version", "license"):
            if manifest.get(key) != entry[key]:
                found.append(f"{where}: {key} {entry[key]!r} differs from the manifest's {manifest.get(key)!r}")
    if entry["source"] != {"repository": REPOSITORY, "path": plugin_id}:
        found.append(f"{where}: source is not repository {REPOSITORY} and path {plugin_id}")
    found.extend(requires_problems(entry["requires"], where))
    found.extend(release_problems(entry["release"], f"{plugin_id}-{entry['version']}.zip", where))
    return found


def problems(catalogue):
    if not isinstance(catalogue, dict) or set(catalogue) != {"schema", "plugins"}:
        return ["the catalogue is not an object with exactly the keys schema and plugins"]
    found = []
    if catalogue["schema"] != 1:
        found.append(f"schema {catalogue['schema']!r} is not 1")
    if not isinstance(catalogue["plugins"], list):
        return found + ["plugins is not a list"]
    seen = set()
    for index, entry in enumerate(catalogue["plugins"]):
        where = f"plugins[{index}]"
        if not isinstance(entry, dict):
            found.append(f"{where} is not an object")
            continue
        if set(entry) != ENTRY_KEYS:
            found.append(f"{where}: keys {sorted(entry)} are not {sorted(ENTRY_KEYS)}")
            continue
        where = f"{where} ({entry['id']})"
        if entry["id"] in seen:
            found.append(f"{where}: listed twice")
        seen.add(entry["id"])
        found.extend(entry_problems(entry, where))
    return found


def check():
    catalogue = load()
    found = problems(catalogue)
    for problem in found:
        print(f"plugins.json: {problem}", file=sys.stderr)
    if found:
        return 1
    listed = sorted(entry["id"] for entry in catalogue["plugins"])
    print(f"plugins.json: {len(listed)} plugins, OK ({', '.join(listed)})")
    others = [name for name in plugin_folders() if name not in listed]
    if others:
        print(f"not in the catalogue: {', '.join(others)}")
    return 0


def release(plugin_id, archive, url):
    catalogue = load()
    found = problems(catalogue)
    if found:
        raise SystemExit("plugins.json does not pass --check:\n  " + "\n  ".join(found))
    entry = next((item for item in catalogue["plugins"] if item["id"] == plugin_id), None)
    if entry is None:
        raise SystemExit(f"{plugin_id} is not in plugins.json")
    path = Path(archive)
    name = f"{plugin_id}-{entry['version']}.zip"
    if path.name != name:
        raise SystemExit(f"the archive of {plugin_id} {entry['version']} is named {name}, not {path.name}")
    if not url.startswith("https://") or not url.endswith("/" + name):
        raise SystemExit(f"the URL is not an https URL ending with /{name}")
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if f"{plugin_id}/manifest.yml" not in names:
            raise SystemExit(f"{path.name} holds no {plugin_id}/manifest.yml")
        version = manifest_fields(bundle.read(f"{plugin_id}/manifest.yml").decode("utf-8")).get("version")
    if version != entry["version"]:
        raise SystemExit(f"{path.name} holds version {version!r}, plugins.json lists {entry['version']!r}")
    if any(item.startswith(f"{plugin_id}/tests/") for item in names):
        raise SystemExit(f"{path.name} holds the tests of the plugin")
    if (ROOT / plugin_id / "frontend" / "src").is_dir() and not any(item.startswith(f"{plugin_id}/frontend/dist/") for item in names):
        raise SystemExit(f"{path.name} holds no frontend/dist")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    entry["release"] = {"archive": url, "sha256": digest}
    save(catalogue)
    print(f"plugins.json: {plugin_id} {entry['version']} -> {url} (sha256 {digest})")
    return 0


def tag(name):
    plugin_id, separator, version = name.rpartition("-v")
    if not separator or not plugin_id or not version:
        raise SystemExit(f"{name} is not a tag <id>-v<version>")
    manifest = read_manifest(plugin_id)
    if manifest is None:
        raise SystemExit(f"{name}: no folder {plugin_id}/ with a manifest.yml")
    if manifest.get("version") != version:
        raise SystemExit(f"{name}: the manifest of {plugin_id} reads version {manifest.get('version')!r}")
    print(f"id={plugin_id}")
    print(f"version={version}")
    print(f"name={manifest.get('name') or plugin_id}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check plugins.json, or record the release archive of a plugin in it.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="check the schema, the folders and the versions against the manifests")
    action.add_argument("--release", nargs=3, metavar=("ID", "ZIP", "URL"), help="record the URL and the sha256 of a release zip")
    action.add_argument("--tag", metavar="TAG", help="read a release tag <id>-v<version> against the manifest, as key=value lines")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if args.release:
        return release(*args.release)
    return tag(args.tag)


if __name__ == "__main__":
    sys.exit(main())
