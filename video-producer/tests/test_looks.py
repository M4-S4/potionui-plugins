import asyncio

import pytest
from PIL import Image

from backend import bible, estimate, generation, looks, presets, projects, takes, tracker
from backend.estimate import Order

from .test_chain_frame import FFMPEG, TAKE_FILE, _luma, library, video

BASE = "/api/plugins/video-producer"
RED = (200, 30, 30)
BLUE = (30, 40, 200)
GREEN = (30, 190, 40)
ASSET = {"kind": "video", "src": "/api/media/generations/g/1.mp4", "srcDur": 4.0, "generated": True, "quality": "draft"}


class Frames:
    def __init__(self, monkeypatch):
        self.takes = {}
        self.images = {}
        self.calls = []
        monkeypatch.setattr(looks, "_take_frames", self.take_frames)
        monkeypatch.setattr(looks, "_image_frames", self.image_frames)

    def _write(self, folder, name, color):
        path = folder / f"{name}.png"
        Image.new("RGB", (16, 9), color).save(path)
        return path

    async def take_frames(self, owner, take, folder):
        self.calls.append(take["id"])
        return [(at, self._write(folder, f"t{index}", color)) for index, (at, color) in enumerate(self.takes[take["id"]])]

    async def image_frames(self, owner, source, folder):
        self.calls.append(source["value"])
        return [(None, self._write(folder, "image", self.images[source["value"]]))]


@pytest.fixture
def frames(monkeypatch, export_storage):
    return Frames(monkeypatch)


def _run():
    return asyncio.run(looks.run_once())


def _done(project_id, shot_id, take_id=None, **fields):
    return takes.create_take(
        {"project_id": project_id, "shot_id": shot_id, "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": f"g-{shot_id}", "file_id": "f", "file_path": f"generations/x/{shot_id}.mp4", "duration_s": 4.0, **fields}
    )


def _placed(make_project, core, *, cast=False, src_in=0.0):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4, "srcIn": src_in}])
    first, second = _done(project["id"], "s1"), _done(project["id"], "s2")
    doc = projects.get_project(project["id"])["doc"]
    shape = {key: None for key in ("origin", "width", "height", "fps", "res", "role", "synth", "transcript", "character", "lipSync")}
    for clip, take in zip(doc["clips"], (first, second)):
        doc["assets"].append({**shape, **ASSET, "id": f"gen-{take['id']}", "name": take["id"], "resultId": take["id"]})
        clip.update({"assetId": f"gen-{take['id']}", "take": take["id"], "stage": "draft"})
    if cast:
        core.add_media({"kind": "library", "item_id": "it-marin"}, "uploads/marin.png")
        doc["assets"].append({**shape, "kind": "image", "src": "/api/media/uploads/marin.png", "srcDur": None, "generated": False, "quality": None, "resultId": None, "id": "marin", "name": "marin.png", "origin": {"kind": "library", "itemId": "it-marin"}})
        doc["references"].append({"id": "r-marin", "name": "Marin", "space": "identite", "type": "image", "assetId": "marin", "role": "Identité", "scope": None})
        doc["bible"] = {"characters": [{"id": "c-marin", "label": "Marin", "text": "", "props": "", "references": ["r-marin"]}, {"id": "c-lina", "label": "Lina", "text": "", "props": "", "references": []}], "places": []}
        doc["clips"][1]["cast"] = {"characters": ["c-marin", "c-lina"]}
    saved = projects.save_project(project["id"], doc, projects.get_project(project["id"])["version"])
    return saved, first, second


def _report(core, project, enqueue=False):
    return looks.report(core.users["user-1"], projects.get_project(project["id"]), enqueue=enqueue)


def test_a_take_is_looked_at_on_its_start_once_a_second_and_its_last_image():
    assert looks.sample_times(0.0) == [0.0]
    assert looks.sample_times(3.0) == [0.0, 1.0, 2.0, 3.0]
    assert looks.sample_times(4.2) == [0.0, 1.0, 2.0, 3.0, 4.0, 4.2]
    assert looks.sample_times(4.03) == [0.0, 1.0, 2.0, 3.0, 4.03]
    long = looks.sample_times(30.0)
    assert len(long) == looks.MAX_SAMPLES and long[0] == 0.0 and long[-1] == 30.0


