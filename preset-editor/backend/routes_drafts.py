import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_admin_user
from src.plugin_api.storage import generate_ulid

from . import catalog, core_bridge, drafts, paths, publish, settings
from .drafts import DraftError
from .publish import PublishError
from .routes_common import draft_payload, error, ok
from .schema import DraftCreate, PublishRequest

logger = logging.getLogger("plugins.preset-editor")

router = APIRouter(dependencies=[Depends(get_current_admin_user)])


def _load(draft_id: str) -> drafts.Draft:
    try:
        return drafts.load(paths.roots(), draft_id)
    except DraftError as failure:
        raise error(404, failure.code, failure.message)


async def _lint(draft: drafts.Draft):
    errors, warnings = await core_bridge.lint_async(draft.dir)
    drafts.record_lint(draft, errors, warnings)
    return errors, warnings


@router.get("/drafts")
async def list_drafts():
    return ok([draft.to_dict() for draft in drafts.list_drafts(paths.roots())])


@router.post("/drafts", status_code=201)
async def create_draft(body: DraftCreate, current_user: User = Depends(get_current_admin_user)):
    template = core_bridge.find_preset(body.from_id)
    if template is None:
        raise error(404, "not_found", f"no preset '{body.from_id}' in the catalogue")
    preset_id = body.preset_id or generate_ulid()
    try:
        draft = await asyncio.to_thread(
            drafts.create_copy,
            paths.roots(),
            source_dir=Path(template.path),
            preset_id=preset_id,
            name=body.name,
            target_dir=body.target_dir,
            created_by=current_user.id,
            source=f"copy_of:{template.id}",
        )
    except DraftError as failure:
        raise error(409, failure.code, failure.message)
    except OSError as failure:
        logger.exception("[PRESET-EDITOR] Could not copy %s", template.path)
        raise error(500, "copy_failed", f"could not copy the preset: {failure}")
    await _lint(draft)
    return ok(draft_payload(draft))


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    return ok(draft_payload(_load(draft_id)))


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str):
    draft = _load(draft_id)
    await asyncio.to_thread(drafts.delete, paths.roots(), draft.draft_id)
    return ok({"draft_id": draft.draft_id})


@router.post("/drafts/{draft_id}/lint")
async def lint_draft(draft_id: str):
    draft = _load(draft_id)
    errors, warnings = await _lint(draft)
    return ok({"errors": errors, "warnings": warnings})


@router.post("/drafts/{draft_id}/publish")
async def publish_draft(draft_id: str, body: PublishRequest, current_user: User = Depends(get_current_admin_user)):
    draft = _load(draft_id)
    roots = paths.roots()
    errors, warnings = await _lint(draft)
    if errors:
        raise error(409, "lint_errors", "the preset has lint errors", lint={"errors": errors, "warnings": warnings})
    try:
        await asyncio.to_thread(
            publish.check_collisions,
            roots,
            preset_id=draft.preset_id,
            target_dir=draft.target_dir,
            catalog=core_bridge.catalog(),
            disk_roots=core_bridge.preset_roots(),
        )
        result = await asyncio.to_thread(
            publish.publish_draft, roots, draft, history_depth=settings.get_setting("history_depth")
        )
    except PublishError as failure:
        raise error(409, failure.code, failure.message)
    await core_bridge.reload_presets_async()
    template = core_bridge.find_preset(draft.preset_id)
    expected = paths.local_preset_dir(roots, draft.target_dir).resolve()
    if template is None or Path(template.path).resolve() != expected:
        raise error(500, "publish_unverified", "the preset was written but the catalogue does not show it at its folder")
    install = body.install if body.install is not None else settings.get_setting("install_after_publish")
    installed = await asyncio.to_thread(core_bridge.is_installed, draft.preset_id)
    if install and not installed:
        await asyncio.to_thread(core_bridge.install_preset, draft.preset_id, current_user)
        installed = True
    drafts.mark_published(draft)
    return ok(
        {
            **result,
            "installed": installed,
            "lint": {"errors": errors, "warnings": warnings},
            "preset": catalog.summary(template),
            "draft": draft_payload(draft),
        }
    )
