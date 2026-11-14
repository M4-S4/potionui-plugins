#!/usr/bin/env python3
"""Refresh the OpenModelDB fixtures under model-browser/tests/fixtures/openmodeldb.

Usage: python -I scripts/capture-openmodeldb-fixtures.py model-browser/tests/fixtures/openmodeldb [--from DIR]
Downloads https://openmodeldb.info/api/v1/{models,tags,architectures}.json (or reads the
three files from DIR, a copy saved earlier) and writes `tags.json` and
`architectures.json` whole, and `models.json` cut down to the models of `IDS` (in the
catalogue's order). The ids cover every shape the source reads; review the diff before
committing, and the tests that name these models when one of them changes or disappears.
"""
import json, sys, urllib.request, urllib.error
from pathlib import Path

BASE = "https://openmodeldb.info/api/v1"
UA = "PotionUI-ModelBrowser-fixtures/0.1 (+https://github.com/PotionUI/PotionUI)"
FILES = ("models", "tags", "architectures")

#: The models kept, and what each one is there for.
IDS = {
    "16x-ESRGAN": "Oracle object storage (+ Mega), scale 16, no images, no thumbnail",
    "1x-Archiver-AntiLines": "GitHub release asset, paired image",
    "1x-Book-Compact": "safetensors GitHub release asset, inline HTML in the description",
    "1x-BroadcastToStudio-SPAN": "Mega only (pth and onnx), standalone images and thumbnail",
    "1x-BW-Denoise": "misspelt keys (Datasize, Training epochs ...), Mega only",
    "1x-Debandurh-FS-Ultra-lite": "small ESRGAN on Oracle and Backblaze (+ Proton Drive)",
    "1x-DeJpeg-Fatality-PlusULTRA": "Oracle, Backblaze and Proton Drive",
    "1x-DeNoise-realplksr-otf": "pth, safetensors and onnx GitHub release assets (the onnx is never offered), standalone thumbnail",
    "1x-KDM003-scans": "no licence, Oracle (+ Dropbox)",
    "1x-MangaJPEGLQ": "1 -> 1 channels",
    "1x-NMKD-YandereInpaint": "no licence, Icedrive only, paired and standalone images",
    "2x-AnimeJaNai-Standard-v1-SuperUltraCompact": "onnx in a GitHub release .zip of several models",
    "2x-cainREALTIME": "video input (CAIN)",
    "2x-GameUp-TSCUNet": "video input (TSCUNet), two pth and two onnx",
    "2x-LD-Anime-Compact": "two authors",
    "2x-LiveActionV1-SPAN": "raw.githubusercontent.com pth and github.com/raw onnx, thumbnail pair without sizes",
    "3x-OmniSR-DF2K": "Google Drive only, scale 3",
    "4x-AnalogFrames-1-0": "an http:// link only",
    "4x-Nomos8kSC": "github.com/<owner>/<repo>/raw/ pth (ESRGAN)",
    "4x-Nomos8kSCHAT-S": "onnx listed before the pth (only the pth is offered)",
    "4x-Nomos8kSCSRFormer": "onnx on GitHub and pth on Google Drive (not downloadable)",
    "4x-Remacri": "huggingface.co /resolve/ with ?download=true (+ pCloud)",
    "4x-SPANkendata": "raw.githubusercontent.com onnx only (not downloadable)",
    "4x-Swift-SRGAN": "pth as a GitHub release .pth.tar",
    "4x-UltraSharp": "Mega only",
    "4x-UltraSharpV2": "Hugging Face /resolve/ safetensors and /blob/ onnx, standalone thumbnail",
    "8x-classicalSR-DIV2K-s64w8-SwinIR-M": "scale 8, author given as a one-name list",
}


def fetch(name):
    request = urllib.request.Request(f"{BASE}/{name}.json", headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        print(f"{name}.json: HTTP {response.status}, {response.headers.get('Content-Length')} bytes")
        return json.loads(response.read())


def load(source, name):
    if source is None:
        return fetch(name)
    return json.loads((Path(source) / f"{name}.json").read_text(encoding="utf-8"))


def save(out, name, data):
    with open(Path(out) / f"{name}.json", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")


def main(argv):
    out = argv[1]
    source = argv[argv.index("--from") + 1] if "--from" in argv else None
    catalogue = {name: load(source, name) for name in FILES}
    models = catalogue["models"]
    missing = [model_id for model_id in IDS if model_id not in models]
    if missing:
        sys.exit(f"Not in the catalogue any more: {', '.join(missing)}; pick other models for IDS")
    save(out, "models", {model_id: entry for model_id, entry in models.items() if model_id in IDS})
    save(out, "tags", catalogue["tags"])
    save(out, "architectures", catalogue["architectures"])
    print(f"models.json: {len(IDS)} of {len(models)} models; tags.json: {len(catalogue['tags'])}; "
          f"architectures.json: {len(catalogue['architectures'])}")


if __name__ == "__main__":
    main(sys.argv)
