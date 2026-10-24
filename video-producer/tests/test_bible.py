import copy
import json
from pathlib import Path

import pytest

from backend import bible, director, presets
from backend.chat.context import build_context
from backend.chat.tools import check_continuity
from backend.projects import DocError, migrate, validate_doc

LABEL_CASES = json.loads((Path(__file__).parent / "fixtures" / "bible_labels.json").read_text(encoding="utf-8"))

SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Quay"}
WOMAN = {
    "id": "c-woman",
    "label": "the red-haired woman",
    "text": "A woman in her thirties, short copper hair,\n navy wool raincoat",
    "props": "a brass lantern",
    "references": [],
}
FISHER = {"id": "c-fisher", "label": "the old fisherman", "text": "A man in his seventies, white beard, yellow oilskin.", "props": "", "references": []}
HARBOUR = {"id": "p-harbour", "label": "the harbour at dawn", "text": "Wet cobblestones, moored boats, low mist.", "references": []}
CAST = {"characters": ["c-woman"], "place": "p-harbour"}
WALK = "The red-haired woman walks along the quay."
NO_FRAME = {"code": "fl2va_no_frame", "message": "The shot has no first frame: it is generated from its text alone.", "data": {"shot_id": "s1"}}

WOMAN_LINE = "The red-haired woman: A woman in her thirties, short copper hair, navy wool raincoat. Props: a brass lantern."
HARBOUR_LINE = "Setting — the harbour at dawn: Wet cobblestones, moored boats, low mist."
WOMAN_SUBJECT = "<Subject 1> is the red-haired woman: A woman in her thirties, short copper hair, navy wool raincoat. Props: a brass lantern."


def _doc(make_doc, cast=CAST, prompt=WALK, characters=(WOMAN, FISHER), places=(HARBOUR,), direction=None, language="en", **parts):
    doc = make_doc(
        clips=[{**SHOT, **({"cast": copy.deepcopy(cast)} if cast is not None else {})}],
        prompts=[{"id": "p", "shotId": "s1", "text": prompt}],
        direction=direction,
        language=language,
        **parts,
    )
    doc["bible"] = {"characters": [dict(card) for card in characters], "places": [dict(card) for card in places]}
    return doc


def _plan(core, doc, preset_id, **options):
    plans = director.build_plans(core.users["user-1"], doc, ["s1"], preset_id, "draft", **options)
    assert plans.blocks == []
    (plan,) = plans.shots
    return plan, plans.warnings


def _codes(warnings):
    return [item["code"] for item in warnings]


def _composer(warnings):
    return [item for item in warnings if item["code"] in ("bible_label_missing", "prompt_too_long")]


def _sections(prompt):
    return dict(block.partition(": ")[::2] for block in prompt.split("\n\n"))


def test_wan_reads_the_cast_ahead_of_the_action_then_the_direction(core, make_doc):
    core.use_wan()

    plan, warnings = _plan(core, _doc(make_doc, direction={"univers": "A fishing village."}), presets.WAN)

    assert plan.prompt_text == "\n".join([WOMAN_LINE, HARBOUR_LINE, WALK, "A fishing village."])
    assert plan.request["prompts"][0]["positive"] == plan.prompt_text
    assert plan.request["form_data"]["video_director"]["segments"][0]["prompt"] == plan.prompt_text
    assert _composer(warnings) == []


def test_ltx_reannounces_the_visual_tag_after_the_action_in_one_paragraph(core, make_doc):
    core.use_ltx25()

    plan, warnings = _plan(core, _doc(make_doc, direction={"univers": "A fishing village", "palette": "Cold blues"}), presets.LTX_2_5)

    assert plan.prompt_text == " ".join([WALK, WOMAN_LINE, HARBOUR_LINE, "A fishing village.", "Cold blues."])
    assert "\n" not in plan.prompt_text
    assert _composer(warnings) == []


def test_h3_in_fl2va_opens_on_subject_definitions_and_keeps_the_plain_prompt_after(core, make_doc):
    core.use_h3()
    doc = _doc(make_doc, cast={"characters": ["c-fisher", "c-woman"], "place": "p-harbour"}, direction={"univers": "A fishing village."})

    plan, _ = _plan(core, doc, presets.MINIMAX_H3)

    assert plan.director_mode == "t2v"
    assert plan.prompt_text == (
        f"subject_definitions: {WOMAN_SUBJECT} "
        "<Subject 2> is the old fisherman: A man in his seventies, white beard, yellow oilskin. "
        "<Subject 3> is the setting, the harbour at dawn: Wet cobblestones, moored boats, low mist."
        f"\n\n{WALK}\nA fishing village."
    )


