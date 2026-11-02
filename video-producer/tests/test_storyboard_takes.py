import asyncio

import pytest

from backend import director, estimate, presets, takes, tracker
from backend.projects import DocError, validate_doc
from backend.tables import create_tables

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4, "firstFromPrevious": False}]
ORDER = {"shots": ["s1"], "quality": "draft", "variants": 2, "preset_id": presets.WAN}


def _generate(client, project_id, **order):
    response = client.post(f"{BASE}/projects/{project_id}/generate", json={**ORDER, **order})
    assert response.status_code == 202, response.text
    return response.json()["data"]["takes"]


def _finish(core, generation_id):
    core.complete(generation_id)
    asyncio.run(tracker.Tracker().tick())


def _label(client, project_id, take_id, label):
    return client.post(f"{BASE}/projects/{project_id}/takes/{take_id}/label", json={"label": label})


def _labels(project_id):
    return {take["id"]: take["label"] for take in takes.list_takes(project_id)}


@pytest.fixture
def project(core, make_project):
    core.use_wan()
    return make_project(clips=SHOTS)


@pytest.fixture
def finished(client, core, project):
    created = _generate(client, project["id"], variants=3)
    for take in created:
        _finish(core, take["generation_id"])
    return created


def _old_row(cursor, take_id, chosen, flag, quality="draft"):
    cursor.execute(
        "INSERT INTO video_producer_takes (id, project_id, shot_id, quality, kind, status, chosen, flag, label) "
        "VALUES (?, 'p-1', 's1', ?, 'render', 'done', ?, ?, NULL)",
        (take_id, quality, chosen, flag),
    )


def test_the_takes_stored_before_labels_are_labelled_from_their_former_marks(project_db):
    with project_db.get_cursor() as cursor:
        _old_row(cursor, "t-chosen", 1, None)
        _old_row(cursor, "t-chosen-kept", 1, "keep")
        _old_row(cursor, "t-kept", 0, "keep")
        _old_row(cursor, "t-rejected", 0, "reject")
        _old_row(cursor, "t-plain", 0, None)
        _old_row(cursor, "t-final-quality", 0, None, quality="final")

    create_tables()

    with project_db.get_cursor() as cursor:
        cursor.execute("SELECT id, label FROM video_producer_takes ORDER BY id")
        stored = {row["id"]: row["label"] for row in cursor.fetchall()}
    assert stored == {
        "t-chosen": "final",
        "t-chosen-kept": "final",
        "t-kept": "candidate",
        "t-rejected": "rejected",
        "t-plain": "draft",
        "t-final-quality": "draft",
    }


def test_the_migration_leaves_labelled_takes_alone_and_runs_once(project_db):
    with project_db.get_cursor() as cursor:
        _old_row(cursor, "t-1", 1, None)
        cursor.execute("UPDATE video_producer_takes SET label = 'rejected' WHERE id = 't-1'")
        _old_row(cursor, "t-2", 0, "keep")

    assert takes.migrate_labels() == 1
    assert takes.migrate_labels() == 0
    assert (takes.get_take("t-1")["label"], takes.get_take("t-2")["label"]) == ("rejected", "candidate")


def test_a_take_read_before_the_migration_shows_the_label_of_its_marks(project_db):
    with project_db.get_cursor() as cursor:
        _old_row(cursor, "t-1", 0, "reject")

    assert takes.get_take("t-1")["label"] == "rejected"


@pytest.mark.parametrize(
    ("fields", "label"),
    [({"chosen": True}, "final"), ({"flag": "reject"}, "rejected"), ({"quality": "final", "label": "rejected"}, "rejected")],
)
def test_a_take_created_with_former_marks_or_a_label_keeps_them(project_db, fields, label):
    take = takes.create_take({"project_id": "p-1", "shot_id": "s1", "quality": "draft", "kind": "render", **fields})

    assert take["label"] == label


