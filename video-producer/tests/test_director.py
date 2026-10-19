import copy
import math

import pytest

from backend import director, presets
from backend.director import DirectorError

SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Opening"}
TEXT_ONLY_WARNING = {
    "code": "text_only_preset",
    "message": "The preset generates from text only: the frames of the shot are not used.",
    "data": {"shot_id": "s1"},
}


def _history(asset_id, generation_id, file_id, kind="image"):
    return {"id": asset_id, "kind": kind, "name": asset_id, "origin": {"kind": "history", "generationId": generation_id, "fileId": file_id}}


def _frame(frame_id, asset_id, role, time=0, shot_id="s1"):
    return {"id": frame_id, "shotId": shot_id, "time": time, "assetId": asset_id, "role": role}


def _images(core):
    core.add_media({"kind": "history", "generation_id": "g-a", "file_id": "1"}, "generations/2026-10-17/g-a/1.png", "IMAGE")
    core.add_media({"kind": "history", "generation_id": "g-b", "file_id": "2"}, "generations/2026-10-17/g-b/2.png", "IMAGE")
    return [_history("a", "g-a", "1"), _history("b", "g-b", "2")]


def _plans(core, doc, preset_id=presets.WAN, quality="draft", shots=("s1",), **options):
    return director.build_plans(core.users["user-1"], doc, list(shots), preset_id, quality, **options)


def test_a_shot_without_frame_runs_text_to_video_on_wan_with_the_t2v_models(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[SHOT], prompts=[{"id": "p", "shotId": "s1", "text": "A lighthouse at dusk."}])

    plans = _plans(core, doc)

    assert plans.blocks == []
    (plan,) = plans.shots
    assert (plan.director_mode, plan.preset_mode, plan.seconds, plan.resolution, plan.fps) == ("t2v", "video", 4.0, "832x480", 16)
    assert plan.request == {
        "preset_id": presets.WAN,
        "mode": "video",
        "prompts": [{"positive": "A lighthouse at dusk.", "negative": ""}],
        "form_data": {
            "seed": -1,
            "resolution": "832x480",
            "fps": 16,
            "video_director": {
                "schema_version": 1,
                "mode": "t2v",
                "settings": {"fps": 16, "duration": 4.0, "resolution": "832x480", "seed": -1},
                "segments": [{"id": "seg-1", "prompt": "A lighthouse at dusk.", "negative_prompt": ""}],
                "media": [],
            },
            "text_encoder": "model:id-text_encoder-sha",
            "vae": "model:id-vae-sha",
            "t2v_high_noise_model": "model:id-t2v_high_noise_model-sha",
            "t2v_low_noise_model": "model:id-t2v_low_noise_model-sha",
        },
    }
    assert plans.warnings == [
        {
            "code": "fl2va_no_frame",
            "message": "The shot has no first frame: it is generated from its text alone.",
            "data": {"shot_id": "s1"},
        }
    ]


def test_a_take_request_carries_its_seed_and_idempotency_key(core, make_doc):
    core.use_wan()
    (plan,) = _plans(core, make_doc(clips=[SHOT])).shots

    request = plan.request_for("01TAKE", 4242)

    assert request["idempotency_key"] == "vp:01TAKE"
    assert request["form_data"]["seed"] == 4242
    assert request["form_data"]["video_director"]["settings"]["seed"] == 4242
    assert "quantity" not in request["form_data"]
    assert plan.request["form_data"]["seed"] == -1 and "idempotency_key" not in plan.request


def test_a_first_frame_makes_the_shot_image_to_video_with_the_i2v_models(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[SHOT], frames=[_frame("f1", "a", "first")], assets=_images(core))

    plans = _plans(core, doc)

    (plan,) = plans.shots
    form = plan.request["form_data"]
    assert plan.director_mode == "i2v" and form["video_director"]["mode"] == "i2v"
    assert form["video_director"]["media"] == [
        {
            "id": "bound-first-seg-1",
            "role": "first",
            "segment_id": "seg-1",
            "at": 0,
            "strength": 1.0,
            "media": {
                "path": "generations/2026-10-17/g-a/1.png",
                "relative_path": "generations/2026-10-17/g-a/1.png",
                "type": "image",
            },
        }
    ]
    assert form["i2v_high_noise_model"] == "model:id-i2v_high_noise_model-sha"
    assert form["i2v_low_noise_model"] == "model:id-i2v_low_noise_model-sha"
    assert "t2v_high_noise_model" not in form
    assert plans.warnings == []


@pytest.mark.parametrize("first_role, last_role", [("first", "last"), ("Début", "Fin")])
def test_a_first_and_a_last_frame_make_the_shot_first_last_frame(core, make_doc, first_role, last_role):
    core.use_wan()
    frames = [_frame("f2", "b", last_role, time=3.9), _frame("f1", "a", first_role, time=0.1)]
    doc = make_doc(clips=[SHOT], frames=frames, assets=_images(core))

    (plan,) = _plans(core, doc).shots

    media = plan.request["form_data"]["video_director"]["media"]
    assert plan.director_mode == "flf"
    assert [(entry["role"], entry["media"]["path"], entry["at"]) for entry in media] == [
        ("first", "generations/2026-10-17/g-a/1.png", 0),
        ("last", "generations/2026-10-17/g-b/2.png", 4.0),
    ]


def test_a_last_frame_alone_leaves_the_shot_text_to_video_with_a_warning(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[SHOT], frames=[_frame("f2", "b", "last")], assets=_images(core))

    plans = _plans(core, doc)

    assert plans.shots[0].director_mode == "t2v"
    assert [warning["code"] for warning in plans.warnings] == ["fl2va_no_frame"]


def test_frames_of_other_shots_or_roles_and_unreachable_media_are_ignored(core, make_doc):
    core.use_wan()
    assets = _images(core) + [_history("gone", "g-gone", "9"), _history("clip", "g-v", "3", kind="video")]
    core.add_media({"kind": "history", "generation_id": "g-v", "file_id": "3"}, "generations/x/3.mp4", "VIDEO")
    frames = [
        _frame("f1", "a", "first", shot_id="s2"),
        _frame("f2", "a", "Transition"),
        _frame("f3", "gone", "first"),
        _frame("f4", "clip", "first"),
    ]
    doc = make_doc(clips=[SHOT, {"id": "s2", "start": 4}], frames=frames, assets=assets)

    plans = _plans(core, doc)

    assert plans.shots[0].director_mode == "t2v"
    assert plans.warnings[0]["data"] == {"shot_id": "s1"}


def test_the_prompt_is_the_shot_instruction_then_the_filled_direction_fields_in_order(core, make_doc):
    core.use_wan()
    direction = {"univers": " Rainy neon city ", "personnages": "", "photographie": "Anamorphic", "palette": "  ", "rythme": "Slow"}
    prompts = [
        {"id": "g", "shotId": None, "start": 0, "dur": 30, "text": "The whole film."},
        {"id": "p", "shotId": "s1", "start": 0, "dur": 4, "text": "Une femme marche sous la pluie."},
    ]
    doc = make_doc(clips=[SHOT], prompts=prompts, direction=direction)

    (plan,) = _plans(core, doc).shots

    expected = "Une femme marche sous la pluie.\nRainy neon city\nAnamorphic\nSlow"
    assert plan.prompt_text == expected
    assert plan.request["prompts"] == [{"positive": expected, "negative": ""}]
    assert plan.request["form_data"]["video_director"]["segments"][0]["prompt"] == expected


