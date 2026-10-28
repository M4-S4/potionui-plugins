import asyncio

import pytest

from backend import cadence, core_bridge, estimate, formats, generation, presets, renditions, takes, tracker
from backend.estimate import Order

SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4, "firstFromPrevious": False}]
BASE = "/api/plugins/video-producer"


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _media(core, generation_id):
    ref = {"kind": "history", "generation_id": generation_id, "file_id": f"file-{generation_id}"}
    core.add_media(ref, f"generations/x/{generation_id}.mp4", "VIDEO")


def _finish(core, project_id, **output):
    while any(take["status"] in takes.ACTIVE for take in takes.list_takes(project_id)):
        for take in takes.list_active(project_id):
            if take["generation_id"] and take["generation_id"] not in core.files:
                core.complete(take["generation_id"], **output)
                _media(core, take["generation_id"])
        _tick()


def _drafts(core, make_project, clips=SHOTS, film_fps=None, **output):
    project = make_project(clips=clips)
    if film_fps is not None:
        from backend import projects

        doc = {**project["doc"], "fps": film_fps}
        projects.save_project(project["id"], doc, project["version"])
        project = projects.get_project(project["id"])
    user = core.users["user-1"]
    order = Order(shots=[clip["id"] for clip in clips], quality="draft", variants=1, preset_id=presets.WAN)
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    created = asyncio.run(generation.start(user, project, evaluation))
    _finish(core, project["id"], **output)
    return project, [takes.get_take(take["id"]) for take in created]


@pytest.mark.parametrize(
    "take_fps, fps, needed",
    [
        (16, 24, True),
        (16, 25, True),
        (16, 30, True),
        (24, 25, False),
        (24, 26.8, True),
        (25, 24, False),
        (24, 48, True),
        (25, 50, True),
        (30, 60, True),
        (None, 25, False),
        (0, 25, False),
        (16, None, False),
    ],
)
def test_a_take_is_conformed_when_it_is_slower_than_the_film_by_the_table_s_share_or_more(take_fps, fps, needed):
    assert cadence.needs_conform(take_fps, fps) is needed


def test_the_cadences_rule_comes_from_the_formats_table():
    assert formats.CADENCES == (24, 25, 30, 48, 50, 60)
    assert formats.DEFAULT_CADENCE == 25
    assert formats.SLOWER == 0.1


@pytest.mark.parametrize("fps, target", [(25, 25), (48, 48), (60.0, 60), (23.976, None), (29.97, None), (12, None), (None, 25)])
def test_only_a_cadence_of_the_table_is_a_frame_rate_takes_are_brought_to(fps, target):
    assert cadence.target_of({} if fps is None else {"fps": fps}) == target


@pytest.mark.parametrize(
    "final_pass, choice",
    [(None, "auto"), ({}, "auto"), ({"interpolator": "rife"}, "rife"), ({"interpolator": "rtx"}, "rtx"), ({"interpolator": "high"}, "auto")],
)
def test_the_film_asks_for_auto_unless_its_final_pass_choices_name_an_interpolator(final_pass, choice):
    assert cadence.choice_of({} if final_pass is None else {"finalPass": final_pass}) == choice


def test_no_interpolator_is_ready_without_video_tools_or_frame_generation(core):
    assert cadence.ready(core.users["user-1"]) == {"rife": False, "rtx": False}


def test_rife_is_ready_with_video_tools_that_takes_a_target_frame_rate(core):
    core.use_video_tools()

    assert cadence.ready(core.users["user-1"]) == {"rife": True, "rtx": False}


def test_rife_is_not_ready_with_a_video_tools_older_than_the_target_frame_rate(core):
    core.use_video_tools(target=False)

    assert cadence.ready(core.users["user-1"])["rife"] is False


