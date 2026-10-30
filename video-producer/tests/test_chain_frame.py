import shutil
import subprocess
from pathlib import Path

import pytest

from backend import core_bridge, frame_grab, presets, projects, takes
from backend.core_bridge import MediaRefError
from backend.projects import DocError
from src.plugin_api import AccountType, get_current_active_user

from .test_director import TEXT_ONLY_WARNING, _plans, _wan_tier

BASE = "/api/plugins/video-producer"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FFMPEG = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg and ffprobe are not on the PATH")
TAKE_FILE = "generations/2026-10-24/g-1/1.mp4"
UPLOAD = "uploads/harbour-dawn.mp4"
FPS = 10


def _as(app, user):
    app.dependency_overrides[get_current_active_user] = lambda: user


def _write_video(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ramp = f"color=c=black:s=64x36:r={FPS}:d=3,format=yuv420p,geq=lum=30+6*N:cb=128:cr=128"
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", ramp]
    subprocess.run([*command, "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", "-g", "30", "-y", str(path)], check=True)
    return path


def _luma(png):
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vf", "format=gray", "-f", "rawvideo", "-"]
    pixels = subprocess.run(command, input=png, capture_output=True, check=True).stdout
    return sum(pixels) / len(pixels)


def _frame_luma(video, index):
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(video)]
    picked = [*command, "-vf", f"select=eq(n\\,{index})", "-fps_mode", "passthrough", "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"]
    return _luma(subprocess.run(picked, capture_output=True, check=True).stdout)


class Library:
    def __init__(self):
        self.saved = []
        self.error = None
        self.files = {}

    def local_media_file(self, kind, value, folder):
        return self.files.get((kind, value))

    async def save_user_media(self, user, path):
        if self.error is not None:
            raise self.error
        path = Path(path)
        self.saved.append((user.id, path.name, path.read_bytes()))
        return {"value": f"uploads/stored-{len(self.saved)}.png", "media_type": "image", "original_filename": path.name, "origin": None}

    def upload_item(self, user_id, value):
        return {"item_id": f"item-{value.rsplit('/', 1)[-1]}", "filename": value, "width": 64, "height": 36}


@pytest.fixture
def library(core, export_storage, monkeypatch):
    found = Library()
    monkeypatch.setattr(core_bridge, "local_media_file", found.local_media_file)
    monkeypatch.setattr(core_bridge, "save_user_media", found.save_user_media)
    monkeypatch.setattr(core_bridge, "upload_item", found.upload_item)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: shutil.which("ffmpeg"))
    return found


@pytest.fixture
def video(tmp_path):
    return _write_video(tmp_path / "source" / "1.mp4") if HAS_FFMPEG else None


def _take(project_id):
    return takes.create_take(
        {
            "project_id": project_id,
            "shot_id": "s1",
            "user_id": "user-1",
            "quality": "draft",
            "kind": "render",
            "status": "done",
            "generation_id": "g-1",
            "file_id": "f-1",
            "file_path": TAKE_FILE,
        }
    )


def _shot(make_project, asset=None, src_in=0.0, dur=4.0):
    first = {"id": "s1", "start": 0, "dur": dur, "srcIn": src_in, "assetId": asset["id"] if asset else None, "stage": "draft"}
    return make_project(clips=[first, {"id": "s2", "start": dur, "dur": 4}], assets=[asset] if asset else [])


def _placed(make_project, src_in=0.0, dur=4.0):
    project = _shot(make_project, src_in=src_in, dur=dur)
    take = _take(project["id"])
    asset = {
        "id": f"gen-{take['id']}",
        "kind": "video",
        "name": "Take 1",
        "src": "/api/media/generations/g-1/1.mp4",
        "origin": {"kind": "history", "generationId": "g-1", "fileId": "f-1"},
        "srcDur": 3.0,
        "generated": True,
        "quality": "draft",
        "resultId": take["id"],
    }
    doc = projects.get_project(project["id"])["doc"]
    doc["assets"].append({**_asset_shape(), **asset})
    doc["clips"][0]["assetId"] = asset["id"]
    doc["clips"][0]["take"] = take["id"]
    saved = projects.save_project(project["id"], doc, projects.get_project(project["id"])["version"])
    return saved, take, asset


def _asset_shape():
    return {
        "kind": "image",
        "name": "",
        "src": None,
        "origin": None,
        "srcDur": None,
        "width": None,
        "height": None,
        "fps": None,
        "res": None,
        "generated": False,
        "quality": None,
        "resultId": None,
        "role": None,
    }


def _end_frame(client, project_id, shot_id="s1"):
    return client.post(f"{BASE}/projects/{project_id}/shots/{shot_id}/end-frame")


def test_the_cut_of_a_shot_ends_at_its_source_in_plus_its_duration():
    assert frame_grab.end_of({"srcIn": 0.5, "dur": 1.5}) == 2.0
    assert frame_grab.end_of({"srcIn": 1.2344, "dur": 2}) == 3.234
    assert frame_grab.end_of({"dur": 4}) == 4.0


