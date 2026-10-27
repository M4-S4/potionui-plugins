import json

import pytest

from backend import core_bridge, presets, projects, routes_exports, takes
from backend.chat import cards, control, edits, tools
from backend.chat.control import (
    AddShotsTool,
    AssembleTool,
    DeleteShotsTool,
    ExportVideoTool,
    GenerateTool,
    LabelTakeTool,
    ReadProjectTool,
    StatusTool,
    UpdateShotsTool,
)
from backend.exports import jobs
from src.plugin_api.chat import ToolContext

NEW_TOOLS = [
    (ReadProjectTool, "vp_get_project", False, "core"),
    (AddShotsTool, "vp_add_shots", False, "core"),
    (UpdateShotsTool, "vp_update_shots", False, "core"),
    (DeleteShotsTool, "vp_delete_shots", True, "core"),
    (GenerateTool, "vp_generate", True, "vp_production"),
    (StatusTool, "vp_status", False, "vp_production"),
    (LabelTakeTool, "vp_label_take", False, "vp_production"),
    (AssembleTool, "vp_assemble", False, "vp_production"),
    (ExportVideoTool, "vp_export_video", False, "vp_production"),
]
OLD_TOOLS = [tools.WriteShotPromptTool, tools.FixConflictsTool, tools.SplitSynopsisTool, tools.CheckContinuityTool]
ENGINE = {"quality": "draft", "variants": 1, "backend": "b-local", "preset": presets.WAN, "model": None}
BIBLE = {
    "characters": [{"id": "c-mara", "label": "Mara", "text": "a courier in a red coat", "props": "", "references": []}],
    "places": [{"id": "p-dock", "label": "Dock", "text": "a foggy harbor", "references": []}],
}


def _clip(shot_id, start, dur, **fields):
    return {"id": shot_id, "start": start, "dur": dur, **fields}


def _doc(make_doc, **parts):
    doc = make_doc(
        clips=[
            _clip("s1", 0, 4, label="Arrival"),
            _clip("s2", 4, 5, label="Bridge"),
            _clip("s3", 9, 3, label="Exit"),
        ],
        prompts=[
            {"id": "p1", "shotId": "s1", "start": 0, "dur": 4, "text": "Wide shot of the rider"},
            {"id": "p3", "shotId": "s3", "start": 9, "dur": 3, "text": "The rider leaves"},
        ],
        frames=[
            {"id": "f3", "shotId": "s3", "time": 9, "assetId": "img-gate", "role": "first", "strength": 100},
            {"id": "f3l", "shotId": "s3", "time": 11.96, "assetId": "img-gate", "role": "last", "strength": 100},
        ],
        references=[{"id": "r-look", "name": "Look", "assetId": "img-look", "scope": {"type": "global"}}],
        assets=[
            {"id": "img-gate", "name": "Gate", "kind": "image"},
            {"id": "img-look", "name": "Look", "kind": "image"},
            {"id": "vid-run", "name": "Run", "kind": "video"},
        ],
        **parts,
    )
    doc["engine"] = dict(ENGINE)
    doc["bible"] = json.loads(json.dumps(BIBLE))
    return doc


@pytest.fixture(autouse=True)
def no_cards():
    cards.clear()
    yield
    cards.clear()


@pytest.fixture
def project(core, make_project, make_doc, clock):
    core.use_wan()
    return make_project(doc=_doc(make_doc))


def _context(project_id, user_id="user-1", is_admin=False, turn="turn-1"):
    page = {"contextId": turn, "projectId": project_id}
    return ToolContext(user_id=user_id, mode_id="video-producer", is_admin=is_admin, session_metadata={"video_producer": page})


def _stored(project_id):
    return projects.get_project(project_id)


def _data(result):
    assert result.success, result.error
    return json.loads(result.data)


def _code(result):
    assert not result.success and result.data == ""
    return result.error.split(":", 1)[0]


def _clips(project_id):
    return [(clip["id"], clip["start"], clip["dur"]) for clip in _stored(project_id)["doc"]["clips"]]


def _done_take(project_id, shot_id, variant, quality="draft", label=None, **fields):
    return takes.create_take(
        {
            "project_id": project_id,
            "shot_id": shot_id,
            "user_id": "user-1",
            "quality": quality,
            "variant": variant,
            "status": "done",
            "kind": "render",
            "generation_id": f"gen-{shot_id}-{variant}-{quality}",
            "file_path": f"generations/{shot_id}/{variant}.mp4",
            "file_id": f"file-{shot_id}-{variant}",
            "width": 832,
            "height": 480,
            "duration_s": 5.0,
            "fps": 16.0,
            "preset_id": presets.WAN,
            **({"label": label} if label else {}),
            **fields,
        }
    )


@pytest.mark.parametrize("tool, name, approval, group", NEW_TOOLS)
def test_each_new_tool_is_built_without_arguments_scoped_to_the_mode_and_grouped(tool, name, approval, group):
    instance = tool()

    assert (instance.name, instance.requires_approval, instance.modes, instance.context_group) == (name, approval, ["video-producer"], group)
    assert instance.group == "Video Producer"
    assert instance.description and instance.hint and instance.user_description and instance.icon and instance.label
    assert instance.parameters["type"] == "object"
    assert set(instance.parameters["required"]) <= set(instance.parameters["properties"])


