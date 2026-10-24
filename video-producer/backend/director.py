import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from . import bible, catalog, core_bridge, engine_options, models, presets, settings
from .catalog import FL2VA, PROFILES, REF2VA, REFS_MODE
from .core_bridge import CLOUD_ENGINE, DirectorBindingError, MediaRefError, User

logger = logging.getLogger("plugins.video-producer")

DIRECTION_FIELDS = ("univers", "personnages", "photographie", "palette", "rythme")

FIRST_ROLES = ("first", "début", "debut")
LAST_ROLES = ("last", "fin")

TXT2VIDEO = "txt2video"
IMG2VIDEO = "img2video"

AUDIO_VAE = "audio_vae"

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

QUALITIES = ("draft", "final")

SEED_RANGE = 2**31

AI = "ai"
RENDER_3D = "render3d"
RENDER_3D_AI = "render3d_ai"

PRODUCTIONS = (AI, RENDER_3D, RENDER_3D_AI)

SCENE3D = "scene3d"

GUIDE_MIN_SECONDS = 2.0

LAYOUT_LORA = "ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors"
LAYOUT_REPO = "Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render"
LAYOUT_ID = "ic-layout"
MAX_FPS = 60
LTX_FRAME_STEP = 8
DISTILLED = "distilled"
DISTILLED_RECIPE = {"steps": 8, "cfg": 1.0, "sampler": "euler_ancestral"}

GUIDE = "guide"
REFERENCE = "reference"
SCENE_PICTURE = "scene"
TRACK = "track"

TRACK_PREFIX = "track:"

CONDITION = "condition"
MUX = "mux"
IGNORED = "ignored"

MUX_ID = "a-1"

MAX_MARGIN = 10.0

EPSILON = 1e-6

LABELS = {"image": "Picture", "video": "Video", "audio": "Audio"}

STILL = 0.02
MIN_SHIFT = 0.03
MIN_DEGREES = 1.0
MIN_ZOOM = 0.05

REFS_TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "define_character": "<Subject {subject}> is the character shown in {label}.",
        "define_setting": "<Subject {subject}> is the setting shown in {label}.",
        "define_motion": "{label} is the source of the motion of [Shot 1].",
        "define_audio": "{label} is a reference sound for [Shot 1].",
        "define_guide": "{label} is a rough 3D preview render of the scene, used only as the source of the camera path of [Shot 1].",
        "define_scene": "{label} shows the scene itself: keep its look, colours and lighting.",
        "summary": "[reference generation] A {seconds}-second shot made from the description below and its references.",
        "summary_camera": "[reference generation] A {seconds}-second shot made from the description below, with its camera movement taken from {videos}.",
        "keep_character": "<Subject {subject}> (appears in [Shot 1]): fully_preserved - keeps the identity and the appearance.",
        "keep_setting": "<Subject {subject}> (appears in [Shot 1]): partially_preserved - keeps the place, the subjects, the light and the colours; the framing follows the camera move.",
        "keep_motion": "{label} (motion of [Shot 1]): attribute_transfer - its motion is carried over to the subjects of the shot.",
        "keep_audio": "{label} (sound of [Shot 1]): reference - its voice or sound serves as a reference.",
        "keep_guide": "{label} (camera path of [Shot 1]): weak_reference - camera movement only, not the look: only the direction, amplitude and speed of its camera move are followed; its content, colours, textures, blurred or stretched patches, holes and black borders are not reproduced.",
        "keep_scene": "{label} (look of the scene of [Shot 1]): partially_preserved - keeps the look, the colours and the lighting of the scene; the framing follows the camera path.",
        "cite_setting": "The shot takes place in <Subject {subject}>.",
        "cite_character": "<Subject {subject}> appears in the shot.",
        "camera": "The camera {moves} over the whole shot.",
        "camera_unknown": "The camera follows the camera path of {label}.",
        "forward": "The move follows {label} forward in time: the shot opens on the viewpoint of its first frame and ends on the viewpoint of its last frame, never in reverse.",
        "override": "This camera movement replaces any other camera movement mentioned above.",
        "and": "and",
        "soundscape": "The natural ambient sound of the place and the physical sounds of the action described above.",
        "arc_right": "arcs from left to right around the subject through about {amount} degrees",
        "arc_left": "arcs from right to left around the subject through about {amount} degrees",
        "crane_up": "rises through about {amount} degrees, tilting down to keep the subject framed",
        "crane_down": "lowers through about {amount} degrees, tilting up to keep the subject framed",
        "push_in": "pushes in toward the subject, closing about {amount} % of the distance",
        "pull_out": "pulls back from the subject, widening the distance by about {amount} %",
        "truck_right": "trucks from left to right",
        "truck_left": "trucks from right to left",
        "pedestal_up": "pedestals up",
        "pedestal_down": "pedestals down",
        "pan_right": "pans from left to right through about {amount} degrees",
        "pan_left": "pans from right to left through about {amount} degrees",
        "tilt_up": "tilts up through about {amount} degrees",
        "tilt_down": "tilts down through about {amount} degrees",
        "zoom_in": "zooms in",
        "zoom_out": "zooms out",
        "static": "stays still",
    },
    "fr": {
        "define_character": "<Subject {subject}> est le personnage montré par {label}.",
        "define_setting": "<Subject {subject}> est le décor montré par {label}.",
        "define_motion": "{label} est la source du mouvement de [Shot 1].",
        "define_audio": "{label} est un son de référence pour [Shot 1].",
        "define_guide": "{label} est un rendu 3D de prévisualisation, grossier, de la scène, utilisé seulement comme source de la trajectoire de caméra de [Shot 1].",
        "define_scene": "{label} montre la scène elle-même : garder son aspect, ses couleurs et sa lumière.",
        "summary": "[reference generation] Un plan de {seconds} secondes fait d'après la description ci-dessous et ses références.",
        "summary_camera": "[reference generation] Un plan de {seconds} secondes fait d'après la description ci-dessous, dont le mouvement de caméra vient de {videos}.",
        "keep_character": "<Subject {subject}> (appears in [Shot 1]): fully_preserved - garde l'identité et l'apparence.",
        "keep_setting": "<Subject {subject}> (appears in [Shot 1]): partially_preserved - garde le lieu, les sujets, la lumière et les couleurs ; le cadrage suit le mouvement de caméra.",
        "keep_motion": "{label} (mouvement de [Shot 1]): attribute_transfer - son mouvement est repris par les sujets du plan.",
        "keep_audio": "{label} (son de [Shot 1]): reference - sa voix ou son son sert de référence.",
        "keep_guide": "{label} (trajectoire de caméra de [Shot 1]): weak_reference - mouvement de caméra seulement, pas l'aspect : seuls le sens, l'amplitude et la vitesse de son mouvement de caméra sont suivis ; son contenu, ses couleurs, ses textures, ses zones floues ou étirées, ses trous et ses bords noirs ne sont pas reproduits.",
        "keep_scene": "{label} (aspect de la scène de [Shot 1]): partially_preserved - garde l'aspect, les couleurs et la lumière de la scène ; le cadrage suit la trajectoire de caméra.",
        "cite_setting": "Le plan se déroule dans <Subject {subject}>.",
        "cite_character": "<Subject {subject}> apparaît dans le plan.",
        "camera": "La caméra {moves} sur toute la durée du plan.",
        "camera_unknown": "La caméra suit la trajectoire de caméra de {label}.",
        "forward": "Le mouvement suit {label} dans le sens du temps : le plan s'ouvre sur le point de vue de sa première image et se termine sur celui de sa dernière image, jamais à l'envers.",
        "override": "Ce mouvement de caméra remplace tout autre mouvement de caméra mentionné plus haut.",
        "and": "et",
        "soundscape": "Le son ambiant naturel du lieu et les sons physiques de l'action décrite plus haut.",
        "arc_right": "décrit un arc de gauche à droite d'environ {amount} degrés autour du sujet",
        "arc_left": "décrit un arc de droite à gauche d'environ {amount} degrés autour du sujet",
        "crane_up": "s'élève d'environ {amount} degrés en basculant vers le bas pour garder le sujet cadré",
        "crane_down": "descend d'environ {amount} degrés en basculant vers le haut pour garder le sujet cadré",
        "push_in": "avance vers le sujet en réduisant la distance d'environ {amount} %",
        "pull_out": "recule depuis le sujet en augmentant la distance d'environ {amount} %",
        "truck_right": "se déplace latéralement de gauche à droite",
        "truck_left": "se déplace latéralement de droite à gauche",
        "pedestal_up": "monte verticalement",
        "pedestal_down": "descend verticalement",
        "pan_right": "fait un panoramique de gauche à droite d'environ {amount} degrés",
        "pan_left": "fait un panoramique de droite à gauche d'environ {amount} degrés",
        "tilt_up": "bascule vers le haut d'environ {amount} degrés",
        "tilt_down": "bascule vers le bas d'environ {amount} degrés",
        "zoom_in": "fait un zoom avant",
        "zoom_out": "fait un zoom arrière",
        "static": "reste immobile",
    },
}

