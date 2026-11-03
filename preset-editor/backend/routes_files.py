import asyncio
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, Header

from src.plugin_api import get_current_admin_user
from src.plugin_api.cloud import CLOUD_BLOCKS

from . import core_bridge, drafts, files, paths, scaffold
from .drafts import DraftError
from .files import FilesError
from .routes_common import error, ok
from .schema import FileWrite, ModeCreate

router = APIRouter(dependencies=[Depends(get_current_admin_user)])

STATUS_BY_CODE = {
    "invalid_path": 400,
    "invalid_request": 400,
    "not_text": 400,
    "not_media": 400,
    "too_large": 413,
    "not_found": 404,
    "precondition_required": 428,
    "precondition_failed": 412,
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


@router.get("/drafts/{draft_id}/files/{path:path}")
async def read_file(draft_id: str, path: str):
    draft = _load(draft_id)
    try:
        return ok(files.read_text(draft.dir, path))
    except FilesError as failure:
        raise _files_error(failure)


@router.put("/drafts/{draft_id}/files/{path:path}")
async def write_file(draft_id: str, path: str, body: FileWrite, if_match: Optional[str] = Header(None)):
    draft = _load(draft_id)
    try:
        written = await asyncio.to_thread(files.write_text, draft.dir, path, body.content, if_match)
    except FilesError as failure:
        raise _files_error(failure)
    drafts.save(draft)
    return ok({**written, "lint": await _lint(draft)})


@router.delete("/drafts/{draft_id}/files/{path:path}")
async def delete_file(draft_id: str, path: str):
    draft = _load(draft_id)
    try:
        removed = files.delete_file(draft.dir, path)
    except FilesError as failure:
        raise _files_error(failure)
    drafts.save(draft)
    return ok({**removed, "lint": await _lint(draft), "files": drafts.file_tree(draft.dir)})


@router.post("/drafts/{draft_id}/modes", status_code=201)
async def add_mode(draft_id: str, body: ModeCreate):
    draft = _load(draft_id)
    manifest = draft.dir / files.MANIFEST
    text = manifest.read_text(encoding="utf-8")
    if body.mode in files.manifest_modes(text) or (draft.dir / "modes" / body.mode).exists():
        raise error(409, "conflict", f"the mode {body.mode} already exists")
    engine = str(drafts.read_header(draft.dir).get("engine") or "native")
    if engine == "cloud" and body.mode not in scaffold.CLOUD_MODES:
        raise error(400, "invalid_request", f"unknown cloud mode {body.mode}; choose from {sorted(scaffold.CLOUD_MODES)}")
    family = body.family.to_pipes() if body.family is not None and engine not in ("cloud", "comfyui") else None
    scaffold.write_files(draft.dir, scaffold.mode_files(body.mode, engine, family))
    manifest.write_text(files.add_mode_to_manifest(text, body.mode), encoding="utf-8")
    drafts.save(draft)
    return ok({"mode": body.mode, "modes": files.manifest_modes(manifest.read_text(encoding="utf-8")), "files": drafts.file_tree(draft.dir), "lint": await _lint(draft)})


@router.delete("/drafts/{draft_id}/modes/{mode}")
async def remove_mode(draft_id: str, mode: str):
    draft = _load(draft_id)
    try:
        files.check_mode_name(mode)
    except FilesError as failure:
        raise _files_error(failure)
    manifest = draft.dir / files.MANIFEST
    text = manifest.read_text(encoding="utf-8")
    modes = files.manifest_modes(text)
    if mode not in modes and not (draft.dir / "modes" / mode).exists():
        raise error(404, "not_found", f"no mode {mode}")
    if modes == [mode]:
        raise error(409, "conflict", "a preset keeps at least one mode")
    citing = await asyncio.to_thread(files.citing_files, draft.dir, mode)
    if citing:
        raise error(
            409, "conflict",
            f"{', '.join(citing)} load files of the mode {mode}: point them elsewhere before removing it",
            citing=citing,
        )
    folder = draft.dir / "modes" / mode
    if folder.is_dir():
        await asyncio.to_thread(shutil.rmtree, folder)
    manifest.write_text(files.remove_mode_from_manifest(text, mode), encoding="utf-8")
    drafts.save(draft)
    return ok({"mode": mode, "modes": files.manifest_modes(manifest.read_text(encoding="utf-8")), "files": drafts.file_tree(draft.dir), "lint": await _lint(draft)})


@router.get("/reference/shared")
async def shared_reference():
    root = paths.SHARED_DIR
    listed = []
    if root.is_dir():
        listed = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.yml") if path.is_file())
    return ok({"root": "{{ paths._shared }}", "files": listed, "cloud_blocks": list(CLOUD_BLOCKS)})
