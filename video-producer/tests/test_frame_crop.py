import asyncio
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from backend import core_bridge, director, estimate, formats, framefit, frame_grab, generation, presets, takes, tracker
from backend.core_bridge import MediaRefError
from backend.estimate import Order

RED = (205, 35, 35)
TEAL = (0, 140, 150)
SHOT = {"id": "s1", "start": 0, "dur": 4, "label": "Opening"}
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}]
PROMPTS = [{"id": "p1", "shotId": "s1", "text": "A slow push-in."}, {"id": "p2", "shotId": "s2", "text": "The wind rises."}]


def _ref_key(ref):
    return tuple(sorted(ref.items()))


def _disc(size, color=RED):
    width, height = size
    image = Image.new("RGB", size, (244, 244, 238))
    draw = ImageDraw.Draw(image)
    radius = min(width, height) * 0.25
    draw.ellipse([width / 2 - radius, height / 2 - radius, width / 2 + radius, height / 2 + radius], fill=color)
    side = round(min(width, height) * 0.1)
    draw.rectangle([0, 0, side - 1, side - 1], fill=(40, 170, 60))
    return image


def _disc_ratio(path, color=RED):
    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)
    mask = (np.abs(pixels - np.array(color)) <= 45).all(axis=-1)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    return (cols.max() - cols.min() + 1) / (rows.max() - rows.min() + 1)


class Pictures:
    def __init__(self, core, folder):
        self.core = core
        self.folder = folder
        self.files = {}
        self.stored = []
        self.error = None

    def add(self, asset_id, size, color=RED, kind="library", suffix=".png"):
        if kind == "library":
            ref = {"kind": "library", "item_id": f"lib-{asset_id}"}
            value = f"uploads/{asset_id}{suffix}"
            origin = {"kind": "library", "itemId": f"lib-{asset_id}"}
        else:
            ref = {"kind": "history", "generation_id": f"g-{asset_id}", "file_id": "1"}
            value = f"generations/g-{asset_id}/1.png"
            origin = {"kind": "history", "generationId": f"g-{asset_id}", "fileId": "1"}
        path = self.folder / f"{asset_id}{suffix}"
        _disc(size, color).save(path)
        self.core.add_media(ref, value, "image")
        self.files[_ref_key(ref)] = path
        return {"id": asset_id, "kind": "image", "name": f"{asset_id}{suffix}", "origin": origin, "width": size[0], "height": size[1]}

    def path(self, user, ref):
        found = self.files.get(_ref_key(ref))
        return str(found) if found is not None else None

    def stored_path(self, value):
        return self.folder / f"{Path(value).name}"

    async def save(self, user, path):
        if self.error is not None:
            raise self.error
        number = len(self.stored) + 1
        value = f"uploads/stored-{number}-{Path(path).name}"
        ref = {"kind": "library", "item_id": f"stored-{number}"}
        copy = self.stored_path(value)
        shutil.copy(path, copy)
        self.stored.append((value, Path(path).name))
        self.core.add_media(ref, value, "image")
        self.files[_ref_key(ref)] = copy
        with Image.open(copy) as image:
            width, height = image.size
        return {"value": value, "media_type": "image", "original_filename": Path(path).name, "origin": None, "ref": ref, "width": width, "height": height}

    def forget(self, value):
        self.core.media = {key: item for key, item in self.core.media.items() if item["value"] != value}


@pytest.fixture
def pictures(core, monkeypatch, tmp_path, export_storage):
    folder = tmp_path / "pictures"
    folder.mkdir()
    found = Pictures(core, folder)
    monkeypatch.setattr(core_bridge, "media_file_path", found.path)
    monkeypatch.setattr(core_bridge, "local_media_file", lambda user, ref, target: None)
    monkeypatch.setattr(core_bridge, "save_user_media", found.save)
    return found


def _frame(frame_id, asset_id, role, time=0, shot_id="s1"):
    return {"id": frame_id, "shotId": shot_id, "time": time, "assetId": asset_id, "role": role}


def _start(core, project, preset_id, shots=("s1",), **fields):
    user = core.users["user-1"]
    order = Order(**{"shots": list(shots), "quality": "draft", "variants": 1, "preset_id": preset_id, **fields})
    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], order))
    return asyncio.run(generation.start(user, project, evaluation))


def _tick():
    return asyncio.run(tracker.Tracker().tick())


def _paths(request):
    return [(entry["role"], entry["media"]["path"]) for entry in request["form_data"]["video_director"]["media"]]


def _project(make_doc, make_project, assets, frames, clips=(SHOT,), **parts):
    doc = make_doc(clips=list(clips), prompts=PROMPTS, frames=frames, assets=assets, **parts)
    return make_project(doc=doc)


@pytest.mark.parametrize(
    "value, ratio",
    [
        ("832x480", (26, 15)),
        ("1344x768", (7, 4)),
        ("480x832", (15, 26)),
        ("640x640", (1, 1)),
        ("16:9", (16, 9)),
        ("2.39:1", (239, 100)),
        ("720p", None),
        (None, None),
    ],
)
def test_the_ratio_of_a_size_or_a_format_is_two_whole_numbers_without_a_common_divisor(value, ratio):
    assert framefit.ratio_of(value) == ratio


def test_the_ratio_of_a_take_is_its_size_else_the_aspect_ratio_its_request_or_its_cloud_parameters_send():
    assert framefit.request_ratio("960x544", {"form_data": {"aspect_ratio": "9:16"}}) == (30, 17)
    assert framefit.request_ratio("720p", {"form_data": {"aspect_ratio": "9:16"}}, "16:9") == (9, 16)
    assert framefit.request_ratio("720p", {"form_data": {}}, "4:3") == (4, 3)
    assert framefit.request_ratio("720p", {"form_data": {}}) is None


