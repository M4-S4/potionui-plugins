import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends

from src.plugin_api import User, get_current_admin_user

from . import catalog, core_bridge, drafts, history, paths, publish, settings
from .drafts import DraftError
from .publish import PublishError
from .routes_common import draft_payload, error, ok, refuse_mirror

router = APIRouter(dependencies=[Depends(get_current_admin_user)])


def _preset_id(value: str) -> str:
    try:
        return paths.check_preset_id(value)
    except ValueError as failure:
        raise error(400, "invalid_request", str(failure))


def local_template(preset_id: str):
    template = core_bridge.find_preset(_preset_id(preset_id))
    if template is None:
        raise error(404, "not_found", f"no preset '{preset_id}' in the catalogue")
    refuse_mirror(template)
    if not catalog.is_local(template):
        raise error(409, "not_local", f"preset '{preset_id}' is not a local preset: duplicate it instead")
    return template


@router.get("/presets/{preset_id}/history")
async def list_history(preset_id: str):
    return ok(history.list_entries(paths.roots(), _preset_id(preset_id)))


@router.post("/presets/{preset_id}/history/{stamp}/restore", status_code=201)
async def restore_version(preset_id: str, stamp: str, current_user: User = Depends(get_current_admin_user)):
    roots = paths.roots()
    try:
        entry = history.entry_dir(roots, _preset_id(preset_id), stamp)
    except DraftError as failure:
        raise error(404, failure.code, failure.message)
    header = drafts.read_header(entry)
    declared = header.get("id")
    restored_id = declared if isinstance(declared, str) and paths.PRESET_ID_RE.match(declared) else preset_id
    meta = next((item for item in history.list_entries(roots, preset_id) if item["stamp"] == stamp), {})
    target_dir = meta.get("target_dir")
    template = core_bridge.find_preset(restored_id)
    if template is not None:
        refuse_mirror(template)
        if catalog.is_local(template):
            target_dir = catalog.target_dir(template)
    if not target_dir:
        raise error(409, "no_target", "this version does not say where the preset lived")
    try:
        draft = await asyncio.to_thread(
            drafts.create_edit,
            roots,
            source_dir=entry,
            preset_id=restored_id,
            name=str(header.get("name") or restored_id),
            target_dir=target_dir,
            created_by=current_user.id,
        )
    except DraftError as failure:
        raise error(409, failure.code, failure.message)
    draft.source = f"restore_of:{preset_id}@{stamp}"
    drafts.save(draft)
    errors, warnings = await core_bridge.lint_async(draft.dir)
    drafts.record_lint(draft, errors, warnings)
    return ok(draft_payload(draft))


@router.post("/presets/{preset_id}/edit", status_code=201)
async def edit_preset(preset_id: str, current_user: User = Depends(get_current_admin_user)):
    template = local_template(preset_id)
    try:
        draft = await asyncio.to_thread(
            drafts.create_edit,
            paths.roots(),
            source_dir=Path(template.path),
            preset_id=template.id,
            name=template.name,
            target_dir=catalog.target_dir(template),
            created_by=current_user.id,
        )
    except DraftError as failure:
        raise error(409, failure.code, failure.message)
    errors, warnings = await core_bridge.lint_async(draft.dir)
    drafts.record_lint(draft, errors, warnings)
    return ok(draft_payload(draft))


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str, current_user: User = Depends(get_current_admin_user)):
    template = local_template(preset_id)
    roots = paths.roots()
    preset_dir, target_dir = Path(template.path), catalog.target_dir(template)
    try:
        publish.check_deletable(roots, preset_dir=preset_dir, preset_id=template.id, target_dir=target_dir)
    except PublishError as failure:
        raise error(409, failure.code, failure.message)
    uninstalled = False
    if await asyncio.to_thread(core_bridge.is_installed, template.id):
        await asyncio.to_thread(core_bridge.uninstall_preset, template.id, current_user)
        uninstalled = True
    try:
        stamp = await asyncio.to_thread(
            publish.delete_local_preset,
            roots,
            preset_dir=preset_dir,
            preset_id=template.id,
            target_dir=target_dir,
            history_depth=settings.get_setting("history_depth"),
        )
    except PublishError as failure:
        raise error(409, failure.code, failure.message)
    await core_bridge.reload_presets_async()
    return ok({"preset_id": template.id, "archived": stamp, "uninstalled": uninstalled})
