import asyncio

import pytest

from backend import final_pass, generation, presets, projects, renditions, takes, tracker
from backend.generation import Blocked
from backend.renditions import Refused

from .test_cadence import SHOTS, _drafts, _media, _tick

BASE = "/api/plugins/video-producer"


def _order(core, project, take, choice=None, owner="user-1"):
    return renditions.order(core.users[owner], projects.get_project(project["id"]), takes.get_take(take["id"]), choice)


def _settle_all(core, **output):
    for rendition in renditions.list_active():
        if rendition["generation_id"] and rendition["generation_id"] not in core.files:
            core.complete(rendition["generation_id"], **output)
    _tick()


def test_a_finished_slower_take_gets_a_queued_version_at_the_film_s_frame_rate(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)

    rendition = _order(core, project, drafts[0])

    assert rendition["status"] == "queued"
    assert rendition["fps"] == 25.0
    assert rendition["source_fps"] == 16.0
    assert rendition["interpolator"] == "rife"
    assert rendition["preset_id"] == presets.VIDEO_TOOLS
    assert rendition["resolution"] == "832x480"
    assert rendition["request"]["idempotency_key"] == f"vp:rendition:{rendition['id']}"
    assert rendition["request"]["form_data"]["target_fps"] == 25


def test_asking_twice_gives_the_version_already_on_its_way(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)

    first = _order(core, project, drafts[0])
    again = _order(core, project, drafts[0])

    assert again["id"] == first["id"]
    assert len(renditions.list_for_take(drafts[0]["id"])) == 1


@pytest.mark.parametrize("film_fps, take_fps", [(25, 24.0), (24, 25.0), (25, 25.0)])
def test_a_take_as_fast_as_the_film_or_within_the_table_s_share_gets_no_version(core, make_project, film_fps, take_fps):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project, film_fps=film_fps, fps=take_fps)

    with pytest.raises(Refused) as caught:
        _order(core, project, drafts[0])

    assert caught.value.block["code"] == "not_slower"


def test_a_film_at_a_frame_rate_outside_the_table_cannot_bring_takes_to_it(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project, film_fps=23.976)

    with pytest.raises(Refused) as caught:
        _order(core, project, drafts[0])

    assert caught.value.block["code"] == "cadence_unknown"


def test_without_an_interpolator_the_version_is_refused_with_what_to_install(core, make_project):
    core.use_wan()
    project, drafts = _drafts(core, make_project)

    with pytest.raises(Refused) as caught:
        _order(core, project, drafts[0])

    assert caught.value.block["code"] == "interpolator_missing"
    assert "Video Tools" in caught.value.block["message"]


def test_frame_generation_is_taken_when_it_is_ready_and_rife_when_the_film_asks_for_it(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_frame_generation()
    project, drafts = _drafts(core, make_project)

    automatic = _order(core, project, drafts[0])
    asked = _order(core, project, drafts[1], "rife")

    assert (automatic["interpolator"], automatic["preset_id"]) == ("rtx", presets.RTX_UPSCALE)
    assert automatic["request"]["form_data"]["mode"] == "medium"
    assert (asked["interpolator"], asked["preset_id"]) == ("rife", presets.VIDEO_TOOLS)


def test_a_missing_rife_weight_refuses_the_version(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.missing.add("flownet_v4.25.pth")
    project, drafts = _drafts(core, make_project)

    with pytest.raises(Refused) as caught:
        _order(core, project, drafts[0])

    assert caught.value.block["code"] == "missing_models"


def test_the_version_is_handed_to_the_core_finishes_and_measures_the_interpolator(core, make_project, store):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])

    _tick()
    handed = renditions.get(rendition["id"])
    core.states[handed["generation_id"]] = {"id": handed["generation_id"], "status": "running", "progress": 0.5, "backend_id": "b-local"}
    _tick()
    running = renditions.get(rendition["id"])
    core.complete(handed["generation_id"], duration_ms=3000, fps=25.0)
    _tick()
    done = renditions.get(rendition["id"])

    assert handed["generation_id"] and core.submitted[-1][1]["preset_id"] == presets.VIDEO_TOOLS
    assert (running["status"], running["progress"]) == ("running", 50.0)
    assert done["status"] == "done"
    assert done["file_path"] == f"generations/2026-10-17/{handed['generation_id']}/1.mp4"
    assert takes.calibration(presets.VIDEO_TOOLS, "b-local", "832x480") == [(4.0, 3000)]
    assert renditions.public(done)["url"] == f"/api/media/generations/{handed['generation_id']}/1.mp4"


