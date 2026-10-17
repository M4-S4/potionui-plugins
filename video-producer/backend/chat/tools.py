import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from src.plugin_api.chat import BaseTool, ToolApprovalPreview, ToolContext, ToolResult

from .. import projects
from ..catalog import FL2VA
from ..core_bridge import generate_ulid
from ..director import profile_of, shot_frames
from . import rules
from .context import CONTEXT_KEY

MODE = "video-producer"
GROUP = "Video Producer"
VERSION_LABEL = "Assistant"
SOURCE_STAGE = "source"
DEFAULT_STRENGTH = 75
MAX_TEXT_CHARS = 4000
MAX_REWRITES = 100
MAX_SHOTS = 24
MIN_DURATION_S = 2
MAX_DURATION_S = 15
MAX_LABEL_CHARS = 34
PREVIEW_PROMPT_CHARS = 90

PROJECT_NOT_FOUND = "project_not_found"
SHOT_NOT_FOUND = "shot_not_found"
INVALID_ARGUMENTS = "invalid_arguments"
VERSION_CONFLICT = "version_conflict"

PAGE_FIXES = {
    "lum": "Match the shot's exposure to the previous shot.",
    "warm": "Match the shot's color temperature to the previous shot.",
    "identity": "Regenerate one of the two takes with the same look or identity reference.",
}

SHOT_ID_SCHEMA = {"type": "string", "description": "The id of the shot, as the context block lists it"}
TEXT_SCHEMA = {"type": "string", "description": "The complete new instruction, in the project's prompt language"}


class ToolFailure(Exception):
    """A tool call refused with a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def result(self) -> ToolResult:
        """The failure as the result the model reads: the code first, then the message."""
        return ToolResult(success=False, data="", error=f"{self.code}: {self.message}")


def _ok(payload: Mapping[str, Any], preview: Optional[ToolApprovalPreview] = None) -> ToolResult:
    return ToolResult(success=True, data=json.dumps(payload, ensure_ascii=False), preview=preview)


def _invalid(message: str) -> ToolFailure:
    return ToolFailure(INVALID_ARGUMENTS, message)


def _dicts(value: Any) -> List[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _ident(value: Any) -> Any:
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _seconds(value: Any) -> str:
    return f"{round(_number(value), 2):g}"


def _head(text: str, limit: int = PREVIEW_PROMPT_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def page_context(context: ToolContext) -> Dict[str, Any]:
    """What the page sent with the turn under the video_producer key, or an empty dict."""
    page = (context.session_metadata or {}).get(CONTEXT_KEY)
    return page if isinstance(page, dict) else {}


def load_project(context: ToolContext) -> Dict[str, Any]:
    """The project open on the page, read from the database, when the caller owns it or is an administrator."""
    project_id = page_context(context).get("projectId")
    if not isinstance(project_id, str) or not project_id:
        raise ToolFailure(PROJECT_NOT_FOUND, "No Video Producer project is open on the page.")
    project = projects.get_project(project_id)
    if project is None or (project["user_id"] != context.user_id and not context.is_admin):
        raise ToolFailure(PROJECT_NOT_FOUND, "The project does not exist.")
    return project


def shot_label(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> str:
    """The shot's label, else the name of its media, else its position."""
    if clip.get("label"):
        return str(clip["label"])
    asset = next((item for item in _dicts(doc.get("assets")) if clip.get("assetId") and item.get("id") == clip.get("assetId")), None)
    if asset is not None and asset.get("name"):
        return str(asset["name"])
    index = next((i for i, item in enumerate(_dicts(doc.get("clips")), 1) if item.get("id") == clip.get("id")), 0)
    return f"Shot {index}"


def find_clip(doc: Mapping[str, Any], shot_id: str) -> Dict[str, Any]:
    """The shot with this id; shot_not_found otherwise."""
    clip = next((item for item in _dicts(doc.get("clips")) if item.get("id") == shot_id), None)
    if clip is None:
        raise ToolFailure(SHOT_NOT_FOUND, f"The project has no shot with the id {shot_id!r}.")
    return clip


def linked_prompt(doc: Mapping[str, Any], shot_id: Any) -> Optional[Dict[str, Any]]:
    """The prompt attached to a shot, or None."""
    return next((prompt for prompt in _dicts(doc.get("prompts")) if prompt.get("shotId") == shot_id), None)


def _overlap(start: float, end: float, item: Mapping[str, Any]) -> float:
    begin = _number(item.get("start"))
    return min(end, begin + _number(item.get("dur"))) - max(start, begin)


