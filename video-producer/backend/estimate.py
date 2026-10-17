import logging
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from . import core_bridge, director, limits, takes
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
    preset_id: str
    model_id: Optional[str] = None
    label: Optional[str] = None


@dataclass
class Evaluation:
    plans: Plans
    variants: int
    minutes: Dict[str, float]
    payload: Dict[str, Any]

    @property
    def blocked(self) -> bool:
        return bool(self.payload["blocks"])


def parse_order(body: Any) -> Order:
    """The shots, quality, variants, preset and model a body asks for; OrderError for a malformed one."""
    if not isinstance(body, dict):
        raise OrderError("The request body must be a JSON object.")
    shots = body.get("shots")
    if not isinstance(shots, list) or not all(isinstance(shot, str) and shot for shot in shots):
        raise OrderError("shots must be a list of shot ids.")
    quality = body.get("quality")
    if quality not in QUALITIES:
        raise OrderError(f"quality must be one of: {', '.join(QUALITIES)}.")
    variants = body.get("variants")
    if not isinstance(variants, int) or isinstance(variants, bool) or not 1 <= variants <= MAX_VARIANTS:
        raise OrderError(f"variants must be an integer from 1 to {MAX_VARIANTS}.")
    preset_id = body.get("preset_id")
    if not isinstance(preset_id, str) or not preset_id:
        raise OrderError("preset_id must be a preset id.")
    model_id = body.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        raise OrderError("model_id must be a model id or null.")
    label = body.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > LABEL_LIMIT):
        raise OrderError(f"label must be a string of at most {LABEL_LIMIT} characters.")
    return Order(shots=list(shots), quality=quality, variants=variants, preset_id=preset_id, model_id=model_id, label=label)


def calibrated_ratio(preset_id: str, backend_id: Optional[str], resolution: Optional[str]) -> Tuple[Optional[float], int]:
    """Seconds of work per second of video measured for a preset at a resolution, and how many measures back it."""
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
    """The GPU minutes one take of a plan reserves."""
    ratio, _ = calibrated_ratio(preset_id, backend_id, plan.resolution)
    return take_minutes(plan.seconds, ratio)


def _unknown_vram(backend_id: Optional[str] = None) -> Dict[str, Any]:
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


async def _vram(owner: User, plans: Plans) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if plans.preset is None or plans.preset.cloud or not plans.shots:
        return _unknown_vram(), []
    if any(block["code"] == "missing_models" for block in plans.blocks):
        return _unknown_vram(), []
    try:
        result = await core_bridge.preview_memory(owner, plans.shots[0].request_for())
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not preview the memory of a take", exc_info=True)
        return _unknown_vram(), [note("vram_unknown", "The memory a take needs could not be estimated.")]
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


def _quota(owner: User, plans: Plans, minutes: Mapping[str, float], variants: int) -> Dict[str, Any]:
    status = limits.gpu_minutes_status(owner.id)
    applies = plans.preset is not None and not plans.preset.cloud
    needed = sum(minutes.values()) * variants if applies else 0.0
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


def _cost(caller: User, plans: Plans, variants: int) -> Optional[Dict[str, Any]]:
    if getattr(caller, "account_type", None) != AccountType.ADMIN:
        return None
    if plans.preset is None or not plans.preset.cloud or plans.model is None or not plans.shots:
        return None
    shots = [{"task": plan.cloud_task, "params": dict(plan.cloud_params)} for plan in plans.shots for _ in range(variants)]
    try:
        result = core_bridge.estimate_cloud_cost(caller, plans.model["id"], shots)
    except PermissionError:
        return None
    except ValueError as exc:
        return {"total_usd": None, "known": False, "message": str(exc)}
    except Exception:
        logger.warning("[VIDEO-PRODUCER] Could not estimate the cost of a cloud run", exc_info=True)
        return {"total_usd": None, "known": False, "message": "The cost could not be estimated."}
    return {"total_usd": result.get("total_usd"), "known": bool(result.get("known")), "message": result.get("message")}


async def evaluate(caller: User, owner: User, doc: Mapping[str, Any], order: Order) -> Evaluation:
    """What the takes an order asks for would need and cost, and what blocks them, in the contract's shape."""
    plans = director.build_plans(owner, doc, order.shots, order.preset_id, order.quality, order.model_id)
    vram, vram_warnings = await _vram(owner, plans)
    backend_id = vram.get("backend_id") or (plans.model or {}).get("backend_id")
    minutes: Dict[str, float] = {}
    work: Optional[float] = 0.0
    samples = 0
    for index, plan in enumerate(plans.shots):
        ratio, count = calibrated_ratio(plans.preset.id, backend_id, plan.resolution)
        if index == 0:
            samples = count
        minutes[plan.shot_id] = take_minutes(plan.seconds, ratio)
        work = None if ratio is None or work is None else work + ratio * plan.seconds * order.variants
    seconds = round(work, 1) if work is not None and plans.shots else None
    quota = _quota(owner, plans, minutes, order.variants)
    blocks = list(plans.blocks) + ([quota_block(quota)] if quota["blocks"] else [])
    warnings = list(plans.warnings) + vram_warnings
    if plans.shots and seconds is None:
        warnings.append(note("time_unknown", "No take of this preset was measured at this resolution yet."))
    payload = {
        "shots": [plan.summary() for plan in plans.shots],
        "vram": vram,
        "time": {"seconds": seconds, "samples": samples},
        "quota": quota,
        "cost": _cost(caller, plans, order.variants),
        "blocks": blocks,
        "warnings": warnings,
    }
    return Evaluation(plans=plans, variants=order.variants, minutes=minutes, payload=payload)