def test_the_tolerance_is_the_share_the_film_crops_without_a_word():
    assert framefit.TOLERANCE == formats.EXACT_LOSS == formats.load_table()["framing"]["exact"] == 0.03
    assert "tolerance" not in formats.load_table()["startImages"]


@pytest.mark.parametrize(
    "size, ratio, box",
    [
        ((1024, 1024), (26, 15), (0, 217, 1024, 590)),
        ((768, 1152), (26, 15), (0, 354, 768, 444)),
        ((1280, 720), (26, 15), None),
        ((1024, 576), (26, 15), None),
        ((1280, 720), (9, 16), (438, 0, 404, 720)),
        ((1023, 767), (1, 1), (128, 0, 766, 766)),
        ((768, 1152), (1, 1), (0, 192, 768, 768)),
        ((1280, 720), (16, 9), None),
        ((1344, 768), (26, 15), None),
        ((832, 480), (26, 15), None),
        ((1, 1), (16, 9), None),
        ((31, 31), (26, 15), None),
        ((3, 1000), (16, 9), None),
        ((400, 400), (26, 15), (0, 85, 400, 230)),
    ],
)
def test_the_crop_keeps_the_centre_in_the_ratio_with_even_sides_and_leaves_a_picture_within_the_tolerance(size, ratio, box):
    found = framefit.crop_box(*size, ratio)

    assert found == box
    if found is not None:
        left, top, width, height = found
        assert width % 2 == 0 and height % 2 == 0
        assert width <= size[0] and height <= size[1]
        assert abs(width / height - ratio[0] / ratio[1]) / (ratio[0] / ratio[1]) < 0.005
        assert (left, top) == ((size[0] - width) // 2, (size[1] - height) // 2)


def test_the_crop_file_is_the_centre_at_the_resolution_of_the_picture_and_its_disc_stays_round(tmp_path):
    source = tmp_path / "square.png"
    _disc((1024, 1024)).save(source)

    output = framefit.crop_file(source, framefit.crop_box(1024, 1024, (26, 15)), tmp_path, "square.jpg")

    assert output.name == "square-crop-1024x590.png"
    with Image.open(output) as image:
        assert image.size == (1024, 590) and image.format == "PNG"
        assert image.getpixel((5, 5)) == (244, 244, 238)
    assert _disc_ratio(output) == pytest.approx(1.0, abs=0.01)


def test_a_cmyk_picture_is_cropped_to_an_rgb_picture(tmp_path):
    source = tmp_path / "print.jpg"
    _disc((600, 600)).convert("CMYK").save(source)

    output = framefit.crop_file(source, framefit.crop_box(600, 600, (16, 9)), tmp_path, "print.jpg")

    with Image.open(output) as image:
        assert image.mode == "RGB" and image.size == (600, 338) and image.format == "JPEG"


def test_a_picture_is_cropped_and_stored_once_for_a_ratio_and_found_again(core, pictures):
    asset = pictures.add("square", (1024, 1024))
    user = core.users["user-1"]
    ref = {"kind": "library", "item_id": "lib-square"}

    first = asyncio.run(framefit.fit(user, "uploads/square.png", ref, (26, 15), asset["name"]))
    again = asyncio.run(framefit.fit(user, "uploads/square.png", ref, (26, 15), asset["name"]))
    other = asyncio.run(framefit.fit(user, "uploads/square.png", ref, (9, 16), asset["name"]))

    assert first == again
    assert (first.width, first.height, first.value) == (1024, 590, "uploads/stored-1-square-crop-1024x590.png")
    assert (other.width, other.height) == (576, 1024)
    assert [name for _, name in pictures.stored] == ["square-crop-1024x590.png", "square-crop-576x1024.png"]
    assert _disc_ratio(pictures.stored_path(first.value)) == pytest.approx(1.0, abs=0.01)


def test_a_stored_crop_the_library_lost_is_made_again(core, pictures):
    pictures.add("square", (1024, 1024))
    user = core.users["user-1"]
    ref = {"kind": "library", "item_id": "lib-square"}
    first = asyncio.run(framefit.fit(user, "uploads/square.png", ref, (26, 15), "square.png"))
    pictures.forget(first.value)

    again = asyncio.run(framefit.fit(user, "uploads/square.png", ref, (26, 15), "square.png"))

    assert again.value != first.value and len(pictures.stored) == 2
    assert framefit.recorded(user.id, "uploads/square.png", (26, 15)).fitted == again


def test_the_crops_of_one_user_are_not_the_crops_of_another(core, pictures):
    pictures.add("square", (1024, 1024))
    ref = {"kind": "library", "item_id": "lib-square"}

    asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", ref, (26, 15), "square.png"))
    asyncio.run(framefit.fit(core.users["user-2"], "uploads/square.png", ref, (26, 15), "square.png"))

    assert len(pictures.stored) == 2


def test_a_picture_within_the_tolerance_is_not_stored(core, pictures):
    pictures.add("wide", (1344, 768))

    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/wide.png", {"kind": "library", "item_id": "lib-wide"}, (26, 15), "wide.png"))

    assert found is None and pictures.stored == []


def test_a_picture_whose_file_cannot_be_read_here_is_left_as_it_is(core, pictures):
    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/gone.png", {"kind": "library", "item_id": "lib-gone"}, (26, 15), "gone.png"))

    assert found is None and pictures.stored == []


def test_a_crop_the_library_refuses_raises_a_crop_error(core, pictures):
    pictures.add("square", (1024, 1024))
    pictures.error = MediaRefError("upload_rejected", "The library is full.")

    with pytest.raises(framefit.CropError) as raised:
        asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", {"kind": "library", "item_id": "lib-square"}, (26, 15), "square.png"))

    assert (raised.value.code, raised.value.cause) == ("frame_not_cropped", "failed")
    assert raised.value.message == "is sent as it is: it could not be cropped to the frame of the take."


def test_a_minimax_h3_take_starts_from_its_first_image_cropped_to_the_ratio_of_the_take(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    (_, request) = core.submitted[0]
    assert request["form_data"]["resolution"] == "832x480"
    assert _paths(request) == [("first", "uploads/stored-1-square-crop-1024x590.png")]
    assert request["form_data"]["video_director"]["media"][0]["media"]["relative_path"] == "uploads/stored-1-square-crop-1024x590.png"
    assert take["request"] == request


def test_a_minimax_h3_fast_take_starts_from_its_first_image_cropped(core, make_doc, make_project, pictures):
    core.use_h3_fast_12gb_continue()
    project = _project(make_doc, make_project, [pictures.add("portrait", (768, 1152))], [_frame("f1", "portrait", "first")])

    _start(core, project, presets.MINIMAX_H3_FAST_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/stored-1-portrait-crop-768x444.png")]


def test_a_first_and_last_image_take_crops_both_images_the_same_way(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    assets = [pictures.add("square", (1024, 1024)), pictures.add("portrait", (768, 1152), TEAL)]
    project = _project(make_doc, make_project, assets, [_frame("f1", "square", "first"), _frame("f2", "portrait", "last", 4)])

    _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [
        ("first", "uploads/stored-1-square-crop-1024x590.png"),
        ("last", "uploads/stored-2-portrait-crop-768x444.png"),
    ]
    assert _disc_ratio(pictures.stored_path("uploads/stored-2-portrait-crop-768x444.png"), TEAL) == pytest.approx(1.0, abs=0.01)


def test_a_shot_that_keeps_its_framing_crops_its_one_image_once_for_both_ends(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    clip = {**SHOT, "keepFraming": True}
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")], clips=(clip,))

    _start(core, project, presets.MINIMAX_H3_12GB)

    cropped = "uploads/stored-1-square-crop-1024x590.png"
    assert _paths(core.submitted[0][1]) == [("first", cropped), ("last", cropped)]
    assert len(pictures.stored) == 1


def test_the_director_document_of_a_mixed_shot_carries_the_cropped_image(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    core.add_media({"kind": "library", "item_id": "lib-sound"}, "uploads/sound.wav", "audio")
    sound = {"id": "sound", "kind": "audio", "name": "sound.wav", "origin": {"kind": "library", "itemId": "lib-sound"}, "srcDur": 8.0}
    references = [{"id": "r-sound", "assetId": "sound", "scope": {"type": "shot", "shotId": "s1"}}]
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024)), sound], [_frame("f1", "square", "first")], references=references)
    (plan,) = director.build_plans(core.users["user-1"], project["doc"], ["s1"], presets.MINIMAX_H3_12GB, "draft").shots

    asyncio.run(generation.with_frames(core.users["user-1"], project, [plan]))

    document = plan.request["form_data"]["video_director"]
    assert document["mode"] == "director" and plan.audio.behavior == "mux"
    assert _paths(plan.request) == [("first", "uploads/stored-1-square-crop-1024x590.png")]


def test_a_wan_take_starts_from_its_first_image_cropped(core, make_doc, make_project, pictures):
    core.use_wan()
    project = _project(make_doc, make_project, [pictures.add("landscape", (1280, 720))], [_frame("f1", "landscape", "first")], aspect="9:16")

    _start(core, project, presets.WAN)

    (_, request) = core.submitted[0]
    assert request["form_data"]["resolution"] == "480x832"
    assert _paths(request) == [("first", "uploads/stored-1-landscape-crop-416x720.png")]


def test_a_start_image_kept_from_the_candidates_is_cropped_like_any_other(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    candidate = {**pictures.add("candidate", (1024, 1024), kind="history"), "generated": True}
    project = _project(make_doc, make_project, [candidate], [_frame("f1", "candidate", "first")])

    _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/stored-1-candidate-crop-1024x590.png")]


def test_a_cloud_take_starts_from_its_first_image_cropped_to_the_aspect_ratio_it_sends(core, make_doc, make_project, pictures):
    core.use_openrouter()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    _start(core, project, presets.OPENROUTER_VIDEO, model_id="cm-veo")

    (_, request) = core.submitted[0]
    assert request["form_data"]["aspect_ratio"] == "16:9"
    assert _paths(request) == [("first", "uploads/stored-1-square-crop-1024x576.png")]


def test_an_image_in_the_ratio_of_the_take_is_sent_as_it_is(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("exact", (832, 480))], [_frame("f1", "exact", "first")])

    _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/exact.png")]
    assert pictures.stored == []


def test_a_retry_reuses_the_crop_its_first_take_stored(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)
    core.fail("gen-1")
    _tick()

    asyncio.run(generation.retry(core.users["user-1"], project, takes.get_take(take["id"])))

    assert _paths(core.submitted[-1][1]) == [("first", "uploads/stored-1-square-crop-1024x590.png")]
    assert len(pictures.stored) == 1


def _not_cropped(cause, message, roles=("first",), chained=False, image="start image of the shot"):
    return {"code": "frame_not_cropped", "message": f"The {image} {message}", "data": {"shot_id": "s1", "cause": cause, "roles": list(roles), "chained": chained}}


def test_a_crop_that_cannot_be_stored_sends_the_image_as_it_is_and_says_why_on_the_take(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    pictures.error = MediaRefError("upload_rejected", "The library is full.")

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/square.png")]
    assert take["frame_notes"] == [_not_cropped("failed", "is sent as it is: it could not be cropped to the frame of the take.")]
    assert takes.public(take)["frame_notes"] == take["frame_notes"]


class Frames:
    def __init__(self, monkeypatch, pictures, size):
        self.pictures = pictures
        self.size = size
        monkeypatch.setattr(frame_grab, "cut_frame", self.cut)

    async def cut(self, owner, project_id, clip, asset):
        end = frame_grab.end_of(clip)
        name = f"{asset['id']}-frame-{frame_grab.num(end)}s"
        self.pictures.add(name, self.size)
        value = f"uploads/{name}.png"
        return {"value": value, "filename": f"{name}.png", "ref": {"kind": "library", "item_id": f"lib-{name}"}, "width": self.size[0], "height": self.size[1], "source": {"shotId": clip["id"], "takeId": asset.get("resultId"), "assetId": asset["id"], "at": end}}


def test_the_last_image_of_a_previous_shot_in_another_ratio_is_cropped_before_the_chained_take_starts(core, make_doc, make_project, pictures, monkeypatch, store):
    store[("max_parallel_jobs", None)] = "4"
    core.use_wan()
    Frames(monkeypatch, pictures, (768, 1152))
    project = make_project(doc=make_doc(clips=SHOTS, prompts=PROMPTS))
    first, second = _start(core, project, presets.WAN, shots=("s1", "s2"))
    _tick()
    core.complete(first["generation_id"])

    _tick()

    taken = takes.get_take(second["id"])
    (_, request) = core.submitted[1]
    assert _paths(request) == [("first", "uploads/stored-1-gen-" + first["id"] + "-frame-4s-crop-768x444.png")]
    assert taken["chain"]["frame"]["origin"] == {"kind": "library", "itemId": f"lib-gen-{first['id']}-frame-4s"}
    assert taken["request"] == request


def _done(core, take):
    core.complete(take["generation_id"])
    ref = {"kind": "history", "generation_id": take["generation_id"], "file_id": f"file-{take['generation_id']}"}
    core.add_media(ref, f"generations/x/{take['generation_id']}.mp4", "VIDEO")
    _tick()
    done = takes.get_take(take["id"])
    assert done["status"] == "done"
    return done


def _cropped_square(request):
    ratio = framefit.ratio_of(request["form_data"]["resolution"])
    box = framefit.crop_box(1024, 1024, ratio)
    return f"square-crop-{box[2]}x{box[3]}.png"


def test_a_final_render_of_a_take_starts_from_its_first_image_cropped_to_the_ratio_of_the_final(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)
    done = _done(core, take)

    asyncio.run(generation.final(core.users["user-1"], project, done, "render", "hd720"))

    (_, request) = core.submitted[-1]
    ((role, path),) = _paths(request)
    assert role == "first" and path.startswith("uploads/stored-") and path.endswith(_cropped_square(request))


def test_a_final_pass_render_starts_from_the_first_image_cropped_to_the_ratio_of_the_final(core, make_doc, make_project, pictures):
    from backend import final_pass

    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)
    done = _done(core, take)
    user = core.users["user-1"]
    evaluation = asyncio.run(final_pass.evaluate(user, project, final_pass.Order(takes=[done["id"]], method="render", target="hd720"), [done]))

    asyncio.run(final_pass.start(user, project, evaluation))

    (_, request) = core.submitted[-1]
    ((role, path),) = _paths(request)
    assert role == "first" and path.startswith("uploads/stored-") and path.endswith(_cropped_square(request))


def test_a_guided_final_starts_from_the_first_frame_of_its_draft_cropped_to_the_ratio_of_the_final(core, make_doc, make_project, pictures, monkeypatch):
    from types import SimpleNamespace

    core.use_ltx25()
    core.use_wan()
    project = make_project(doc=make_doc(clips=[SHOT], prompts=PROMPTS))
    (take,) = _start(core, project, presets.WAN)
    done = _done(core, take)

    async def extract_frame(user, ref, at="last"):
        pictures.add("draft-first", (832, 480))
        return {"value": "uploads/draft-first.png", "media_type": "image", "original_filename": "draft-first.png", "ref": {"kind": "library", "item_id": "lib-draft-first"}}

    monkeypatch.setattr(core_bridge, "extract_frame", extract_frame)
    monkeypatch.setattr(core_bridge, "local_media_file", lambda user, ref, folder: Path(f"/storage/{ref['generation_id']}.mp4") if ref.get("kind") == "history" else None)
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: SimpleNamespace(has_audio=False))

    asyncio.run(generation.final(core.users["user-1"], project, done, "guided", "hd720"))

    (_, request) = core.submitted[-1]
    assert request["form_data"]["resolution"] == "1280x704"
    assert _paths(request) == [("first", "uploads/stored-1-Opening-first-frame-crop-832x458.png")]
    assert _disc_ratio(pictures.stored_path("uploads/stored-1-Opening-first-frame-crop-832x458.png")) == pytest.approx(1.0, abs=0.02)


def test_a_photo_in_jpeg_is_cropped_to_a_jpeg_of_quality_95_and_any_other_picture_to_a_png(tmp_path):
    photo = tmp_path / "photo.jpg"
    _disc((1024, 1024)).save(photo, quality=90)
    drawing = tmp_path / "drawing.webp"
    _disc((1024, 1024)).save(drawing, lossless=True)

    cropped_photo = framefit.crop_file(photo, framefit.crop_box(1024, 1024, (26, 15)), tmp_path, "photo.jpg")
    cropped_drawing = framefit.crop_file(drawing, framefit.crop_box(1024, 1024, (26, 15)), tmp_path, "drawing.webp")

    assert (cropped_photo.name, cropped_drawing.name) == ("photo-crop-1024x590.jpg", "drawing-crop-1024x590.png")
    with Image.open(cropped_photo) as image:
        assert (image.format, image.size, image.mode) == ("JPEG", (1024, 590), "RGB")
        assert [layer[1:3] for layer in image.layer] == [(1, 1), (1, 1), (1, 1)]
    assert _disc_ratio(cropped_photo) == pytest.approx(1.0, abs=0.01)


def test_a_photo_crop_stored_in_the_library_keeps_the_jpeg_format(core, pictures):
    pictures.add("photo", (1024, 1024), suffix=".jpg")

    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/photo.jpg", {"kind": "library", "item_id": "lib-photo"}, (26, 15), "photo.jpg"))

    assert found.value == "uploads/stored-1-photo-crop-1024x590.jpg"


def test_a_picture_with_more_pixels_than_the_ceiling_follows_the_failure_rule(core, pictures, monkeypatch):
    pictures.add("huge", (1024, 1024))
    ref = {"kind": "library", "item_id": "lib-huge"}
    monkeypatch.setattr(framefit, "MAX_PIXELS", 1_000_000)

    with pytest.raises(framefit.CropError) as raised:
        asyncio.run(framefit.fit(core.users["user-1"], "uploads/huge.png", ref, (26, 15), "huge.png"))

    assert raised.value.cause == "too_many_pixels" and pictures.stored == []


def test_the_pixel_ceiling_lets_a_48_megapixel_phone_photo_through():
    assert framefit.MAX_PIXELS == 64_000_000 == formats.load_table()["startImages"]["maxPixels"]
    assert not framefit.too_large(8064, 6048) and not framefit.too_large(8160, 6144)
    assert framefit.too_large(14000, 14000)


def test_a_file_in_a_format_the_core_does_not_read_is_neither_measured_nor_cropped(core, pictures):
    pictures.add("print", (1024, 1024))
    path = pictures.files[_ref_key({"kind": "library", "item_id": "lib-print"})]
    _disc((1024, 1024)).save(path, format="TIFF")

    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/print.png", {"kind": "library", "item_id": "lib-print"}, (26, 15), "print.png"))

    assert framefit.picture_size(path) is None
    assert found is None and pictures.stored == []


@pytest.mark.parametrize(
    "name, cropped",
    [
        ("../../etc/passwd.png", "passwd-crop-640x360.png"),
        ("..\\..\\evil.png", "evil-crop-640x360.png"),
        ("a\x00b\x07c.png", "a-b-c-crop-640x360.png"),
        ("..", "image-crop-640x360.png"),
        ("", "image-crop-640x360.png"),
        ("Carre", "Carre-crop-640x360.png"),
        ("photo.final.jpg", "photo.final-crop-640x360.png"),
        ("x" * 300 + ".png", "x" * 80 + "-crop-640x360.png"),
    ],
)
def test_the_name_of_a_crop_is_a_plain_bounded_file_name(name, cropped):
    assert framefit.cropped_name(name, (0, 0, 640, 360)) == cropped


@pytest.mark.parametrize(
    "code, cause, message",
    [
        ("storage_quota_exceeded", "storage_full", "is sent as it is, not cropped to the frame of the take: the storage of the project's owner is full."),
        ("upload_file_size_exceeded", "upload_too_large", "is sent as it is, not cropped to the frame of the take: its crop is larger than the largest file the project's owner may upload."),
        ("daily_generations_exceeded", "failed", "is sent as it is: it could not be cropped to the frame of the take."),
    ],
)
def test_a_refused_crop_says_a_fixed_text_for_its_cause_and_nothing_of_the_core(core, pictures, code, cause, message):
    pictures.add("square", (1024, 1024))
    refusal = {"code": code, "message": "used 9.8 GB of /srv/storage", "kind": "storage", "label": "", "format": "", "used": 1, "limit": 1, "percent": 100, "resets_at": None}
    pictures.error = core_bridge.LimitExceeded([refusal], "upload", None)

    with pytest.raises(framefit.CropError) as raised:
        asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", {"kind": "library", "item_id": "lib-square"}, (26, 15), "square.png"))

    assert (raised.value.cause, raised.value.message) == (cause, message)


def test_a_work_folder_that_cannot_be_made_gives_the_general_cause_and_no_path(core, pictures, monkeypatch):
    from backend import workdir

    pictures.add("square", (1024, 1024))

    def scratch(name, owner_id):
        raise workdir.WorkdirError(Path("/secret/storage/video_producer/frames"), OSError(30, "Read-only file system"))

    monkeypatch.setattr(workdir, "scratch", scratch)

    with pytest.raises(framefit.CropError) as raised:
        asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", {"kind": "library", "item_id": "lib-square"}, (26, 15), "square.png"))

    assert raised.value.cause == "failed" and "secret" not in raised.value.message


def test_an_error_other_than_a_crop_error_becomes_the_general_note_of_the_take(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])
    pictures.error = RuntimeError("disk /secret/storage exploded")

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert take["frame_notes"] == [_not_cropped("failed", "is sent as it is: it could not be cropped to the frame of the take.")]
    assert "secret" not in str(take["frame_notes"])


