import json
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .client import ApiClient, ApiError, ApiUnreachable, unwrap
from .run import RunRefused

LIST_LIMIT = 100
UPLOAD_GONE = {400, 404}
TRACE = "cleanup"
UPLOADS_URL = "/api/media/uploads/"
CLOCK_SLACK_SECONDS = 2.0
FAILURES = (ApiError, ApiUnreachable, ValueError)


def instant(text) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def library_mark(client: ApiClient) -> dict | None:
    try:
        page = unwrap(client.get_json("/api/media/uploads", {"limit": 1}))
    except FAILURES:
        return None
    if not isinstance(page, dict) or not isinstance(page.get("total"), int):
        return None
    items = page.get("uploads") or []
    first = items[0] if items and isinstance(items[0], dict) else {}
    return {"total": page["total"], "id": first.get("id"), "created_at": first.get("created_at")}


def _mark_key(mark: dict) -> tuple | None:
    if not mark.get("id"):
        return None
    created = instant(mark.get("created_at"))
    return (created, str(mark["id"])) if created else ()


def run_span(run_id: str, record: dict) -> dict:
    start, end = instant(record.get("started_at")), instant(record.get("ended_at"))
    marks = None
    first, last = record.get("library_start"), record.get("library_end")
    if isinstance(first, dict) and isinstance(last, dict) and _mark_key(first) != () and _mark_key(last) != ():
        marks = (_mark_key(first), _mark_key(last))
    return {"run": run_id, "window": (start, end) if start and end and start <= end else None, "marks": marks}


def clock_margin(client: ApiClient) -> dict:
    offset = client.server_offset()
    return {"server_offset_seconds": offset, "margin_seconds": None if offset is None else round(abs(offset) + CLOCK_SLACK_SECONDS, 3)}


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


def candidate(filename: str, kind: str, span: dict, *, upload_id=None, created=None, export_name=None) -> dict:
    return {"filename": filename, "id": upload_id, "kind": kind, "runs": [span["run"]], "evidence": [{"run": span["run"], "created": created, "span": span, "export_name": export_name}]}


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


def attribute(item: dict, rows: dict[str, dict], margin: float | None) -> dict:
    found = {"filename": item["filename"], "id": item["id"], "kind": item["kind"], "runs": list(item["runs"])}
    row = rows.get(item["filename"])
    if row is None:
        return {**found, "on_instance": False, "attributed": None, "proof": "the library of the account holds no such file"}
    found.update(on_instance=True, created_at=row.get("created_at"), original_filename=row.get("original_filename"))
    if item.get("id_conflict") or (item["id"] and row.get("id") and item["id"] != row["id"]):
        return {**found, "attributed": False, "proof": f"the library row of this file is {row.get('id')}, the runs recorded another id"}
    for evidence in item["evidence"]:
        if evidence["created"] is True:
            return {**found, "attributed": True, "proof": f"uploads.json of {evidence['run']} records that the run created it"}
    reused = {evidence["run"] for evidence in item["evidence"] if evidence["created"] is False}
    created = instant(row.get("created_at"))
    key = (created, str(row.get("id") or "")) if created else None
    reasons = []
    for evidence in item["evidence"]:
        if evidence["run"] in reused:
            reasons.append(f"uploads.json of {evidence['run']} records that the server answered a file it already held")
            continue
        if not item["id"]:
            reasons.append(f"{evidence['run']} recorded no library id for it")
            continue
        proof, reason = _proof(evidence, row, created, key, margin)
        if proof:
            return {**found, "attributed": True, "proof": proof}
        reasons.append(reason)
    return {**found, "attributed": False, "proof": "; ".join(dict.fromkeys(reasons))}


def _proof(evidence: dict, row: dict, created: datetime | None, key: tuple | None, margin: float | None) -> tuple[str | None, str]:
    run = evidence["run"]
    name = evidence["export_name"]
    if name and row.get("original_filename") == name and run in name:
        return f"its original name {name} is the export file name {run} recorded, with its run id", ""
    if key is None:
        return None, "the library gives no creation time"
    span = evidence["span"]
    if span["marks"] is not None:
        start, end = span["marks"]
        if (start is None or key > start) and end is not None and key <= end:
            return f"created at {_when(created)}, after the newest library file at the start of {run} and no later than the newest at its end", ""
        return None, f"created at {_when(created)}, outside the library files {run} saw appear"
    if span["window"] is None:
        return None, f"{run} recorded no start and end"
    if margin is None:
        return None, f"{run} recorded no library marks, and the clock of the server could not be read"
    start, end = span["window"][0] + timedelta(seconds=margin), span["window"][1] - timedelta(seconds=margin)
    if start <= created <= end:
        return f"created at {_when(created)}, during {run} ({_when(span['window'][0])} to {_when(span['window'][1])}, {margin} s kept off each end for the clocks)", ""
    return None, f"created at {_when(created)}, outside {run} less {margin} s at each end"


