import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Pattern, Tuple, Union

RULES_PATH = Path(__file__).with_name("rules.json")

LANGUAGES = ("en", "fr")
DEFAULT_LANGUAGE = "en"
DIRECTION_FIELDS = ("univers", "personnages", "photographie", "palette", "rythme")

_WORD = "[A-Za-z0-9_]"
_JS_WORD_BOUNDARY = f"(?:(?<={_WORD})(?!{_WORD})|(?<!{_WORD})(?={_WORD}))"


@dataclass(frozen=True)
class ConflictRule:
    """One contradiction between the global direction and a shot instruction."""

    id: str
    global_pattern: Pattern[str]
    local_pattern: Pattern[str]
    message: str


def compile_pattern(source: str, flags: str = "i") -> Pattern[str]:
    """A Python pattern that matches what the page's JavaScript RegExp of the same source matches."""
    return re.compile(source.replace("\\b", _JS_WORD_BOUNDARY), re.IGNORECASE if "i" in flags else 0)


def load_rules(path: Path = RULES_PATH) -> Dict[str, Any]:
    """The shared rule tables, as the page reads them."""
    return json.loads(path.read_text(encoding="utf-8"))


RULES = load_rules()

CONFLICTS: Dict[str, Tuple[ConflictRule, ...]] = {
    language: tuple(
        ConflictRule(
            id=rule["id"],
            global_pattern=compile_pattern(rule["global"], RULES["flags"]),
            local_pattern=compile_pattern(rule["local"], RULES["flags"]),
            message=RULES["messages"][rule["id"]],
        )
        for rule in rules
    )
    for language, rules in RULES["conflicts"].items()
}

CAMERA_WORDS: Dict[str, Pattern[str]] = {
    language: compile_pattern(source, RULES["flags"]) for language, source in RULES["cameraWords"].items()
}


def language_of(value: Any) -> str:
    """A supported prompt language, English when the value names none."""
    return value if value in LANGUAGES else DEFAULT_LANGUAGE


def global_prompt(direction: Union[Mapping[str, Any], str, None]) -> str:
    """The filled direction fields joined the way the page joins them."""
    if isinstance(direction, str):
        return direction
    fields = direction if isinstance(direction, Mapping) else {}
    return " ".join(text for text in (str(fields.get(name) or "").strip() for name in DIRECTION_FIELDS) if text)


def conflicts_for(direction: Union[Mapping[str, Any], str, None], prompt_text: Any, language: Any) -> List[Dict[str, str]]:
    """The rules a shot instruction breaks against the global direction, each as its id and English message."""
    whole, text = global_prompt(direction), str(prompt_text or "")
    return [
        {"id": rule.id, "text": rule.message}
        for rule in CONFLICTS[language_of(language)]
        if rule.global_pattern.search(whole) and rule.local_pattern.search(text)
    ]


def camera_moves(text: Any, language: Any) -> List[str]:
    """The camera movements an instruction names, lowercased, first seen first."""
    moves: List[str] = []
    for match in CAMERA_WORDS[language_of(language)].finditer(str(text or "")):
        word = match.group(0).lower()
        if word not in moves:
            moves.append(word)
    return moves


def camera_change(prev_text: Any, next_text: Any, language: Any) -> Optional[Tuple[str, str]]:
    """The first movement of each instruction when both name one and they share none, else None."""
    before, after = camera_moves(prev_text, language), camera_moves(next_text, language)
    if before and after and not set(before) & set(after):
        return before[0], after[0]
    return None
