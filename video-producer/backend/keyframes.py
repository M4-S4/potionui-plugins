import logging
import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import core_bridge, director, estimate, generation, limits, models, takes
from .core_bridge import CLOUD_ENGINE, EDIT_TASK, MediaRefError, User
from .director import ShotPlan, note
from .generation import Blocked

logger = logging.getLogger("plugins.video-producer")

KEYFRAME = takes.KEYFRAME

EDIT_MODE = "edit"
IMG2IMG_MODE = "img2img"
IMAGE_MODES = (EDIT_MODE, IMG2IMG_MODE)
MODEL_FIELD = "model"
OUTPUT_SIZE = "output_size"
IMAGE = "image"

FIRST = "first"
LAST = "last"
BOTH = "both"
ROLES = (FIRST, LAST)
ORDER_ROLES = (FIRST, LAST, BOTH)

NO_IMAGE_MODE = "no_image_mode"
MISSING_MODELS = "missing_models"
NO_BACKEND = "no_backend"
NO_KEY = "no_key"
NO_EDIT_MODEL = "no_edit_model"

UNUSABLE = {
    NO_IMAGE_MODE: "This preset has no edit or image to image mode: it cannot keep the pictures of the shot.",
    NO_BACKEND: "The provider of this preset is turned off or not set up in PotionUI.",
    NO_KEY: "The provider of this preset has no API key in PotionUI.",
    NO_EDIT_MODEL: "No edit model of this provider is turned on in its catalog.",
}

MIN_CANDIDATES = 2
MAX_CANDIDATES = 4
DEFAULT_CANDIDATES = 2

MAX_PICTURES = 10
NAME_LIMIT = 200
PROMPT_LIMIT = 4000

FLOOR_SECONDS = 60.0
EDIT_AREA = 1024 * 1024
SIZE_STEP = 16

FRAME = "frame"
SETTING = "setting"
CHARACTER = "character"
OBJECT = "object"
STYLE = "style"

PICTURE_ROLES = (FRAME, SETTING, CHARACTER, OBJECT, STYLE)

SPACES = ("identite", "decors3d")
SET_SPACE = "decors3d"
TYPE_ROLES = {"Personnage": CHARACTER, "Décor": SETTING, "Objet": OBJECT, "Style": STYLE}

REFERENCE = "reference"

TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        FIRST: "The opening frame of a film shot, in a {aspect} frame.",
        LAST: "The closing frame of a film shot, in a {aspect} frame.",
        "frame_first": "Image {n} is the framing of the shot: keep its camera angle, layout, light and colours.",
        "frame_last": "Image {n} is the opening frame of the same shot: keep its place, characters, costumes, light and colours.",
        SETTING: "Image {n} shows the setting{name}: keep its place, light and colours.",
        CHARACTER: "Keep the face, hair, body and costume of {name} from image {n}.",
        OBJECT: "Keep the look of {name} from image {n}.",
        STYLE: "Follow the style, palette and lighting of image {n}, not its content.",
        "character_name": "the character",
        "object_name": "the object",
        "still": "One photographic still: no text, no caption, no border, no split panels.",
    },
    "fr": {
        FIRST: "La première image d'un plan de film, au format {aspect}.",
        LAST: "La dernière image d'un plan de film, au format {aspect}.",
        "frame_first": "L'image {n} est le cadrage du plan : garder son angle de caméra, sa composition, sa lumière et ses couleurs.",
        "frame_last": "L'image {n} est la première image du même plan : garder son lieu, ses personnages, leurs costumes, sa lumière et ses couleurs.",
        SETTING: "L'image {n} montre le décor{name} : garder son lieu, sa lumière et ses couleurs.",
        CHARACTER: "Garder le visage, les cheveux, la silhouette et le costume de {name} de l'image {n}.",
        OBJECT: "Garder l'apparence de {name} de l'image {n}.",
        STYLE: "Suivre le style, la palette et la lumière de l'image {n}, pas son contenu.",
        "character_name": "le personnage",
        "object_name": "l'objet",
        "still": "Une seule image photographique : sans texte, sans légende, sans bordure, sans vignettes.",
    },
}


class OrderError(ValueError):
    """A body the start image routes refuse."""


@dataclass(frozen=True)
class Order:
    preset_id: str
    model_id: Optional[str] = None
    role: str = FIRST
    count: int = DEFAULT_CANDIDATES
    prompt: Optional[str] = None
    pictures: Optional[List[Dict[str, Any]]] = None