def test_without_its_own_prompt_a_shot_takes_the_global_prompt_covering_most_of_it(core, make_doc):
    core.use_wan()
    prompts = [
        {"id": "g1", "shotId": None, "start": 0, "dur": 5, "text": "Before."},
        {"id": "g2", "shotId": None, "start": 5, "dur": 10, "text": "During."},
        {"id": "other", "shotId": "s9", "start": 5, "dur": 10, "text": "Someone else's."},
    ]
    doc = make_doc(clips=[{"id": "s1", "start": 4, "dur": 6}], prompts=prompts)

    assert _plans(core, doc).shots[0].prompt_text == "During."


def test_a_shot_longer_than_the_preset_allows_is_clamped_with_a_warning(core, make_doc):
    core.use_h3()
    doc = make_doc(clips=[{"id": "s1", "start": 0, "dur": 22}], direction={"mode": "Hybrid AV"})

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    assert plans.shots[0].seconds == 15.0
    assert plans.shots[0].request["form_data"]["video_director"]["settings"]["duration"] == 15.0
    assert plans.warnings == [
        {"code": "duration_clamped", "message": "The shot is longer than the 15 s the preset allows.", "data": {"shot_id": "s1", "max": 15}}
    ]


def test_a_shot_without_duration_takes_the_preset_default(core, make_doc):
    core.use_wan()

    assert _plans(core, make_doc(clips=[{"id": "s1", "dur": 0}])).shots[0].seconds == 5.0


def test_a_final_render_takes_the_largest_size_in_the_project_aspect(core, make_doc):
    core.use_wan()

    landscape = _plans(core, make_doc(clips=[SHOT]), quality="final").shots[0]
    portrait = _plans(core, make_doc(clips=[SHOT], aspect="9:16"), quality="final").shots[0]

    assert landscape.resolution == "1280x720"
    assert portrait.resolution == "720x1280"


def test_a_draft_follows_the_admin_setting_turned_to_the_project_orientation(core, make_doc, store):
    core.use_wan()
    store[("draft_resolution", None)] = "960x544"

    assert _plans(core, make_doc(clips=[SHOT])).shots[0].resolution == "960x544"
    assert _plans(core, make_doc(clips=[SHOT], aspect="9:16")).shots[0].resolution == "544x960"


def test_a_draft_size_the_preset_does_not_offer_falls_back_to_the_closest_area(core, make_doc, store):
    core.use_h3()
    store[("draft_resolution", None)] = "1280x720"

    plan = _plans(core, make_doc(clips=[SHOT]), preset_id=presets.MINIMAX_H3).shots[0]

    assert plan.resolution == "1344x768"
    assert plan.fps == 24 and "fps" not in plan.request["form_data"]
    assert plan.request["form_data"]["quantity"] == 1


COMFY_DIT = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
WAN2GP_DIT = "MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors"


def _h3_12gb(core, preset_id=presets.MINIMAX_H3_12GB, name="MiniMax-H3 (12 GB)"):
    core.use_h3_variant(preset_id, name)
    core.fields[(preset_id, "video")]["resolution"]["default"] = "832x480"
    return preset_id


@pytest.mark.parametrize("preset_id", [presets.MINIMAX_H3_12GB, presets.MINIMAX_H3_FAST_12GB])
@pytest.mark.parametrize("aspect, draft_size, final_size", [("16:9", "832x480", "1344x768"), ("9:16", "480x832", "768x1344")])
def test_a_12_gb_h3_preset_drafts_at_832x480_and_finishes_at_its_largest_canvas(core, make_doc, preset_id, aspect, draft_size, final_size):
    _h3_12gb(core, preset_id, "MiniMax-H3 (12 GB)")
    doc = make_doc(clips=[SHOT], aspect=aspect)

    draft = _plans(core, doc, preset_id=preset_id).shots[0]
    final = _plans(core, doc, preset_id=preset_id, quality="final").shots[0]

    assert (draft.resolution, final.resolution) == (draft_size, final_size)
    assert draft.request["form_data"]["resolution"] == draft_size
    assert draft.request["form_data"]["video_director"]["settings"]["resolution"] == draft_size
    assert (draft.preset_mode, draft.fps, draft.request["form_data"]["quantity"]) == ("video", 24, 1)


def test_a_12_gb_h3_preset_runs_the_wan2gp_dit_found_by_its_file_name(core, make_doc):
    preset_id = _h3_12gb(core)
    core.fields[(preset_id, "video")]["model"]["recommendations"] = [
        {"sha256": "comfy-sha", "filename": COMFY_DIT},
        {"sha256": "wan2gp-sha", "filename": WAN2GP_DIT},
    ]
    core.missing = {"comfy-sha", COMFY_DIT, "wan2gp-sha"}

    plans = _plans(core, make_doc(clips=[SHOT]), preset_id=preset_id)

    assert plans.blocks == []
    assert plans.shots[0].request["form_data"]["model"] == f"model:id-{WAN2GP_DIT}"


def _wan_tier(core, modes=None, preset_id=presets.WAN22_TI2V_5B_8GB, fps=24):
    wan = core.use_wan()
    director_vars = {
        **wan.vars["video_director"],
        "modes": {"t2v": {}} if modes is None else modes,
        "limits": {"default_duration": 5, "default_fps": fps, "max_duration": 5},
    }
    variables = {**wan.vars, "default_fps": fps, "video_director": director_vars}
    fields = copy.deepcopy(core.fields[(presets.WAN, "video")])
    core.add_preset(preset_id, "Wan 2.2 TI2V 5B (8 GB)", {"video": fields}, variables=variables)
    return preset_id


@pytest.mark.parametrize("preset_id", presets.WAN_TIER_PRESETS)
def test_a_shot_with_a_first_frame_runs_text_to_video_on_a_text_only_preset_without_linking_the_frame(core, make_doc, preset_id):
    _wan_tier(core, preset_id=preset_id)
    doc = make_doc(clips=[SHOT], frames=[_frame("f1", "a", "first")], assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id)

    assert plans.blocks == []
    (plan,) = plans.shots
    form = plan.request["form_data"]
    assert (plan.director_mode, plan.preset_mode) == ("t2v", "video")
    assert form["video_director"]["mode"] == "t2v" and form["video_director"]["media"] == []
    assert form["t2v_high_noise_model"] == "model:id-t2v_high_noise_model-sha"
    assert not any(key.startswith("i2v_") for key in form)
    assert plans.warnings == [TEXT_ONLY_WARNING]


def test_a_first_and_a_last_frame_are_both_left_out_of_a_text_only_preset_with_a_single_warning(core, make_doc):
    preset_id = _wan_tier(core)
    frames = [_frame("f1", "a", "first", time=0.1), _frame("f2", "b", "last", time=3.9)]
    doc = make_doc(clips=[SHOT], frames=frames, assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id)

    assert plans.shots[0].director_mode == "t2v"
    assert plans.shots[0].request["form_data"]["video_director"]["media"] == []
    assert plans.warnings == [TEXT_ONLY_WARNING]


