import math
from typing import Any, Dict, List, NoReturn, Optional, Tuple

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse, Response

from . import access, core_bridge, projects, settings, takes
from .core_bridge import AccountType, LimitExceeded, MediaRefError, User, get_current_active_user
from .exports import EXCHANGE, content_disposition, jobs, render, video
from .exports.common import timing_error
from .exports.media import MEDIA_MODES, Resolver, basename, exportable, files_of
from .responses import fail, ok

router = APIRouter()

MB = 1024 * 1024


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _job_not_found() -> NoReturn:
    fail(404, "job_not_found", "The export does not exist.")


def _object(body: Any) -> Dict[str, Any]:
    if body is None:
        return {}
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    return body


def _timed(doc: Dict[str, Any], frames: bool = True) -> None:
    error = timing_error(doc, frames)
    if error is not None:
        fail(422, "invalid_doc", error)


def _locale(user: User) -> str:
    return settings.user_locale(user.id) or "en"


def _job_for(user: User, job_id: str) -> Dict[str, Any]:
    job = jobs.get_job(job_id)
    if job is None:
        _job_not_found()
    if job["user_id"] != user.id and user.account_type != AccountType.ADMIN:
        project = projects.get_project(job["project_id"])
        if project is None or not access.can_reach(user, project):
            _job_not_found()
    return job