def test_a_vector_is_kept_as_half_floats_close_enough_for_a_cosine():
    vector = [0.6, -0.8, 0.0001, 0.0]
    back = looks.unpack(looks.pack(vector))

    assert len(back) == 4 and max(abs(a - b) for a, b in zip(vector, back)) < 1e-3
    assert abs(looks.cosine(vector, back) - 1.0) < 1e-3


def test_a_finished_take_asks_for_its_look_which_the_tracker_computes_when_nothing_runs(core, make_project, frames):
    core.use_wan()
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 4}])
    user = core.users["user-1"]
    order = Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.WAN)
    (take,) = asyncio.run(generation.start(user, project, asyncio.run(estimate.evaluate(user, user, project["doc"], order))))
    frames.takes[take["id"]] = [(0.0, RED), (4.0, BLUE)]

    assert looks.rows([looks.take_key(take["id"])]) == {}
    core.complete(take["generation_id"])
    asyncio.run(tracker.Tracker().tick())

    row = looks.rows([looks.take_key(take["id"])])[looks.take_key(take["id"])]
    assert (row["status"], row["model"], row["kind"]) == ("done", "local-google-siglip-base-patch16-224", "take")
    assert [frame[0] for frame in row["frames"]] == [0.0, 4.0]
    assert [frame[2] for frame in row["frames"]] == [None, None]
    assert [frame[3] for frame in row["frames"]] == [None, None]
    assert frames.calls == [take["id"]]