@pytest.mark.parametrize(("quality", "label"), [("draft", "draft"), ("final", "candidate")])
def test_a_new_take_is_a_draft_and_a_final_quality_take_a_candidate(project_db, quality, label):
    take = takes.create_take({"project_id": "p-1", "shot_id": "s1", "quality": quality, "kind": "render"})

    assert (take["label"], take["chosen"], take["flag"]) == (label, False, "keep" if label == "candidate" else None)


def test_a_final_take_is_the_only_one_of_its_shot_and_the_previous_final_becomes_candidate(client, core, project, finished):
    first, second, third = finished
    (other,) = _generate(client, project["id"], shots=["s2"], variants=1)
    _finish(core, other["generation_id"])
    _label(client, project["id"], other["id"], "final")
    _label(client, project["id"], third["id"], "rejected")
    _label(client, project["id"], first["id"], "final")

    response = _label(client, project["id"], second["id"], "final")

    assert response.status_code == 200
    answered = response.json()["data"]["take"]
    assert (answered["label"], answered["chosen"], answered["flag"]) == ("final", True, None)
    assert _labels(project["id"]) == {first["id"]: "candidate", second["id"]: "final", third["id"]: "rejected", other["id"]: "final"}
    assert takes.get_take(first["id"])["chosen"] is False


@pytest.mark.parametrize(("label", "chosen", "flag"), [("draft", False, None), ("rejected", False, "reject"), ("candidate", False, "keep")])
def test_the_former_marks_follow_the_label(client, project, finished, label, chosen, flag):
    take = finished[0]
    _label(client, project["id"], take["id"], "final")

    answered = _label(client, project["id"], take["id"], label).json()["data"]["take"]

    assert (answered["label"], answered["chosen"], answered["flag"]) == (label, chosen, flag)


def test_only_a_finished_take_can_be_final_but_any_take_can_be_rejected(client, project):
    take = _generate(client, project["id"])[0]

    refused = _label(client, project["id"], take["id"], "final")
    rejected = _label(client, project["id"], take["id"], "rejected")

    assert (refused.status_code, refused.json()["detail"]["error"]) == (409, "take_not_done")
    assert (rejected.status_code, rejected.json()["data"]["take"]["label"]) == (200, "rejected")


@pytest.mark.parametrize("body", [{}, {"label": "keep"}, {"label": "Final"}, {"label": None}, []])
def test_a_label_must_be_one_of_the_four(client, project, finished, body):
    response = client.post(f"{BASE}/projects/{project['id']}/takes/{finished[0]['id']}/label", json=body)

    assert (response.status_code, response.json()["detail"]["error"]) == (422, "invalid_request")


def test_the_label_of_a_take_of_another_project_is_not_found(client, core, project, make_project, finished):
    second = make_project(clips=SHOTS)

    response = _label(client, second["id"], finished[0]["id"], "final")

    assert response.status_code == 404


def test_choose_is_kept_as_an_alias_of_the_final_label(client, project, finished):
    first, second, _ = finished
    client.post(f"{BASE}/projects/{project['id']}/takes/{first['id']}/choose", json={"chosen": True})
    client.post(f"{BASE}/projects/{project['id']}/takes/{second['id']}/choose", json={"chosen": True})

    unchosen_other = client.post(f"{BASE}/projects/{project['id']}/takes/{first['id']}/choose", json={"chosen": False})
    unchosen = client.post(f"{BASE}/projects/{project['id']}/takes/{second['id']}/choose", json={"chosen": False})

    assert unchosen_other.json()["data"]["take"]["label"] == "candidate"
    assert (unchosen.json()["data"]["take"]["label"], unchosen.json()["data"]["take"]["chosen"]) == ("candidate", False)


@pytest.mark.parametrize(
    ("start", "flag", "label"),
    [
        ("draft", "keep", "candidate"),
        ("draft", "reject", "rejected"),
        ("candidate", None, "draft"),
        ("rejected", None, "draft"),
        ("final", "keep", "final"),
        ("final", None, "final"),
        ("final", "reject", "rejected"),
    ],
)
def test_flag_is_kept_as_an_alias_of_the_labels(client, project, finished, start, flag, label):
    take = finished[0]
    _label(client, project["id"], take["id"], start)

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/flag", json={"flag": flag})

    assert response.json()["data"]["take"]["label"] == label


