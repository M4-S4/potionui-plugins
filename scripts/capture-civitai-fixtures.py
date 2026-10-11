#!/usr/bin/env python3
"""Refresh the trimmed CivitAI API fixtures under model-browser/tests/fixtures/civitai.

Usage: python -I scripts/capture-civitai-fixtures.py model-browser/tests/fixtures/civitai
Run it when the API changes shape; review the diff before committing (the fixtures are
real public responses, trimmed to 2 items, 2 versions and 3 images each).
"""
import json, sys, urllib.request, urllib.parse, urllib.error
OUT = sys.argv[1]
BASE = "https://civitai.com/api/v1"
UA = "PotionUI-ModelBrowser-fixtures/0.1 (+https://github.com/PotionUI/PotionUI)"

def get(path, params=None, full_url=None):
    url = full_url or (BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else ""))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def trim(obj):
    if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
        obj["items"] = [trim_model(m) for m in obj["items"][:2]]
        return obj
    if isinstance(obj, dict) and "modelVersions" in obj:
        return trim_model(obj)
    if isinstance(obj, dict) and "files" in obj and "images" in obj:
        return trim_version(obj)
    return obj

def trim_model(m):
    if isinstance(m.get("description"), str) and len(m["description"]) > 600:
        m["description"] = m["description"][:600] + "…"
    m["modelVersions"] = [trim_version(v) for v in m.get("modelVersions", [])[:2]]
    return m

def trim_version(v):
    v["images"] = v.get("images", [])[:3]
    if isinstance(v.get("description"), str) and len(v["description"]) > 300:
        v["description"] = v["description"][:300] + "…"
    return v

def save(name, status, headers, body, keep_headers=("Cache-Control", "Content-Type", "x-ratelimit-limit", "x-ratelimit-remaining")):
    try:
        data = json.loads(body)
    except Exception:
        data = {"_raw": body[:500].decode("utf-8", "replace")}
    data = trim(data)
    doc = {"_status": status, "_headers": {k: v for k, v in headers.items() if k in keep_headers or k.lower().startswith("x-ratelimit")}, "body": data}
    with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"{name}: HTTP {status}, {len(body)} bytes raw")
    return data

p1 = save("models_lora_page1", *get("/models", {"limit": 3, "types": "LORA", "sort": "Most Downloaded", "nsfw": "false"}))
nxt = (p1.get("metadata") or {}).get("nextPage")
if nxt:
    save("models_lora_page2", *get(None, full_url=nxt))
save("models_flux_nsfwlevel", *get("/models", {"limit": 3, "types": "LORA", "nsfw": "false", "baseModels": "Flux.1 D", "sort": "Most Downloaded"}))
save("models_ids", *get("/models", {"ids": "122359"}))
save("models_query", *get("/models", {"query": "detail tweaker", "limit": 2}))
save("model_122359", *get("/models/122359"))
save("model_version_135867", *get("/model-versions/135867"))
save("model_version_by_hash", *get("/model-versions/by-hash/" + "a" * 64))
save("enums", *get("/enums"))
save("error_404_model", *get("/models/1"))
save("error_400_limit", *get("/models", {"limit": 1000}))
