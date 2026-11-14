import json
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .client import ApiClient, ApiError, unwrap
from .run import RunRefused

LIST_LIMIT = 100
UPLOAD_GONE = {400, 404}
TRACE = "cleanup"
UPLOADS_URL = "/api/media/uploads/"


def instant(text) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def run_window(run_id: str, record: dict) -> tuple[str, datetime, datetime] | None:
    start, end = instant(record.get("started_at")), instant(record.get("ended_at"))
    return (run_id, start, end) if start and end and start <= end else None


def safe_name(name) -> str | None:
    text = str(name or "")
    return text if text and "/" not in text and "\\" not in text and not text.startswith(".") else None


def name_of_url(url) -> str | None:
    text = str(url or "")
    return safe_name(urllib.parse.unquote(text[len(UPLOADS_URL):])) if text.startswith(UPLOADS_URL) else None


def library(client: ApiClient) -> dict[str, dict]:
    found = {}
    offset = 0
    while True:
        page = unwrap(client.get_json("/api/media/uploads", {"limit": LIST_LIMIT, "offset": offset})) or {}
        items = page.get("uploads") or []
        for item in items:
            if item.get("filename"):
                found[item["filename"]] = {key: item.get(key) for key in ("id", "filename", "original_filename", "media_type", "created_at")}
        offset += len(items)
        if not items or offset >= int(page.get("total") or 0):
            return found


def candidate(filename: str, kind: str, run_id: str, window: tuple | None, *, upload_id=None, created=None, export_name=None) -> dict:
    return {"filename": filename, "id": upload_id, "kind": kind, "runs": [run_id], "evidence": [{"run": run_id, "created": created, "window": window, "export_name": export_name}]}


def merge(found: dict[str, dict], item: dict) -> None:
    known = found.get(item["filename"])
    if known is None:
        found[item["filename"]] = {**item, "runs": list(item["runs"]), "evidence": list(item["evidence"])}
        return
    if known["id"] and item["id"] and known["id"] != item["id"]:
        known["id_conflict"] = True
    known["id"] = known["id"] or item["id"]
    known["runs"] += [run for run in item["runs"] if run not in known["runs"]]
    known["evidence"] += item["evidence"]
    if item["kind"] not in known["kind"].split("+"):
        known["kind"] = f"{known['kind']}+{item['kind']}"