def test_a_text_only_preset_warns_about_each_shot_that_has_a_first_frame_and_only_those(core, make_doc):
    preset_id = _wan_tier(core)
    clips = [SHOT, {"id": "s2", "start": 4, "dur": 4}, {"id": "s3", "start": 8, "dur": 4}]
    frames = [_frame("f1", "a", "first", shot_id="s1"), _frame("f3", "b", "first", shot_id="s3")]
    doc = make_doc(clips=clips, frames=frames, assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id, shots=("s1", "s2", "s3"))

    assert [plan.director_mode for plan in plans.shots] == ["t2v", "t2v", "t2v"]
    assert [(warning["code"], warning["data"]["shot_id"]) for warning in plans.warnings] == [
        ("text_only_preset", "s1"),
        ("fl2va_no_frame", "s2"),
        ("text_only_preset", "s3"),
    ]


@pytest.mark.parametrize("frames", [[], [_frame("f2", "b", "last")]])
def test_a_text_only_preset_keeps_the_no_first_frame_warning_when_the_shot_has_no_first_frame(core, make_doc, frames):
    preset_id = _wan_tier(core)
    doc = make_doc(clips=[SHOT], frames=frames, assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id)

    assert plans.shots[0].director_mode == "t2v"
    assert [warning["code"] for warning in plans.warnings] == ["fl2va_no_frame"]


@pytest.mark.parametrize(
    "modes, director_mode, roles",
    [
        ({"t2v": {}, "i2v": {}}, "i2v", ["first"]),
        ({"t2v": {}, "i2v": {}, "flf": {}}, "flf", ["first", "last"]),
        ({"t2v": {}, "i2v": {}, "flf": {}, "director": {"max_segments": 8}}, "flf", ["first", "last"]),
        ({}, "flf", ["first", "last"]),
    ],
)
def test_a_preset_that_declares_image_to_video_keeps_binding_the_frames_its_modes_allow(core, make_doc, modes, director_mode, roles):
    preset_id = _wan_tier(core, modes=modes)
    frames = [_frame("f1", "a", "first", time=0.1), _frame("f2", "b", "last", time=3.9)]
    doc = make_doc(clips=[SHOT], frames=frames, assets=_images(core))

    plans = _plans(core, doc, preset_id=preset_id)

    (plan,) = plans.shots
    media = plan.request["form_data"]["video_director"]["media"]
    assert plan.director_mode == director_mode and plan.request["form_data"]["video_director"]["mode"] == director_mode
    assert [entry["role"] for entry in media] == roles
    assert plan.request["form_data"]["i2v_high_noise_model"] == "model:id-i2v_high_noise_model-sha"
    assert plans.warnings == []


@pytest.mark.parametrize("preset_id, fps", [(presets.WAN21_T2V_1_3B_8GB, 16), (presets.WAN22_TI2V_5B_8GB, 24)])
def test_a_text_only_preset_plans_a_shot_at_its_own_frame_rate_and_cuts_it_to_5_seconds(core, make_doc, preset_id, fps):
    _wan_tier(core, preset_id=preset_id, fps=fps)
    doc = make_doc(clips=[{"id": "s1", "start": 0, "dur": 8}])

    plans = _plans(core, doc, preset_id=preset_id)

    (plan,) = plans.shots
    assert (plan.fps, plan.seconds) == (fps, 5.0)
    assert plan.request["form_data"]["fps"] == fps
    assert plan.request["form_data"]["video_director"]["settings"] == {"fps": fps, "duration": 5.0, "resolution": "832x480", "seed": -1}
    assert [warning["code"] for warning in plans.warnings] == ["duration_clamped", "fl2va_no_frame"]


LIGHTNING_HIGH = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors"
LIGHTNING_LOW = "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"


def _lightning(core):
    preset_id = _wan_tier(core, preset_id="wan-with-default-loras", fps=16)
    fields = core.fields[(preset_id, "video")]
    fields["t2v_loras_high"] = {**fields["seed"], "type": "lora_picker", "default": [{"model": f"models/loras/{LIGHTNING_HIGH}", "strength": 1.0}]}
    fields["t2v_loras_low"] = {**fields["seed"], "type": "lora_picker", "default": [{"model": LIGHTNING_LOW, "strength": 0.8}]}
    fields["i2v_loras_high"] = {**fields["seed"], "type": "lora_picker", "default": []}
    return preset_id


def test_the_default_loras_of_a_preset_are_sent_as_installed_models(core, make_doc):
    preset_id = _lightning(core)

    plans = _plans(core, make_doc(clips=[SHOT]), preset_id=preset_id)

    assert plans.blocks == []
    form = plans.shots[0].request["form_data"]
    assert form["t2v_loras_high"] == [{"model": f"model:id-{LIGHTNING_HIGH}", "strength": 1.0}]
    assert form["t2v_loras_low"] == [{"model": f"model:id-{LIGHTNING_LOW}", "strength": 0.8}]
    assert "i2v_loras_high" not in form


def test_a_default_lora_that_is_not_installed_blocks_with_its_field(core, make_doc):
    preset_id = _lightning(core)
    core.missing.add(LIGHTNING_LOW)

    plans = _plans(core, make_doc(clips=[SHOT]), preset_id=preset_id)

    assert plans.blocks == [
        {
            "code": "missing_models",
            "message": "Install a recommended file for: t2v_loras_low.",
            "data": {"fields": ["t2v_loras_low"]},
        }
    ]
    assert "t2v_loras_low" not in plans.shots[0].request["form_data"]


def test_ref2va_runs_the_h3_refs_mode_with_the_shot_references_then_the_global_ones(core, make_doc):
    core.use_h3()
    core.add_media({"kind": "library", "item_id": "lib-1"}, "uploads/hero.png", "image")
    core.add_media({"kind": "history", "generation_id": "g-v", "file_id": "7"}, "generations/x/7.mp4", "VIDEO")
    assets = [
        {"id": "hero", "kind": "image", "origin": {"kind": "library", "itemId": "lib-1"}},
        _history("walk", "g-v", "7", kind="video"),
        {"id": "loose", "kind": "image", "origin": None},
    ]
    references = [
        {"id": "r1", "assetId": "walk", "scope": {"type": "global"}},
        {"id": "r2", "assetId": "hero", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "r3", "assetId": "hero", "scope": {"type": "shot", "shotId": "s2"}},
        {"id": "r4", "assetId": "loose", "scope": None},
    ]
    doc = make_doc(clips=[SHOT], references=references, assets=assets, direction={"mode": "Ref2VA"})

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    assert plans.blocks == [] and plans.warnings == []
    (plan,) = plans.shots
    form = plan.request["form_data"]
    assert (plan.director_mode, plan.preset_mode, plan.request["mode"]) == ("refs", "refs", "refs")
    assert form["references"] == ["uploads/hero.png", "generations/x/7.mp4"]
    assert form["video_director"]["mode"] == "t2v" and form["video_director"]["media"] == []
    assert form["model"] == "model:id-ref2va-sha"
    assert (form["text_encoder"], form["video_vae"], form["audio_vae"]) == (
        "model:id-h3_text_encoder-sha",
        "model:id-video_vae-sha",
        "model:id-audio_vae-sha",
    )


