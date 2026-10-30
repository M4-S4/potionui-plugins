import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import chain, core_bridge, director, projects, takes
from .chain import ChainError
from .core_bridge import LimitExceeded, MediaRefError
from .exports.common import asset_of

logger = logging.getLogger("plugins.video-producer")

BATCH = "batch"
TAKE = "take"
MEDIA = "media"
STILL = "still"

WAITING = "waiting"
TAKEN = "taken"

RENDER = "render"

OWN = "own"
CHAINED = "chained"

Fail = Callable[[Mapping[str, Any], str, str], bool]


@dataclass
class Wait:
    shot_id: str
    previous: str
    source: str
    takes: List[Dict[str, Any]] = field(default_factory=list)
    asset_id: Optional[str] = None

    @property
    def chain(self) -> director.Chain:
        return director.Chain(self.previous, self.asset_id if self.source == STILL else None)


def chained(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> bool:
    """True when a shot starts from the last image of the previous one: its own firstFromPrevious, else the project's, on unless false."""
    own = clip.get("firstFromPrevious")
    return own if isinstance(own, bool) else doc.get("firstFromPrevious") is not False


def placed_media(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The still or the video placed on a shot that a last image can be taken from, as the page reads it."""
    asset = asset_of(doc, clip.get("assetId"))
    if asset is None or not asset.get("src"):
        return None
    if asset.get("kind") == "image":
        return asset
    return asset if asset.get("kind") == "video" and (asset.get("origin") or asset.get("generated")) else None


def first_kind(doc: Mapping[str, Any], shot_id: str) -> Optional[str]:
    """What opens a shot: CHAINED for a last image taken from a previous shot, OWN for an image chosen otherwise, None for nothing."""
    first, _ = director.shot_frames(doc, shot_id)
    asset = asset_of(doc, first.get("assetId")) if first is not None else None
    if asset is None:
        return None
    frame_of = asset.get("frameOf")
    return CHAINED if isinstance(frame_of, Mapping) else OWN


def waits(project_id: str, doc: Mapping[str, Any], shot_ids: Sequence[str]) -> Dict[str, Wait]:
    """The shots of an order that start from the last image of the previous shot and have to wait for it."""
    clips = doc.get("clips") or []
    batch = set(shot_ids)
    active: Optional[List[Dict[str, Any]]] = None
    found: Dict[str, Wait] = {}
    for index, clip in enumerate(clips):
        if index == 0 or clip.get("id") not in batch or not chained(doc, clip):
            continue
        previous = clips[index - 1]
        opening = first_kind(doc, clip["id"])
        if opening == OWN or (opening == CHAINED and previous["id"] not in batch):
            continue
        if previous["id"] in batch:
            found[clip["id"]] = Wait(clip["id"], previous["id"], BATCH)
            continue
        media = placed_media(doc, previous)
        if media is not None:
            source = STILL if media.get("kind") == "image" else MEDIA
            found[clip["id"]] = Wait(clip["id"], previous["id"], source, asset_id=media["id"])
            continue
        if active is None:
            active = [take for take in takes.list_active(project_id) if take.get("kind") == RENDER] if project_id else []
        theirs = [take for take in active if take["shot_id"] == previous["id"]]
        if theirs:
            found[clip["id"]] = Wait(clip["id"], previous["id"], TAKE, takes=theirs)
    return found


def chain_map(found: Mapping[str, Wait]) -> Dict[str, director.Chain]:
    """What build_plans binds for each waiting shot."""
    return {shot_id: wait.chain for shot_id, wait in found.items()}


def record(wait: Optional[Wait], letter: str, created: Sequence[Mapping[str, Any]], batch: str) -> Optional[Dict[str, Any]]:
    """What a new take of a waiting shot stores: the previous shot, the take it waits for (the one of the same letter among the previous shot's new takes, or its takes on their way, else the first of them), and its state; a still is taken at once and a placed video when the tracker comes by."""
    if wait is None:
        return None
    base = {"previous": wait.previous, "batch": batch, "after": None, "source": None, "frame": None}
    if wait.source == STILL:
        return {**base, "state": TAKEN, "source": {"shotId": wait.previous, "takeId": None, "assetId": wait.asset_id, "at": None}}
    pool = [take for take in created if take["shot_id"] == wait.previous] if wait.source == BATCH else wait.takes
    if wait.source == MEDIA or not pool:
        return {**base, "state": WAITING}
    after = next((take for take in pool if take.get("variant") == letter), pool[0])
    return {**base, "after": after["id"], "state": WAITING}


def swap(value: Any, stand_in: str, stored: str) -> Any:
    """A copy of a request with every string equal to stand_in replaced by stored."""
    if isinstance(value, str):
        return stored if value == stand_in else value
    if isinstance(value, Mapping):
        return {key: swap(item, stand_in, stored) for key, item in value.items()}
    if isinstance(value, list):
        return [swap(item, stand_in, stored) for item in value]
    return value


def _reason(after: Optional[Mapping[str, Any]]) -> Optional[Tuple[str, str]]:
    if after is None:
        return "previous_take_gone", "The take of the previous shot this take was to start from was deleted."
    if after["status"] == "failed":
        return "previous_take_failed", "The take of the previous shot this take was to start from failed: retry it, then retry this one."
    if after["status"] == "cancelled":
        return "previous_take_cancelled", "The take of the previous shot this take was to start from was cancelled: start it again, then retry this one."
    return None


async def _frame(owner: Any, project: Mapping[str, Any], wait: Mapping[str, Any], after: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if after is not None:
        return await chain.take_end_frame(owner, project, wait["previous"], after)
    return await chain.end_frame(owner, project, wait["previous"])


async def take_frame(take: Mapping[str, Any], fail: Fail) -> bool:
    """Give a waiting take the last image of the previous shot once there is one, or fail it with a reason; True when it stops waiting."""
    wait = take.get("chain") or {}
    after = None
    if wait.get("after"):
        after = takes.get_take(wait["after"])
        if after is not None and after["status"] in takes.ACTIVE:
            return False
        reason = _reason(after) if after is None or after["status"] != "done" else None
        if reason is not None:
            return fail(take, *reason)
    owner = core_bridge.get_user(take.get("user_id")) if take.get("user_id") else None
    project = projects.get_project(take["project_id"])
    if owner is None or project is None:
        return False
    try:
        frame = await _frame(owner, project, wait, after)
    except ChainError as exc:
        return fail(take, "chain_frame_failed", exc.message)
    except (MediaRefError, LimitExceeded) as exc:
        return fail(take, "chain_frame_failed", str(exc) or "The last image of the previous shot could not be stored.")
    media = chain.media_of(owner.id, frame)
    if media is None:
        return fail(take, "chain_frame_failed", "The last image of the previous shot was stored but its library item cannot be found.")
    request = swap(copy.deepcopy(take.get("request") or {}), director.chain_value(wait["previous"]), frame["value"])
    taken = {**wait, "state": TAKEN, "source": frame["source"], "frame": media}
    return takes.take_frame(take["id"], taken, request)


async def take_frames(fail: Fail) -> int:
    """One round over the takes that wait for the last image of the previous shot; how many joined the queue or failed."""
    moved = 0
    for take in takes.chain_waiting():
        try:
            moved += int(await take_frame(take, fail))
        except Exception:
            logger.warning("[VIDEO-PRODUCER] Could not give take %s the last image of the previous shot", take.get("id"), exc_info=True)
    return moved
