import asyncio

import pytest

from backend import presets, takes, tracker
from src.plugin_api import get_current_active_user

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}]
ORDER = {"shots": ["s1"], "quality": "draft", "variants": 2, "preset_id": presets.WAN}


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _generate(client, project_id, **order):
    response = client.post(f"{BASE}/projects/{project_id}/generate", json={**ORDER, **order})
    assert response.status_code == 202, response.text
    return response.json()["data"]["takes"]


def _finish(core, generation_id):
    core.complete(generation_id)
    asyncio.run(tracker.Tracker().tick())


@pytest.fixture
def project(core, make_project):
    core.use_wan()
    return make_project(clips=SHOTS)


def test_the_takes_of_a_project_are_listed_oldest_first_in_the_contract_shape(client, core, project):
    created = _generate(client, project["id"])

    response = client.get(f"{BASE}/projects/{project['id']}/takes")

    assert response.status_code == 200
    listed = response.json()["data"]["takes"]
    assert [take["id"] for take in listed] == [take["id"] for take in created]
    assert set(listed[0]) == set(takes.PUBLIC)
    assert "request" not in listed[0] and "user_id" not in listed[0]


def test_the_takes_of_another_users_project_are_not_found(client, core, make_project):
    core.use_wan()
    other = make_project(user_id="user-2", clips=SHOTS)

    response = client.get(f"{BASE}/projects/{other['id']}/takes")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "project_not_found"


def test_choosing_a_take_unchooses_the_other_takes_of_its_shot(client, core, project):
    first, second = _generate(client, project["id"])
    for take in (first, second):
        _finish(core, take["generation_id"])
    (other,) = _generate(client, project["id"], shots=["s2"], variants=1)
    _finish(core, other["generation_id"])
    client.post(f"{BASE}/projects/{project['id']}/takes/{other['id']}/choose", json={"chosen": True})
    client.post(f"{BASE}/projects/{project['id']}/takes/{first['id']}/choose", json={"chosen": True})

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{second['id']}/choose", json={"chosen": True})

    assert response.status_code == 200
    assert response.json()["data"]["take"]["chosen"] is True
    assert [(take["id"], take["chosen"]) for take in takes.list_takes(project["id"])] == [
        (first["id"], False),
        (second["id"], True),
        (other["id"], True),
    ]
    response = client.post(f"{BASE}/projects/{project['id']}/takes/{second['id']}/choose", json={"chosen": False})
    assert response.json()["data"]["take"]["chosen"] is False


def test_only_a_finished_take_can_be_chosen(client, core, project):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/choose", json={"chosen": True})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "take_not_done"


@pytest.mark.parametrize("body", [{}, {"chosen": "yes"}, {"chosen": None}, [True]])
def test_choose_needs_a_boolean(client, core, project, body):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/choose", json=body)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"


@pytest.mark.parametrize("flag", ["keep", "reject", None])
def test_a_take_can_be_flagged_or_unflagged(client, core, project, flag):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/flag", json={"flag": flag})

    assert response.status_code == 200
    assert response.json()["data"]["take"]["flag"] == flag


@pytest.mark.parametrize("body", [{}, {"flag": "favori"}, {"flag": 1}])
def test_a_flag_must_be_keep_reject_or_null(client, core, project, body):
    take = _generate(client, project["id"])[0]

    assert client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/flag", json=body).status_code == 422


def test_a_take_of_another_project_is_not_found(client, core, project, make_project):
    take = _generate(client, project["id"])[0]
    second = make_project(clips=SHOTS)

    response = client.post(f"{BASE}/projects/{second['id']}/takes/{take['id']}/flag", json={"flag": "keep"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "take_not_found"


def test_deleting_an_in_flight_take_cancels_and_refunds_it_but_keeps_the_generation(client, core, project):
    take = _generate(client, project["id"])[0]

    response = client.delete(f"{BASE}/projects/{project['id']}/takes/{take['id']}")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"deleted": take["id"]}}
    assert takes.get_take(take["id"]) is None
    assert core.cancelled == [("user-1", take["generation_id"])]
    assert core.refunded == [f"video-producer:{take['id']}"]
    assert take["generation_id"] in core.states


def test_a_final_by_upscale_answers_202_with_the_new_take(client, core, project):
    core.use_seedvr2()
    take = _generate(client, project["id"])[0]
    _finish(core, take["generation_id"])
    core.add_media({"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}, "generations/x/1.mp4", "VIDEO")

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "uhd2160"})

    assert response.status_code == 202
    final = response.json()["data"]["take"]
    assert (final["quality"], final["kind"], final["parent_take_id"], final["mode"]) == ("final", "upscale", take["id"], "video_upscale")
    assert core.scheduled


@pytest.mark.parametrize(
    "body",
    [{"method": "remix", "target": "fhd1080"}, {"method": "upscale", "target": "8k"}, {"method": "render"}, {"method": "upscale", "target": "fhd1080", "rtx_source": "raw"}, None],
)
def test_a_final_needs_a_known_method_and_target(client, core, project, body):
    take = _generate(client, project["id"])[0]

    assert client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json=body).status_code == 422


def test_a_blocked_final_answers_409_with_its_blocks(client, core, project):
    take = _generate(client, project["id"])[0]
    _finish(core, take["generation_id"])

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "fhd1080"})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "blocked"
    assert [block["code"] for block in detail["data"]["blocks"]] == ["no_preset"]


def test_a_final_of_an_unfinished_take_answers_409(client, core, project):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "render", "target": "fhd1080"})

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "take_not_done"