def test_ref2va_without_any_reference_is_blocked(core, make_doc):
    core.use_h3()

    plans = _plans(core, make_doc(clips=[SHOT], direction={"mode": "Ref2VA"}), preset_id=presets.MINIMAX_H3)

    assert plans.shots == []
    assert plans.blocks == [
        {"code": "no_references", "message": "Ref2VA needs at least one reference for this shot.", "data": {"shot_id": "s1"}}
    ]


@pytest.mark.parametrize("profile", ["Ref2VA", "Hybrid AV"])
def test_ref2va_and_hybrid_av_are_refused_on_a_preset_other_than_h3(core, make_doc, profile):
    core.use_wan()

    plans = _plans(core, make_doc(clips=[SHOT], direction={"mode": profile}))

    assert plans.shots == []
    assert plans.blocks == [
        {
            "code": "profile_unsupported",
            "message": f"Wan 2.1 / 2.2 cannot run the {profile} profile.",
            "data": {"profile": profile, "preset_id": presets.WAN},
        }
    ]


def test_hybrid_av_runs_the_h3_video_mode_with_the_fl2va_document_and_no_warning(core, make_doc):
    core.use_h3()
    doc = make_doc(clips=[SHOT], frames=[_frame("f1", "a", "first")], assets=_images(core), direction={"mode": "Hybrid AV"})

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    (plan,) = plans.shots
    assert (plan.director_mode, plan.preset_mode, plan.profile) == ("i2v", "video", "Hybrid AV")
    assert plan.request["form_data"]["model"] == "model:id-fl2va-sha"
    assert "audio" not in plan.request["form_data"]["video_director"]
    assert plans.warnings == []


def test_the_profile_asked_for_wins_over_the_project_direction(core, make_doc):
    core.use_h3()
    doc = make_doc(clips=[SHOT], direction={"mode": "Ref2VA"})

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3, profile="FL2VA")

    assert plans.profile == "FL2VA" and plans.shots[0].director_mode == "t2v"


def test_an_unknown_direction_mode_counts_as_fl2va(core, make_doc):
    core.use_wan()

    assert _plans(core, make_doc(clips=[SHOT], direction={"mode": "Other"})).profile == "FL2VA"


def test_models_without_an_installed_recommendation_block_with_their_fields(core, make_doc):
    core.use_wan()
    core.missing.update({"vae-sha", "t2v_high_noise_model-sha", "t2v_low_noise_model-sha"})

    plans = _plans(core, make_doc(clips=[SHOT, {"id": "s2", "start": 4}]), shots=("s1", "s2"))

    assert len(plans.shots) == 2
    assert plans.blocks == [
        {
            "code": "missing_models",
            "message": "Install a recommended file for: vae, t2v_high_noise_model.",
            "data": {"fields": ["vae", "t2v_high_noise_model"]},
        }
    ]
    assert "t2v_low_noise_model" not in plans.shots[0].request["form_data"]


def test_a_preset_the_user_may_not_run_is_blocked(core, make_doc):
    plans = _plans(core, make_doc(clips=[SHOT]))

    assert plans.preset is None and plans.shots == []
    assert plans.blocks == [{"code": "no_preset", "message": "The preset is not available to you.", "data": {"preset_id": presets.WAN}}]


def test_an_upscaler_is_not_a_video_director_preset(core, make_doc):
    core.use_seedvr2()

    assert _plans(core, make_doc(clips=[SHOT]), preset_id=presets.SEEDVR2).blocks[0]["code"] == "no_preset"


def test_unknown_shots_are_left_out_and_none_left_blocks(core, make_doc):
    core.use_wan()
    doc = make_doc(clips=[SHOT])

    assert [plan.shot_id for plan in _plans(core, doc, shots=("nope", "s1", "s1")).shots] == ["s1"]
    assert _plans(core, doc, shots=("nope",)).blocks == [{"code": "no_shots", "message": "Select at least one shot of the project."}]


def test_a_cloud_shot_without_frame_runs_txt2video_with_the_model_parameters(core, make_doc):
    core.use_openrouter()
    doc = make_doc(clips=[{"id": "s1", "start": 0, "dur": 5}], prompts=[{"id": "p", "shotId": "s1", "text": "Waves."}])

    plans = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    (plan,) = plans.shots
    assert plan.request == {
        "preset_id": presets.OPENROUTER_VIDEO,
        "mode": "txt2video",
        "prompts": [{"positive": "Waves.", "negative": ""}],
        "form_data": {
            "seed": -1,
            "model": "model:cm-veo",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "video_director": {
                "schema_version": 1,
                "mode": "t2v",
                "settings": {"fps": 24, "duration": 6.0, "resolution": "720p", "seed": -1},
                "segments": [{"id": "seg-1", "prompt": "Waves.", "negative_prompt": ""}],
                "media": [],
            },
        },
    }
    assert (plan.cloud_task, plan.cloud_params, plan.model_id) == (
        "txt2video",
        {"duration_s": 6.0, "resolution": "720p", "aspect_ratio": "16:9"},
        "cm-veo",
    )
    assert plan.missing_models == []


def test_a_cloud_shot_with_a_first_frame_runs_img2video(core, make_doc):
    core.use_openrouter()
    doc = make_doc(clips=[SHOT], frames=[_frame("f1", "a", "first"), _frame("f2", "b", "last", 4)], assets=_images(core))

    plans = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo", quality="final")

    (plan,) = plans.shots
    assert (plan.request["mode"], plan.director_mode, plan.cloud_task, plan.resolution) == ("img2video", "flf", "img2video", "1080p")
    assert plans.warnings == []


def test_a_cloud_model_without_a_last_frame_input_keeps_only_the_first(core, make_doc):
    core.use_openrouter(core.model_spec(last_frame=False))
    doc = make_doc(clips=[SHOT], frames=[_frame("f1", "a", "first"), _frame("f2", "b", "last", 4)], assets=_images(core))

    assert _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo").shots[0].director_mode == "i2v"


def test_a_cloud_shot_snaps_its_duration_to_the_model_and_warns_past_its_longest(core, make_doc):
    core.use_openrouter()
    doc = make_doc(clips=[{"id": "s1", "dur": 5.2}, {"id": "s2", "start": 6, "dur": 9}])

    plans = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo", shots=("s1", "s2"))

    assert [plan.seconds for plan in plans.shots] == [6.0, 8.0]
    assert [warning for warning in plans.warnings if warning["code"] == "duration_clamped"] == [
        {"code": "duration_clamped", "message": "The shot is longer than the 8 s the model allows.", "data": {"shot_id": "s2", "max": 8.0}}
    ]


def test_a_cloud_preset_needs_an_enabled_model(core, make_doc):
    core.use_openrouter()
    doc = make_doc(clips=[SHOT])

    for model_id in (None, "unknown"):
        plans = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id=model_id)
        assert plans.blocks == [
            {"code": "no_model", "message": "Choose a video model the cloud backend has turned on.", "data": {"model_id": model_id}}
        ]


