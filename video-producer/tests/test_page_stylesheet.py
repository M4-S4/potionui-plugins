import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SOURCE = PLUGIN / "frontend" / "src" / "VideoProducerPage.css"
DIST = PLUGIN / "frontend" / "dist" / "VideoProducerPage.css"
SCOPE = ":where([data-potionui-plugin=video-producer])"
KEYFRAMES = re.compile(r"@keyframes\s+[\w-]+\s*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}")


def selectors(css):
    found = []
    for prelude in re.findall(r"([^{};]+)\{", KEYFRAMES.sub("", css)):
        prelude = prelude.strip()
        if prelude.startswith("@"):
            continue
        found.extend(part.strip() for part in re.split(r"(?<!\\),(?![^()]*\))", prelude))
    return found


def test_the_page_ships_a_stylesheet_next_to_its_component():
    assert (PLUGIN / "frontend" / "src" / "VideoProducerPage.svelte").is_file()
    assert SOURCE.read_text(encoding="utf-8").split() == ["@tailwind", "utilities;"]


def test_the_built_stylesheet_holds_the_classes_only_the_page_uses():
    css = DIST.read_text(encoding="utf-8")

    assert "@tailwind" not in css
    for utility in (r".border-l-\[3px\]", r".h-\[18px\]", r".w-\[42\%\]"):
        assert f"{SCOPE} {utility}" in css, utility


def test_every_rule_of_the_built_stylesheet_stays_inside_the_page():
    found = selectors(DIST.read_text(encoding="utf-8"))

    assert len(found) > 500
    assert [selector for selector in found if not selector.startswith(f"{SCOPE} ")] == []


def test_the_built_stylesheet_reads_the_tokens_of_the_app_and_sets_none():
    css = DIST.read_text(encoding="utf-8")

    assert "rgb(var(--fg))" in css or "rgb(var(--fg)/" in css
    assert not re.search(r"(?<![\w-])--(?:fg|surface-\d|line)\s*:", css)
