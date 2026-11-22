import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import core_bridge, presets, retouch, takes, tracker
from backend.exports import video
from backend.generation import TakeError

BASE = "/api/plugins/video-producer"
SHOTS = [{"id": "s1", "start": 0, "dur": 5}, {"id": "s2", "start": 5, "dur": 5}]


@pytest.fixture
def media(monkeypatch, media_store, export_storage):
    ran = []

    async def assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        ran.append(list(command))
        Path(command[-1]).write_bytes(b"mp4")
        return ""

    def local(user, ref, folder):
        path = Path(folder) / f"{ref['kind']}-{ref.get('file_id') or ref.get('item_id')}.mp4"
        path.write_bytes(b"source")
        return path

    monkeypatch.setattr(video, "assemble", assemble)
    monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(core_bridge, "local_media_file", local)
    monkeypatch.setattr(core_bridge, "probe_video", lambda path: SimpleNamespace(width=832, height=480, fps=24.0, duration=5.0, has_audio=True))
    return SimpleNamespace(ran=ran, store=media_store)


@pytest.fixture
def project(core, make_project):
    core.use_h3_retouch()
    return make_project(clips=SHOTS)


def _source(project, shot="s1", variant="A", **fields):
    values = {
        "project_id": project["id"],
        "shot_id": shot,
        "user_id": "user-1",
        "quality": "draft",
        "kind": "render",
        "preset_id": presets.MINIMAX_H3_12GB,
        "mode": "video",
        "status": "done",
        "generation_id": f"gen-src-{variant}",
        "file_id": f"file-src-{variant}",
        "file_path": f"generations/2026-11-22/gen-src-{variant}/1.mp4",
        "resolution": "832x480",
        "width": 832,
        "height": 480,
        "duration_s": 5.0,
        "fps": 24.0,
        "variant": variant,
        "shot_revision": 1,
        **fields,
    }
    return takes.create_take(values)


def _retouch(client, project, take, **body):
    order = {"task": "refine_faces", "start_s": 2.0, "end_s": 3.25, **body}
    return client.post(f"{BASE}/projects/{project['id']}/takes/{take['id']}/retouch", json=order)


def _finish(core, generation_id):
    core.complete(generation_id, seconds=1.25, fps=24.0)
    asyncio.run(tracker.Tracker().tick())


def test_a_range_snaps_to_the_frames_of_the_take():
    take = {"fps": 24.0, "duration_s": 5.0}

    window = retouch.window_of(take, retouch.REFINE, 2.01, 3.26)

    assert (window.first, window.last, window.frames, window.count) == (48, 78, 120, 30)
    assert window.start_s == 2.0 and window.end_s == 3.25


@pytest.mark.parametrize(
    ("task", "start", "end", "code"),
    [
        (retouch.REFINE, 3.0, 2.0, "range_invalid"),
        (retouch.REFINE, -1.0, 2.0, "range_invalid"),
        (retouch.REFINE, 4.0, 5.5, "range_outside_take"),
        (retouch.REFINE, 1.0, 1.2, "range_too_short"),
        (retouch.REMIX, 1.0, 1.5, "range_too_short"),
        (retouch.REMIX, 1.0, 4.5, "range_too_long"),
        (retouch.REFINE, 1.0, "two", "range_invalid"),
    ],
)
def test_a_range_outside_what_the_task_takes_is_refused(task, start, end, code):
    with pytest.raises(TakeError) as refused:
        retouch.window_of({"fps": 24.0, "duration_s": 5.0}, task, start, end)

    assert refused.value.code == code


def test_refine_faces_takes_the_whole_take_and_remix_its_capped_range():
    assert retouch.window_of({"fps": 24.0, "duration_s": 5.0}, retouch.REFINE, 0, 5.0).count == 120
    assert retouch.window_of({"fps": 24.0, "duration_s": 5.0}, retouch.REMIX, 1.0, 4.0).count == 72


def test_the_cut_keeps_the_frames_of_the_range_and_their_sound():
    window = retouch.Window(48, 78, 24.0, 120)

    command = retouch.cut_command("ffmpeg", "in.mp4", window, Path("out.mp4"), True)

    assert command[command.index("-vf") + 1].startswith("trim=start_frame=48:end_frame=78,setpts=PTS-STARTPTS")
    assert command[command.index("-af") + 1] == "atrim=start=2:end=3.25,asetpts=PTS-STARTPTS"
    assert command[command.index("-frames:v") + 1] == "30"
    assert "-an" in retouch.cut_command("ffmpeg", "in.mp4", window, Path("out.mp4"), False)