def test_an_image_only_cloud_model_cannot_run_a_shot_without_frame(core, make_doc):
    core.use_openrouter(core.model_spec(tasks=("img2video",)))

    plans = _plans(core, make_doc(clips=[SHOT]), preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert plans.blocks == [{"code": "no_model", "message": "The model needs a first frame for this shot.", "data": {"shot_id": "s1"}}]


def _source(**fields):
    return {
        "id": "t-1",
        "shot_id": "s1",
        "generation_id": "gen-9",
        "file_id": "file-gen-9",
        "preset_id": presets.WAN,
        "width": 832,
        "height": 480,
        "duration_s": 4.0,
        "fps": 16,
        "profile": "FL2VA",
        "prompt_text": "A lighthouse.",
        "seed": 77,
        **fields,
    }


def _source_video(core):
    core.complete("gen-9")
    core.add_media(
        {"kind": "history", "generation_id": "gen-9", "file_id": "file-gen-9"},
        "generations/2026-10-17/gen-9/1.mp4",
        "VIDEO",
        origin={"generation_id": "gen-9", "file_index": 1},
    )


def test_an_upscale_runs_seedvr2_on_the_take_video_with_the_models_of_its_image_mode(core):
    core.use_seedvr2()
    _source_video(core)

    plan = director.build_upscale(core.users["user-1"], _source(), "fhd1080")

    assert plan.request == {
        "preset_id": presets.SEEDVR2,
        "mode": "video_upscale",
        "prompts": [{"positive": "", "negative": ""}],
        "form_data": {
            "input_video": "generations/2026-10-17/gen-9/1.mp4",
            "input_video__origin": {"generation_id": "gen-9", "file_index": 1},
            "seed": -1,
            "restoration_intent": "faithful",
            "resolution_target": "fhd1080",
            "diffusion_model": "model:id-seedvr2_ema_3b_fp16.safetensors",
            "vae": "model:id-ema_vae_fp16.safetensors",
            "prompt_embedding": "model:id-pos_emb.pt",
        },
    }
    assert (plan.resolution, plan.seconds, plan.director_mode, plan.seeded) == ("1872x1080", 4.0, None, False)
    assert plan.request_for("t-2", 77)["form_data"]["seed"] == -1


@pytest.mark.parametrize("target, size", [("hd720", "hd"), ("fhd1080", "hd"), ("qhd1440", "2k"), ("uhd2160", "2k")])
def test_an_h3_take_is_upscaled_by_its_own_preset(core, target, size):
    core.use_h3()
    _source_video(core)

    plan = director.build_upscale(core.users["user-1"], _source(preset_id=presets.MINIMAX_H3), target)

    form = plan.request["form_data"]
    assert (plan.request["preset_id"], plan.request["mode"]) == (presets.MINIMAX_H3, "upscale")
    assert (form["target_size"], form["quantity"]) == (size, 1)
    assert form["model"] == "model:id-fl2va-sha" and form["upscale_model"] == "model:id-upscale_model-sha"
    assert plan.request["prompts"] == [{"positive": "A lighthouse.", "negative": ""}]


def test_an_upscale_without_the_upscaler_or_the_video_is_refused(core):
    with pytest.raises(DirectorError) as caught:
        director.build_upscale(core.users["user-1"], _source(), "fhd1080")
    assert caught.value.code == "no_preset"

    core.use_seedvr2()
    with pytest.raises(DirectorError) as caught:
        director.build_upscale(core.users["user-1"], _source(), "fhd1080")
    assert caught.value.code == "source_unavailable"


def test_an_upscale_reports_its_missing_models(core):
    core.use_seedvr2()
    _source_video(core)
    core.missing.add("pos_emb.pt")

    assert director.build_upscale(core.users["user-1"], _source(), "hd720").missing_models == ["prompt_embedding"]


def test_the_upscale_target_of_an_upscale_take_is_read_back_from_its_request():
    assert director.upscale_target({"request": {"form_data": {"resolution_target": "qhd1440"}}}) == "qhd1440"
    assert director.upscale_target({"request": {"form_data": {"target_size": "2k"}}}) == "qhd1440"
    assert director.upscale_target({"request": None}) == "fhd1080"


def _video_asset(asset_id, item_id, seconds=4.0, kind="video"):
    return {"id": asset_id, "kind": kind, "name": asset_id, "origin": {"kind": "library", "itemId": item_id}, "srcDur": seconds}


def _guide(control_id, asset_id, shot_id="s1", stale=False, start=0, dur=4):
    return {"id": control_id, "shotId": shot_id, "start": start, "dur": dur, "stale": stale, "planId": f"plan-{control_id}", "assetId": asset_id}


def _guided(core, make_doc, controls, assets=(), references=(), direction=None, language="en", prompt="The hut at dawn."):
    for item_id, value, kind in (
        ("lib-orbit", "uploads/orbit.mp4", "video"),
        ("lib-dolly", "uploads/dolly.mp4", "video"),
        ("lib-walk", "uploads/walk.mp4", "video"),
        ("lib-swim", "uploads/swim.mp4", "video"),
        ("lib-hero", "uploads/hero.png", "image"),
    ):
        core.add_media({"kind": "library", "item_id": item_id}, value, kind)
    base = [
        _video_asset("orbit", "lib-orbit"),
        _video_asset("dolly", "lib-dolly"),
        _video_asset("walk", "lib-walk"),
        _video_asset("swim", "lib-swim"),
        {"id": "hero", "kind": "image", "name": "hero", "origin": {"kind": "library", "itemId": "lib-hero"}},
    ]
    return make_doc(
        clips=[SHOT],
        prompts=[{"id": "p", "shotId": "s1", "text": prompt}],
        assets=[*base, *assets],
        references=list(references),
        controls=list(controls),
        direction={"mode": "Ref2VA", **(direction or {})},
        language=language,
    )


def _sections(prompt):
    sections = {}
    for block in prompt.split("\n\n"):
        name, _, content = block.partition(": ")
        sections[name] = content
    return sections


def _key(key_id, time, pos, target, focal):
    return {"id": key_id, "t": time, "pos": list(pos), "target": list(target), "focal": focal, "roll": 0}


def _plan3d(plan_id, start_pos, end_pos, start_target=(0, 0, -4), end_target=None, scene_id="scene-1", focal=(30, 30), dur=4):
    return {
        "id": plan_id,
        "shotId": "s1",
        "sceneId": scene_id,
        "name": plan_id,
        "start": 0,
        "dur": dur,
        "source": "trajectory",
        "preset": None,
        "amount": None,
        "camera": None,
        "keyframes": [_key("k1", 0, start_pos, start_target, focal[0]), _key("k2", dur, end_pos, end_target or start_target, focal[1])],
    }


def _around(degrees):
    return (4 * math.sin(math.radians(degrees)), 0, -4 + 4 * math.cos(math.radians(degrees)))


def _orbit(plan_id="plan-c1", degrees=10, scene_id="scene-1"):
    return _plan3d(plan_id, _around(-degrees), _around(degrees), scene_id=scene_id)


def _splat(scene_id="scene-1", source="hero"):
    return {"id": scene_id, "kind": "splat", "name": "Bow", "sourceAssetId": source, "sourceTime": None, "status": "done", "progress": 100,
            "jobId": "j1", "fileId": "f1", "count": 10, "view": {"fov": 32, "aspect": 1.73, "depth": 4}, "error": None}


ORBIT_SENTENCES = (
    "The camera arcs from left to right around the subject through about 20 degrees over the whole shot. "
    "The move follows <Video 1> forward in time: the shot opens on the viewpoint of its first frame and ends on the viewpoint of its last frame, never in reverse. "
    "This camera movement replaces any other camera movement mentioned above."
)
GUIDE_RETENTION = (
    "<Video 1> (camera path of [Shot 1]): weak_reference - camera movement only, not the look: only the direction, amplitude and speed of its camera move are followed; "
    "its content, colours, textures, blurred or stretched patches, holes and black borders are not reproduced."
)


def test_ref2va_sends_the_fresh_3d_guide_video_first_in_a_six_section_prompt_that_keeps_only_its_camera_movement(core, make_doc):
    core.use_h3()
    references = [{"id": "r1", "assetId": "hero", "scope": {"type": "global"}}, {"id": "r2", "assetId": "walk", "scope": {"type": "shot", "shotId": "s1"}}]
    doc = _guided(core, make_doc, [_guide("c1", "orbit")], references=references, direction={"univers": "A small harbour at dawn", "palette": "Cold blues."})
    doc["plans3d"] = [_orbit()]

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    assert plans.blocks == [] and plans.warnings == []
    (plan,) = plans.shots
    form = plan.request["form_data"]
    assert form["references"] == ["uploads/orbit.mp4", "uploads/walk.mp4", "uploads/hero.png"]
    assert plan.prompt_text == "\n\n".join(
        [
            "subject_definitions: <Video 1> is a rough 3D preview render of the scene, used only as the source of the camera path of [Shot 1]. "
            "<Subject 1> is the character shown in <Video 2>. <Subject 2> is the character shown in <Picture 1>.",
            "summary: [reference generation] A 4-second shot made from the description below, with its camera movement taken from <Video 1>.",
            "retention_analysis: " + GUIDE_RETENTION + "\n"
            "<Subject 1> (appears in [Shot 1]): fully_preserved - keeps the identity and the appearance.\n"
            "<Subject 2> (appears in [Shot 1]): fully_preserved - keeps the identity and the appearance.",
            "detailed_description: A small harbour at dawn. Cold blues. [Shot 1] The hut at dawn. "
            "<Subject 1> appears in the shot. <Subject 2> appears in the shot. " + ORBIT_SENTENCES,
            "overall_soundscape: The natural ambient sound of the place and the physical sounds of the action described above.",
            "non_diegetic_music: N/A",
        ]
    )
    assert plan.request["prompts"] == [{"positive": plan.prompt_text, "negative": ""}]
    assert form["video_director"]["segments"][0]["prompt"] == plan.prompt_text
    assert plan.guides == ["c1"]
    assert plan.summary()["guides"] == ["c1"]
    assert plans.renders == [{"shot_id": "s1", "control_id": "c1", "plan_id": "plan-c1", "asset_id": "orbit"}]


def test_the_picture_a_splat_scene_was_built_from_goes_with_its_guide_as_the_look_of_the_shot(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")])
    doc["plans3d"] = [_orbit()]
    doc["scenes"] = [_splat()]

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3, production="render3d_ai").shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4", "uploads/hero.png"]
    sections = _sections(plan.prompt_text)
    assert list(sections) == ["subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music"]
    assert sections["subject_definitions"] == (
        "<Video 1> is a rough 3D preview render of the scene, used only as the source of the camera path of [Shot 1]. "
        "<Subject 1> is the scene shown in <Picture 1>, a clean picture of the set of [Shot 1]."
    )
    assert sections["retention_analysis"].splitlines() == [
        GUIDE_RETENTION,
        "<Subject 1> (appears in [Shot 1]): partially_preserved - keeps the place, the subjects, the light and the colours; the framing follows the camera move.",
    ]
    assert sections["detailed_description"] == "[Shot 1] The hut at dawn. The shot takes place in <Subject 1>. " + ORBIT_SENTENCES


@pytest.mark.parametrize(
    "scene",
    [
        {**_splat(), "sourceAssetId": "walk", "sourceTime": 1.5},
        {"id": "scene-1", "kind": "glb", "name": "Set", "fileId": "f1", "cameras": []},
        {**_splat(), "sourceAssetId": "gone"},
        {**_splat(), "id": "other"},
    ],
)
def test_no_picture_goes_with_a_guide_whose_scene_was_not_built_from_a_picture_found(core, make_doc, scene):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")])
    doc["plans3d"] = [_orbit()]
    doc["scenes"] = [scene]

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4"]
    assert "<Picture" not in plan.prompt_text and "<Subject" not in plan.prompt_text


def test_the_scene_picture_of_a_stale_guide_is_not_sent_and_a_picture_shared_by_two_guides_is_sent_once(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit"), _guide("c2", "dolly"), _guide("c3", "walk", stale=True)])
    doc["plans3d"] = [_orbit("plan-c1"), _orbit("plan-c2"), _orbit("plan-c3", scene_id="scene-2")]
    doc["scenes"] = [_splat(), _splat("scene-2", source="swim")]

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4", "uploads/dolly.mp4", "uploads/hero.png"]


@pytest.mark.parametrize(
    "plan, move",
    [
        (_orbit(degrees=10), "arcs from left to right around the subject through about 20 degrees"),
        (_plan3d("plan-c1", (0.694593, 0, -0.060769), (-0.694593, 0, -0.060769)), "arcs from right to left around the subject through about 20 degrees"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, -0.6)), "pushes in toward the subject, closing about 15 % of the distance"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, 1)), "pulls back from the subject, widening the distance by about 25 %"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 4 * math.sin(math.radians(10)), -4 + 4 * math.cos(math.radians(10)))), "rises through about 10 degrees, tilting down to keep the subject framed"),
        (_plan3d("plan-c1", (0, 0, 0), (1, 0, 0), end_target=(1, 0, -4)), "trucks from left to right"),
        (_plan3d("plan-c1", (0, 0, 0), (0, -0.5, 0), end_target=(0, -0.5, -4)), "pedestals down"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, 0), end_target=(-4 * math.sin(math.radians(15)), 0, -4 * math.cos(math.radians(15)))), "pans from right to left through about 15 degrees"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, 0), end_target=(0, 1, -4)), "tilts up through about 14 degrees"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, 0), focal=(30, 50)), "zooms in"),
        (_plan3d("plan-c1", (0, 0, 0), (0, 0, 0)), "stays still"),
        (
            _plan3d("plan-c1", (-0.694593, 0, -0.060769), (0.694593, 0, -0.060769), focal=(50, 30)),
            "arcs from left to right around the subject through about 20 degrees and zooms out",
        ),
    ],
)
def test_the_prompt_spells_out_the_move_of_the_3d_shot_from_its_first_key_to_its_last(core, make_doc, plan, move):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")])
    doc["plans3d"] = [plan]

    (shot,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert f"[Shot 1] The hut at dawn. The camera {move} over the whole shot. The move follows <Video 1> forward in time" in shot.prompt_text


def test_the_keys_are_read_in_time_order_and_a_3d_shot_without_two_usable_keys_falls_back_to_following_the_video(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit"), _guide("c2", "dolly")])
    shuffled = _orbit("plan-c1")
    shuffled["keyframes"] = list(reversed(shuffled["keyframes"]))
    broken = _orbit("plan-c2")
    broken["keyframes"][1]["pos"] = [0, "x", 0]
    broken["keyframes"].append(_key("k3", 5, (0, 0, -4), (0, 0, -4), 30))
    doc["plans3d"] = [shuffled, broken]

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert _sections(plan.prompt_text)["detailed_description"] == (
        "[Shot 1] The hut at dawn. "
        "The camera arcs from left to right around the subject through about 20 degrees over the whole shot. "
        "The move follows <Video 1> forward in time: the shot opens on the viewpoint of its first frame and ends on the viewpoint of its last frame, never in reverse. "
        "The camera follows the camera path of <Video 2>. "
        "The move follows <Video 2> forward in time: the shot opens on the viewpoint of its first frame and ends on the viewpoint of its last frame, never in reverse. "
        "This camera movement replaces any other camera movement mentioned above."
    )
    assert _sections(plan.prompt_text)["summary"].endswith("with its camera movement taken from <Video 1> and <Video 2>.")


def test_the_six_sections_keep_their_english_labels_and_markers_and_follow_the_prompt_language(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")], language="fr", prompt="La cabane à l'aube")
    doc["plans3d"] = [_orbit()]
    doc["scenes"] = [_splat()]
    doc["clips"][0]["dur"] = 4.5

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert _sections(plan.prompt_text) == {
        "subject_definitions": "<Video 1> est un rendu 3D de prévisualisation, grossier, de la scène, utilisé seulement comme source de la trajectoire de caméra de [Shot 1]. "
        "<Subject 1> est la scène montrée par <Picture 1>, une image nette du décor de [Shot 1].",
        "summary": "[reference generation] Un plan de 4,5 secondes fait d'après la description ci-dessous, dont le mouvement de caméra vient de <Video 1>.",
        "retention_analysis": "<Video 1> (trajectoire de caméra de [Shot 1]): weak_reference - mouvement de caméra seulement, pas l'aspect : seuls le sens, l'amplitude et la vitesse "
        "de son mouvement de caméra sont suivis ; son contenu, ses couleurs, ses textures, ses zones floues ou étirées, ses trous et ses bords noirs ne sont pas reproduits.\n"
        "<Subject 1> (appears in [Shot 1]): partially_preserved - garde le lieu, les sujets, la lumière et les couleurs ; le cadrage suit le mouvement de caméra.",
        "detailed_description": "[Shot 1] La cabane à l'aube. Le plan se déroule dans <Subject 1>. "
        "La caméra décrit un arc de gauche à droite d'environ 20 degrés autour du sujet sur toute la durée du plan. "
        "Le mouvement suit <Video 1> dans le sens du temps : le plan s'ouvre sur le point de vue de sa première image et se termine sur celui de sa dernière image, jamais à l'envers. "
        "Ce mouvement de caméra remplace tout autre mouvement de caméra mentionné plus haut.",
        "overall_soundscape": "Le son ambiant naturel du lieu et les sons physiques de l'action décrite plus haut.",
        "non_diegetic_music": "N/A",
    }


def test_each_reference_of_a_ref2va_shot_without_guide_is_defined_and_kept_by_its_space(core, make_doc):
    core.use_h3()
    core.add_media({"kind": "library", "item_id": "lib-voice"}, "uploads/voice.wav", "audio")
    references = [
        {"id": "r1", "assetId": "hero", "space": "identite", "scope": {"type": "shot", "shotId": "s1"}},
        {"id": "r2", "assetId": "walk", "space": "mouvement", "scope": None},
        {"id": "r3", "assetId": "voice", "space": "identite", "scope": None},
        {"id": "r4", "assetId": "swim", "space": "decors3d", "scope": None},
    ]
    voice = {"id": "voice", "kind": "audio", "name": "voice", "origin": {"kind": "library", "itemId": "lib-voice"}}
    doc = _guided(core, make_doc, [], references=references, assets=[voice])

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/hero.png", "uploads/walk.mp4", "uploads/voice.wav", "uploads/swim.mp4"]
    assert _sections(plan.prompt_text) == {
        "subject_definitions": "<Subject 1> is the character shown in <Picture 1>. <Video 1> is the source of the motion of [Shot 1]. "
        "<Audio 1> is a reference sound for [Shot 1]. <Subject 2> is the setting shown in <Video 2>.",
        "summary": "[reference generation] A 4-second shot made from the description below and its references.",
        "retention_analysis": "<Subject 1> (appears in [Shot 1]): fully_preserved - keeps the identity and the appearance.\n"
        "<Video 1> (motion of [Shot 1]): attribute_transfer - its motion is carried over to the subjects of the shot.\n"
        "<Audio 1> (sound of [Shot 1]): reference - its voice or sound serves as a reference.\n"
        "<Subject 2> (appears in [Shot 1]): partially_preserved - keeps the place, the subjects, the light and the colours; the framing follows the camera move.",
        "detailed_description": "[Shot 1] The hut at dawn. <Subject 1> appears in the shot. The shot takes place in <Subject 2>.",
        "overall_soundscape": "The natural ambient sound of the place and the physical sounds of the action described above.",
        "non_diegetic_music": "N/A",
    }


def test_a_reference_video_already_sent_as_a_guide_is_not_sent_twice_and_the_guides_keep_their_ranks(core, make_doc):
    core.use_h3()
    references = [{"id": "r1", "assetId": "orbit", "scope": {"type": "shot", "shotId": "s1"}}]
    doc = _guided(core, make_doc, [_guide("c1", "orbit"), _guide("c2", "dolly")], references=references)

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4", "uploads/dolly.mp4"]
    assert _sections(plan.prompt_text)["subject_definitions"] == (
        "<Video 1> is a rough 3D preview render of the scene, used only as the source of the camera path of [Shot 1]. "
        "<Video 2> is a rough 3D preview render of the scene, used only as the source of the camera path of [Shot 1]."
    )
    assert plan.guides == ["c1", "c2"]


def test_the_shot_prompt_outside_ref2va_is_the_instruction_then_the_direction_without_any_section(core, make_doc):
    core.use_wan()
    doc = _guided(core, make_doc, [], direction={"mode": "FL2VA", "univers": "A harbour."})

    (plan,) = _plans(core, doc).shots

    assert plan.prompt_text == "The hut at dawn.\nA harbour."


def test_the_3d_guides_count_within_the_three_reference_videos_of_a_shot(core, make_doc):
    core.use_h3()
    references = [{"id": f"r{index}", "assetId": asset, "scope": {"type": "global"}} for index, asset in enumerate(("walk", "swim"))]
    doc = _guided(core, make_doc, [_guide("c1", "orbit"), _guide("c2", "dolly")], references=references)

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4", "uploads/dolly.mp4", "uploads/walk.mp4"]


def test_a_stale_guide_is_left_out_with_a_warning_and_does_not_block(core, make_doc):
    core.use_h3()
    references = [{"id": "r1", "assetId": "hero", "scope": None}]
    doc = _guided(core, make_doc, [_guide("c1", "orbit", stale=True)], references=references)

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    (plan,) = plans.shots
    assert plan.request["form_data"]["references"] == ["uploads/hero.png"]
    assert _sections(plan.prompt_text)["detailed_description"] == "[Shot 1] The hut at dawn. <Subject 1> appears in the shot." and plan.guides == []
    assert plans.warnings == [
        {"code": "stale_guide", "message": "The 3D guide of the shot is stale: render it again.", "data": {"shot_id": "s1", "control_id": "c1"}}
    ]
    assert plans.renders == []


def test_a_guide_video_under_two_seconds_is_sent_with_a_warning(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "short")], assets=[_video_asset("short", "lib-orbit", seconds=1.5)])

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3)

    assert plans.shots[0].request["form_data"]["references"] == ["uploads/orbit.mp4"]
    assert plans.warnings == [
        {
            "code": "guide_too_short",
            "message": "The 3D guide video of the shot is shorter than the 2 s MiniMax-H3 reads.",
            "data": {"shot_id": "s1", "control_id": "c1", "min": 2.0},
        }
    ]