def test_every_schema_fits_the_hosts_budget_and_the_tools_sent_up_front_stay_small():
    every = [tool() for tool in OLD_TOOLS] + [tool() for tool, *_ in NEW_TOOLS]
    sizes = {tool.name: len(json.dumps(tool.to_schema())) for tool in every}
    up_front = [tool for tool in every if tool.context_group == "core"]

    assert max(sizes.values()) <= 2000, sizes
    assert sum(sizes[tool.name] for tool in up_front) <= 8500
    assert all(len(tool().hint) <= 120 and "\n" not in tool().hint for tool, *_ in NEW_TOOLS)
    assert len({tool.name for tool in every}) == len(every)


async def test_reading_lists_the_shots_with_their_prompt_cast_frames_references_and_takes(project):
    _done_take(project["id"], "s1", "A", label="final")
    stored = _stored(project["id"])
    stored["doc"]["clips"][0]["cast"] = {"characters": ["c-mara"], "place": "p-dock"}
    stored["doc"]["clips"][2]["referenceOverrides"] = {"exclude": ["r-look"]}
    projects.save_project(project["id"], stored["doc"], stored["version"])

    data = _data(await ReadProjectTool().execute(_context(project["id"])))

    assert (data["project_id"], data["version"], data["engine"]["preset"]) == (project["id"], 2, presets.WAN)
    assert data["bible"] == {"characters": [{"id": "c-mara", "label": "Mara"}], "places": [{"id": "p-dock", "label": "Dock"}]}
    assert [item["id"] for item in data["media"]] == ["img-gate", "img-look", "vid-run"]
    first, second, third = data["shots"]
    assert {key: first[key] for key in ("id", "n", "label", "start_s", "duration_s", "prompt", "cast")} == {
        "id": "s1",
        "n": 1,
        "label": "Arrival",
        "start_s": 0,
        "duration_s": 4,
        "prompt": "Wide shot of the rider",
        "cast": ["Mara", "Dock"],
    }
    assert [(take["variant"], take["label"], take["status"]) for take in first["takes"]] == [("A", "final", "done")]
    assert second["prompt"] == "" and second["takes"] == []
    assert (third["first_frame"], third["last_frame"]) == ("Gate", "Gate")
    assert third["references"] == [{"id": "r-look", "name": "Look", "space": "identity", "own": False, "excluded": True}]


async def test_reading_says_which_references_a_shot_takes_from_its_cast_and_which_it_leaves_for_a_card_it_does_not_cast(project):
    stored = _stored(project["id"])
    doc = stored["doc"]
    doc["references"].append({"id": "r-back", "name": "Back", "space": "identite", "type": "Personnage", "role": "Identité", "assetId": "img-gate", "scope": {"type": "shot", "shotId": "s3"}})
    doc["bible"]["characters"][0]["references"] = ["r-look", "r-back"]
    doc["clips"][0]["cast"] = {"characters": ["c-mara"]}
    projects.save_project(project["id"], doc, stored["version"])

    first, second, third = _data(await ReadProjectTool().execute(_context(project["id"])))["shots"]

    assert first["references"] == [
        {"id": "r-look", "name": "Look", "space": "identity", "own": False},
        {"id": "r-back", "name": "Back", "space": "identity", "own": False, "cast": True},
    ]
    assert second["references"] == [{"id": "r-look", "name": "Look", "space": "identity", "own": False, "not_cast": True}]
    assert third["references"] == [
        {"id": "r-back", "name": "Back", "space": "identity", "own": True},
        {"id": "r-look", "name": "Look", "space": "identity", "own": False, "not_cast": True},
    ]


async def test_reading_names_shots_by_number_or_label_and_refuses_an_unknown_one(project):
    picked = _data(await ReadProjectTool().execute(_context(project["id"]), shots=["2", "exit"]))
    unknown = await ReadProjectTool().execute(_context(project["id"]), shots=["Finale"])

    assert [shot["id"] for shot in picked["shots"]] == ["s2", "s3"]
    assert _code(unknown) == "shot_not_found"


async def test_reading_stays_within_its_budget_and_says_how_many_shots_it_left_out(project, monkeypatch):
    monkeypatch.setattr(control, "MAX_READ_CHARS", 1000)

    data = _data(await ReadProjectTool().execute(_context(project["id"])))

    assert 1 <= len(data["shots"]) < 3
    assert data["more_shots"] == 3 - len(data["shots"])


async def test_a_tool_without_an_open_project_or_on_someone_elses_project_answers_project_not_found(project):
    closed = ToolContext(user_id="user-1", mode_id="video-producer", session_metadata={})

    assert _code(await ReadProjectTool().execute(closed)) == "project_not_found"
    assert _code(await AddShotsTool().execute(_context(project["id"], user_id="user-2"), shots=[{"label": "X", "duration_s": 3, "prompt": "x"}])) == "project_not_found"
    assert _code(await StatusTool().execute(_context(project["id"], user_id="user-2"))) == "project_not_found"


