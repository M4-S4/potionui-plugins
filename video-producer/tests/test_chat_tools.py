import json
from datetime import datetime

import pytest

from backend import projects
from backend.chat import tools
from backend.chat.tools import CheckContinuityTool, FixConflictsTool, SplitSynopsisTool, WriteShotPromptTool
from src.plugin_api.chat import ToolApprovalPreview, ToolContext


@pytest.fixture
def db(project_db, store, clock):
    return project_db


def _clip(shot_id, start=0, dur=4, **fields):
    return {"id": shot_id, "start": start, "dur": dur, **fields}


def _prompt(prompt_id, text, shot_id=None, start=0, dur=4):
    return {"id": prompt_id, "shotId": shot_id, "start": start, "dur": dur, "text": text}


def _frame(frame_id, shot_id, role="first"):
    return {"id": frame_id, "shotId": shot_id, "assetId": f"asset-{frame_id}", "role": role}


@pytest.fixture
def project(db, make_project):
    return make_project(
        clips=[_clip("s1", 0, 4, label="Arrival"), _clip("s2", 4, 5, label="Bridge"), _clip("s3", 9, 4)],
        prompts=[_prompt("p1", "Wide shot of the rider", "s1", 0, 4), _prompt("seq", "Rain over the city", None, 9, 4)],
        direction={"univers": "No neon. Steady camera."},
    )


def _context(project_id, user_id="user-1", is_admin=False, **page):
    return ToolContext(
        user_id=user_id,
        mode_id="video-producer",
        is_admin=is_admin,
        session_metadata={"video_producer": {"projectId": project_id, **page}},
    )


def _stored(project_id):
    return projects.get_project(project_id)


def _data(result):
    assert result.success, result.error
    return json.loads(result.data)


def _code(result):
    assert not result.success
    assert result.data == ""
    return result.error.split(":", 1)[0]


@pytest.mark.parametrize(
    "tool, name, approval",
    [
        (WriteShotPromptTool, "vp_write_shot_prompt", True),
        (FixConflictsTool, "vp_fix_conflicts", True),
        (SplitSynopsisTool, "vp_split_synopsis", True),
        (CheckContinuityTool, "vp_check_continuity", False),
    ],
)
def test_each_tool_is_built_without_arguments_and_scoped_to_the_mode(tool, name, approval):
    instance = tool()

    assert (instance.name, instance.requires_approval, instance.modes) == (name, approval, ["video-producer"])
    assert instance.group == "Video Producer"
    assert instance.description and instance.hint and instance.user_description and instance.icon
    assert instance.parameters["type"] == "object"
    assert set(instance.parameters["required"]) <= set(instance.parameters["properties"])


async def test_write_previews_the_change_without_saving(project):
    result = await WriteShotPromptTool().execute(_context(project["id"]), shot_id="s2", text="Static shot of the bridge")

    assert _data(result) == {
        "status": "pending_approval",
        "project_id": project["id"],
        "shot_id": "s2",
        "text": "Static shot of the bridge",
    }
    assert result.preview == ToolApprovalPreview(
        action="Write shot prompt",
        target="Bridge",
        kind="text_edit",
        summary="Write the prompt of “Bridge”",
        text_blocks=[{"label": "Bridge", "text": "Static shot of the bridge"}],
    )
    assert _stored(project["id"])["version"] == 1


async def test_write_shows_the_shots_own_prompt_or_the_sequence_prompt_that_covers_it(project):
    own = await WriteShotPromptTool().execute(_context(project["id"]), shot_id="s1", text="New")
    covered = await WriteShotPromptTool().execute(_context(project["id"]), shot_id="s3", text="New")

    assert own.preview.text_blocks == [{"label": "Arrival", "text": "New", "old_text": "Wide shot of the rider"}]
    assert covered.preview.text_blocks == [{"label": "Shot 3", "text": "New", "old_text": "Rain over the city"}]
    assert covered.preview.target == "Shot 3"


