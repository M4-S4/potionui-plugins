import asyncio
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from src.plugin_api import User, generate_ulid, get_current_admin_user

from . import archive, core_bridge, drafts, paths
from .drafts import DraftError
from .files import FilesError
from .routes_common import draft_payload, error, ok
from .routes_files import STATUS_BY_CODE
from .routes_media import admin_viewer
from .routes_presets import local_template

router = APIRouter(dependencies=[Depends(get_current_admin_user)])
public_router = APIRouter()


def _load(draft_id: str) -> drafts.Draft:
    try:
        return drafts.load(paths.roots(), draft_id)
    except DraftError as failure:
        raise error(404, failure.code, failure.message)


def _zip(data: bytes, filename: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"}
    return Response(content=data, media_type="application/zip", headers=headers)


@public_router.get("/drafts/{draft_id}/export")
async def export_draft(draft_id: str, viewer: User = Depends(admin_viewer)):
    draft = _load(draft_id)
    data = await asyncio.to_thread(archive.export_dir, draft.dir)
    return _zip(data, f"{draft.preset_id}-draft.zip")


@public_router.get("/presets/{preset_id}/export")
async def export_preset(preset_id: str, viewer: User = Depends(admin_viewer)):
    template = local_template(preset_id)
    data = await asyncio.to_thread(archive.export_dir, Path(template.path))
    return _zip(data, f"{template.id}.zip")


@router.post("/drafts/import", status_code=201)
async def import_draft(
    file: UploadFile = File(...),
    model_dir: str = Form(...),
    variant_dir: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    preset_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_admin_user),
):
    wanted_id = (preset_id or "").strip()
    wanted_name = (name or "").strip()
    try:
        target_dir = paths.target_dir(model_dir.strip(), (variant_dir or "").strip() or None)
        if wanted_id:
            paths.check_preset_id(wanted_id)
    except ValueError as failure:
        raise error(422, "invalid_request", str(failure))
    data = await file.read(archive.MAX_ARCHIVE_BYTES + 1)
    roots = paths.roots()
    roots.drafts.mkdir(parents=True, exist_ok=True)
    staging = roots.drafts / f".import-{generate_ulid()}"
    try:
        await asyncio.to_thread(archive.extract, data, staging)
        header = drafts.read_header(staging)
        wanted_id = wanted_id or str(header.get("id") or "")
        draft = await asyncio.to_thread(
            drafts.create_import,
            roots,
            source_dir=staging,
            preset_id=wanted_id,
            name=wanted_name or str(header.get("name") or wanted_id),
            target_dir=target_dir,
            created_by=current_user.id,
            source=f"import:{Path(file.filename or 'archive.zip').name}",
            rewrite=bool(preset_id and preset_id.strip()) or bool(wanted_name),
        )
    except FilesError as failure:
        raise error(STATUS_BY_CODE.get(failure.code, 400), failure.code, failure.message, **failure.extra)
    except DraftError as failure:
        raise error(400, failure.code, failure.message)
    except ValueError as failure:
        raise error(422, "invalid_request", str(failure))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    errors, warnings = await core_bridge.lint_async(draft.dir)
    drafts.record_lint(draft, errors, warnings)
    return ok(draft_payload(draft))