def test_a_task_cancelled_while_it_crops_leaves_no_work_folder(core, pictures, monkeypatch):
    import threading

    from backend import workdir

    pictures.add("square", (1024, 1024))
    started = threading.Event()
    release = threading.Event()
    crop_file = framefit.crop_file

    def slow(source, box, folder, name):
        started.set()
        release.wait(5)
        return crop_file(source, box, folder, name)

    monkeypatch.setattr(framefit, "crop_file", slow)

    async def run():
        task = asyncio.create_task(framefit.fit(core.users["user-1"], "uploads/square.png", {"kind": "library", "item_id": "lib-square"}, (26, 15), "square.png"))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

    asyncio.run(run())

    area = workdir.area(workdir.FRAMES, "user-1")
    assert not area.exists() or list(area.iterdir()) == []
    assert pictures.stored == []


def test_the_first_crop_creates_the_table_when_it_is_missing(core, pictures):
    from src.plugin_api import db

    pictures.add("square", (1024, 1024))
    with db.get_cursor() as cursor:
        cursor.execute(f"DROP TABLE {framefit.CROPS}")

    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", {"kind": "library", "item_id": "lib-square"}, (26, 15), "square.png"))

    assert framefit.recorded("user-1", "uploads/square.png", (26, 15)).fitted == found


