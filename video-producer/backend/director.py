import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import catalog, core_bridge, models, presets, settings
from .catalog import FL2VA, PROFILES, REF2VA, REFS_MODE
from .core_bridge import CLOUD_ENGINE, DirectorBindingError, MediaRefError, User

logger = logging.getLogger("plugins.video-producer")

DIRECTION_FIELDS = ("univers", "personnages", "photographie", "palette", "rythme")

FIRST_ROLES = ("first", "début", "debut")
LAST_ROLES = ("last", "fin")

TXT2VIDEO = "txt2video"
IMG2VIDEO = "img2video"

FIRST_FRAME = "first_frame"
LAST_FRAME = "last_frame"

SEGMENT_ID = "seg-1"

DEFAULT_DURATION = 5.0
DEFAULT_ASPECT = 16 / 9
ASPECT_TOLERANCE = 0.03

REFERENCE_LIMITS = {"image": 9, "video": 3, "audio": 3}

SEEDVR2_MODE = "video_upscale"
H3_UPSCALE_MODE = "upscale"

UPSCALE_SHORT_SIDES = {"hd720": 720, "fhd1080": 1080, "qhd1440": 1440, "uhd2160": 2160}
H3_TARGET_SIZES = {"hd720": "hd", "fhd1080": "hd", "qhd1440": "2k", "uhd2160": "2k"}
H3_TARGET_BACK = {"hd": "fhd1080", "2k": "qhd1440"}