async def test_write_confirmed_creates_the_prompt_of_a_shot_that_has_none(project):
    result = await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s2", text="Static shot of the bridge")

    data = _data(result)
    stored = _stored(project["id"])
    created = next(prompt for prompt in stored["doc"]["prompts"] if prompt["shotId"] == "s2")
    assert data == {
        "project_id": project["id"],
        "shot_id": "s2",
        "prompt_id": created["id"],
        "text": "Static shot of the bridge",
        "version": 2,
    }
    assert len(created["id"]) == 26
    assert created == {"id": created["id"], "shotId": "s2", "start": 4, "dur": 5, "strength": 75, "text": "Static shot of the bridge"}
    assert stored["version"] == 2
    assert projects.list_versions(project["id"])[0]["label"] == "Assistant"


async def test_write_confirmed_replaces_the_text_as_given_and_keeps_everything_else(project):
    text = "  Plan large du cavalier,\nsous la pluie fine.  "

    data = _data(await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s1", text=text))

    stored = _stored(project["id"])["doc"]
    assert data["prompt_id"] == "p1"
    assert [(prompt["id"], prompt["text"]) for prompt in stored["prompts"]] == [("p1", text), ("seq", "Rain over the city")]
    assert stored["clips"] == [{**clip, "revision": 1} if clip["id"] == "s1" else clip for clip in project["doc"]["clips"]]


async def test_write_confirmed_bumps_the_revision_of_the_shot_only_when_its_text_changes(project):
    revisions = []
    for text in ("Static shot of the bridge", "Static shot of the bridge", "Slow pan over the bridge"):
        _data(await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s2", text=text))
        revisions.append(next(clip.get("revision") for clip in _stored(project["id"])["doc"]["clips"] if clip["id"] == "s2"))

    assert revisions == [1, 1, 2]


async def test_an_administrator_writes_into_any_project(db, make_project, project):
    data = _data(
        await WriteShotPromptTool().execute_confirmed(
            _context(project["id"], user_id="admin-1", is_admin=True), shot_id="s1", text="Admin text"
        )
    )

    assert data["version"] == 2
    assert _stored(project["id"])["user_id"] == "user-1"


@pytest.mark.parametrize("method", ["execute", "execute_confirmed"])
async def test_write_refuses_a_project_the_caller_cannot_reach(project, method):
    tool = WriteShotPromptTool()
    calls = [
        ToolContext(user_id="user-1", session_metadata={}),
        ToolContext(user_id="user-1", session_metadata={"video_producer": None}),
        _context(""),
        _context("01M5UNKNOWNPROJECT00000000"),
        _context(project["id"], user_id="user-2"),
    ]

    for context in calls:
        assert _code(await getattr(tool, method)(context, shot_id="s1", text="x")) == "project_not_found"
    assert _stored(project["id"])["version"] == 1


@pytest.mark.parametrize("method", ["execute", "execute_confirmed"])
async def test_write_refuses_an_unknown_shot(project, method):
    result = await getattr(WriteShotPromptTool(), method)(_context(project["id"]), shot_id="nope", text="x")

    assert _code(result) == "shot_not_found"
    assert "'nope'" in result.error
    assert _stored(project["id"])["version"] == 1


@pytest.mark.parametrize(
    "arguments",
    [{}, {"shot_id": "s1"}, {"shot_id": "s1", "text": "   "}, {"shot_id": 3, "text": "x"}, {"shot_id": "s1", "text": ["x"]}, {"shot_id": "s1", "text": "x" * 4001}],
)
async def test_write_refuses_invalid_arguments(project, arguments):
    for method in ("execute", "execute_confirmed"):
        assert _code(await getattr(WriteShotPromptTool(), method)(_context(project["id"]), **arguments)) == "invalid_arguments"


def _race(monkeypatch, conflicts):
    real = projects.save_project
    calls = []

    def save(project_id, doc, expected_version, label=None):
        calls.append(expected_version)
        if len(calls) <= conflicts:
            current = projects.get_project(project_id)
            real(project_id, {**current["doc"], "synopsis": f"Edited {len(calls)}"}, current["version"])
        return real(project_id, doc, expected_version, label=label)

    monkeypatch.setattr(projects, "save_project", save)
    return calls


async def test_a_version_conflict_is_read_and_applied_again_once(project, monkeypatch):
    calls = _race(monkeypatch, conflicts=1)

    data = _data(await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s2", text="Static"))

    stored = _stored(project["id"])
    assert calls == [1, 2]
    assert data["version"] == stored["version"] == 3
    assert stored["doc"]["synopsis"] == "Edited 1"
    assert any(prompt["shotId"] == "s2" and prompt["text"] == "Static" for prompt in stored["doc"]["prompts"])


async def test_a_second_version_conflict_fails_without_writing(project, monkeypatch):
    calls = _race(monkeypatch, conflicts=2)

    result = await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s2", text="Static")

    stored = _stored(project["id"])
    assert _code(result) == "version_conflict"
    assert calls == [1, 2]
    assert stored["version"] == 3
    assert not any(prompt["shotId"] == "s2" for prompt in stored["doc"]["prompts"])


async def test_a_document_the_plugin_refuses_comes_back_with_its_code(project, monkeypatch):
    def refuse(project_id, doc, expected_version, label=None):
        raise projects.DocError("doc_too_large", "$: too large")

    monkeypatch.setattr(projects, "save_project", refuse)

    result = await WriteShotPromptTool().execute_confirmed(_context(project["id"]), shot_id="s1", text="x")

    assert result.error == "doc_too_large: $: too large"


async def test_fix_conflicts_previews_one_block_per_shot(project):
    result = await FixConflictsTool().execute(
        _context(project["id"]),
        rewrites=[{"shot_id": "s1", "text": "Wide shot, steady"}, {"shot_id": "s2", "text": "Bridge at dusk"}],
    )

    assert _data(result) == {
        "status": "pending_approval",
        "project_id": project["id"],
        "rewrites": [{"shot_id": "s1", "text": "Wide shot, steady"}, {"shot_id": "s2", "text": "Bridge at dusk"}],
    }
    assert result.preview == ToolApprovalPreview(
        action="Fix conflicts",
        target="2 shots",
        kind="text_edit",
        summary="Rewrite the prompts of 2 shots",
        text_blocks=[
            {"label": "Arrival", "text": "Wide shot, steady", "old_text": "Wide shot of the rider"},
            {"label": "Bridge", "text": "Bridge at dusk"},
        ],
    )
    assert _stored(project["id"])["version"] == 1


async def test_fix_conflicts_confirmed_applies_every_rewrite_in_one_save(project):
    data = _data(
        await FixConflictsTool().execute_confirmed(
            _context(project["id"]),
            rewrites=[{"shot_id": "s1", "text": "Wide shot, steady"}, {"shot_id": "s3", "text": "Rain on the bridge, steady"}],
        )
    )
    assert {clip["id"]: clip.get("revision") for clip in _stored(project["id"])["doc"]["clips"]} == {"s1": 1, "s2": None, "s3": 1}

    stored = _stored(project["id"])
    created = next(prompt for prompt in stored["doc"]["prompts"] if prompt["shotId"] == "s3")
    assert data == {
        "project_id": project["id"],
        "changes": [
            {"shot_id": "s1", "prompt_id": "p1", "before": "Wide shot of the rider", "after": "Wide shot, steady"},
            {"shot_id": "s3", "prompt_id": created["id"], "before": "Rain over the city", "after": "Rain on the bridge, steady"},
        ],
        "version": 2,
    }
    assert stored["version"] == 2
    assert len(projects.list_versions(project["id"])) == 2


@pytest.mark.parametrize(
    "rewrites",
    [None, [], "s1", ["s1"], [{"shot_id": "s1"}], [{"shot_id": "s1", "text": "a"}, {"shot_id": "s1", "text": "b"}], [{"shot_id": "s1", "text": "a"}] * 101],
)
async def test_fix_conflicts_refuses_invalid_rewrites(project, rewrites):
    for method in ("execute", "execute_confirmed"):
        assert _code(await getattr(FixConflictsTool(), method)(_context(project["id"]), rewrites=rewrites)) == "invalid_arguments"


async def test_fix_conflicts_writes_nothing_when_one_shot_is_unknown(project):
    rewrites = [{"shot_id": "s1", "text": "a"}, {"shot_id": "gone", "text": "b"}]

    assert _code(await FixConflictsTool().execute(_context(project["id"]), rewrites=rewrites)) == "shot_not_found"
    assert _code(await FixConflictsTool().execute_confirmed(_context(project["id"]), rewrites=rewrites)) == "shot_not_found"
    assert _stored(project["id"])["version"] == 1


async def test_fix_conflicts_refuses_another_users_project_and_retries_a_conflict_once(project, monkeypatch):
    rewrites = [{"shot_id": "s1", "text": "a"}]
    assert _code(await FixConflictsTool().execute_confirmed(_context(project["id"], user_id="user-2"), rewrites=rewrites)) == "project_not_found"

    calls = _race(monkeypatch, conflicts=1)
    data = _data(await FixConflictsTool().execute_confirmed(_context(project["id"]), rewrites=rewrites))

    assert calls == [1, 2]
    assert data["version"] == 3


SHOTS = [
    {"label": "Arrival", "prompt": "The rider enters the city under the rain, wide shot", "duration_s": 4},
    {"label": "Bridge", "prompt": "Static shot of the bridge", "duration_s": 5.5},
    {"label": "Gate", "prompt": "Close-up on the gate", "duration_s": "3"},
]


async def test_split_previews_the_shots_as_timeline_rows(project):
    result = await SplitSynopsisTool().execute(_context(project["id"]), shots=SHOTS)

    proposal = [
        {"label": "Arrival", "prompt": "The rider enters the city under the rain, wide shot", "duration_s": 4},
        {"label": "Bridge", "prompt": "Static shot of the bridge", "duration_s": 5.5},
        {"label": "Gate", "prompt": "Close-up on the gate", "duration_s": 3.0},
    ]
    assert _data(result) == {"status": "pending_approval", "project_id": project["id"], "proposal": proposal}
    assert result.preview == ToolApprovalPreview(
        action="Split synopsis",
        target="3 shots, 12.5 s",
        kind="timeline",
        summary="Propose 3 shots (12.5 s) from the synopsis",
        rows=[
            {"range": "0–4 s", "text": "Arrival: The rider enters the city under the rain, wide shot"},
            {"range": "4–9.5 s", "text": "Bridge: Static shot of the bridge"},
            {"range": "9.5–12.5 s", "text": "Gate: Close-up on the gate"},
        ],
    )


async def test_split_confirmed_returns_the_proposal_and_writes_nothing(project):
    shots = [{"label": "  One  ", "prompt": f"  {'Long instruction ' * 10}  ", "duration_s": 15}]

    data = _data(await SplitSynopsisTool().execute_confirmed(_context(project["id"]), shots=shots))

    assert data == {"project_id": project["id"], "proposal": [{"label": "One", "prompt": ("Long instruction " * 10).strip(), "duration_s": 15}]}
    assert _stored(project["id"])["version"] == 1


async def test_split_preview_rows_shorten_long_prompts(project):
    result = await SplitSynopsisTool().execute(_context(project["id"]), shots=[{"label": "One", "prompt": "word " * 100, "duration_s": 2}])

    [row] = result.preview.rows
    assert row["text"].endswith("…") and len(row["text"]) == len("One: ") + tools.PREVIEW_PROMPT_CHARS


def _shots(count, **override):
    return [{"label": f"Shot {index}", "prompt": "Instruction", "duration_s": 4, **override} for index in range(count)]


@pytest.mark.parametrize(
    "shots",
    [
        None,
        [],
        _shots(25),
        _shots(1, duration_s=1.5),
        _shots(1, duration_s=15.5),
        _shots(1, duration_s=True),
        _shots(1, duration_s="soon"),
        _shots(1, duration_s=float("nan")),
        _shots(1, label="x" * 35),
        _shots(1, label="   "),
        _shots(1, prompt=""),
        ["Shot 1"],
    ],
)
async def test_split_refuses_invalid_shots(project, shots):
    for method in ("execute", "execute_confirmed"):
        assert _code(await getattr(SplitSynopsisTool(), method)(_context(project["id"]), shots=shots)) == "invalid_arguments"


async def test_split_accepts_the_bounds_and_needs_a_reachable_project(project):
    assert len(_data(await SplitSynopsisTool().execute(_context(project["id"]), shots=_shots(24, duration_s=2)))["proposal"]) == 24
    assert _code(await SplitSynopsisTool().execute(_context(project["id"], user_id="user-2"), shots=_shots(1))) == "project_not_found"
    assert _code(await SplitSynopsisTool().execute_confirmed(ToolContext(user_id="user-1"), shots=_shots(1))) == "project_not_found"


@pytest.fixture
def continuity_project(db, make_project):
    return make_project(
        clips=[
            _clip("a", 0, 4, label="Arrival"),
            _clip("b", 4, 5, label="Bridge"),
            _clip("c", 9, 20, label="Gate"),
            _clip("d", 29, 30, label="Archive", stage="source"),
        ],
        prompts=[_prompt("pa", "Dolly in on the rider", "a"), _prompt("pb", "Static shot of the bridge, a neon sign", "b", 4, 5)],
        frames=[_frame("fa", "a"), _frame("fc", "c", role="last")],
        direction={"univers": "No neon"},
    )


def _issues(seam):
    return [(issue["kind"], issue.get("shot_id")) for issue in seam["issues"]]


async def test_continuity_runs_the_server_checks_seam_by_seam(continuity_project):
    result = await CheckContinuityTool().execute(_context(continuity_project["id"]))

    data = _data(result)
    assert data["project_id"] == continuity_project["id"]
    assert datetime.fromisoformat(data["checked_at"]).tzinfo is not None
    assert [(seam["from_shot_id"], seam["to_shot_id"], seam["from_label"], seam["to_label"]) for seam in data["seams"]] == [
        ("a", "b", "Arrival", "Bridge"),
        ("b", "c", "Bridge", "Gate"),
    ]
    first, second = data["seams"]
    assert _issues(first) == [("conflict", "b"), ("fl2va_no_frame", "b"), ("camera_change", None)]
    assert _issues(second) == [("no_instruction", "c"), ("duration", "c"), ("fl2va_no_frame", "c")]
    assert first["issues"][0] == {
        "kind": "conflict",
        "text": "“Bridge”: The global direction excludes neon lights.",
        "fix": "Rewrite the instruction so it agrees with the direction.",
        "shot_id": "b",
        "rule": "noNeon",
    }
    assert first["issues"][2]["text"] == "The camera move changes from “dolly” in “Arrival” to “static shot” in “Bridge”."
    assert second["issues"][1]["text"] == "“Gate” lasts 20 s; a generated shot lasts 2 to 15 s."
    assert all(issue["fix"] for seam in data["seams"] for issue in seam["issues"])
    assert result.preview is None
    assert _stored(continuity_project["id"])["version"] == 1


async def test_continuity_merges_the_seams_the_page_measured(continuity_project):
    page_seams = [
        {"fromShotId": "a", "toShotId": "b", "issues": [{"kind": "lum", "text": "“Bridge” is brighter than the previous shot"}], "measured": True},
        {"fromShotId": "c", "toShotId": "new", "issues": [{"kind": "warm", "text": "“New” is warmer"}], "measured": True},
        {"fromShotId": "c", "toShotId": "ghost", "issues": [{"kind": "warm", "text": "unknown shot"}], "measured": True},
        {"fromShotId": "c", "toShotId": "d", "issues": [{"kind": "identity", "text": "Check the identity"}, {"kind": 3}], "measured": True},
        "junk",
    ]
    page_shots = [{"id": "new", "label": "Unsaved shot"}]

    data = _data(await CheckContinuityTool().execute(_context(continuity_project["id"], seams=page_seams, shots=page_shots)))

    by_pair = {(seam["from_shot_id"], seam["to_shot_id"]): seam for seam in data["seams"]}
    assert list(by_pair) == [("a", "b"), ("b", "c"), ("c", "d"), ("c", "new")]
    assert by_pair[("a", "b")]["issues"][-1] == {
        "kind": "lum",
        "text": "“Bridge” is brighter than the previous shot",
        "fix": "Match the shot's exposure to the previous shot.",
    }
    assert by_pair[("c", "d")]["issues"] == [
        {"kind": "identity", "text": "Check the identity", "fix": "Regenerate one of the two takes with the same look or identity reference."}
    ]
    assert (by_pair[("c", "new")]["to_label"], by_pair[("c", "new")]["issues"][0]["fix"]) == ("Unsaved shot", "Match the shot's color temperature to the previous shot.")


async def test_continuity_of_a_ref2va_project_in_french(db, make_project):
    project = make_project(
        clips=[_clip("a", 0, 4, label="Arrivée"), _clip("b", 4, 4, label="Pont")],
        prompts=[_prompt("pa", "Survol de la ville", "a"), _prompt("pb", "Plan fixe sur le pont, caméra à l’épaule", "b", 4, 4)],
        direction={"photographie": "Caméra stable", "mode": "Ref2VA"},
    )
    project["doc"]["promptLanguage"] = "fr"
    projects.save_project(project["id"], project["doc"], 1)

    data = _data(await CheckContinuityTool().execute(_context(project["id"])))

    [seam] = data["seams"]
    assert _issues(seam) == [("conflict", "b"), ("camera_change", None)]
    assert seam["issues"][0]["rule"] == "stableCamera"
    assert seam["issues"][1]["text"] == "The camera move changes from “survol” in “Arrivée” to “plan fixe” in “Pont”."


async def test_continuity_of_a_single_shot_and_of_a_clean_project(db, make_project):
    alone = make_project(clips=[_clip("a", 0, 1, label="Alone")], prompts=[_prompt("pa", "A rider", "a", 0, 1)], frames=[_frame("fa", "a")])
    clean = make_project(
        clips=[_clip("a", 0, 4), _clip("b", 4, 4)],
        prompts=[_prompt("pa", "Dolly in on the rider", "a"), _prompt("pb", "Dolly out over the bridge", "b", 4, 4)],
        frames=[_frame("fa", "a"), _frame("fb", "b", role="début")],
    )

    [seam] = _data(await CheckContinuityTool().execute(_context(alone["id"])))["seams"]
    assert (seam["from_shot_id"], seam["to_shot_id"], _issues(seam)) == ("a", "a", [("duration", "a")])
    assert _data(await CheckContinuityTool().execute(_context(clean["id"])))["seams"] == []


async def test_continuity_refuses_a_project_the_caller_cannot_reach(continuity_project):
    assert _code(await CheckContinuityTool().execute(_context(continuity_project["id"], user_id="user-2"))) == "project_not_found"
    assert _code(await CheckContinuityTool().execute(ToolContext(user_id="user-1"))) == "project_not_found"
    assert _data(await CheckContinuityTool().execute(_context(continuity_project["id"], user_id="admin-1", is_admin=True)))["seams"]
