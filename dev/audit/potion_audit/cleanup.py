import json
import time
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
MARGIN_FLOOR_SECONDS = 60.0
STOPPING = {401, 403}
FAILURES = (ApiError, ApiUnreachable, ValueError)
UNRECORDED = "--allow-unrecorded-instance"
VP_ROUTE = "/api/plugins/video-producer"
VP_PLUGIN = "video-producer"
TRACE_ATTEMPTS = 3
TRACE_PAUSE_SECONDS = 0.5


class TraceError(RuntimeError):
    pass


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


def account_identity(client: ApiClient) -> dict | None:
    try:
        me = unwrap(client.get_json("/api/auth/me"))
    except FAILURES:
        return None
    if not isinstance(me, dict) or not me.get("id"):
        return None
    return {"account_id": str(me["id"]), "account_created_at": me.get("created_at")}


def _mark_key(mark: dict) -> tuple | None:
    if not mark.get("id"):
        return None if mark.get("total") == 0 else ()
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
    margin = None if offset is None else round(max(abs(offset) + CLOCK_SLACK_SECONDS, MARGIN_FLOOR_SECONDS), 3)
    return {"server_offset_seconds": offset, "margin_seconds": margin, "measured": "when the cleanup runs"}


def guard(record: dict, name: str, current: dict | None, allow_unrecorded: bool) -> tuple[list[str], list[str]]:
    refusals = []
    notes = []
    if not record.get("ended_at"):
        refusals.append(f"{name} recorded no end: it may still be running, so --confirm refuses it")
    recorded = record.get("account")
    if not isinstance(recorded, dict) or not recorded.get("account_id"):
        notes.append(f"{name} recorded no account, so the instance cannot be checked")
        if not allow_unrecorded:
            refusals.append(f"{name} recorded no account: pass {UNRECORDED} to delete on this instance anyway")
    elif current is None:
        refusals.append("the account of the instance could not be read")
    elif recorded.get("account_id") != current.get("account_id") or (recorded.get("account_created_at") and current.get("account_created_at") and recorded["account_created_at"] != current["account_created_at"]):
        refusals.append(f"{name} ran with another account or on another instance: account {recorded.get('account_id')}, this one {current.get('account_id')}")
    else:
        notes.append(f"{name} ran with this account on this instance")
    return refusals, notes


def refuse_cleaned(run_dir: Path) -> None:
    traces = sorted(path.name for path in run_dir.glob(f"{TRACE}*.json"))
    if traces:
        raise RunRefused(f"{run_dir.name} holds the trace of a cleanup ({', '.join(traces)}): start the run under a new run id")


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
    if not item["id"]:
        return {**found, "attributed": False, "proof": "the runs recorded no library id for it"}
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


def fatal(error: Exception) -> bool:
    return isinstance(error, ApiUnreachable) or (isinstance(error, ApiError) and error.status in STOPPING)


def failed_item(item: dict, error: Exception) -> Exception:
    item["error"] = str(error) or type(error).__name__
    item.setdefault("exists_after", None)
    return error


def delete_upload(client: ApiClient, item: dict) -> Exception | None:
    try:
        answer = client.delete_json(f"/api/media/uploads/{urllib.parse.quote(item['filename'], safe='')}", missing_ok=True)
        item["deleted"] = answer is not None
        item["exists_after"] = upload_exists(client, item["filename"])
    except FAILURES as error:
        return failed_item(item, error)
    return None


def generation_record(client: ApiClient, generation_id: str):
    return client.get_json(f"/api/generations/history/{generation_id}", missing_ok=True)


def generation_on_instance(client: ApiClient, generation_id: str) -> bool:
    return generation_record(client, generation_id) is not None