class DirectorError(Exception):
    """A shot the plugin cannot turn into a generation request."""

    def __init__(self, code: str, message: str, **data: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def note(self) -> Dict[str, Any]:
        """The error as a block of the estimate."""
        return note(self.code, self.message, **self.data)


def note(code: str, message: str, **data: Any) -> Dict[str, Any]:
    """A block or warning: a stable code, an English message and, when given, its data."""
    return {"code": code, "message": message, **({"data": data} if data else {})}


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    engine: Optional[str]
    variables: Dict[str, Any]
    modes: Tuple[str, ...]

    @property
    def cloud(self) -> bool:
        return self.engine == CLOUD_ENGINE

    @property
    def main_mode(self) -> Optional[str]:
        return catalog.main_mode(self.variables, list(self.modes))

    @property
    def fps(self) -> float:
        return catalog.preset_fps(self.variables)

    @property
    def limits(self) -> Dict[str, Any]:
        return catalog.preset_limits(self.variables)

    @property
    def profiles(self) -> List[str]:
        return catalog.profiles(self.id, self.variables, list(self.modes))


@dataclass
class ShotPlan:
    shot_id: str
    profile: Optional[str]
    director_mode: Optional[str]
    preset_mode: str
    seconds: float
    resolution: Optional[str]
    fps: Optional[float]
    prompt_text: str
    request: Dict[str, Any]
    model_id: Optional[str] = None
    cloud_task: Optional[str] = None
    cloud_params: Dict[str, Any] = field(default_factory=dict)
    missing_models: List[str] = field(default_factory=list)
    seeded: bool = True

    def summary(self) -> Dict[str, Any]:
        """The shot as the estimate reports it."""
        return {
            "shot_id": self.shot_id,
            "director_mode": self.director_mode,
            "seconds": self.seconds,
            "resolution": self.resolution,
            "fps": self.fps,
        }

    def request_for(self, take_id: Optional[str] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        """The generation request of one take: its idempotency key and, for a seeded plan, its seed."""
        request = copy.deepcopy(self.request)
        if take_id is not None:
            request["idempotency_key"] = f"vp:{take_id}"
        if self.seeded and seed is not None:
            form = request["form_data"]
            form["seed"] = seed
            document = form.get("video_director")
            if isinstance(document, dict):
                document["settings"]["seed"] = seed
        return request


@dataclass
class Plans:
    preset: Optional[Preset]
    model: Optional[Dict[str, Any]]
    quality: str
    profile: str
    shots: List[ShotPlan] = field(default_factory=list)
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


def find_preset(user: User, preset_id: str, video: bool = True) -> Optional[Preset]:
    """A preset the user may run, a Video Director one unless video is False; None otherwise."""
    if not isinstance(preset_id, str) or not preset_id:
        return None
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s", getattr(user, "id", None), exc_info=True)
        return None
    for description in descriptions:
        if description.id == preset_id and (not video or catalog.is_video_preset(description)):
            return Preset(
                id=description.id,
                name=description.name,
                engine=description.engine,
                variables=dict(description.vars or {}),
                modes=tuple(description.modes or {}),
            )
    return None


def profile_of(doc: Mapping[str, Any]) -> str:
    """The profile the project's direction asks for; FL2VA when it names none the plugin knows."""
    mode = (doc.get("direction") or {}).get("mode")
    return mode if mode in PROFILES else FL2VA


def clip_of(doc: Mapping[str, Any], shot_id: str) -> Optional[Dict[str, Any]]:
    """The clip with this id, or None."""
    return next((clip for clip in doc.get("clips") or [] if clip.get("id") == shot_id), None)


def _overlap(start: float, end: float, item: Mapping[str, Any]) -> float:
    begin = float(item.get("start") or 0)
    return min(end, begin + float(item.get("dur") or 0)) - max(start, begin)


def shot_prompt(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> str:
    """The shot's own instruction, else the global one over its interval, then the filled direction fields, one per line."""
    prompts = doc.get("prompts") or []
    local = next((prompt for prompt in prompts if prompt.get("shotId") == clip.get("id")), None)
    if local is None:
        start = float(clip.get("start") or 0)
        end = start + float(clip.get("dur") or 0)
        covering = [
            (overlap, prompt)
            for prompt in prompts
            if not prompt.get("shotId") and (overlap := _overlap(start, end, prompt)) > 0
        ]
        local = max(covering, key=lambda pair: pair[0])[1] if covering else None
    direction = doc.get("direction") or {}
    lines = [str(local.get("text") or "").strip()] if local is not None else []
    lines += [str(direction.get(name) or "").strip() for name in DIRECTION_FIELDS]
    return "\n".join(line for line in lines if line)


def aspect_of(doc: Mapping[str, Any]) -> float:
    """The project's aspect ratio, width over height."""
    aspect = str(doc.get("aspect") or "")
    for separator in (":", "/", "x"):
        if aspect.count(separator) == 1:
            left, right = aspect.split(separator)
            try:
                width, height = float(left), float(right)
            except ValueError:
                break
            if width > 0 and height > 0:
                return width / height
    size = models.parse_size(doc.get("resolution"))
    return size[0] / size[1] if size else DEFAULT_ASPECT


def _matching(options: Sequence[Mapping[str, str]], aspect: float) -> List[Tuple[str, int, int]]:
    sizes = [(option["value"], *models.parse_size(option["value"])) for option in options]
    if not sizes:
        return []
    distance = {value: abs(math.log(width / height) - math.log(aspect)) for value, width, height in sizes}
    closest = min(distance.values())
    return [size for size in sizes if distance[size[0]] <= closest + ASPECT_TOLERANCE]


def draft_resolution(options: Sequence[Mapping[str, str]], setting: str, aspect: float) -> Optional[str]:
    """The admin's draft resolution, turned to the project's orientation, when offered; else the closest offered size in area."""
    size = models.parse_size(setting)
    if size is None:
        return None
    width, height = size if (size[0] >= size[1]) == (aspect >= 1) else (size[1], size[0])
    wanted = f"{width}x{height}"
    candidates = _matching(options, aspect)
    if not candidates:
        return wanted
    if any(value == wanted for value, _, _ in candidates):
        return wanted
    area = width * height
    return min(candidates, key=lambda option: (abs(option[1] * option[2] - area), option[1] * option[2]))[0]


def final_resolution(options: Sequence[Mapping[str, str]], aspect: float) -> Optional[str]:
    """The largest offered size in the project's aspect ratio."""
    candidates = _matching(options, aspect)
    return max(candidates, key=lambda option: option[1] * option[2])[0] if candidates else None


def _clamped(wanted: float, maximum: Any, clip_id: str, warnings: List[Dict[str, Any]]) -> float:
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and 0 < maximum < wanted:
        warnings.append(
            note("duration_clamped", f"The shot is longer than the {maximum:g} s the preset allows.", shot_id=clip_id, max=maximum)
        )
        return float(maximum)
    return wanted


def _wanted_seconds(clip: Mapping[str, Any], preset: Preset) -> float:
    duration = clip.get("dur")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        return float(duration)
    default = preset.limits.get("default_duration")
    return float(default) if isinstance(default, (int, float)) and default > 0 else DEFAULT_DURATION


def media_ref(origin: Any) -> Optional[Dict[str, Any]]:
    """The core media reference of an asset origin, or None."""
    if not isinstance(origin, Mapping):
        return None
    if origin.get("kind") == "history" and origin.get("generationId") and origin.get("fileId") is not None:
        return {"kind": "history", "generation_id": str(origin["generationId"]), "file_id": str(origin["fileId"])}
    if origin.get("kind") == "library" and origin.get("itemId"):
        return {"kind": "library", "item_id": str(origin["itemId"])}
    return None


def _asset(doc: Mapping[str, Any], asset_id: Any) -> Optional[Dict[str, Any]]:
    return next((asset for asset in doc.get("assets") or [] if asset_id and asset.get("id") == asset_id), None)


def _category(media_type: Any) -> str:
    return str(media_type or "").split("/", 1)[0].strip().lower()


def _resolve(user: User, asset: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    ref = media_ref(asset.get("origin")) if asset else None
    if ref is None:
        return None
    try:
        resolved = core_bridge.resolve_media(user, ref)
    except MediaRefError:
        return None
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not resolve media %s", ref, exc_info=True)
        return None
    return {**resolved, "media_type": _category(resolved.get("media_type")) or asset.get("kind")}


def shot_frames(doc: Mapping[str, Any], shot_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """The first and last frames linked to a shot."""
    frames = [frame for frame in doc.get("frames") or [] if frame.get("shotId") == shot_id and frame.get("assetId")]
    firsts = [frame for frame in frames if str(frame.get("role") or "").strip().lower() in FIRST_ROLES]
    lasts = [frame for frame in frames if str(frame.get("role") or "").strip().lower() in LAST_ROLES]
    first = min(firsts, key=lambda frame: float(frame.get("time") or 0)) if firsts else None
    last = max(lasts, key=lambda frame: float(frame.get("time") or 0)) if lasts else None
    return first, last


def _frame_media(user: User, doc: Mapping[str, Any], frame: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if frame is None:
        return None
    resolved = _resolve(user, _asset(doc, frame.get("assetId")))
    if resolved is None or resolved["media_type"] != "image":
        return None
    return {"value": resolved["value"], "media_type": "image"}


def bind_frames(
    user: User, doc: Mapping[str, Any], shot_id: str, request: Dict[str, Any], last_allowed: bool = True
) -> Tuple[Dict[str, Any], str]:
    """The request with the shot's first and last frames bound, and the composition mode that results."""
    first, last = shot_frames(doc, shot_id)
    first_media = _frame_media(user, doc, first)
    if first_media is None:
        return request, "t2v"
    try:
        request = core_bridge.bind_director_media(request, "first", first_media, promote=True)
    except DirectorBindingError:
        logger.warning("[VIDEO-PRODUCER] Could not bind the first frame of shot %s", shot_id, exc_info=True)
        return request, "t2v"
    last_media = _frame_media(user, doc, last) if last_allowed else None
    if last_media is None:
        return request, "i2v"
    try:
        return core_bridge.bind_director_media(request, "last", last_media, promote=True), "flf"
    except DirectorBindingError:
        logger.warning("[VIDEO-PRODUCER] Could not bind the last frame of shot %s", shot_id, exc_info=True)
        return request, "i2v"


def shot_references(user: User, doc: Mapping[str, Any], shot_id: str) -> List[str]:
    """The media values of the shot's own references, then the global ones, within the per-kind limits."""
    scoped, shared = [], []
    for reference in doc.get("references") or []:
        scope = reference.get("scope")
        if isinstance(scope, Mapping) and scope.get("type") == "shot":
            if scope.get("shotId") == shot_id:
                scoped.append(reference)
        else:
            shared.append(reference)
    values: List[str] = []
    counts = {kind: 0 for kind in REFERENCE_LIMITS}
    for reference in [*scoped, *shared]:
        resolved = _resolve(user, _asset(doc, reference.get("assetId")))
        if resolved is None or resolved["value"] in values:
            continue
        kind = resolved["media_type"]
        if kind in counts and counts[kind] < REFERENCE_LIMITS[kind]:
            counts[kind] += 1
            values.append(resolved["value"])
    return values


def _document(prompt: str, fps: float, seconds: float, resolution: Optional[str]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "t2v",
        "settings": {"fps": fps, "duration": seconds, "resolution": resolution or "", "seed": -1},
        "segments": [{"id": SEGMENT_ID, "prompt": prompt, "negative_prompt": ""}],
        "media": [],
    }


def _request(preset_id: str, mode: str, prompt: str, form: Dict[str, Any]) -> Dict[str, Any]:
    return {"preset_id": preset_id, "mode": mode, "prompts": [{"positive": prompt, "negative": ""}], "form_data": form}


@dataclass
class _Context:
    user: User
    doc: Mapping[str, Any]
    preset: Preset
    quality: str
    profile: str
    model: Optional[Dict[str, Any]]
    draft_setting: str
    fields: Dict[str, models.Fields] = field(default_factory=dict)

    def mode_fields(self, mode: str) -> models.Fields:
        if mode not in self.fields:
            self.fields[mode] = models.form_fields(self.preset.id, mode)
        return self.fields[mode]


def _native_plan(context: _Context, clip: Mapping[str, Any], warnings: List[Dict[str, Any]]) -> ShotPlan:
    preset, doc, shot_id = context.preset, context.doc, clip["id"]
    mode = REFS_MODE if context.profile == REF2VA else preset.main_mode
    if mode is None or mode not in preset.modes:
        raise DirectorError("no_preset", "The preset has no mode the Video Director can run.")
    fields = context.mode_fields(mode)
    options = models.resolution_options(fields)
    aspect = aspect_of(doc)
    resolution = (
        final_resolution(options, aspect)
        if context.quality == "final"
        else draft_resolution(options, context.draft_setting, aspect)
    ) or (fields.get("resolution") or {}).get("default") or context.draft_setting
    seconds = _clamped(_wanted_seconds(clip, preset), preset.limits.get("max_duration"), shot_id, warnings)
    fps = preset.fps
    prompt = shot_prompt(doc, clip)
    form: Dict[str, Any] = {"seed": -1, "video_director": _document(prompt, fps, seconds, resolution)}
    if "resolution" in fields:
        form["resolution"] = resolution
    if "fps" in fields:
        form["fps"] = fps
    if "quantity" in fields:
        form["quantity"] = 1
    request = _request(preset.id, mode, prompt, form)
    if context.profile == REF2VA:
        references = shot_references(context.user, doc, shot_id)
        if not references:
            raise DirectorError("no_references", "Ref2VA needs at least one reference for this shot.", shot_id=shot_id)
        request["form_data"]["references"] = references
        director_mode = REFS_MODE
    else:
        request, director_mode = bind_frames(context.user, doc, shot_id, request)
        if director_mode == "t2v" and context.profile == FL2VA:
            warnings.append(note("fl2va_no_frame", "The shot has no first frame: it is generated from its text alone.", shot_id=shot_id))
    resolved = models.resolve_models(preset.id, mode, director_mode, fields)
    request["form_data"].update(resolved.values)
    return ShotPlan(
        shot_id=shot_id,
        profile=context.profile,
        director_mode=director_mode,
        preset_mode=mode,
        seconds=seconds,
        resolution=resolution,
        fps=fps,
        prompt_text=prompt,
        request=request,
        missing_models=list(resolved.missing),
    )


def _applies(item: Mapping[str, Any], task: str) -> bool:
    tasks = item.get("tasks") or []
    return not tasks or task in tasks


def _param(model: Mapping[str, Any], name: str, task: str) -> Optional[Dict[str, Any]]:
    return next((param for param in model.get("params") or [] if param.get("name") == name and _applies(param, task)), None)


def _has_input(model: Mapping[str, Any], role: str, task: str) -> bool:
    return any(item.get("role") == role and _applies(item, task) for item in model.get("inputs") or [])


def _tier(value: str) -> Optional[float]:
    text = value.strip().lower()
    size = models.parse_size(text)
    if size:
        return float(min(size))
    for suffix, factor in (("p", 1.0), ("k", 1000.0)):
        if text.endswith(suffix) and text[:-1].replace(".", "", 1).isdigit():
            return float(text[:-1]) * factor
    return float(text) if text.replace(".", "", 1).isdigit() else None


def cloud_resolution(param: Optional[Mapping[str, Any]], quality: str) -> Optional[str]:
    """The model's resolution for a draft (its default, else the smallest) or a final take (the largest)."""
    if param is None:
        return None
    values = [str(value) for value in param.get("values") or []]
    default = param.get("default")
    if not values:
        return None if default is None else str(default)
    ranked = sorted((tier, index, value) for index, value in enumerate(values) if (tier := _tier(value)) is not None)
    if quality == "final":
        return ranked[-1][2] if ranked else values[-1]
    if default is not None and str(default) in values:
        return str(default)
    return ranked[0][2] if ranked else values[0]


def cloud_duration(param: Optional[Mapping[str, Any]], wanted: float) -> Tuple[float, Optional[float]]:
    """The duration closest to the wanted one that the model accepts, and the longest it accepts."""
    if param is None:
        return wanted, None
    if param.get("kind") == "enum":
        allowed = []
        for value in param.get("values") or []:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                allowed.append(number)
        if not allowed:
            return wanted, None
        return min(allowed, key=lambda number: (abs(number - wanted), -number)), max(allowed)
    low, high = param.get("minimum"), param.get("maximum")
    value = wanted
    if isinstance(high, (int, float)):
        value = min(value, float(high))
    if isinstance(low, (int, float)):
        value = max(value, float(low))
        step = param.get("step")
        if isinstance(step, (int, float)) and step > 0:
            value = float(low) + round((value - float(low)) / float(step)) * float(step)
            if isinstance(high, (int, float)):
                value = min(value, float(high))
    return round(value, 3), float(high) if isinstance(high, (int, float)) else None


def _cloud_plan(context: _Context, clip: Mapping[str, Any], warnings: List[Dict[str, Any]]) -> ShotPlan:
    preset, doc, model, shot_id = context.preset, context.doc, context.model or {}, clip["id"]
    tasks = model.get("tasks") or []
    first, last = shot_frames(doc, shot_id)
    image_task = IMG2VIDEO in tasks and IMG2VIDEO in preset.modes and _has_input(model, FIRST_FRAME, IMG2VIDEO)
    first_media = _frame_media(context.user, doc, first) if image_task else None
    task = IMG2VIDEO if first_media is not None else TXT2VIDEO
    if task == TXT2VIDEO and (TXT2VIDEO not in tasks or TXT2VIDEO not in preset.modes):
        raise DirectorError("no_model", "The model needs a first frame for this shot.", shot_id=shot_id)
    fields = context.mode_fields(task)
    resolution = cloud_resolution(_param(model, "resolution", task), context.quality)
    aspect_param = _param(model, "aspect_ratio", task)
    aspect_values = [str(value) for value in (aspect_param or {}).get("values") or []]
    aspect = doc.get("aspect") if doc.get("aspect") in aspect_values else (aspect_param or {}).get("default")
    duration_param = _param(model, "duration_s", task)
    wanted = _clamped(_wanted_seconds(clip, preset), preset.limits.get("max_duration"), shot_id, warnings)
    seconds, longest = cloud_duration(duration_param, wanted)
    if longest is not None and wanted > longest and not any(
        item["code"] == "duration_clamped" and (item.get("data") or {}).get("shot_id") == shot_id for item in warnings
    ):
        warnings.append(
            note("duration_clamped", f"The shot is longer than the {longest:g} s the model allows.", shot_id=shot_id, max=longest)
        )
    fps = preset.fps
    prompt = shot_prompt(doc, clip)
    form: Dict[str, Any] = {
        "seed": -1,
        "model": f"{models.MODEL_REF}{model['id']}",
        "video_director": _document(prompt, fps, seconds, resolution),
    }
    if "resolution" in fields and resolution is not None:
        form["resolution"] = resolution
    if "aspect_ratio" in fields and aspect is not None:
        form["aspect_ratio"] = str(aspect)
    request = _request(preset.id, task, prompt, form)
    director_mode = "t2v"
    if first_media is not None:
        request, director_mode = bind_frames(
            context.user, doc, shot_id, request, last_allowed=_has_input(model, LAST_FRAME, IMG2VIDEO)
        )
    if director_mode == "t2v" and context.profile == FL2VA:
        warnings.append(note("fl2va_no_frame", "The shot has no first frame: it is generated from its text alone.", shot_id=shot_id))
    params = {"duration_s": seconds, "resolution": resolution, "aspect_ratio": aspect}
    return ShotPlan(
        shot_id=shot_id,
        profile=context.profile,
        director_mode=director_mode,
        preset_mode=task,
        seconds=seconds,
        resolution=resolution,
        fps=fps,
        prompt_text=prompt,
        request=request,
        model_id=model["id"],
        cloud_task=task,
        cloud_params={key: value for key, value in params.items() if value is not None},
    )


def _cloud_model(model_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not model_id:
        return None
    try:
        return core_bridge.cloud_model(model_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read cloud model %s", model_id, exc_info=True)
        return None


def build_plans(
    user: User,
    doc: Mapping[str, Any],
    shot_ids: Sequence[str],
    preset_id: str,
    quality: str,
    model_id: Optional[str] = None,
    profile: Optional[str] = None,
) -> Plans:
    """The generation request of each shot, with what blocks the run and what the user should know."""
    profile = profile if profile in PROFILES else profile_of(doc)
    preset = find_preset(user, preset_id)
    plans = Plans(preset=preset, model=None, quality=quality, profile=profile)
    if preset is None:
        plans.blocks.append(note("no_preset", "The preset is not available to you.", preset_id=preset_id))
        return plans
    if profile not in preset.profiles:
        plans.blocks.append(
            note("profile_unsupported", f"{preset.name} cannot run the {profile} profile.", profile=profile, preset_id=preset.id)
        )
        return plans
    if preset.cloud:
        plans.model = _cloud_model(model_id)
        if plans.model is None:
            plans.blocks.append(note("no_model", "Choose a video model the cloud backend has turned on.", model_id=model_id))
            return plans
    clips = [clip for clip in (clip_of(doc, shot_id) for shot_id in dict.fromkeys(shot_ids)) if clip is not None]
    if not clips:
        plans.blocks.append(note("no_shots", "Select at least one shot of the project."))
        return plans
    context = _Context(
        user=user,
        doc=doc,
        preset=preset,
        quality=quality,
        profile=profile,
        model=plans.model,
        draft_setting=str(settings.get_setting("draft_resolution")),
    )
    missing: List[str] = []
    for clip in clips:
        try:
            plan = (_cloud_plan if preset.cloud else _native_plan)(context, clip, plans.warnings)
        except DirectorError as exc:
            if exc.note() not in plans.blocks:
                plans.blocks.append(exc.note())
            continue
        plans.shots.append(plan)
        missing.extend(name for name in plan.missing_models if name not in missing)
    if missing:
        plans.blocks.append(
            note("missing_models", f"Install a recommended file for: {', '.join(missing)}.", fields=missing)
        )
    return plans


def source_video(user: User, take: Mapping[str, Any]) -> Dict[str, Any]:
    """The resolved video file of a finished take; DirectorError when it is gone."""
    generation_id = take.get("generation_id")
    try:
        files = core_bridge.list_generation_files(user, generation_id) if generation_id else []
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the files of generation %s", generation_id, exc_info=True)
        files = []
    chosen = next((item for item in files if str(item.get("id")) == str(take.get("file_id"))), None)
    if chosen is None:
        chosen = next((item for item in files if _category(item.get("file_type")) == "video"), None)
    if chosen is None:
        raise DirectorError("source_unavailable", "The video of the source take is no longer available.")
    try:
        return core_bridge.resolve_media(
            user, {"kind": "history", "generation_id": str(generation_id), "file_id": str(chosen["id"])}
        )
    except MediaRefError:
        raise DirectorError("source_unavailable", "The video of the source take is no longer available.") from None


def upscaled_size(width: Any, height: Any, target: str) -> Optional[str]:
    """The size an upscale to a target gives a video of this size: its short side pinned to the target's."""
    short = UPSCALE_SHORT_SIDES.get(target)
    if not short or not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None
    scale = short / min(width, height)
    return f"{2 * round(width * scale / 2)}x{2 * round(height * scale / 2)}"


def h3_target_size(fields: models.Fields, target: str) -> str:
    """The MiniMax-H3 target size closest to an upscale target that the mode offers."""
    wanted = H3_TARGET_SIZES.get(target, "hd")
    spec = fields.get("target_size") or {}
    values = [option["value"] for option in spec.get("options") or []]
    if not values or wanted in values:
        return wanted
    default = spec.get("default")
    return str(default) if default in values else values[0]


def upscale_target(take: Mapping[str, Any]) -> str:
    """The upscale target an upscale take was asked for."""
    form = (take.get("request") or {}).get("form_data") or {}
    target = form.get("resolution_target")
    if target in UPSCALE_SHORT_SIDES:
        return str(target)
    return H3_TARGET_BACK.get(str(form.get("target_size")), "fhd1080")


def build_upscale(user: User, source: Mapping[str, Any], target: str) -> ShotPlan:
    """The final take of a finished take upscaled: a MiniMax-H3 preset's own Upscale mode for its takes, SeedVR2 otherwise."""
    source_preset = source.get("preset_id")
    own = find_preset(user, str(source_preset), video=False) if source_preset in presets.MINIMAX_H3_PRESETS else None
    h3 = own is not None and H3_UPSCALE_MODE in own.modes
    preset_id = own.id if h3 else presets.SEEDVR2
    mode = H3_UPSCALE_MODE if h3 else SEEDVR2_MODE
    preset = own if h3 else find_preset(user, presets.SEEDVR2, video=False)
    if preset is None or mode not in preset.modes:
        if own is not None:
            raise DirectorError(
                "upscale_unsupported",
                f"{own.name} has no Upscale mode: install SeedVR2 for final takes, or render the take again at full resolution.",
                preset_id=own.id,
            )
        raise DirectorError("no_preset", "The upscaler preset is not available to you.", preset_id=preset_id)
    fields = models.form_fields(preset_id, mode)
    media = source_video(user, source)
    form: Dict[str, Any] = {"input_video": media["value"], "seed": -1}
    if media.get("origin"):
        form["input_video__origin"] = media["origin"]
    if h3:
        form["target_size"] = h3_target_size(fields, target)
        if "quantity" in fields:
            form["quantity"] = 1
    else:
        form["restoration_intent"] = "faithful"
        form["resolution_target"] = target
    resolved = models.resolve_models(preset_id, mode, None, fields)
    form.update(resolved.values)
    prompt = str(source.get("prompt_text") or "") if h3 else ""
    return ShotPlan(
        shot_id=str(source["shot_id"]),
        profile=source.get("profile"),
        director_mode=None,
        preset_mode=mode,
        seconds=float(source.get("duration_s") or 0),
        resolution=upscaled_size(source.get("width"), source.get("height"), target),
        fps=source.get("fps"),
        prompt_text=prompt,
        request=_request(preset_id, mode, prompt, form),
        missing_models=list(resolved.missing),
        seeded=False,
    )
