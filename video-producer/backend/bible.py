import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import presets

H3 = "h3"
LTX = "ltx"
WAN = "wan"
CLOUD = "cloud"
OTHER = "other"

LTX_PRESETS = (presets.LTX_2, presets.LTX_2_5)
WAN_PRESETS = (presets.WAN, *presets.WAN_TIER_PRESETS)

CHARACTERS = "characters"
PLACES = "places"

WAN_TOKENS = 512
CHARS_PER_TOKEN = 4

REFS_LAYOUT = "refs"
SUBJECTS_LAYOUT = "subjects"
CAST_LAYOUT = "cast"

SUBJECT_DEFINITIONS = "subject_definitions"
RETENTION = "retention_analysis"
CITATIONS = "citations"
CAST_PART = "cast"

LAYOUTS: Dict[str, Tuple[str, ...]] = {
    REFS_LAYOUT: (SUBJECT_DEFINITIONS, RETENTION, CITATIONS),
    SUBJECTS_LAYOUT: (SUBJECT_DEFINITIONS,),
    CAST_LAYOUT: (CAST_PART,),
}

PARTS = (SUBJECT_DEFINITIONS, RETENTION, CITATIONS, CAST_PART)

TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "named": "{label}: {description}",
        "props": "Props: {props}",
        "setting": "Setting — {card}",
        "define_character": "<Subject {subject}> is {card}",
        "define_setting": "<Subject {subject}> is the setting, {card}",
        "shown_character": "<Subject {subject}> is the character shown in {label}, {card}",
        "shown_setting": "<Subject {subject}> is the setting shown in {label}, {card}",
    },
    "fr": {
        "named": "{label} : {description}",
        "props": "Accessoires : {props}",
        "setting": "Lieu — {card}",
        "define_character": "<Subject {subject}> est {card}",
        "define_setting": "<Subject {subject}> est le décor, {card}",
        "shown_character": "<Subject {subject}> est le personnage montré par {label}, {card}",
        "shown_setting": "<Subject {subject}> est le décor montré par {label}, {card}",
    },
}


@dataclass(frozen=True)
class Card:
    id: str
    kind: str
    label: str
    text: str
    props: str = ""
    references: Tuple[str, ...] = ()
    voice: str = ""
    language: str = ""
    voice_ref: Optional[str] = None


@dataclass(frozen=True)
class ReferencePart:
    layout: str
    composed: Dict[str, str]
    sent: Dict[str, str]
    overridden: bool = False
    changed: bool = False
    ignored: bool = False

    def summary(self) -> Dict[str, Any]:
        """The part as the prompts route reports it."""
        return {
            "layout": self.layout,
            "composed": dict(self.composed),
            "sent": dict(self.sent),
            "overridden": self.overridden,
            "changed": self.changed,
            "ignored": self.ignored,
        }


def _part(value: Any) -> str:
    return value if isinstance(value, str) else ""


def reference_part(clip: Mapping[str, Any], layout: str, composed: Mapping[str, str]) -> ReferencePart:
    """The part of a shot's prompt made from its references and its cast, in the layout of its engine: the composed text, or the text the shot sets for itself in that layout, sent as it is, with whether the composed text changed since it was replaced; a replacement written for another layout is not sent."""
    override = clip.get("referencePrompt")
    parts = override.get("parts") if isinstance(override, Mapping) else None
    if not isinstance(parts, Mapping):
        return ReferencePart(layout, dict(composed), dict(composed))
    if override.get("layout") != layout:
        return ReferencePart(layout, dict(composed), dict(composed), ignored=True)
    base = override.get("base") if isinstance(override.get("base"), Mapping) else {}
    names = LAYOUTS[layout]
    sent = {name: _part(parts.get(name)) for name in names}
    changed = any(_part(base.get(name)) != composed[name] for name in names)
    return ReferencePart(layout, dict(composed), sent, overridden=True, changed=changed)