def test_a_final_by_upscale_is_born_candidate_and_keeps_the_revision_of_its_source(client, core, make_project):
    core.use_wan()
    core.use_seedvr2()
    project = make_project(clips=[{**SHOTS[0], "revision": 2}])
    take = _generate(client, project["id"], variants=1)[0]
    _finish(core, take["generation_id"])
    core.add_media({"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}, "generations/x/1.mp4", "VIDEO")

    response = client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/final", json={"method": "upscale", "target": "fhd1080"})

    final = response.json()["data"]["take"]
    assert (final["quality"], final["label"], final["shot_revision"]) == ("final", "candidate", 2)


def test_each_shot_gets_its_own_number_of_drafts(client, project):
    created = _generate(client, project["id"], shots=["s1", "s2"], variants=1, shot_variants={"s1": 3})

    assert [(take["shot_id"], take["variant"]) for take in created] == [("s1", "A"), ("s1", "B"), ("s1", "C"), ("s2", "A")]
    assert {take["label"] for take in created} == {"draft"}


def test_a_shot_count_for_a_shot_not_asked_for_is_ignored(client, project):
    created = _generate(client, project["id"], shots=["s2"], variants=2, shot_variants={"s1": 5})

    assert [(take["shot_id"], take["variant"]) for take in created] == [("s2", "A"), ("s2", "B")]


@pytest.mark.parametrize(
    "shot_variants", [{"s1": 0}, {"s1": 17}, {"s1": True}, {"s1": "2"}, {"": 2}, ["s1"], "s1"]
)
def test_a_malformed_shot_count_is_refused(client, project, shot_variants):
    response = client.post(f"{BASE}/projects/{project['id']}/generate", json={**ORDER, "shot_variants": shot_variants})

    assert (response.status_code, response.json()["detail"]["error"]) == (422, "invalid_request")


def test_the_estimate_counts_the_takes_of_each_shot(client, project):
    def needed(**order):
        response = client.post(f"{BASE}/projects/{project['id']}/estimate", json={**ORDER, **order})
        assert response.status_code == 200, response.text
        return response.json()["data"]["quota"]["needed_minutes"]

    alone = needed(shots=["s1"], variants=3) + needed(shots=["s2"], variants=1)

    assert needed(shots=["s1", "s2"], variants=1, shot_variants={"s1": 3}) == pytest.approx(alone)
    assert needed(shots=["s1", "s2"], variants=1, shot_variants={"s1": 3}) > needed(shots=["s1", "s2"], variants=1)


def test_an_order_without_shot_counts_gives_every_shot_the_same_count():
    order = estimate.parse_order({**ORDER, "shots": ["s1", "s2"], "variants": 4})

    assert (order.count("s1"), order.count("s2"), order.shot_variants) == (4, 4, {})


def test_a_take_records_the_revision_of_its_shot_and_a_retry_the_current_one(client, core, make_project):
    from backend import projects

    core.use_wan()
    project = make_project(clips=[{**SHOTS[0], "revision": 3}, SHOTS[1]])
    created = _generate(client, project["id"], shots=["s1", "s2"], variants=1)
    assert [take["shot_revision"] for take in created] == [3, 0]

    doc = {**project["doc"], "clips": [{**project["doc"]["clips"][0], "revision": 4}, project["doc"]["clips"][1]]}
    projects.save_project(project["id"], doc, project["version"])
    core.fail(created[0]["generation_id"])
    asyncio.run(tracker.Tracker().tick())
    retried = client.post(f"{BASE}/takes/{created[0]['id']}/retry").json()["data"]["take"]

    assert retried["shot_revision"] == 4


@pytest.mark.parametrize(("revision", "expected"), [(None, 0), (0, 0), (5, 5), (-1, 0), (True, 0), (2.5, 0)])
def test_the_revision_of_a_shot_is_a_positive_integer_or_zero(make_doc, revision, expected):
    clip = {**SHOTS[0], **({} if revision is None else {"revision": revision})}

    assert director.shot_revision(make_doc(clips=[clip]), "s1") == expected
    assert director.shot_revision(make_doc(clips=[clip]), "missing") == 0


def _images(core, count):
    assets, references = [], []
    for index in range(count):
        core.add_media({"kind": "library", "item_id": f"lib-{index}"}, f"uploads/{index}.png", "image")
        assets.append({"id": f"a{index}", "kind": "image", "origin": {"kind": "library", "itemId": f"lib-{index}"}})
        references.append({"id": f"r{index}", "assetId": f"a{index}", "scope": {"type": "global"}})
    return assets, references


def test_a_shot_leaves_out_the_global_references_it_excludes_before_the_limits(core, make_doc):
    assets, references = _images(core, 10)
    overrides = {"exclude": ["r0", "r3"]}
    doc = make_doc(clips=[{**SHOTS[0], "referenceOverrides": overrides}, SHOTS[1]], references=references, assets=assets)

    sent = director.reference_media(core.users["user-1"], doc, "s1")
    other = director.reference_media(core.users["user-1"], doc, "s2")

    assert [entry.value for entry in sent] == [f"uploads/{index}.png" for index in (1, 2, 4, 5, 6, 7, 8, 9)]
    assert [entry.rank for entry in sent] == list(range(1, 9))
    assert len(other) == 9 and other[0].value == "uploads/0.png"


def test_an_exclusion_never_drops_a_reference_of_the_shot_itself(core, make_doc):
    assets, references = _images(core, 2)
    references[1] = {**references[1], "scope": {"type": "shot", "shotId": "s1"}}
    doc = make_doc(clips=[{**SHOTS[0], "referenceOverrides": {"exclude": ["r0", "r1"]}}], references=references, assets=assets)

    sent = director.reference_media(core.users["user-1"], doc, "s1")

    assert [entry.value for entry in sent] == ["uploads/1.png"]


def test_ref2va_is_blocked_when_the_shot_excludes_its_only_reference(core, make_doc):
    core.use_h3()
    assets, references = _images(core, 1)
    doc = make_doc(clips=[{**SHOTS[0], "referenceOverrides": {"exclude": ["r0"]}}], references=references, assets=assets, direction={"mode": "Ref2VA"})

    plans = director.build_plans(core.users["user-1"], doc, ["s1"], presets.MINIMAX_H3, "draft")

    assert [block["code"] for block in plans.blocks] == ["no_references"]


@pytest.mark.parametrize("overrides", [None, {"exclude": "r0"}, {"other": []}])
def test_malformed_overrides_exclude_nothing(core, make_doc, overrides):
    assets, references = _images(core, 1)
    clip = {**SHOTS[0], **({} if overrides is None else {"referenceOverrides": overrides})}

    assert director.excluded_references(make_doc(clips=[clip], references=references, assets=assets), "s1") == set()


def test_the_shot_fields_of_the_storyboard_are_valid_and_optional(make_doc):
    validate_doc(make_doc(clips=[SHOTS[0]]))
    validate_doc(make_doc(clips=[{**SHOTS[0], "drafts": 8, "revision": 0, "referenceOverrides": {"exclude": ["r1", "r2"]}}]))
    validate_doc(make_doc(clips=[{**SHOTS[0], "drafts": 16, "referenceOverrides": {}}]))


@pytest.mark.parametrize(
    "change",
    [
        {"drafts": 0},
        {"drafts": 17},
        {"drafts": 2.5},
        {"drafts": "3"},
        {"revision": -1},
        {"revision": 1.5},
        {"referenceOverrides": {"exclude": ["r1", "r1"]}},
        {"referenceOverrides": {"exclude": [""]}},
        {"referenceOverrides": {"include": []}},
        {"referenceOverrides": None},
    ],
)
def test_malformed_shot_fields_are_refused(make_doc, change):
    with pytest.raises(DocError):
        validate_doc(make_doc(clips=[{**SHOTS[0], **change}]))
