import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Dict, Mapping, Optional, Tuple

from src.plugin_api.chat import ToolContext

from .tools import ToolFailure, page_context

MAX_CARDS_PER_USER = 32
CARD_TTL_S = 7 * 24 * 3600
PAGE_OUTDATED = "page_outdated"
REFUSED = "refused"

Cards = "OrderedDict[str, Tuple[float, Dict[str, Any]]]"
_cards: Dict[str, Cards] = {}


def _key(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> str:
    raw = json.dumps([tool, dict(arguments), page_context(context)], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _of(user_id: str) -> Cards:
    cards = _cards.setdefault(user_id, OrderedDict())
    oldest = time.monotonic() - CARD_TTL_S
    for key in [key for key, (made, _) in cards.items() if made < oldest]:
        del cards[key]
    return cards


def _copy(value: Mapping[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(value, default=str))


def turn_of(context: ToolContext) -> str:
    """The id the page gives the context of each message it sends, which ties an approval card to the turn that showed it; refused when the page sends none."""
    turn = page_context(context).get("contextId")
    if not isinstance(turn, str) or not turn:
        raise ToolFailure(PAGE_OUTDATED, "The Video Producer page is older than the server and cannot show approval cards: reload the page and ask again.")
    return turn


def keep(context: ToolContext, tool: str, arguments: Mapping[str, Any], shown: Mapping[str, Any]) -> None:
    """Record what the approval card of a call shows for the turn that shows it, replacing an earlier record of the same turn; the preview the host runs when the user approves comes with a context of its own and never replaces it."""
    cards = _of(context.user_id)
    key = _key(context, tool, arguments)
    cards[key] = (time.monotonic(), _copy(shown))
    cards.move_to_end(key)
    while len(cards) > MAX_CARDS_PER_USER:
        cards.popitem(last=False)


def shown(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """What the approval card of this call showed in its turn, a refusal already given for it, or None when the server no longer has it."""
    found = _of(context.user_id).get(_key(context, tool, arguments))
    return _copy(found[1]) if found else None


def refuse(context: ToolContext, tool: str, arguments: Mapping[str, Any], failure: ToolFailure) -> None:
    """Retire the card of an approval that was refused, keeping only the refusal so that a retry gives it again."""
    cards = _of(context.user_id)
    key = _key(context, tool, arguments)
    if key in cards:
        cards[key] = (time.monotonic(), {REFUSED: {"code": failure.code, "message": failure.message}})


def forget(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> None:
    """Drop the card of a call once its approved action ran."""
    _of(context.user_id).pop(_key(context, tool, arguments), None)


def clear() -> None:
    """Forget every card."""
    _cards.clear()
