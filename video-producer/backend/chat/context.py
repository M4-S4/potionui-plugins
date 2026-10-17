from typing import Any, Dict, List, Mapping, Optional

from . import rules

CONTEXT_KEY = "video_producer"

MAX_BLOCK_CHARS = 8000
MAX_TAIL_CHARS = 2500
MAX_SYNOPSIS_CHARS = 800
MAX_FIELD_CHARS = 240
MAX_PROMPT_CHARS = 160
MAX_ISSUE_CHARS = 200
MAX_SHOTS = 40
MAX_ISSUES = 20
MAX_SEAM_LINES = 20

NOT_OPEN = "Video Producer: the page is not open on a project this turn, so there is no project context."

LANGUAGE_NAMES = {"en": "English", "fr": "French"}

DIRECTION_NAMES = (
    ("univers", "universe"),
    ("personnages", "characters"),
    ("photographie", "photography"),
    ("palette", "palette"),
    ("rythme", "rhythm"),
)


def _cap(text: Any, limit: int) -> str:
    text = " ".join(str(text if text is not None else "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _seconds(value: Any) -> str:
    try:
        return f"{round(float(value), 2):g}"
    except (TypeError, ValueError):
        return "?"


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _dicts(value: Any) -> List[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _ident(value: Any) -> Optional[str]:
    return (_cap(value, 40) or None) if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _label(shot: Mapping[str, Any], index: int) -> str:
    return _cap(shot.get("label") or f"Shot {index}", 60)


def _frames(shot: Mapping[str, Any]) -> str:
    first, last = bool(shot.get("hasFirstFrame")), bool(shot.get("hasLastFrame"))
    return "first+last" if first and last else "first" if first else "last" if last else "none"


def _shot_at(shots: List[Dict[str, Any]], time: float) -> Optional[Dict[str, Any]]:
    for shot in shots:
        start = _number(shot.get("start"))
        if start <= time < start + _number(shot.get("dur")):
            return shot
    return None


def _selection(page: Mapping[str, Any], shots: List[Dict[str, Any]], labels: Dict[Any, str]) -> Optional[str]:
    selection = page.get("selection")
    if not isinstance(selection, dict) or not selection.get("kind"):
        return None
    kind, item = _cap(selection.get("kind"), 20), _ident(selection.get("id"))
    if kind == "clip" and item in labels:
        return f'shot "{labels[item]}" [{item}]'
    if kind == "prompt":
        owner = next((shot for shot in shots if shot.get("promptId") == item), None)
        if owner is not None:
            return f'the prompt of shot "{labels[owner.get("id")]}" [{owner.get("id")}]'
    return f"{kind} {item}"


def _where(page: Mapping[str, Any], shots: List[Dict[str, Any]], labels: Dict[Any, str]) -> str:
    parts = []
    if page.get("workspace"):
        parts.append(f"Workspace: {_cap(page['workspace'], 80)}.")
    playhead = page.get("playhead")
    if isinstance(playhead, (int, float)) and not isinstance(playhead, bool):
        current = _shot_at(shots, _number(playhead))
        under = f' (shot "{labels[current.get("id")]}" [{current.get("id")}])' if current is not None else ""
        parts.append(f"Playhead: {_seconds(playhead)} s{under}.")
    selection = _selection(page, shots, labels)
    parts.append(f"Selection: {selection}." if selection else "Selection: none.")
    span = page.get("range")
    if isinstance(span, dict) and "in" in span and "out" in span:
        parts.append(f"Range: {_seconds(span['in'])}–{_seconds(span['out'])} s.")
    return " ".join(parts)


def _direction(page: Mapping[str, Any]) -> List[str]:
    direction = page.get("direction") if isinstance(page.get("direction"), dict) else {}
    lines = [f"Direction (generation profile {_cap(direction.get('mode'), 20) or 'FL2VA'}):"]
    filled = [(name, _cap(direction.get(key), MAX_FIELD_CHARS)) for key, name in DIRECTION_NAMES]
    lines += [f"  {name}: {text}" for name, text in filled if text]
    if len(lines) == 1:
        lines.append("  (empty)")
    return lines


def _shot_line(index: int, shot: Mapping[str, Any], labels: Dict[Any, str]) -> str:
    start = _number(shot.get("start"))
    end = start + _number(shot.get("dur"))
    take = f", take {_cap(shot['take'], 40)}" if shot.get("take") else ""
    prompt = _cap(shot.get("prompt"), MAX_PROMPT_CHARS)
    instruction = f'prompt: "{prompt}"' if prompt else "no prompt"
    return (
        f'  {index}. [{shot.get("id") or "?"}] "{labels[shot.get("id")]}" {_seconds(start)}–{_seconds(end)} s, '
        f"{_cap(shot.get('stage'), 20) or 'todo'}{take}, frames {_frames(shot)}; {instruction}"
    )


def _shots(shots: List[Dict[str, Any]], labels: Dict[Any, str], budget: int) -> List[str]:
    total = sum(_number(shot.get("dur")) for shot in shots)
    lines = [f"Shots ({len(shots)}, {_seconds(total)} s), in timeline order:"]
    if not shots:
        return lines + ["  (none yet)"]
    used, more = len(lines[0]) + 1, "  … {} more shots not shown."
    for index, shot in enumerate(shots[:MAX_SHOTS], 1):
        line = _shot_line(index, shot, labels)
        reserve = len(more.format(len(shots))) + 1 if index < len(shots) else 0
        if used + len(line) + 1 + reserve > budget:
            break
        lines.append(line)
        used += len(line) + 1
    shown = len(lines) - 1
    if shown < len(shots):
        lines.append(more.format(len(shots) - shown))
    return lines


def _issues(page: Mapping[str, Any], labels: Dict[Any, str]) -> List[str]:
    issues = _dicts(page.get("issues"))
    if not issues:
        return ["Conflicts flagged by the page: none."]
    lines = [f"Conflicts flagged by the page ({len(issues)}):"]
    for issue in issues[:MAX_ISSUES]:
        shot_id = _ident(issue.get("shotId"))
        where = f'"{labels[shot_id]}" [{shot_id}]' if shot_id in labels else "sequence prompt"
        lines.append(f"  - {where} {_cap(issue.get('level'), 20) or 'conflict'}: {_cap(issue.get('text'), MAX_ISSUE_CHARS)}")
    if len(issues) > MAX_ISSUES:
        lines.append(f"  … {len(issues) - MAX_ISSUES} more.")
    return lines


def _seams(page: Mapping[str, Any], labels: Dict[Any, str]) -> List[str]:
    seams = _dicts(page.get("seams"))
    found = [(seam, issue) for seam in seams for issue in _dicts(seam.get("issues"))]
    if not found:
        measured = any(seam.get("measured") for seam in seams)
        return ["Continuity measured by the page: nothing flagged."] if measured else []
    lines = [f"Continuity measured by the page ({len(found)}):"]
    for seam, issue in found[:MAX_SEAM_LINES]:
        from_id, to_id = _ident(seam.get("fromShotId")), _ident(seam.get("toShotId"))
        before, after = labels.get(from_id, from_id or "?"), labels.get(to_id, to_id or "?")
        lines.append(f'  - "{before}" → "{after}" {_cap(issue.get("kind"), 20)}: {_cap(issue.get("text"), MAX_ISSUE_CHARS)}')
    if len(found) > MAX_SEAM_LINES:
        lines.append(f"  … {len(found) - MAX_SEAM_LINES} more.")
    return lines


def _production(page: Mapping[str, Any]) -> List[str]:
    production = page.get("production")
    if not isinstance(production, dict):
        return []
    field = lambda key, limit, default: _cap(production.get(key), limit) or default
    return [
        f"Production: {field('state', 20, 'ready')}, {field('progress', 10, '0')}% "
        f"({field('mode', 20, '?')} mode, {field('quality', 20, '?')} quality, "
        f"target {field('target', 20, '?')}, {field('queue', 10, '0')} queued)."
    ]


def build_context(context_metadata: Optional[Dict[str, Any]], session: Any, user_id: str) -> str:
    """The Video Producer mode's system block for this turn, built from the page's context."""
    page = (context_metadata or {}).get(CONTEXT_KEY)
    if not isinstance(page, dict) or not page.get("projectId"):
        return NOT_OPEN
    shots = [dict(shot, id=_ident(shot.get("id"))) for shot in _dicts(page.get("shots"))]
    labels = {shot.get("id"): _label(shot, index) for index, shot in enumerate(shots, 1)}
    language = rules.language_of(page.get("promptLanguage"))
    version = page.get("projectVersion")
    head = [
        f'VIDEO PRODUCER: project "{_cap(page.get("name") or "Untitled", 80)}" '
        f"[{_cap(page['projectId'], 40)}], saved version {_cap(version, 20) if version is not None else 'none'}.",
        f"Prompt language: {language}. Write every shot instruction in {LANGUAGE_NAMES[language]}; "
        "never translate what the user wrote.",
        _where(page, shots, labels),
        f"Synopsis: {_cap(page.get('synopsis'), MAX_SYNOPSIS_CHARS) or '(empty)'}",
        *_direction(page),
    ]
    tail = [*_issues(page, labels), *_seams(page, labels), *_production(page)]
    budget = MAX_BLOCK_CHARS - len("\n".join(head)) - min(len("\n".join(tail)), MAX_TAIL_CHARS) - 2
    text = "\n".join([*head, *_shots(shots, labels, budget), *tail])
    return text if len(text) <= MAX_BLOCK_CHARS else text[: MAX_BLOCK_CHARS - 1].rstrip() + "…"