def test_a_guide_without_a_known_length_is_as_long_as_its_control(core, make_doc):
    core.use_h3()
    unknown = {**_video_asset("unknown", "lib-orbit"), "srcDur": None}
    doc = _guided(core, make_doc, [_guide("c1", "unknown", dur=1.0)], assets=[unknown])

    assert [warning["code"] for warning in _plans(core, doc, preset_id=presets.MINIMAX_H3).warnings] == ["guide_too_short"]


def test_a_guide_linked_to_no_shot_counts_for_the_shots_it_overlaps_and_other_guides_are_ignored(core, make_doc):
    core.use_h3()
    controls = [
        _guide("over", "orbit", shot_id=None, start=3, dur=5),
        _guide("after", "dolly", shot_id=None, start=4, dur=2),
        _guide("other", "walk", shot_id="s2"),
        {**_guide("import", "swim"), "source": "import"},
        _guide("unrendered", None),
    ]
    doc = _guided(core, make_doc, controls)

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4"] and plan.guides == ["over"]


def test_a_scene3d_control_with_neither_a_3d_shot_nor_a_video_is_not_a_guide(core, make_doc):
    core.use_wan()
    simulated = {"id": "simulated", "shotId": "s1", "start": 0, "dur": 4, "stale": False, "planId": None, "assetId": None}
    legacy = {"id": "legacy", "shotId": None, "start": 0, "dur": 4, "stale": True}
    doc = _guided(core, make_doc, [simulated, legacy, _guide("planned", None)], direction={"mode": "FL2VA"})

    assert [guide["id"] for guide in director.shot_guides(doc, doc["clips"][0])] == ["planned"]
    doc["controls"] = doc["controls"][:2]
    assert director.shot_guides(doc, doc["clips"][0]) == []
    assert [warning["code"] for warning in _plans(core, doc).warnings if warning["code"] != "fl2va_no_frame"] == []


