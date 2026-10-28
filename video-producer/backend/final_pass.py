from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import director, estimate, generation, limits, takes, upscalers
from .core_bridge import User
from .director import ShotPlan, note
from .generation import Blocked, TakeError

AUTO = upscalers.AUTO

MAX_TAKES = 200


class PassError(ValueError):
    """A body the final pass routes refuse."""


@dataclass(frozen=True)
class Order:
    takes: List[str]
    method: str
    target: str
    upscaler: str = AUTO
    rtx_source: str = upscalers.DEFAULT_RTX_SOURCE


@dataclass
class Planned:
    source: Dict[str, Any]
    plan: ShotPlan
    preset_id: str
    native: bool
    minutes: float = 0.0


@dataclass
class Evaluation:
    order: Order
    planned: List[Planned]
    payload: Dict[str, Any]
    reserve: bool = False

    @property
    def blocked(self) -> bool:
        return bool(self.payload["blocks"])


def parse_order(body: Any) -> Order:
    """The takes, method, target, upscaler and kind of source for RTX a body asks for; PassError for a malformed one."""
    if not isinstance(body, dict):
        raise PassError("The request body must be a JSON object.")
    ids = body.get("takes")
    if not isinstance(ids, list) or not ids or not all(isinstance(take_id, str) and take_id for take_id in ids):
        raise PassError("takes must be a non-empty list of take ids.")
    if len(set(ids)) > MAX_TAKES:
        raise PassError(f"takes holds at most {MAX_TAKES} take ids.")
    method = body.get("method")
    if method not in generation.METHODS:
        raise PassError(f"method must be one of: {', '.join(generation.METHODS)}.")
    target = body.get("target")
    if target not in upscalers.TARGETS:
        raise PassError(f"target must be one of: {', '.join(upscalers.TARGETS)}.")
    upscaler = body.get("upscaler", AUTO)
    if upscaler not in upscalers.CHOICES:
        raise PassError(f"upscaler must be one of: {', '.join(upscalers.CHOICES)}.")
    rtx_source = body.get("rtx_source", upscalers.DEFAULT_RTX_SOURCE)
    if rtx_source not in upscalers.RTX_SOURCES:
        raise PassError(f"rtx_source must be one of: {', '.join(upscalers.RTX_SOURCES)}.")
    return Order(takes=list(dict.fromkeys(ids)), method=method, target=target, upscaler=upscaler, rtx_source=rtx_source)


def _add(blocks: List[Dict[str, Any]], block: Mapping[str, Any], shot_id: str) -> None:
    data = {key: value for key, value in (block.get("data") or {}).items() if key not in ("shot_id", "shot_ids")}
    for item in blocks:
        same = {key: value for key, value in item["data"].items() if key not in ("shot_ids", "fields")}
        mine = {key: value for key, value in data.items() if key != "fields"}
        if item["code"] == block["code"] and same == mine:
            shots = item["data"]["shot_ids"]
            if shot_id not in shots:
                shots.append(shot_id)
            if "fields" in data:
                item["data"]["fields"] = list(dict.fromkeys([*item["data"].get("fields", []), *data["fields"]]))
            return
    blocks.append({"code": block["code"], "message": block["message"], "data": {**data, "shot_ids": [shot_id]}})


def _running(source: Mapping[str, Any], project_takes: List[Dict[str, Any]]) -> bool:
    return any(
        take["parent_take_id"] == source["id"] and take["quality"] == "final" and take["status"] in takes.ACTIVE for take in project_takes
    )


async def _plan_all(owner: User, project: Mapping[str, Any], order: Order, sources: List[Dict[str, Any]]) -> Tuple[List[Planned], List[Dict[str, Any]]]:
    planned: List[Planned] = []
    blocks: List[Dict[str, Any]] = []
    project_takes = takes.list_takes(project["id"])
    for source in sources:
        shot_id = str(source["shot_id"])
        if _running(source, project_takes):
            _add(blocks, note("final_running", "A final take of this take is already queued or running."), shot_id)
            continue
        try:
            plan, preset_id, native = await generation.final_plan(owner, project, source, order.method, order.target, order.upscaler, order.rtx_source)
        except TakeError as exc:
            _add(blocks, note(exc.code, exc.message), shot_id)
            continue
        except Blocked as exc:
            for block in exc.blocks:
                _add(blocks, block, shot_id)
            continue
        if plan.missing_models:
            _add(blocks, generation.missing_block(plan.missing_models), shot_id)
            continue
        planned.append(Planned(source=source, plan=plan, preset_id=preset_id, native=native))
    return planned, blocks