def test_a_source_file_rewritten_under_the_same_name_is_cropped_again(core, pictures):
    import os

    pictures.add("square", (1024, 1024))
    ref = {"kind": "library", "item_id": "lib-square"}
    first = asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", ref, (26, 15), "square.png"))
    path = pictures.files[_ref_key(ref)]
    _disc((1024, 1024), TEAL).save(path)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))

    again = asyncio.run(framefit.fit(core.users["user-1"], "uploads/square.png", ref, (26, 15), "square.png"))

    assert again.value != first.value and len(pictures.stored) == 2
    assert _disc_ratio(pictures.stored_path(again.value), TEAL) == pytest.approx(1.0, abs=0.01)


def _turned(path, stored_size, orientation=6):
    exif = Image.Exif()
    exif[0x0112] = orientation
    _disc(stored_size).save(path, exif=exif.tobytes())


def test_a_photo_that_declares_an_orientation_is_measured_and_cropped_upright(tmp_path):
    path = tmp_path / "turned.jpg"
    _turned(path, (400, 300))

    size = framefit.picture_size(path)
    output = framefit.crop_file(path, framefit.crop_box(*size, (9, 16)), tmp_path, "turned.jpg")

    assert size == (300, 400)
    with Image.open(output) as image:
        assert image.size == (224, 400) and image.getexif().get(0x0112) is None
    assert _disc_ratio(output) == pytest.approx(1.0, abs=0.02)