def test_the_splice_puts_the_result_between_the_untouched_frames_and_keeps_the_sound_of_the_take():
    window = retouch.Window(48, 78, 24.0, 120)

    command = retouch.splice_command("ffmpeg", "take.mp4", "result.mp4", window, (832, 480), Path("out.mp4"), True)

    graph = command[command.index("-filter_complex") + 1]
    assert "[0:v]trim=end_frame=48" in graph
    assert "[1:v]fps=24,scale=832:480" in graph and "tpad=stop_mode=clone:stop=30,trim=end_frame=30" in graph
    assert "[0:v]trim=start_frame=78" in graph
    assert graph.endswith("[head][middle][tail]concat=n=3:v=1:a=0[picture]")
    assert command[command.index("-c:a") + 1] == "copy" and command[command.index("-frames:v") + 1] == "120"


def test_a_range_at_an_edge_of_the_take_splices_without_the_missing_part():
    start = retouch.splice_command("ffmpeg", "t.mp4", "r.mp4", retouch.Window(0, 30, 24.0, 120), (832, 480), Path("o.mp4"), False)
    end = retouch.splice_command("ffmpeg", "t.mp4", "r.mp4", retouch.Window(90, 120, 24.0, 120), (832, 480), Path("o.mp4"), False)

    assert start[start.index("-filter_complex") + 1].endswith("[middle][tail]concat=n=2:v=1:a=0[picture]")
    assert end[end.index("-filter_complex") + 1].endswith("[head][middle]concat=n=2:v=1:a=0[picture]")
    assert "-an" in start


def test_the_offers_name_the_engines_and_limits_of_each_task(client, core, project):
    response = client.get(f"{BASE}/retouch/offers")

    assert response.status_code == 200
    offers = {offer["task"]: offer for offer in response.json()["data"]["offers"]}
    assert [engine["preset_id"] for engine in offers["refine_faces"]["engines"]] == [presets.MINIMAX_H3_12GB, presets.MINIMAX_H3_FAST_12GB]
    assert [engine["preset_id"] for engine in offers["remix"]["engines"]] == [presets.MINIMAX_H3_12GB]
    assert (offers["remix"]["min_s"], offers["remix"]["max_s"], offers["refine_faces"]["max_s"]) == (1.0, 3.0, None)
    assert offers["refine_faces"]["ready"] is True and offers["refine_faces"]["missing"] == []


def test_the_offers_say_when_the_detection_models_are_missing(client, core, project):
    core.missing.update({"face_landmarker.task", "hand_landmarker.task"})

    offers = {offer["task"]: offer for offer in client.get(f"{BASE}/retouch/offers").json()["data"]["offers"]}

    assert offers["refine_faces"]["ready"] is False and offers["refine_faces"]["reason"] == "detector_missing"
    assert offers["refine_faces"]["missing"] == ["face_landmarker.task", "hand_landmarker.task"]
    assert offers["remix"]["ready"] is True


def test_refine_faces_cuts_the_range_and_queues_a_new_take_of_the_same_shot(client, core, project, media):
    source = _source(project)

    response = _retouch(client, project, source, strength="light", hands=False)

    assert response.status_code == 202, response.text
    made = response.json()["data"]["take"]
    assert (made["kind"], made["parent_take_id"], made["shot_id"], made["variant"], made["quality"]) == ("retouch", source["id"], "s1", "B", "draft")
    assert made["retouch"] == {
        "task": "refine_faces", "start_s": 2.0, "end_s": 3.25, "source_take_id": source["id"],
        "preset_id": presets.MINIMAX_H3_12GB, "strength": "light", "faces": True, "hands": False,
    }
    (_, request), = core.submitted
    assert (request["preset_id"], request["mode"]) == (presets.MINIMAX_H3_12GB, "refine_faces")
    form = request["form_data"]
    assert form["input_video"].startswith("uploads/")
    assert (form["enhancement_strength"], form["refine_faces"], form["refine_hands"]) == ("light", True, False)
    assert form["face_detector_model"] == "model:id-face_landmarker.task" and "hand_detector_model" not in form
    assert form["model"].startswith("model:")
    assert media.store.saved[0]["name"] == f"retouch-{source['id']}-48-78.mp4"
    stored = takes.get_take(made["id"])
    assert stored["retouch"]["cut"] == {"kind": "library", "item_id": "item-1"} and stored["shot_revision"] == 1


def test_refine_faces_is_refused_while_its_detection_model_is_missing(client, core, project, media):
    core.missing.add("face_landmarker.task")
    source = _source(project)

    response = _retouch(client, project, source)

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "detector_missing"
    assert "face_landmarker.task" in response.json()["detail"]["message"]
    assert "scan the models (Admin > Models)" in response.json()["detail"]["message"]
    assert core.submitted == [] and media.ran == [] and len(takes.list_takes(project["id"])) == 1


def test_refine_faces_needs_faces_or_hands(client, core, project, media):
    response = _retouch(client, project, _source(project), faces=False, hands=False)

    assert response.status_code == 422 and response.json()["detail"]["error"] == "nothing_to_refine"


