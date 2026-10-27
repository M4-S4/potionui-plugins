import json
import re
import tokenize
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
I18N = PLUGIN / "frontend" / "src" / "i18n"
SHOTS = PLUGIN / "docs" / "screenshots"
DIST = PLUGIN / "frontend" / "dist" / "VideoProducerPage.js"
SIMULATION_ORDER = ("identity",)
ALLOWED_COMMENTS = {("backend/exports/video.py", "# one frame of slack: a file can end a frame before its probed length")}


def _norm(text):
    text = text.replace("**", "").replace("`", "").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _simulations(lang):
    shell = json.loads((I18N / lang / "shell.json").read_text(encoding="utf-8"))
    return [(shell[f"simulations.{key}.title"], shell[f"simulations.{key}.text"]) for key in SIMULATION_ORDER]


def _table_rows(section):
    rows = []
    for line in section.splitlines():
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows[1:]


def _guide_section(path):
    text = path.read_text(encoding="utf-8")
    return re.search(r"^## 17\..*?(?=^## 18\.)", text, re.S | re.M).group(0)


def _readme_section():
    text = (PLUGIN / "README.md").read_text(encoding="utf-8")
    start = text.index("## What stays simulated")
    end = text.find("\n## ", start + 5)
    return text[start:end] if end > 0 else text[start:]


def test_the_page_dictionary_lists_exactly_the_one_simulation_left_in_both_languages():
    for lang in ("en", "fr"):
        shell = json.loads((I18N / lang / "shell.json").read_text(encoding="utf-8"))
        assert len([key for key in shell if re.fullmatch(r"simulations\.\w+\.title", key)]) == 1
        assert [title for title, _ in _simulations(lang)] and all(text for _, text in _simulations(lang))


@pytest.mark.parametrize(
    "lang, section",
    [
        ("en", lambda: _guide_section(PLUGIN / "docs" / "user-guide.md")),
        ("fr", lambda: _guide_section(PLUGIN / "docs" / "user-guide.fr.md")),
        ("en", _readme_section),
    ],
    ids=["guide-en", "guide-fr", "readme"],
)
def test_the_simulation_table_repeats_the_window_titles_and_texts_in_order(lang, section):
    rows = _table_rows(section())
    expected = _simulations(lang)

    assert len(rows) == 1
    assert [_norm(row[0]) for row in rows] == [_norm(title) for title, _ in expected]
    assert [_norm(row[1]) for row in rows] == [_norm(text) for _, text in expected]


def test_every_screenshot_the_readme_cites_exists_and_every_image_is_cited():
    text = (SHOTS / "README.md").read_text(encoding="utf-8")
    cited = {name for name in re.findall(r"[\w\-./]+\.(?:png|jpg|jpeg)", text) if not name.startswith("-")}
    files = {path.name for path in SHOTS.iterdir() if path.suffix.lower() in (".png", ".jpg", ".jpeg")}

    assert sorted(cited - files) == []
    assert sorted(files - cited) == []


def test_the_python_sources_hold_no_comment_but_the_one_kept_in_the_video_export():
    found = set()
    for folder in ("backend", "hooks"):
        for path in sorted((PLUGIN / folder).rglob("*.py")):
            with open(path, "rb") as handle:
                for token in tokenize.tokenize(handle.readline):
                    if token.type == tokenize.COMMENT:
                        found.add((path.relative_to(PLUGIN).as_posix(), token.string))

    assert found == ALLOWED_COMMENTS


def test_the_served_dist_keeps_no_trace_of_the_retired_simulated_take():
    dist = DIST.read_text(encoding="utf-8")

    for leftover in ("generation.card.legacy", "viewer.simDraft", "shell.menubar.simulated"):
        assert leftover not in dist, leftover
    assert dist.count("vp-sim") == 4


def test_the_page_draws_a_focus_ring_around_the_host_switches():
    page = (PLUGIN / "frontend" / "src" / "VideoProducerPage.svelte").read_text(encoding="utf-8")

    assert "[role='switch']:focus-visible" in page
    assert "[role='switch'][data-focus-ring]:focus" in page


def test_the_screenshots_readme_cites_no_state_that_the_page_no_longer_has():
    text = (SHOTS / "README.md").read_text(encoding="utf-8")

    for gone in ("Prise finale · IA simulée", "Export vidéo simulé", "nine entries", '"Non enregistré" until'):
        assert gone not in text, gone
