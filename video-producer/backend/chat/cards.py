import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Dict, Mapping, Optional, Tuple

from src.plugin_api.chat import ToolContext

from .tools import page_context

MAX_CARDS = 256
CARD_TTL_S = 7 * 24 * 3600

_cards: "OrderedDict[str, Tuple[float, Dict[str, Any]]]" = OrderedDict()


def _key(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> str:
    raw = json.dumps([context.user_id, tool, dict(arguments), page_context(context)], sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _expire() -> None:
    oldest = time.monotonic() - CARD_TTL_S
    for key in [key for key, (made, _) in _cards.items() if made < oldest]:
        del _cards[key]


def keep(context: ToolContext, tool: str, arguments: Mapping[str, Any], shown: Dict[str, Any]) -> None:
    """Remember what an approval card showed, the first time the turn that asked for it shows it, so that a later preview of the same call cannot change it."""
    _expire()
    key = _key(context, tool, arguments)
    if key in _cards:
        return
    _cards[key] = (time.monotonic(), json.loads(json.dumps(shown, default=str)))
    while len(_cards) > MAX_CARDS:
        _cards.popitem(last=False)


def shown(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """What the approval card of this call showed in its turn, or None when the server no longer knows it."""
    _expire()
    found = _cards.get(_key(context, tool, arguments))
    return json.loads(json.dumps(found[1])) if found else None


def forget(context: ToolContext, tool: str, arguments: Mapping[str, Any]) -> None:
    """Drop the card of a call once its approved action ran."""
    _cards.pop(_key(context, tool, arguments), None)


def clear() -> None:
    """Forget every card."""
    _cards.clear()