async def test_adding_shots_after_a_shot_lays_the_timeline_out_again_and_saves_an_assistant_version(project):
    result = await AddShotsTool().execute(
        _context(project["id"]),
        shots=[{"label": "Close-up", "duration_s": 2.5, "prompt": "Close on Mara's hands", "characters": ["mara"], "place": "Dock"}],
        after="1",
    )

    data = _data(result)
    stored = _stored(project["id"])
    doc = stored["doc"]
    [added] = data["added"]
    assert (data["version"], stored["version"]) == (2, 2)
    assert {key: added[key] for key in ("n", "label", "start_s", "duration_s")} == {"n": 2, "label": "Close-up", "start_s": 4, "duration_s": 2.52}
    assert [clip["id"] for clip in doc["clips"]] == ["s1", added["id"], "s2", "s3"]
    assert [clip["start"] for clip in doc["clips"]] == [0, 4, 6.52, 11.52]
    assert next(clip for clip in doc["clips"] if clip["id"] == added["id"])["cast"] == {"characters": ["c-mara"], "place": "p-dock"}
    assert {prompt["shotId"]: prompt["start"] for prompt in doc["prompts"]} == {"s1": 0, "s3": 11.52, added["id"]: 4}
    assert [(frame["id"], frame["time"]) for frame in doc["frames"]] == [("f3", 11.52), ("f3l", 14.48)]
    assert projects.list_versions(project["id"])[0]["label"] == "Assistant"


async def test_adding_shots_at_the_start_or_the_end(project):
    start = _data(await AddShotsTool().execute(_context(project["id"]), shots=[{"label": "Title", "duration_s": 2, "prompt": "Black"}], after="start"))
    end = _data(await AddShotsTool().execute(_context(project["id"]), shots=[{"label": "Credits", "duration_s": 3, "prompt": "Night"}]))

    ids = [clip_id for clip_id, _, _ in _clips(project["id"])]
    assert ids == [start["added"][0]["id"], "s1", "s2", "s3", end["added"][0]["id"]]
    assert _clips(project["id"])[-1][1:] == (14, 3)


@pytest.mark.parametrize(
    "shot, code",
    [
        ({"label": "", "duration_s": 3, "prompt": "x"}, "invalid_arguments"),
        ({"label": "A label far too long for the storyboard band", "duration_s": 3, "prompt": "x"}, "invalid_arguments"),
        ({"label": "Short", "duration_s": 30, "prompt": "x"}, "invalid_arguments"),
        ({"label": "Cast", "duration_s": 3, "prompt": "x", "characters": ["Nobody"]}, "card_not_found"),
    ],
)
async def test_a_shot_the_document_refuses_saves_nothing(project, shot, code):
    result = await AddShotsTool().execute(_context(project["id"]), shots=[shot])

    assert _code(result) == code
    assert _stored(project["id"])["version"] == 1


async def test_lengthening_a_shot_moves_its_prompt_frames_and_the_shots_after_it_and_counts_an_edit(project):
    data = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "Arrival", "duration_s": 6, "label": "Arrival wide"}]))

    doc = _stored(project["id"])["doc"]
    assert data["updated"] == [{"shot_id": "s1", "changed": ["label", "duration_s"]}]
    assert [(clip["id"], clip["start"], clip["dur"]) for clip in doc["clips"]] == [("s1", 0, 6), ("s2", 6, 5), ("s3", 11, 3)]
    assert doc["clips"][0]["label"] == "Arrival wide" and doc["clips"][0]["revision"] == 1
    assert {prompt["id"]: (prompt["start"], prompt["dur"]) for prompt in doc["prompts"]} == {"p1": (0, 6), "p3": (11, 3)}
    assert [(frame["id"], frame["time"]) for frame in doc["frames"]] == [("f3", 11), ("f3l", 13.96)]


async def test_moving_casting_and_framing_shots_in_one_call(project):
    data = _data(
        await UpdateShotsTool().execute(
            _context(project["id"]),
            updates=[
                {"shot": "s3", "position": 1},
                {"shot": "Bridge", "characters": ["Mara"], "place": "dock", "first_frame": "Gate", "takes_per_run": 3, "chain": False},
            ],
        )
    )

    doc = _stored(project["id"])["doc"]
    bridge = next(clip for clip in doc["clips"] if clip["id"] == "s2")
    assert [clip["id"] for clip in doc["clips"]] == ["s3", "s1", "s2"]
    assert [clip["start"] for clip in doc["clips"]] == [0, 3, 7]
    assert data["updated"] == [
        {"shot_id": "s3", "changed": ["position"]},
        {"shot_id": "s2", "changed": ["cast", "first_frame", "takes_per_run", "chain"]},
    ]
    assert bridge["cast"] == {"characters": ["c-mara"], "place": "p-dock"}
    assert (bridge["drafts"], bridge["firstFromPrevious"], bridge["revision"]) == (3, False, 1)
    assert [frame for frame in doc["frames"] if frame["shotId"] == "s2"] == [
        {"id": frame["id"], "shotId": "s2", "time": 7, "assetId": "img-gate", "role": "first", "strength": 100}
        for frame in doc["frames"]
        if frame["shotId"] == "s2"
    ]
    assert next(frame for frame in doc["frames"] if frame["id"] == "f3")["time"] == 0


