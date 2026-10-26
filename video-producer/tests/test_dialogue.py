import copy

import pytest

from backend import director, presets
from backend.projects import DocError, migrate, validate_doc

SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Quay"}
WOMAN = {
    "id": "c-woman",
    "label": "the red-haired woman",
    "text": "A woman in her thirties, short copper hair, navy wool raincoat.",
    "props": "",
    "references": [],
    "voice": "a low, husky voice.",
    "language": "French",
}
FISHER = {"id": "c-fisher", "label": "the old fisherman", "text": "A man in his seventies, white beard.", "props": "", "references": []}
HARBOUR = {"id": "p-harbour", "label": "the harbour at dawn", "text": "Wet cobblestones, low mist.", "references": []}
WALK = "The red-haired woman walks along the quay."

WOMAN_SUBJECT = "<Subject 1> is the red-haired woman: A woman in her thirties, short copper hair, navy wool raincoat."
HARBOUR_SUBJECT = "<Subject 2> is the setting, the harbour at dawn: Wet cobblestones, low mist."
WOMAN_LINE = "The red-haired woman: A woman in her thirties, short copper hair, navy wool raincoat."
HARBOUR_LINE = "Setting — the harbour at dawn: Wet cobblestones, low mist."


def _line(text, speaker="c-woman", line_id=None, **fields):
    return {"id": line_id or f"l-{len(text)}-{text[:6]}", "speaker": speaker, "text": text, **fields}


def _doc(make_doc, lines=(), cast=None, characters=(WOMAN, FISHER), language="en", references=(), assets=(), mode=None, **extra):
    cast = {"characters": ["c-woman"], "place": "p-harbour"} if cast is None else cast
    doc = make_doc(
        clips=[{**SHOT, "cast": copy.deepcopy(cast), "dialogue": [dict(line) for line in lines]}],
        prompts=[{"id": "p", "shotId": "s1", "text": WALK}],
        references=list(references),
        assets=list(assets),
        direction={"mode": mode} if mode else None,
        language=language,
    )
    doc["bible"] = {"characters": [dict(card) for card in characters], "places": [dict(HARBOUR)]}
    doc.update(extra)
    return doc


def _plan(core, doc, preset_id):
    plans = director.build_plans(core.users["user-1"], doc, ["s1"], preset_id, "draft")
    assert plans.blocks == []
    (plan,) = plans.shots
    return plan, plans.warnings


def _codes(warnings):
    return [item["code"] for item in warnings if item["code"].startswith("dialogue_")]


def _sections(prompt):
    return dict(block.partition(": ")[::2] for block in prompt.split("\n\n"))


def _voice_media(core):
    core.add_media({"kind": "library", "item_id": "lib-hero"}, "uploads/hero.png", "image")
    core.add_media({"kind": "library", "item_id": "lib-voice"}, "uploads/voice.wav", "audio")
    return [
        {"id": "hero", "kind": "image", "name": "hero", "origin": {"kind": "library", "itemId": "lib-hero"}},
        {"id": "voice", "kind": "audio", "name": "voice.wav", "origin": {"kind": "library", "itemId": "lib-voice"}, "srcDur": 6.0},
    ]


HERO_REFERENCE = {"id": "r-hero", "assetId": "hero", "space": "identite", "scope": {"type": "global"}}
VOICE_REFERENCE = {"id": "r-voice", "assetId": "voice", "space": "son", "type": "Voix", "role": "Son", "scope": {"type": "global"}}


def test_h3_speaks_each_line_by_its_subject_with_its_voice_once_and_the_exact_words(core, make_doc):
    core.use_h3()
    doc = _doc(make_doc, [_line("Je descends au prochain arrêt."), _line("Adieu.")])

    plan, warnings = _plan(core, doc, presets.MINIMAX_H3)

    assert plan.prompt_text == (
        f"subject_definitions: {WOMAN_SUBJECT} {HARBOUR_SUBJECT}\n\n"
        f"{WALK}\n"
        "<Subject 1> (S1), a low, husky voice, says: <d>[French] Je descends au prochain arrêt.</d> "
        "<Subject 1> (S1) says: <d>[French] Adieu.</d>"
    )
    assert _codes(warnings) == []


def test_h3_says_a_voiceover_and_an_unnamed_voice_in_the_project_language(core, make_doc):
    core.use_h3()
    lines = [_line("Tout a commencé ici.", speaker=None, offscreen=True), _line("Bonjour.")]
    doc = _doc(make_doc, lines, dialogueLanguage="French")

    plan, _ = _plan(core, doc, presets.MINIMAX_H3)

    assert plan.prompt_text.endswith(
        "A voice (S1) says in an off-screen voiceover: <d>[French] Tout a commencé ici.</d> On-screen lips stay closed. "
        "<Subject 1> (S2), a low, husky voice, says: <d>[French] Bonjour.</d>"
    )


def test_ltx_puts_the_lines_in_quotation_marks_after_the_action_and_before_the_cast(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc, [_line("Bonjour."), _line("Le bateau part.", speaker="c-fisher", offscreen=True)], cast={"characters": ["c-woman", "c-fisher"], "place": "p-harbour"})

    plan, warnings = _plan(core, doc, presets.LTX_2_5)

    assert plan.prompt_text == " ".join(
        [
            WALK,
            'The red-haired woman, a low, husky voice, says in French: "Bonjour."',
            'The old fisherman speaks off-screen in English: "Le bateau part."',
            "On-screen lips stay closed.",
            WOMAN_LINE,
            "The old fisherman: A man in his seventies, white beard.",
            HARBOUR_LINE,
        ]
    )
    assert "\n" not in plan.prompt_text
    assert _codes(warnings) == []