def test_the_cut_of_a_slowed_shot_ends_where_its_take_stops_showing():
    assert frame_grab.end_of({"srcIn": 1, "dur": 4, "speed": 0.5}) == 3.0
    assert frame_grab.end_of({"srcIn": 0.5, "dur": 8, "speed": 0.25}) == 2.5
    assert frame_grab.end_of({"srcIn": 1, "dur": 4, "speed": 2}) == 5.0


def test_the_command_decodes_from_one_second_before_the_end_and_drops_every_frame_from_the_end_on():
    late = frame_grab.frame_command("ffmpeg", "in.mp4", 2.0, Path("out.png"))
    early = frame_grab.frame_command("ffmpeg", "in.mp4", 0.6, Path("out.png"))

    assert late[late.index("-ss") + 1] == "1" and late.index("-ss") < late.index("-i")
    assert late[late.index("-vf") + 1] == "trim=end=1"
    assert "-ss" not in early and early[early.index("-vf") + 1] == "trim=end=0.6"
    assert late[-6:] == ["-fps_mode", "passthrough", "-update", "1", "-y", "out.png"]
    past = frame_grab.frame_command("ffmpeg", "in.mp4", 6.0, Path("out.png"), 3.0)
    assert past[past.index("-ss") + 1] == "2" and past[past.index("-vf") + 1] == "trim=end=4"


@FFMPEG
@pytest.mark.requires_ffmpeg
@pytest.mark.parametrize(
    ("src_in", "dur", "index"),
    [(0.5, 1.5, 19), (0.0, 1.25, 12), (0.2, 1.25, 14), (2.0, 4.0, 29), (0.0, 0.4, 3)],
)
def test_the_frame_is_the_last_one_the_cut_of_the_shot_shows(client, make_project, library, video, src_in, dur, index):
    project, take, asset = _placed(make_project, src_in=src_in, dur=dur)
    library.files[("history", TAKE_FILE)] = video

    response = _end_frame(client, project["id"])

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    end = round(src_in + dur, 3)
    assert data["source"] == {"shotId": "s1", "takeId": take["id"], "assetId": asset["id"], "at": end}
    ((user_id, name, png),) = library.saved
    assert user_id == "user-1" and name == f"1-frame-{end:g}s.png" == data["media"]["filename"]
    luma = _luma(png)
    assert abs(luma - _frame_luma(video, index)) < 1.5
    assert all(abs(luma - _frame_luma(video, other)) > 3 for other in (index - 1, index + 1) if 0 <= other < 30)


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_the_frame_is_stored_as_an_image_of_the_library_and_the_work_folder_is_removed(client, make_project, library, video, export_storage):
    project, _, _ = _placed(make_project, src_in=0.5, dur=1.5)
    library.files[("history", TAKE_FILE)] = video

    response = _end_frame(client, project["id"])

    assert response.json()["data"]["media"] == {
        "kind": "library",
        "item_id": "item-stored-1.png",
        "media_type": "image",
        "url": "/api/media/uploads/stored-1.png",
        "filename": "1-frame-2s.png",
        "width": 64,
        "height": 36,
        "origin": {"kind": "library", "itemId": "item-stored-1.png"},
    }
    assert list((export_storage / "video_producer" / "frames" / "user-1").iterdir()) == []


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_an_imported_video_gives_its_frame_without_a_take(client, core, make_project, library, video):
    core.add_media({"kind": "library", "item_id": "it-7"}, UPLOAD, media_type="video")
    asset = {**_asset_shape(), "id": "imp", "kind": "video", "name": "Harbour", "src": "/api/media/uploads/harbour-dawn.mp4", "origin": {"kind": "library", "itemId": "it-7"}}
    project = _shot(make_project, asset=asset, src_in=1.0, dur=1.0)
    library.files[("library", UPLOAD)] = video

    response = _end_frame(client, project["id"])

    assert response.status_code == 200, response.text
    assert response.json()["data"]["source"] == {"shotId": "s1", "takeId": None, "assetId": "imp", "at": 2.0}
    assert library.saved[0][1] == "harbour-dawn-frame-2s.png"
    assert abs(_luma(library.saved[0][2]) - _frame_luma(video, 19)) < 1.5


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_an_administrator_stores_the_frame_in_the_library_of_the_project_owner(app, client, make_project, library, video, make_user):
    project, _, _ = _placed(make_project)
    library.files[("history", TAKE_FILE)] = video
    _as(app, make_user(AccountType.ADMIN, user_id="admin-1"))

    assert _end_frame(client, project["id"]).status_code == 200
    assert library.saved[0][0] == "user-1"