async def test_references_are_attached_removed_left_out_and_used_again(project):
    first = _data(
        await UpdateShotsTool().execute(
            _context(project["id"]),
            updates=[{"shot": "s2", "add_references": [{"media": "Run", "space": "motion"}], "exclude_references": ["r-look"]}],
        )
    )
    doc = _stored(project["id"])["doc"]
    own = next(ref for ref in doc["references"] if ref.get("scope", {}).get("type") == "shot")
    second = _data(
        await UpdateShotsTool().execute(
            _context(project["id"]), updates=[{"shot": "s2", "remove_references": [own["id"]], "include_references": ["r-look"]}]
        )
    )

    clip = next(clip for clip in _stored(project["id"])["doc"]["clips"] if clip["id"] == "s2")
    assert first["updated"][0]["changed"] == ["references"] and second["updated"][0]["changed"] == ["references"]
    assert {key: own[key] for key in ("name", "space", "type", "assetId", "role", "scope")} == {
        "name": "Run",
        "space": "mouvement",
        "type": "Control video",
        "assetId": "vid-run",
        "role": "Mouvement",
        "scope": {"type": "shot", "shotId": "s2"},
    }
    assert [ref["id"] for ref in _stored(project["id"])["doc"]["references"]] == ["r-look"]
    assert "referenceOverrides" not in clip and clip["revision"] == 2


@pytest.mark.parametrize(
    "update, code",
    [
        ({"shot": "s2", "prompt": "New text"}, "invalid_arguments"),
        ({"shot": "s2"}, "invalid_arguments"),
        ({"shot": "s9", "label": "x"}, "shot_not_found"),
        ({"shot": "s2", "first_frame": "Nothing"}, "media_not_found"),
        ({"shot": "s2", "add_references": [{"media": "Gate", "space": "motion"}]}, "invalid_arguments"),
        ({"shot": "s2", "remove_references": ["r-look"]}, "reference_not_found"),
    ],
)
async def test_an_update_the_document_refuses_saves_nothing(project, update, code):
    result = await UpdateShotsTool().execute(_context(project["id"]), updates=[update])

    assert _code(result) == code
    assert _stored(project["id"])["version"] == 1


async def test_writing_a_prompt_through_an_update_points_to_the_prompt_tool(project):
    result = await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s2", "prompt": "New text"}])

    assert "vp_write_shot_prompt" in result.error


async def test_lengthening_a_shot_past_its_placed_take_releases_the_take_back_to_draft(project):
    take = _done_take(project["id"], "s1", "A", label="final")
    stored = _stored(project["id"])
    edits.place_take(stored["doc"], stored["doc"]["clips"][0], takes.public(take), "en")
    projects.save_project(project["id"], stored["doc"], stored["version"])

    data = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s1", "duration_s": 8}]))

    clip = _stored(project["id"])["doc"]["clips"][0]
    assert data["updated"] == [{"shot_id": "s1", "changed": ["duration_s"], "released_take": take["id"]}]
    assert (clip["take"], clip["assetId"], clip["stage"]) == (None, None, "todo")
    assert takes.get_take(take["id"])["label"] == "draft"


def _edit_stored(project_id, change):
    stored = _stored(project_id)
    change(stored["doc"])
    projects.save_project(project_id, stored["doc"], stored["version"])


def _before(preview):
    return [change["before"] for change in preview.changes]


async def _approved(tool, context, **arguments):
    _data(await tool.execute(context, **arguments))
    return await tool.execute_confirmed(context, **arguments)


async def test_chain_sets_the_shots_own_choice_either_way_and_off_drops_the_image_taken_from_the_previous_shot(project, make_doc):
    frame_of = {"shotId": "s1", "takeId": "t0", "assetId": "gen-t0", "at": 3.96}
    still = make_doc(assets=[{"id": "still-1", "name": "1-frame-4s.png", "origin": {"kind": "library", "itemId": "it-9"}, "frameOf": frame_of}])["assets"][0]

    def setup(doc):
        doc["firstFromPrevious"] = False
        doc["assets"].append(still)
        doc["frames"].append({"id": "f2", "shotId": "s2", "time": 4, "assetId": "still-1", "role": "first", "strength": 100})

    _edit_stored(project["id"], setup)
    on = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s2", "chain": True}, {"shot": "s1", "chain": True}]))
    clips = {clip["id"]: clip for clip in _stored(project["id"])["doc"]["clips"]}
    off = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s2", "chain": False}, {"shot": "s3", "chain": True}]))
    doc = _stored(project["id"])["doc"]
    read = _data(await ReadProjectTool().execute(_context(project["id"])))

    assert on["updated"] == [{"shot_id": "s2", "changed": ["chain"]}, {"shot_id": "s1", "changed": []}]
    assert clips["s2"]["firstFromPrevious"] is True and "firstFromPrevious" not in clips["s1"]
    assert off["updated"] == [{"shot_id": "s2", "changed": ["chain"]}, {"shot_id": "s3", "changed": ["chain"]}]
    assert [clip.get("firstFromPrevious") for clip in doc["clips"]] == [None, False, True]
    assert [frame["id"] for frame in doc["frames"]] == ["f3", "f3l"]
    assert [shot.get("chain") for shot in read["shots"]] == [None, False, True]


async def test_a_shot_is_not_lengthened_past_what_its_source_media_has_left(project):
    _edit_stored(project["id"], lambda doc: (doc["assets"][2].update(srcDur=8), doc["clips"][1].update(assetId="vid-run", srcIn=1, stage="source")))

    data = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s2", "duration_s": 9}]))

    assert data["updated"] == [{"shot_id": "s2", "changed": ["duration_s"], "duration_limit": {"max_s": 7, "by": "source"}}]
    assert _clips(project["id"]) == [("s1", 0, 4), ("s2", 4, 7), ("s3", 11, 3)]