def test_h3_hybrid_av_takes_the_same_subject_definitions(core, make_doc):
    core.use_h3()

    plan, _ = _plan(core, _doc(make_doc, cast={"characters": ["c-woman"]}), presets.MINIMAX_H3, profile="Hybrid AV")

    assert plan.prompt_text == f"subject_definitions: {WOMAN_SUBJECT}\n\n{WALK}"


def _hero(core):
    core.add_media({"kind": "library", "item_id": "lib-hero"}, "uploads/hero.png", "image")
    return {"id": "hero", "kind": "image", "name": "hero", "origin": {"kind": "library", "itemId": "lib-hero"}}


def test_ref2va_defines_a_linked_reference_with_its_card_and_the_rest_of_the_cast_by_its_words(core, make_doc):
    core.use_h3()
    woman = {**WOMAN, "references": ["r1"]}
    references = [{"id": "r1", "assetId": "hero", "space": "identite", "scope": {"type": "global"}}]
    doc = _doc(
        make_doc,
        cast={"characters": ["c-woman", "c-fisher"], "place": "p-harbour"},
        characters=(woman, FISHER),
        assets=[_hero(core)],
        references=references,
        direction={"mode": "Ref2VA"},
    )

    plan, _ = _plan(core, doc, presets.MINIMAX_H3)
    sections = _sections(plan.prompt_text)

    assert plan.request["form_data"]["references"] == ["uploads/hero.png"]
    assert list(sections) == ["subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music"]
    assert sections["subject_definitions"] == (
        "<Subject 1> is the character shown in <Picture 1>, the red-haired woman: A woman in her thirties, short copper hair, navy wool raincoat. Props: a brass lantern. "
        "<Subject 2> is the old fisherman: A man in his seventies, white beard, yellow oilskin. "
        "<Subject 3> is the setting, the harbour at dawn: Wet cobblestones, moored boats, low mist."
    )
    assert sections["retention_analysis"] == "<Subject 1> (appears in [Shot 1]): fully_preserved - keeps the identity and the appearance."
    assert sections["detailed_description"] == (
        f"[Shot 1] {WALK} <Subject 1> appears in the shot. <Subject 2> appears in the shot. The shot takes place in <Subject 3>."
    )


def test_ref2va_names_a_linked_reference_with_its_card_even_when_the_card_is_not_cast(core, make_doc):
    core.use_h3()
    references = [{"id": "r1", "assetId": "hero", "space": "decors3d", "scope": {"type": "global"}}]
    doc = _doc(make_doc, cast=None, places=({**HARBOUR, "references": ["r1"]},), assets=[_hero(core)], references=references, direction={"mode": "Ref2VA"})

    plan, warnings = _plan(core, doc, presets.MINIMAX_H3)

    assert _sections(plan.prompt_text)["subject_definitions"] == (
        "<Subject 1> is the setting shown in <Picture 1>, the harbour at dawn: Wet cobblestones, moored boats, low mist."
    )
    assert "bible_label_missing" not in _codes(warnings)


def test_a_cloud_model_reads_the_same_simple_format_as_wan(core, make_doc):
    core.use_openrouter()

    plans = director.build_plans(core.users["user-1"], _doc(make_doc), ["s1"], presets.OPENROUTER_VIDEO, "draft", "cm-veo")
    (plan,) = plans.shots

    assert plan.prompt_text == "\n".join([WOMAN_LINE, HARBOUR_LINE, WALK])
    assert plan.request["form_data"]["video_director"]["segments"][0]["prompt"] == plan.prompt_text