async def _vram(owner: User, planned: List[Planned]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    firsts: Dict[str, ShotPlan] = {}
    for item in planned:
        if item.native:
            firsts.setdefault(item.preset_id, item.plan)
    if not firsts:
        return estimate.unknown_vram(), []
    results = [await estimate.plan_vram(owner, plan) for plan in firsts.values()]
    vram = max(results, key=lambda result: (result[0]["streams"], result[0]["estimate_gb"] or 0.0))[0]
    warnings: List[Dict[str, Any]] = []
    for _, found in results:
        warnings.extend(item for item in found if item not in warnings)
    return vram, warnings


def _quota(status: Mapping[str, Any], needed: float, applies: bool) -> Dict[str, Any]:
    limited = generation.reserves(status)
    remaining = status.get("remaining")
    return {
        "limit": status.get("limit"),
        "used": status.get("used"),
        "remaining": remaining,
        "exempt": bool(status.get("exempt")),
        "needed_minutes": round(needed, 2),
        "applies": applies,
        "blocks": bool(applies and limited and remaining is not None and needed > float(remaining) + 1e-9),
    }


def _shot(item: Planned, method: str) -> Dict[str, Any]:
    plan = item.plan
    return {
        "shot_id": plan.shot_id,
        "take_id": item.source["id"],
        "method": method,
        "preset_id": item.preset_id,
        "mode": plan.preset_mode,
        "resolution": plan.resolution,
        "seconds": plan.seconds,
        "minutes": item.minutes,
        "sound": plan.audio is not None and plan.audio.behavior == director.MUX,
    }


async def evaluate(owner: User, project: Mapping[str, Any], order: Order, sources: List[Dict[str, Any]]) -> Evaluation:
    """What making these takes final would need in memory, time and GPU minutes, and what blocks it, shot by shot: each final planned as a single final take would be, its minutes measured on the backend of its source; the blocks name their shots."""
    planned, blocks = await _plan_all(owner, project, order, sources)
    vram, warnings = await _vram(owner, planned)
    work: Optional[float] = 0.0
    samples = 0
    for index, item in enumerate(planned):
        plan = item.plan
        backend_id = item.source.get("backend_id") or vram.get("backend_id")
        ratio, count = estimate.calibrated_ratio(item.preset_id, backend_id, plan.resolution) if item.native else (None, 0)
        if index == 0:
            samples = count
        item.minutes = estimate.take_minutes(plan.seconds * plan.work_scale, ratio) if item.native else 0.0
        work = None if ratio is None or work is None else work + ratio * plan.seconds * plan.work_scale
    seconds = round(work, 1) if work is not None and planned else None
    native = [item for item in planned if item.native]
    status = limits.gpu_minutes_status(owner.id)
    quota = _quota(status, sum(item.minutes for item in native), bool(native))
    if quota["blocks"]:
        blocks.append(estimate.quota_block(quota))
    if planned and seconds is None:
        warnings.append(note("time_unknown", "No take of this preset was measured at this resolution yet."))
    payload = {
        "shots": [_shot(item, order.method) for item in planned],
        "vram": vram,
        "time": {"seconds": seconds, "samples": samples},
        "quota": quota,
        "blocks": blocks,
        "warnings": warnings,
    }
    return Evaluation(order=order, planned=planned, payload=payload, reserve=generation.reserves(status))


async def start(owner: User, project: Mapping[str, Any], evaluation: Evaluation) -> List[Dict[str, Any]]:
    """Create the final take of every planned take, the sound of each cut and its first frame bound first, then hand what fits to the core; Blocked when anything blocks, nothing created then."""
    if evaluation.blocked:
        raise Blocked(evaluation.payload["blocks"])
    planned = evaluation.planned
    await generation.with_sound(owner, project, [item.plan for item in planned])
    await generation.with_first(owner, [(item.source, item.plan) for item in planned])
    created = [
        generation.create_final(
            owner,
            project,
            item.source,
            evaluation.order.method,
            item.plan,
            item.preset_id,
            item.minutes if evaluation.reserve and item.native else 0.0,
        )
        for item in planned
    ]
    await generation.pump(owner)
    return [takes.get_take(take["id"]) for take in created]