async def test_a_shot_holding_a_take_is_not_lengthened_past_what_its_engine_makes(project, core):
    core.use_openrouter()
    take = _done_take(project["id"], "s1", "A", label="final")

    def setup(doc):
        edits.place_take(doc, doc["clips"][0], takes.public(take), "en")
        doc["clips"][0]["engine"] = {"preset": presets.OPENROUTER_VIDEO, "model": "vendor/video-1"}

    _edit_stored(project["id"], setup)
    data = _data(await UpdateShotsTool().execute(_context(project["id"]), updates=[{"shot": "s1", "duration_s": 14}]))

    assert data["updated"] == [{"shot_id": "s1", "changed": ["duration_s"], "released_take": take["id"], "duration_limit": {"max_s": 10, "by": "engine"}}]
    assert _clips(project["id"])[0] == ("s1", 0, 10)


async def test_deleting_shots_previews_them_and_deletes_only_once_approved(project):
    _done_take(project["id"], "s3", "A")
    preview = await DeleteShotsTool().execute(_context(project["id"]), shots=["Exit", "s3"])

    assert _data(preview) == {"status": "pending_approval", "project_id": project["id"], "shots": ["s3"]}
    assert preview.preview.kind == "timeline" and preview.preview.target == "1 shot"
    assert preview.preview.rows == [{"range": "9–12 s", "text": "Exit: The rider leaves", "op": "remove"}]
    assert _before(preview.preview) == [{"id": "s3", "n": 3, "label": "Exit", "start_s": 9, "duration_s": 3, "prompt": "The rider leaves"}]
    assert _stored(project["id"])["version"] == 1

    confirmed = _data(await DeleteShotsTool().execute_confirmed(_context(project["id"]), shots=["Exit", "s3"]))

    doc = _stored(project["id"])["doc"]
    assert confirmed == {"project_id": project["id"], "version": 2, "deleted": ["s3"]}
    assert [(clip["id"], clip["start"]) for clip in doc["clips"]] == [("s1", 0), ("s2", 4)]
    assert doc["frames"] == [] and [prompt["id"] for prompt in doc["prompts"]] == ["p1"]
    assert len(takes.list_takes(project["id"])) == 1


async def test_an_approved_deletion_removes_the_shot_the_card_showed_even_after_it_moved(project):
    context = _context(project["id"])
    card = await DeleteShotsTool().execute(context, shots=["2"])
    _edit_stored(project["id"], lambda doc: doc["clips"].insert(0, doc["clips"].pop(2)))
    again = await DeleteShotsTool().execute(_context(project["id"], turn="approval"), shots=["2"])

    confirmed = _data(await DeleteShotsTool().execute_confirmed(context, shots=["2"]))

    assert _before(card.preview)[0]["id"] == "s2" and _before(again.preview)[0]["id"] == "s1"
    assert confirmed["deleted"] == ["s2"]
    assert [clip["id"] for clip in _stored(project["id"])["doc"]["clips"]] == ["s3", "s1"]


async def test_an_approved_deletion_of_a_shot_deleted_since_the_card_deletes_nothing(project):
    context = _context(project["id"])
    await DeleteShotsTool().execute(context, shots=["Bridge", "Exit"])
    _edit_stored(project["id"], lambda doc: doc["clips"].pop(1))

    result = await DeleteShotsTool().execute_confirmed(context, shots=["Bridge", "Exit"])

    assert _code(result) == "card_out_of_date" and "Bridge no longer exists" in result.error
    assert [clip["id"] for clip in _stored(project["id"])["doc"]["clips"]] == ["s1", "s3"]
    assert _stored(project["id"])["version"] == 2


async def test_an_approval_the_server_has_no_card_for_runs_nothing(project, core):
    deletion = await DeleteShotsTool().execute_confirmed(_context(project["id"]), shots=["s2"])
    generation = await GenerateTool().execute_confirmed(_context(project["id"]), shots=["s1"])

    assert _code(deletion) == "card_expired" and _code(generation) == "card_expired"
    assert len(_stored(project["id"])["doc"]["clips"]) == 3 and core.submitted == []


async def test_a_card_belongs_to_the_turn_that_showed_it(project):
    turn = _context(project["id"])
    later = _context(project["id"], turn="turn-2")
    await DeleteShotsTool().execute(turn, shots=["Exit"])

    assert _code(await DeleteShotsTool().execute_confirmed(later, shots=["Exit"])) == "card_expired"
    assert _data(await DeleteShotsTool().execute_confirmed(turn, shots=["Exit"]))["deleted"] == ["s3"]
    assert _code(await DeleteShotsTool().execute_confirmed(turn, shots=["Exit"])) == "card_expired"


async def test_generating_previews_the_estimate_and_starts_nothing_before_approval(project, core):
    result = await GenerateTool().execute(_context(project["id"]), shots=["1", "Bridge"], takes_per_shot=2)

    data = _data(result)
    fields = {field["label"]: field["value"] for field in result.preview.fields}
    assert data["status"] == "pending_approval" and data["takes"] == 4 and data["shots"] == ["s1", "s2"]
    assert result.preview.kind == "generation" and result.preview.summary == "Generate 4 takes for 2 shots"
    assert fields["Shots"] == "Arrival, Bridge" and fields["Takes"] == "4" and fields["Quality"] == "draft"
    assert fields["GPU minutes"].endswith("of 600 left this month")
    assert _before(result.preview) == [
        {
            "shots": [{"id": "s1", "duration_s": 4, "takes": 2}, {"id": "s2", "duration_s": 5, "takes": 2}],
            "quality": "draft",
            "engine": presets.WAN,
            "model": None,
            "presets": {"s1": presets.WAN, "s2": presets.WAN},
        }
    ]
    assert takes.list_takes(project["id"]) == [] and core.submitted == []


