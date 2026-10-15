import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from src.plugin_api import User, get_current_admin_user

from . import core_bridge, drafts, media, paths
from .drafts import DraftError
from .files import FilesError
from .routes_common import error, ok
from .routes_files import STATUS_BY_CODE
from .schema import MediaUpdate

router = APIRouter(dependencies=[Depends(get_current_admin_user)])
public_router = APIRouter()

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def _load(draft_id: str) -> drafts.Draft:
    try:
        return drafts.load(paths.roots(), draft_id)
    except DraftError as failure:
        raise error(404, failure.code, failure.message)


def _files_error(failure: FilesError):
    return error(STATUS_BY_CODE.get(failure.code, 400), failure.code, failure.message, **failure.extra)


async def _lint(draft: drafts.Draft):
    errors, warnings = await core_bridge.lint_async(draft.dir)
    drafts.record_lint(draft, errors, warnings)
    return {"errors": errors, "warnings": warnings}


async def _changed(draft: drafts.Draft):
    drafts.save(draft)
    return {"media": media.listing(draft.dir), "files": drafts.file_tree(draft.dir), "lint": await _lint(draft)}


async def admin_viewer(request: Request) -> User:
    viewer = await core_bridge.media_viewer(request)
    if viewer is None:
        raise error(401, "unauthorized", "Could not validate credentials")
    return await get_current_admin_user(viewer)


@router.get("/drafts/{draft_id}/media")
async def list_media(draft_id: str):
    draft = _load(draft_id)
    return ok(media.listing(draft.dir))


@router.post("/drafts/{draft_id}/media", status_code=201)
async def upload_media(
    draft_id: str,
    file: UploadFile = File(...),
    role: str = Form("gallery"),
    caption: Optional[str] = Form(None),
    mode: Optional[str] = Form(None),
):
    draft = _load(draft_id)
    data = await file.read(media.MAX_UPLOAD_BYTES + 1)
    try:
        stored = await asyncio.to_thread(media.store, draft.dir, role, file.filename or "", data)
        if role == "cover":
            media.set_cover(draft.dir, stored["path"])
        elif role == "gallery":
            media.add_gallery_item(draft.dir, stored["path"], caption=(caption or "").strip() or None, mode=(mode or "").strip() or None)
    except FilesError as failure:
        raise _files_error(failure)
    return ok({**stored, **await _changed(draft)})


@router.put("/drafts/{draft_id}/media")
async def update_media(draft_id: str, body: MediaUpdate):
    draft = _load(draft_id)
    try:
        media.declare(
            draft.dir,
            cover=body.cover if "cover" in body.model_fields_set else media.KEEP,
            gallery=[item.model_dump(exclude_none=True) for item in body.gallery] if body.gallery is not None else media.KEEP,
        )
    except FilesError as failure:
        raise _files_error(failure)
    return ok(await _changed(draft))


@router.delete("/drafts/{draft_id}/media/{path:path}")
async def delete_media(draft_id: str, path: str):
    draft = _load(draft_id)
    try:
        media.remove(draft.dir, path)
    except FilesError as failure:
        raise _files_error(failure)
    return ok({"path": path, **await _changed(draft)})


@public_router.get("/drafts/{draft_id}/public/{path:path}")
async def serve_media(draft_id: str, path: str, viewer: User = Depends(admin_viewer)):
    draft = _load(draft_id)
    try:
        target = media.public_path(draft.dir, path)
    except FilesError as failure:
        raise _files_error(failure)
    if not target.is_file():
        raise error(404, "not_found", f"no media file {path}")
    return FileResponse(target, media_type=MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream"), headers={"Cache-Control": "no-store"})