def test_no_look_is_computed_while_a_generation_runs_here_or_anywhere(core, make_project, frames):
    project, first, _ = _placed(make_project, core)
    frames.takes[first["id"]] = [(0.0, RED)]
    looks.queue_take(first)
    core.busy = True

    assert _run() is False
    core.busy = False
    takes.create_take({"project_id": project["id"], "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "queued"})
    assert _run() is False
    assert frames.calls == []
    assert looks.rows([looks.take_key(first["id"])])[looks.take_key(first["id"])]["status"] == "queued"


def test_without_the_weights_every_queued_look_is_unavailable_until_asked_again(core, make_project, frames):
    project, first, second = _placed(make_project, core)
    frames.takes.update({first["id"]: [(0.0, RED)], second["id"]: [(0.0, RED)]})
    looks.queue_take(first)
    looks.queue_take(second)
    core.embedder["available"] = False

    assert _run() is False
    found = looks.rows([looks.take_key(first["id"]), looks.take_key(second["id"])])
    assert {row["status"] for row in found.values()} == {"unavailable"}
    assert _report(core, project)["embedder"] == {"model": "google/siglip-base-patch16-224", "available": False}

    core.embedder["available"] = True
    report = _report(core, project, enqueue=True)
    assert report["queued"] == 2 and report["missing"] == 0
    assert _run() is True and _run() is True
    assert _report(core, project)["queued"] == 0


@pytest.mark.parametrize(("end", "start", "low"), [(RED, RED, False), (RED, BLUE, True)])
def test_a_seam_compares_the_end_of_the_cut_before_with_the_start_of_the_cut_after(core, make_project, frames, end, start, low):
    project, first, second = _placed(make_project, core, src_in=1.0)
    frames.takes[first["id"]] = [(0.0, GREEN), (2.0, GREEN), (4.0, end)]
    frames.takes[second["id"]] = [(0.0, GREEN), (1.0, start), (4.0, GREEN)]

    before = _report(core, project)
    assert before["seams"] == [{"shot_id": "s2", "previous_id": "s1", "from_take": first["id"], "to_take": second["id"], "score": None, "status": "missing"}]
    assert before["missing"] == 2

    _report(core, project, enqueue=True)
    while _run():
        pass
    (seam,) = _report(core, project)["seams"]

    assert seam["status"] == "done"
    assert (seam["score"] < looks.SEAM_LOW) is low
    assert _report(core, project)["thresholds"] == {"seam": looks.SEAM_LOW, "cast": looks.CAST_LOW, "face": looks.FACE_LOW, "place": looks.PLACE_LOW, "final": looks.FINAL_LOW, "drift": looks.DRIFT_LOW, "push_in": looks.PUSH_IN_HIGH}


def test_a_take_is_scored_against_the_pictures_of_each_bible_card_of_its_shot_s_cast(core, make_project, frames):
    project, first, second = _placed(make_project, core, cast=True)
    frames.takes[first["id"]] = [(0.0, GREEN)]
    frames.takes[second["id"]] = [(0.0, BLUE), (4.0, RED)]
    frames.images["uploads/marin.png"] = RED
    looks.queue_take(second)

    assert _run() is True
    queued = looks.rows([looks.image_key("uploads/marin.png")])[looks.image_key("uploads/marin.png")]
    assert (queued["status"], queued["kind"], queued["source"]["ref"]) == ("queued", "image", {"kind": "library", "item_id": "it-marin"})
    assert _run() is True

    take = next(item for item in _report(core, project)["takes"] if item["take_id"] == second["id"])
    marin, lina = take["cards"]
    assert (marin["card_id"], marin["label"], marin["status"]) == ("c-marin", "Marin", "done")
    assert marin["score"] > 0.99
    assert (lina["status"], lina["score"]) == ("no_images", None)


class Painted(Frames):
    async def take_frames(self, owner, take, folder):
        self.calls.append(take["id"])
        found = []
        for index, (at, color, face) in enumerate(self.takes[take["id"]]):
            path = folder / f"t{index}.png"
            image = Image.new("RGB", (64, 36), color)
            if face is not None:
                image.paste(face, (20, 8, 36, 24))
            image.save(path)
            found.append((at, path))
        return found

    async def image_frames(self, owner, source, folder):
        self.calls.append(source["value"])
        color, face = self.images[source["value"]]
        path = folder / "image.png"
        image = Image.new("RGB", (64, 36), color)
        if face is not None:
            image.paste(face, (20, 8, 36, 24))
        image.save(path)
        return [(None, path)]


@pytest.fixture
def painted(monkeypatch, export_storage):
    return Painted(monkeypatch)


FACE = {"x": 20.0, "y": 8.0, "width": 32.0, "height": 32.0, "score": 0.9}


def _with_faces(core, colors):
    core.faces["available"] = True
    for color in colors:
        core.face_boxes[color] = [FACE]


def test_with_the_face_detector_a_take_and_a_card_are_compared_on_their_cropped_faces_by_the_median_of_the_images_that_show_one(core, make_project, painted):
    project, _, second = _placed(make_project, core, cast=True)
    painted.takes[second["id"]] = [(0.0, BLUE, RED), (1.0, BLUE, RED), (2.0, BLUE, GREEN), (3.0, GREEN, None)]
    painted.images["uploads/marin.png"] = (BLUE, RED)
    _with_faces(core, [BLUE])

    report = _report(core, project, enqueue=True)
    while _run():
        pass
    report = _report(core, project)

    row = looks.rows([looks.take_key(second["id"])])[looks.take_key(second["id"])]
    assert row["model"] == "local-google-siglip-base-patch16-224+faces"
    assert [frame[2] is not None for frame in row["frames"]] == [True, True, True, False]
    marin = next(card for card in next(item for item in report["takes"] if item["take_id"] == second["id"])["cards"] if card["card_id"] == "c-marin")
    assert (marin["kind"], marin["method"], marin["seen"], marin["status"]) == ("character", "face", 0.75, "done")
    assert marin["score"] > 0.99
    assert report["faces"] == {"model": "face_detection_yunet_2023mar.onnx", "available": True}


def test_a_face_too_small_to_read_counts_as_none(core, make_project, painted):
    project, _, second = _placed(make_project, core, cast=True)
    painted.takes[second["id"]] = [(0.0, BLUE, RED), (4.0, BLUE, RED)]
    painted.images["uploads/marin.png"] = (BLUE, RED)
    core.faces["available"] = True
    core.face_boxes[BLUE] = [{**FACE, "height": looks.MIN_FACE - 1.0}]

    _report(core, project, enqueue=True)
    while _run():
        pass
    marin = _report(core, project)["takes"][1]["cards"][0]

    assert (marin["method"], marin["seen"]) == ("whole", 0.0)


def test_a_take_without_a_face_falls_back_on_the_whole_image_and_says_none_was_seen(core, make_project, painted):
    project, _, second = _placed(make_project, core, cast=True)
    painted.takes[second["id"]] = [(0.0, RED, None), (4.0, BLUE, None)]
    painted.images["uploads/marin.png"] = (RED, None)
    core.faces["available"] = True

    _report(core, project, enqueue=True)
    while _run():
        pass
    marin = _report(core, project)["takes"][1]["cards"][0]

    assert (marin["method"], marin["seen"]) == ("whole", 0.0)
    assert marin["score"] > 0.99


def test_a_take_keeps_the_height_of_the_face_it_follows_and_says_how_many_times_it_grows(core, make_project, painted):
    project, _, second = _placed(make_project, core, cast=True)
    painted.takes[second["id"]] = [(0.0, BLUE, RED), (1.0, GREEN, RED), (2.0, RED, None), (3.0, GREEN, RED)]
    painted.images["uploads/marin.png"] = (GREEN, RED)
    core.faces["available"] = True
    core.face_boxes[BLUE] = [{**FACE, "height": 16.0}]
    core.face_boxes[GREEN] = [{**FACE, "height": 40.0}, {**FACE, "height": 60.0, "score": 0.6}]

    _report(core, project, enqueue=True)
    while _run():
        pass
    report = _report(core, project)

    row = looks.rows([looks.take_key(second["id"])])[looks.take_key(second["id"])]
    assert [frame[3] for frame in row["frames"]] == [16.0, 40.0, None, 40.0]
    assert [frame[2] is not None for frame in row["frames"]] == [False, True, False, True]
    assert next(item for item in report["takes"] if item["take_id"] == second["id"])["push_in"] == 2.5
    assert report["thresholds"]["push_in"] == looks.PUSH_IN_HIGH


def test_with_two_people_the_push_in_follows_the_face_of_the_first_image_and_not_the_best_face_of_each(core, make_project, painted):
    project, first, second = _placed(make_project, core)
    painted.takes[first["id"]] = [(0.0, RED, None)]
    painted.takes[second["id"]] = [(0.0, BLUE, None), (1.0, GREEN, None), (2.0, RED, None), (3.0, GREEN, None)]
    core.faces["available"] = True
    marin = {"x": 2.0, "y": 4.0, "width": 10.0, "height": 10.0, "score": 0.9}
    lina = {"x": 40.0, "y": 4.0, "width": 20.0, "height": 20.0, "score": 0.8}
    core.face_boxes[BLUE] = [marin, lina]
    core.face_boxes[GREEN] = [{**lina, "x": 38.0, "y": 2.0, "width": 24.0, "height": 24.0, "score": 0.95}, {**marin, "x": 1.0, "y": 3.0, "width": 12.0, "height": 12.0, "score": 0.7}]
    core.face_boxes[RED] = [{**lina, "x": 38.0, "y": 2.0, "width": 24.0, "height": 24.0}]

    _report(core, project, enqueue=True)
    while _run():
        pass

    row = looks.rows([looks.take_key(second["id"])])[looks.take_key(second["id"])]
    assert [frame[3] for frame in row["frames"]] == [10.0, 12.0, None, 12.0]
    assert next(item for item in _report(core, project)["takes"] if item["take_id"] == second["id"])["push_in"] == 1.2
    assert looks.overlap(marin, lina) == 0.0
    assert looks.overlap(marin, {**marin, "x": 7.0}) == 0.5
    assert looks.follow(None, [lina, marin]) is lina
    assert looks.follow(marin, [lina]) is None
    assert looks.follow(marin, []) is None


def test_a_take_says_no_push_in_under_two_images_with_a_face_or_without_its_look(core, make_project, painted):
    project, first, second = _placed(make_project, core, cast=True)
    painted.takes[first["id"]] = [(0.0, BLUE, RED), (4.0, RED, None)]
    painted.takes[second["id"]] = [(0.0, RED, None)]
    painted.images["uploads/marin.png"] = (BLUE, RED)
    _with_faces(core, [BLUE])

    assert all(item["push_in"] is None for item in _report(core, project, enqueue=True)["takes"])
    while _run():
        pass

    assert [item["push_in"] for item in _report(core, project)["takes"]] == [None, None]


def test_a_take_measured_with_faces_before_the_heights_were_kept_is_measured_again(core, make_project, frames):
    project, first, second = _placed(make_project, core)
    core.faces["available"] = True
    model = "local-google-siglip-base-patch16-224+faces"
    for take in (first, second):
        looks.queue_take(take)
    looks._mark(looks.take_key(first["id"]), "done", model=model, frames=[[0.0, looks.pack([1.0, 0.0]), None]])
    looks._mark(looks.take_key(second["id"]), "done", model=model, frames=[[0.0, looks.pack([1.0, 0.0]), None, None]])

    before = {item["take_id"]: item["status"] for item in _report(core, project)["takes"]}
    after = {item["take_id"]: item["status"] for item in _report(core, project, enqueue=True)["takes"]}

    assert before == {first["id"]: "done", second["id"]: "done"}
    assert after == {first["id"]: "queued", second["id"]: "done"}


GRAY = (128, 128, 128)
DARK = (10, 10, 10)
FRONT = {"x": 18.0, "y": 6.0, "width": 20.0, "height": 32.0, "score": 0.93, "landmarks": [[22.0, 12.0], [34.0, 12.0], [28.0, 16.0], [24.0, 20.0], [32.0, 20.0]]}
PROFILE = {**FRONT, "landmarks": [[22.0, 12.0], [34.0, 12.0], [35.0, 16.0], [24.0, 20.0], [32.0, 20.0]]}


def _with_identity(core):
    core.faces["available"] = True
    core.identity["available"] = True
    core.face_boxes[GRAY] = [FRONT]
    core.face_boxes[DARK] = [PROFILE]
    core.identities.update({RED: [1.0, 0.0], GREEN: [0.6, 0.8], BLUE: [0.0, 1.0]})


def test_a_look_is_measured_under_the_faces_and_the_face_recognition_it_had():
    info = {"slug": "local-siglip"}

    assert looks.measure_key(info, {"available": False}, {"available": True}) == "local-siglip"
    assert looks.measure_key(info, {"available": True}) == "local-siglip+faces"
    assert looks.measure_key(info, {"available": True}, {"available": False}) == "local-siglip+faces"
    assert looks.measure_key(info, {"available": True}, {"available": True}) == "local-siglip+faces+identity"


def test_a_face_counts_as_seen_from_the_front_with_a_sure_detection_its_nose_between_its_eyes_and_its_eyes_apart():
    assert looks.frontal(FRONT) is True
    assert looks.frontal(PROFILE) is False
    assert looks.frontal({**FRONT, "score": 0.8}) is False
    assert looks.frontal({**FRONT, "width": 40.0}) is False
    assert looks.frontal({**FRONT, "landmarks": []}) is False


def test_with_the_face_recognition_a_take_says_how_much_of_its_first_frontal_face_is_left_and_when(core, make_project, painted):
    project, _, second = _placed(make_project, core)
    painted.takes[second["id"]] = [(0.0, GRAY, RED), (1.0, GRAY, GREEN), (2.0, DARK, BLUE), (3.0, GRAY, BLUE)]
    _with_identity(core)

    _report(core, project, enqueue=True)
    while _run():
        pass
    report = _report(core, project)

    row = looks.rows([looks.take_key(second["id"])])[looks.take_key(second["id"])]
    assert row["model"] == "local-google-siglip-base-patch16-224+faces+identity"
    assert [frame[4] is not None for frame in row["frames"]] == [True, True, False, True]
    assert next(item for item in report["takes"] if item["take_id"] == second["id"])["identity"] == {"score": 0.0, "at": 3.0}
    assert report["identity"] == {"model": "glintr100.onnx", "available": True}
    assert report["thresholds"]["identity"] == looks.IDENTITY_LOW


@pytest.mark.parametrize("chained, expected", [(True, 0.6), (False, None)])
def test_a_chained_seam_compares_the_last_face_of_the_first_take_with_the_first_face_of_the_second(core, make_project, painted, chained, expected):
    project, first, second = _placed(make_project, core)
    stored = projects.get_project(project["id"])
    doc = stored["doc"]
    doc["clips"][1]["firstFromPrevious"] = chained
    projects.save_project(project["id"], doc, stored["version"])
    painted.takes[first["id"]] = [(0.0, GRAY, BLUE), (4.0, GRAY, RED)]
    painted.takes[second["id"]] = [(0.0, GRAY, GREEN), (4.0, GRAY, BLUE)]
    _with_identity(core)

    _report(core, project, enqueue=True)
    while _run():
        pass
    (seam,) = _report(core, project)["seams"]

    assert seam["identity"] == expected


def test_a_look_measured_before_the_face_recognition_counts_as_missing_once_it_is_here(core, make_project, painted):
    project, first, _ = _placed(make_project, core)
    painted.takes[first["id"]] = [(0.0, GRAY, RED)]
    core.faces["available"] = True
    core.face_boxes[GRAY] = [FRONT]
    looks.queue_take(first)
    assert _run() is True
    assert next(item for item in _report(core, project)["takes"] if item["take_id"] == first["id"])["status"] == "done"

    core.identity["available"] = True

    assert next(item for item in _report(core, project)["takes"] if item["take_id"] == first["id"])["status"] == "missing"


def test_a_look_measured_before_the_face_detector_counts_as_missing_once_it_is_here(core, make_project, frames):
    project, first, _ = _placed(make_project, core)
    frames.takes[first["id"]] = [(0.0, RED)]
    looks.queue_take(first)
    assert _run() is True

    core.faces["available"] = True
    report = _report(core, project)

    assert next(item for item in report["takes"] if item["take_id"] == first["id"])["status"] == "missing"


def test_the_place_cast_in_a_shot_is_scored_on_the_whole_image_by_the_median_of_its_images(core, make_project, frames):
    project, _, second = _placed(make_project, core, cast=True)
    stored = projects.get_project(project["id"])
    doc = stored["doc"]
    core.add_media({"kind": "library", "item_id": "it-quay"}, "uploads/quay.png")
    doc["assets"].append({**doc["assets"][-1], "id": "quay", "name": "quay.png", "origin": {"kind": "library", "itemId": "it-quay"}})
    doc["references"].append({"id": "r-quay", "name": "Quay", "space": "decors3d", "type": "Décor", "assetId": "quay", "role": "Décor", "scope": None})
    doc["bible"]["places"] = [{"id": "p-quay", "label": "Quay", "text": "", "references": ["r-quay"]}]
    doc["clips"][1]["cast"] = {"characters": ["c-marin"], "place": "p-quay"}
    projects.save_project(project["id"], doc, stored["version"])
    frames.takes[second["id"]] = [(0.0, BLUE), (1.0, BLUE), (2.0, RED)]
    frames.images["uploads/marin.png"] = RED
    frames.images["uploads/quay.png"] = BLUE

    _report(core, project, enqueue=True)
    while _run():
        pass
    cards = {card["card_id"]: card for card in _report(core, project)["takes"][1]["cards"]}

    assert (cards["p-quay"]["kind"], cards["p-quay"]["method"], cards["p-quay"]["seen"]) == ("place", "whole", None)
    assert cards["p-quay"]["score"] > 0.99
    assert cards["c-marin"]["score"] > 0.99


def test_a_final_take_is_compared_with_the_draft_it_comes_from_image_by_image(core, make_project, frames):
    project, first, _ = _placed(make_project, core)
    final = _done(project["id"], "s1", quality="final", parent_take_id=first["id"], file_path="generations/x/s1-final.mp4")
    frames.takes[first["id"]] = [(0.0, RED), (2.0, BLUE)]
    frames.takes[final["id"]] = [(0.0, RED), (1.0, RED), (2.0, GREEN)]

    _report(core, project, enqueue=True)
    while _run():
        pass
    (found,) = _report(core, project)["finals"]

    assert (found["take_id"], found["parent_id"], found["shot_id"], found["status"], found["face"]) == (final["id"], first["id"], "s1", "done", None)
    assert found["score"] > 0.99


def test_the_takes_of_one_character_are_compared_from_shot_to_shot_once_three_show_its_face(core, make_project, painted):
    project = make_project(clips=[{"id": f"s{n}", "start": 4 * (n - 1), "dur": 4} for n in (1, 2, 3)])
    placed = [_done(project["id"], f"s{n}") for n in (1, 2, 3)]
    doc = projects.get_project(project["id"])["doc"]
    shape = {key: None for key in ("origin", "width", "height", "fps", "res", "role", "synth", "transcript", "character", "lipSync")}
    for clip, take in zip(doc["clips"], placed):
        doc["assets"].append({**shape, **ASSET, "id": f"gen-{take['id']}", "name": take["id"], "resultId": take["id"]})
        clip.update({"assetId": f"gen-{take['id']}", "take": take["id"], "stage": "draft", "cast": {"characters": ["c-marin"]}})
    doc["bible"] = {"characters": [{"id": "c-marin", "label": "Marin", "text": "", "props": "", "references": []}], "places": []}
    projects.save_project(project["id"], doc, projects.get_project(project["id"])["version"])
    painted.takes.update({placed[0]["id"]: [(0.0, BLUE, RED)], placed[1]["id"]: [(0.0, BLUE, RED)], placed[2]["id"]: [(0.0, BLUE, GREEN)]})
    _with_faces(core, [BLUE])

    _report(core, project, enqueue=True)
    while _run():
        pass
    drift = {item["shot_id"]: item for item in _report(core, project)["drift"]}

    assert set(drift) == {"s1", "s2", "s3"}
    assert drift["s3"]["score"] < drift["s1"]["score"] == drift["s2"]["score"]
    assert drift["s3"]["take_id"] == placed[2]["id"] and drift["s3"]["card_id"] == "c-marin"


def test_the_last_frame_a_chained_shot_starts_from_is_scored_against_the_cards_of_that_shot(core, make_project, frames):
    project, first, second = _placed(make_project, core, cast=True)
    stored = projects.get_project(project["id"])
    doc = stored["doc"]
    doc["clips"][1]["cast"] = {"characters": ["c-marin"]}
    projects.save_project(project["id"], doc, stored["version"])
    frames.takes[first["id"]] = [(0.0, RED), (4.0, BLUE)]
    frames.takes[second["id"]] = [(0.0, RED)]
    frames.images["uploads/marin.png"] = RED

    _report(core, project, enqueue=True)
    while _run():
        pass
    (chain,) = _report(core, project)["chains"]

    assert (chain["shot_id"], chain["previous_id"], chain["from_take"]) == ("s2", "s1", first["id"])
    (marin,) = chain["cards"]
    assert (marin["card_id"], marin["status"], marin["method"]) == ("c-marin", "done", "whole")
    assert marin["score"] < looks.CAST_LOW

    stored = projects.get_project(project["id"])
    doc = stored["doc"]
    doc["clips"][1]["firstFromPrevious"] = False
    projects.save_project(project["id"], doc, stored["version"])
    assert _report(core, project)["chains"] == []


def test_a_card_picture_from_the_history_counts_though_the_core_stores_its_type_in_capitals(core):
    ref = {"kind": "history", "generation_id": "g-marin", "file_id": "0"}
    core.add_media(ref, "generations/2026-10-27/g-marin/0.png", "IMAGE")
    doc = {
        "assets": [{"id": "marin", "kind": "image", "origin": {"kind": "history", "generationId": "g-marin", "fileId": "0"}}],
        "references": [{"id": "r-marin", "assetId": "marin"}],
        "bible": {"characters": [{"id": "c-marin", "label": "Marin", "references": ["r-marin"]}], "places": []},
    }
    card = bible.cards(doc, "characters")[0]

    assert looks._card_images(core.users["user-1"], doc, card) == [("c-marin", ref, "generations/2026-10-27/g-marin/0.png")]


def test_a_look_of_another_model_counts_as_missing(core, make_project, frames):
    project, first, _ = _placed(make_project, core)
    frames.takes[first["id"]] = [(0.0, RED)]
    looks.queue_take(first)
    _run()
    core.embedder["slug"] = "local-other-model"

    take = next(item for item in _report(core, project)["takes"] if item["take_id"] == first["id"])
    assert take["status"] == "missing"


def test_a_failed_look_says_why_and_can_be_asked_again(core, make_project, frames, monkeypatch):
    project, first, _ = _placed(make_project, core)

    async def broken(owner, take, folder):
        raise looks.chain.ChainError("no_media", "The video of the take is no longer available.")

    monkeypatch.setattr(looks, "_take_frames", broken)
    looks.queue_take(first)
    _run()

    row = looks.rows([looks.take_key(first["id"])])[looks.take_key(first["id"])]
    assert (row["status"], row["error"]) == ("failed", "The video of the take is no longer available.")
    assert _report(core, project, enqueue=True)["queued"] >= 1


def test_deleting_a_take_or_its_project_drops_their_looks(core, make_project, frames):
    project, first, second = _placed(make_project, core)
    frames.takes.update({first["id"]: [(0.0, RED)], second["id"]: [(0.0, RED)]})
    looks.queue_take(first)
    looks.queue_take(second)

    takes.delete_take(first["id"])
    assert list(looks.rows([looks.take_key(first["id"]), looks.take_key(second["id"])])) == [looks.take_key(second["id"])]
    projects.delete_project(project["id"])
    assert looks.rows([looks.take_key(second["id"])]) == {}


def test_a_start_image_candidate_asks_for_its_look_and_is_reported_with_its_cast_cards(core, make_project, frames):
    project, _, second = _placed(make_project, core, cast=True)
    candidate = _done(project["id"], "s2", kind=takes.KEYFRAME, file_path="generations/x/k.png")
    frames.takes[candidate["id"]] = [(0.0, RED)]
    frames.images["uploads/marin.png"] = RED

    looks.queue_take(candidate)
    assert _run() is True
    assert _run() is True
    report = _report(core, project)

    row = looks.rows([looks.take_key(candidate["id"])])[looks.take_key(candidate["id"])]
    assert (row["status"], row["kind"]) == ("done", "take")
    assert [item["take_id"] for item in report["takes"]] == [report["takes"][0]["take_id"], second["id"]]
    (found,) = report["candidates"]
    assert (found["take_id"], found["shot_id"], found["status"]) == (candidate["id"], "s2", "done")
    marin, lina = found["cards"]
    assert (marin["card_id"], marin["status"]) == ("c-marin", "done") and marin["score"] > 0.99
    assert lina["status"] == "no_images"


def test_a_start_image_candidate_is_looked_at_once_as_the_image_it_is(core, make_project, tmp_path, monkeypatch):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 4}])
    candidate = _done(project["id"], "s1", kind=takes.KEYFRAME, file_path="generations/x/k.png")
    image = tmp_path / "k.png"
    Image.new("RGB", (16, 9), RED).save(image)
    monkeypatch.setattr(looks.media.Resolver, "local", lambda self, kind, value, folder: image)

    picked = asyncio.run(looks._take_frames(core.users["user-1"], candidate, tmp_path))

    assert picked == [(0.0, image)]