def check_generation(client: ApiClient, item: dict, window: tuple | None, margin: float | None) -> None:
    found = generation_record(client, item["id"])
    item["on_instance"] = found is not None
    if found is None:
        item.update(attributed=None, proof="no longer on the instance")
        return
    try:
        data = unwrap(found) or {}
    except ValueError as error:
        item.update(attributed=False, proof=f"its record could not be read: {error}")
        return
    reasons = []
    checked = []
    created = instant(data.get("created_at"))
    if created is None:
        checked.append("the record gives no creation time")
    elif window is None or margin is None:
        checked.append("its creation time is not checked: the run recorded no start and end, or the clock of the server could not be read")
    elif window[0] - timedelta(seconds=margin) <= created <= window[1] + timedelta(seconds=margin):
        checked.append(f"created at {_when(created)}, during the run")
    else:
        reasons.append(f"created at {_when(created)}, more than {margin} s outside the run")
    if item.get("preset_id") and data.get("preset_id"):
        if str(data["preset_id"]) == str(item["preset_id"]):
            checked.append("the preset the run recorded")
        else:
            reasons.append(f"its preset is {data['preset_id']}, the run recorded {item['preset_id']}")
    if item.get("mode") and data.get("mode"):
        if str(data["mode"]) == str(item["mode"]):
            checked.append("the mode the run recorded")
        else:
            reasons.append(f"its mode is {data['mode']}, the run recorded {item['mode']}")
    item["record"] = {key: data.get(key) for key in ("created_at", "preset_id", "mode", "status")}
    item["attributed"] = not reasons
    item["proof"] = "; ".join(reasons) if reasons else "the run recorded its id; " + "; ".join(checked)


def delete_generation(client: ApiClient, item: dict) -> Exception | None:
    try:
        answer = client.delete_json(f"/api/generations/history/{item['id']}", missing_ok=True)
        item["message"] = (answer or {}).get("message") if isinstance(answer, dict) else None
        item["exists_after"] = generation_on_instance(client, item["id"])
    except FAILURES as error:
        return failed_item(item, error)
    return None


def delete_all(client: ApiClient, steps: list, save: Callable[[], None]) -> str | None:
    stopped = None
    for act, item in steps:
        if stopped:
            item["skipped"] = stopped
            continue
        error = act(client, item)
        try:
            save()
        except TraceError as problem:
            stopped = f"not tried: the cleanup stopped because {problem}"
            continue
        if error is not None and fatal(error):
            stopped = f"not tried: the cleanup stopped after {item['error']}"
    return stopped


def first_save(save: Callable[[], None]) -> None:
    try:
        save()
    except TraceError as problem:
        raise RunRefused(f"nothing was deleted: {problem}") from None


def last_save(save: Callable[[], None], plan: dict, log: Callable[[str], None]) -> None:
    try:
        save()
    except TraceError as problem:
        plan.update(trace_error=str(problem), failed=True)
        log(f"error: {problem}")


def tally(items: list[dict]) -> dict:
    tried = [item for item in items if not item.get("skipped")]
    done = [item for item in tried if item.get("exists_after") is False and not item.get("error")]
    return {"deleted": len(done), "not_deleted": len(tried) - len(done), "not_tried": len(items) - len(tried)}