def test_a_turned_photo_already_in_the_ratio_of_the_take_is_sent_as_an_upright_copy(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    asset = pictures.add("phone", (480, 832), suffix=".jpg")
    _turned(pictures.files[_ref_key({"kind": "library", "item_id": "lib-phone"})], (480, 832), 8)
    project = _project(make_doc, make_project, [asset], [_frame("f1", "phone", "first")])

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/stored-1-phone-upright-832x480.jpg")]
    with Image.open(pictures.stored_path("uploads/stored-1-phone-upright-832x480.jpg")) as image:
        assert image.size == (832, 480) and image.getexif().get(0x0112) is None
    assert take["frame_notes"] is None


def test_a_turned_photo_whose_upright_copy_is_refused_is_sent_as_it_is_with_the_note(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    asset = pictures.add("phone", (480, 832), suffix=".jpg")
    _turned(pictures.files[_ref_key({"kind": "library", "item_id": "lib-phone"})], (480, 832), 6)
    project = _project(make_doc, make_project, [asset], [_frame("f1", "phone", "first")])
    refusal = {"code": "storage_quota_exceeded", "message": "full", "kind": "storage", "label": "", "format": "", "used": 1, "limit": 1, "percent": 100, "resets_at": None}
    pictures.error = core_bridge.LimitExceeded([refusal], "upload", None)

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/phone.jpg")]
    assert take["frame_notes"] == [_not_cropped("storage_full", "is sent as it is, not cropped to the frame of the take: the storage of the project's owner is full.")]


def test_a_16_9_photo_on_an_832x480_draft_is_sent_as_it_is_without_a_copy(core, make_doc, make_project, pictures):
    core.use_h3_12gb()
    project = _project(make_doc, make_project, [pictures.add("wide", (1280, 720))], [_frame("f1", "wide", "first")])

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/wide.png")]
    assert pictures.stored == [] and take["frame_notes"] is None


def test_a_picture_past_the_pixel_ceiling_is_sent_as_it_is_with_its_note(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    monkeypatch.setattr(framefit, "MAX_PIXELS", 1_000_000)
    project = _project(make_doc, make_project, [pictures.add("square", (1024, 1024))], [_frame("f1", "square", "first")])

    (take,) = _start(core, project, presets.MINIMAX_H3_12GB)

    assert _paths(core.submitted[0][1]) == [("first", "uploads/square.png")]
    assert [note["data"]["cause"] for note in take["frame_notes"]] == ["too_many_pixels"]


def test_the_last_image_of_a_previous_shot_that_cannot_be_cropped_starts_the_chained_take_as_it_is_with_the_note(core, make_doc, make_project, pictures, monkeypatch, store):
    store[("max_parallel_jobs", None)] = "4"
    core.use_wan()
    frames = Frames(monkeypatch, pictures, (768, 1152))
    project = make_project(doc=make_doc(clips=SHOTS, prompts=PROMPTS))
    first, second = _start(core, project, presets.WAN, shots=("s1", "s2"))
    _tick()
    core.complete(first["generation_id"])
    pictures.error = MediaRefError("upload_rejected", "The library is full.")

    _tick()

    taken = takes.get_take(second["id"])
    (_, request) = core.submitted[1]
    assert taken["status"] != "failed"
    assert _paths(request) == [("first", f"uploads/gen-{first['id']}-frame-4s.png")]
    assert taken["frame_notes"] == [
        {
            "code": "frame_not_cropped",
            "message": "The last image of the previous shot is sent as it is: it could not be cropped to the frame of the take.",
            "data": {"shot_id": "s2", "cause": "failed", "roles": ["first"], "chained": True},
        }
    ]


def test_a_phone_photo_in_several_pictures_is_read_and_cropped_like_a_jpeg(tmp_path):
    path = tmp_path / "phone.jpg"
    _disc((1024, 1024)).save(path, format="MPO", save_all=True, append_images=[_disc((1024, 1024), TEAL)])

    output = framefit.crop_file(path, framefit.crop_box(*framefit.picture_size(path), (26, 15)), tmp_path, "phone.jpg")

    with Image.open(output) as image:
        assert (output.name, image.format, image.size) == ("phone-crop-1024x590.jpg", "JPEG", (1024, 590))
    assert _disc_ratio(output) == pytest.approx(1.0, abs=0.01)


def test_a_picture_not_on_this_server_is_sent_as_it_is_when_no_work_folder_can_be_made_to_copy_it(core, pictures, monkeypatch):
    from backend import workdir

    pictures.add("far", (1024, 1024))
    monkeypatch.setattr(core_bridge, "media_file_path", lambda user, ref: None)

    def scratch(name, owner_id):
        raise RuntimeError("no settings table")

    monkeypatch.setattr(workdir, "scratch", scratch)

    found = asyncio.run(framefit.fit(core.users["user-1"], "uploads/far.png", {"kind": "library", "item_id": "lib-far"}, (26, 15), "far.png"))

    assert found is None and pictures.stored == []


class Loads:
    def __init__(self, monkeypatch):
        from PIL import ImageFile

        self.formats = []
        original = ImageFile.ImageFile.load

        def counted(image):
            self.formats.append(image.format)
            return original(image)

        monkeypatch.setattr(ImageFile.ImageFile, "load", counted)


def _limit(cause):
    return core_bridge.LimitExceeded([{"code": cause, "message": "x", "kind": "storage", "label": "", "format": "", "used": 1, "limit": 1, "percent": 100, "resets_at": None}], "upload", None)


def test_a_png_past_the_pixel_ceiling_is_never_decoded_before_generate_nor_when_the_take_is_made(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    monkeypatch.setattr(framefit, "MAX_PIXELS", 1_000_000)
    project = _project(make_doc, make_project, [pictures.add("huge", (1024, 1024))], [_frame("f1", "huge", "first")])
    loads = Loads(monkeypatch)
    user = core.users["user-1"]

    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.MINIMAX_H3_12GB)))
    decoded_before = list(loads.formats)
    (take,) = asyncio.run(generation.start(user, project, evaluation))

    assert [warning["data"]["cause"] for warning in evaluation.payload["warnings"] if warning["code"] == "frame_not_cropped"] == ["too_many_pixels"]
    assert [note["data"]["cause"] for note in take["frame_notes"]] == ["too_many_pixels"]
    assert decoded_before == [] and loads.formats == []


def test_the_orientation_of_a_png_is_read_from_its_header_only(tmp_path, monkeypatch):
    plain = tmp_path / "plain.png"
    _disc((400, 300)).save(plain)
    turned = tmp_path / "turned.png"
    exif = Image.Exif()
    exif[0x0112] = 6
    _disc((400, 300)).save(turned, exif=exif.tobytes())
    loads = Loads(monkeypatch)

    found = [framefit.picture(plain), framefit.picture(turned)]

    assert [(item.width, item.height, item.turned) for item in found] == [(400, 300, False), (300, 400, True)]
    assert loads.formats == []


def test_a_picture_pillow_refuses_as_too_large_is_said_to_have_too_many_pixels_before_generate_and_on_the_take(core, make_doc, make_project, pictures, monkeypatch):
    from PIL import Image as PillowImage

    core.use_h3_12gb()
    monkeypatch.setattr(PillowImage, "MAX_IMAGE_PIXELS", 200_000)
    project = _project(make_doc, make_project, [pictures.add("bomb", (1024, 1024))], [_frame("f1", "bomb", "first")])
    user = core.users["user-1"]

    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.MINIMAX_H3_12GB)))
    (take,) = asyncio.run(generation.start(user, project, evaluation))

    assert framefit.picture(pictures.files[_ref_key({"kind": "library", "item_id": "lib-bomb"})]) == framefit.Picture(0, 0, False, True)
    assert [warning["data"]["cause"] for warning in evaluation.payload["warnings"] if warning["code"] == "frame_not_cropped"] == ["too_many_pixels"]
    assert _paths(core.submitted[0][1]) == [("first", "uploads/bomb.png")]
    assert [note["data"]["cause"] for note in take["frame_notes"]] == ["too_many_pixels"]


