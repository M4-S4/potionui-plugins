import pytest

from backend.chat import context
from backend.chat.context import NOT_OPEN, build_context

PROJECT_ID = "01M5PROJECT000000000000000"


def _shot(index, **fields):
    return {
        "id": f"shot-{index}",
        "label": f"Shot {index}",
        "start": (index - 1) * 4,
        "dur": 4,
        "stage": "todo",
        "promptId": f"prompt-{index}",
        "prompt": f"Instruction {index}",
        "hasFirstFrame": False,
        "hasLastFrame": False,
        "take": None,
        **fields,
    }


def _page(**fields):
    return {
        "projectId": PROJECT_ID,
        "projectVersion": 7,
        "name": "Night ride",
        "promptLanguage": "fr",
        "workspace": "storyboard",
        "selection": {"kind": "clip", "id": "shot-2"},
        "playhead": 5.2,
        "range": {"in": 2, "out": 10},
        "synopsis": "Une cavalière traverse la ville la nuit.",
        "direction": {
            "univers": "Ville nocturne",
            "personnages": "Une cavalière",
            "photographie": "Caméra stable",
            "palette": "",
            "rythme": "Lent",
            "mode": "Ref2VA",
        },
        "production": {"target": "selection", "mode": "draft", "quality": "draft", "state": "running", "progress": 40, "queue": 2},
        "shots": [
            _shot(1, label="Arrivée", hasFirstFrame=True, hasLastFrame=True, take="take-1", stage="draft"),
            _shot(2, label="Le pont", hasFirstFrame=True),
            _shot(3, prompt=""),
        ],
        "issues": [{"shotId": "shot-2", "level": "conflict", "text": "La direction globale demande une caméra stable et lente."}],
        "seams": [
            {"fromShotId": "shot-1", "toShotId": "shot-2", "issues": [{"kind": "lum", "text": "“Le pont” is brighter than the previous shot"}], "measured": True},
            {"fromShotId": "shot-2", "toShotId": "shot-3", "issues": [], "measured": True},
        ],
        **fields,
    }


def _metadata(**fields):
    return {"video_producer": _page(**fields)}


@pytest.mark.parametrize(
    "metadata",
    [None, {}, {"video_producer": None}, {"video_producer": "open"}, {"video_producer": {"name": "No id"}}, {"other": {"projectId": "x"}}],
)
def test_without_the_pages_context_the_block_says_the_page_is_not_open(metadata):
    assert build_context(metadata, None, "user-1") == NOT_OPEN
    assert "\n" not in NOT_OPEN and "not open" in NOT_OPEN


def test_the_block_describes_the_project_the_page_sent():
    block = build_context(_metadata(), None, "user-1")

    lines = block.splitlines()
    assert lines[0] == f'VIDEO PRODUCER: project "Night ride" [{PROJECT_ID}], saved version 7.'
    assert lines[1] == "Prompt language: fr. Write every shot instruction in French; never translate what the user wrote."
    assert lines[2] == (
        'Workspace: storyboard. Playhead: 5.2 s (shot "Le pont" [shot-2]). Selection: shot "Le pont" [shot-2]. Range: 2–10 s.'
    )
    assert "Synopsis: Une cavalière traverse la ville la nuit." in lines
    assert lines[lines.index("Direction (generation profile Ref2VA):") + 1 : lines.index("Direction (generation profile Ref2VA):") + 5] == [
        "  universe: Ville nocturne",
        "  characters: Une cavalière",
        "  photography: Caméra stable",
        "  rhythm: Lent",
    ]
    assert "Shots (3, 12 s), in timeline order:" in lines
    assert '  1. [shot-1] "Arrivée" 0–4 s, draft, take take-1, frames first+last; prompt: "Instruction 1"' in lines
    assert '  2. [shot-2] "Le pont" 4–8 s, todo, frames first; prompt: "Instruction 2"' in lines
    assert '  3. [shot-3] "Shot 3" 8–12 s, todo, frames none; no prompt' in lines
    assert "Conflicts flagged by the page (1):" in lines
    assert '  - "Le pont" [shot-2] conflict: La direction globale demande une caméra stable et lente.' in lines
    assert "Continuity measured by the page (1):" in lines
    assert '  - "Arrivée" → "Le pont" lum: “Le pont” is brighter than the previous shot' in lines
    assert lines[-1] == "Production: running, 40% (draft quality, target selection, 2 queued)."


def test_the_block_resolves_a_selected_prompt_to_its_shot_and_names_other_selections():
    assert 'Selection: the prompt of shot "Shot 3" [shot-3].' in build_context(
        _metadata(selection={"kind": "prompt", "id": "prompt-3"}), None, "user-1"
    )
    assert "Selection: audio a-1." in build_context(_metadata(selection={"kind": "audio", "id": "a-1"}), None, "user-1")
    assert "Selection: none." in build_context(_metadata(selection=None), None, "user-1")


def test_an_empty_project_still_renders_every_section():
    block = build_context(
        {"video_producer": {"projectId": PROJECT_ID, "projectVersion": None, "promptLanguage": "xx"}}, None, "user-1"
    )

    assert f'project "Untitled" [{PROJECT_ID}], saved version none.' in block
    assert "Prompt language: en. Write every shot instruction in English" in block
    assert "Synopsis: (empty)" in block
    assert "Direction (generation profile FL2VA):\n  (empty)" in block
    assert "Shots (0, 0 s), in timeline order:\n  (none yet)" in block
    assert "Conflicts flagged by the page: none." in block
    assert "Continuity" not in block and "Production" not in block