def test_the_cast_reads_in_french_with_french_typography(core, make_doc):
    core.use_wan()
    woman = {**WOMAN, "label": "la femme rousse", "text": "Une trentaine d'années, cheveux cuivrés courts, ciré marine.", "props": "une lanterne en laiton"}
    harbour = {**HARBOUR, "label": "le port à l'aube", "text": "Pavés mouillés, bateaux amarrés, brume basse."}
    doc = _doc(make_doc, characters=(woman,), places=(harbour,), prompt="La femme rousse longe le quai.", language="fr")

    plan, warnings = _plan(core, doc, presets.WAN)

    assert plan.prompt_text == (
        "La femme rousse : Une trentaine d'années, cheveux cuivrés courts, ciré marine. Accessoires : une lanterne en laiton.\n"
        "Lieu — le port à l'aube : Pavés mouillés, bateaux amarrés, brume basse.\n"
        "La femme rousse longe le quai."
    )
    assert _composer(warnings) == []


def test_the_h3_definitions_follow_the_prompt_language(core, make_doc):
    core.use_h3()
    doc = _doc(make_doc, cast={"place": "p-harbour"}, places=({**HARBOUR, "label": "le port", "text": "Brume basse."},), prompt="Le quai.", language="fr")

    plan, _ = _plan(core, doc, presets.MINIMAX_H3)

    assert plan.prompt_text == "subject_definitions: <Subject 1> est le décor, le port : Brume basse.\n\nLe quai."


def test_the_cast_is_repeated_word_for_word_in_every_shot(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc)
    doc["clips"].append({**doc["clips"][0], "id": "s2", "start": 4, "label": "Boat"})
    doc["prompts"].append({**doc["prompts"][0], "id": "p2", "shotId": "s2", "start": 4, "text": "The red-haired woman climbs aboard."})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2"], presets.LTX_2_5, "draft")

    first, second = (plan.prompt_text for plan in plans.shots)
    assert first.removeprefix(WALK) == second.removeprefix("The red-haired woman climbs aboard.")


def test_a_shot_without_a_cast_keeps_the_prompt_it_had(core, make_doc):
    core.use_ltx25()

    plan, warnings = _plan(core, _doc(make_doc, cast=None, direction={"univers": "A fishing village."}), presets.LTX_2_5)

    assert plan.prompt_text == f"{WALK}\nA fishing village."
    assert _composer(warnings) == []


def test_unknown_cards_and_cards_without_a_label_are_left_out(core, make_doc):
    core.use_wan()
    blank = {**FISHER, "id": "c-blank", "label": "  "}
    doc = _doc(make_doc, cast={"characters": ["c-gone", "c-blank"], "place": "p-gone"}, characters=(WOMAN, blank))

    plan, warnings = _plan(core, doc, presets.WAN)

    assert plan.prompt_text == WALK
    assert _composer(warnings) == []


def test_the_characters_follow_the_order_of_the_bible_whatever_the_order_of_the_cast(core, make_doc):
    core.use_wan()
    doc = _doc(make_doc, cast={"characters": ["c-fisher", "c-woman"]}, prompt="The red-haired woman greets the old fisherman.")

    plan, _ = _plan(core, doc, presets.WAN)

    assert plan.prompt_text.splitlines()[:2] == [WOMAN_LINE, "The old fisherman: A man in his seventies, white beard, yellow oilskin."]


def test_a_cast_character_the_instruction_does_not_name_is_flagged(core, make_doc):
    core.use_wan()
    doc = _doc(make_doc, cast={"characters": ["c-woman", "c-fisher"]}, prompt="A woman walks along the quay.")

    _, warnings = _plan(core, doc, presets.WAN)

    assert _composer(warnings) == [
        {
            "code": "bible_label_missing",
            "message": "The instruction of the shot does not name the red-haired woman, the old fisherman, cast in it.",
            "data": {"shot_id": "s1", "labels": ["the red-haired woman", "the old fisherman"]},
        }
    ]


@pytest.mark.parametrize("case", LABEL_CASES, ids=lambda case: f"{case['label']}|{case['text']}")
def test_a_label_is_found_as_whole_words_ignoring_case_accents_and_spacing(case):
    assert bible.names(case["text"], case["label"]) is case["found"]