def test_a_guide_whose_media_is_not_a_video_is_not_sent_as_a_camera_reference(core, make_doc):
    core.use_h3()
    references = [{"id": "r1", "assetId": "walk", "scope": None}]
    doc = _guided(core, make_doc, [_guide("c1", "hero"), _guide("c2", "gone")], references=references)

    (plan,) = _plans(core, doc, preset_id=presets.MINIMAX_H3).shots

    assert plan.request["form_data"]["references"] == ["uploads/walk.mp4"]
    assert _sections(plan.prompt_text)["detailed_description"] == "[Shot 1] The hut at dawn. <Subject 1> appears in the shot." and plan.guides == []


@pytest.mark.parametrize("stale", [False, True])
def test_a_3d_guide_on_a_shot_generated_without_references_warns_that_only_ref2va_follows_it(core, make_doc, stale):
    core.use_wan()
    doc = _guided(core, make_doc, [_guide("c1", "orbit", stale=stale)], direction={"mode": "FL2VA"})

    plans = _plans(core, doc)

    (plan,) = plans.shots
    assert "references" not in plan.request["form_data"] and plan.prompt_text == "The hut at dawn."
    assert [warning for warning in plans.warnings if warning["code"] != "fl2va_no_frame"] == [
        {"code": "guide_needs_refs", "message": "The shot has a 3D guide video: only a Ref2VA preset follows it.", "data": {"shot_id": "s1"}}
    ]


