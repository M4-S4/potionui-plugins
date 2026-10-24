import logging
import statistics
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import core_bridge, director, limits, soundtrack, takes
from .core_bridge import AccountType, User
from .director import Plans, ShotPlan, note

logger = logging.getLogger("plugins.video-producer")

QUALITIES = ("draft", "final")

MAX_VARIANTS = 16

LABEL_LIMIT = 200

FLOOR_FACTOR = 10.0


class OrderError(ValueError):
    """A body the estimate and generate routes refuse."""


@dataclass(frozen=True)
class Order:
    shots: List[str]
    quality: str
    variants: int
    preset_id: Optional[str]
    model_id: Optional[str] = None
    label: Optional[str] = None
    production: str = director.AI
    shot_variants: Mapping[str, int] = field(default_factory=dict)

    def count(self, shot_id: str) -> int:
        """How many takes the order asks for this shot: its own count, else the order's."""
        return self.shot_variants.get(shot_id, self.variants)


@dataclass
class Evaluation:
    plans: Plans
    variants: int
    minutes: Dict[str, float]
    payload: Dict[str, Any]
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return bool(self.payload["blocks"])

    def count(self, shot_id: str) -> int:
        """How many takes to create for this shot."""
        return self.counts.get(shot_id, self.variants)


def _variant_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_VARIANTS


def parse_order(body: Any) -> Order:
    """The shots, quality, variants (one count for all, and optionally one per shot), preset, model and production mode a body asks for; OrderError for a malformed one. The 3D render mode needs no preset."""
    if not isinstance(body, dict):
        raise OrderError("The request body must be a JSON object.")
    shots = body.get("shots")
    if not isinstance(shots, list) or not all(isinstance(shot, str) and shot for shot in shots):
        raise OrderError("shots must be a list of shot ids.")
    quality = body.get("quality")
    if quality not in QUALITIES:
        raise OrderError(f"quality must be one of: {', '.join(QUALITIES)}.")
    variants = body.get("variants")
    if not _variant_count(variants):
        raise OrderError(f"variants must be an integer from 1 to {MAX_VARIANTS}.")
    shot_variants = body.get("shot_variants") or {}
    if not isinstance(shot_variants, dict) or not all(
        isinstance(shot, str) and shot and _variant_count(count) for shot, count in shot_variants.items()
    ):
        raise OrderError(f"shot_variants must map shot ids to integers from 1 to {MAX_VARIANTS}.")
    production = body.get("production", director.AI)
    if production not in director.PRODUCTIONS:
        raise OrderError(f"production must be one of: {', '.join(director.PRODUCTIONS)}.")
    preset_id = body.get("preset_id")
    rendered = production == director.RENDER_3D and preset_id is None
    if not rendered and (not isinstance(preset_id, str) or not preset_id):
        raise OrderError("preset_id must be a preset id.")
    model_id = body.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        raise OrderError("model_id must be a model id or null.")
    label = body.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > LABEL_LIMIT):
        raise OrderError(f"label must be a string of at most {LABEL_LIMIT} characters.")
    return Order(
        shots=list(shots),
        quality=quality,
        variants=variants,
        preset_id=preset_id,
        model_id=model_id,
        label=label,
        production=production,
        shot_variants={shot: count for shot, count in shot_variants.items() if shot in shots},
    )


def calibrated_ratio(preset_id: str, backend_id: Optional[str], resolution: Optional[str]) -> Tuple[Optional[float], int]:
    """Seconds of work per second of video measured for a preset at a resolution at the steps of its defaults, and how many measures back it."""
    if not resolution:
        return None, 0
    rows = [(seconds, duration_ms) for seconds, duration_ms in takes.calibration(preset_id, backend_id, resolution) if seconds > 0]
    if not rows:
        return None, 0
    return statistics.median(duration_ms / 1000 / seconds for seconds, duration_ms in rows), len(rows)


def take_minutes(seconds: float, ratio: Optional[float]) -> float:
    """The GPU minutes a take reserves: the calibrated time, else ten seconds of work per second of video."""
    work = ratio * seconds if ratio is not None else seconds * FLOOR_FACTOR
    return round(work / 60, 3)


