import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

TABLE_PATH = Path(__file__).with_name("reception.json")


def load_table(path: Path = TABLE_PATH) -> Dict[str, Any]:
    """The table of what each engine receives of the references, as the page reads it."""
    return json.loads(path.read_text(encoding="utf-8"))


TABLE = load_table()

LIMITS: Dict[str, int] = {kind: int(count) for kind, count in TABLE["limits"].items()}


def takes_references(profile: Optional[str]) -> bool:
    """Whether a profile sends the references themselves to the engine, each kind within its limit."""
    return profile in TABLE["references"]


def _matches(rule: Mapping[str, Any], family: str, profile: Optional[str]) -> bool:
    return ("profiles" not in rule or profile in rule["profiles"]) and ("families" not in rule or family in rule["families"])


def layout(family: str, profile: Optional[str] = None) -> str:
    """The layout of the part of a shot's prompt made from its references and its cast: the first rule of the table that matches the engine family and the profile."""
    return next(str(rule["layout"]) for rule in TABLE["layouts"] if _matches(rule, family, profile))
