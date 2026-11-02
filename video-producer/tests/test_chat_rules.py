import json
import re
from pathlib import Path

import pytest

from backend.chat import rules

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RULES_JSON = PLUGIN_ROOT / "backend" / "chat" / "rules.json"
PAGE_RULES_COPY = PLUGIN_ROOT / "frontend" / "src" / "lib" / "rules.json"


def _shared():
    return json.loads(RULES_JSON.read_text(encoding="utf-8"))


def test_the_python_tables_are_built_from_the_shared_json():
    shared = _shared()

    assert set(rules.CONFLICTS) == set(shared["conflicts"]) == set(rules.LANGUAGES)
    for language, entries in shared["conflicts"].items():
        built = rules.CONFLICTS[language]
        assert [rule.id for rule in built] == [entry["id"] for entry in entries]
        assert [rule.message for rule in built] == [shared["messages"][entry["id"]] for entry in entries]
        for rule, entry in zip(built, entries):
            assert rule.global_pattern.pattern == rules.compile_pattern(entry["global"]).pattern
            assert rule.local_pattern.pattern == rules.compile_pattern(entry["local"]).pattern
            assert rule.global_pattern.flags & re.IGNORECASE and rule.local_pattern.flags & re.IGNORECASE
    assert {language: pattern.pattern for language, pattern in rules.CAMERA_WORDS.items()} == {
        language: rules.compile_pattern(source).pattern for language, source in shared["cameraWords"].items()
    }


def test_both_languages_share_the_same_rules_and_every_rule_has_an_english_message():
    shared = _shared()

    assert shared["flags"] == "i"
    assert [entry["id"] for entry in shared["conflicts"]["en"]] == [entry["id"] for entry in shared["conflicts"]["fr"]]
    assert set(shared["messages"]) == {entry["id"] for entry in shared["conflicts"]["en"]}
    assert all(text.endswith(".") for text in shared["messages"].values())


def test_the_page_reads_an_identical_copy_of_the_rules():
    assert json.loads(PAGE_RULES_COPY.read_text(encoding="utf-8")) == _shared()


@pytest.mark.parametrize(
    "source, text, matches",
    [
        ("\\btext\\b", "on-screen text.", True),
        ("\\btext\\b", "context", False),
        ("\\btext\\b", "texts", False),
        ("\\bneons?\\b", "éneon", True),
        ("\\bneons?\\b", "neonlight", False),
        ("n[ée]on", "NÉON", True),
        ("cam[ée]ra (à l’épaule|tremblée)", "Caméra à l’épaule", True),
    ],
)
def test_patterns_match_like_the_pages_javascript_regexps(source, text, matches):
    assert bool(rules.compile_pattern(source).search(text)) is matches


def test_global_prompt_joins_the_filled_direction_fields_like_the_page():
    direction = {"univers": " Night city ", "personnages": "", "photographie": "Steady camera", "palette": None, "rythme": "Slow", "mode": "no neon"}

    assert rules.global_prompt(direction) == "Night city Steady camera Slow"
    assert rules.global_prompt("No neon") == "No neon"
    assert rules.global_prompt(None) == ""


def test_english_conflicts_follow_the_rule_order():
    direction = {"univers": "No neon. Steady camera, natural colours.", "photographie": "No on-screen text"}

    found = rules.conflicts_for(direction, "Handheld shot under a neon sign, black-and-white, a logo on the wall", "en")

    assert [conflict["id"] for conflict in found] == ["noNeon", "noText", "naturalColors", "stableCamera"]
    assert found[0]["text"] == "The global direction excludes neon lights."


def test_french_conflicts_read_the_french_tables():
    direction = {"univers": "Aucun néon, couleurs naturelles", "photographie": "Caméra stable"}

    assert [conflict["id"] for conflict in rules.conflicts_for(direction, "Enseigne au NÉON, plan en noir et blanc", "fr")] == [
        "noNeon",
        "naturalColors",
    ]
    assert [conflict["id"] for conflict in rules.conflicts_for(direction, "Caméra à l’épaule dans la foule", "fr")] == [
        "stableCamera"
    ]
    assert rules.conflicts_for(direction, "Enseigne au néon", "en") == []


def test_no_conflict_without_a_matching_direction_and_an_unknown_language_reads_english():
    assert rules.conflicts_for({}, "Handheld shot under neon", "en") == []
    assert rules.conflicts_for({"univers": "No neon"}, "", "en") == []
    assert [conflict["id"] for conflict in rules.conflicts_for({"univers": "No neon"}, "neon", "de")] == ["noNeon"]
    assert rules.language_of("fr") == "fr"
    assert rules.language_of(None) == "en"


def test_camera_moves_are_lowercased_and_listed_once_in_order():
    assert rules.camera_moves("Slow DOLLY in, then a zoom and another dolly", "en") == ["dolly", "zoom"]
    assert rules.camera_moves("Plan fixe puis travelling latéral", "fr") == ["plan fixe", "travelling"]
    assert rules.camera_moves("A pan across the panorama", "en") == ["pan"]
    assert rules.camera_moves(None, "en") == []


def test_camera_change_needs_a_move_on_both_sides_and_none_in_common():
    assert rules.camera_change("Dolly in on the rider", "Static shot of the bridge", "en") == ("dolly", "static shot")
    assert rules.camera_change("Dolly in on the rider", "Dolly out, then zoom", "en") is None
    assert rules.camera_change("The rider waits", "Static shot of the bridge", "en") is None
    assert rules.camera_change("Survol de la vallée", "Plan fixe sur le pont", "fr") == ("survol", "plan fixe")
    assert rules.camera_change("Survol de la vallée", "Plan fixe sur le pont", "en") is None
