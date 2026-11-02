import json
import re
import tokenize
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
I18N = PLUGIN / "frontend" / "src" / "i18n"
SHOTS = PLUGIN / "docs" / "screenshots"
DIST = PLUGIN / "frontend" / "dist" / "VideoProducerPage.js"
ALLOWED_COMMENTS = {("backend/exports/video.py", "# one frame of slack: a file can end a frame before its probed length")}
GUIDES = (PLUGIN / "docs" / "user-guide.md",)


def test_nothing_is_simulated_any_more_in_the_dictionaries_the_readme_or_the_guides():
    for lang in ("en", "fr"):
        for path in sorted((I18N / lang).glob("*.json")):
            words = json.loads(path.read_text(encoding="utf-8"))
            assert [key for key, text in words.items() if re.search(r"simulat", f"{key} {text}", re.I)] == [], path.name
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert "## What stays simulated" not in readme and "Simulated features" not in readme
    for path in GUIDES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"Simulated features|What is simulated|\*\*Simul", text), path.name


@pytest.mark.parametrize("path", GUIDES, ids=["guide-en"])
def test_the_chapters_of_a_guide_follow_each_other_and_every_chapter_it_names_exists(path):
    text = path.read_text(encoding="utf-8")
    numbers = [int(number) for number in re.findall(r"^## (\d+)\. ", text, re.M)]
    named = {int(number) for number in re.findall(r"chapters? (\d+)", text)}
    named |= {int(number) for pair in re.findall(r"chapters (\d+) and (\d+)", text) for number in pair}

    assert numbers == list(range(1, len(numbers) + 1))
    assert sorted(named - set(numbers)) == []


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


def test_the_served_dist_keeps_no_trace_of_a_simulation():
    dist = DIST.read_text(encoding="utf-8")

    for leftover in ("generation.card.legacy", "viewer.simDraft", "shell.menubar.simulated", "shell.simulations", "help-sim", "simulatedTip", "vp-toast-sim"):
        assert leftover not in dist, leftover
    assert dist.count("vp-sim") == 0


def test_the_page_draws_a_focus_ring_around_the_host_switches():
    page = (PLUGIN / "frontend" / "src" / "VideoProducerPage.svelte").read_text(encoding="utf-8")

    assert "[role='switch']:focus-visible" in page
    assert "[role='switch'][data-focus-ring]:focus" in page


def test_the_screenshots_readme_cites_no_state_that_the_page_no_longer_has():
    text = (SHOTS / "README.md").read_text(encoding="utf-8")

    for gone in ("Prise finale · IA simulée", "Export vidéo simulé", "nine entries", '"Non enregistré" until'):
        assert gone not in text, gone
