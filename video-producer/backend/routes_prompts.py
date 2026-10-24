from typing import Any, Dict, List, Mapping, NoReturn

from fastapi import APIRouter, Body, Depends

from . import access, bible, director, projects
from .core_bridge import User, get_current_active_user
from .projects import DocError
from .responses import fail, ok

router = APIRouter()

COMPOSED = (director.AI, director.RENDER_3D_AI)


def _invalid(message: str) -> NoReturn:
    fail(422, "invalid_request", message)


def _checked(body: Any) -> Dict[str, Any]:
    if not isinstance(body, dict):
        _invalid("The request body must be a JSON object.")
    shots = body.get("shots")
    if not isinstance(shots, list) or not all(isinstance(shot, str) and shot for shot in shots):
        _invalid("shots must be a list of shot ids.")
    preset_id = body.get("preset_id")
    if not isinstance(preset_id, str) or not preset_id:
        _invalid("preset_id must be a preset id.")
    model_id = body.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        _invalid("model_id must be a model id or null.")
    production = body.get("production", director.AI)
    if production not in COMPOSED:
        _invalid(f"production must be one of: {', '.join(COMPOSED)}.")
    if "doc" in body and not isinstance(body["doc"], dict):
        _invalid("doc must be a project document.")
    return body


def _document(body: Mapping[str, Any], stored: Dict[str, Any]) -> Dict[str, Any]:
    if "doc" not in body:
        return stored
    doc = projects.migrate(body["doc"])
    try:
        projects.validate_doc(doc)
    except DocError as exc:
        fail(422, exc.code, str(exc))
    return doc


def _own(warnings: List[Dict[str, Any]], shot_id: str) -> List[Dict[str, Any]]:
    return [item for item in warnings if (item.get("data") or {}).get("shot_id") == shot_id]


@router.post("/projects/{project_id}/prompts")
def compose_prompts(project_id: str, body: Any = Body(default=None), user: User = Depends(get_current_active_user)) -> Dict[str, Any]:
    """The prompt each shot would send to its engine, with the cast of the bible in the engine's format, the part made from its references and its cast (composed, sent, replaced or not, changed since replaced) and the composer's warnings, from the document in the body when given (unsaved edits) or else the stored one; nothing is started, stored or measured."""
    checked = _checked(body)
    project = access.project_for(user, project_id)
    doc = _document(checked, project["doc"])
    plans = director.build_plans(
        access.owner_of(user, project),
        doc,
        checked["shots"],
        checked["preset_id"],
        "draft",
        checked.get("model_id"),
        production=checked.get("production", director.AI),
        overrides=True,
    )
    return ok(
        {
            "prompts": [
                {
                    "shot_id": plan.shot_id,
                    "preset_id": plan.preset_id,
                    "profile": plan.profile,
                    "engine": bible.family(plan.preset_id, plan.cloud),
                    "prompt": plan.prompt_text,
                    "reference": plan.reference.summary() if plan.reference is not None else None,
                    "warnings": _own(plans.warnings, plan.shot_id),
                }
                for plan in plans.shots
            ],
            "blocks": list(plans.blocks),
        }
    )
