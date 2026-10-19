import math
from typing import Any, Dict, NoReturn, Optional

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from . import access, tracker
from .core_bridge import User, get_current_active_user
from .generation import Blocked
from .responses import fail, ok
from .routes_takes import blocked
from .scene3d import captures, files, formats, jobs, renders
from .scene3d.storage import SceneError

router = APIRouter()

TEXT_LIMIT = 200


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _scene_error(exc: SceneError) -> NoReturn:
    fail(exc.status_code, exc.error, exc.message, **exc.data)


def _object(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    return body


def _id(body: Dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value or len(value) > TEXT_LIMIT:
        _invalid(f"{key} must be a non-empty string of at most {TEXT_LIMIT} characters.")
    return value


def _name(body: Dict[str, Any]) -> Optional[str]:
    value = body.get("name")
    if value is not None and (not isinstance(value, str) or len(value) > TEXT_LIMIT):
        _invalid(f"name must be a string of at most {TEXT_LIMIT} characters, or null.")
    return value


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(body: Dict[str, Any], key: str, low: int, high: int) -> int:
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        _invalid(f"{key} must be an integer from {low} to {high}.")
    return value


def _job_for(project: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    job = jobs.get_job(job_id)
    if job is None or job["project_id"] != project["id"]:
        fail(404, "job_not_found", "The scene job does not exist.")
    return job


def _render_for(project: Dict[str, Any], render_id: str) -> Dict[str, Any]:
    render = renders.get_render(project["id"], render_id)
    if render is None:
        fail(404, "render_not_found", "The render does not exist.")
    return render


@router.post("/projects/{project_id}/scenes/from-image", status_code=202)
async def scene_from_image(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Make a Gaussian Splat scene of an image of the project, or of a frame of one of its videos, with the Image to Splat preset."""
    body = _object(body)
    scene_id, asset_id = _id(body, "sceneId"), _id(body, "assetId")
    time = body.get("time")
    if time is not None and not (_number(time) and time >= 0):
        _invalid("time must be a number of seconds from the start of the video, or null.")
    _name(body)
    project = access.project_for(user, project_id)
    try:
        job = await jobs.from_image(access.owner_of(user, project), project, scene_id, asset_id, time)
    except Blocked as exc:
        blocked(exc)
    except SceneError as exc:
        _scene_error(exc)
    tracker.ensure_running()
    return ok({"job": jobs.public(job)})


@router.get("/projects/{project_id}/scenes/jobs")
def list_scene_jobs(project_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The splat jobs of a project, oldest first."""
    access.project_for(user, project_id)
    return ok({"jobs": [jobs.public(job) for job in jobs.list_project(project_id)]})


@router.post("/projects/{project_id}/scenes/jobs/{job_id}/cancel")
async def cancel_scene_job(project_id: str, job_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Cancel a queued or running splat job and refund its minutes."""
    project = access.project_for(user, project_id)
    job = _job_for(project, job_id)
    return ok({"job": jobs.public(await jobs.cancel(access.owner_of(user, project), job))})


@router.post("/projects/{project_id}/scene-files", status_code=201)
async def upload_scene_file(
    project_id: str,
    file: Optional[UploadFile] = File(default=None),
    kind: Optional[str] = Form(default=None),
    user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Store a Gaussian Splat (.ply, .spz, .splat) or a Blender scene (.glb) of at most 1 GiB, with its gaussian count, source view or cameras."""
    if kind not in formats.KINDS:
        _invalid(f"kind must be one of: {', '.join(formats.KINDS)}.")
    if file is None or not file.filename:
        _invalid("The request needs a file.")
    try:
        files.accepted_format(kind, file.filename)
        project = access.project_for(user, project_id)
        stored = await files.store_upload(project["id"], project["user_id"], kind, file)
    except SceneError as exc:
        _scene_error(exc)
    return ok({"file": files.public(stored)})


@router.get("/projects/{project_id}/scene-files/{file_id}")
def scene_file(project_id: str, file_id: str, user: User = Depends(get_current_active_user)) -> FileResponse:
    """A stored scene file."""
    project = access.project_for(user, project_id)
    found = files.get_file(file_id)
    path = files.path_of(found) if found is not None and found["project_id"] == project["id"] else None
    if path is None or not path.is_file():
        fail(404, "file_not_found", "The scene file does not exist.")
    return FileResponse(path, media_type=formats.MEDIA_TYPES.get(found["format"], "application/octet-stream"))


@router.post("/projects/{project_id}/captures")
async def store_capture(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Store a PNG capture of a scene as an image of the project owner's library."""
    body = _object(body)
    png = captures.decode(body.get("png"), "png")
    if png is None:
        _invalid("png must be a base64 data URL of a PNG image of at most 40 MiB.")
    name = _name(body)
    project = access.project_for(user, project_id)
    try:
        media = await captures.capture(access.owner_of(user, project), project["id"], png, name)
    except SceneError as exc:
        _scene_error(exc)
    return ok({"media": media})


@router.post("/projects/{project_id}/renders", status_code=201)
def open_render(
    project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Open a render of a plan 3D: a folder that receives its JPEG frames before they are encoded into a video."""
    body = _object(body)
    width = _integer(body, "width", 16, renders.MAX_SIDE)
    height = _integer(body, "height", 16, renders.MAX_SIDE)
    if width % 2 or height % 2:
        _invalid("width and height must be even.")
    fps = body.get("fps")
    if not _number(fps) or not 0 < fps <= renders.MAX_FPS:
        _invalid(f"fps must be a number above 0 and at most {renders.MAX_FPS}.")
    frames = _integer(body, "frames", 1, renders.MAX_FRAMES)
    name = _name(body) or ""
    project = access.project_for(user, project_id)
    render = renders.create(project["id"], user.id, width, height, float(fps), frames, name)
    return ok({"render": {key: render[key] for key in ("id", "width", "height", "fps", "frames")}})


@router.post("/projects/{project_id}/renders/{render_id}/frames")
def render_frames(
    project_id: str, render_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Store a batch of JPEG frames of a render; answers how many of its frames have arrived."""
    body = _object(body)
    start, images = body.get("start"), body.get("images")
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        _invalid("start must be the index of the first frame of the batch.")
    if not isinstance(images, list) or not 1 <= len(images) <= renders.MAX_BATCH:
        _invalid(f"images must be a list of 1 to {renders.MAX_BATCH} JPEG data URLs.")
    decoded = [captures.decode(image, "jpeg") for image in images]
    bad = next((index for index, data in enumerate(decoded) if data is None), None)
    if bad is not None:
        _invalid(f"images[{bad}] is not a base64 data URL of a JPEG image of at most 40 MiB.")
    project = access.project_for(user, project_id)
    render = _render_for(project, render_id)
    if start + len(decoded) > render["frames"]:
        _invalid(f"The render has {render['frames']} frames; this batch ends past them.")
    return ok({"received": renders.add_frames(render, start, decoded)})


@router.post("/projects/{project_id}/renders/{render_id}/finish")
async def finish_render(project_id: str, render_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Encode a render whose frames all arrived into an H.264 MP4 and store it as a video of the project owner's library."""
    project = access.project_for(user, project_id)
    render = _render_for(project, render_id)
    try:
        media = await renders.finish(access.owner_of(user, project), render)
    except SceneError as exc:
        _scene_error(exc)
    return ok({"media": media})


@router.delete("/projects/{project_id}/renders/{render_id}")
def delete_render(project_id: str, render_id: str, user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """Stop and delete a render in progress with its frames."""
    project = access.project_for(user, project_id)
    renders.delete(_render_for(project, render_id))
    return ok({})