def plan_minutes(plan: ShotPlan, preset_id: str, backend_id: Optional[str] = None) -> float:
    """The GPU minutes one take of a plan reserves, longer or shorter with the steps its options ask for."""
    ratio, _ = calibrated_ratio(preset_id, backend_id, plan.resolution)
    return take_minutes(plan.seconds * plan.work_scale, ratio)


def unknown_vram(backend_id: Optional[str] = None) -> Dict[str, Any]:
    """The memory estimate of a run that could not be previewed."""
    return {
        "estimate_gb": None,
        "free_gb": None,
        "total_gb": None,
        "budget_gb": None,
        "streams": False,
        "unknown": True,
        "backend_id": backend_id,
    }


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


async def plan_vram(owner: User, plan: ShotPlan) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The memory one take of a plan needs against what its backend offers, with the warnings to show."""
    try:
        result = await core_bridge.preview_memory(owner, plan.request_for())
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not preview the memory of a take", exc_info=True)
        return unknown_vram(), [note("vram_unknown", "The memory a take needs could not be estimated.")]
    estimate = _number((result.get("estimate") or {}).get("checkpoint_estimate_gb"))
    device = result.get("device") or {}
    free, total = _number(device.get("free_gb")), _number(device.get("total_gb"))
    budget = _number((result.get("budget") or {}).get("configured_gb"))
    capacities = [capacity for capacity in (free, budget, total) if capacity is not None]
    unknown = estimate is None or not capacities
    streams = not unknown and any(estimate > capacity for capacity in capacities)
    vram = {
        "estimate_gb": estimate,
        "free_gb": free,
        "total_gb": total,
        "budget_gb": budget,
        "streams": streams,
        "unknown": unknown,
        "backend_id": (result.get("backend") or {}).get("id"),
    }
    if unknown:
        return vram, [note("vram_unknown", "The memory a take needs could not be estimated.")]
    if streams:
        return vram, [
            note(
                "vram_stream",
                "The model does not fit in the GPU memory it may use: it will stream through host RAM, slower.",
                estimate_gb=estimate,
                free_gb=free,
                budget_gb=budget,
                total_gb=total,
            )
        ]
    return vram, []


async def _vram(owner: User, plans: Plans) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The memory of the most demanding local preset of the run, previewed once per preset, with the warnings of every preset."""
    if any(block["code"] == "missing_models" for block in plans.blocks):
        return unknown_vram(), []
    firsts: Dict[str, ShotPlan] = {}
    for plan in plans.shots:
        if not plan.cloud:
            firsts.setdefault(plan.preset_id, plan)
    if not firsts:
        return unknown_vram(), []
    results = [await plan_vram(owner, plan) for plan in firsts.values()]
    vram = max(results, key=lambda result: (result[0]["streams"], result[0]["estimate_gb"] or 0.0))[0]
    warnings: List[Dict[str, Any]] = []
    for _, found in results:
        warnings.extend(item for item in found if item not in warnings)
    return vram, warnings


def _quota(owner: User, plans: Plans, minutes: Mapping[str, float], counts: Mapping[str, int]) -> Dict[str, Any]:
    status = limits.gpu_minutes_status(owner.id)
    native = [plan for plan in plans.shots if not plan.cloud]
    applies = bool(native) or (not plans.shots and plans.preset is not None and not plans.preset.cloud)
    needed = sum(minutes.get(plan.shot_id, 0.0) * counts.get(plan.shot_id, 1) for plan in native)
    limited = status.get("limit") is not None and not status.get("exempt")
    remaining = status.get("remaining")
    blocks = bool(applies and limited and remaining is not None and needed > float(remaining) + 1e-9)
    return {
        "limit": status.get("limit"),
        "used": status.get("used"),
        "remaining": remaining,
        "exempt": bool(status.get("exempt")),
        "needed_minutes": round(needed, 2),
        "applies": applies,
        "blocks": blocks,
    }