def _when(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def attribute(item: dict, rows: dict[str, dict]) -> dict:
    found = {"filename": item["filename"], "id": item["id"], "kind": item["kind"], "runs": list(item["runs"])}
    row = rows.get(item["filename"])
    if row is None:
        return {**found, "on_instance": False, "attributed": None, "proof": "the library of the account holds no such file"}
    found.update(on_instance=True, created_at=row.get("created_at"), original_filename=row.get("original_filename"))
    if item.get("id_conflict") or (item["id"] and row.get("id") and item["id"] != row["id"]):
        return {**found, "attributed": False, "proof": f"the library row of this file is {row.get('id')}, the runs recorded another id"}
    created = instant(row.get("created_at"))
    reasons = []
    for evidence in item["evidence"]:
        proof = _proof(evidence, row, created)
        if proof:
            return {**found, "attributed": True, "proof": proof}
        reasons.append(_refusal(evidence, created))
    return {**found, "attributed": False, "proof": "; ".join(dict.fromkeys(reasons))}


def _proof(evidence: dict, row: dict, created: datetime | None) -> str | None:
    if evidence["created"] is True:
        return f"uploads.json of {evidence['run']} records that the run created it"
    if evidence["created"] is False:
        return None
    window = evidence["window"]
    if created and window and window[1] <= created <= window[2]:
        return f"created at {_when(created)}, during {evidence['run']} ({_when(window[1])} to {_when(window[2])})"
    name = evidence["export_name"]
    if name and row.get("original_filename") == name and evidence["run"] in name:
        return f"its original name {name} is the export file name {evidence['run']} recorded, with its run id"
    return None


def _refusal(evidence: dict, created: datetime | None) -> str:
    if evidence["created"] is False:
        return f"uploads.json of {evidence['run']} records that the server answered a file it already held"
    if created is None:
        return "the library gives no creation time"
    if evidence["window"] is None:
        return f"{evidence['run']} recorded no start and end"
    return f"created at {_when(created)}, outside {evidence['run']}"


def upload_exists(client: ApiClient, filename: str) -> bool:
    try:
        client.get_json(f"/api/media/uploads/{urllib.parse.quote(filename, safe='')}/info")
    except ApiError as error:
        if error.status in UPLOAD_GONE:
            return False
        raise
    return True


def delete_upload(client: ApiClient, item: dict) -> None:
    answer = client.delete_json(f"/api/media/uploads/{urllib.parse.quote(item['filename'], safe='')}", missing_ok=True)
    item.update(deleted=answer is not None, exists_after=upload_exists(client, item["filename"]))


def generation_on_instance(client: ApiClient, generation_id: str) -> bool:
    return client.get_json(f"/api/generations/history/{generation_id}", missing_ok=True) is not None


def delete_generation(client: ApiClient, item: dict) -> None:
    answer = client.delete_json(f"/api/generations/history/{item['id']}", missing_ok=True) if item["on_instance"] else None
    item.update(message=(answer or {}).get("message") if isinstance(answer, dict) else None, exists_after=generation_on_instance(client, item["id"]))


def split(items: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    return [item for item in items if item["attributed"] and item["on_instance"]], [item for item in items if item["on_instance"] and not item["attributed"]], [item for item in items if not item["on_instance"]]


def trace_path(run_dir: Path) -> Path:
    path = run_dir / f"{TRACE}.json"
    number = 2
    while path.exists():
        path = run_dir / f"{TRACE}-{number}.json"
        number += 1
    return path


def write_trace(run_dir: Path, data: dict) -> Path:
    path = trace_path(run_dir)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def log_files(items: list[dict], log: Callable[[str], None]) -> None:
    delete, kept, gone = split(items)
    for item in delete:
        log(f"file {item['filename']} ({item['kind']}): to delete, {item['proof']}")
    for item in kept:
        log(f"file {item['filename']} ({item['kind']}): not attributed, kept: {item['proof']}")
    for item in gone:
        log(f"file {item['filename']} ({item['kind']}): no longer on the instance")


def chain_frame(take: dict) -> dict | None:
    frame = ((take or {}).get("chain") or {}).get("frame") or {}
    name = name_of_url(frame.get("url"))
    return {"filename": name, "id": frame.get("item_id"), "kind": "chain_frame", "export_name": None} if name else None


def export_media(job: dict) -> dict | None:
    media = (job or {}).get("media") or {}
    name = name_of_url(media.get("url"))
    return {"filename": name, "id": media.get("item_id"), "kind": "export", "export_name": ((job or {}).get("file") or {}).get("name")} if name else None


def recorded_uploads(run_dir: Path, run_id: str, window: tuple | None) -> list[dict]:
    record = run_dir / "uploads.json"
    if not record.is_file():
        return []
    found = []
    for item in (json.loads(record.read_text(encoding="utf-8")) or {}).values():
        filename = safe_name((item or {}).get("filename"))
        if filename:
            found.append(candidate(filename, "upload", run_id, window, upload_id=item.get("id"), created=item.get("created")))
    return found


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def matrix_generations(run_dir: Path, run: dict) -> list[dict]:
    found = {}
    for entry in run.get("cells") or ():
        if entry.get("generation_id"):
            found.setdefault(entry["generation_id"], {"id": entry["generation_id"], "cell": entry.get("cell"), "warm_repeat": entry.get("warm_repeat", False), "verdict": entry.get("verdict")})
    for path in sorted((run_dir / "cells").glob("*/result.json")):
        result = _read(path)
        if result.get("generation_id"):
            found.setdefault(result["generation_id"], {"id": result["generation_id"], "cell": result.get("cell"), "warm_repeat": result.get("warm_repeat", False), "verdict": result.get("verdict")})
    return list(found.values())


def matrix_cleanup(client: ApiClient, run_dirs: list[Path], confirm: bool, log: Callable[[str], None] = print) -> dict:
    segments = []
    for run_dir in run_dirs:
        path = run_dir / "run.json"
        if not path.is_file():
            raise RunRefused(f"{run_dir.name} holds no run.json: cleanup takes the segment folders of a matrix run")
        run = json.loads(path.read_text(encoding="utf-8"))
        if run.get("dry_run"):
            raise RunRefused(f"{run_dir.name} is a dry run: it created nothing on the instance")
        run_id = str(run.get("run_id") or run_dir.name)
        window = run_window(run_id, run)
        segments.append({"dir": run_dir, "run_id": run_id, "window": window, "generations": matrix_generations(run_dir, run), "files": recorded_uploads(run_dir, run_id, window)})
    rows = library(client)
    merged = {}
    for segment in segments:
        for item in segment["files"]:
            merge(merged, item)
    files = [attribute(item, rows) for item in merged.values()]
    generations = []
    for segment in segments:
        for item in segment["generations"]:
            if item["id"] not in {known["id"] for known in generations}:
                generations.append({**item, "run": segment["run_id"], "on_instance": generation_on_instance(client, item["id"])})
    for item in generations:
        log(f"generation {item['id']} ({item['cell']}{' warm' if item.get('warm_repeat') else ''}, {item['run']}): {'on the instance' if item['on_instance'] else 'no longer on the instance'}")
    log_files(files, log)
    delete, kept, gone = split(files)
    present = [item for item in generations if item["on_instance"]]
    names = ", ".join(segment["run_id"] for segment in segments)
    plan = {"confirmed": confirm, "segments": [segment["run_id"] for segment in segments], "generations": generations, "files": files}
    if not confirm:
        log(f"{len(present)} of {len(generations)} generations and {len(delete)} files of {names} to delete: pass --confirm to delete them; {len(kept)} files not attributed are kept, {len(gone)} files and {len(generations) - len(present)} generations are already gone")
        return plan
    for item in generations:
        delete_generation(client, item)
    for item in delete:
        delete_upload(client, item)
    for segment in segments:
        own = {item["id"] for item in segment["generations"]}
        named = {item["filename"] for item in segment["files"]}
        trace = {"run_id": segment["run_id"], "confirmed": True, "done_at": datetime.now(UTC).isoformat(timespec="seconds"), "segments": plan["segments"], "generations": [item for item in generations if item["id"] in own], "files": [item for item in files if item["filename"] in named]}
        plan.setdefault("traces", []).append(str(write_trace(segment["dir"], trace)))
    left = [item["id"] for item in generations if item.get("exists_after")]
    files_left = [item["filename"] for item in delete if item.get("exists_after")]
    log(f"{len(present)} generations and {len(delete)} files of {names} deleted, {len(left)} generations and {len(files_left)} files still there; {len(kept)} files not attributed are kept")
    return plan
