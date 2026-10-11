#!/usr/bin/env python3
"""Refresh the CivArchive fixtures under model-browser/tests/fixtures/civarchive.

Usage: python -I scripts/capture-civarchive-fixtures.py model-browser/tests/fixtures/civarchive [--from DIR] [--raw DIR]

CivArchive has no API: the source reads the Next.js data routes of civarchive.com
(`/_next/data/<build id>/...json`, PLAN.md section 8.5). The script resolves the build id from
https://civarchive.com/, then asks for each answer of `FIXTURES` (one request per second, the
source's own rate), or reads them from DIR (`<name>.json` / `<name>.html` and `<name>.status`, as
`--raw DIR` saves them), and writes them trimmed: the home page cut down to its start and the few
KB around `"buildId"`, the error pages to their head, at most 5 results per search page, no
`comments` / `faqSections` in a model page, and at most `MAX_MIRRORS` mirrors per file (always
keeping the first of each source, so the download policy picks the same URL). `FIXTURES` says
where each file comes from (path under `/_next/data/<build id>/`, parameters, status) and what it
is there for; review the diff before committing, and the tests that name these models when one of
them changes.
"""
import json, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

SITE = "https://civarchive.com"
UA = "PotionUI-ModelBrowser-fixtures/0.1 (+https://github.com/PotionUI/PotionUI)"
BUILD_ID = re.compile(r'"buildId":"([^"]+)"')
#: A build id no deployment has: its data URLs answer the 404 page.
STALE_BUILD_ID = "staleBuildId0000000000"
MAX_RESULTS = 5
MAX_MIRRORS = 8
#: What the search sends by default (`backend/sources/civarchive.py`), before the fixture's own parameters.
SEARCH = [("platform", "civitai"), ("kind", "version"), ("rating", "all"), ("sort", "top"), ("period", "all"), ("page", "1")]


def search(**changes):
    """The default search parameters with some replaced or added (a list value repeats the name)."""
    params = dict(SEARCH)
    params.update(changes)
    return [(name, item) for name, value in params.items() for item in (value if isinstance(value, list) else [value])]


#: name -> (path under /_next/data/<build id>/, or "/" for the home page; parameters; expected status; what for).
FIXTURES = {
    "index": ("/", [], 200, "the home page: the build id at the end of __NEXT_DATA__"),
    "build_id_404": ("search.json", [("platform", "civitai")], 404, "a data URL under a stale build id (the HTML 404 page)"),
    "search_civitai_top": ("search.json", search(), 200, "the default search: kind=version (kind=model answers 0 results)"),
    "search_civitai_page2": ("search.json", search(page="2"), 200, "its second page"),
    "search_civitai_lora_sd15_newest": (
        "search.json", search(type=["LORA"], base_model=["SD 1.5"], sort="newest"), 200, "type, base model and sort",
    ),
    "search_tag": ("search.json", search(tags="anime"), 200, "#anime"),
    "search_user": ("search.json", search(username="TangBohu"), 200, "@TangBohu"),
    "search_safe": ("search.json", search(rating="safe"), 200, "rating=safe (users who never see NSFW)"),
    "search_empty": ("search.json", search(q="zzqxjv-no-such-model-0"), 200, "a text with 0 hits"),
    "search_deleted": (
        "search.json", search(platform_status="deleted", type=["LORA"], sort="newest", rating="safe"), 200,
        "models deleted from CivitAI that rating=safe lets through (is_nsfw false; not reliable on deleted models)",
    ),
    "search_filters": ("search.json", [("platform", "civitai")], 200, "the plain search info() reads filterOptions from"),
    "model_78291_v83095": (
        "models/78291.json", [("platform", "civitai"), ("modelVersionId", "83095")], 200,
        "a small live LoRA (26 MB): CivitAI URL, HF mirrors with spaces and non-ASCII paths, level 3 (PG-13)",
    ),
    "model_78291_redirect": ("models/78291.json", [("platform", "civitai")], 200, "no version: __N_REDIRECT to the latest"),
    "model_78291_v1": (
        "models/78291.json", [("platform", "civitai"), ("modelVersionId", "1")], 200,
        "a version of another model: CivArchive answers model 78291 with version 1 of model 1",
    ),
    "model_78291_unknown_version_500": (
        "models/78291.json", [("platform", "civitai"), ("modelVersionId", "999999999")], 500,
        "an unknown version: HTTP 500, 'Model version not found'",
    ),
    "model_122359_v135867": (
        "models/122359.json", [("platform", "civitai"), ("modelVersionId", "135867")], 200,
        "Detail Tweaker XL: NSFW by the model bitmask (5 = PG | R), its version and images PG, two versions",
    ),
    "model_298188_v334947": (
        "models/298188.json", [("platform", "civitai"), ("modelVersionId", "334947")], 200,
        "deleted, level 7, images at PG-13 and R; its file only on a deleted CivitAI version and tensordrive.app",
    ),
    "model_195519_v225222": (
        "models/195519.json", [("platform", "civitai"), ("modelVersionId", "225222")], 200,
        "four versions; the requested one deleted, its file still on CivitAI under another version",
    ),
    "model_48139_v52753": (
        "models/48139.json", [("platform", "civitai"), ("modelVersionId", "52753")], 200,
        "deleted model: CivitAI mirror deleted, Hugging Face mirrors, images without a level, a trigger word",
    ),
    "model_1879_v2026": (
        "models/1879.json", [("platform", "civitai"), ("modelVersionId", "2026")], 200,
        "deleted embedding (.pt), Hugging Face mirrors, .mp4 previews without id, type or level",
    ),
    "model_unknown_500": (
        "models/999999999.json", [("platform", "civitai"), ("modelVersionId", "1")], 500,
        "an unknown model: HTTP 500, 'Model not found:999999999' (not a 404)",
    ),
    "sha256_e47d": (
        "sha256/e47d1de297b8ec749aab188969172e79898028e8ad5e9333e87d7d975087269a.json", [], 200,
        "the file of model 78291",
    ),
    "sha256_unknown": (
        "sha256/5f1c3a9e7b2d4c6a8e0f1b3d5c7e9a1b2c4d6e8f0a1b3c5d7e9f1a2b3c4d5e6f.json", [], 200,
        "a hash CivArchive does not know: 200 with no file and no model (not a 404)",
    ),
}


