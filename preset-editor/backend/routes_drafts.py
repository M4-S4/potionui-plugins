import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_admin_user
from src.plugin_api.storage import generate_ulid

from . import catalog, core_bridge, drafts, paths, publish, scaffold, settings
from .drafts import DraftError
from .publish import PublishError
from .routes_common import draft_payload, error, ok
from .schema import DraftCreate, PublishRequest

logger = logging.getLogger("plugins.preset-editor")

router = APIRouter(dependencies=[Depends(get_current_admin_user)])

_publishing = asyncio.Lock()


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
    preset_id = body.preset_id or generate_ulid()
    try:
        if body.mode == "copy":
            template = core_bridge.find_preset(body.from_id)
            if template is None:
                raise error(404, "not_found", f"no preset '{body.from_id}' in the catalogue")
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
        else:
            produced = scaffold.preset_files(
                preset_id=preset_id,
                name=body.name,
                category=body.resolved_category,
                engine=body.engine,
                modes=body.modes,
                driver=body.driver,
                family=body.family.to_pipes() if body.family is not None else None,
            )
            draft = await asyncio.to_thread(
                drafts.create_blank,
                paths.roots(),
                files=produced,
                preset_id=preset_id,
                name=body.name,
                target_dir=body.target_dir,
                created_by=current_user.id,
            )
    except DraftError as failure:
        raise error(409, failure.code, failure.message)
    except OSError as failure:
        logger.exception("[PRESET-EDITOR] Could not write the draft of %s", body.name)
        raise error(500, "copy_failed", f"could not write the draft: {failure}")
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
    async with _publishing:
        try:
            await asyncio.to_thread(
                publish.check_collisions,
                roots,
                preset_id=draft.preset_id,
                target_dir=draft.target_dir,
                catalog=core_bridge.catalog(),
                disk_roots=core_bridge.preset_roots(),
            )
            swapped = await asyncio.to_thread(publish.publish_draft, roots, draft)
        except PublishError as failure:
            raise error(409, failure.code, failure.message)
        await core_bridge.reload_presets_async()
        template = core_bridge.find_preset(draft.preset_id)
        expected = paths.local_preset_dir(roots, draft.target_dir).resolve()
        if template is None or Path(template.path).resolve() != expected:
            refused = core_bridge.load_errors().get(expected / "preset.yml", [])
            await asyncio.to_thread(publish.rollback_publish, roots, swapped["target"], swapped["backup"])
            await core_bridge.reload_presets_async()
            raise error(
                409, "load_failed",
                "PotionUI refused to load the published preset, so the previous state was put back",
                errors=refused,
            )
        archived = await asyncio.to_thread(
            publish.commit_publish, roots, draft, swapped["backup"], history_depth=settings.get_setting("history_depth")
        )
    install = body.install if body.install is not None else settings.get_setting("install_after_publish")
    installed = await asyncio.to_thread(core_bridge.is_installed, draft.preset_id)
    if install and not installed:
        await asyncio.to_thread(core_bridge.install_preset, draft.preset_id, current_user)
        installed = True
    drafts.mark_published(draft)
    return ok(
        {
            "preset_id": draft.preset_id,
            "target_dir": draft.target_dir,
            "archived": archived,
            "installed": installed,
            "lint": {"errors": errors, "warnings": warnings},
            "preset": catalog.summary(template),
            "draft": draft_payload(draft),
        }
    )