async def test_generating_once_approved_starts_each_shots_own_number_of_takes(project, core):
    _edit_stored(project["id"], lambda doc: doc["clips"][1].update(drafts=2, firstFromPrevious=False))

    data = _data(await _approved(GenerateTool(), _context(project["id"]), shots=["s1", "s2"]))

    assert [(take["shot_id"], take["variant"], take["quality"]) for take in data["takes"]] == [("s1", "A", "draft"), ("s2", "A", "draft"), ("s2", "B", "draft")]
    assert len(takes.list_takes(project["id"])) == 3 and len(core.submitted) == 2


async def test_an_administrator_generates_on_a_users_project_as_its_owner(project, core):
    await _approved(GenerateTool(), _context(project["id"], user_id="admin-1", is_admin=True), shots=["s1"])

    assert [user_id for user_id, _ in core.submitted] == ["user-1"]


async def test_an_approved_generation_starts_the_quality_and_takes_the_card_showed(project, core):
    context = _context(project["id"])
    card = await GenerateTool().execute(context, shots=["Arrival"])

    def change(doc):
        doc["engine"]["quality"] = "final"
        doc["clips"][0]["drafts"] = 3

    _edit_stored(project["id"], change)
    again = await GenerateTool().execute(_context(project["id"], turn="approval"), shots=["Arrival"])
    data = _data(await GenerateTool().execute_confirmed(context, shots=["Arrival"]))

    assert _before(card.preview) != _before(again.preview)
    assert [(take["shot_id"], take["variant"], take["quality"]) for take in data["takes"]] == [("s1", "A", "draft")]


async def test_an_approved_generation_whose_estimate_rose_or_whose_shot_is_gone_starts_nothing(project, core):
    context = _context(project["id"])
    await GenerateTool().execute(context, shots=["s1"])
    await GenerateTool().execute(context, shots=["s2", "s3"])
    _edit_stored(project["id"], lambda doc: doc["clips"][0].update(dur=12))
    _edit_stored(project["id"], lambda doc: doc["clips"].pop(2))

    longer = await GenerateTool().execute_confirmed(context, shots=["s1"])
    gone = await GenerateTool().execute_confirmed(context, shots=["s2", "s3"])

    assert _code(longer) == "card_out_of_date" and "The estimate rose to 1 take and" in longer.error
    assert _code(gone) == "card_out_of_date" and "Exit no longer exists" in gone.error
    assert takes.list_takes(project["id"]) == [] and core.submitted == []


async def test_a_generation_refused_then_asked_again_after_a_change_starts_what_the_new_card_shows(project, core):
    _edit_stored(project["id"], lambda doc: doc["clips"][2].update(drafts=4, firstFromPrevious=False))
    first = await GenerateTool().execute(_context(project["id"], turn="turn-1"), shots=["3"])
    _data(await UpdateShotsTool().execute(_context(project["id"], turn="turn-2"), updates=[{"shot": "3", "takes_per_run": 1}]))
    second = await GenerateTool().execute(_context(project["id"], turn="turn-2"), shots=["3"])
    stale_check = await GenerateTool().execute(_context(project["id"], turn="approval"), shots=["3"])

    data = _data(await GenerateTool().execute_confirmed(_context(project["id"], turn="turn-2"), shots=["3"]))

    assert [_data(result)["takes"] for result in (first, second, stale_check)] == [4, 1, 1]
    assert _before(second.preview) == _before(stale_check.preview)
    assert [take["variant"] for take in data["takes"]] == ["A"] and len(takes.list_takes(project["id"])) == 1


async def test_a_deletion_refused_then_asked_again_after_a_reorder_deletes_the_shot_the_new_card_shows(project):
    first = await DeleteShotsTool().execute(_context(project["id"], turn="turn-1"), shots=["2"])
    _data(await UpdateShotsTool().execute(_context(project["id"], turn="turn-2"), updates=[{"shot": "Exit", "position": 2}]))
    second = await DeleteShotsTool().execute(_context(project["id"], turn="turn-2"), shots=["2"])
    await DeleteShotsTool().execute(_context(project["id"], turn="approval"), shots=["2"])

    data = _data(await DeleteShotsTool().execute_confirmed(_context(project["id"], turn="turn-2"), shots=["2"]))

    assert [_before(result.preview)[0]["id"] for result in (first, second)] == ["s2", "s3"]
    assert data["deleted"] == ["s3"]
    assert [clip["id"] for clip in _stored(project["id"])["doc"]["clips"]] == ["s1", "s2"]


async def test_a_new_preview_of_the_same_call_in_the_same_turn_replaces_its_card(project):
    turn = _context(project["id"])
    await DeleteShotsTool().execute(turn, shots=["2"])
    _edit_stored(project["id"], lambda doc: doc["clips"].insert(0, doc["clips"].pop(2)))
    await DeleteShotsTool().execute(turn, shots=["2"])

    assert _data(await DeleteShotsTool().execute_confirmed(turn, shots=["2"]))["deleted"] == ["s1"]