def test_a_wan_prompt_past_its_512_tokens_is_flagged_and_an_ltx_one_is_not(core, make_doc):
    core.use_wan()
    core.use_ltx25()
    long = {**WOMAN, "text": "A woman with copper hair. " * 90}
    doc = _doc(make_doc, characters=(long,))

    wan, wan_warnings = _plan(core, doc, presets.WAN)
    _, ltx_warnings = _plan(core, doc, presets.LTX_2_5)

    tokens = -(-len(wan.prompt_text) // 4)
    assert tokens > 512
    assert _composer(wan_warnings) == [
        {
            "code": "prompt_too_long",
            "message": f"The prompt of the shot takes about {tokens} tokens, more than the 512 the engine reads.",
            "data": {"shot_id": "s1", "tokens": tokens, "limit": 512},
        }
    ]
    assert _composer(ltx_warnings) == []


def test_the_engine_family_of_each_preset():
    assert [bible.family(preset_id, False) for preset_id in (presets.MINIMAX_H3_12GB, presets.LTX_2, presets.WAN22_14B_LIGHTNING_12GB, "custom")] == [
        bible.H3,
        bible.LTX,
        bible.WAN,
        bible.OTHER,
    ]
    assert bible.family(presets.GEMINI_VIDEO, True) == bible.CLOUD


def test_the_schema_accepts_a_bible_and_a_cast_and_an_older_document_without_them(make_doc):
    validate_doc(_doc(make_doc))
    validate_doc(make_doc(clips=[SHOT]))
    validate_doc(_doc(make_doc, cast={}))
    validate_doc(_doc(make_doc, cast={"place": None}))


@pytest.mark.parametrize(
    "change",
    [
        lambda doc: doc["bible"]["characters"][0].update(age=30),
        lambda doc: doc["bible"]["places"][0].update(props="a boat"),
        lambda doc: doc["bible"]["characters"][0].pop("props"),
        lambda doc: doc["bible"].pop("places"),
        lambda doc: doc["bible"]["characters"][0].update(references=["r1", "r1"]),
        lambda doc: doc["clips"][0]["cast"].update(characters=["c-woman", "c-woman"]),
        lambda doc: doc["clips"][0]["cast"].update(place=3),
        lambda doc: doc["clips"][0]["cast"].update(lead="c-woman"),
    ],
)
def test_the_schema_refuses_a_malformed_bible_or_cast(make_doc, change):
    doc = _doc(make_doc)
    change(doc)

    with pytest.raises(DocError):
        validate_doc(doc)


def test_migrate_clears_the_cast_of_cards_that_no_longer_exist(make_doc):
    doc = _doc(make_doc, cast={"characters": ["c-gone", "c-woman"], "place": "p-gone"}, characters=(WOMAN,))
    doc["clips"].append({**doc["clips"][0], "id": "s2", "cast": {"characters": ["c-gone"]}})
    before = copy.deepcopy(doc)

    migrated = migrate(doc)

    assert doc == before
    assert [clip.get("cast") for clip in migrated["clips"]] == [{"characters": ["c-woman"]}, None]
    assert "cast" not in migrated["clips"][1]
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_migrate_leaves_a_document_whose_cast_is_whole_or_absent_as_it_is(make_doc):
    whole = _doc(make_doc)
    without = make_doc(clips=[SHOT])

    assert migrate(whole) is whole
    assert migrate(without) is without


def test_migrate_drops_a_cast_when_the_document_has_no_bible(make_doc):
    doc = make_doc(clips=[{**SHOT, "cast": {"characters": ["c-woman"], "place": None}}])

    assert migrate(doc)["clips"][0] == {**doc["clips"][0], "cast": {"place": None}}


def _post(client, project_id, body):
    return client.post(f"/api/plugins/video-producer/projects/{project_id}/prompts", json=body)


def test_the_prompts_route_composes_the_unsaved_document_it_is_given(core, client, make_doc, make_project):
    core.use_wan()
    project = make_project(doc=_doc(make_doc, cast=None))
    edited = _doc(make_doc, prompt="A woman waits.")

    stored = _post(client, project["id"], {"shots": ["s1"], "preset_id": presets.WAN})
    unsaved = _post(client, project["id"], {"shots": ["s1"], "preset_id": presets.WAN, "doc": edited})

    assert stored.status_code == 200
    assert stored.json()["data"] == {
        "prompts": [{"shot_id": "s1", "preset_id": presets.WAN, "profile": "FL2VA", "engine": "wan", "prompt": WALK, "warnings": [NO_FRAME]}],
        "blocks": [],
    }
    (item,) = unsaved.json()["data"]["prompts"]
    assert item["prompt"] == "\n".join([WOMAN_LINE, HARBOUR_LINE, "A woman waits."])
    assert _codes(_composer(item["warnings"])) == ["bible_label_missing"]
    assert core.submitted == []


def test_the_prompts_route_follows_the_engine_each_shot_sets_for_itself(core, client, make_doc, make_project):
    core.use_wan()
    core.use_ltx25()
    doc = _doc(make_doc)
    doc["clips"][0]["engine"] = {"preset": presets.LTX_2_5, "model": None}
    project = make_project(doc=doc)

    response = _post(client, project["id"], {"shots": ["s1"], "preset_id": presets.WAN})

    (item,) = response.json()["data"]["prompts"]
    assert (item["preset_id"], item["engine"]) == (presets.LTX_2_5, "ltx")
    assert item["prompt"] == " ".join([WALK, WOMAN_LINE, HARBOUR_LINE])


def test_the_prompts_route_reports_the_blocks_of_the_run(core, client, make_doc, make_project):
    core.use_wan()
    project = make_project(doc=_doc(make_doc))

    response = _post(client, project["id"], {"shots": ["s1"], "preset_id": presets.MINIMAX_H3})

    assert response.json()["data"]["prompts"] == []
    assert _codes(response.json()["data"]["blocks"]) == ["no_preset"]


@pytest.mark.parametrize(
    "body, code",
    [
        (None, "invalid_request"),
        ({"preset_id": presets.WAN}, "invalid_request"),
        ({"shots": ["s1"]}, "invalid_request"),
        ({"shots": ["s1"], "preset_id": presets.WAN, "model_id": ""}, "invalid_request"),
        ({"shots": ["s1"], "preset_id": presets.WAN, "production": "render3d"}, "invalid_request"),
        ({"shots": ["s1"], "preset_id": presets.WAN, "doc": []}, "invalid_request"),
        ({"shots": ["s1"], "preset_id": presets.WAN, "doc": {"name": "x"}}, "invalid_doc"),
    ],
)
def test_the_prompts_route_refuses_a_malformed_body(core, client, make_doc, make_project, body, code):
    core.use_wan()
    project = make_project(doc=_doc(make_doc))

    response = _post(client, project["id"], body)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == code


def test_the_continuity_check_flags_a_cast_character_the_instruction_does_not_name(make_doc):
    doc = _doc(make_doc, prompt="A woman walks along the quay.", cast={"characters": ["c-woman", "c-fisher"]})
    named = _doc(make_doc)
    empty = _doc(make_doc, prompt="")

    (seam,) = check_continuity(doc, {})
    issues = [issue for issue in seam["issues"] if issue["kind"] == "cast_unnamed"]

    assert issues == [
        {
            "kind": "cast_unnamed",
            "text": "“Quay” does not name “the red-haired woman”, “the old fisherman”, cast in the shot.",
            "fix": "Name each character cast in the shot by its label, so that the engine ties the words of the bible to it.",
            "shot_id": "s1",
            "labels": ["the red-haired woman", "the old fisherman"],
        }
    ]
    assert all(issue["kind"] != "cast_unnamed" for seam in check_continuity(named, {}) + check_continuity(empty, {}) for issue in seam["issues"])


def test_the_assistant_reads_the_bible_and_the_cast_of_each_shot():
    page = {
        "projectId": "p1",
        "bible": {
            "characters": [{"label": "the red-haired woman", "text": "Copper hair, navy raincoat."}, {"label": " ", "text": "No label."}],
            "places": [{"label": "the harbour at dawn", "text": ""}],
        },
        "shots": [{"id": "s1", "label": "Quay", "start": 0, "dur": 4, "prompt": "She walks.", "cast": ["the red-haired woman", "the harbour at dawn"]}],
    }

    block = build_context({"video_producer": page}, None, "user-1")

    assert (
        "Bible (repeated word for word in the prompt of each shot that casts it; name a cast character by its label):\n"
        '  character "the red-haired woman": Copper hair, navy raincoat.\n'
        '  place "the harbour at dawn"\n'
    ) in block
    assert 'prompt: "She walks."; cast: the red-haired woman, the harbour at dawn' in block
    assert "No label" not in block
    assert "Bible" not in build_context({"video_producer": {**page, "bible": {}}}, None, "user-1")
