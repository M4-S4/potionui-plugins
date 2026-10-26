from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import chain, core_bridge, projects

from .test_chain_frame import BASE, FFMPEG, TAKE_FILE, _asset_shape, _frame_luma, _luma, _placed, _shot, library, video


def _start_frame(client, project_id, shot_id="s1"):
    return client.post(f"{BASE}/projects/{project_id}/shots/{shot_id}/start-frame")


def test_the_cut_of_a_shot_starts_at_its_source_in():
    assert chain.start_of({"srcIn": 1.2344, "dur": 2}) == 1.234
    assert chain.start_of({"srcIn": -1, "dur": 2}) == 0.0
    assert chain.start_of({"dur": 4}) == 0.0


def test_the_first_frame_command_seeks_on_the_input_and_keeps_one_frame():
    later = chain.first_frame_command("ffmpeg", "in.mp4", 1.25, Path("out.png"))
    start = chain.first_frame_command("ffmpeg", "in.mp4", 0.0, Path("out.png"))

    assert later[later.index("-ss") + 1] == "1.25" and later.index("-ss") < later.index("-i")
    assert later[-4:] == ["-frames:v", "1", "-y", "out.png"]
    assert "-ss" not in start


@FFMPEG
@pytest.mark.requires_ffmpeg
@pytest.mark.parametrize(("src_in", "index"), [(0.0, 0), (0.5, 5), (1.25, 13), (2.0, 20)])
def test_the_frame_is_the_first_one_the_cut_of_the_shot_keeps(client, make_project, library, video, src_in, index):
    project, take, asset = _placed(make_project, src_in=src_in, dur=0.8)
    library.files[("history", TAKE_FILE)] = video

    response = _start_frame(client, project["id"])

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"] == {"shotId": "s1", "takeId": take["id"], "assetId": asset["id"], "at": src_in}
    ((user_id, name, png),) = library.saved
    assert user_id == "user-1" and name == f"1-frame-{src_in:g}s.png" == data["media"]["filename"]
    luma = _luma(png)
    assert abs(luma - _frame_luma(video, index)) < 1.5
    assert all(abs(luma - _frame_luma(video, other)) > 3 for other in (index - 1, index + 1) if 0 <= other < 30)


def test_a_shot_without_a_video_has_no_first_frame(client, make_project, library):
    still = {**_asset_shape(), "id": "pic", "src": "/api/media/uploads/pic.png", "origin": {"kind": "library", "itemId": "it-1"}}

    for project in (_shot(make_project), _shot(make_project, asset=still)):
        response = _start_frame(client, project["id"])
        detail = response.json()["detail"]
        assert response.status_code == 409 and (detail["error"], detail["message"]) == ("no_media", "The shot has no video to take its first frame from.")
    assert library.saved == []


def test_the_start_frame_of_an_unknown_shot_is_not_found_and_leaves_the_document_alone(client, make_project, library):
    project, _, _ = _placed(make_project)
    before = projects.get_project(project["id"])

    unknown = _start_frame(client, project["id"], shot_id="nope")
    _start_frame(client, project["id"])

    assert unknown.status_code == 404 and unknown.json()["detail"]["error"] == "shot_not_found"
    assert projects.get_project(project["id"]) == before


def test_a_cloud_video_model_says_which_frames_it_takes():
    frames = (SimpleNamespace(role="first_frame", tasks=frozenset({"img2video"})), SimpleNamespace(role="last_frame", tasks=frozenset({"img2video"})))
    entry = SimpleNamespace(label="Veo", provider_model_id="google/veo", tasks=["img2video"], spec=SimpleNamespace(typical_seconds=60, max_seconds=8, inputs=frames))

    summary = core_bridge._cloud_summary("veo", entry)

    assert summary["inputs"] == [{"role": "first_frame", "tasks": ["img2video"]}, {"role": "last_frame", "tasks": ["img2video"]}]