async def test_a_refused_approval_is_not_run_again_by_a_retry_and_the_next_turn_gets_a_new_card(project, core):
    turn = _context(project["id"])
    await GenerateTool().execute(turn, shots=["s1"])
    _edit_stored(project["id"], lambda doc: doc["clips"][0].update(dur=12))
    refused = await GenerateTool().execute_confirmed(turn, shots=["s1"])
    _edit_stored(project["id"], lambda doc: doc["clips"][0].update(dur=4))
    retried = await GenerateTool().execute_confirmed(turn, shots=["s1"])
    assert takes.list_takes(project["id"]) == []

    fresh = _data(await _approved(GenerateTool(), _context(project["id"], turn="turn-2"), shots=["s1"]))

    assert _code(refused) == "card_out_of_date" and retried.error == refused.error
    assert len(fresh["takes"]) == 1 and len(takes.list_takes(project["id"])) == 1


async def test_cards_are_kept_per_user_and_an_evicted_card_says_why(project, monkeypatch):
    monkeypatch.setattr(cards, "MAX_CARDS_PER_USER", 2)
    pending = _context(project["id"], turn="pending")
    await DeleteShotsTool().execute(pending, shots=["Exit"])
    for index in range(3):
        await DeleteShotsTool().execute(_context(project["id"], user_id="admin-1", is_admin=True, turn=f"admin-{index}"), shots=["Exit"])
    kept = _data(await DeleteShotsTool().execute_confirmed(pending, shots=["Exit"]))
    await DeleteShotsTool().execute(pending, shots=["Bridge"])
    for index in range(2):
        await DeleteShotsTool().execute(_context(project["id"], turn=f"newer-{index}"), shots=["Arrival"])

    evicted = await DeleteShotsTool().execute_confirmed(pending, shots=["Bridge"])

    assert kept["deleted"] == ["s3"]
    assert _code(evicted) == "card_expired" and "more than 2 newer cards of yours" in evicted.error
    assert [clip["id"] for clip in _stored(project["id"])["doc"]["clips"]] == ["s1", "s2"]


async def test_a_page_that_sends_no_context_id_gets_no_approval_card(project, core):
    bare = ToolContext(user_id="user-1", mode_id="video-producer", session_metadata={"video_producer": {"projectId": project["id"]}})

    deletion = await DeleteShotsTool().execute(bare, shots=["Exit"])
    generation = await GenerateTool().execute(bare, shots=["Exit"])

    assert _code(deletion) == "page_outdated" and _code(generation) == "page_outdated"
    assert "reload the page" in deletion.error


async def test_generating_without_an_engine_or_past_the_quota_is_refused_with_its_reason(project, core):
    core.quota = {"limit": 1, "used": 1, "remaining": 0.0, "exempt": False, "resets_at": None}
    blocked = await GenerateTool().execute(_context(project["id"]), shots=["s1"])
    stored = _stored(project["id"])
    stored["doc"]["engine"]["preset"] = None
    projects.save_project(project["id"], stored["doc"], stored["version"])
    no_engine = await GenerateTool().execute(_context(project["id"]), shots=["s1"])

    assert _code(blocked) == "blocked" and "GPU minutes" in blocked.error
    assert _code(no_engine) == "no_engine"
    assert _code(await GenerateTool().execute(_context(project["id"]), shots=["s1"], quality="best")) == "invalid_arguments"
    assert takes.list_takes(project["id"]) == []


async def test_the_status_lists_the_takes_in_flight_and_the_latest_exports(project, core, store):
    store[("max_parallel_jobs", None)] = "1"
    stored = _stored(project["id"])
    stored["doc"]["clips"][1]["firstFromPrevious"] = False
    projects.save_project(project["id"], stored["doc"], stored["version"])
    await _approved(GenerateTool(), _context(project["id"]), shots=["s1", "s2"])
    jobs.create_job(project["id"], "user-1", "web", "1080p")

    data = _data(await StatusTool().execute(_context(project["id"])))

    assert [(item["shot"], item["variant"], item["status"], item.get("queue_position")) for item in data["queue"]] == [
        ("Arrival", "A", "queued", None),
        ("Bridge", "A", "queued", 1),
    ]
    assert data["slots"] == {"in_flight": 1, "max": 1}
    assert data["gpu_minutes"]["limit"] == 600
    assert [(job["format"], job["status"]) for job in data["exports"]] == [("web", "queued")]


async def test_labelling_a_take_final_puts_it_on_its_shot_and_demotes_the_previous_final(project, store):
    store[("locale", "user-1")] = "fr"
    before = _done_take(project["id"], "s2", "A", label="final")
    take = _done_take(project["id"], "s2", "B")
    stored = _stored(project["id"])
    stored["doc"]["removedTakes"] = [take["id"]]
    projects.save_project(project["id"], stored["doc"], stored["version"])

    data = _data(await LabelTakeTool().execute(_context(project["id"]), shot="Bridge", variant="b", label="final"))

    doc = _stored(project["id"])["doc"]
    clip = doc["clips"][1]
    asset = next(item for item in doc["assets"] if item["id"] == f"gen-{take['id']}")
    assert {key: data[key] for key in ("take_id", "shot_id", "variant", "label", "placed", "version")} == {
        "take_id": take["id"],
        "shot_id": "s2",
        "variant": "B",
        "label": "final",
        "placed": True,
        "version": 3,
    }
    assert (clip["assetId"], clip["take"], clip["stage"], clip["srcIn"]) == (f"gen-{take['id']}", take["id"], "draft", 0)
    assert (asset["name"], asset["generated"], asset["srcDur"], asset["res"]) == ("Bridge · Brouillon B", True, 5.0, "832×480")
    assert asset["origin"] == {"kind": "history", "generationId": take["generation_id"], "fileId": take["file_id"]}
    assert "removedTakes" not in doc
    assert (takes.get_take(take["id"])["label"], takes.get_take(before["id"])["label"]) == ("final", "candidate")