def test_ltx_reads_the_lines_in_french_when_the_prompts_are_french(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc, [_line("Bonjour.")], cast={"characters": []}, characters=({**WOMAN, "voice": ""},), language="fr")

    plan, _ = _plan(core, doc, presets.LTX_2_5)

    assert plan.prompt_text == "\n".join([WALK, 'The red-haired woman dit en français : "Bonjour."'])


def test_ref2va_defines_the_voice_of_a_character_and_says_its_lines_in_the_shot(core, make_doc):
    core.use_h3()
    woman = {**WOMAN, "references": ["r-hero"], "voiceRef": "r-voice"}
    doc = _doc(
        make_doc,
        [_line("Bonjour.")],
        cast={"characters": ["c-woman"]},
        characters=(woman,),
        references=[HERO_REFERENCE, VOICE_REFERENCE],
        assets=_voice_media(core),
        mode="Ref2VA",
    )

    plan, warnings = _plan(core, doc, presets.MINIMAX_H3)
    sections = _sections(plan.prompt_text)

    assert plan.request["form_data"]["references"] == ["uploads/hero.png", "uploads/voice.wav"]
    assert sections["subject_definitions"].endswith("<Audio 1> is the voice of <Subject 1>.")
    assert sections["retention_analysis"].splitlines()[-1] == "<Audio 1> (sound of [Shot 1]): reference - the voice of <Subject 1>, kept for its lines."
    assert sections["detailed_description"] == f"[Shot 1] {WALK} <Subject 1> appears in the shot. <Subject 1> (S1), a low, husky voice, says, <d>[French] Bonjour.</d>"
    assert _codes(warnings) == []


def test_ref2va_warns_when_the_voice_of_a_speaker_is_not_sent(core, make_doc):
    core.use_h3()
    woman = {**WOMAN, "references": ["r-hero"], "voiceRef": "r-voice"}
    scoped = {**VOICE_REFERENCE, "scope": {"type": "shot", "shotId": "other"}}
    doc = _doc(make_doc, [_line("Bonjour.")], cast={"characters": ["c-woman"]}, characters=(woman,), references=[HERO_REFERENCE, scoped], assets=_voice_media(core), mode="Ref2VA")

    _, warnings = _plan(core, doc, presets.MINIMAX_H3)

    (warning,) = [item for item in warnings if item["code"] == "dialogue_voice_not_sent"]
    assert warning["data"] == {"shot_id": "s1", "labels": ["the red-haired woman"]}


def test_a_voice_of_the_bible_is_never_mixed_onto_a_take(core, make_doc):
    core.use_ltx25()
    doc = _doc(make_doc, [_line("Bonjour.")], characters=({**WOMAN, "voiceRef": "r-voice"},), references=[VOICE_REFERENCE], assets=_voice_media(core))

    plan, warnings = _plan(core, doc, presets.LTX_2_5)

    assert plan.audio is None
    assert not [item for item in warnings if item["code"].startswith("audio_")]


def test_an_engine_without_speech_leaves_the_lines_out_and_says_so(core, make_doc):
    core.use_wan()

    plan, warnings = _plan(core, _doc(make_doc, [_line("Bonjour.")]), presets.WAN)

    assert "Bonjour" not in plan.prompt_text
    assert _codes(warnings) == ["dialogue_ignored"]


def test_the_lines_warn_about_a_missing_speaker_an_absent_one_and_their_length(core, make_doc):
    core.use_ltx25()
    lines = [
        _line("Who goes there?", speaker="c-ghost"),
        _line("It is only me, the fisherman, back from the sea with nothing at all.", speaker="c-fisher"),
        _line("Off you go.", speaker="c-fisher", offscreen=True),
    ]

    plan, warnings = _plan(core, _doc(make_doc, lines), presets.LTX_2_5)

    assert _codes(warnings) == ["dialogue_speaker_unknown", "dialogue_speaker_not_cast", "dialogue_too_long"]
    by_code = {item["code"]: item["data"] for item in warnings}
    assert by_code["dialogue_speaker_not_cast"]["labels"] == ["the old fisherman"]
    assert by_code["dialogue_too_long"] == {"shot_id": "s1", "words": 20, "limit": 12}
    assert 'A voice says in English: "Who goes there?"' in plan.prompt_text


def test_empty_lines_are_not_spoken(core, make_doc):
    core.use_h3()

    plan, warnings = _plan(core, _doc(make_doc, [_line("   ")]), presets.MINIMAX_H3)

    assert "<d>" not in plan.prompt_text
    assert _codes(warnings) == []


def test_the_document_keeps_the_lines_and_the_voices_and_frees_the_lines_of_a_removed_character(make_doc):
    doc = _doc(make_doc, [_line("Bonjour.", line_id="l1"), _line("Salut.", speaker="c-gone", line_id="l2", offscreen=True)], characters=({**WOMAN, "voiceRef": "r-voice"},), dialogueLanguage="French")

    migrated = migrate(doc)
    validate_doc(migrated)

    assert migrated["clips"][0]["dialogue"] == [
        {"id": "l1", "speaker": "c-woman", "text": "Bonjour."},
        {"id": "l2", "speaker": None, "text": "Salut.", "offscreen": True},
    ]
    assert migrate(migrated) is migrated


@pytest.mark.parametrize("line", [{"id": "l1", "text": "Bonjour."}, {"id": "l1", "speaker": None, "text": "Hi", "tone": "soft"}, {"id": "", "speaker": None, "text": "Hi"}])
def test_a_line_out_of_shape_is_refused(make_doc, line):
    doc = _doc(make_doc)
    doc["clips"][0]["dialogue"] = [line]

    with pytest.raises(DocError):
        validate_doc(doc)