def instruction_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> str:
    """The shot's own prompt text, else the sequence prompt that covers most of it, else an empty string."""
    prompt = linked_prompt(doc, clip.get("id"))
    if prompt is None:
        start = _number(clip.get("start"))
        end = start + _number(clip.get("dur"))
        covering = [
            (overlap, item)
            for item in _dicts(doc.get("prompts"))
            if not item.get("shotId") and (overlap := _overlap(start, end, item)) > 0
        ]
        prompt = max(covering, key=lambda pair: pair[0])[1] if covering else None
    return str(prompt.get("text") or "") if prompt is not None else ""


def write_prompt(doc: Dict[str, Any], clip: Mapping[str, Any], text: str) -> str:
    """Set the text of the shot's prompt, creating the prompt when the shot has none; returns its id."""
    prompt = linked_prompt(doc, clip["id"])
    if prompt is None:
        prompt = {
            "id": generate_ulid(),
            "shotId": clip["id"],
            "start": clip["start"],
            "dur": clip["dur"],
            "strength": DEFAULT_STRENGTH,
            "text": text,
        }
        doc.setdefault("prompts", []).append(prompt)
    else:
        prompt["text"] = text
    return prompt["id"]


def commit(context: ToolContext, change: Callable[[Dict[str, Any]], Any]) -> Tuple[Dict[str, Any], Any, int]:
    """Apply a change to the latest stored document and save it, reading and applying it again once on a version conflict."""
    for _ in range(2):
        project = load_project(context)
        outcome = change(project["doc"])
        try:
            saved = projects.save_project(project["id"], project["doc"], project["version"], label=VERSION_LABEL)
        except projects.VersionConflict:
            continue
        except projects.ProjectNotFound:
            raise ToolFailure(PROJECT_NOT_FOUND, "The project does not exist.") from None
        except projects.DocError as exc:
            raise ToolFailure(exc.code, str(exc)) from None
        return project, outcome, saved["version"]
    raise ToolFailure(VERSION_CONFLICT, "The project changed while the change was being saved. Reload the project and ask again.")


def _shot_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{name} must be the id of a shot from the context.")
    return value.strip()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{name} must be a non-empty string.")
    if len(value) > MAX_TEXT_CHARS:
        raise _invalid(f"{name} is longer than {MAX_TEXT_CHARS} characters.")
    return value


def write_arguments(arguments: Mapping[str, Any]) -> Tuple[str, str]:
    """The shot id and text of a vp_write_shot_prompt call."""
    return _shot_id(arguments.get("shot_id"), "shot_id"), _text(arguments.get("text"), "text")