@dataclass(frozen=True)
class EditPreset:
    id: str
    name: str
    engine: Optional[str]
    field: str
    max_images: int
    driver: Optional[str] = None
    backend_id: Optional[str] = None
    requires: Optional[Dict[str, Any]] = None
    output_sizes: Tuple[str, ...] = ()
    models: Tuple[Dict[str, Any], ...] = ()
    mode: Optional[str] = EDIT_MODE
    reason: Optional[str] = None
    missing: Tuple[str, ...] = ()

    @property
    def cloud(self) -> bool:
        return self.engine == CLOUD_ENGINE

    @property
    def usable(self) -> bool:
        return self.reason is None

    def model(self, model_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """The enabled edit model of a cloud preset with this id, or None."""
        return next((model for model in self.models if model["id"] == model_id), None)

    def limit(self, model_id: Optional[str]) -> int:
        """The most reference pictures a run takes: the field's limit, lowered to the cloud model's."""
        own = int((self.model(model_id) or {}).get("max_images") or 0)
        return min(self.max_images, own) if self.cloud and own > 0 else self.max_images

    def summary(self) -> Dict[str, Any]:
        """The preset as GET /me lists it."""
        return {
            "id": self.id,
            "name": self.name,
            "engine": self.engine,
            "driver": self.driver,
            "backend_id": self.backend_id,
            "requires": self.requires,
            "mode": self.mode,
            "max_images": self.max_images,
            "usable": self.usable,
            "reason": self.reason,
            "missing": list(self.missing),
            "models": [
                {"id": model["id"], "name": model["name"], "max_images": self.limit(model["id"])} for model in self.models
            ],
        }


@dataclass(frozen=True)
class Picture:
    value: str
    role: str
    name: str
    origin: str
    asset_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def summary(self, rank: int) -> Dict[str, Any]:
        """The picture as the estimate reports it, with its rank among the images sent."""
        return {"rank": rank, "asset_id": self.asset_id, "role": self.role, "name": self.name, "origin": self.origin}


@dataclass
class KeyframePlan:
    preset: Optional[EditPreset]
    shot_id: str
    role: str = FIRST
    pictures: List[Picture] = field(default_factory=list)
    plan: Optional[ShotPlan] = None
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Evaluation:
    parts: List[KeyframePlan]
    minutes: float
    payload: Dict[str, Any]

    @property
    def built(self) -> KeyframePlan:
        return self.parts[0]

    @property
    def blocked(self) -> bool:
        return bool(self.payload["blocks"])


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_CANDIDATES <= value <= MAX_CANDIDATES


def _pictures(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_PICTURES * 2:
        raise OrderError(f"references must be a list of at most {MAX_PICTURES * 2} pictures.")
    pictures = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("asset_id"), str) or not item["asset_id"]:
            raise OrderError("Each reference needs an asset_id.")
        role = item.get("role", SETTING)
        if role not in PICTURE_ROLES:
            raise OrderError(f"A reference role must be one of: {', '.join(PICTURE_ROLES)}.")
        name = item.get("name", "")
        if not isinstance(name, str) or len(name) > NAME_LIMIT:
            raise OrderError(f"A reference name must be a string of at most {NAME_LIMIT} characters.")
        pictures.append({"asset_id": item["asset_id"], "role": role, "name": name.strip()})
    return pictures


def parse_order(body: Any) -> Order:
    """The preset, model, frame role, number of candidates, prompt and pictures a body asks for; OrderError for a malformed one."""
    if not isinstance(body, dict):
        raise OrderError("The request body must be a JSON object.")
    preset_id = body.get("preset_id")
    if not isinstance(preset_id, str) or not preset_id:
        raise OrderError("preset_id must be a preset id.")
    model_id = body.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        raise OrderError("model_id must be a model id or null.")
    role = body.get("role", FIRST)
    if role not in ORDER_ROLES:
        raise OrderError(f"role must be one of: {', '.join(ORDER_ROLES)}.")
    count = body.get("count", DEFAULT_CANDIDATES)
    if not _count(count):
        raise OrderError(f"count must be an integer from {MIN_CANDIDATES} to {MAX_CANDIDATES}.")
    prompt = body.get("prompt")
    if prompt is not None and (not isinstance(prompt, str) or len(prompt) > PROMPT_LIMIT):
        raise OrderError(f"prompt must be a string of at most {PROMPT_LIMIT} characters.")
    pictures = _pictures(body["references"]) if body.get("references") is not None else None
    return Order(preset_id=preset_id, model_id=model_id, role=role, count=count, prompt=prompt, pictures=pictures)


def _asset(doc: Mapping[str, Any], asset_id: Any) -> Optional[Dict[str, Any]]:
    return next((asset for asset in doc.get("assets") or [] if asset_id and asset.get("id") == asset_id), None)


def _param(model: Mapping[str, Any], name: str) -> Optional[Dict[str, Any]]:
    return next(
        (
            param
            for param in model.get("params") or []
            if param.get("name") == name and (not param.get("tasks") or EDIT_TASK in param["tasks"])
        ),
        None,
    )


def _request(preset_id: str, mode: str, prompt: str, form: Dict[str, Any]) -> Dict[str, Any]:
    return {"preset_id": preset_id, "mode": mode, "prompts": [{"positive": prompt, "negative": ""}], "form_data": form}


def _image_field(mode: Any) -> Optional[str]:
    forms = mode.forms or {}
    fields = forms.get(mode.default_form) or next(iter(forms.values()), {})
    images = [name for name, spec in fields.items() if spec.type == IMAGE]
    return next((name for name in images if fields[name].multi), images[0] if images else None)


def _limit(spec: Mapping[str, Any]) -> int:
    if not spec.get("multi"):
        return 1
    value = spec.get("max_items")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else MAX_PICTURES


def _edit_models(backend_id: Optional[str]) -> Tuple[Dict[str, Any], ...]:
    if not backend_id:
        return ()
    try:
        return tuple(core_bridge.cloud_edit_models(backend_id))
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the edit models of cloud backend %s", backend_id, exc_info=True)
        return ()


def _cloud_backends() -> List[Dict[str, Any]]:
    try:
        return [backend for backend in core_bridge.enabled_backends() if backend.get("engine") == CLOUD_ENGINE]
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the backends; no edit preset is tied to a cloud one", exc_info=True)
        return []


def _image_modes(description: Any) -> List[str]:
    modes = description.modes or {}
    return [name for name in IMAGE_MODES if name in modes and _image_field(modes[name]) is not None]


def _mode_preset(description: Any, mode: str, **extra: Any) -> EditPreset:
    name = _image_field(description.modes[mode]) or ""
    fields = models.form_fields(description.id, mode)
    sizes = (fields.get(OUTPUT_SIZE) or {}).get("options") or []
    return EditPreset(
        id=description.id,
        name=description.name,
        engine=description.engine,
        field=name,
        max_images=_limit(fields.get(name) or {}),
        requires=description.requires,
        output_sizes=tuple(option["value"] for option in sizes if models.parse_size(option["value"])),
        mode=mode,
        **extra,
    )


def _native_preset(description: Any, mode: str) -> EditPreset:
    missing = tuple(models.resolve_models(description.id, mode, None, models.form_fields(description.id, mode)).missing)
    return _mode_preset(description, mode, reason=MISSING_MODELS if missing else None, missing=missing)


def _provider(driver: Optional[str], cloud_backends: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    own = [backend for backend in cloud_backends if driver and backend.get("driver") == driver]
    return next((backend for backend in own if backend.get("configured") is not False), own[0] if own else None)


def _cloud_preset(description: Any, mode: str, cloud_backends: List[Dict[str, Any]]) -> EditPreset:
    driver = core_bridge.preset_driver(description.id)
    backend = _provider(driver, cloud_backends)
    ready = backend is not None and backend.get("configured") is not False
    found = _edit_models(backend.get("id")) if ready else ()
    reason = None
    if backend is None:
        reason = NO_BACKEND
    elif not ready:
        reason = NO_KEY
    elif MODEL_FIELD not in models.form_fields(description.id, mode) or not found:
        reason = NO_EDIT_MODEL
    return _mode_preset(description, mode, driver=driver, backend_id=backend.get("id") if backend else None, models=found, reason=reason)


def _image_preset(description: Any, cloud_backends: List[Dict[str, Any]]) -> Optional[EditPreset]:
    modes = _image_modes(description)
    if not modes:
        if description.category != IMAGE:
            return None
        return EditPreset(id=description.id, name=description.name, engine=description.engine, field="", max_images=0, requires=description.requires, mode=None, reason=NO_IMAGE_MODE)
    if description.engine == CLOUD_ENGINE:
        return _cloud_preset(description, modes[0], cloud_backends)
    found = [_native_preset(description, mode) for mode in modes]
    return next((preset for preset in found if preset.usable), found[0])


def image_presets(user: User) -> List[EditPreset]:
    """Every image preset the user may run, each with the mode its start images use (edit, else image to image, the first whose models are installed) or why it cannot make one; usable ones first, local before cloud."""
    try:
        descriptions = core_bridge.list_presets(user)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s; reporting no image preset", user.id, exc_info=True)
        return []
    wanted = [description for description in descriptions if _image_modes(description) or description.category == IMAGE]
    cloud_backends = _cloud_backends() if any(description.engine == CLOUD_ENGINE for description in wanted) else []
    found = []
    for description in wanted:
        try:
            preset = _image_preset(description, cloud_backends)
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not read the image modes of preset %s", description.id, exc_info=True)
            continue
        if preset is not None:
            found.append(preset)
    return sorted(found, key=lambda preset: (not preset.usable, preset.cloud, preset.name.lower()))


def edit_presets(user: User) -> List[EditPreset]:
    """The image presets the user may run that can make a start image now."""
    return [preset for preset in image_presets(user) if preset.usable]


def _visible(user: User, preset_id: str) -> bool:
    try:
        return any(description.id == preset_id for description in core_bridge.list_presets(user))
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not list the presets of user %s", user.id, exc_info=True)
        return False


def preset_state(user: User, preset_id: str) -> str:
    """Why an image preset is missing for the user: not_loaded, not_installed, not_assigned (to them), not_edit when they may run it but it makes no image, or unknown."""
    try:
        state = core_bridge.preset_state(preset_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read the state of preset %s", preset_id, exc_info=True)
        return "unknown"
    if not state.loaded:
        return "not_loaded"
    if not state.installed:
        return "not_installed"
    return "not_edit" if _visible(user, preset_id) else "not_assigned"


def _missing_preset(user: User, preset_id: str) -> Dict[str, Any]:
    return note(
        "preset_missing",
        "This image preset is not available to you: it is not installed, not assigned to you, or makes no image.",
        preset_id=preset_id,
        state=preset_state(user, preset_id),
    )


def _unusable(preset: EditPreset) -> Dict[str, Any]:
    return note("preset_unusable", UNUSABLE.get(preset.reason or "", "This image preset cannot make a start image."), preset_id=preset.id, reason=preset.reason)


def _role_of(reference: Mapping[str, Any]) -> str:
    if reference.get("space") == SET_SPACE:
        return SETTING
    return TYPE_ROLES.get(str(reference.get("type") or ""), CHARACTER)


def _dimension(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _picture(user: User, doc: Mapping[str, Any], asset_id: Any, role: str, name: str, origin: str) -> Optional[Picture]:
    asset = _asset(doc, asset_id)
    if asset is None or asset.get("kind") != IMAGE:
        return None
    ref = director.media_ref(asset.get("origin"))
    if ref is None:
        return None
    try:
        resolved = core_bridge.resolve_media(user, ref)
    except MediaRefError:
        return None
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not resolve media %s", ref, exc_info=True)
        return None
    if str(resolved.get("media_type") or IMAGE).split("/", 1)[0] != IMAGE:
        return None
    return Picture(
        value=resolved["value"],
        role=role,
        name=name or str(asset.get("name") or ""),
        origin=origin,
        asset_id=str(asset_id),
        width=_dimension(asset.get("width")),
        height=_dimension(asset.get("height")),
    )


def _frame_base(doc: Mapping[str, Any], shot_id: str, role: str) -> Optional[Mapping[str, Any]]:
    first, _ = director.shot_frames(doc, shot_id)
    if first is None:
        return None
    return first if role == LAST else None


def _shot_references(doc: Mapping[str, Any], shot_id: str) -> List[Mapping[str, Any]]:
    excluded = director.excluded_references(doc, shot_id)
    scoped, shared = [], []
    for reference in doc.get("references") or []:
        if reference.get("space") not in SPACES or not reference.get("assetId"):
            continue
        scope = reference.get("scope")
        if isinstance(scope, Mapping) and scope.get("type") == "shot":
            if scope.get("shotId") == shot_id:
                scoped.append(reference)
        elif reference.get("id") not in excluded:
            shared.append(reference)
    return [*scoped, *shared]


def default_pictures(user: User, doc: Mapping[str, Any], clip: Mapping[str, Any], role: str) -> List[Picture]:
    """What a shot sends to make its start or end image: its start image (for the end image), then its Décors and Identité pictures, its own before the global ones it does not exclude; settings before characters, objects and styles."""
    found: List[Picture] = []

    def add(picture: Optional[Picture]) -> None:
        if picture is not None and all(seen.value != picture.value for seen in found):
            found.append(picture)

    base = _frame_base(doc, clip["id"], role)
    if base is not None:
        add(_picture(user, doc, base.get("assetId"), FRAME, "", FRAME))
    for reference in _shot_references(doc, clip["id"]):
        add(_picture(user, doc, reference.get("assetId"), _role_of(reference), str(reference.get("name") or ""), REFERENCE))
    rank = {value: index for index, value in enumerate(PICTURE_ROLES)}
    return sorted(found, key=lambda picture: rank[picture.role])


def chosen_pictures(
    user: User, doc: Mapping[str, Any], chosen: Sequence[Mapping[str, Any]], warnings: List[Dict[str, Any]]
) -> List[Picture]:
    """The pictures a body names, in its order, each an image asset of the project the user may read; the others are left out with a warning."""
    found: List[Picture] = []
    for item in chosen:
        picture = _picture(user, doc, item["asset_id"], item["role"], item["name"], FRAME if item["role"] == FRAME else REFERENCE)
        if picture is None:
            warnings.append(
                note("reference_unavailable", "A picture is not an image of the project you can read: it is left out.", asset_id=item["asset_id"])
            )
        elif all(seen.value != picture.value for seen in found):
            found.append(picture)
    return found


def _language(doc: Mapping[str, Any]) -> str:
    language = doc.get("promptLanguage")
    return language if language in TEXT else "en"


def _aspect_text(doc: Mapping[str, Any]) -> str:
    aspect = str(doc.get("aspect") or "").strip()
    return aspect or f"{director.aspect_of(doc):.2f}:1"


def picture_lines(pictures: Sequence[Picture], role: str, language: str) -> List[str]:
    """What the prompt says of each picture sent, by its rank."""
    text = TEXT[language]
    lines = []
    for rank, picture in enumerate(pictures, start=1):
        if picture.role == FRAME:
            lines.append(text["frame_last" if role == LAST else "frame_first"].format(n=rank))
        elif picture.role == SETTING:
            lines.append(text[SETTING].format(n=rank, name=f" ({picture.name})" if picture.name else ""))
        elif picture.role in (CHARACTER, OBJECT):
            lines.append(text[picture.role].format(n=rank, name=picture.name or text[f"{picture.role}_name"]))
        else:
            lines.append(text[STYLE].format(n=rank))
    return lines


def keyframe_prompt(
    doc: Mapping[str, Any], clip: Mapping[str, Any], pictures: Sequence[Picture], role: str, instruction: Optional[str] = None
) -> str:
    """The edit prompt of a start or end image: the frame it is, the instruction given (else the shot's) and the project's direction, what to keep of each picture, and a still with no text."""
    language = _language(doc)
    text = TEXT[language]
    own = (instruction or "").strip() or director.shot_instruction(doc, clip)
    lines = [
        text[role].format(aspect=_aspect_text(doc)),
        own,
        *director.direction_lines(doc),
        *picture_lines(pictures, role, language),
        text["still"],
    ]
    return "\n".join(line for line in lines if line)


def _distance(width: int, height: int, aspect: float) -> float:
    return abs(math.log(width / height) - math.log(aspect))


def closest_size(values: Sequence[str], aspect: float) -> Optional[str]:
    """The offered size closest to the aspect ratio, then to one megapixel."""
    sizes = [(value, *models.parse_size(value)) for value in values if models.parse_size(value)]
    if not sizes:
        return None
    return min(sizes, key=lambda size: (round(_distance(size[1], size[2], aspect), 3), abs(size[1] * size[2] - EDIT_AREA)))[0]


def edit_size(picture: Picture) -> Optional[str]:
    """The size an edit takes from its first picture: its aspect ratio at about one megapixel, in steps of 16 pixels."""
    if not picture.width or not picture.height:
        return None
    scale = math.sqrt(EDIT_AREA / (picture.width * picture.height))
    width = max(SIZE_STEP, round(picture.width * scale / SIZE_STEP) * SIZE_STEP)
    height = max(SIZE_STEP, round(picture.height * scale / SIZE_STEP) * SIZE_STEP)
    return f"{width}x{height}"


def _mismatch(size: Optional[str], aspect: float) -> bool:
    parsed = models.parse_size(size)
    return parsed is not None and _distance(parsed[0], parsed[1], aspect) > director.ASPECT_TOLERANCE


def _ratio(value: Any) -> Optional[float]:
    parts = str(value).split(":")
    if len(parts) != 2 or not all(part.strip().replace(".", "", 1).isdigit() for part in parts):
        return None
    width, height = float(parts[0]), float(parts[1])
    return width / height if width > 0 and height > 0 else None


def closest_aspect(values: Sequence[Any], aspect: float) -> Optional[str]:
    """The offered aspect ratio closest to the project's."""
    ratios = [(abs(math.log(ratio) - math.log(aspect)), str(value)) for value in values if (ratio := _ratio(value)) is not None]
    return min(ratios)[1] if ratios else None


def _cloud_form(model: Mapping[str, Any], doc: Mapping[str, Any], fields: models.Fields) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    form: Dict[str, Any] = {"seed": -1, MODEL_FIELD: f"{models.MODEL_REF}{model['id']}"}
    if "count" in fields:
        form["count"] = 1
    params: Dict[str, Any] = {}
    aspect_param = _param(model, "aspect_ratio")
    if aspect_param is not None and "aspect_ratio" in fields:
        values = [str(value) for value in aspect_param.get("values") or []]
        wanted = doc.get("aspect") if doc.get("aspect") in values else closest_aspect(values, director.aspect_of(doc))
        chosen = wanted or aspect_param.get("default")
        if chosen is not None:
            form["aspect_ratio"] = params["aspect_ratio"] = str(chosen)
    resolution = director.cloud_resolution(_param(model, "resolution"), "draft")
    if resolution is not None and "resolution" in fields:
        form["resolution"] = params["resolution"] = resolution
    return form, params


def build(user: User, doc: Mapping[str, Any], shot_id: str, order: Order) -> KeyframePlan:
    """The edit request of a shot's start or end image candidates, with the pictures it sends and what blocks or warns about it."""
    clip = director.clip_of(doc, shot_id)
    preset = next((preset for preset in image_presets(user) if preset.id == order.preset_id), None)
    built = KeyframePlan(preset=preset, shot_id=shot_id, role=order.role)
    if clip is None:
        built.blocks.append(note("shot_not_found", "The shot does not exist.", shot_id=shot_id))
        return built
    if preset is None:
        built.blocks.append(_missing_preset(user, order.preset_id))
        return built
    if not preset.usable and preset.reason != MISSING_MODELS:
        built.blocks.append(_unusable(preset))
        return built
    model = preset.model(order.model_id) if preset.cloud else None
    if preset.cloud and model is None:
        built.blocks.append(note("no_model", "Choose an edit model that is turned on for this provider.", preset_id=preset.id))
        return built
    if order.pictures is None:
        pictures = default_pictures(user, doc, clip, order.role)
    else:
        pictures = chosen_pictures(user, doc, order.pictures, built.warnings)
    limit = preset.limit(order.model_id)
    if len(pictures) > limit:
        built.warnings.append(
            note("references_trimmed", f"The model takes at most {limit} {'picture' if limit == 1 else 'pictures'}: the last ones are left out.", sent=limit, found=len(pictures))
        )
        pictures = pictures[:limit]
    built.pictures = pictures
    if not pictures:
        built.blocks.append(note("no_references", "Add an identity or 3D set picture to the shot first.", shot_id=shot_id))
        return built
    mode = preset.mode or EDIT_MODE
    fields = models.form_fields(preset.id, mode)
    aspect = director.aspect_of(doc)
    prompt = keyframe_prompt(doc, clip, pictures, order.role, order.prompt)
    params: Dict[str, Any] = {}
    missing: List[str] = []
    if preset.cloud:
        form, params = _cloud_form(model or {}, doc, fields)
        size = None
        if form.get("aspect_ratio") and form["aspect_ratio"] != doc.get("aspect"):
            built.warnings.append(
                note("aspect_mismatch", "The model offers no frame in the project's aspect ratio.", aspect=doc.get("aspect"), size=form["aspect_ratio"])
            )
    else:
        form = {"seed": -1}
        if "quantity" in fields:
            form["quantity"] = 1
        size = closest_size(preset.output_sizes, aspect) if preset.output_sizes else edit_size(pictures[0])
        if size is not None and preset.output_sizes:
            form[OUTPUT_SIZE] = size
        if _mismatch(size, aspect):
            built.warnings.append(
                note("aspect_mismatch", "The image takes the aspect ratio of the first picture, not the project's.", aspect=doc.get("aspect"), size=size)
            )
        resolved = models.resolve_models(preset.id, mode, None, fields)
        form.update(resolved.values)
        missing = list(resolved.missing)
        if missing:
            built.blocks.append(generation.missing_block(missing))
    form[preset.field] = [picture.value for picture in pictures]
    built.plan = ShotPlan(
        shot_id=shot_id,
        profile=None,
        director_mode=None,
        preset_mode=mode,
        seconds=0.0,
        resolution=size,
        fps=None,
        prompt_text=prompt,
        request=_request(preset.id, mode, prompt, form),
        model_id=model["id"] if model else None,
        cloud_task=EDIT_TASK if preset.cloud else None,
        cloud_params=params,
        missing_models=missing,
        preset_id=preset.id,
        cloud=preset.cloud,
        backend_id=preset.backend_id,
        seed=director.shot_engine(doc, shot_id).get("seed"),
    )
    return built


def candidate_minutes(preset_id: str, backend_id: Optional[str], resolution: Optional[str]) -> Tuple[float, Optional[float], int]:
    """The GPU minutes one candidate reserves, the seconds one took when measured, and how many measures back them."""
    ratio, samples = estimate.calibrated_ratio(preset_id, backend_id, resolution)
    return round((ratio if ratio is not None else FLOOR_SECONDS) / 60, 3), ratio, samples


def _quota(owner: User, needed: float, applies: bool) -> Dict[str, Any]:
    status = limits.gpu_minutes_status(owner.id)
    remaining = status.get("remaining")
    limited = generation.reserves(status)
    return {
        "limit": status.get("limit"),
        "used": status.get("used"),
        "remaining": remaining,
        "exempt": bool(status.get("exempt")),
        "needed_minutes": round(needed, 2) if applies else 0.0,
        "applies": applies,
        "blocks": bool(applies and limited and remaining is not None and needed > float(remaining) + 1e-9),
    }


def _part(order: Order, role: str) -> Order:
    if order.role != BOTH:
        return order
    pictures = order.pictures
    if role == FIRST and pictures is not None:
        pictures = [picture for picture in pictures if picture["role"] != FRAME]
    return replace(order, role=role, pictures=pictures)


def _distinct(notes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for item in notes:
        if item not in kept:
            kept.append(item)
    return kept


def _summary(part: KeyframePlan) -> Dict[str, Any]:
    plan = part.plan
    return {
        "role": part.role,
        "resolution": plan.resolution if plan else None,
        "prompt": plan.prompt_text if plan else None,
        "references": [picture.summary(rank) for rank, picture in enumerate(part.pictures, start=1)],
    }


async def evaluate(caller: User, owner: User, project: Mapping[str, Any], shot_id: str, order: Order) -> Evaluation:
    """What the start or end image candidates of a shot, or both, would need in memory, time, GPU minutes and money, the pictures each image sends, and what blocks them; with both, the end image takes the frame pictures and the start image does not."""
    roles = ROLES if order.role == BOTH else (order.role,)
    parts = [build(owner, project["doc"], shot_id, _part(order, role)) for role in roles]
    built = parts[0]
    plan = built.plan
    runs = order.count * len(parts)
    vram = estimate.unknown_vram()
    warnings = [item for part in parts for item in part.warnings]
    minutes, ratio, samples = 0.0, None, 0
    cost = None
    if plan is not None and not plan.cloud:
        if not plan.missing_models:
            vram, found = await estimate.plan_vram(owner, plan)
            warnings.extend(found)
        minutes, ratio, samples = candidate_minutes(plan.preset_id, vram.get("backend_id"), plan.resolution)
        if ratio is None:
            warnings.append(note("time_unknown", "No candidate of this preset was measured at this size yet."))
    elif plan is not None and plan.model_id:
        cloud_runs = [{"task": EDIT_TASK, "params": dict(part.plan.cloud_params)} for part in parts if part.plan for _ in range(order.count)]
        cost = estimate.model_cost(caller, plan.model_id, cloud_runs)
    native = plan is not None and not plan.cloud
    quota = _quota(owner, minutes * runs, native)
    blocks = _distinct([item for part in parts for item in part.blocks]) + ([estimate.quota_block(quota)] if quota["blocks"] else [])
    preset = built.preset
    payload = {
        "shot_id": shot_id,
        "role": order.role,
        "count": order.count,
        "preset": {"id": preset.id, "name": preset.name, "cloud": preset.cloud, "mode": preset.mode} if preset else None,
        "model_id": plan.model_id if plan else None,
        "resolution": plan.resolution if plan else None,
        "prompt": plan.prompt_text if plan else None,
        "references": [picture.summary(rank) for rank, picture in enumerate(built.pictures, start=1)],
        "parts": [_summary(part) for part in parts],
        "vram": vram,
        "time": {
            "seconds": round(ratio * runs, 1) if ratio is not None else None,
            "per_candidate": round(ratio, 1) if ratio is not None else None,
            "samples": samples,
        },
        "quota": quota,
        "cost": cost,
        "blocks": blocks,
        "warnings": _distinct(warnings),
    }
    return Evaluation(parts=parts, minutes=minutes if native and generation.reserves(quota) else 0.0, payload=payload)


def next_variants(project_id: str, shot_id: str, count: int) -> List[str]:
    """The first count variant letters no candidate of the shot uses yet."""
    used = {take["variant"] for take in takes.list_keyframes(project_id, shot_id) if take["variant"]}
    free: List[str] = []
    index = 0
    while len(free) < count:
        letter = generation.variant_letter(index)
        if letter not in used:
            free.append(letter)
        index += 1
    return free


async def start(owner: User, project: Mapping[str, Any], evaluation: Evaluation) -> List[Dict[str, Any]]:
    """Create one candidate take per asked image, the start ones first with both, each with the image it is made for, its letter and a seed from the shot's fixed seed or a fresh one, and hand what fits to the core."""
    if evaluation.blocked:
        raise Blocked(evaluation.payload["blocks"])
    first = evaluation.built.plan
    base = first.seed if first.seed is not None else generation.new_seed()
    revision = director.shot_revision(project["doc"], first.shot_id)
    count = evaluation.payload["count"]
    letters = next_variants(project["id"], first.shot_id, count * len(evaluation.parts))
    runs = [part for part in evaluation.parts for _ in range(count)]
    created = [
        generation.create(
            owner,
            project["id"],
            part.plan,
            preset_id=part.plan.preset_id,
            quality="draft",
            kind=KEYFRAME,
            seed=(base + rank) % generation.SEED_RANGE,
            variant=letters[rank],
            minutes=evaluation.minutes,
            revision=revision,
            frame_role=part.role,
        )
        for rank, part in enumerate(runs)
    ]
    await generation.pump(owner)
    return [takes.get_take(take["id"]) for take in created]


def stored_plan(source: Mapping[str, Any]) -> ShotPlan:
    """The plan of a candidate take as it was submitted, to submit it again."""
    request = {key: value for key, value in (source.get("request") or {}).items() if key != "idempotency_key"}
    return ShotPlan(
        shot_id=str(source["shot_id"]),
        profile=None,
        director_mode=None,
        preset_mode=str(source.get("mode") or EDIT_MODE),
        seconds=0.0,
        resolution=source.get("resolution"),
        fps=None,
        prompt_text=str(source.get("prompt_text") or ""),
        request=request,
        model_id=source.get("model_id"),
        preset_id=str(source.get("preset_id") or ""),
        cloud=bool(source.get("model_id")),
    )


async def retry(owner: User, project: Mapping[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    """A new candidate like a failed or cancelled one: same shot, request, seed, letter and image."""
    if source["status"] not in generation.RETRYABLE:
        raise generation.TakeError(409, "take_not_retryable", "Only a failed or cancelled take can be retried.")
    plan = stored_plan(source)
    minutes = 0.0
    if not plan.cloud:
        minutes = candidate_minutes(plan.preset_id, source.get("backend_id"), plan.resolution)[0]
        quota = _quota(owner, minutes, True)
        if quota["blocks"]:
            raise Blocked([estimate.quota_block(quota)])
        if not generation.reserves(quota):
            minutes = 0.0
    take = generation.create(
        owner,
        project["id"],
        plan,
        preset_id=plan.preset_id,
        quality="draft",
        kind=KEYFRAME,
        seed=int(source["seed"]) if source.get("seed") is not None else generation.new_seed(),
        variant=source.get("variant") or generation.variant_letter(0),
        minutes=minutes,
        revision=source.get("shot_revision"),
        frame_role=source.get("frame_role"),
    )
    await generation.pump(owner)
    return takes.get_take(take["id"])
