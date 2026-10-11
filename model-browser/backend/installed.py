"""Which files are installed, as one user sees it (PLAN.md §7.3): the one rule behind
`POST /installed` and the `installed` badge of `GET /{source}/search`, so both answer the same way.

A file is installed for a user when the core has indexed a model with its SHA256, that
model's file is still on the disk (`is_available`), and, for a non-admin, the model is
visible to them (assigned directly or through a group: `core_bridge.visible_model_ids`).
An admin sees every model, so nothing is checked for visibility.

The core calls are synchronous. A request makes all of them in a single worker-thread hop
(`asyncio.to_thread`): the hashes are collected first, the visible model ids are read once,
then each hash is looked up.
"""

import asyncio
import logging
from typing import Dict, Iterable, List, Sequence

from . import core_bridge
from .permissions import Principal
from .schema import SearchItem

logger = logging.getLogger("plugins.model-browser")


def _normal(sha256: str) -> str:
    return sha256.strip().lower()


def _lookup(sha256s: List[str], user_id: str, admin: bool) -> Dict[str, bool]:
    """The blocking part of `installed_map`, for hashes already normalised and unique; runs in a worker thread."""
    visible = None if admin else set(core_bridge.visible_model_ids(user_id))
    result: Dict[str, bool] = {}
    for sha256 in sha256s:
        model = core_bridge.find_model_by_sha256(sha256)
        result[sha256] = (
            model is not None
            and model.get("is_available", True) is not False
            and (visible is None or model.get("id") in visible)
        )
    return result


async def installed_map(sha256s: Iterable[str], principal: Principal) -> Dict[str, bool]:
    """`{lower-case sha256: installed}` for these hashes (any case, duplicates and blanks ignored).

    A hash the core does not know, whose file has gone from the disk, or (for a non-admin)
    whose model is not visible to the caller maps to False. Without any hash the core is not
    asked. Raises whatever the core raises: the caller decides what an unanswered lookup means.
    """
    hashes = list(dict.fromkeys(_normal(value) for value in sha256s if value and value.strip()))
    if not hashes:
        return {}
    return await asyncio.to_thread(_lookup, hashes, principal.user.id, principal.is_admin)


async def mark_installed(items: Sequence[SearchItem], principal: Principal) -> None:
    """Set `installed` on every item that has a `primary_sha256`: True when installed, else False.

    An item without a hash keeps None. One lookup serves the whole page. When the core cannot
    answer, no item is marked and the cause goes to the debug log: a badge is never worth
    failing a search for.

    The items are changed in place, so pass the ones built for this request, never an object
    shared between users.
    """
    hashes = [item.primary_sha256 for item in items if item.primary_sha256]
    if not hashes:
        return
    try:
        found = await installed_map(hashes, principal)
    except Exception:
        logger.debug("[MODEL-BROWSER] Could not tell which results are installed: leaving them unmarked", exc_info=True)
        return
    for item in items:
        if item.primary_sha256:
            item.installed = found.get(_normal(item.primary_sha256))