def test_cancel_cancels_a_take_and_refunds_it(client, core, project):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/takes/{take['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["data"]["take"]["status"] == "cancelled"
    assert core.refunded == [f"video-producer:{take['id']}"]


def test_retry_answers_202_with_a_new_take(client, core, project):
    take = _generate(client, project["id"])[0]
    core.fail(take["generation_id"])
    asyncio.run(tracker.Tracker().tick())

    response = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert response.status_code == 202
    retried = response.json()["data"]["take"]
    assert retried["id"] != take["id"] and retried["seed"] == take["seed"]


def test_retrying_a_take_in_flight_answers_409(client, core, project):
    take = _generate(client, project["id"])[0]

    response = client.post(f"{BASE}/takes/{take['id']}/retry")

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "take_not_retryable"


@pytest.mark.parametrize("action", ["cancel", "retry"])
def test_another_users_take_is_not_found(app, client, core, project, action):
    take = _generate(client, project["id"])[0]
    _as(app, core.users["user-2"])

    response = client.post(f"{BASE}/takes/{take['id']}/{action}")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "take_not_found"


def test_an_unknown_take_is_not_found(client, core):
    assert client.post(f"{BASE}/takes/nope/cancel").status_code == 404


def test_an_admin_cancels_the_take_of_a_user_as_its_owner(app, client, core, project):
    take = _generate(client, project["id"])[0]
    _as(app, core.users["admin-1"])

    response = client.post(f"{BASE}/takes/{take['id']}/cancel")

    assert response.status_code == 200
    assert core.cancelled == [("user-1", take["generation_id"])]


def test_deleting_a_project_cancels_and_refunds_its_takes_in_flight_first(client, core, project, store):
    store[("max_parallel_jobs", None)] = "1"
    submitted, waiting = _generate(client, project["id"])

    response = client.delete(f"{BASE}/projects/{project['id']}")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"deleted": project["id"]}}
    assert (submitted["generation_id"], waiting["generation_id"]) == ("gen-1", None)
    assert core.cancelled == [("user-1", "gen-1")]
    assert sorted(core.refunded) == sorted(f"video-producer:{take['id']}" for take in (submitted, waiting))
    assert takes.get_take(submitted["id"]) is None and takes.get_take(waiting["id"]) is None
    assert takes.list_jobs(submitted["id"]) == []
    assert client.get(f"{BASE}/projects/{project['id']}").status_code == 404


def test_an_admin_deleting_a_users_project_cancels_its_takes_as_the_owner(app, client, core, project):
    (take,) = _generate(client, project["id"], variants=1)
    _as(app, core.users["admin-1"])

    assert client.delete(f"{BASE}/projects/{project['id']}").status_code == 200

    assert core.cancelled == [("user-1", take["generation_id"])]


def test_deleting_a_project_leaves_its_finished_takes_alone_until_they_go(client, core, project):
    (take,) = _generate(client, project["id"], variants=1)
    _finish(core, take["generation_id"])
    refunded = list(core.refunded)

    assert client.delete(f"{BASE}/projects/{project['id']}").status_code == 200

    assert core.cancelled == [] and core.refunded == refunded
    assert takes.get_take(take["id"]) is None


H3_VARIANTS = [(presets.MINIMAX_H3_FAST, "MiniMax-H3-Fast"), (presets.MINIMAX_H3_VDN, "MiniMax-H3 VDN (experimental)")]


def _variant_take(client, core, project, preset_id, name):
    core.use_h3_variant(preset_id, name)
    (take,) = _generate(client, project["id"], variants=1, preset_id=preset_id)
    _finish(core, take["generation_id"])
    core.add_media({"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}, "generations/x/1.mp4", "VIDEO")
    return take


@pytest.mark.parametrize("preset_id, name", H3_VARIANTS)
def test_an_h3_variant_without_upscale_mode_is_upscaled_by_seedvr2(client, core, project, preset_id, name):
    core.use_seedvr2()
    take = _variant_take(client, core, project, preset_id, name)

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "fhd1080"})

    assert response.status_code == 202
    final = response.json()["data"]["take"]
    assert (final["preset_id"], final["mode"], final["kind"], final["parent_take_id"]) == (presets.SEEDVR2, "video_upscale", "upscale", take["id"])
    assert core.submitted[-1][1]["form_data"]["resolution_target"] == "fhd1080"


@pytest.mark.parametrize("preset_id, name", H3_VARIANTS)
def test_an_h3_variant_without_upscale_mode_nor_seedvr2_refuses_a_final_by_upscale(client, core, project, preset_id, name):
    take = _variant_take(client, core, project, preset_id, name)

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "fhd1080"})

    assert response.status_code == 409
    assert response.json()["detail"]["data"]["blocks"] == [
        {
            "code": "upscale_unsupported",
            "message": f"{name} has no Upscale mode: install SeedVR2 for final takes, or render the take again at full resolution.",
            "data": {"preset_id": preset_id},
        }
    ]
    assert len(takes.list_takes(project["id"])) == 1
    rendered = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "render", "target": "fhd1080"})
    assert rendered.status_code == 202 and rendered.json()["data"]["take"]["preset_id"] == preset_id


def test_the_base_h3_preset_upscales_its_own_takes_even_with_seedvr2(client, core, project):
    core.use_h3()
    core.use_seedvr2()
    (take,) = _generate(client, project["id"], variants=1, preset_id=presets.MINIMAX_H3)
    _finish(core, take["generation_id"])
    core.add_media({"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}, "generations/x/1.mp4", "VIDEO")

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "fhd1080"})

    assert response.status_code == 202
    assert (response.json()["data"]["take"]["preset_id"], response.json()["data"]["take"]["mode"]) == (presets.MINIMAX_H3, "upscale")