def _clean(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _sentence(text: str) -> str:
    return text if text[-1:] in ".!?…»\"'" else f"{text}."


def _upper(text: str) -> str:
    return text[:1].upper() + text[1:]


def _language(language: str) -> Dict[str, str]:
    return TEXT.get(language, TEXT["en"])


def cards(doc: Mapping[str, Any], kind: str) -> List[Card]:
    """The cards of one kind of the project's bible, in order, the ones without a label left out: a card enters a prompt by its label."""
    bible = doc.get("bible")
    items = bible.get(kind) if isinstance(bible, Mapping) else None
    found: List[Card] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or not _clean(item.get("label")):
            continue
        references = item.get("references")
        found.append(
            Card(
                id=item["id"],
                kind=kind,
                label=_clean(item.get("label")),
                text=_clean(item.get("text")),
                props=_clean(item.get("props")) if kind == CHARACTERS else "",
                references=tuple(ref for ref in references if isinstance(ref, str)) if isinstance(references, list) else (),
                voice=_clean(item.get("voice")) if kind == CHARACTERS else "",
                language=_clean(item.get("language")) if kind == CHARACTERS else "",
                voice_ref=item["voiceRef"] if kind == CHARACTERS and isinstance(item.get("voiceRef"), str) and item["voiceRef"] else None,
            )
        )
    return found


def cast_of(doc: Mapping[str, Any], clip: Mapping[str, Any]) -> Tuple[List[Card], Optional[Card]]:
    """The characters cast in a shot, in the order of the bible, and its place; cards that no longer exist are left out."""
    cast = clip.get("cast")
    cast = cast if isinstance(cast, Mapping) else {}
    listed = cast.get("characters")
    chosen = {item for item in listed if isinstance(item, str)} if isinstance(listed, list) else set()
    place = next((card for card in cards(doc, PLACES) if card.id == cast.get("place")), None)
    return [card for card in cards(doc, CHARACTERS) if card.id in chosen], place


def card_for_reference(doc: Mapping[str, Any], reference_id: Any) -> Optional[Card]:
    """The first card, characters first, that a reference of the project is linked to."""
    if not isinstance(reference_id, str):
        return None
    return next((card for kind in (CHARACTERS, PLACES) for card in cards(doc, kind) if reference_id in card.references), None)


def description(card: Card, language: str) -> str:
    """The fixed words of a card: its description, then the props of a character."""
    parts = [_sentence(card.text)] if card.text else []
    if card.props:
        parts.append(_sentence(_language(language)["props"].format(props=card.props)))
    return " ".join(parts)


def named(card: Card, language: str, initial: bool = False) -> str:
    """A card as its label followed by its fixed words, the label capitalized when it opens a sentence."""
    label = _upper(card.label) if initial else card.label
    words = description(card, language)
    return _language(language)["named"].format(label=label, description=words) if words else _sentence(label)


def prose(characters: Sequence[Card], place: Optional[Card], language: str) -> List[str]:
    """The cast of a shot as sentences, one per character then the place, repeated word for word in every shot."""
    lines = [named(card, language, initial=True) for card in characters]
    if place is not None:
        lines.append(_language(language)["setting"].format(card=named(place, language)))
    return lines


def definition(card: Card, subject: int, language: str, shown: Optional[str] = None) -> str:
    """The MiniMax-H3 definition of a card as a subject, tied to the reference that shows it when one is sent."""
    text = _language(language)
    kind = "character" if card.kind == CHARACTERS else "setting"
    if shown is not None:
        return text[f"shown_{kind}"].format(subject=subject, label=shown, card=named(card, language))
    return text[f"define_{kind}"].format(subject=subject, card=named(card, language))


def family(preset_id: str, cloud: bool) -> str:
    """The prompt format an engine reads: MiniMax-H3, LTX, Wan, a cloud model, or another engine."""
    if cloud:
        return CLOUD
    if preset_id in presets.MINIMAX_H3_PRESETS:
        return H3
    if preset_id in LTX_PRESETS:
        return LTX
    if preset_id in WAN_PRESETS:
        return WAN
    return OTHER


def _folded(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(char for char in decomposed if not unicodedata.category(char).startswith("M")).split())


def names(text: str, label: str) -> bool:
    """Whether a text names a label as whole words, ignoring case, accents and spacing."""
    wanted = _folded(label)
    return bool(wanted) and re.search(rf"(?<!\w){re.escape(wanted)}(?!\w)", _folded(text)) is not None


def missing_labels(instruction: str, characters: Sequence[Card]) -> List[str]:
    """The labels of the characters cast in a shot that its instruction does not name."""
    return [card.label for card in characters if not names(instruction, card.label)]


def estimated_tokens(text: str) -> int:
    """The tokens a prompt takes, estimated at four characters a token: the plugin has no tokenizer of its own."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def token_limit(engine: str) -> Optional[int]:
    """The prompt length an engine reads, in tokens, when it has one: Wan's text encoder is trained on 512 tokens and its pipeline cuts the rest."""
    return WAN_TOKENS if engine == WAN else None