@FFMPEG
@pytest.mark.requires_ffmpeg
def test_a_frame_the_library_refuses_is_a_store_failure(client, make_project, library, video):
    project, _, _ = _placed(make_project)
    library.files[("history", TAKE_FILE)] = video
    library.error = MediaRefError("upload_rejected", "The file is too large.")

    response = _end_frame(client, project["id"])

    detail = response.json()["detail"]
    assert response.status_code == 502 and (detail["error"], detail["data"]) == ("extract_failed", {"code": "store_failed"})


def test_a_shot_without_a_video_has_no_media(client, make_project, library):
    still = {**_asset_shape(), "id": "pic", "src": "/api/media/uploads/pic.png", "origin": {"kind": "library", "itemId": "it-1"}}
    empty = _shot(make_project)
    image = _shot(make_project, asset=still)

    for project in (empty, image):
        response = _end_frame(client, project["id"])
        assert response.status_code == 409 and response.json()["detail"]["error"] == "no_media"
    assert library.saved == []


def test_a_take_whose_file_is_gone_has_no_media(client, make_project, library):
    project, _, _ = _placed(make_project)

    response = _end_frame(client, project["id"])

    assert response.status_code == 409 and response.json()["detail"]["error"] == "no_media"


def test_an_unknown_shot_is_not_found(client, make_project, library):
    project, _, _ = _placed(make_project)

    response = _end_frame(client, project["id"], shot_id="nope")

    assert response.status_code == 404 and response.json()["detail"]["error"] == "shot_not_found"


def test_another_users_project_is_not_found(app, client, make_project, library, make_user):
    project, _, _ = _placed(make_project)
    _as(app, make_user(user_id="user-2"))

    assert _end_frame(client, project["id"]).status_code == 404


def test_without_ffmpeg_the_frame_cannot_be_taken(client, make_project, library, monkeypatch, tmp_path):
    project, _, _ = _placed(make_project)
    library.files[("history", TAKE_FILE)] = tmp_path / "1.mp4"
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: None)

    response = _end_frame(client, project["id"])

    assert response.status_code == 503 and response.json()["detail"]["error"] == "ffmpeg_missing"


def test_without_a_writable_work_folder_the_frame_cannot_be_taken(client, make_project, library, export_storage, tmp_path, monkeypatch):
    project, _, _ = _placed(make_project)
    library.files[("history", TAKE_FILE)] = tmp_path / "1.mp4"
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    (export_storage / "video_producer").write_text("not a directory", encoding="utf-8")

    response = _end_frame(client, project["id"])

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "workdir_unwritable"
    assert response.json()["detail"]["message"].startswith(f"Video Producer cannot write in {export_storage / 'video_producer' / 'frames' / 'user-1'}: ")


def test_the_end_frame_leaves_the_document_alone(client, make_project, library):
    project, _, _ = _placed(make_project)
    before = projects.get_project(project["id"])

    _end_frame(client, project["id"])

    after = projects.get_project(project["id"])
    assert (after["version"], after["doc"]) == (before["version"], before["doc"])


def test_the_document_keeps_the_option_and_where_a_frame_was_taken(make_doc):
    frame_of = {"shotId": "s1", "takeId": "t1", "assetId": "gen-t1", "at": 4.0}
    still = {"shotId": "s1", "takeId": None, "assetId": "pic", "at": None}
    doc = make_doc(assets=[{"id": "a", "frameOf": frame_of}, {"id": "b", "frameOf": still}, {"id": "c"}])
    doc["firstFromPrevious"] = False

    projects.validate_doc(doc)

    for broken in ({**frame_of, "extra": 1}, {key: value for key, value in frame_of.items() if key != "at"}, {**frame_of, "at": "end"}):
        with pytest.raises(DocError):
            projects.validate_doc({**doc, "assets": [{**doc["assets"][0], "frameOf": broken}]})
    with pytest.raises(DocError):
        projects.validate_doc({**doc, "firstFromPrevious": "yes"})


def test_a_text_only_preset_says_that_it_leaves_out_a_first_frame_taken_from_the_previous_shot(core, make_doc):
    preset_id = _wan_tier(core, preset_id=presets.WAN22_14B_LIGHTNING_12GB)
    core.add_media({"kind": "library", "item_id": "it-9"}, "uploads/1-frame-4s.png", "image")
    chained = {"id": "fr", "kind": "image", "name": "1-frame-4s.png", "origin": {"kind": "library", "itemId": "it-9"}, "frameOf": {"shotId": "s0", "takeId": "t0", "assetId": "gen-t0", "at": 4.0}}
    frame = {"id": "f1", "shotId": "s1", "time": 0, "assetId": "fr", "role": "first", "strength": 100}
    doc = make_doc(clips=[{"id": "s1", "start": 0, "dur": 4, "label": "Opening"}], frames=[frame], assets=[chained])

    plans = _plans(core, doc, preset_id=preset_id)

    assert plans.shots[0].director_mode == "t2v"
    assert plans.shots[0].request["form_data"]["video_director"]["media"] == []
    assert plans.warnings == [TEXT_ONLY_WARNING]
