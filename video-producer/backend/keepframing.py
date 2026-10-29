"""Shots that keep their framing, their start image sent as their end image too, and actions that ask for a move such an end image undoes."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

KEEP = "keepFraming"


def load_table() -> Dict[str, Any]:
    """The words of moving, the table the page keeps an identical copy of."""
    return json.loads(Path(__file__).with_name("keepframing.json").read_text(encoding="utf-8"))


TABLE = load_table()
MOVES = frozenset(TABLE["moves"])
VERBS = frozenset(TABLE["phrases"]["verbs"])
PARTICLES = frozenset(TABLE["phrases"]["particles"])


def keeps_framing(clip: Any) -> bool:
    """True for a shot that keeps its framing."""
    return isinstance(clip, Mapping) and clip.get(KEEP) is True


def _words(text: Any) -> List[str]:
    return re.findall(r"[a-z]+", str(text or "").lower())


def moves(text: Any) -> bool:
    """True when an English instruction asks the subject to move: a verb of moving, such as walks or crosses, or a verb followed by a direction, such as steps forward or comes closer; turns toward, looks toward and faces are no move."""
    found = _words(text)
    return any(word in MOVES for word in found) or any(first in VERBS and second in PARTICLES for first, second in zip(found, found[1:]))