async def test_labels_other_than_final_change_only_the_take(project):
    take = _done_take(project["id"], "s1", "A")

    data = _data(await LabelTakeTool().execute(_context(project["id"]), take_id=take["id"], label="rejected"))

    assert data["label"] == "rejected" and "version" not in data
    assert takes.get_take(take["id"])["label"] == "rejected" and _stored(project["id"])["version"] == 1


async def test_a_take_that_cannot_take_the_label_is_refused(project):
    running = takes.create_take({"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "variant": "A", "status": "running", "kind": "render"})
    final = _done_take(project["id"], "s2", "A", label="final")
    _done_take(project["id"], "s3", "A")
    _done_take(project["id"], "s3", "A", quality="final")

    assert _code(await LabelTakeTool().execute(_context(project["id"]), take_id=running["id"], label="final")) == "take_not_done"
    assert _code(await LabelTakeTool().execute(_context(project["id"]), take_id=final["id"], label="candidate")) == "take_is_final"
    assert _code(await LabelTakeTool().execute(_context(project["id"]), shot="s3", variant="A", label="final")) == "ambiguous_take"
    assert _code(await LabelTakeTool().execute(_context(project["id"]), shot="s3", variant="C", label="final")) == "take_not_found"
    assert _code(await LabelTakeTool().execute(_context(project["id"]), take_id="nope", label="final")) == "take_not_found"
    assert _code(await LabelTakeTool().execute(_context(project["id"]), take_id=final["id"], label="best")) == "invalid_arguments"


async def test_assembling_puts_every_final_take_on_its_shot_and_lists_the_shots_without_one(project):
    one = _done_take(project["id"], "s1", "A", label="final")
    three = _done_take(project["id"], "s3", "B", quality="final", label="final")
    _done_take(project["id"], "s2", "A", label="candidate")

    data = _data(await AssembleTool().execute(_context(project["id"])))

    doc = _stored(project["id"])["doc"]
    assert data["placed"] == [{"shot_id": "s1", "variant": "A"}, {"shot_id": "s3", "variant": "B"}]
    assert data["without_final"] == ["Bridge"] and data["version"] == 2
    assert [(clip["take"], clip["stage"]) for clip in doc["clips"]] == [(one["id"], "draft"), (None, "todo"), (three["id"], "final")]


async def test_exporting_queues_the_video_with_the_routes_checks(project, core, export_storage, monkeypatch):
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    nothing = await ExportVideoTool().execute(_context(project["id"]))
    monkeypatch.setattr(routes_exports, "exportable", lambda doc, listed, resolver: True)

    data = _data(await ExportVideoTool().execute(_context(project["id"]), format="social", resolution="720p"))
    again = await ExportVideoTool().execute(_context(project["id"]))

    assert _code(nothing) == "nothing_to_export"
    assert {key: data[key] for key in ("status", "format", "resolution")} == {"status": "queued", "format": "social", "resolution": "720p"}
    assert jobs.get_job(data["job_id"])["user_id"] == "user-1"
    assert _code(again) == "export_running"
    assert data["stems"] is False
    assert _code(await ExportVideoTool().execute(_context(project["id"]), format="prores")) == "invalid_request"
    jobs.cancel(jobs.get_job(data["job_id"]))
    master = _data(await ExportVideoTool().execute(_context(project["id"]), format="master", stems=True))
    assert (master["format"], master["stems"]) == ("master", True) and jobs.get_job(master["job_id"])["stems"] is True
    assert set(ExportVideoTool().parameters["properties"]) == {"format", "resolution", "ratio", "stems"}
    assert ExportVideoTool().parameters["properties"]["ratio"]["enum"] == ["9:16", "4:5", "1:1"]
    assert ExportVideoTool().parameters["properties"]["format"]["enum"] == ["web", "social", "master", "archive"]


async def test_a_change_retries_once_on_a_version_conflict_and_then_gives_up(project, monkeypatch):
    calls = []
    save = projects.save_project

    def conflicting(project_id, doc, version, label=None):
        calls.append(version)
        raise projects.VersionConflict(version + 1)

    monkeypatch.setattr(projects, "save_project", conflicting)
    result = await AddShotsTool().execute(_context(project["id"]), shots=[{"label": "X", "duration_s": 3, "prompt": "x"}])
    monkeypatch.setattr(projects, "save_project", save)

    assert _code(result) == "version_conflict" and calls == [1, 1]
    assert _stored(project["id"])["version"] == 1


async def test_a_final_take_is_named_in_the_language_the_page_shows_before_the_saved_one(project, store):
    store[("locale", "user-1")] = "en"
    take = _done_take(project["id"], "s1", "A")
    context = ToolContext(user_id="user-1", mode_id="video-producer", session_metadata={"video_producer": {"projectId": project["id"], "locale": "fr"}})

    await LabelTakeTool().execute(context, take_id=take["id"], label="final")

    names = [asset["name"] for asset in _stored(project["id"])["doc"]["assets"] if asset["id"] == f"gen-{take['id']}"]
    assert names == ["Arrival · Brouillon A"]