def test_a_turned_photo_past_the_ceiling_already_in_the_ratio_says_the_same_before_generate_and_on_the_take(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    monkeypatch.setattr(framefit, "MAX_PIXELS", 100_000)
    asset = pictures.add("phone", (480, 832), suffix=".jpg")
    _turned(pictures.files[_ref_key({"kind": "library", "item_id": "lib-phone"})], (480, 832), 6)
    project = _project(make_doc, make_project, [asset], [_frame("f1", "phone", "first")])
    user = core.users["user-1"]

    evaluation = asyncio.run(estimate.evaluate(user, user, project["doc"], Order(shots=["s1"], quality="draft", variants=1, preset_id=presets.MINIMAX_H3_12GB)))
    (take,) = asyncio.run(generation.start(user, project, evaluation))

    before = [warning for warning in evaluation.payload["warnings"] if warning["code"] == "frame_not_cropped"]
    assert before == take["frame_notes"] and [note["data"]["cause"] for note in before] == ["too_many_pixels"]


def test_a_cmyk_photo_cropped_to_rgb_drops_its_colour_profile_and_an_rgb_photo_keeps_its_own(tmp_path):
    cmyk = tmp_path / "print.jpg"
    _disc((600, 600)).convert("CMYK").save(cmyk, icc_profile=b"cmyk-profile")
    rgb = tmp_path / "photo.jpg"
    _disc((600, 600)).save(rgb, icc_profile=b"rgb-profile")

    (tmp_path / "out").mkdir()
    outputs = [framefit.crop_file(source, framefit.crop_box(600, 600, (16, 9)), tmp_path / "out", source.name) for source in (cmyk, rgb)]

    with Image.open(outputs[0]) as image:
        assert image.mode == "RGB" and image.info.get("icc_profile") is None
    with Image.open(outputs[1]) as image:
        assert image.info.get("icc_profile") == b"rgb-profile"


def _three_squares(make_doc, make_project, pictures):
    clips = [{"id": f"s{n}", "start": (n - 1) * 4, "dur": 4} for n in (1, 2, 3)]
    prompts = [{"id": f"p{n}", "shotId": f"s{n}", "text": "A slow push-in."} for n in (1, 2, 3)]
    assets = [pictures.add(f"square{n}", (1024, 1024)) for n in (1, 2, 3)]
    frames = [_frame(f"f{n}", f"square{n}", "first", (n - 1) * 4, f"s{n}") for n in (1, 2, 3)]
    return make_project(doc=make_doc(clips=clips, prompts=prompts, frames=frames, assets=assets))


def test_after_a_full_storage_the_next_images_of_the_same_order_get_the_note_without_being_cropped(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    project = _three_squares(make_doc, make_project, pictures)
    pictures.error = _limit("storage_quota_exceeded")
    crops = []
    crop_file = framefit.crop_file
    monkeypatch.setattr(framefit, "crop_file", lambda *args: crops.append(args[0]) or crop_file(*args))

    made = _start(core, project, presets.MINIMAX_H3_12GB, shots=("s1", "s2", "s3"))

    assert len(crops) == 1
    assert [[note["data"]["cause"] for note in take["frame_notes"]] for take in made] == [["storage_full"]] * 3


def test_after_a_full_storage_a_crop_already_stored_for_a_next_image_of_the_same_order_is_still_sent(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    project = _three_squares(make_doc, make_project, pictures)
    known = asyncio.run(framefit.fit(core.users["user-1"], "uploads/square2.png", {"kind": "library", "item_id": "lib-square2"}, (26, 15), "square2.png"))
    pictures.error = _limit("storage_quota_exceeded")
    crops = []
    crop_file = framefit.crop_file
    monkeypatch.setattr(framefit, "crop_file", lambda *args: crops.append(args[0]) or crop_file(*args))

    made = _start(core, project, presets.MINIMAX_H3_12GB, shots=("s1", "s2", "s3"))

    assert len(crops) == 1
    assert [[note["data"]["cause"] for note in take["frame_notes"] or []] for take in made] == [["storage_full"], [], ["storage_full"]]
    assert [_paths(takes.get_take(take["id"])["request"]) for take in made] == [
        [("first", "uploads/square1.png")],
        [("first", known.value)],
        [("first", "uploads/square3.png")],
    ]


def test_a_crop_larger_than_the_largest_upload_does_not_stop_the_next_images_from_being_tried(core, make_doc, make_project, pictures, monkeypatch):
    core.use_h3_12gb()
    project = _three_squares(make_doc, make_project, pictures)
    pictures.error = _limit("upload_file_size_exceeded")
    crops = []
    crop_file = framefit.crop_file
    monkeypatch.setattr(framefit, "crop_file", lambda *args: crops.append(args[0]) or crop_file(*args))

    made = _start(core, project, presets.MINIMAX_H3_12GB, shots=("s1", "s2", "s3"))

    assert len(crops) == 3
    assert [[note["data"]["cause"] for note in take["frame_notes"]] for take in made] == [["upload_too_large"]] * 3


def test_a_chained_take_keeps_the_note_of_its_own_end_image_and_adds_the_one_of_the_chained_image(core, make_doc, make_project, pictures, monkeypatch, store):
    store[("max_parallel_jobs", None)] = "4"
    core.use_h3_12gb()
    Frames(monkeypatch, pictures, (768, 1152))
    end = pictures.add("end", (1024, 1024))
    project = make_project(doc=make_doc(clips=SHOTS, prompts=PROMPTS, assets=[end], frames=[_frame("f2", "end", "last", 8, "s2")]))
    pictures.error = MediaRefError("upload_rejected", "The library is full.")
    first, second = _start(core, project, presets.MINIMAX_H3_12GB, shots=("s1", "s2"))
    _tick()
    core.complete(first["generation_id"])

    _tick()

    taken = takes.get_take(second["id"])
    assert [(note["data"]["roles"], note["data"]["chained"]) for note in taken["frame_notes"]] == [(["last"], False), (["first"], True)]