def upload_exists(client: ApiClient, filename: str) -> bool:
    try:
        client.get_json(f"/api/media/uploads/{urllib.parse.quote(filename, safe='')}/info")
    except ApiError as error:
        if error.status in UPLOAD_GONE:
            return False
        raise
    return True


def _failed(item: dict, error: Exception) -> None:
    item["error"] = str(error) or type(error).__name__
    item.setdefault("exists_after", None)


def delete_upload(client: ApiClient, item: dict) -> None:
    try:
        answer = client.delete_json(f"/api/media/uploads/{urllib.parse.quote(item['filename'], safe='')}", missing_ok=True)
        item["deleted"] = answer is not None
        item["exists_after"] = upload_exists(client, item["filename"])
    except FAILURES as error:
        _failed(item, error)


def generation_on_instance(client: ApiClient, generation_id: str) -> bool:
    return client.get_json(f"/api/generations/history/{generation_id}", missing_ok=True) is not None


def delete_generation(client: ApiClient, item: dict) -> None:
    try:
        answer = client.delete_json(f"/api/generations/history/{item['id']}", missing_ok=True) if item["on_instance"] else None
        item["message"] = (answer or {}).get("message") if isinstance(answer, dict) else None
        item["exists_after"] = generation_on_instance(client, item["id"])
    except FAILURES as error:
        _failed(item, error)


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


def recorded_uploads(run_dir: Path, span: dict) -> list[dict]:
    record = run_dir / "uploads.json"
    if not record.is_file():
        return []
    found = []
    for item in (json.loads(record.read_text(encoding="utf-8")) or {}).values():
        filename = safe_name((item or {}).get("filename"))
        if filename:
            found.append(candidate(filename, "upload", span, upload_id=item.get("id"), created=item.get("created")))
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
        span = run_span(str(run.get("run_id") or run_dir.name), run)
        segments.append({"dir": run_dir, "run_id": span["run"], "generations": matrix_generations(run_dir, run), "files": recorded_uploads(run_dir, span)})
    clock = clock_margin(client)
    rows = library(client)
    merged = {}
    for segment in segments:
        for item in segment["files"]:
            merge(merged, item)
    files = [attribute(item, rows, clock["margin_seconds"]) for item in merged.values()]
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
    plan = {"confirmed": confirm, "segments": [segment["run_id"] for segment in segments], "clock": clock, "generations": generations, "files": files}
    if not confirm:
        log(f"{len(present)} of {len(generations)} generations and {len(delete)} files of {names} to delete: pass --confirm to delete them; {len(kept)} files not attributed are kept, {len(gone)} files and {len(generations) - len(present)} generations are already gone")
        return plan
    try:
        for item in generations:
            delete_generation(client, item)
        for item in delete:
            delete_upload(client, item)
    finally:
        for segment in segments:
            own = {item["id"] for item in segment["generations"]}
            named = {item["filename"] for item in segment["files"]}
            trace = {"run_id": segment["run_id"], "confirmed": True, "done_at": datetime.now(UTC).isoformat(timespec="seconds"), "segments": plan["segments"], "clock": clock, "generations": [item for item in generations if item["id"] in own], "files": [item for item in files if item["filename"] in named]}
            plan.setdefault("traces", []).append(str(write_trace(segment["dir"], trace)))
    left = [item["id"] for item in generations if item.get("exists_after")]
    files_left = [item["filename"] for item in delete if item.get("exists_after")]
    errors = [item for item in generations + delete if item.get("error")]
    log(f"{len(present)} generations and {len(delete)} files of {names} deleted, {len(left)} generations and {len(files_left)} files still there, {len(errors)} errors; {len(kept)} files not attributed are kept")
    return plan
