from typing import Any, Dict


def origin(template: Any) -> Dict[str, Any]:
    return dict(getattr(template, "origin", None) or {})


def is_local(template: Any) -> bool:
    return origin(template).get("kind") == "local"


def target_dir(template: Any) -> str:
    return str(origin(template).get("path") or "")


def summary(template: Any) -> Dict[str, Any]:
    where = origin(template)
    return {
        "id": template.id,
        "name": template.name,
        "version": template.version,
        "kind": where.get("kind"),
        "plugin_id": where.get("plugin_id"),
        "path": where.get("path"),
        "engine": template.engine,
        "category": template.category,
        "modes": list(template.modes or {}),
    }
