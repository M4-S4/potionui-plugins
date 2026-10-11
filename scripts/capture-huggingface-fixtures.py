#!/usr/bin/env python3
"""Refresh the trimmed Hugging Face API fixtures under model-browser/tests/fixtures/huggingface.

Usage: python -I scripts/capture-huggingface-fixtures.py model-browser/tests/fixtures/huggingface
Real public responses, trimmed (3 list items, 20 siblings, a few tree entries, 3000 README
characters). Review the diff before committing. Unknown repos answer 401 (not 404); the
README of a gated repo answers 401 without a token.
"""
import json, sys, urllib.request, urllib.parse, urllib.error
OUT = sys.argv[1]
BASE = "https://huggingface.co"
UA = "PotionUI-ModelBrowser-fixtures/0.1 (+https://github.com/PotionUI/PotionUI)"
KEEP_HEADERS = ("Link", "Content-Type", "X-Total-Count", "ETag", "Content-Length")

def get(path, params=None, full_url=None):
    url = full_url or (BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else ""))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def trim_model(m):
    if isinstance(m, dict) and isinstance(m.get("siblings"), list):
        m["siblings"] = m["siblings"][:20]
    if isinstance(m, dict) and isinstance(m.get("tags"), list):
        m["tags"] = m["tags"][:40]
    return m

def trim(data, kind):
    if kind == "list" and isinstance(data, list):
        return [trim_model(m) for m in data[:3]]
    if kind == "model":
        return trim_model(data)
    if kind == "tree" and isinstance(data, list):
        files = [e for e in data if e.get("type") == "file"]
        dirs = [e for e in data if e.get("type") == "directory"]
        lfs = [e for e in files if e.get("lfs")][:8]
        plain = [e for e in files if not e.get("lfs")][:5]
        return dirs[:4] + plain + lfs
    return data

def save(name, status, headers, body, kind="json"):
    if kind == "text":
        data = body[:3000].decode("utf-8", "replace")
    else:
        try:
            data = json.loads(body)
        except Exception:
            data = {"_raw": body[:500].decode("utf-8", "replace")}
        data = trim(data, kind)
    doc = {"_status": status, "_headers": {k: v for k, v in headers.items() if k in KEEP_HEADERS or k.lower().startswith("x-ratelimit")}, "body": data}
    with open(f"{OUT}/{name}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"{name}: HTTP {status}, {len(body)} bytes raw, link={'yes' if 'Link' in headers else 'no'}")
    return data, headers

d, h = save("models_search_lora", *get("/api/models", {"search": "lora", "limit": 3, "full": "true"}), kind="list")
link = h.get("Link", "")
if "rel=\"next\"" in link:
    nxt = link.split("<", 1)[1].split(">", 1)[0]
    save("models_search_lora_page2", *get(None, full_url=nxt), kind="list")
save("models_text_to_image_top", *get("/api/models", {"pipeline_tag": "text-to-image", "sort": "downloads", "direction": -1, "limit": 3, "full": "true"}), kind="list")
save("models_filter_lora_tag", *get("/api/models", {"filter": "lora", "sort": "likes", "direction": -1, "limit": 3, "full": "true"}), kind="list")
save("models_filter_nsfw_tag", *get("/api/models", {"filter": "not-for-all-audiences", "limit": 2, "full": "true"}), kind="list")
save("models_author", *get("/api/models", {"author": "latent-consistency", "limit": 3, "full": "true"}), kind="list")
for name, repo in [("model_lcm_lora_sdxl", "latent-consistency/lcm-lora-sdxl"), ("model_flux_dev_gated", "black-forest-labs/FLUX.1-dev"), ("model_sdxl_base", "stabilityai/stable-diffusion-xl-base-1.0"), ("model_sd35_large", "stabilityai/stable-diffusion-3.5-large"), ("model_real_esrgan", "ai-forever/Real-ESRGAN")]:
    save(name, *get(f"/api/models/{repo}"), kind="model")
    save(name.replace("model_", "tree_"), *get(f"/api/models/{repo}/tree/main", {"recursive": 1}), kind="tree")
save("readme_lcm_lora_sdxl", *get("/latent-consistency/lcm-lora-sdxl/raw/main/README.md"), kind="text")
save("readme_flux_dev_gated", *get("/black-forest-labs/FLUX.1-dev/raw/main/README.md"), kind="text")
save("error_401_unknown_repo", *get("/api/models/no-such-org/no-such-repo"))
save("error_401_unknown_tree", *get("/api/models/no-such-org/no-such-repo/tree/main"))