def test_the_routes_report_and_ask_for_the_looks_of_the_caller_s_project(client, core, make_project, frames, app, make_user):
    project, first, second = _placed(make_project, core)

    read = client.get(f"{BASE}/projects/{project['id']}/looks")
    asked = client.post(f"{BASE}/projects/{project['id']}/looks")

    assert read.status_code == 200 and read.json()["data"]["missing"] == 2
    assert asked.status_code == 200 and asked.json()["data"]["queued"] == 2
    other = make_project(user_id="user-2", clips=[{"id": "s1", "start": 0, "dur": 4}])
    assert client.get(f"{BASE}/projects/{other['id']}/looks").status_code == 404


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_the_images_of_a_take_are_cut_from_its_file_at_the_sample_times(core, make_project, library, video, tmp_path):
    project = make_project(clips=[{"id": "s1", "start": 0, "dur": 3}])
    take = takes.create_take(
        {"project_id": project["id"], "shot_id": "s1", "user_id": "user-1", "quality": "draft", "kind": "render", "status": "done", "generation_id": "g-1", "file_id": "f-1", "file_path": TAKE_FILE, "duration_s": 3.0}
    )
    library.files[("history", TAKE_FILE)] = video
    folder = tmp_path / "work"
    folder.mkdir()

    picked = asyncio.run(looks._take_frames(core.users["user-1"], take, folder))

    assert [at for at, _ in picked] == [0.0, 1.0, 2.0, 3.0]
    lumas = [_luma(path.read_bytes()) for _, path in picked]
    assert lumas == sorted(lumas) and lumas[-1] - lumas[0] > 100