def quota_block(quota: Mapping[str, Any]) -> Dict[str, Any]:
    """The block of a quota the takes would exceed."""
    return note(
        "quota_exceeded",
        f"These takes need {quota['needed_minutes']:g} GPU minutes; {float(quota['remaining'] or 0):g} remain this month.",
        needed_minutes=quota["needed_minutes"],
        remaining=quota["remaining"],
    )


def model_cost(caller: User, model_id: str, shots: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What some runs on a cloud model cost, for an administrator; None for anyone else."""
    try:
        result = core_bridge.estimate_cloud_cost(caller, model_id, shots)
    except PermissionError:
        return None
    except ValueError as exc:
        return {"total_usd": None, "known": False, "message": str(exc)}
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not estimate the cost of a cloud run", exc_info=True)
        return {"total_usd": None, "known": False, "message": "The cost could not be estimated."}
    return {"total_usd": result.get("total_usd"), "known": bool(result.get("known")), "message": result.get("message")}


def _total(costs: List[Dict[str, Any]]) -> Optional[str]:
    try:
        return str(sum((Decimal(str(cost["total_usd"])) for cost in costs), Decimal(0)))
    except (InvalidOperation, TypeError):
        return None


def _cost(caller: User, plans: Plans, counts: Mapping[str, int]) -> Optional[Dict[str, Any]]:
    """What the cloud shots of the run cost an administrator, summed over the cloud models they run on."""
    if getattr(caller, "account_type", None) != AccountType.ADMIN:
        return None
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for plan in plans.shots:
        if plan.cloud and plan.model_id:
            by_model.setdefault(plan.model_id, []).extend(
                {"task": plan.cloud_task, "params": dict(plan.cloud_params)} for _ in range(counts.get(plan.shot_id, 1))
            )
    costs = [cost for cost in (model_cost(caller, model_id, shots) for model_id, shots in by_model.items()) if cost is not None]
    if not costs:
        return None
    if len(costs) == 1:
        return costs[0]
    known = all(cost["known"] and cost["total_usd"] is not None for cost in costs)
    message = next((cost["message"] for cost in costs if cost["message"]), None)
    return {"total_usd": _total(costs) if known else None, "known": known, "message": message}


async def evaluate(caller: User, owner: User, doc: Mapping[str, Any], order: Order, project_id: str = "") -> Evaluation:
    """What the takes an order asks for would need and cost, and what blocks them, in the contract's shape, the time and the minutes following the steps the options of each shot ask for; the reference tracks a guided shot would send silent are left out."""
    plans = await soundtrack.heard_plans(
        owner, project_id, doc, order.shots, order.preset_id, order.quality, order.model_id, production=order.production, overrides=True
    )
    vram, vram_warnings = await _vram(owner, plans)
    counts = {plan.shot_id: order.count(plan.shot_id) for plan in plans.shots}
    minutes: Dict[str, float] = {}
    work: Optional[float] = 0.0
    samples = 0
    for index, plan in enumerate(plans.shots):
        ratio, count = calibrated_ratio(plan.preset_id, plan.backend_id or vram.get("backend_id"), plan.resolution)
        if index == 0:
            samples = count
        minutes[plan.shot_id] = take_minutes(plan.seconds * plan.work_scale, ratio)
        work = None if ratio is None or work is None else work + ratio * plan.seconds * plan.work_scale * counts[plan.shot_id]
    seconds = round(work, 1) if work is not None and plans.shots else None
    quota = _quota(owner, plans, minutes, counts)
    blocks = list(plans.blocks) + ([quota_block(quota)] if quota["blocks"] else [])
    warnings = list(plans.warnings) + vram_warnings
    if plans.shots and seconds is None:
        warnings.append(note("time_unknown", "No take of this preset was measured at this resolution yet."))
    payload = {
        "production": plans.production,
        "shots": [plan.summary() for plan in plans.shots],
        "renders": list(plans.renders),
        "vram": vram,
        "time": {"seconds": seconds, "samples": samples},
        "quota": quota,
        "cost": _cost(caller, plans, counts),
        "blocks": blocks,
        "warnings": warnings,
    }
    return Evaluation(plans=plans, variants=order.variants, minutes=minutes, payload=payload, counts=counts)