def test_a_3d_guide_on_a_cloud_shot_warns_that_only_ref2va_follows_it(core, make_doc):
    core.use_openrouter()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")], direction={"mode": "FL2VA"})

    plans = _plans(core, doc, preset_id=presets.OPENROUTER_VIDEO, model_id="cm-veo")

    assert "guide_needs_refs" in [warning["code"] for warning in plans.warnings]


def test_the_3d_render_and_ai_mode_runs_ref2va_whatever_the_project_profile(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [_guide("c1", "orbit")], direction={"mode": "FL2VA"})

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3, production="render3d_ai")

    (plan,) = plans.shots
    assert (plans.profile, plans.production, plan.director_mode, plan.preset_mode) == ("Ref2VA", "render3d_ai", "refs", "refs")
    assert plan.request["form_data"]["references"] == ["uploads/orbit.mp4"] and plans.warnings == []


def test_the_3d_render_and_ai_mode_warns_about_a_shot_without_a_rendered_guide(core, make_doc):
    core.use_h3()
    doc = _guided(core, make_doc, [], references=[{"id": "r1", "assetId": "hero", "scope": None}])

    plans = _plans(core, doc, preset_id=presets.MINIMAX_H3, production="render3d_ai")

    assert plans.warnings == [{"code": "render_missing", "message": "The shot has no up-to-date 3D render.", "data": {"shot_id": "s1"}}]
    assert plans.shots[0].request["form_data"]["references"] == ["uploads/hero.png"]


@pytest.mark.parametrize("preset_id", [presets.MINIMAX_H3_12GB, presets.WAN])
def test_the_3d_render_and_ai_mode_needs_a_minimax_h3_preset_with_its_refs_mode(core, make_doc, preset_id):
    core.use_wan()
    core.use_h3_variant(presets.MINIMAX_H3_12GB, "MiniMax-H3 (12 GB)")
    doc = _guided(core, make_doc, [_guide("c1", "orbit")])

    plans = _plans(core, doc, preset_id=preset_id, production="render3d_ai")

    assert plans.shots == []
    assert plans.blocks == [
        {
            "code": "refs_preset_needed",
            "message": "The 3D render + AI mode needs a MiniMax-H3 preset with its References mode.",
            "data": {"preset_id": preset_id},
        }
    ]


def test_the_3d_render_mode_gives_each_shot_its_latest_fresh_render_without_a_preset(core, make_doc):
    doc = _guided(core, make_doc, [_guide("c1", "orbit"), _guide("c2", "dolly"), _guide("c3", "walk", stale=True), _guide("c4", "missing")])
    doc["clips"].append({**doc["clips"][0], "id": "s2", "start": 4})

    plans = director.build_plans(core.users["user-1"], doc, ["s1", "s2", "nowhere"], None, "draft", production="render3d")

    assert (plans.preset, plans.production, plans.shots, plans.blocks) == (None, "render3d", [], [])
    assert plans.renders == [{"shot_id": "s1", "control_id": "c2", "plan_id": "plan-c2", "asset_id": "dolly"}]
    assert [(warning["code"], warning["data"]) for warning in plans.warnings] == [
        ("stale_guide", {"shot_id": "s1", "control_id": "c3"}),
        ("render_missing", {"shot_id": "s2"}),
    ]


def test_the_3d_render_mode_without_any_render_or_shot_is_blocked(core, make_doc):
    doc = _guided(core, make_doc, [])
    user = core.users["user-1"]

    assert [block["code"] for block in director.build_plans(user, doc, ["s1"], None, "draft", production="render3d").blocks] == ["no_render"]
    assert [block["code"] for block in director.build_plans(user, doc, [], None, "draft", production="render3d").blocks] == ["no_shots"]
