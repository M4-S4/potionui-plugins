import asyncio

from backend import estimate, framefit, presets
from backend.estimate import Order

from .test_frame_crop import _disc, _frame, _project, _ref_key, pictures


def _losses(core, project):
    user = core.users["user-1"]
    order = Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.MINIMAX_H3_12GB)
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    return [warning["data"]["loss"] for warning in evaluation.payload["warnings"] if warning["code"].startswith("frame_cropped")]


def test_an_estimate_reads_a_picture_once_and_reads_it_again_when_its_file_changes(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    path = pictures.files[_ref_key({"kind": "library", "item_id": "lib-square"})]
    read = framefit.picture
    reads = []
    monkeypatch.setattr(framefit, "picture", lambda found: reads.append(found) or read(found))

    assert [_losses(core, project), _losses(core, project)] == [[42], [42]]
    assert reads == [path]

    _disc((1024, 768)).save(path)

    assert _losses(core, project) == [23]
    assert reads == [path, path]


def test_the_pictures_known_are_bounded_and_the_oldest_is_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr(framefit, "SEEN_LIMIT", 1)
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    _disc((64, 48)).save(first)
    _disc((48, 64)).save(second)
    read = framefit.picture
    reads = []
    monkeypatch.setattr(framefit, "picture", lambda found: reads.append(found.name) or read(found))

    sizes = [framefit.known_picture(path)[:2] for path in (first, first, second, first)]

    assert sizes == [(64, 48), (64, 48), (48, 64), (64, 48)]
    assert reads == ["first.png", "second.png", "first.png"]


def test_a_picture_that_could_not_be_read_once_is_read_again_by_the_next_estimate(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    opened = framefit.Image.open
    failures = [OSError("busy")]

    def flaky(*args, **kwargs):
        if failures:
            raise failures.pop()
        return opened(*args, **kwargs)

    monkeypatch.setattr(framefit.Image, "open", flaky)

    assert [_losses(core, project), _losses(core, project)] == [[], [42]]