def test_remix_sends_the_change_at_the_size_of_the_take_and_keeps_its_sound(client, core, project, media):
    source = _source(project)

    response = _retouch(client, project, source, task="remix", start_s=1.0, end_s=3.5, prompt="make it snow")

    assert response.status_code == 202, response.text
    (_, request), = core.submitted
    assert request["mode"] == "remix" and request["prompts"] == [{"positive": "make it snow", "negative": ""}]
    form = request["form_data"]
    assert (form["resolution"], form["keep_sound"], form["max_seconds"], form["quantity"]) == ("832x480", True, 14, 1)
    assert form["source_video"].startswith("uploads/")


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"task": "remix", "prompt": " "}, 422, "prompt_required"),
        ({"task": "remix", "prompt": "snow", "start_s": 0.0, "end_s": 4.0}, 422, "range_too_long"),
        ({"task": "remix", "prompt": "snow", "preset_id": presets.MINIMAX_H3_FAST_12GB}, 422, "task_not_offered"),
        ({"task": "extend"}, 422, "task_invalid"),
        ({"strength": "huge"}, 422, "strength_invalid"),
    ],
)
def test_a_retouch_the_plugin_cannot_run_is_refused_before_anything_is_cut(client, core, project, media, body, status, code):
    response = _retouch(client, project, _source(project), **body)

    assert response.status_code == status
    assert response.json()["detail"]["error"] == code
    assert media.ran == [] and core.submitted == []


def test_only_a_finished_take_of_the_users_project_can_be_retouched(client, core, project, media, make_project):
    running = _source(project, status="running")
    other = make_project(user_id="user-2", clips=SHOTS)
    foreign = _source(other)

    assert _retouch(client, project, running).json()["detail"]["error"] == "take_not_done"
    assert _retouch(client, other, foreign).status_code == 404


def test_the_retouched_take_is_spliced_once_its_range_is_generated(client, core, project, media):
    source = _source(project)
    made = _retouch(client, project, source).json()["data"]["take"]

    _finish(core, made["generation_id"])

    done = takes.get_take(made["id"])
    assert done["status"] == "done" and done["progress"] == 100.0
    assert done["media_ref"] == {"kind": "library", "item_id": "item-2"}
    assert (done["duration_s"], done["fps"], done["width"], done["height"]) == (5.0, 24.0, 832, 480)
    shown = takes.public(done)
    assert shown["url"] == f"/api/media/uploads/{done['file_path'].removeprefix('uploads/')}"
    assert shown["origin"] == {"kind": "library", "itemId": "item-2"}
    assert "cut" not in shown["retouch"] and "output" not in shown["retouch"]
    splice = media.ran[-1]
    assert splice[splice.index("-i") + 1].endswith(f"history-{source['file_id']}.mp4")
    assert splice[-1].endswith(f"{source['id']}-B-retouch.mp4")
    assert takes.get_take(source["id"])["status"] == "done"


def test_a_retouched_take_can_be_retouched_again_from_its_own_video(client, core, project, media):
    source = _source(project)
    first = _retouch(client, project, source).json()["data"]["take"]
    _finish(core, first["generation_id"])
    again = takes.get_take(first["id"])

    response = _retouch(client, project, again, start_s=0.5, end_s=1.5)

    assert response.status_code == 202, response.text
    second = response.json()["data"]["take"]
    assert second["parent_take_id"] == first["id"] and second["variant"] == "C"
    assert media.ran[-1][media.ran[-1].index("-i") + 1].endswith("library-item-2.mp4")


def test_a_failed_splice_fails_the_take_and_refunds_it(client, core, project, media, monkeypatch):
    made = _retouch(client, project, _source(project)).json()["data"]["take"]

    async def broken(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        raise video.ExportError(code, "ffmpeg stopped.")

    monkeypatch.setattr(video, "assemble", broken)
    _finish(core, made["generation_id"])

    failed = takes.get_take(made["id"])
    assert (failed["status"], failed["error_code"], failed["error_message"]) == ("failed", "retouch_splice_failed", "ffmpeg stopped.")


def test_a_failed_retouch_is_retried_on_the_same_range(client, core, project, media):
    source = _source(project)
    made = _retouch(client, project, source, task="remix", start_s=1.0, end_s=2.0, prompt="rain").json()["data"]["take"]
    core.fail(made["generation_id"])
    asyncio.run(tracker.Tracker().tick())

    response = client.post(f"{BASE}/takes/{made['id']}/retry")

    assert response.status_code == 202, response.text
    again = response.json()["data"]["take"]
    assert again["kind"] == "retouch" and again["parent_take_id"] == source["id"]
    assert (again["retouch"]["task"], again["retouch"]["start_s"], again["retouch"]["prompt"]) == ("remix", 1.0, "rain")
    assert core.submitted[-1][1]["prompts"][0]["positive"] == "rain"