ROLES_BY_SPACE = {"identite": "character", "decors3d": "setting", "mouvement": "motion"}


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
class ShotAudio:
    behavior: str
    start: float
    end: float
    lanes: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    sent: Dict[str, str] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return round(self.end - self.start, 6)

    def summary(self) -> Dict[str, Any]:
        """What the shot sends of its sound and how the engine takes it."""
        return {"behavior": self.behavior, "lanes": list(self.lanes), "references": len(self.references)}


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
    guides: List[str] = field(default_factory=list)
    preset_id: str = ""
    quality: str = "draft"
    cloud: bool = False
    backend_id: Optional[str] = None
    seed: Optional[int] = None
    audio: Optional[ShotAudio] = None
    work_scale: float = 1.0

    @property
    def needs_audio(self) -> bool:
        """True when a file of the shot's sound must be cut before its takes are created."""
        return self.audio is not None and self.audio.behavior in (CONDITION, MUX) and bool(self.audio.lanes or self.audio.references)

    def summary(self) -> Dict[str, Any]:
        """The shot as the estimate reports it, with the 3D guides sent as its camera references."""
        return {
            "shot_id": self.shot_id,
            "director_mode": self.director_mode,
            "seconds": self.seconds,
            "resolution": self.resolution,
            "fps": self.fps,
            "guides": list(self.guides),
            "preset_id": self.preset_id,
            "model_id": self.model_id,
            "profile": self.profile,
            "quality": self.quality,
            "audio": self.audio.summary() if self.audio is not None else None,
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


@dataclass(frozen=True)
class TrackCut:
    shot_id: str
    lane_id: str
    start: float
    end: float


@dataclass(frozen=True)
class SentReference:
    value: str
    kind: str
    rank: int
    origin: str
    item: Optional[Dict[str, Any]] = None

    @property
    def label(self) -> str:
        return f"<{LABELS[self.kind]} {self.rank}>"

    @property
    def role(self) -> str:
        if self.origin in (GUIDE, SCENE_PICTURE):
            return self.origin
        if self.kind == "audio":
            return "audio"
        return ROLES_BY_SPACE.get(str((self.item or {}).get("space")), "setting")


@dataclass
class Plans:
    preset: Optional[Preset]
    model: Optional[Dict[str, Any]]
    quality: str
    profile: str
    production: str = AI
    shots: List[ShotPlan] = field(default_factory=list)
    renders: List[Dict[str, Any]] = field(default_factory=list)
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    track_cuts: List[TrackCut] = field(default_factory=list)


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


def shot_revision(doc: Mapping[str, Any], shot_id: str) -> int:
    """How many times the shot was edited in its shot editor; 0 for a shot never edited or unknown."""
    revision = (clip_of(doc, shot_id) or {}).get("revision")
    return revision if isinstance(revision, int) and not isinstance(revision, bool) and revision > 0 else 0


def shot_engine(doc: Mapping[str, Any], shot_id: str) -> Dict[str, Any]:
    """The engine settings a shot sets for itself instead of the project's: a preset with its model, a profile, a quality and a seed, each only when valid."""
    engine = (clip_of(doc, shot_id) or {}).get("engine")
    if not isinstance(engine, Mapping):
        return {}
    chosen: Dict[str, Any] = {}
    preset = engine.get("preset")
    if isinstance(preset, str) and preset:
        model = engine.get("model")
        chosen.update(preset=preset, model=model if isinstance(model, str) and model else None)
    if engine.get("profile") in PROFILES:
        chosen["profile"] = engine["profile"]
    if engine.get("quality") in QUALITIES:
        chosen["quality"] = engine["quality"]
    seed = engine.get("seed")
    if isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < SEED_RANGE:
        chosen["seed"] = seed
    return chosen


def excluded_references(doc: Mapping[str, Any], shot_id: str) -> Set[str]:
    """The ids of the global references the shot leaves out."""
    overrides = (clip_of(doc, shot_id) or {}).get("referenceOverrides")
    exclude = overrides.get("exclude") if isinstance(overrides, Mapping) else None
    return {str(item) for item in exclude if isinstance(item, str)} if isinstance(exclude, list) else set()


def excluded_lanes(doc: Mapping[str, Any], shot_id: str) -> Set[str]:
    """The ids of the reference tracks the shot leaves out."""
    overrides = (clip_of(doc, shot_id) or {}).get("referenceOverrides")
    lanes = overrides.get("excludeLanes") if isinstance(overrides, Mapping) else None
    return {str(item) for item in lanes if isinstance(item, str)} if isinstance(lanes, list) else set()


def reference_margin(doc: Mapping[str, Any]) -> float:
    """The seconds a reference track is cut before and after the shot, from 0 to MAX_MARGIN; 0 when the project sets none."""
    margin = (doc.get("engine") or {}).get("referenceMargin")
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not math.isfinite(margin):
        return 0.0
    return float(min(max(margin, 0.0), MAX_MARGIN))


def item_reference(item: Mapping[str, Any], lane: Mapping[str, Any]) -> bool:
    """Whether an audio item is sent as a reference for the generation: its own flag when it sets one, else its track's."""
    flag = item.get("reference")
    return flag if isinstance(flag, bool) else lane.get("reference") is True


def reference_lanes(doc: Mapping[str, Any], shot_id: str, start: float, end: float) -> List[Dict[str, Any]]:
    """The audio tracks a shot takes a reference sound from between start and end that it does not leave out, in track order: each track with an item sent as a reference there, and each track checked as a reference with nothing at all there, which the shot says is empty."""
    excluded = excluded_lanes(doc, shot_id)
    lanes = []
    for lane in doc.get("lanes") or []:
        if lane.get("id") in excluded:
            continue
        heard = _items_under(doc, lane.get("id"), start, end)
        if any(item_reference(item, lane) for item in heard) or (not heard and lane.get("reference") is True):
            lanes.append(lane)
    return lanes


def _any_solo(doc: Mapping[str, Any]) -> bool:
    video = doc.get("video") if isinstance(doc.get("video"), Mapping) else {}
    return video.get("solo") is True or any(lane.get("solo") is True for lane in doc.get("lanes") or [])


def lane_heard(doc: Mapping[str, Any], lane: Mapping[str, Any]) -> bool:
    """Whether a track is in the mix: not muted, and soloed when any track is."""
    return not lane.get("mute") and (not _any_solo(doc) or lane.get("solo") is True)


def _items_under(doc: Mapping[str, Any], lane_id: Any, start: float, end: float) -> List[Dict[str, Any]]:
    items = [
        item
        for item in doc.get("audio") or []
        if item.get("lane") == lane_id
        and float(item.get("dur") or 0) > EPSILON
        and _overlap(start, end, item) > EPSILON
    ]
    return sorted(items, key=lambda item: float(item.get("start") or 0))


def lane_items(doc: Mapping[str, Any], lane_id: Any, start: float, end: float) -> List[Dict[str, Any]]:
    """The audio items of a track that play between start and end on the timeline and are sent as a reference, in time order."""
    lane = next((lane for lane in doc.get("lanes") or [] if lane.get("id") == lane_id), {})
    return [item for item in _items_under(doc, lane_id, start, end) if item_reference(item, lane)]


def _asset_kind(doc: Mapping[str, Any], asset_id: Any) -> Optional[str]:
    return (_asset(doc, asset_id) or {}).get("kind")


def audio_references(doc: Mapping[str, Any], shot_id: str) -> List[Dict[str, Any]]:
    """The references of the shot whose media is a sound: its own, then the global ones it does not exclude."""
    excluded = excluded_references(doc, shot_id)
    scoped, shared = [], []
    for reference in doc.get("references") or []:
        if _asset_kind(doc, reference.get("assetId")) != "audio":
            continue
        scope = reference.get("scope")
        if isinstance(scope, Mapping) and scope.get("type") == "shot":
            if scope.get("shotId") == shot_id:
                scoped.append(reference)
        elif reference.get("id") not in excluded:
            shared.append(reference)
    return [*scoped, *shared]


def audio_behavior(preset: Preset, profile: Optional[str]) -> str:
    """How an engine takes the sound of a shot: as a guide in MiniMax-H3's reference mode, mixed onto the take when its director mode declares audio, else not at all."""
    if profile == REF2VA:
        return CONDITION
    if preset.cloud:
        return IGNORED
    return MUX if catalog.audio_mux(preset.variables) else IGNORED


def _track_lanes(
    doc: Mapping[str, Any],
    shot_id: str,
    start: float,
    end: float,
    warnings: List[Dict[str, Any]],
    silent: Collection[str] = (),
) -> List[str]:
    lanes: List[str] = []
    for lane in reference_lanes(doc, shot_id, start, end):
        if not lane_heard(doc, lane):
            warnings.append(
                note("audio_track_muted", "The reference track is muted: nothing of it is sent.", shot_id=shot_id, lane_id=lane["id"])
            )
        elif not lane_items(doc, lane["id"], start, end):
            warnings.append(
                note("audio_track_empty", "The reference track has no sound under the shot: nothing of it is sent.", shot_id=shot_id, lane_id=lane["id"])
            )
        elif lane["id"] in silent:
            warnings.append(
                note("audio_track_silent", "The reference track is silent under the shot: nothing of it is sent.", shot_id=shot_id, lane_id=lane["id"])
            )
        else:
            lanes.append(str(lane["id"]))
    return lanes


def condition_window(doc: Mapping[str, Any], clip: Mapping[str, Any], seconds: float) -> Tuple[float, float]:
    """The part of the timeline a reference track is cut from for a guided shot: the shot with the project's margin on both sides, never before 0."""
    start = float(clip.get("start") or 0)
    margin = reference_margin(doc)
    return max(0.0, start - margin), start + seconds + margin


def mux_window(clip: Mapping[str, Any], seconds: float) -> Tuple[float, float]:
    """The part of the timeline mixed onto a take: exactly the shot, so that the sound stays in sync with the picture."""
    start = float(clip.get("start") or 0)
    return start, start + seconds


def _audio_note(behavior: str, shot_id: str) -> Dict[str, Any]:
    if behavior == CONDITION:
        return note("audio_condition", "The sound of the shot guides the generation.", shot_id=shot_id)
    if behavior == MUX:
        return note("audio_mux", "The sound of the shot is mixed onto the take, not used as a guide.", shot_id=shot_id)
    return note("audio_ignored", "This engine ignores the sound of the shot.", shot_id=shot_id)


def _ignored_audio(doc: Mapping[str, Any], clip: Mapping[str, Any], seconds: float, warnings: List[Dict[str, Any]]) -> Optional[ShotAudio]:
    shot_id = clip["id"]
    if not audio_references(doc, shot_id) and not reference_lanes(doc, shot_id, *mux_window(clip, seconds)):
        return None
    warnings.append(_audio_note(IGNORED, shot_id))
    return ShotAudio(behavior=IGNORED, start=0.0, end=0.0)


def mux_audio(doc: Mapping[str, Any], clip: Mapping[str, Any], seconds: float, warnings: List[Dict[str, Any]]) -> Optional[ShotAudio]:
    """What a shot mixes onto its take: the part of its reference tracks under it and its audio references, or None when it has neither."""
    shot_id = clip["id"]
    references = [str(reference["assetId"]) for reference in audio_references(doc, shot_id)]
    start, end = mux_window(clip, seconds)
    if not references and not reference_lanes(doc, shot_id, start, end):
        return None
    lanes = _track_lanes(doc, shot_id, start, end, warnings)
    if not lanes and not references:
        return None
    warnings.append(_audio_note(MUX, shot_id))
    return ShotAudio(behavior=MUX, start=start, end=end, lanes=lanes, references=list(dict.fromkeys(references)))


def mux_entry(value: str, length: float) -> Dict[str, Any]:
    """The audio entry of a director document that lays a stored sound onto the finished video."""
    return {
        "id": MUX_ID,
        "role": MUX,
        "start": 0.0,
        "trim_start": 0.0,
        "length": length,
        "media": {"path": value, "relative_path": value, "type": "audio"},
    }


def audio_document(document: Dict[str, Any], seconds: float, fps: float, capabilities: Mapping[str, Any]) -> Dict[str, Any]:
    """A one-segment document turned into a director document that can carry an audio entry: timed by start and end, or by a frame count when the preset chains its segments."""
    document = copy.deepcopy(document)
    document["mode"] = "director"
    segment = document["segments"][0]
    if capabilities.get("segment_routing"):
        segment["frames"] = max(1, math.floor(seconds * fps + 0.5))
    else:
        segment.update(start=0.0, end=seconds)
    return document


def _overlap(start: float, end: float, item: Mapping[str, Any]) -> float:
    begin = float(item.get("start") or 0)
    return min(end, begin + float(item.get("dur") or 0)) - max(start, begin)


def shot_instruction(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> str:
    """The shot's own instruction, else the global one covering most of its interval."""
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
    return str(local.get("text") or "").strip() if local is not None else ""


def direction_lines(doc: Mapping[str, Any]) -> List[str]:
    """The filled direction fields of the project, in order."""
    direction = doc.get("direction") or {}
    return [text for text in (str(direction.get(name) or "").strip() for name in DIRECTION_FIELDS) if text]


def shot_prompt(doc: Mapping[str, Any], clip: Mapping[str, Any], engine: str = bible.OTHER) -> str:
    """The shot's instruction, then the filled direction fields, one per line; the characters and the place cast in the shot from the bible are repeated word for word in the engine's format: as subject_definitions ahead of the prompt for MiniMax-H3, re-announced after the action in one paragraph for LTX, ahead of the action for Wan, the cloud models and the other engines."""
    instruction = shot_instruction(doc, clip)
    plain = [line for line in [instruction, *direction_lines(doc)] if line]
    characters, place = bible.cast_of(doc, clip)
    cast = [*characters, *([place] if place is not None else [])]
    if not cast:
        return "\n".join(plain)
    language = _language(doc)
    if engine == bible.H3:
        subjects = " ".join(bible.definition(card, index, language) for index, card in enumerate(cast, 1))
        return "\n\n".join(part for part in (f"subject_definitions: {subjects}", "\n".join(plain)) if part)
    described = bible.prose(characters, place, language)
    if engine == bible.LTX:
        return " ".join(_sentence(line) for line in [instruction, *described, *direction_lines(doc)] if line)
    return "\n".join([*described, *plain])


def _bible_warnings(doc: Mapping[str, Any], clip: Mapping[str, Any], prompt: str, engine: str, warnings: List[Dict[str, Any]]) -> None:
    characters, _ = bible.cast_of(doc, clip)
    missing = bible.missing_labels(shot_instruction(doc, clip), characters)
    if missing:
        warnings.append(
            note(
                "bible_label_missing",
                f"The instruction of the shot does not name {', '.join(missing)}, cast in it.",
                shot_id=clip["id"],
                labels=missing,
            )
        )
    limit, tokens = bible.token_limit(engine), bible.estimated_tokens(prompt)
    if limit is not None and tokens > limit:
        warnings.append(
            note(
                "prompt_too_long",
                f"The prompt of the shot takes about {tokens} tokens, more than the {limit} the engine reads.",
                shot_id=clip["id"],
                tokens=tokens,
                limit=limit,
            )
        )


def _language(doc: Mapping[str, Any]) -> str:
    language = doc.get("promptLanguage")
    return language if language in REFS_TEXT else "en"


def _sentence(text: str) -> str:
    return text if text[-1:] in ".!?…»\"'" else f"{text}."


def _listed(items: Sequence[str], conjunction: str) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def _seconds_text(seconds: float, language: str) -> str:
    text = f"{seconds:g}"
    return text.replace(".", ",") if language == "fr" else text


def _point(value: Any) -> Optional[List[float]]:
    if isinstance(value, Sequence) and not isinstance(value, str) and len(value) == 3:
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value):
            return [float(item) for item in value]
    return None


def _sub(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [x - y for x, y in zip(a, b)]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _length(a: Sequence[float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Sequence[float]) -> Optional[List[float]]:
    size = _length(a)
    return [x / size for x in a] if size > 1e-9 else None


def _cross(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _heading(vector: Sequence[float]) -> float:
    return math.degrees(math.atan2(vector[0], -vector[2]))


def _elevation(vector: Sequence[float]) -> float:
    return math.degrees(math.asin(max(-1.0, min(1.0, vector[1] / _length(vector)))))


def _turn(start: float, end: float) -> float:
    return (end - start + 180.0) % 360.0 - 180.0


def _keys(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    keys = []
    for key in plan.get("keyframes") or []:
        pos, target, time = _point(key.get("pos")), _point(key.get("target")), key.get("t")
        if pos and target and _length(_sub(target, pos)) > 1e-9 and isinstance(time, (int, float)) and not isinstance(time, bool):
            focal = key.get("focal")
            keys.append({"t": float(time), "pos": pos, "target": target, "focal": focal if isinstance(focal, (int, float)) else None})
    return sorted(keys, key=lambda key: key["t"])


def camera_move(plan: Mapping[str, Any]) -> Optional[List[Tuple[str, Optional[float]]]]:
    """The camera move of a 3D shot from its first key to its last, as clauses with their amount in degrees or percent; None without two usable keys."""
    keys = _keys(plan)
    if len(keys) < 2:
        return None
    first, last = keys[0], keys[-1]
    offset = _sub(first["pos"], first["target"])
    distance = _length(offset)
    forward = _unit(_sub(first["target"], first["pos"]))
    if forward is None:
        return None
    right = _unit(_cross(forward, [0.0, 1.0, 0.0])) or [1.0, 0.0, 0.0]
    up = _cross(right, forward)
    moved = _sub(last["pos"], first["pos"])
    clauses: List[Tuple[str, Optional[float]]] = []
    if _length(_sub(last["target"], first["target"])) <= STILL * distance:
        reached = _sub(last["pos"], first["target"])
        arc = _turn(math.degrees(math.atan2(offset[0], offset[2])), math.degrees(math.atan2(reached[0], reached[2])))
        rise = _elevation(reached) - _elevation(offset) if _length(reached) > 1e-9 else 0.0
        ratio = _length(reached) / distance
        if abs(arc) >= MIN_DEGREES:
            clauses.append(("arc_right" if _dot(moved, right) > 0 else "arc_left", abs(arc)))
        if abs(rise) >= MIN_DEGREES:
            clauses.append(("crane_up" if rise > 0 else "crane_down", abs(rise)))
        if abs(1 - ratio) >= MIN_SHIFT:
            clauses.append(("push_in" if ratio < 1 else "pull_out", abs(1 - ratio) * 100))
    elif _length(moved) <= STILL * distance:
        facing = _sub(last["target"], last["pos"])
        pan = _turn(_heading(forward), _heading(facing))
        tilt = _elevation(facing) - _elevation(forward)
        if abs(pan) >= MIN_DEGREES:
            clauses.append(("pan_right" if pan > 0 else "pan_left", abs(pan)))
        if abs(tilt) >= MIN_DEGREES:
            clauses.append(("tilt_up" if tilt > 0 else "tilt_down", abs(tilt)))
    else:
        side, lift, ahead = (_dot(moved, axis) / distance for axis in (right, up, forward))
        if abs(side) >= MIN_SHIFT:
            clauses.append(("truck_right" if side > 0 else "truck_left", None))
        if abs(lift) >= MIN_SHIFT:
            clauses.append(("pedestal_up" if lift > 0 else "pedestal_down", None))
        if abs(ahead) >= MIN_SHIFT:
            clauses.append(("push_in" if ahead > 0 else "pull_out", abs(ahead) * 100))
    if first["focal"] and last["focal"] and abs(last["focal"] / first["focal"] - 1) >= MIN_ZOOM:
        clauses.append(("zoom_in" if last["focal"] > first["focal"] else "zoom_out", None))
    return clauses or [("static", None)]


def _plan3d(doc: Mapping[str, Any], plan_id: Any) -> Optional[Dict[str, Any]]:
    return next((plan for plan in doc.get("plans3d") or [] if plan_id and plan.get("id") == plan_id), None)


def camera_sentences(doc: Mapping[str, Any], guide: SentReference) -> List[str]:
    """What the camera of a shot does along a 3D guide, in the project's prompt language: the move read from its 3D shot, then the order it is played in."""
    text = REFS_TEXT[_language(doc)]
    move = camera_move(_plan3d(doc, (guide.item or {}).get("planId")) or {})
    if move is None:
        described = text["camera_unknown"].format(label=guide.label)
    else:
        clauses = [text[name].format(amount=max(1, round(amount)) if amount is not None else "") for name, amount in move]
        described = text["camera"].format(moves=_listed(clauses, text["and"]))
    return [described, text["forward"].format(label=guide.label)]


def refs_prompt(doc: Mapping[str, Any], clip: Mapping[str, Any], sent: Sequence[SentReference], seconds: float) -> str:
    """The six-section document of MiniMax-H3's reference mode: what each reference is, the task, how much of each is kept, the shot itself with the move of its 3D guides spelled out, its sound and its score. A reference linked to a card of the bible is defined with the card's words; the characters and the place cast in the shot that no sent reference shows are defined by their words alone and cited in the shot, without a retention line."""
    language = _language(doc)
    text = REFS_TEXT[language]
    definitions: List[str] = []
    retention: List[str] = []
    citations: List[str] = []
    defined: Set[str] = set()
    subject = 0
    for entry in sent:
        role = entry.role
        if role in ("character", "setting"):
            subject += 1
            kept = "character" if role == "character" else "setting"
            card = bible.card_for_reference(doc, (entry.item or {}).get("id")) if entry.origin == REFERENCE else None
            if card is not None:
                defined.add(card.id)
                definitions.append(bible.definition(card, subject, language, shown=entry.label))
            else:
                definitions.append(text[f"define_{role}"].format(subject=subject, label=entry.label))
            retention.append(text[f"keep_{kept}"].format(subject=subject))
            citations.append(text[f"cite_{kept}"].format(subject=subject))
        else:
            definitions.append(text[f"define_{role}"].format(label=entry.label))
            retention.append(text[f"keep_{role}"].format(label=entry.label))
    characters, place = bible.cast_of(doc, clip)
    for card in [*characters, *([place] if place is not None else [])]:
        if card.id not in defined:
            subject += 1
            definitions.append(bible.definition(card, subject, language))
            citations.append(text["cite_character" if card.kind == bible.CHARACTERS else "cite_setting"].format(subject=subject))
    guides = [entry for entry in sent if entry.origin == GUIDE]
    seconds_text = _seconds_text(seconds, language)
    summary = (
        text["summary_camera"].format(seconds=seconds_text, videos=_listed([guide.label for guide in guides], text["and"]))
        if guides
        else text["summary"].format(seconds=seconds_text)
    )
    shot = [shot_instruction(doc, clip), *citations]
    for guide in guides:
        shot += camera_sentences(doc, guide)
    if guides:
        shot.append(text["override"])
    style = " ".join(_sentence(line) for line in direction_lines(doc))
    body = " ".join(_sentence(line) for line in shot if line)
    description = " ".join(part for part in (style, f"[Shot 1] {body}".rstrip()) if part)
    sections = [
        ("subject_definitions", " ".join(definitions)),
        ("summary", summary),
        ("retention_analysis", "\n".join(retention)),
        ("detailed_description", description),
        ("overall_soundscape", text["soundscape"]),
        ("non_diegetic_music", "N/A"),
    ]
    return "\n\n".join(f"{name}: {content}" for name, content in sections)


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
    user: User,
    doc: Mapping[str, Any],
    shot_id: str,
    request: Dict[str, Any],
    last_allowed: bool = True,
    segment_id: Optional[str] = None,
    capabilities: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """The request with the shot's first and last frames bound, on segment_id of a director document when given, and the composition mode that results."""
    first, last = shot_frames(doc, shot_id)
    first_media = _frame_media(user, doc, first)
    if first_media is None:
        return request, "t2v"
    placed = {"segment_id": segment_id, "capabilities": capabilities} if segment_id is not None else {"promote": True}
    try:
        request = core_bridge.bind_director_media(request, "first", first_media, **placed)
    except DirectorBindingError:
        logger.warning("[VIDEO-PRODUCER] Could not bind the first frame of shot %s", shot_id, exc_info=True)
        return request, "t2v"
    last_media = _frame_media(user, doc, last) if last_allowed else None
    if last_media is None:
        return request, "i2v"
    try:
        return core_bridge.bind_director_media(request, "last", last_media, **placed), "flf"
    except DirectorBindingError:
        logger.warning("[VIDEO-PRODUCER] Could not bind the last frame of shot %s", shot_id, exc_info=True)
        return request, "i2v"


def shot_guides(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The 3D guides of a shot: the scene3d controls with a 3D shot or a video linked to it, and those linked to no shot that overlap it."""
    start = float(clip.get("start") or 0)
    end = start + float(clip.get("dur") or 0)
    return [
        control
        for control in doc.get("controls") or []
        if control.get("source") == SCENE3D
        and (control.get("planId") or control.get("assetId"))
        and (control.get("shotId") == clip.get("id") or (not control.get("shotId") and _overlap(start, end, control) > 0))
    ]


def fresh_guides(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The 3D guides of a shot that are rendered and not stale."""
    return [control for control in shot_guides(doc, clip) if control.get("assetId") and not control.get("stale")]


def guide_seconds(doc: Mapping[str, Any], guide: Mapping[str, Any]) -> float:
    """How long the video of a 3D guide lasts: its asset's length when known, else the guide's."""
    asset = _asset(doc, guide.get("assetId")) or {}
    length = asset.get("srcDur")
    if isinstance(length, (int, float)) and not isinstance(length, bool) and length > 0:
        return float(length)
    return float(guide.get("dur") or 0)


def _scene_of(doc: Mapping[str, Any], guide: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    scene_id = (_plan3d(doc, guide.get("planId")) or {}).get("sceneId")
    return next((scene for scene in doc.get("scenes") or [] if scene_id and scene.get("id") == scene_id), None)


def scene_picture(user: User, doc: Mapping[str, Any], guide: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The picture the splat scene of a 3D guide was built from: its image asset, or the frame its scene job took from a video; None for an imported scene or a picture no longer readable."""
    scene = _scene_of(doc, guide)
    if scene is None or scene.get("kind") != "splat" or scene.get("status") != "done":
        return None
    asset = _asset(doc, scene.get("sourceAssetId"))
    if asset is None:
        return None
    if asset.get("kind") == "image":
        resolved = _resolve(user, asset)
        if resolved is None or resolved["media_type"] != "image":
            return None
        return {"value": resolved["value"], "media_type": "image", "scene_id": scene["id"]}
    from .scene3d import jobs

    job = jobs.get_job(str(scene["jobId"])) if scene.get("jobId") else None
    value = (job or {}).get("source_value")
    if not value or core_bridge.upload_item(user.id, str(value)) is None:
        return None
    return {"value": str(value), "media_type": "image", "scene_id": scene["id"]}


def reference_media(
    user: User,
    doc: Mapping[str, Any],
    shot_id: str,
    guides: Sequence[Mapping[str, Any]] = (),
    tracks: Sequence[str] = (),
) -> List[SentReference]:
    """What a shot sends as references, within the per-kind limits: its 3D guide videos, the picture the scene of the first one was built from, its own references, the cut of each of its reference tracks (a track: placeholder until the cut is stored), then the global ones it does not exclude; each with its rank among the references of its kind."""
    scoped, shared = [], []
    excluded = excluded_references(doc, shot_id)
    for reference in doc.get("references") or []:
        scope = reference.get("scope")
        if isinstance(scope, Mapping) and scope.get("type") == "shot":
            if scope.get("shotId") == shot_id:
                scoped.append(reference)
        elif reference.get("id") not in excluded:
            shared.append(reference)
    sent: List[SentReference] = []
    counts = {kind: 0 for kind in REFERENCE_LIMITS}

    def add(
        origin: str,
        asset_id: Any,
        item: Optional[Mapping[str, Any]] = None,
        wanted: Optional[str] = None,
        resolved: Optional[Mapping[str, Any]] = None,
    ) -> None:
        resolved = resolved if resolved is not None else _resolve(user, _asset(doc, asset_id))
        if resolved is None or any(entry.value == resolved["value"] for entry in sent):
            return
        kind = resolved["media_type"]
        if (wanted is not None and kind != wanted) or kind not in counts or counts[kind] >= REFERENCE_LIMITS[kind]:
            return
        counts[kind] += 1
        sent.append(SentReference(resolved["value"], kind, counts[kind], origin, dict(item) if item is not None else None))

    for guide in guides:
        add(GUIDE, guide.get("assetId"), guide, "video")
    for entry in [entry for entry in sent if entry.origin == GUIDE]:
        picture = scene_picture(user, doc, entry.item or {})
        if picture is not None:
            add(SCENE_PICTURE, None, {"sceneId": picture["scene_id"], "controlId": (entry.item or {}).get("id")}, "image", picture)
            break
    for reference in scoped:
        add(REFERENCE, reference.get("assetId"), reference)
    for lane_id in tracks:
        add(TRACK, None, {"laneId": lane_id}, "audio", {"value": f"{TRACK_PREFIX}{lane_id}", "media_type": "audio"})
    for reference in shared:
        add(REFERENCE, reference.get("assetId"), reference)
    return sent


def shot_references(user: User, doc: Mapping[str, Any], shot_id: str) -> List[str]:
    """The media values of the shot's own references, then the global ones, within the per-kind limits."""
    return [entry.value for entry in reference_media(user, doc, shot_id)]


def _guide_warnings(doc: Mapping[str, Any], clip: Mapping[str, Any], warnings: List[Dict[str, Any]], refs: bool) -> None:
    guides = shot_guides(doc, clip)
    if guides and not refs:
        warnings.append(
            note("guide_needs_refs", "The shot has a 3D guide video: only a Ref2VA preset follows it.", shot_id=clip["id"])
        )
        return
    for guide in guides:
        if guide.get("stale"):
            warnings.append(
                note("stale_guide", "The 3D guide of the shot is stale: render it again.", shot_id=clip["id"], control_id=guide.get("id"))
            )


def _render_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    rendered = [guide for guide in fresh_guides(doc, clip) if _asset(doc, guide.get("assetId")) is not None]
    if not rendered:
        return None
    guide = rendered[-1]
    return {"shot_id": clip["id"], "control_id": guide.get("id"), "plan_id": guide.get("planId"), "asset_id": guide["assetId"]}


def shot_renders(doc: Mapping[str, Any], clips: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The rendered 3D guide videos the shots would take as they are in the 3D render mode: shot, guide, plan 3D and asset."""
    return [render for render in (_render_of(doc, clip) for clip in clips) if render is not None]


def _render_missing(clip: Mapping[str, Any]) -> Dict[str, Any]:
    return note("render_missing", "The shot has no up-to-date 3D render.", shot_id=clip["id"])


def build_renders(doc: Mapping[str, Any], shot_ids: Sequence[str], quality: str) -> Plans:
    """The 3D render mode: each shot with an up-to-date rendered guide takes its video as it is, without a generation."""
    plans = Plans(preset=None, model=None, quality=quality, profile=profile_of(doc), production=RENDER_3D)
    clips = [clip for clip in (clip_of(doc, shot_id) for shot_id in dict.fromkeys(shot_ids)) if clip is not None]
    if not clips:
        plans.blocks.append(note("no_shots", "Select at least one shot of the project."))
        return plans
    for clip in clips:
        _guide_warnings(doc, clip, plans.warnings, refs=True)
        render = _render_of(doc, clip)
        if render is None:
            plans.warnings.append(_render_missing(clip))
        else:
            plans.renders.append(render)
    if not plans.renders:
        plans.blocks.append(note("no_render", "No selected shot has an up-to-date 3D render."))
    return plans


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
    production: str = AI
    layout_lora: Optional[str] = None
    silent: Mapping[str, Collection[str]] = field(default_factory=dict)
    fields: Dict[str, models.Fields] = field(default_factory=dict)
    cuts: List[TrackCut] = field(default_factory=list)

    def mode_fields(self, mode: str) -> models.Fields:
        if mode not in self.fields:
            self.fields[mode] = models.form_fields(self.preset.id, mode)
        return self.fields[mode]


def _text_only(preset: Preset) -> bool:
    modes = catalog.director_modes(preset.variables)
    return bool(modes) and "i2v" not in modes


def _native_size(context: _Context, fields: models.Fields) -> Optional[str]:
    options = models.resolution_options(fields)
    aspect = aspect_of(context.doc)
    return (
        final_resolution(options, aspect)
        if context.quality == "final"
        else draft_resolution(options, context.draft_setting, aspect)
    ) or (fields.get("resolution") or {}).get("default") or context.draft_setting


def _native_form(fields: models.Fields, document: Dict[str, Any], resolution: Optional[str], fps: float) -> Dict[str, Any]:
    form: Dict[str, Any] = {"seed": -1, "video_director": document}
    if "resolution" in fields:
        form["resolution"] = resolution
    if "fps" in fields:
        form["fps"] = fps
    if "quantity" in fields:
        form["quantity"] = 1
    return form


def project_options(context: _Context, fields: models.Fields, warnings: List[Dict[str, Any]]) -> engine_options.Chosen:
    """The options the project sets for the preset of a plan, a warning naming those that no longer fit their field and are left out."""
    chosen = engine_options.chosen(context.doc, context.preset.id, fields, context.preset.cloud)
    if chosen.invalid:
        warning = note(
            "engine_option_invalid",
            f"Some options of {context.preset.name} no longer fit their field and are left out: {', '.join(chosen.invalid)}.",
            preset_id=context.preset.id,
            fields=list(chosen.invalid),
        )
        if warning not in warnings:
            warnings.append(warning)
    return chosen


def layout_preset(preset: Preset) -> bool:
    """True for a preset that runs the Layout-To-Render IC-LoRA: LTX-2.5, whose director mode takes IC-LoRA."""
    composition = catalog.director_of(preset.variables).get("modes") or {}
    capabilities = composition.get("director") if isinstance(composition, Mapping) else None
    return preset.id in presets.LAYOUT_PRESETS and isinstance(capabilities, Mapping) and bool(capabilities.get("ic_lora"))


def layout_lora() -> Optional[str]:
    """The installed Layout-To-Render IC-LoRA as model:<id>, or None."""
    try:
        model_id = core_bridge.installed_model_for_file(LAYOUT_LORA)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not look up the model file %s", LAYOUT_LORA, exc_info=True)
        return None
    return f"{models.MODEL_REF}{model_id}" if model_id else None


def layout_guide(user: User, doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """The latest up-to-date 3D guide of a shot whose video resolves, with that video."""
    for guide in reversed(fresh_guides(doc, clip)):
        resolved = _resolve(user, _asset(doc, guide.get("assetId")))
        if resolved is not None and resolved["media_type"] == "video":
            return guide, resolved
    return None


def _layout_fps(preset: Preset, fields: models.Fields, asset: Optional[Mapping[str, Any]]) -> float:
    fps = (asset or {}).get("fps")
    if "fps" in fields and isinstance(fps, (int, float)) and not isinstance(fps, bool) and 0 < fps <= MAX_FPS:
        return fps
    return preset.fps


def snapped_frames(frames: int) -> int:
    """The 1 + 8k frame count LTX gives a clip of this many frames: the nearest, the lower one on a tie."""
    return 1 + LTX_FRAME_STEP * max(0, math.ceil((frames - 1) / LTX_FRAME_STEP - 0.5))


def guide_coverage(asset: Optional[Mapping[str, Any]], seconds: float, fps: float) -> Optional[Tuple[int, int]]:
    """How many frames of the shot a 3D guide video conditions and how many the shot has, when the video is too short; None when it covers the shot or its length is unknown."""
    length, rate = (asset or {}).get("srcDur"), (asset or {}).get("fps")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 for value in (length, rate)):
        return None
    covered = (round(length * rate) - 1) // LTX_FRAME_STEP * LTX_FRAME_STEP + 1
    needed = snapped_frames(math.floor(seconds * fps + 0.5))
    return (covered, needed) if covered < needed else None


def distilled_form(fields: models.Fields, resolved: models.ResolvedModels) -> Dict[str, Any]:
    """The Distilled speed profile Lightricks runs Layout-To-Render with (8 steps, CFG 1, euler_ancestral), for the fields the mode has, when the DiT in use is a distilled file and the mode offers that profile; empty otherwise."""
    options = [option.get("value") for option in (fields.get("speed_profile") or {}).get("options") or []]
    if DISTILLED not in options or DISTILLED not in resolved.files.get(models.MODEL_FIELD, "").lower():
        return {}
    return {name: value for name, value in {"speed_profile": DISTILLED, **DISTILLED_RECIPE}.items() if name in fields}


def layout_document(prompt: str, fps: float, seconds: float, resolution: Optional[str], lora: str, video: str) -> Dict[str, Any]:
    """A director document of one segment whose IC-LoRA entry takes a 3D guide video as its reference, the LoRA and the reference both at strength 1: below 1 the reference tokens are no longer clean and LTX-2.5 copies the render instead of following it."""
    document = _document(prompt, fps, seconds, resolution)
    document["mode"] = "director"
    document["segments"][0].update(start=0.0, end=seconds)
    document["ic_lora"] = [
        {
            "id": LAYOUT_ID,
            "lora": {"model": lora, "strength": 1.0},
            "reference": {"path": video, "relative_path": video, "type": "video"},
            "strength": 1.0,
        }
    ]
    return document


def _layout_plan(
    context: _Context, clip: Mapping[str, Any], warnings: List[Dict[str, Any]], guide: Mapping[str, Any], video: Mapping[str, Any]
) -> ShotPlan:
    preset, doc, shot_id = context.preset, context.doc, clip["id"]
    mode = preset.main_mode
    if mode is None or mode not in preset.modes:
        raise DirectorError("no_preset", "The preset has no mode the Video Director can run.")
    fields = context.mode_fields(mode)
    resolution = _native_size(context, fields)
    seconds = _clamped(_wanted_seconds(clip, preset), preset.limits.get("max_duration"), shot_id, warnings)
    asset = _asset(doc, guide.get("assetId"))
    fps = _layout_fps(preset, fields, asset)
    _guide_warnings(doc, clip, warnings, refs=True)
    coverage = guide_coverage(asset, seconds, fps)
    if coverage is not None:
        warnings.append(
            note(
                "layout_guide_short",
                f"The 3D guide video conditions {coverage[0]} of the {coverage[1]} frames of the shot: render it again.",
                shot_id=shot_id,
                control_id=guide.get("id"),
                covered=coverage[0],
                needed=coverage[1],
            )
        )
    engine = bible.family(preset.id, preset.cloud)
    prompt = shot_prompt(doc, clip, engine)
    _bible_warnings(doc, clip, prompt, engine, warnings)
    audio = _shot_mux(context, clip, seconds, warnings)
    document = layout_document(prompt, fps, seconds, resolution, str(context.layout_lora), video["value"])
    request = _request(preset.id, mode, prompt, _native_form(fields, document, resolution, fps))
    first_media = _frame_media(context.user, doc, shot_frames(doc, shot_id)[0])
    bound = False
    if first_media is not None:
        try:
            request = core_bridge.bind_director_media(
                request, "first", first_media, segment_id=SEGMENT_ID, capabilities=catalog.director_of(preset.variables)
            )
            bound = True
        except DirectorBindingError:
            logger.warning("[VIDEO-PRODUCER] Could not bind the first frame of shot %s", shot_id, exc_info=True)
    if not bound:
        warnings.append(
            note("layout_no_frame", "The shot has no first frame: LTX-2.5 keeps the look of its 3D render.", shot_id=shot_id)
        )
    resolved = models.resolve_models(preset.id, mode, "director", fields, (AUDIO_VAE,) if audio is not None and audio.behavior == MUX else ())
    request["form_data"].update(resolved.values)
    request["form_data"].update(distilled_form(fields, resolved))
    chosen = project_options(context, fields, warnings)
    request["form_data"].update(chosen.values)
    return ShotPlan(
        shot_id=shot_id,
        profile=context.profile,
        director_mode="director",
        preset_mode=mode,
        seconds=seconds,
        resolution=resolution,
        fps=fps,
        prompt_text=prompt,
        request=request,
        missing_models=[name for name in resolved.missing if name not in chosen.values],
        guides=[str(guide.get("id"))],
        seed=chosen.seed,
        audio=audio,
        work_scale=engine_options.work_scale(fields, request["form_data"]),
    )


def _native_plan(context: _Context, clip: Mapping[str, Any], warnings: List[Dict[str, Any]]) -> ShotPlan:
    preset, doc, shot_id = context.preset, context.doc, clip["id"]
    layout = context.layout_lora is not None
    guided = layout_guide(context.user, doc, clip) if layout else None
    if guided is not None:
        return _layout_plan(context, clip, warnings, *guided)
    mode = REFS_MODE if context.profile == REF2VA else preset.main_mode
    if mode is None or mode not in preset.modes:
        raise DirectorError("no_preset", "The preset has no mode the Video Director can run.")
    fields = context.mode_fields(mode)
    resolution = _native_size(context, fields)
    seconds = _clamped(_wanted_seconds(clip, preset), preset.limits.get("max_duration"), shot_id, warnings)
    fps = preset.fps
    sent: List[SentReference] = []
    guides: List[Dict[str, Any]] = []
    audio: Optional[ShotAudio] = None
    engine = bible.family(preset.id, preset.cloud)
    if context.profile == REF2VA:
        window = condition_window(doc, clip, seconds)
        tracks = _track_lanes(doc, shot_id, *window, warnings, context.silent.get(shot_id, ()))
        context.cuts.extend(TrackCut(shot_id, lane_id, *window) for lane_id in tracks)
        sent = reference_media(context.user, doc, shot_id, fresh_guides(doc, clip), tracks)
        if not sent:
            raise DirectorError("no_references", "Ref2VA needs at least one reference for this shot.", shot_id=shot_id)
        if all(entry.kind == "audio" for entry in sent):
            raise DirectorError(
                "audio_only_references", "Ref2VA needs a picture or a video next to the sound of this shot.", shot_id=shot_id
            )
        sounds = [entry for entry in sent if entry.kind == "audio"]
        if sounds:
            warnings.append(_audio_note(CONDITION, shot_id))
            audio = ShotAudio(
                behavior=CONDITION,
                start=window[0],
                end=window[1],
                lanes=[str((entry.item or {}).get("laneId")) for entry in sounds if entry.origin == TRACK],
                references=[str((entry.item or {}).get("assetId")) for entry in sounds if entry.origin == REFERENCE],
                sent={str((entry.item or {}).get("assetId")): entry.value for entry in sounds if entry.origin == REFERENCE},
            )
        guides = [entry.item or {} for entry in sent if entry.origin == GUIDE]
        _guide_warnings(doc, clip, warnings, refs=True)
        for guide in guides:
            if guide_seconds(doc, guide) < GUIDE_MIN_SECONDS:
                warnings.append(
                    note(
                        "guide_too_short",
                        f"The 3D guide video of the shot is shorter than the {GUIDE_MIN_SECONDS:g} s MiniMax-H3 reads.",
                        shot_id=shot_id,
                        control_id=guide.get("id"),
                        min=GUIDE_MIN_SECONDS,
                    )
                )
        if context.production == RENDER_3D_AI and not guides:
            warnings.append(_render_missing(clip))
        prompt = refs_prompt(doc, clip, sent, seconds)
    else:
        _guide_warnings(doc, clip, warnings, refs=layout)
        if layout:
            warnings.append(_render_missing(clip))
        prompt = shot_prompt(doc, clip, engine)
        audio = _shot_mux(context, clip, seconds, warnings)
    _bible_warnings(doc, clip, prompt, engine, warnings)
    capabilities = catalog.director_of(preset.variables)
    document = _document(prompt, fps, seconds, resolution)
    mixed = audio is not None and audio.behavior == MUX
    if mixed:
        document = audio_document(document, seconds, fps, capabilities)
    request = _request(preset.id, mode, prompt, _native_form(fields, document, resolution, fps))
    if context.profile == REF2VA:
        request["form_data"]["references"] = [entry.value for entry in sent]
        director_mode = REFS_MODE
    elif _text_only(preset) and shot_frames(doc, shot_id)[0] is not None:
        director_mode = "t2v"
        warnings.append(note("text_only_preset", "The preset generates from text only: the frames of the shot are not used.", shot_id=shot_id))
    else:
        modes = catalog.director_modes(preset.variables)
        request, director_mode = bind_frames(
            context.user,
            doc,
            shot_id,
            request,
            last_allowed=not modes or "flf" in modes,
            segment_id=SEGMENT_ID if mixed else None,
            capabilities=capabilities if mixed else None,
        )
        if director_mode == "t2v" and context.profile == FL2VA:
            warnings.append(note("fl2va_no_frame", "The shot has no first frame: it is generated from its text alone.", shot_id=shot_id))
    resolved = models.resolve_models(preset.id, mode, director_mode, fields, (AUDIO_VAE,) if mixed else ())
    request["form_data"].update(resolved.values)
    chosen = project_options(context, fields, warnings)
    request["form_data"].update(chosen.values)
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
        missing_models=[name for name in resolved.missing if name not in chosen.values],
        guides=[str(guide.get("id")) for guide in guides],
        seed=chosen.seed,
        audio=audio,
        work_scale=engine_options.work_scale(fields, request["form_data"]),
    )


def _shot_mux(context: _Context, clip: Mapping[str, Any], seconds: float, warnings: List[Dict[str, Any]]) -> Optional[ShotAudio]:
    if audio_behavior(context.preset, context.profile) == MUX:
        return mux_audio(context.doc, clip, seconds, warnings)
    return _ignored_audio(context.doc, clip, seconds, warnings)


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
    prompt = shot_prompt(doc, clip, bible.CLOUD)
    _bible_warnings(doc, clip, prompt, bible.CLOUD, warnings)
    form: Dict[str, Any] = {
        "seed": -1,
        "model": f"{models.MODEL_REF}{model['id']}",
        "video_director": _document(prompt, fps, seconds, resolution),
    }
    if "resolution" in fields and resolution is not None:
        form["resolution"] = resolution
    if "aspect_ratio" in fields and aspect is not None:
        form["aspect_ratio"] = str(aspect)
    chosen = project_options(context, fields, warnings)
    form.update(chosen.values)
    request = _request(preset.id, task, prompt, form)
    director_mode = "t2v"
    if first_media is not None:
        request, director_mode = bind_frames(
            context.user, doc, shot_id, request, last_allowed=_has_input(model, LAST_FRAME, IMG2VIDEO)
        )
    if director_mode == "t2v" and context.profile == FL2VA:
        warnings.append(note("fl2va_no_frame", "The shot has no first frame: it is generated from its text alone.", shot_id=shot_id))
    _guide_warnings(doc, clip, warnings, refs=False)
    audio = _ignored_audio(doc, clip, seconds, warnings)
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
        seed=chosen.seed,
        audio=audio,
    )


def _cloud_model(model_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not model_id:
        return None
    try:
        return core_bridge.cloud_model(model_id)
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not read cloud model %s", model_id, exc_info=True)
        return None


def _engine_of(
    doc: Mapping[str, Any], shot_id: str, preset_id: str, quality: str, model_id: Optional[str], profile: Optional[str], production: str
) -> Tuple[str, str, Optional[str], Optional[str]]:
    chosen = shot_engine(doc, shot_id)
    if "preset" in chosen:
        preset_id, model_id = chosen["preset"], chosen["model"]
    if production == AI and "profile" in chosen:
        profile = chosen["profile"]
    return preset_id, chosen.get("quality", quality), model_id, profile


def _merge(plans: Plans, part: Plans, shot_ids: Sequence[str], own: bool) -> None:
    plans.shots.extend(part.shots)
    plans.renders.extend(part.renders)
    plans.track_cuts.extend(part.track_cuts)
    for kind in ("blocks", "warnings"):
        target = getattr(plans, kind)
        for item in getattr(part, kind):
            data = item.get("data") or {}
            if own and kind == "blocks" and "shot_id" not in data:
                item = {**item, "data": {**data, "shot_ids": list(shot_ids)}}
            if item not in target:
                target.append(item)


def build_plans(
    user: User,
    doc: Mapping[str, Any],
    shot_ids: Sequence[str],
    preset_id: str,
    quality: str,
    model_id: Optional[str] = None,
    profile: Optional[str] = None,
    production: str = AI,
    overrides: bool = False,
    silent: Optional[Mapping[str, Collection[str]]] = None,
) -> Plans:
    """The generation request of each shot, with what blocks the run and what the user should know; in the 3D render mode, the rendered guide each shot takes instead; in the 3D render + AI mode, a Ref2VA run on a MiniMax-H3 preset with its refs mode, or on LTX-2.5 a director run whose Layout-To-Render IC-LoRA takes the 3D guide video as its reference. With overrides, each shot runs on the preset, model, profile, quality and seed its clip sets for itself, the shots sharing the same engine planned together, and the blocks of a shot's own engine name its shots, a shot's own seed before the fixed seed of the project's options. The options the project keeps for each preset go into the requests of its shots. Silent maps a shot to the reference tracks found silent under it, which a guided shot leaves out; track_cuts lists the tracks a guided shot would cut, before the limit on sounds."""
    if production == RENDER_3D:
        return build_renders(doc, shot_ids, quality)
    silent = silent or {}
    if not overrides:
        return _build(user, doc, shot_ids, preset_id, quality, model_id, profile, production, silent)
    project = (preset_id, quality, model_id, profile)
    groups: Dict[Tuple[str, str, Optional[str], Optional[str]], List[str]] = {}
    for shot_id in dict.fromkeys(shot_ids):
        if clip_of(doc, shot_id) is not None:
            groups.setdefault(_engine_of(doc, shot_id, *project, production), []).append(shot_id)
    if not groups:
        return _build(user, doc, shot_ids, preset_id, quality, model_id, profile, production, silent)
    parts = [(key, ids, _build(user, doc, ids, *key, production, silent)) for key, ids in groups.items()]
    main = next((part for key, _, part in parts if key == project), parts[0][2])
    plans = Plans(preset=main.preset, model=main.model, quality=quality, profile=main.profile, production=production)
    for key, ids, part in parts:
        _merge(plans, part, ids, own=key != project)
    for plan in plans.shots:
        plan.seed = shot_engine(doc, plan.shot_id).get("seed", plan.seed)
    order = {shot_id: index for index, shot_id in enumerate(dict.fromkeys(shot_ids))}
    plans.shots.sort(key=lambda plan: order[plan.shot_id])
    return plans


def _build(
    user: User,
    doc: Mapping[str, Any],
    shot_ids: Sequence[str],
    preset_id: str,
    quality: str,
    model_id: Optional[str],
    profile: Optional[str],
    production: str,
    silent: Mapping[str, Collection[str]],
) -> Plans:
    if production == RENDER_3D_AI:
        profile = REF2VA
    profile = profile if profile in PROFILES else profile_of(doc)
    preset = find_preset(user, preset_id)
    plans = Plans(preset=preset, model=None, quality=quality, profile=profile, production=production)
    if preset is None:
        plans.blocks.append(note("no_preset", "The preset is not available to you.", preset_id=preset_id))
        return plans
    lora: Optional[str] = None
    if production == RENDER_3D_AI and layout_preset(preset):
        plans.profile = profile = FL2VA
        lora = layout_lora()
        if lora is None:
            plans.blocks.append(
                note(
                    "layout_lora_missing",
                    f"Install the Layout-To-Render IC-LoRA {LAYOUT_LORA} ({LAYOUT_REPO} on Hugging Face) to run LTX-2.5 in the 3D render + AI mode.",
                    file=LAYOUT_LORA,
                    repo=LAYOUT_REPO,
                )
            )
            return plans
    elif production == RENDER_3D_AI and (preset.id not in presets.MINIMAX_H3_PRESETS or REFS_MODE not in preset.modes):
        plans.blocks.append(
            note(
                "refs_preset_needed",
                "The 3D render + AI mode needs a MiniMax-H3 preset with its References mode, or LTX-2.5.",
                preset_id=preset.id,
            )
        )
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
    plans.renders = shot_renders(doc, clips)
    context = _Context(
        user=user,
        doc=doc,
        preset=preset,
        quality=quality,
        profile=profile,
        model=plans.model,
        draft_setting=str(settings.get_setting("draft_resolution")),
        production=production,
        layout_lora=lora,
        silent=silent,
    )
    plans.track_cuts = context.cuts
    missing: List[str] = []
    for clip in clips:
        try:
            plan = (_cloud_plan if preset.cloud else _native_plan)(context, clip, plans.warnings)
        except DirectorError as exc:
            if exc.note() not in plans.blocks:
                plans.blocks.append(exc.note())
            continue
        plan.preset_id, plan.quality, plan.cloud = preset.id, quality, preset.cloud
        plan.backend_id = (plans.model or {}).get("backend_id") if preset.cloud else None
        plans.shots.append(plan)
        missing.extend(name for name in plan.missing_models if name not in missing)
    if missing:
        plans.blocks.append(
            note("missing_models", f"Install a recommended file for: {', '.join(missing)}.", fields=missing)
        )
    cutting = [plan.shot_id for plan in plans.shots if plan.needs_audio]
    if cutting and not core_bridge.find_ffmpeg():
        plans.blocks.append(
            note("audio_ffmpeg_missing", "ffmpeg is not available on this server: the sound of the shots cannot be cut.", shot_ids=cutting)
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