@pytest.mark.parametrize(
    "version, module, target, ready",
    [
        ("0.2.0.0", True, True, True),
        ("0.3", True, True, True),
        ("0.1.0.0", True, True, False),
        (None, True, True, False),
        ("0.2.0.0", False, True, False),
        ("0.2.0.0", True, False, False),
    ],
)
def test_frame_generation_needs_the_interpolate_mode_and_nvidia_vfx_0_2(core, version, module, target, ready):
    core.use_frame_generation(version=version, target=target)
    if not module:
        core.modules.discard("nvvfx")

    assert cadence.ready(core.users["user-1"])["rtx"] is ready


def test_an_rtx_upscale_without_its_interpolate_mode_brings_no_frame_generation(core):
    core.use_rtx()
    core.versions["nvidia-vfx"] = "0.2.0.0"

    assert cadence.ready(core.users["user-1"])["rtx"] is False


@pytest.mark.parametrize(
    "choice, found, picked",
    [
        ("auto", {"rife": True, "rtx": True}, "rtx"),
        ("auto", {"rife": True, "rtx": False}, "rife"),
        ("auto", {"rife": False, "rtx": False}, None),
        ("rife", {"rife": True, "rtx": True}, "rife"),
        ("rtx", {"rife": True, "rtx": False}, None),
        ("rife", {"rife": False, "rtx": True}, None),
    ],
)
def test_auto_takes_frame_generation_when_it_is_ready_and_rife_otherwise(choice, found, picked):
    assert cadence.pick(choice, found) == picked


def test_a_rife_request_keeps_the_duration_and_the_sound_detects_cuts_and_uses_rife_4_25(core, make_project):
    core.use_wan()
    core.use_video_tools()
    _, drafts = _drafts(core, make_project)

    request, missing = cadence.build_request(core.users["user-1"], drafts[0], 25, "rife")

    assert missing == []
    assert request == {
        "preset_id": presets.VIDEO_TOOLS,
        "mode": "interpolate",
        "prompts": [{"positive": "", "negative": ""}],
        "form_data": {
            "input_video": f"generations/x/{drafts[0]['generation_id']}.mp4",
            "target_fps": 25,
            "keep_audio": True,
            "scene_detection": True,
            "flow_scale": 1.0,
            "model": "model:id-flownet_v4.25.pth",
        },
    }


def test_rife_halves_its_flow_from_a_1440_short_side(core, make_project):
    core.use_wan()
    core.use_video_tools()
    _, drafts = _drafts(core, make_project, width=2560, height=1440)

    request, _ = cadence.build_request(core.users["user-1"], drafts[0], 50, "rife")

    assert request["form_data"]["flow_scale"] == 0.5
    assert request["form_data"]["target_fps"] == 50


def test_a_missing_rife_weight_is_reported(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.missing.add("flownet_v4.25.pth")
    _, drafts = _drafts(core, make_project)

    _, missing = cadence.build_request(core.users["user-1"], drafts[0], 25, "rife")

    assert missing == ["model"]


def test_a_frame_generation_request_asks_for_the_medium_model_and_no_weight(core, make_project):
    core.use_wan()
    core.use_frame_generation()
    _, drafts = _drafts(core, make_project)

    request, missing = cadence.build_request(core.users["user-1"], drafts[0], 30, "rtx")

    assert missing == []
    assert request["preset_id"] == presets.RTX_UPSCALE
    assert request["mode"] == "interpolate"
    assert request["form_data"] == {
        "input_video": f"generations/x/{drafts[0]['generation_id']}.mp4",
        "target_fps": 30,
        "keep_audio": True,
        "scene_detection": True,
        "mode": "medium",
    }


def test_the_time_of_a_version_comes_from_the_interpolator_s_measures(project_db):
    assert cadence.seconds_for("rife", "b-local", "832x480", 4.0) is None
    takes.add_calibration(presets.VIDEO_TOOLS, "b-local", "832x480", 4.0, 2000)

    assert cadence.seconds_for("rife", "b-local", "832x480", 4.0) == pytest.approx(2.0)
    assert cadence.seconds_for(None, "b-local", "832x480", 4.0) is None
    assert cadence.seconds_for("rife", "b-local", "832x480", None) is None