def rewrite_arguments(arguments: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """The (shot id, text) pairs of a vp_fix_conflicts call, one per shot."""
    rewrites = arguments.get("rewrites")
    if not isinstance(rewrites, list) or not rewrites:
        raise _invalid("rewrites must be a non-empty list of {shot_id, text}.")
    if len(rewrites) > MAX_REWRITES:
        raise _invalid(f"rewrites lists more than {MAX_REWRITES} shots.")
    pairs: List[Tuple[str, str]] = []
    for index, item in enumerate(rewrites):
        if not isinstance(item, dict):
            raise _invalid(f"rewrites[{index}] must be an object with shot_id and text.")
        shot_id = _shot_id(item.get("shot_id"), f"rewrites[{index}].shot_id")
        if any(shot_id == seen for seen, _ in pairs):
            raise _invalid(f"rewrites[{index}] repeats the shot {shot_id!r}.")
        pairs.append((shot_id, _text(item.get("text"), f"rewrites[{index}].text")))
    return pairs


def _duration(value: Any, name: str) -> float:
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            value = None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not MIN_DURATION_S <= value <= MAX_DURATION_S:
        raise _invalid(f"{name} must be a number of seconds from {MIN_DURATION_S} to {MAX_DURATION_S}.")
    return value


def split_arguments(arguments: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The validated shots of a vp_split_synopsis call."""
    shots = arguments.get("shots")
    if not isinstance(shots, list) or not 1 <= len(shots) <= MAX_SHOTS:
        raise _invalid(f"shots must list 1 to {MAX_SHOTS} shots.")
    proposal: List[Dict[str, Any]] = []
    for index, item in enumerate(shots):
        if not isinstance(item, dict):
            raise _invalid(f"shots[{index}] must be an object with label, prompt and duration_s.")
        label = item.get("label")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > MAX_LABEL_CHARS:
            raise _invalid(f"shots[{index}].label must be 1 to {MAX_LABEL_CHARS} characters.")
        prompt = _text(item.get("prompt"), f"shots[{index}].prompt").strip()
        duration = _duration(item.get("duration_s"), f"shots[{index}].duration_s")
        proposal.append({"label": label.strip(), "prompt": prompt, "duration_s": duration})
    return proposal


def _issue(kind: str, text: str, fix: str, **extra: Any) -> Dict[str, Any]:
    return {"kind": kind, "text": text, "fix": fix, **extra}


def _shot_issues(doc: Mapping[str, Any], clip: Mapping[str, Any], label: str, text: str, fl2va: bool) -> List[Dict[str, Any]]:
    shot_id = clip.get("id")
    language = rules.language_of(doc.get("promptLanguage"))
    issues: List[Dict[str, Any]] = []
    if not text.strip():
        issues.append(_issue("no_instruction", f"“{label}” has no instruction.", "Write an instruction for the shot.", shot_id=shot_id))
    for conflict in rules.conflicts_for(doc.get("direction"), text, language):
        issues.append(
            _issue(
                "conflict",
                f"“{label}”: {conflict['text']}",
                "Rewrite the instruction so it agrees with the direction.",
                shot_id=shot_id,
                rule=conflict["id"],
            )
        )
    duration = _number(clip.get("dur"))
    if not MIN_DURATION_S <= duration <= MAX_DURATION_S:
        issues.append(
            _issue(
                "duration",
                f"“{label}” lasts {_seconds(duration)} s; a generated shot lasts {MIN_DURATION_S} to {MAX_DURATION_S} s.",
                f"Trim the shot or split it into shots of {MIN_DURATION_S} to {MAX_DURATION_S} s.",
                shot_id=shot_id,
            )
        )
    if fl2va and shot_frames(doc, shot_id)[0] is None:
        issues.append(
            _issue(
                "fl2va_no_frame",
                f"“{label}” has no first frame: FL2VA will generate it from its text alone.",
                "Add a first frame to the shot, or keep a text-only generation.",
                shot_id=shot_id,
            )
        )
    return issues


def check_continuity(doc: Mapping[str, Any], page: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The seams to check, in timeline order: the server's checks merged with the seams the page measured."""
    clips = _dicts(doc.get("clips"))
    language = rules.language_of(doc.get("promptLanguage"))
    fl2va = profile_of(doc) == FL2VA
    labels = {clip.get("id"): shot_label(doc, clip) for clip in clips}
    for index, shot in enumerate(_dicts(page.get("shots")), 1):
        if isinstance(shot.get("id"), str):
            labels.setdefault(shot["id"], str(shot.get("label") or f"Shot {index}"))
    order = {clip.get("id"): index for index, clip in enumerate(clips)}
    seams: Dict[Tuple[Any, Any], Dict[str, Any]] = {}

    def seam(from_id: Any, to_id: Any) -> List[Dict[str, Any]]:
        if (from_id, to_id) not in seams:
            seams[(from_id, to_id)] = {
                "from_shot_id": from_id,
                "to_shot_id": to_id,
                "from_label": labels.get(from_id, from_id),
                "to_label": labels.get(to_id, to_id),
                "issues": [],
            }
        return seams[(from_id, to_id)]["issues"]

    def around(index: int) -> List[Dict[str, Any]]:
        if index > 0:
            return seam(clips[index - 1].get("id"), clips[index].get("id"))
        return seam(clips[0].get("id"), clips[1 if len(clips) > 1 else 0].get("id"))

    instructions = [instruction_of(doc, clip) for clip in clips]
    for index, clip in enumerate(clips):
        if clip.get("stage") == SOURCE_STAGE:
            continue
        label = labels[clip.get("id")]
        found = _shot_issues(doc, clip, label, instructions[index], fl2va)
        if found:
            around(index).extend(found)
        previous = clips[index - 1] if index > 0 else None
        if previous is None or previous.get("stage") == SOURCE_STAGE:
            continue
        change = rules.camera_change(instructions[index - 1], instructions[index], language)
        if change is not None:
            before = labels[previous.get("id")]
            seam(previous.get("id"), clip.get("id")).append(
                _issue(
                    "camera_change",
                    f"The camera move changes from “{change[0]}” in “{before}” to “{change[1]}” in “{label}”.",
                    f"Keep one camera move across the cut, or motivate the change in “{label}”.",
                )
            )
    for measured in _dicts(page.get("seams")):
        from_id, to_id = _ident(measured.get("fromShotId")), _ident(measured.get("toShotId"))
        if from_id not in labels or to_id not in labels:
            continue
        for issue in _dicts(measured.get("issues")):
            if isinstance(issue.get("kind"), str) and isinstance(issue.get("text"), str):
                seam(from_id, to_id).append(_issue(issue["kind"], issue["text"], PAGE_FIXES.get(issue["kind"], "")))
    last = len(order)
    return sorted(
        (item for item in seams.values() if item["issues"]),
        key=lambda item: (order.get(item["to_shot_id"], last), order.get(item["from_shot_id"], last)),
    )


class _VideoProducerTool(BaseTool):
    modes = [MODE]

    @property
    def group(self) -> str:
        return GROUP


class WriteShotPromptTool(_VideoProducerTool):
    """Write or replace the instruction of one shot, after the user approves it."""

    icon = "text-cursor-input"

    @property
    def name(self) -> str:
        return "vp_write_shot_prompt"

    @property
    def label(self) -> str:
        return "Write shot prompt"

    @property
    def user_description(self) -> str:
        return "Writes or replaces the prompt of one shot of your Video Producer project."

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return (
            "Use it when the user asks to write, rewrite or improve the instruction of one shot: "
            "pass the shot_id from the context and the complete new text in the project's prompt language."
        )

    @property
    def description(self) -> str:
        return (
            "Write the instruction (prompt) of one shot of the Video Producer project open on the page: creates the "
            "shot's own prompt when it has none, otherwise replaces its text. The text is stored exactly as given. "
            "The user sees a before/after preview and nothing is saved until they approve it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"shot_id": SHOT_ID_SCHEMA, "text": TEXT_SCHEMA},
            "required": ["shot_id", "text"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            shot_id, text = write_arguments(kwargs)
            project = load_project(context)
            clip = find_clip(project["doc"], shot_id)
        except ToolFailure as failure:
            return failure.result()
        label = shot_label(project["doc"], clip)
        before = instruction_of(project["doc"], clip)
        preview = ToolApprovalPreview(
            action="Write shot prompt",
            target=label,
            kind="text_edit",
            summary=f"Write the prompt of “{label}”",
            text_blocks=[{"label": label, "text": text, **({"old_text": before} if before else {})}],
        )
        return _ok(
            {"status": "pending_approval", "project_id": project["id"], "shot_id": shot_id, "text": text},
            preview,
        )

    async def execute_confirmed(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            shot_id, text = write_arguments(kwargs)
            project, prompt_id, version = commit(context, lambda doc: write_prompt(doc, find_clip(doc, shot_id), text))
        except ToolFailure as failure:
            return failure.result()
        return _ok({"project_id": project["id"], "shot_id": shot_id, "prompt_id": prompt_id, "text": text, "version": version})


class FixConflictsTool(_VideoProducerTool):
    """Rewrite several shot instructions in one approved change."""

    icon = "sparkles"

    @property
    def name(self) -> str:
        return "vp_fix_conflicts"

    @property
    def label(self) -> str:
        return "Fix conflicts"

    @property
    def user_description(self) -> str:
        return "Rewrites the shot prompts that contradict the direction of your Video Producer project."

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return (
            "Use it when the context lists conflicts and the user wants them fixed: rewrite every "
            "conflicting instruction so it agrees with the direction while keeping its intent, all in one call."
        )

    @property
    def description(self) -> str:
        return (
            "Rewrite the instructions of several shots of the Video Producer project in one change, typically to "
            "resolve the conflicts with the global direction that the context lists. Each text is the complete new "
            "instruction, in the project's prompt language, stored exactly as given. The user sees a before/after "
            "preview for each shot and nothing is saved until they approve it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rewrites": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {"shot_id": SHOT_ID_SCHEMA, "text": TEXT_SCHEMA},
                        "required": ["shot_id", "text"],
                    },
                }
            },
            "required": ["rewrites"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            rewrites = rewrite_arguments(kwargs)
            project = load_project(context)
            clips = [(find_clip(project["doc"], shot_id), text) for shot_id, text in rewrites]
        except ToolFailure as failure:
            return failure.result()
        doc = project["doc"]
        blocks = []
        for clip, text in clips:
            before = instruction_of(doc, clip)
            blocks.append({"label": shot_label(doc, clip), "text": text, **({"old_text": before} if before else {})})
        count = f"{len(blocks)} shot{'s' if len(blocks) > 1 else ''}"
        preview = ToolApprovalPreview(
            action="Fix conflicts",
            target=count,
            kind="text_edit",
            summary=f"Rewrite the prompts of {count}",
            text_blocks=blocks,
        )
        return _ok(
            {
                "status": "pending_approval",
                "project_id": project["id"],
                "rewrites": [{"shot_id": shot_id, "text": text} for shot_id, text in rewrites],
            },
            preview,
        )

    async def execute_confirmed(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        def apply(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
            changes = []
            for shot_id, text in rewrites:
                clip = find_clip(doc, shot_id)
                before = instruction_of(doc, clip)
                changes.append({"shot_id": shot_id, "prompt_id": write_prompt(doc, clip, text), "before": before, "after": text})
            return changes

        try:
            rewrites = rewrite_arguments(kwargs)
            project, changes, version = commit(context, apply)
        except ToolFailure as failure:
            return failure.result()
        return _ok({"project_id": project["id"], "changes": changes, "version": version})


class SplitSynopsisTool(_VideoProducerTool):
    """Propose a cut of the synopsis into shots, shown on the page once approved."""

    icon = "list-plus"

    @property
    def name(self) -> str:
        return "vp_split_synopsis"

    @property
    def label(self) -> str:
        return "Split synopsis"

    @property
    def user_description(self) -> str:
        return "Proposes shots cut from the synopsis of your Video Producer project."

    @property
    def requires_approval(self) -> bool:
        return True

    @property
    def hint(self) -> str:
        return (
            "Use it when the user asks to cut the synopsis (or a story they describe) into shots: "
            f"1 to {MAX_SHOTS} shots, each with a label of at most {MAX_LABEL_CHARS} characters, a duration of "
            f"{MIN_DURATION_S} to {MAX_DURATION_S} seconds and an instruction in the project's prompt language."
        )

    @property
    def description(self) -> str:
        return (
            f"Propose a cut of the synopsis into 1 to {MAX_SHOTS} shots, in story order. Each shot has a label (at most "
            f"{MAX_LABEL_CHARS} characters), a duration in seconds ({MIN_DURATION_S} to {MAX_DURATION_S}) and an "
            "instruction in the project's prompt language. Nothing is written to the project: once the user approves, "
            "the page shows the proposal in its Story panel, where the user accepts or edits it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shots": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": MAX_SHOTS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "maxLength": MAX_LABEL_CHARS, "description": "Short shot name"},
                            "prompt": {"type": "string", "description": "The shot's instruction, in the project's prompt language"},
                            "duration_s": {"type": "number", "minimum": MIN_DURATION_S, "maximum": MAX_DURATION_S},
                        },
                        "required": ["label", "prompt", "duration_s"],
                    },
                }
            },
            "required": ["shots"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            proposal = split_arguments(kwargs)
            project = load_project(context)
        except ToolFailure as failure:
            return failure.result()
        rows, start = [], 0.0
        for shot in proposal:
            end = start + shot["duration_s"]
            rows.append({"range": f"{_seconds(start)}–{_seconds(end)} s", "text": f"{shot['label']}: {_head(shot['prompt'])}"})
            start = end
        count = f"{len(proposal)} shot{'s' if len(proposal) > 1 else ''}"
        preview = ToolApprovalPreview(
            action="Split synopsis",
            target=f"{count}, {_seconds(start)} s",
            kind="timeline",
            summary=f"Propose {count} ({_seconds(start)} s) from the synopsis",
            rows=rows,
        )
        return _ok({"status": "pending_approval", "project_id": project["id"], "proposal": proposal}, preview)

    async def execute_confirmed(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            proposal = split_arguments(kwargs)
            project = load_project(context)
        except ToolFailure as failure:
            return failure.result()
        return _ok({"project_id": project["id"], "proposal": proposal})


class CheckContinuityTool(_VideoProducerTool):
    """List the seams to check between consecutive shots. Read-only."""

    icon = "search"

    @property
    def name(self) -> str:
        return "vp_check_continuity"

    @property
    def label(self) -> str:
        return "Check continuity"

    @property
    def user_description(self) -> str:
        return "Checks the continuity between the shots of your Video Producer project."

    @property
    def hint(self) -> str:
        return (
            "Use it when the user asks about continuity, the cuts between shots or what to check "
            "before generating; it reads the project and needs no approval."
        )

    @property
    def description(self) -> str:
        return (
            "Check the continuity of the Video Producer project open on the page: shots without an instruction, FL2VA "
            "shots without a first frame, camera moves that change between consecutive shots, durations outside "
            f"{MIN_DURATION_S} to {MAX_DURATION_S} seconds and instructions that contradict the direction, merged with "
            "the color and identity seams the page measured. Read-only; the page lists the result for the user."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            project = load_project(context)
        except ToolFailure as failure:
            return failure.result()
        return _ok(
            {
                "project_id": project["id"],
                "seams": check_continuity(project["doc"], page_context(context)),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