def split(items: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    return [item for item in items if item["attributed"] and item["on_instance"]], [item for item in items if item["on_instance"] and not item["attributed"]], [item for item in items if not item["on_instance"]]


def trace_path(run_dir: Path) -> Path:
    path = run_dir / f"{TRACE}.json"
    number = 2
    while path.exists():
        path = run_dir / f"{TRACE}-{number}.json"
        number += 1
    return path


def save_trace(path: Path, data: dict) -> None:
    partial = path.with_name(path.name + ".part")
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    last = None
    for attempt in range(TRACE_ATTEMPTS):
        try:
            partial.write_text(text, encoding="utf-8", newline="\n")
            partial.replace(path)
            return
        except OSError as error:
            last = error
            if attempt + 1 < TRACE_ATTEMPTS:
                time.sleep(TRACE_PAUSE_SECONDS)
    raise TraceError(f"the trace {path.name} could not be written after {TRACE_ATTEMPTS} attempts ({last}); {partial} holds the latest state written")


def project_references(client: ApiClient, rows: dict[str, dict], skip: set[str] | frozenset = frozenset()) -> tuple[dict[str, list[str]], str | None]:
    by_id = {str(row["id"]): name for name, row in rows.items() if row.get("id")}
    found = {}
    try:
        plugins = unwrap(client.get_json("/api/plugins")) or []
        if not any(isinstance(plugin, dict) and plugin.get("id") == VP_PLUGIN for plugin in plugins):
            return {}, None
        listed = (unwrap(client.get_json(f"{VP_ROUTE}/projects")) or {}).get("projects") or []
        for entry in listed:
            project_id = str((entry or {}).get("id") or "")
            if not project_id or project_id in skip:
                continue
            project = (unwrap(client.get_json(f"{VP_ROUTE}/projects/{project_id}")) or {}).get("project") or {}
            for asset in (project.get("doc") or {}).get("assets") or ():
                origin = asset.get("origin") if isinstance(asset, dict) else None
                if isinstance(origin, dict) and origin.get("kind") == "library" and str(origin.get("itemId")) in by_id:
                    found.setdefault(by_id[str(origin["itemId"])], []).append(project_id)
    except FAILURES as error:
        return {}, f"the Video Producer projects of the account could not be read ({str(error) or type(error).__name__})"
    return found, None


def keep_referenced(files: list[dict], references: dict[str, list[str]], error: str | None) -> None:
    for item in files:
        if not item["attributed"] or not item["on_instance"]:
            continue
        if error:
            item.update(attributed=False, proof=f"{error}: a project may point to it")
        elif item["filename"] in references:
            item.update(attributed=False, proof=f"the document of the Video Producer project {', '.join(dict.fromkeys(references[item['filename']]))} points to it")


def log_files(items: list[dict], log: Callable[[str], None]) -> None:
    delete, kept, gone = split(items)
    for item in delete:
        log(f"file {item['filename']} ({item['kind']}): to delete, {item['proof']}")
    for item in kept:
        log(f"file {item['filename']} ({item['kind']}): not attributed, kept: {item['proof']}")
    for item in gone:
        log(f"file {item['filename']} ({item['kind']}): no longer on the instance")


def log_generations(items: list[dict], log: Callable[[str], None], label: Callable[[dict], str]) -> None:
    for item in items:
        if not item["on_instance"]:
            log(f"generation {item['id']}{label(item)}: no longer on the instance")
        elif item["attributed"]:
            log(f"generation {item['id']}{label(item)}: to delete, {item['proof']}")
        else:
            log(f"generation {item['id']}{label(item)}: not attributed, kept: {item['proof']}")


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
    for path in sorted((run_dir / "cells").glob("*/result.json")):
        result = _read(path)
        if result.get("generation_id"):
            request = _read(path.with_name("request.json"))
            found.setdefault(result["generation_id"], {"id": result["generation_id"], "cell": result.get("cell"), "warm_repeat": result.get("warm_repeat", False), "verdict": result.get("verdict"), "preset_id": request.get("preset_id"), "mode": request.get("mode")})
    for entry in run.get("cells") or ():
        if entry.get("generation_id"):
            found.setdefault(entry["generation_id"], {"id": entry["generation_id"], "cell": entry.get("cell"), "warm_repeat": entry.get("warm_repeat", False), "verdict": entry.get("verdict"), "preset_id": None, "mode": None})
    return list(found.values())


def segment_dirs(paths: list[Path]) -> list[Path]:
    found = []
    for path in paths:
        night = path / "night.json"
        if night.is_file() and not (path / "run.json").is_file():
            found += [path.parent / str(segment["run_id"]) for segment in json.loads(night.read_text(encoding="utf-8")).get("segments") or () if segment.get("run_id")]
        else:
            found.append(path)
    return list(dict.fromkeys(found))


def matrix_cleanup(client: ApiClient, run_dirs: list[Path], confirm: bool, log: Callable[[str], None] = print, allow_unrecorded: bool = False) -> dict:
    segments = []
    for run_dir in segment_dirs(run_dirs):
        path = run_dir / "run.json"
        if not path.is_file():
            raise RunRefused(f"{run_dir.name} holds no run.json: cleanup takes the segment folders of a matrix run, or the folder of its night")
        run = json.loads(path.read_text(encoding="utf-8"))
        if run.get("dry_run"):
            raise RunRefused(f"{run_dir.name} is a dry run: it created nothing on the instance")
        span = run_span(str(run.get("run_id") or run_dir.name), run)
        segments.append({"dir": run_dir, "run": run, "run_id": span["run"], "span": span, "generations": matrix_generations(run_dir, run), "files": recorded_uploads(run_dir, span)})
    current = account_identity(client)
    refusals = []
    notes = []
    for segment in segments:
        refused, noted = guard(segment["run"], segment["run_id"], current, allow_unrecorded)
        refusals += refused
        notes += noted
    clock = clock_margin(client)
    rows = library(client)
    merged = {}
    for segment in segments:
        for item in segment["files"]:
            merge(merged, item)
    files = [attribute(item, rows, clock["margin_seconds"]) for item in merged.values()]
    references, unread = project_references(client, rows)
    keep_referenced(files, references, unread)
    if unread:
        notes.append(unread + ", so the files of the run are kept")
    generations = []
    for segment in segments:
        for item in segment["generations"]:
            if item["id"] not in {known["id"] for known in generations}:
                entry = {**item, "run": segment["run_id"]}
                check_generation(client, entry, segment["span"]["window"], clock["margin_seconds"])
                generations.append(entry)
    for line in notes + refusals:
        log(line)
    log_generations(generations, log, lambda item: f" ({item['cell']}{' warm' if item.get('warm_repeat') else ''}, {item['run']})")
    log_files(files, log)
    delete, kept, gone = split(files)
    doomed, spared, absent = split(generations)
    names = ", ".join(segment["run_id"] for segment in segments)
    plan = {"confirmed": confirm, "segments": [segment["run_id"] for segment in segments], "clock": clock, "account": current, "notes": notes, "refusals": refusals, "generations": generations, "files": files, "failed": False}
    if not confirm:
        log(f"{len(doomed)} generations and {len(delete)} files of {names} to delete: pass --confirm to delete them; not attributed and kept: {len(spared)} generations, {len(kept)} files; already gone: {len(absent)} generations, {len(gone)} files" + ("; --confirm would refuse: " + "; ".join(refusals) if refusals else ""))
        return plan
    if refusals:
        raise RunRefused("; ".join(refusals))
    traces = []
    for segment in segments:
        own = {item["id"] for item in segment["generations"]}
        named = {item["filename"] for item in segment["files"]}
        trace = {"run_id": segment["run_id"], "confirmed": True, "state": "deleting", "started_at": datetime.now(UTC).isoformat(timespec="seconds"), "segments": plan["segments"], "clock": clock, "account": current, "generations": [item for item in generations if item["id"] in own], "files": [item for item in files if item["filename"] in named]}
        traces.append((trace_path(segment["dir"]), trace))

    def save() -> None:
        for path, trace in traces:
            save_trace(path, trace)

    first_save(save)
    stopped = delete_all(client, [(delete_generation, item) for item in doomed] + [(delete_upload, item) for item in delete], save)
    counts = {"generations": tally(doomed), "files": tally(delete)}
    plan.update(traces=[str(path) for path, _ in traces], stopped=stopped, counts=counts, failed=bool(stopped) or any(value["not_deleted"] or value["not_tried"] for value in counts.values()))
    for _, trace in traces:
        trace.update(state="stopped" if stopped else "done", stopped=stopped, counts=counts, done_at=datetime.now(UTC).isoformat(timespec="seconds"))
    last_save(save, plan, log)
    log(f"{names}: {counts['generations']['deleted']} of {len(doomed)} generations and {counts['files']['deleted']} of {len(delete)} files deleted; not deleted: {counts['generations']['not_deleted']} generations, {counts['files']['not_deleted']} files; not tried: {counts['generations']['not_tried'] + counts['files']['not_tried']}; {len(kept)} files and {len(spared)} generations not attributed are kept" + (f"; {stopped}" if stopped else ""))
    return plan