def test_measured_seams_without_issues_say_nothing_was_flagged():
    block = build_context(_metadata(seams=[{"fromShotId": "shot-1", "toShotId": "shot-2", "issues": [], "measured": True}]), None, "u")

    assert "Continuity measured by the page: nothing flagged." in block


def _shot_lines(block):
    return [line for line in block.splitlines() if line.startswith("  ") and "[shot-" in line and " s, todo" in line]


def test_the_block_is_bounded():
    shots = [_shot(index, prompt="word " * 200) for index in range(1, 61)]
    issues = [{"shotId": f"shot-{index}", "level": "conflict", "text": "x" * 500} for index in range(1, 31)]
    seams = [
        {"fromShotId": f"shot-{index}", "toShotId": f"shot-{index + 1}", "issues": [{"kind": "lum", "text": "y" * 500}], "measured": True}
        for index in range(1, 31)
    ]

    block = build_context(_metadata(shots=shots, issues=issues, seams=seams, synopsis="s" * 5000), None, "user-1")

    assert len(block) <= context.MAX_BLOCK_CHARS
    assert block.endswith("…")
    synopsis = next(line for line in block.splitlines() if line.startswith("Synopsis: "))
    assert len(synopsis) == len("Synopsis: ") + context.MAX_SYNOPSIS_CHARS and synopsis.endswith("…")
    shown = _shot_lines(block)
    assert 10 <= len(shown) < 60
    assert all(len(line.split('prompt: "', 1)[1]) <= context.MAX_PROMPT_CHARS + 1 for line in shown)
    assert f"  … {60 - len(shown)} more shots not shown." in block.splitlines()


def test_a_long_shot_list_gives_way_before_the_conflicts_and_the_production_state():
    shots = [_shot(index, prompt="word " * 200) for index in range(1, 61)]

    block = build_context(_metadata(shots=shots), None, "user-1")

    lines = block.splitlines()
    shown = _shot_lines(block)
    assert len(block) <= context.MAX_BLOCK_CHARS
    assert len(shown) < context.MAX_SHOTS
    assert lines[lines.index(shown[-1]) + 1] == f"  … {60 - len(shown)} more shots not shown."
    assert "Conflicts flagged by the page (1):" in lines
    assert lines[-1].startswith("Production: running")


def test_at_most_forty_shots_are_listed():
    block = build_context(_metadata(shots=[_shot(index) for index in range(1, 61)]), None, "user-1")

    assert len(_shot_lines(block)) == context.MAX_SHOTS
    assert "  … 20 more shots not shown." in block.splitlines()


def test_issue_and_seam_lists_are_capped():
    issues = [{"shotId": "shot-1", "level": "conflict", "text": f"Issue {index}"} for index in range(25)]
    seams = [{"fromShotId": "shot-1", "toShotId": "shot-2", "issues": [{"kind": "lum", "text": f"Seam {index}"} for index in range(25)]}]

    lines = build_context(_metadata(issues=issues, seams=seams), None, "user-1").splitlines()

    assert "Conflicts flagged by the page (25):" in lines
    assert sum(1 for line in lines if "conflict: Issue" in line) == context.MAX_ISSUES
    assert "Continuity measured by the page (25):" in lines
    assert sum(1 for line in lines if "lum: Seam" in line) == context.MAX_SEAM_LINES
    assert lines.count("  … 5 more.") == 2


def test_malformed_values_from_the_page_never_break_the_block():
    block = build_context(
        _metadata(
            shots=[_shot(1, start="soon", dur=None, label=None), "junk", 3],
            issues="none",
            seams=[None, {"fromShotId": "shot-1", "issues": "x"}],
            selection={"kind": "clip"},
            playhead=True,
            range={"in": 1},
            direction="dark",
            production="busy",
        ),
        None,
        "user-1",
    )

    assert '  1. [shot-1] "Shot 1" 0–0 s, todo, frames none; prompt: "Instruction 1"' in block
    assert "Playhead" not in block and "Range" not in block
    assert "Direction (generation profile FL2VA):\n  (empty)" in block


def test_each_shot_says_how_many_takes_it_has_and_which_one_is_final_and_production_names_the_engine():
    shots = [_shot(1, takes=3, final="B"), _shot(2, takes=1), _shot(3, takes=0)]
    production = {"target": "clip", "quality": "draft", "state": "ready", "progress": 0, "queue": 0, "engine": "Wan 2.1 / 2.2"}

    lines = build_context(_metadata(shots=shots, production=production), None, "user-1").splitlines()

    assert '  1. [shot-1] "Shot 1" 0–4 s, todo, 3 takes (final B), frames none; prompt: "Instruction 1"' in lines
    assert '  2. [shot-2] "Shot 2" 4–8 s, todo, 1 take, frames none; prompt: "Instruction 2"' in lines
    assert '  3. [shot-3] "Shot 3" 8–12 s, todo, no take, frames none; prompt: "Instruction 3"' in lines
    assert lines[-1] == 'Production: ready, 0% (draft quality, target clip, 0 queued, engine "Wan 2.1 / 2.2").'
