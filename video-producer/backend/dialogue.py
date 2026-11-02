import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from . import bible

DEFAULT_LANGUAGE = "English"

WORDS_PER_SECOND = 3.0

NARRATOR = ""

FRENCH_NAMES = {
    "English": "anglais",
    "French": "français",
    "Spanish": "espagnol",
    "German": "allemand",
    "Italian": "italien",
    "Portuguese": "portugais",
    "Russian": "russe",
    "Arabic": "arabe",
    "Chinese": "chinois",
    "Japanese": "japonais",
    "Korean": "coréen",
}

H3_TEXT = {
    "voice": "A voice",
    "says": "{head} says{mark} <d>[{language}] {text}</d>",
    "offscreen": "{head} says in an off-screen voiceover{mark} <d>[{language}] {text}</d> On-screen lips stay closed.",
}

LTX_TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "voice": "A voice",
        "says": '{head} says in {language}: "{text}"',
        "offscreen": '{head} speaks off-screen in {language}: "{text}"',
        "lips": "On-screen lips stay closed.",
    },
    "fr": {
        "voice": "Une voix",
        "says": '{head} dit en {language} : "{text}"',
        "offscreen": '{head} parle hors champ en {language} : "{text}"',
        "lips": "Les lèvres à l'écran restent fermées.",
    },
}


@dataclass(frozen=True)
class Line:
    text: str
    speaker: Optional[bible.Card]
    offscreen: bool
    named: bool

    @property
    def key(self) -> str:
        return self.speaker.id if self.speaker is not None else NARRATOR


def _clean(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _upper(text: str) -> str:
    return text[:1].upper() + text[1:]


def _voice(card: Optional[bible.Card]) -> str:
    return card.voice.rstrip(" .;,!") if card is not None else ""


def lines_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> List[Line]:
    """The lines of a shot that have words, in order, each with its speaker from the bible when the card still exists and has a label."""
    characters = {card.id: card for card in bible.cards(doc, bible.CHARACTERS)}
    items = clip.get("dialogue")
    found: List[Line] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        text = _clean(item.get("text"))
        if not text:
            continue
        speaker = item.get("speaker")
        named = isinstance(speaker, str) and bool(speaker)
        found.append(Line(text=text, speaker=characters.get(speaker) if named else None, offscreen=item.get("offscreen") is True, named=named))
    return found


def speaker_ids(lines: Sequence[Line]) -> Dict[str, str]:
    """The stable speaker id of each voice of a shot, S1, S2… in the order of its first line; the lines without a speaker share one."""
    ids: Dict[str, str] = {}
    for line in lines:
        ids.setdefault(line.key, f"S{len(ids) + 1}")
    return ids


def language_of(doc: Mapping[str, Any], card: Optional[bible.Card]) -> str:
    """The language a voice speaks: the character's own, else the project's, else English."""
    if card is not None and card.language:
        return card.language
    return _clean(doc.get("dialogueLanguage")) or DEFAULT_LANGUAGE


def voice_owner(doc: Mapping[str, Any], reference_id: Any) -> Optional[bible.Card]:
    """The first character of the bible whose voice is this reference."""
    if not isinstance(reference_id, str):
        return None
    return next((card for card in bible.cards(doc, bible.CHARACTERS) if card.voice_ref == reference_id), None)


def voice_references(doc: Mapping[str, Any]) -> Set[str]:
    """The references of the project that are the voice of a character."""
    return {card.voice_ref for card in bible.cards(doc, bible.CHARACTERS) if card.voice_ref}


def words(lines: Sequence[Line]) -> int:
    """The words spoken in a shot."""
    return sum(len(line.text.split()) for line in lines)


def word_limit(seconds: float) -> int:
    """The words a shot of this length can carry at a natural pace."""
    return math.floor(seconds * WORDS_PER_SECOND)


def h3_lines(doc: Mapping[str, Any], lines: Sequence[Line], subjects: Mapping[str, int], refs: bool = False) -> str:
    """The lines of a shot in MiniMax-H3's speech format: each voice cited by its subject when it is one, else its label, with its id, its voice described at its first line, the exact words inside <d> after the language, a voiceover said as one with the lips closed."""
    ids = speaker_ids(lines)
    described: Set[str] = set()
    spoken: List[str] = []
    for line in lines:
        card = line.speaker
        if card is not None and card.id in subjects:
            who = f"<Subject {subjects[card.id]}>"
        else:
            who = _upper(card.label) if card is not None else H3_TEXT["voice"]
        head = f"{who} ({ids[line.key]})"
        voice = _voice(card)
        if voice and line.key not in described:
            head = f"{head}, {voice},"
        described.add(line.key)
        template = H3_TEXT["offscreen" if line.offscreen else "says"]
        spoken.append(template.format(head=head, mark="," if refs else ":", language=language_of(doc, card), text=line.text))
    return " ".join(spoken)


def _ltx_language(name: str, prompt_language: str) -> str:
    return FRENCH_NAMES.get(name, name) if prompt_language == "fr" else name


def ltx_lines(doc: Mapping[str, Any], lines: Sequence[Line], prompt_language: str) -> str:
    """The lines of a shot as LTX reads them: who speaks, the voice at its first line, the language and the exact words in quotation marks, a voice heard off-screen with the lips closed."""
    text = LTX_TEXT.get(prompt_language, LTX_TEXT["en"])
    described: Set[str] = set()
    spoken: List[str] = []
    for line in lines:
        card = line.speaker
        head = _upper(card.label) if card is not None else text["voice"]
        voice = _voice(card)
        if voice and line.key not in described:
            head = f"{head}, {voice},"
        described.add(line.key)
        language = _ltx_language(language_of(doc, card), prompt_language)
        spoken.append(text["offscreen" if line.offscreen else "says"].format(head=head, language=language, text=line.text))
        if line.offscreen:
            spoken.append(text["lips"])
    return " ".join(spoken)