def fetch(url):
    time.sleep(1.0)
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def url_of(name, build_id):
    path, params, _, _ = FIXTURES[name]
    if path == "/":
        return SITE + "/"
    url = f"{SITE}/_next/data/{STALE_BUILD_ID if name == 'build_id_404' else build_id}/{path}"
    return url + ("?" + urllib.parse.urlencode(params) if params else "")


def load(source, name):
    """(status, body bytes) from DIR."""
    folder = Path(source)
    status = int((folder / f"{name}.status").read_text().split()[0])
    for suffix in (".json", ".html"):
        if (folder / f"{name}{suffix}").exists():
            return status, (folder / f"{name}{suffix}").read_bytes()
    sys.exit(f"{name}: no {name}.json or {name}.html in {source}")


def trim_html(text, keep_build_id):
    """The start of the page up to its title and the description after it, and with `keep_build_id`
    the tail of the page from 2000 characters before "buildId"."""
    end = text.find("</title>")
    end = min(len(text), 1200) if end < 0 else end + len("</title>")
    description = re.search(r'<meta name="description"[^>]*>', text[end:end + 2000])
    head = text[: end + (description.end() if description else 0)]
    if not keep_build_id:
        return head + "</head><body></body></html>\n"
    match = BUILD_ID.search(text)
    if not match:
        sys.exit("the home page has no build id any more: the source must change")
    return head + "</head><body><!-- trimmed --><script id=\"__NEXT_DATA__\" type=\"application/json\">…" + text[max(0, match.start() - 2000):] + "\n"


def trim_mirrors(mirrors):
    """At most MAX_MIRRORS, in order, keeping the first mirror of each source."""
    kept, sources = [], set()
    for index, mirror in enumerate(mirrors):
        source = mirror.get("source")
        if index < MAX_MIRRORS or source not in sources:
            kept.append(mirror)
        sources.add(source)
    return kept


def trim_model(model):
    version = model.get("version")
    if isinstance(version, dict):
        for file in version.get("files") or []:
            if isinstance(file.get("mirrors"), list):
                file["mirrors"] = trim_mirrors(file["mirrors"])
    return model


def trim_json(name, data):
    props = data.get("pageProps", {})
    for key in ("comments", "faqSections", "footerLinks"):
        props.pop(key, None)
    results = props.get("data", {}).get("results") if isinstance(props.get("data"), dict) else None
    if isinstance(results, list):
        props["data"]["results"] = results[: (2 if name == "search_filters" else MAX_RESULTS)]
    if isinstance(props.get("model"), dict):
        trim_model(props["model"])
    for model in props.get("models") or []:
        trim_model(model)
    if isinstance(props.get("files"), list):
        props["files"] = trim_mirrors(props["files"])
    return data


def main(argv):
    out = Path(argv[1])
    source = argv[argv.index("--from") + 1] if "--from" in argv else None
    raw = Path(argv[argv.index("--raw") + 1]) if "--raw" in argv else None
    out.mkdir(parents=True, exist_ok=True)
    build_id = None
    for name, (path, params, expected, _) in FIXTURES.items():
        if source is not None:
            status, body = load(source, name)
        else:
            url = url_of(name, build_id)
            status, body = fetch(url)
            print(f"{name}: HTTP {status}, {len(body)} bytes ({url})")
            if raw is not None:
                raw.mkdir(parents=True, exist_ok=True)
                (raw / f"{name}.{'html' if body[:1] == b'<' else 'json'}").write_bytes(body)
                (raw / f"{name}.status").write_text(f"{status}\n{url}\n")
        if status != expected:
            sys.exit(f"{name}: HTTP {status}, expected {expected}")
        text = body.decode("utf-8")
        if name == "index":
            build_id = BUILD_ID.search(text).group(1)
            print(f"build id: {build_id}")
        if body[:1] == b"<":
            (out / f"{name}.html").write_text(trim_html(text, keep_build_id=name == "index"), encoding="utf-8", newline="\n")
        else:
            data = trim_json(name, json.loads(text))
            with open(out / f"{name}.json", "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)
                handle.write("\n")
    print(f"{len(FIXTURES)} fixtures written to {out}")


if __name__ == "__main__":
    main(sys.argv)