def test_a_failed_version_tells_its_owner(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])
    _tick()
    generation_id = renditions.get(rendition["id"])["generation_id"]
    core.fail(generation_id, code="generation_failed", message="RIFE could not read the video.")

    _tick()

    failed = renditions.get(rendition["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "generation_failed", "RIFE could not read the video.")
    assert core.notified[-1]["title"] == "Frame rate version failed"
    assert core.notified[-1]["metadata"]["rendition_id"] == rendition["id"]


def test_the_core_s_hooks_settle_a_version(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])
    _tick()
    generation_id = renditions.get(rendition["id"])["generation_id"]
    core.complete(generation_id, duration_ms=2000)

    assert generation.settle_from_hook(generation_id, "completed", duration=2.0) is True
    assert renditions.get(rendition["id"])["status"] == "done"
    assert generation.settle_from_hook(generation_id, "completed") is False


def test_versions_share_the_parallel_slots_with_the_takes(core, make_project, store):
    core.use_wan()
    core.use_video_tools()
    store[("max_parallel_jobs", None)] = "1"
    project, drafts = _drafts(core, make_project)
    first = _order(core, project, drafts[0])
    second = _order(core, project, drafts[1])

    _tick()

    assert renditions.get(first["id"])["generation_id"] is not None
    assert renditions.get(second["id"])["generation_id"] is None
    core.complete(renditions.get(first["id"])["generation_id"])
    _tick()
    assert renditions.get(second["id"])["generation_id"] is not None


def test_a_version_ordered_for_a_take_still_being_made_waits_for_it(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    final = asyncio.run(generation.final(core.users["user-1"], projects.get_project(project["id"]), drafts[0], "upscale", "fhd1080"))

    waiting = _order(core, project, final)
    assert (waiting["status"], waiting["request"]) == ("waiting", None)

    core.complete(final["generation_id"], width=1872, height=1080)
    _media(core, final["generation_id"])
    _tick()

    ready = renditions.get(waiting["id"])
    assert ready["status"] in ("queued", "running")
    assert ready["resolution"] == "1872x1080"
    assert ready["request"]["form_data"]["input_video"] == f"generations/x/{final['generation_id']}.mp4"


def test_a_version_waiting_for_a_take_that_fails_is_cancelled(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    final = asyncio.run(generation.final(core.users["user-1"], projects.get_project(project["id"]), drafts[0], "upscale", "fhd1080"))
    waiting = _order(core, project, final)
    core.fail(final["generation_id"])

    _tick()

    ended = renditions.get(waiting["id"])
    assert (ended["status"], ended["error_code"]) == ("cancelled", "take_ended")


def test_making_a_take_final_with_conform_orders_its_version_after_it(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)

    final = asyncio.run(
        generation.final(core.users["user-1"], projects.get_project(project["id"]), drafts[0], "upscale", "fhd1080", conform=True)
    )

    [rendition] = renditions.list_for_take(final["id"])
    assert (rendition["status"], rendition["fps"], rendition["interpolator"]) == ("waiting", 25.0, "rife")


def test_conforming_a_final_without_an_interpolator_blocks_before_anything_starts(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    before = len(takes.list_takes(project["id"]))

    with pytest.raises(Blocked) as caught:
        asyncio.run(generation.final(core.users["user-1"], projects.get_project(project["id"]), drafts[0], "upscale", "fhd1080", conform=True))

    assert [block["code"] for block in caught.value.blocks] == ["interpolator_missing"]
    assert len(takes.list_takes(project["id"])) == before


def test_retrying_a_final_that_was_to_have_a_version_orders_it_again(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    owner = core.users["user-1"]
    final = asyncio.run(generation.final(owner, projects.get_project(project["id"]), drafts[0], "upscale", "fhd1080", conform=True))
    core.fail(final["generation_id"])
    _tick()

    again = asyncio.run(generation.retry(owner, projects.get_project(project["id"]), takes.get_take(final["id"])))

    assert [item["status"] for item in renditions.list_for_take(again["id"])] == ["waiting"]


def test_deleting_a_take_cancels_and_deletes_its_versions(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])
    _tick()
    generation_id = renditions.get(rendition["id"])["generation_id"]

    asyncio.run(generation.delete(core.users["user-1"], takes.get_take(drafts[0]["id"])))

    assert renditions.list_for_take(drafts[0]["id"]) == []
    assert ("user-1", generation_id) in core.cancelled


def placed(project, drafts, fps=None):
    doc = projects.get_project(project["id"])["doc"]
    asset = {"kind": "video", "name": "", "src": None, "origin": None, "srcDur": 4, "width": 832, "height": 480, "fps": 16, "res": None, "generated": True, "quality": "draft", "role": None}
    doc["assets"] = [{**asset, "id": f"gen-{take['id']}", "resultId": take["id"]} for take in drafts]
    doc["clips"] = [{**clip, "assetId": f"gen-{take['id']}"} for clip, take in zip(doc["clips"], drafts)]
    if fps is not None:
        doc["fps"] = fps
    projects.save_project(project["id"], doc, projects.get_project(project["id"])["version"])
    return projects.get_project(project["id"])


def test_an_export_reads_the_finished_version_of_a_slower_take_at_the_film_s_frame_rate(core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])
    _tick()
    _settle_all(core, fps=25.0)
    version = renditions.get(rendition["id"])
    project = placed(project, drafts)

    read = renditions.shot_versions(project["id"], project["doc"], takes.list_takes(project["id"]))
    other = placed(project, drafts, fps=30)

    assert {shot: item["id"] for shot, item in read.items()} == {"s1": version["id"]}
    assert renditions.shot_versions(other["id"], other["doc"], takes.list_takes(other["id"])) == {}


def test_an_export_without_a_slower_take_reads_no_version(monkeypatch):
    def refuse(project_id):
        raise AssertionError("no version should be read")

    monkeypatch.setattr(renditions, "list_for_project", refuse)
    doc = {"fps": 25, "assets": [{"id": "gen-t", "resultId": "t"}], "clips": [{"id": "s1", "assetId": "gen-t"}]}

    assert renditions.shot_versions("p", doc, [{"id": "t", "status": "done", "fps": 25.0, "file_path": "a.mp4"}]) == {}


def test_the_final_pass_says_which_finals_are_slower_and_orders_their_versions(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    order = final_pass.Order(takes=[take["id"] for take in drafts], method="upscale", target="fhd1080", conform=True)
    owner = core.users["user-1"]

    evaluation = asyncio.run(final_pass.evaluate(owner, projects.get_project(project["id"]), order, drafts))
    created = asyncio.run(final_pass.start(owner, projects.get_project(project["id"]), evaluation))

    assert evaluation.payload["blocks"] == []
    assert evaluation.payload["cadence"] == {
        "fps": 25,
        "choice": "auto",
        "interpolator": "rife",
        "ready": {"rife": True, "rtx": False, "rtx_checked": True},
        "shots": ["s1", "s2"],
        "slowed": [],
        "near": [],
        "seconds": None,
    }
    assert [shot["conform"] for shot in evaluation.payload["shots"]] == [True, True]
    assert [[item["status"] for item in renditions.list_for_take(take["id"])] for take in created] == [["waiting"], ["waiting"]]


def test_a_final_pass_without_conform_orders_no_version(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    order = final_pass.Order(takes=[take["id"] for take in drafts], method="upscale", target="fhd1080")
    owner = core.users["user-1"]

    evaluation = asyncio.run(final_pass.evaluate(owner, projects.get_project(project["id"]), order, drafts))
    created = asyncio.run(final_pass.start(owner, projects.get_project(project["id"]), evaluation))

    assert evaluation.payload["cadence"]["shots"] == ["s1", "s2"]
    assert all(renditions.list_for_take(take["id"]) == [] for take in created)


def test_a_final_pass_asked_to_conform_without_an_interpolator_is_blocked(core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    order = final_pass.Order(takes=[take["id"] for take in drafts], method="upscale", target="fhd1080", conform=True)

    evaluation = asyncio.run(final_pass.evaluate(core.users["user-1"], projects.get_project(project["id"]), order, drafts))

    assert [block["code"] for block in evaluation.payload["blocks"]] == ["interpolator_missing"]


def test_the_final_pass_estimates_the_versions_from_the_interpolator_s_measures(core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    takes.add_calibration(presets.VIDEO_TOOLS, "b-local", "1872x1080", 4.0, 4000)
    order = final_pass.Order(takes=[take["id"] for take in drafts], method="upscale", target="fhd1080", conform=True)

    evaluation = asyncio.run(final_pass.evaluate(core.users["user-1"], projects.get_project(project["id"]), order, drafts))

    assert evaluation.payload["cadence"]["seconds"] == pytest.approx(8.0)


@pytest.mark.parametrize("conform, message", [("yes", "conform must be true or false."), (1, "conform must be true or false.")])
def test_a_final_pass_with_a_malformed_conform_is_refused(conform, message):
    with pytest.raises(final_pass.PassError) as caught:
        final_pass.parse_order({"takes": ["t"], "method": "upscale", "target": "fhd1080", "conform": conform})

    assert str(caught.value) == message


def test_the_routes_estimate_order_list_and_cancel_versions(client, core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    ids = [take["id"] for take in drafts]

    estimated = client.post(f"{BASE}/projects/{project['id']}/renditions/estimate", json={"takes": ids})
    ordered = client.post(f"{BASE}/projects/{project['id']}/renditions", json={"takes": ids})
    listed = client.get(f"{BASE}/projects/{project['id']}/renditions")
    cancelled = client.post(f"{BASE}/renditions/{ordered.json()['data']['renditions'][0]['id']}/cancel")

    assert estimated.status_code == 200
    assert estimated.json()["data"] == {
        "fps": 25,
        "choice": "auto",
        "interpolator": "rife",
        "ready": {"rife": True, "rtx": False, "rtx_checked": True},
        "takes": ids,
        "seconds": None,
    }
    assert ordered.status_code == 202
    assert [item["take_id"] for item in ordered.json()["data"]["renditions"]] == ids
    assert ordered.json()["data"]["refused"] == []
    assert [item["id"] for item in listed.json()["data"]["renditions"]] == [item["id"] for item in ordered.json()["data"]["renditions"]]
    assert cancelled.json()["data"]["rendition"]["status"] == "cancelled"


def test_the_routes_list_the_takes_that_cannot_have_a_version_and_refuse_a_malformed_body(client, core, make_project):
    core.use_wan()
    project, drafts = _drafts(core, make_project)
    url = f"{BASE}/projects/{project['id']}/renditions"

    refused = client.post(url, json={"takes": [drafts[0]["id"]]})
    malformed = client.post(url, json={"takes": [drafts[0]["id"]], "interpolator": "high"})
    empty = client.post(url, json={"takes": []})
    unknown = client.post(f"{BASE}/renditions/nope/cancel")

    assert refused.status_code == 202
    assert refused.json()["data"]["renditions"] == []
    assert [(item["take_id"], item["code"]) for item in refused.json()["data"]["refused"]] == [(drafts[0]["id"], "interpolator_missing")]
    assert malformed.status_code == 422
    assert empty.status_code == 422
    assert unknown.status_code == 404


def test_the_final_take_route_orders_the_version_when_asked(client, core, make_project):
    core.use_wan()
    core.use_video_tools()
    core.use_seedvr2()
    project, drafts = _drafts(core, make_project)
    url = f"{BASE}/projects/{project['id']}/takes/{drafts[0]['id']}/final"

    started = client.post(url, json={"method": "upscale", "target": "fhd1080", "conform": True})
    malformed = client.post(url, json={"method": "upscale", "target": "fhd1080", "conform": "yes"})

    assert started.status_code == 202
    assert [item["status"] for item in renditions.list_for_take(started.json()["data"]["take"]["id"])] == ["waiting"]
    assert malformed.status_code == 422


def test_deleting_a_project_cancels_its_versions_in_flight_and_deletes_them(client, core, make_project):
    core.use_wan()
    core.use_video_tools()
    project, drafts = _drafts(core, make_project)
    rendition = _order(core, project, drafts[0])
    _tick()
    generation_id = renditions.get(rendition["id"])["generation_id"]

    deleted = client.delete(f"{BASE}/projects/{project['id']}")

    assert deleted.status_code == 200
    assert renditions.list_for_project(project["id"]) == []
    assert ("user-1", generation_id) in core.cancelled
