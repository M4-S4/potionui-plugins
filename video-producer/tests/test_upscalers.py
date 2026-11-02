import asyncio

import pytest

from backend import director, estimate, final_pass, generation, presets, projects, takes, tracker, upscalers
from backend.director import DirectorError
from backend.estimate import Order
from backend.final_pass import PassError

SHOT = {"id": "s1", "start": 0, "dur": 4}


def _done_take(core, make_doc, make_project, preset_id=presets.WAN, resolution=None, **parts):
    doc = make_doc(**({"clips": [SHOT]} | parts))
    if resolution:
        doc["resolution"] = resolution
    project = make_project(doc=doc)
    user = core.users["user-1"]
    order = Order(shots=["s1"], quality="draft", variants=1, preset_id=preset_id)
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    (take,) = asyncio.run(generation.start(user, project, evaluation))
    core.complete(take["generation_id"])
    asyncio.run(tracker.Tracker().tick())
    core.add_media({"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}, "generations/x/1.mp4", "VIDEO")
    return project, takes.get_take(take["id"])


def _source(**fields):
    return {"id": "t-1", "shot_id": "s1", "generation_id": "gen-9", "file_id": "file-gen-9", "preset_id": presets.WAN, "width": 832, "height": 480, "duration_s": 4.0, "fps": 16, "seed": 77, **fields}


def _video(core):
    core.complete("gen-9")
    core.add_media({"kind": "history", "generation_id": "gen-9", "file_id": "file-gen-9"}, "generations/x/9.mp4", "VIDEO")


@pytest.mark.parametrize(
    "aspect, resolution, framing, size, target",
    [
        ("16:9", "1080p", "auto", (832, 480), "fhd1080"),
        ("2.39:1", "1080p", "auto", (832, 480), "fhd1080"),
        ("16:9", "4K", "auto", (832, 480), "uhd2160"),
        ("16:9", "1440p", "auto", (1280, 720), "qhd1440"),
        ("16:9", "720p", "auto", (832, 480), "hd720"),
        ("1:1", "1080p", "auto", (832, 480), "hd720"),
        ("1:1", "1080p", "crop", (832, 480), "fhd1080"),
        ("9:16", "1080p", "auto", (480, 832), "fhd1080"),
        ("16:9", "720p", "auto", (1920, 1080), "fhd1080"),
    ],
)
def test_auto_gives_the_smallest_target_that_fills_the_delivery_frame_as_the_export_shows_it(aspect, resolution, framing, size, target):
    doc = {"aspect": aspect, "resolution": resolution, "framing": framing}

    assert upscalers.auto_target(doc, *size) == target


def test_auto_without_a_take_size_follows_the_delivery_resolution_and_a_named_target_is_kept():
    assert upscalers.auto_target({"resolution": "1440p"}, None, None) == "qhd1440"
    assert upscalers.resolve_target("hd720", {"resolution": "4K"}, {"width": 832, "height": 480}) == "hd720"
    assert upscalers.resolve_target("auto", {"resolution": "4K"}, {"width": 832, "height": 480}) == "uhd2160"
    assert upscalers.TARGETS == ("auto", "hd720", "fhd1080", "qhd1440", "uhd2160")


def test_the_upscaler_of_a_take_is_read_from_its_preset():
    assert upscalers.of_preset(presets.SEEDVR2) == "seedvr2"
    assert upscalers.of_preset(presets.RTX_UPSCALE) == "rtx"
    assert upscalers.of_preset(presets.MINIMAX_H3) == "engine"


def test_rtx_is_ready_only_with_its_video_mode_its_target_field_and_nvidia_vfx(core):
    user = core.users["user-1"]
    assert upscalers.ready(user) == {"seedvr2": False, "rtx": False, "rtx_checked": True}

    core.use_seedvr2()
    core.use_rtx(installed=False)
    assert upscalers.ready(user) == {"seedvr2": True, "rtx": False, "rtx_checked": True}

    core.modules.add("nvvfx")
    assert upscalers.ready(user) == {"seedvr2": True, "rtx": True, "rtx_checked": True}

    core.use_rtx(target=False)
    assert upscalers.ready(user)["rtx"] is False


def test_without_a_native_engine_no_upscaler_is_ready_and_no_upscale_is_planned(core):
    core.use_seedvr2()
    core.use_rtx()
    core.use_h3()
    _video(core)
    core.cloud_only()

    assert upscalers.ready(core.users["user-1"]) == {"seedvr2": False, "rtx": False, "rtx_checked": True}
    for upscaler in ("auto", "seedvr2", "rtx", "engine"):
        with pytest.raises(DirectorError) as caught:
            director.build_upscale(core.users["user-1"], _source(preset_id=presets.MINIMAX_H3), "fhd1080", upscaler)
        assert caught.value.code == "no_native_engine"
        assert caught.value.message == (
            "An upscaler runs on a native backend of this instance, and none is enabled: "
            "enable the native backend of this machine or a native remote worker."
        )


def test_on_a_remote_worker_rtx_is_offered_without_nvidia_vfx_here_and_said_unchecked(core):
    core.use_rtx(installed=False)
    core.use_worker()
    _video(core)

    assert upscalers.ready(core.users["user-1"]) == {"seedvr2": False, "rtx": True, "rtx_checked": False}
    assert director.build_upscale(core.users["user-1"], _source(), "fhd1080", "rtx").request["preset_id"] == presets.RTX_UPSCALE
    assert director.build_upscale(core.users["user-1"], _source(), "fhd1080").request["preset_id"] == presets.RTX_UPSCALE


def test_the_native_engine_of_the_readiness_is_the_first_of_the_engines_given(core):
    core.use_rtx(installed=False)
    local, remote = dict(core.backends[0]), {"id": "b-remote", "name": "Render box", "engine": "native", "driver": "native.remote", "execution_device": "remote"}
    core.backends = [local, remote]

    assert upscalers.ready(core.users["user-1"])["rtx_checked"] is True
    assert upscalers.ready(core.users["user-1"], [{**remote, "kind": "remote"}]) == {"seedvr2": False, "rtx": True, "rtx_checked": False}
    assert upscalers.ready(core.users["user-1"], []) == {"seedvr2": False, "rtx": False, "rtx_checked": True}


def test_rtx_upscales_a_take_to_the_short_side_of_its_target_without_a_seed_tuned_for_a_compressed_source(core):
    core.use_rtx()
    _video(core)

    plan = director.build_upscale(core.users["user-1"], _source(), "fhd1080", "rtx")

    assert (plan.request["preset_id"], plan.request["mode"]) == (presets.RTX_UPSCALE, "video_upscale")
    assert plan.request["form_data"] == {
        "input_video": "generations/x/9.mp4",
        "intent": "upscale_highbitrate",
        "quality": "ultra",
        "target_short_side": 1080,
        "keep_audio": True,
    }
    assert (plan.resolution, plan.missing_models) == ("1872x1080", [])
    assert director.upscale_target({"request": plan.request}) == "fhd1080"
    assert director.upscale_rtx_source({"request": plan.request}) == "compressed"


def test_rtx_is_tuned_for_a_clean_source_only_when_told_so(core):
    core.use_rtx()
    _video(core)

    plan = director.build_upscale(core.users["user-1"], _source(), "fhd1080", "rtx", "clean")

    assert plan.request["form_data"]["intent"] == "upscale"
    assert director.upscale_rtx_source({"request": plan.request}) == "clean"
    assert upscalers.RTX_SOURCES == ("compressed", "clean")
    assert upscalers.rtx_source_of("denoise") == upscalers.rtx_source_of(None) == "compressed"


def test_rtx_is_refused_when_it_cannot_aim_at_a_size_or_nvidia_vfx_is_missing(core):
    _video(core)
    core.use_rtx(target=False)
    with pytest.raises(DirectorError) as caught:
        director.build_upscale(core.users["user-1"], _source(), "fhd1080", "rtx")
    assert caught.value.code == "upscaler_outdated"

    core.use_rtx(installed=False)
    core.modules.clear()
    with pytest.raises(DirectorError) as caught:
        director.build_upscale(core.users["user-1"], _source(), "fhd1080", "rtx")
    assert caught.value.code == "upscaler_missing"


def test_auto_falls_back_to_rtx_only_when_seedvr2_is_missing(core):
    core.use_rtx()
    _video(core)

    assert director.build_upscale(core.users["user-1"], _source(), "hd720").request["preset_id"] == presets.RTX_UPSCALE

    core.use_seedvr2()
    assert director.build_upscale(core.users["user-1"], _source(), "hd720").request["preset_id"] == presets.SEEDVR2
    assert director.build_upscale(core.users["user-1"], _source(), "hd720", "rtx").request["preset_id"] == presets.RTX_UPSCALE


def test_the_engine_upscales_an_h3_take_in_its_own_mode_and_refuses_another_take(core):
    core.use_h3()
    core.use_seedvr2()
    _video(core)

    plan = director.build_upscale(core.users["user-1"], _source(preset_id=presets.MINIMAX_H3), "qhd1440", "engine")
    assert (plan.request["preset_id"], plan.request["mode"]) == (presets.MINIMAX_H3, "upscale")

    assert director.build_upscale(core.users["user-1"], _source(preset_id=presets.MINIMAX_H3), "qhd1440", "seedvr2").request["preset_id"] == presets.SEEDVR2
    with pytest.raises(DirectorError) as caught:
        director.build_upscale(core.users["user-1"], _source(), "qhd1440", "engine")
    assert caught.value.code == "upscale_unsupported"


def test_the_final_pass_takes_the_auto_target_and_every_upscaler():
    order = final_pass.parse_order({"takes": ["t1"], "method": "upscale", "target": "auto", "upscaler": "rtx"})

    assert (order.target, order.upscaler) == ("auto", "rtx")
    assert final_pass.parse_order({"takes": ["t1"], "method": "upscale", "target": "auto", "upscaler": "engine"}).upscaler == "engine"
    for body in ({"takes": ["t1"], "method": "upscale", "target": "8k"}, {"takes": ["t1"], "method": "upscale", "target": "auto", "upscaler": "turbo"}):
        with pytest.raises(PassError):
            final_pass.parse_order(body)


def test_a_final_take_by_rtx_at_the_auto_target_gets_the_size_of_the_film(core, make_doc, make_project):
    core.use_wan()
    core.use_rtx()
    project, source = _done_take(core, make_doc, make_project, aspect="16:9", resolution="4K")

    final = asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "auto", "rtx"))

    assert (final["preset_id"], final["kind"], final["resolution"]) == (presets.RTX_UPSCALE, "upscale", "3744x2160")
    assert core.submitted[-1][1]["form_data"]["target_short_side"] == 2160


def test_a_failed_rtx_upscale_is_retried_with_rtx_and_the_same_target(core, make_doc, make_project):
    core.use_wan()
    core.use_seedvr2()
    core.use_rtx()
    project, source = _done_take(core, make_doc, make_project)
    upscale = asyncio.run(generation.final(core.users["user-1"], project, source, "upscale", "qhd1440", "rtx"))
    core.fail(upscale["generation_id"])
    asyncio.run(tracker.Tracker().tick())

    retried = asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(upscale["id"])))

    assert retried["preset_id"] == presets.RTX_UPSCALE
    assert core.submitted[-1][1]["form_data"]["target_short_side"] == 1440


def test_the_retired_post_switches_of_the_engine_are_dropped_from_a_document(make_doc):
    doc = make_doc()
    old = {**doc, "engine": {**doc["engine"], "post": {"upscale": False, "interpolation": True, "denoise": True}}}

    migrated = projects.migrate(old)

    assert "post" not in migrated["engine"]
    assert {key: value for key, value in migrated["engine"].items()} == doc["engine"]
    projects.validate_doc(migrated)
    with pytest.raises(projects.DocError):
        projects.validate_doc(old)