@router.get("/projects/{project_id}/exports")
def list_exports(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The video exports of a project, newest first."""
    access.project_for(user, project_id)
    return ok({"jobs": [jobs.public(job) for job in jobs.list_project(project_id)]})


@router.get("/projects/{project_id}/exports/{fmt}")
def exchange_export(
    project_id: str, fmt: str, media: str = Query("path"), user: User = Depends(get_current_active_user)
) -> Response:
    """The sequence as FCPXML, OpenTimelineIO, EDL or SubRip, naming each shot's real file by path or by name."""
    if fmt not in EXCHANGE:
        _invalid(f"The format must be one of: {', '.join(EXCHANGE)}.")
    if media not in MEDIA_MODES:
        _invalid(f"media must be one of: {', '.join(MEDIA_MODES)}.")
    project = access.project_for(user, project_id)
    _timed(project["doc"], frames=fmt != "srt")
    locale = _locale(user)
    files = {} if fmt == "srt" else files_of(
        project["doc"], takes.list_takes(project_id), Resolver(access.owner_of(user, project)), media=media, locale=locale
    )
    target = EXCHANGE[fmt]
    return Response(
        content=render(fmt, project["doc"], files, locale=locale).encode("utf-8"),
        media_type=target.content_type,
        headers={"Content-Disposition": content_disposition(project["name"], target.extension)},
    )


@router.post("/projects/{project_id}/exports/video", status_code=202)
def start_video_export(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Queue the assembly of the sequence into an MP4 for the web (project aspect) or social networks (9:16)."""
    body = _object(body)
    fmt, requested = body.get("format"), body.get("resolution")
    if not isinstance(fmt, str) or fmt not in video.FORMATS:
        _invalid(f"format must be one of: {', '.join(video.FORMATS)}.")
    if requested is not None and (not isinstance(requested, str) or requested not in video.RESOLUTIONS):
        _invalid(f"resolution must be one of: {', '.join(video.RESOLUTIONS)}.")
    project = access.project_for(user, project_id)
    _timed(project["doc"])
    owner = access.owner_of(user, project)
    if not core_bridge.find_ffmpeg():
        fail(409, "ffmpeg_unavailable", "ffmpeg is missing on the server.")
    if not exportable(project["doc"], takes.list_takes(project_id), Resolver(owner)):
        fail(409, "nothing_to_export", "No shot of the sequence has a file to export.")
    if jobs.has_active(project_id):
        fail(409, "export_running", "An export of this project is already queued or running.")
    quota = int(settings.get_setting("export_dir_quota_mb"))
    if not jobs.make_room(user.id, quota * MB):
        fail(429, "export_quota", f"Your export cache is over its {quota} MB budget.", quota_mb=quota)
    job = jobs.create_job(project_id, user.id, fmt, video.resolution_of(project["doc"], requested))
    if job is None:
        fail(409, "export_running", "An export of this project is already queued or running.")
    jobs.ensure_running()
    return ok({"job": jobs.public(job)})


@router.get("/exports/{job_id}")
def get_export(job_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """One video export."""
    return ok({"job": jobs.public(_job_for(user, job_id))})


@router.get("/exports/{job_id}/file")
def export_file(job_id: str, user: User = Depends(get_current_active_user)) -> FileResponse:
    """The exported MP4, as an attachment."""
    job = _job_for(user, job_id)
    if job["status"] != "done":
        fail(409, "not_ready", "The export is not finished.")
    path = jobs.file_path(job)
    if path is None:
        fail(404, "job_not_found", "The exported file is no longer available.")
    stem = job["file_name"].rsplit(".", 1)[0]
    project = projects.get_project(job["project_id"])
    name = f"{project['name']}_{job['resolution']}" if project else stem
    return FileResponse(path, media_type="video/mp4", headers={"Content-Disposition": content_disposition(name, "mp4")})


@router.delete("/exports/{job_id}")
async def delete_export(job_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Cancel a queued or running export, killing ffmpeg, or delete a finished one with its file."""
    job = _job_for(user, job_id)
    if job["status"] in jobs.ACTIVE:
        return ok({"job": jobs.public(jobs.cancel(job))})
    jobs.remove(job)
    return ok({"deleted": job_id})


def _seam_source(body: Any) -> Tuple[Optional[str], Any]:
    source = _object(body).get("source", "previous_last")
    if source == "previous_last":
        return None, "last"
    if not isinstance(source, dict) or set(source) != {"take_id", "at"} or not isinstance(source["take_id"], str):
        _invalid('source must be "previous_last" or {"take_id", "at"}.')
    at = source["at"]
    number = isinstance(at, (int, float)) and not isinstance(at, bool)
    if at != "last" and not (number and math.isfinite(at) and at >= 0):
        _invalid('at must be "last" or a number of seconds from the start of the take.')
    return source["take_id"], at


def _with_file(take: Optional[Dict[str, Any]]) -> bool:
    return bool(take and take["status"] == "done" and take.get("generation_id") and take.get("file_id") and take.get("file_path"))


def _previous_take(project: Dict[str, Any], clips: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
    if index == 0:
        fail(409, "no_previous_take", "This shot has no shot before it.")
    previous = clips[index - 1]
    shot_takes = [take for take in takes.list_takes(project["id"]) if take["shot_id"] == previous["id"]]
    chosen = next((take for take in shot_takes if take["id"] == previous.get("take")), None)
    if _with_file(chosen):
        return chosen
    finished = [take for take in shot_takes if _with_file(take)]
    if not finished:
        fail(409, "no_previous_take", "The shot before this one has no finished take.")
    return finished[-1]


@router.post("/projects/{project_id}/shots/{shot_id}/seam-frame")
async def seam_frame(
    project_id: str, shot_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Store a frame of a take, by default the last frame of the previous shot's take, as an image of the project owner."""
    take_id, at = _seam_source(body)
    project = access.project_for(user, project_id)
    clips = project["doc"].get("clips") or []
    index = next((position for position, clip in enumerate(clips) if clip["id"] == shot_id), None)
    if index is None:
        fail(404, "shot_not_found", "The shot does not exist.")
    if take_id is None:
        take = _previous_take(project, clips, index)
    else:
        take = access.take_in(project, take_id)
        if not _with_file(take):
            fail(409, "no_previous_take", "The take has no finished file.")
    owner = access.owner_of(user, project)
    ref = {"kind": "history", "generation_id": take["generation_id"], "file_id": take["file_id"]}
    try:
        frame = await core_bridge.extract_frame(owner, ref, at)
    except MediaRefError as exc:
        fail(502, "extract_failed", str(exc) or "The frame could not be extracted.", code=exc.code)
    except LimitExceeded as exc:
        fail(502, "extract_failed", str(exc) or "The storage plan of the project owner is full.", code="limit_exceeded")
    item = core_bridge.upload_item(owner.id, frame["value"]) or {}
    if not item.get("item_id"):
        fail(502, "extract_failed", "The frame was stored but its library item cannot be found.", code="store_failed")
    filename = basename(frame["value"])
    return ok(
        {
            "media": {
                "kind": "library",
                "item_id": item["item_id"],
                "media_type": "image",
                "url": f"/api/media/uploads/{filename}",
                "filename": frame.get("original_filename") or item.get("filename") or filename,
                "width": item.get("width"),
                "height": item.get("height"),
                "origin": {"kind": "library", "itemId": item["item_id"]},
            }
        }
    )
