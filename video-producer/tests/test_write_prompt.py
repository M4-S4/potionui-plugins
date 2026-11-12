import asyncio
import copy

import pytest

from backend import bible, core_bridge, director, presets, prompt_writer

WOMAN = {"id": "c-woman", "label": "the red-haired woman", "text": "A woman in her thirties, short copper hair.", "props": "a brass lantern", "references": ["r-face"]}
FISHER = {"id": "c-fisher", "label": "the old fisherman", "text": "A man in his seventies, white beard.", "props": "", "references": []}
HARBOUR = {"id": "p-harbour", "label": "the harbour at dawn", "text": "Wet cobblestones, low mist.", "references": ["r-set"]}
REFERENCES = [
    {"id": "r-face", "assetId": "face", "space": "identite", "type": "Personnage", "scope": {"type": "global"}},
    {"id": "r-set", "assetId": "set", "space": "decors3d", "type": "Décor", "scope": {"type": "global"}},
]
READY = {"available": True, "vision": True, "name": "Qwen3-VL", "code": None, "message": None, "models": [{"id": "llm-1", "name": "Qwen3-VL", "vision": True}]}
WRITTEN = "The red-haired woman lifts her lantern as the old fisherman turns toward the sea."


def _pictures(core, *names):
    assets = []
    for name in names:
        core.add_media({"kind": "library", "item_id": f"lib-{name}"}, f"uploads/{name}.png", "image")
        assets.append({"id": name, "kind": "image", "name": name, "origin": {"kind": "library", "itemId": f"lib-{name}"}})
    return assets


def _doc(core, make_doc, mode="Ref2VA", frames=("start", "end"), prompt="The woman waits.", card_words=None, shot_words=None, pictured=True):
    doc = make_doc(
        clips=[{"id": "s1", "start": 0, "dur": 4, "label": "Quay", "cast": {"characters": ["c-woman", "c-fisher"], "place": "p-harbour"}}],
        prompts=[{"id": "p", "shotId": "s1", "text": prompt}] if prompt is not None else [],
        frames=[{"id": f"f-{role}", "shotId": "s1", "time": 0 if role == "start" else 4, "assetId": role, "role": "first" if role == "start" else "last"} for role in frames],
        assets=_pictures(core, "face", "set", "start", "end"),
        references=copy.deepcopy(REFERENCES),
        direction={"mode": mode},
    )
    cards = (WOMAN, FISHER) if pictured else ({**WOMAN, "references": []}, FISHER)
    doc["bible"] = {"characters": [dict(card) for card in cards], "places": [dict(HARBOUR if pictured else {**HARBOUR, "references": []})]}
    if card_words is not None:
        doc["cardWords"] = card_words
    if shot_words is not None:
        doc["clips"][0]["cardWords"] = shot_words
    return doc


class Writer:
    def __init__(self, monkeypatch, status=READY, reply=None, error=None, delay=0.0):
        self.status = dict(status)
        self.reply = {"text": WRITTEN, "reasoning": None, "model_id": None, "llm_id": "llm-1"} if reply is None else reply
        self.error = error
        self.delay = delay
        self.calls = []
        self.asked = []
        self.cancelled = []
        self.root = None
        self.sizes = []
        monkeypatch.setattr(core_bridge, "prompt_writer_status", self.prompt_writer_status)
        monkeypatch.setattr(core_bridge, "write_prompt_for_preset", self.write_prompt_for_preset)

    def prompt_writer_status(self, user_id):
        self.asked.append(user_id)
        self.status_on_loop = _on_loop()
        if isinstance(self.status, Exception):
            raise self.status
        return dict(self.status)

    async def write_prompt_for_preset(self, user_id, instruction, *, preset_id=None, mode=None, form_data=None, media=()):
        self.calls.append({"user_id": user_id, "instruction": instruction, "preset_id": preset_id, "mode": mode, "form_data": form_data, "media": list(media)})
        if self.root is not None:
            self.sizes.append([(self.root / item["value"]).stat().st_size for item in media])
        if self.delay:
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled.append(user_id)
                raise
        if self.error is not None:
            raise self.error
        return dict(self.reply)


def _on_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _write(client, project_id, body, shot_id="s1"):
    return client.post(f"/api/plugins/video-producer/projects/{project_id}/shots/{shot_id}/write-prompt", json=body)


def _body(**extra):
    return {"request": "she lifts the lantern", "preset_id": presets.MINIMAX_H3, **extra}


def test_the_bridge_hands_the_status_and_the_writing_to_the_core_plugin_api(monkeypatch):
    seen = {}

    def status(user_id, llm_id=None):
        seen["status"] = (user_id, llm_id)
        return {"available": False, "code": "no_llm"}

    async def write(user_id, instruction, *, preset_id=None, mode=None, form_data=None, media=(), llm_id=None):
        seen["write"] = (user_id, instruction, preset_id, mode, form_data, media, llm_id)
        return {"text": "A prompt.", "llm_id": "llm-1"}

    monkeypatch.setattr(core_bridge.api_prompts, "prompt_writer_status", status)
    monkeypatch.setattr(core_bridge.api_prompts, "write_prompt_for_preset", write)

    assert core_bridge.prompt_writer_status("user-1") == {"available": False, "code": "no_llm"}
    written = asyncio.run(
        core_bridge.write_prompt_for_preset("user-1", "Say it.", preset_id="p", mode="refs", form_data={"seed": 1}, media=({"value": "uploads/a.png", "media_type": "image"},))
    )

    assert written == {"text": "A prompt.", "llm_id": "llm-1"}
    assert seen["status"] == ("user-1", None)
    assert seen["write"] == ("user-1", "Say it.", "p", "refs", {"seed": 1}, [{"value": "uploads/a.png", "media_type": "image"}], None)
    assert core_bridge.PromptWriteRefused is core_bridge.api_prompts.PromptWriteRefused
    assert {"PromptWriteRefused", "prompt_writer_status", "write_prompt_for_preset"} <= set(core_bridge.__all__)


def test_the_writer_status_route_tells_the_page_whether_a_model_can_write_and_see(client, monkeypatch):
    writer = Writer(monkeypatch)

    ready = client.get("/api/plugins/video-producer/prompt-writer")
    writer.status = {"available": False, "vision": False, "name": None, "code": "llm_disabled", "message": "The language model Ollama is turned off.", "models": []}
    off = client.get("/api/plugins/video-producer/prompt-writer")
    writer.status = RuntimeError("AppContainer not initialized yet")
    broken = client.get("/api/plugins/video-producer/prompt-writer")

    assert ready.json()["data"] == {"available": True, "vision": True, "name": "Qwen3-VL", "code": None, "message": None}
    assert off.json()["data"] == {"available": False, "vision": False, "name": None, "code": "llm_disabled", "message": "The language model Ollama is turned off."}
    assert broken.status_code == 200
    assert broken.json()["data"]["code"] == "writer_unavailable"
    assert writer.asked == ["user-1", "user-1", "user-1"]


def test_writing_sends_the_request_the_preset_guide_of_the_shot_mode_and_its_two_key_frames(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch)
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert response.json()["data"] == {"text": WRITTEN, "name": "Qwen3-VL", "images": 2, "images_skipped": 0, "images_dropped": 0, "lost_tags": [], "kept_tags": []}
    (call,) = writer.calls
    assert call["user_id"] == "user-1"
    assert (call["preset_id"], call["mode"]) == (presets.MINIMAX_H3, "refs")
    assert call["media"] == [{"value": "uploads/start.png", "media_type": "image"}, {"value": "uploads/end.png", "media_type": "image"}]
    assert isinstance(call["form_data"], dict) and "references" in call["form_data"]
    instruction = call["instruction"]
    assert instruction.startswith("she lifts the lantern\n\n")
    assert "Write in English. The shot lasts 4.0 seconds." in instruction
    assert '"the red-haired woman", "the old fisherman"' in instruction
    assert '"the harbour at dawn"' in instruction
    assert "Image 1 is the shot's first frame and image 2 its last frame" in instruction
    assert 'The shot\'s current prompt, to rewrite as the request says: "The woman waits."' in instruction
    assert core.submitted == []


def test_writing_composes_from_the_unsaved_document_of_the_editor(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch)
    project = make_project(doc=_doc(core, make_doc, frames=()))
    edited = _doc(core, make_doc, mode="FL2VA", frames=("start",), prompt="A new line.")

    response = _write(client, project["id"], _body(doc=edited))

    assert response.status_code == 200
    (call,) = writer.calls
    assert call["mode"] != "refs"
    assert call["media"] == [{"value": "uploads/start.png", "media_type": "image"}]
    assert "The image is the shot's first frame" in call["instruction"]
    assert '"A new line."' in call["instruction"]


def test_a_model_that_cannot_see_writes_from_the_words_alone_and_the_page_is_told(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch, status={**READY, "vision": False})
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.json()["data"]["images"] == 0
    assert response.json()["data"]["images_skipped"] == 2
    assert writer.calls[0]["media"] == []
    assert "Image 1" not in writer.calls[0]["instruction"]


def test_without_a_language_model_nothing_is_asked_and_the_reason_comes_back(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch, status={"available": False, "vision": False, "name": None, "code": "no_llm", "message": "No language model is available to you.", "models": []})
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "no_llm"
    assert writer.calls == []


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (core_bridge.PromptWriteRefused("vision_not_supported", "The language model cannot look at images."), 422, "vision_not_supported"),
        (core_bridge.PromptWriteRefused("blocked", "Refused by a plugin."), 422, "blocked"),
        (ConnectionError("Ollama is not running"), 502, "write_failed"),
    ],
)
def test_a_refusal_or_a_failure_of_the_language_model_comes_back_with_its_code(core, client, make_doc, make_project, monkeypatch, error, status, code):
    core.use_h3()
    Writer(monkeypatch, error=error)
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == status
    assert response.json()["detail"]["error"] == code


def test_a_language_model_past_the_time_limit_is_given_up(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    Writer(monkeypatch, delay=1.0)
    monkeypatch.setattr(prompt_writer, "WRITE_TIMEOUT_S", 0.05)
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 504
    assert response.json()["detail"]["error"] == "write_timeout"


def test_an_empty_reply_is_an_error_and_a_whole_document_keeps_only_the_shot_text(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch, reply={"text": "   "})
    project = make_project(doc=_doc(core, make_doc))

    empty = _write(client, project["id"], _body())
    writer.reply = {
        "text": (
            "subject_definitions: <Subject 1> is the woman in <Picture 1>.\n\n"
            "detailed_description: Cinematic live action. [Shot 1] The red-haired woman (<Subject 1>) lifts her lantern,\n"
            "and the camera pushes in slowly.\n\noverall_soundscape: Waves."
        )
    }
    whole = _write(client, project["id"], _body())

    assert empty.status_code == 502
    assert empty.json()["detail"]["error"] == "empty_reply"
    assert whole.json()["data"]["text"] == "The red-haired woman lifts her lantern,\nand the camera pushes in slowly."


@pytest.mark.parametrize(
    "body",
    [None, [], {"preset_id": presets.MINIMAX_H3}, {"request": "  ", "preset_id": presets.MINIMAX_H3}, {"request": "x" * 1001, "preset_id": presets.MINIMAX_H3}, {"request": "a"}, {"request": "a", "preset_id": "p", "model_id": 3}, {"request": "a", "preset_id": "p", "doc": "x"}],
)
def test_a_malformed_request_is_refused_before_anything_is_asked(core, client, make_doc, make_project, monkeypatch, body):
    core.use_h3()
    writer = Writer(monkeypatch)
    project = make_project(doc=_doc(core, make_doc))

    response = client.post(f"/api/plugins/video-producer/projects/{project['id']}/shots/s1/write-prompt", json=body)

    assert response.status_code == 422
    assert writer.calls == []


def test_an_unknown_shot_or_another_users_project_is_not_found(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch)
    mine = make_project(doc=_doc(core, make_doc))
    theirs = make_project(user_id="user-2", doc=_doc(core, make_doc))

    assert _write(client, mine["id"], _body(), shot_id="nope").status_code == 404
    assert _write(client, theirs["id"], _body()).status_code == 404
    assert writer.calls == []


def test_the_instruction_keeps_the_reference_video_tags_and_leaves_out_what_the_shot_lacks():
    text = prompt_writer.instruction("make it rain", current="She walks past @vref1, then @VREF2 again, then @vref1.", seconds=2.5, characters=[], place=None, images=())
    bare = prompt_writer.instruction("make it rain", current="", seconds=2.5, characters=[], place=None, images=())
    look_alike = prompt_writer.instruction("make it rain", current="Mail me@vref1 or @vref0.", seconds=2.5, characters=[], place=None, images=())

    assert "Keep the tags @vref1, @vref2 exactly as they are written" in text
    assert "@vref" not in bare
    assert "Keep the tags" not in look_alike
    assert "current prompt" not in bare
    assert "Name each character" not in bare
    assert "takes place" not in bare
    assert "Image 1" not in bare
    assert "The shot lasts 2.5 seconds." in bare


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("The fisherman lights his lantern.", "The fisherman lights his lantern."),
        ("[Shot 1] The fisherman lights his lantern.", "The fisherman lights his lantern."),
        ("integrated_multimodal_description: [Shot 1] Cinematic. The fisherman (<Subject 2>) waits.\noverall_soundscape: Rain.", "Cinematic. The fisherman waits."),
        ("  The   fisherman\twaits.  ", "The fisherman waits."),
        (None, ""),
    ],
)
def test_the_reply_is_cut_to_the_text_of_the_shot(reply, kept):
    assert prompt_writer.cleaned(reply, ["the fisherman"]) == kept


def _prompts(client, project_id, body):
    return client.post(f"/api/plugins/video-producer/projects/{project_id}/prompts", json=body)


def test_the_prompts_route_says_which_card_words_a_shot_uses_only_when_a_card_picture_goes_with_it(core, client, make_doc, make_project):
    core.use_h3()
    project = make_project(doc=_doc(core, make_doc))
    body = {"shots": ["s1"], "preset_id": presets.MINIMAX_H3}

    project_words = _prompts(client, project["id"], body)
    labelled = _prompts(client, project["id"], {**body, "doc": _doc(core, make_doc, card_words="label")})
    shot_wins = _prompts(client, project["id"], {**body, "doc": _doc(core, make_doc, card_words="label", shot_words="picture")})
    fl2va = _prompts(client, project["id"], {**body, "doc": _doc(core, make_doc, mode="FL2VA", shot_words="picture")})
    unpictured = _prompts(client, project["id"], {**body, "doc": _doc(core, make_doc, shot_words="picture", pictured=False)})

    assert project_words.json()["data"]["prompts"][0]["card_words"] == "card"
    assert labelled.json()["data"]["prompts"][0]["card_words"] == "label"
    (shot,) = shot_wins.json()["data"]["prompts"]
    assert shot["card_words"] == "picture"
    assert "<Subject 1> is the character shown in <Picture 1>. " in shot["prompt"]
    assert fl2va.json()["data"]["prompts"][0]["card_words"] is None
    assert unpictured.json()["data"]["prompts"][0]["card_words"] is None


def test_a_shot_without_card_words_still_follows_the_project_as_before(core, make_doc):
    core.use_h3()
    doc = _doc(core, make_doc, card_words="label")
    plans = director.build_plans(core.users["user-1"], doc, ["s1"], presets.MINIMAX_H3, "draft")
    (plan,) = plans.shots

    assert plan.reference.card_words == "label"
    assert "card_words" not in plan.reference.summary()
    assert bible.card_words(doc, doc["clips"][0]) == "label"


@pytest.mark.parametrize(
    ("reply", "lost"),
    [
        ("The fisherman walks past @vref1 and stops by @vref2.", []),
        ("The fisherman walks past @VREF1 and stops.", ["@vref2"]),
        ("The fisherman walks along the quay.", ["@vref1", "@vref2"]),
    ],
)
def test_the_page_is_told_which_reference_video_tags_the_proposal_dropped(core, client, make_doc, make_project, monkeypatch, reply, lost):
    core.use_h3()
    writer = Writer(monkeypatch, reply={"text": reply})
    project = make_project(doc=_doc(core, make_doc, prompt="The woman walks past @vref1, then waits for @vref2."))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert response.json()["data"]["lost_tags"] == lost
    assert "Keep the tags @vref1, @vref2 exactly as they are written" in writer.calls[0]["instruction"]


def test_the_project_the_document_and_the_status_are_read_off_the_event_loop(core, client, make_doc, make_project, monkeypatch):
    from backend import access, projects

    core.use_h3()
    writer = Writer(monkeypatch)
    project = make_project(doc=_doc(core, make_doc))
    seen = {}
    reach, check = access.project_for, projects.validate_doc

    def project_for(user, project_id):
        seen["project"] = _on_loop()
        return reach(user, project_id)

    def validate_doc(doc):
        seen["doc"] = _on_loop()
        return check(doc)

    monkeypatch.setattr(access, "project_for", project_for)
    monkeypatch.setattr(projects, "validate_doc", validate_doc)

    response = _write(client, project["id"], _body(doc=_doc(core, make_doc)))

    assert response.status_code == 200
    assert seen == {"project": False, "doc": False}
    assert writer.status_on_loop is False


def _shot(core, make_doc):
    doc = _doc(core, make_doc)
    return doc, doc["clips"][0]


def _error(raised):
    return raised.value.status_code, raised.value.detail["error"]


def test_one_user_writes_one_prompt_at_a_time_and_another_user_is_not_held(core, make_doc, monkeypatch):
    from fastapi import HTTPException

    core.use_h3()
    writer = Writer(monkeypatch, delay=0.4)
    doc, clip = _shot(core, make_doc)
    one, two = core.users["user-1"], core.users["user-2"]

    async def scenario():
        first = asyncio.ensure_future(prompt_writer.write(one, one, doc, clip, "a", presets.MINIMAX_H3, None, ""))
        await asyncio.sleep(0.1)
        with pytest.raises(HTTPException) as busy:
            await prompt_writer.write(one, one, doc, clip, "b", presets.MINIMAX_H3, None, "")
        other = await prompt_writer.write(two, two, doc, clip, "c", presets.MINIMAX_H3, None, "")
        done = await first
        again = await prompt_writer.write(one, one, doc, clip, "d", presets.MINIMAX_H3, None, "")
        return busy, other, done, again

    busy, other, done, again = asyncio.run(scenario())

    assert _error(busy) == (409, "write_busy")
    assert [other["text"], done["text"], again["text"]] == [WRITTEN, WRITTEN, WRITTEN]
    assert [call["instruction"][0] for call in writer.calls] == ["a", "c", "d"]
    assert prompt_writer.writing == set()


def test_a_page_that_stops_waiting_stops_the_language_model_call_and_frees_the_user(core, make_doc, monkeypatch):
    from fastapi import HTTPException

    core.use_h3()
    writer = Writer(monkeypatch, delay=30.0)
    monkeypatch.setattr(prompt_writer, "POLL_S", 0.02)
    doc, clip = _shot(core, make_doc)
    user = core.users["user-1"]
    asks = []

    async def gone():
        asks.append(True)
        return len(asks) >= 3

    async def scenario():
        with pytest.raises(HTTPException) as left:
            await asyncio.wait_for(prompt_writer.write(user, user, doc, clip, "a", presets.MINIMAX_H3, None, "", gone=gone), 5)
        return left

    left = asyncio.run(scenario())

    assert _error(left) == (409, "write_cancelled")
    assert writer.cancelled == ["user-1"]
    assert prompt_writer.writing == set()
    writer.delay = 0
    assert asyncio.run(prompt_writer.write(user, user, doc, clip, "b", presets.MINIMAX_H3, None, ""))["text"] == WRITTEN


def test_a_writing_past_the_time_limit_stops_the_language_model_call(core, make_doc, monkeypatch):
    from fastapi import HTTPException

    core.use_h3()
    writer = Writer(monkeypatch, delay=30.0)
    monkeypatch.setattr(prompt_writer, "WRITE_TIMEOUT_S", 0.1)
    monkeypatch.setattr(prompt_writer, "POLL_S", 0.02)
    doc, clip = _shot(core, make_doc)
    user = core.users["user-1"]

    with pytest.raises(HTTPException) as late:
        asyncio.run(asyncio.wait_for(prompt_writer.write(user, user, doc, clip, "a", presets.MINIMAX_H3, None, ""), 5))

    assert _error(late) == (504, "write_timeout")
    assert writer.cancelled == ["user-1"]
    assert prompt_writer.writing == set()


def _noise_png(path, width=1800, height=1200):
    import os

    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes("RGB", (width, height), os.urandom(width * height * 3)).save(path, "PNG")
    return path


def test_a_key_frame_over_five_megabytes_goes_shrunk_and_the_work_copy_is_removed(core, client, make_doc, make_project, monkeypatch, export_storage):
    from PIL import Image

    core.use_h3()
    writer = Writer(monkeypatch)
    writer.root = export_storage
    big = _noise_png(export_storage / "uploads" / "start.png")
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    assert big.stat().st_size > prompt_writer.MAX_IMAGE_BYTES
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert response.json()["data"]["images"] == 2
    assert response.json()["data"]["images_dropped"] == 0
    (call,) = writer.calls
    shrunk, kept = call["media"]
    assert shrunk["value"].startswith("video_producer/writer/user-1/") and shrunk["value"].endswith(".jpg")
    assert kept == {"value": "uploads/end.png", "media_type": "image"}
    assert writer.sizes[0][0] < prompt_writer.MAX_IMAGE_BYTES
    assert not (export_storage / shrunk["value"]).exists()
    assert big.exists()
    with Image.open(big) as image:
        assert image.size == (1800, 1200)


def test_a_key_frame_too_large_that_cannot_be_read_is_left_out_and_the_page_is_told(core, client, make_doc, make_project, monkeypatch, export_storage):
    import os

    core.use_h3()
    writer = Writer(monkeypatch)
    broken = export_storage / "uploads" / "start.png"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(os.urandom(prompt_writer.MAX_IMAGE_BYTES + 10))
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert response.json()["data"]["images"] == 1
    assert response.json()["data"]["images_dropped"] == 1
    assert writer.calls[0]["media"] == [{"value": "uploads/end.png", "media_type": "image"}]
    assert "The image is the shot's last frame" in writer.calls[0]["instruction"]


def test_a_shot_with_only_its_last_frame_is_described_toward_it(core, client, make_doc, make_project, monkeypatch):
    core.use_h3()
    writer = Writer(monkeypatch)
    project = make_project(doc=_doc(core, make_doc, frames=("end",)))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert writer.calls[0]["media"] == [{"value": "uploads/end.png", "media_type": "image"}]
    assert "The image is the shot's last frame: describe the motion that leads to it" in writer.calls[0]["instruction"]
    assert "first frame" not in writer.calls[0]["instruction"]


def test_a_current_prompt_longer_than_the_old_cut_goes_whole_when_the_instruction_has_room():
    current = " ".join(["The old fisherman walks slowly along the wet stone quay toward the lighthouse."] * 30)

    text = prompt_writer.instruction("make it rain", current=current, seconds=4.0, characters=["the old fisherman"], place="the quay", images=("first",))

    assert len(current) > 1500
    assert f'The shot\'s current prompt, to rewrite as the request says: "{current}"' in text
    assert prompt_writer.CUT not in text
    assert len(text) <= prompt_writer.MAX_INSTRUCTION_CHARS


def test_the_instruction_stays_within_the_core_limit_and_says_where_the_current_prompt_is_cut():
    current = "She walks past @vref1. " + " ".join(f"word{index}" for index in range(2000))
    labels = [f"character number {index} " + "x" * 300 for index in range(30)]

    text = prompt_writer.instruction("r" * 1000, current=current, seconds=4.0, characters=labels, place="p" * 500, images=("first", "last"))

    assert len(text) <= prompt_writer.MAX_INSTRUCTION_CHARS
    assert text.startswith("r" * 1000 + "\n\n")
    assert "Keep the tags @vref1 exactly as they are written" in text
    assert text.endswith("\n" + prompt_writer.CUT)
    quoted = text.split("rewrite as the request says: \"", 1)[1].split("\"\n", 1)[0]
    assert quoted.endswith("…")
    assert current.startswith(quoted[:-1])
    assert quoted[-2] != " " and quoted[:-1].split(" ")[-1].startswith("word")
    assert text.count('"character number') == prompt_writer.MAX_LABELS
    assert '"' + "p" * prompt_writer.MAX_LABEL_CHARS + '"' in text


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("Here is the prompt:\n```\nThe fisherman lights his lantern.\n```", "The fisherman lights his lantern."),
        ("Sure, here it is:\n```text\nThe fisherman lights his lantern.\n```\nHope it helps!", "The fisherman lights his lantern."),
        ("Here is the shot prompt:\n\nThe fisherman lights his lantern.", "The fisherman lights his lantern."),
        ("The fisherman <Subject 1> lifts the lantern from <Picture 2> , then waits.", "The fisherman <Subject 1> lifts the lantern from <Picture 2>, then waits."),
        ("At dusk the fisherman waits: the rain starts.", "At dusk the fisherman waits: the rain starts."),
    ],
)
def test_a_preamble_a_fenced_block_and_bare_subject_or_picture_tags_are_cleaned(reply, kept):
    assert prompt_writer.cleaned(reply) == kept


def test_a_reply_too_long_is_cut_at_its_last_whole_sentence_or_at_a_word():
    sentences = " ".join(f"The fisherman takes step number {index}." for index in range(200))
    words = " ".join(f"step{index}" for index in range(600))

    by_sentence = prompt_writer.cleaned(sentences)
    by_word = prompt_writer.cleaned(words)

    assert len(by_sentence) <= prompt_writer.MAX_WRITTEN_CHARS
    assert by_sentence.endswith(".") and sentences.startswith(by_sentence)
    assert len(by_word) <= prompt_writer.MAX_WRITTEN_CHARS
    assert by_word.endswith("\u2026") and words.startswith(by_word[:-1]) and by_word[:-1].split(" ")[-1] in words.split(" ")
    assert prompt_writer.cleaned("A short one.") == "A short one."


@pytest.mark.parametrize(
    ("reply", "kept", "tags"),
    [
        ("The red-haired woman (<Subject 1>) lifts her lantern.", "The red-haired woman lifts her lantern.", []),
        ("The old  fisherman ( <Subject 2> ) waits by the harbour at dawn (<Picture 1>).", "The old fisherman waits by the harbour at dawn.", []),
        ("She looks at the lighthouse shown in (<Picture 2>).", "She looks at the lighthouse shown in (<Picture 2>).", ["<Picture 2>"]),
        ("A woman (<Subject 1>) waves at the fisherman (<Subject 2>).", "A woman (<Subject 1>) waves at the fisherman (<Subject 2>).", ["<Subject 1>", "<Subject 2>"]),
        ("Another red-haired woman's dog (<Subject 1>) barks.", "Another red-haired woman's dog (<Subject 1>) barks.", ["<Subject 1>"]),
    ],
)
def test_a_tag_in_parentheses_goes_only_right_after_a_cast_label_and_any_other_is_kept_and_listed(reply, kept, tags):
    labels = [WOMAN["label"], FISHER["label"], HARBOUR["label"]]

    written = prompt_writer.cleaned(reply, labels)

    assert written == kept
    assert prompt_writer.kept_tags(written) == tags


def test_tags_in_angle_brackets_are_kept_as_written_and_listed_in_order():
    written = prompt_writer.cleaned("<Subject 2> walks toward <Subject 1> while <Audio 1> plays, then <Subject 2> stops.")

    assert written == "<Subject 2> walks toward <Subject 1> while <Audio 1> plays, then <Subject 2> stops."
    assert prompt_writer.kept_tags(written) == ["<Subject 2>", "<Subject 1>", "<Audio 1>"]
    assert prompt_writer.kept_tags("The old fisherman waits.") == []


@pytest.mark.parametrize(
    ("mode", "reply"),
    [
        ("Ref2VA", "<Subject 1> lifts his lantern while <Subject 2> watches from the boat."),
        ("Ref2VA", "<Subject 2> lifts his lantern on <Picture 1>."),
        ("FL2VA", "<Subject 3> walks toward <Subject 1> along the harbour."),
    ],
)
def test_a_reply_numbered_its_own_way_is_never_renamed_and_its_tags_are_listed(core, client, make_doc, make_project, monkeypatch, mode, reply):
    core.use_h3()
    writer = Writer(monkeypatch, reply={"text": reply})
    project = make_project(doc=_doc(core, make_doc, mode=mode))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["text"] == reply
    assert data["kept_tags"] == prompt_writer.kept_tags(reply)
    assert data["kept_tags"]
    for label in ("the red-haired woman", "the old fisherman", "the harbour at dawn"):
        assert label not in data["text"]
    assert "write no tag in angle brackets at all" in writer.calls[0]["instruction"]
    assert "Name every character and place by its label" in writer.calls[0]["instruction"]


def _writer_area(root):
    area = root / "video_producer" / "writer" / "user-1"
    return [path for path in area.rglob("*")] if area.exists() else []


def test_a_writing_cancelled_while_its_frame_is_shrunk_leaves_no_work_folder(core, make_doc, monkeypatch, export_storage):
    import threading

    core.use_h3()
    writer = Writer(monkeypatch)
    _noise_png(export_storage / "uploads" / "start.png")
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    started, release = threading.Event(), threading.Event()
    shrink = prompt_writer._shrunk

    def slow(source, target):
        started.set()
        release.wait(5)
        shrink(source, target)

    monkeypatch.setattr(prompt_writer, "_shrunk", slow)
    doc, clip = _shot(core, make_doc)
    user = core.users["user-1"]

    async def scenario():
        task = asyncio.ensure_future(prompt_writer.write(user, user, doc, clip, "a", presets.MINIMAX_H3, None, ""))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if not _writer_area(export_storage):
                break

    asyncio.run(scenario())

    assert started.is_set()
    assert _writer_area(export_storage) == []
    assert writer.calls == []
    assert prompt_writer.writing == set()


def test_a_core_call_that_outlives_the_grace_keeps_its_frame_until_it_ends(core, make_doc, monkeypatch, export_storage):
    from fastapi import HTTPException

    core.use_h3()
    _noise_png(export_storage / "uploads" / "start.png")
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    monkeypatch.setattr(prompt_writer, "POLL_S", 0.02)
    monkeypatch.setattr(prompt_writer, "GRACE_S", 0.05)
    seen = {}

    async def stubborn(user_id, instruction, *, preset_id=None, mode=None, form_data=None, media=()):
        shrunk = export_storage / media[0]["value"]
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            await asyncio.sleep(0.4)
            seen["frame_at_end"] = shrunk.exists()
        return {"text": WRITTEN}

    monkeypatch.setattr(core_bridge, "prompt_writer_status", lambda user_id: dict(READY))
    monkeypatch.setattr(core_bridge, "write_prompt_for_preset", stubborn)
    doc, clip = _shot(core, make_doc)
    user = core.users["user-1"]
    asks = []

    async def gone():
        asks.append(True)
        return len(asks) >= 2

    async def scenario():
        with pytest.raises(HTTPException) as left:
            await prompt_writer.write(user, user, doc, clip, "a", presets.MINIMAX_H3, None, "", gone=gone)
        during = _writer_area(export_storage)
        await asyncio.sleep(1.0)
        return left, during

    left, during = asyncio.run(scenario())

    assert left.value.detail["error"] == "write_cancelled"
    assert during != []
    assert seen == {"frame_at_end": True}
    assert _writer_area(export_storage) == []


@pytest.mark.parametrize("value", ["../secret.png", "uploads/../../secret.png", "/etc/secret.png", "", None])
def test_a_key_frame_whose_path_leaves_the_file_storage_is_never_opened_and_is_left_out(core, monkeypatch, export_storage, value):
    (export_storage.parent / "secret.png").write_bytes(b"x" * (prompt_writer.MAX_IMAGE_BYTES + 1))
    opened = []
    monkeypatch.setattr(prompt_writer, "_shrunk", lambda source, target: opened.append(source))
    user = core.users["user-1"]

    sent, dropped = prompt_writer.fitted(user, [{"value": value, "media_type": "image", "role": "first"}], export_storage / "work")

    assert (sent, dropped) == ([], 1)
    assert opened == []


@pytest.mark.parametrize("broken", ["corrupt", "truncated_jpeg", "missing", "not_an_image"])
def test_a_small_key_frame_that_is_missing_or_cannot_be_read_is_left_out_and_the_writing_goes_on(core, client, make_doc, make_project, monkeypatch, export_storage, broken):
    core.use_h3()
    writer = Writer(monkeypatch)
    start = export_storage / "uploads" / "start.png"
    _noise_png(start, 64, 36)
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    if broken == "corrupt":
        start.write_bytes(start.read_bytes()[:200])
    elif broken == "truncated_jpeg":
        import io
        import os

        from PIL import Image

        encoded = io.BytesIO()
        Image.frombytes("RGB", (64, 36), os.urandom(64 * 36 * 3)).save(encoded, "JPEG", quality=95)
        whole = encoded.getvalue()
        start.write_bytes(whole[: len(whole) * 2 // 3])
        with Image.open(start) as header:
            header.verify()
    elif broken == "missing":
        start.unlink()
    else:
        start.write_bytes(b"plain text, no picture")
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.status_code == 200
    assert response.json()["data"]["images"] == 1
    assert response.json()["data"]["images_dropped"] == 1
    assert writer.calls[0]["media"] == [{"value": "uploads/end.png", "media_type": "image"}]
    assert "The image is the shot's last frame" in writer.calls[0]["instruction"]


def test_small_readable_key_frames_go_as_they_are(core, client, make_doc, make_project, monkeypatch, export_storage):
    core.use_h3()
    writer = Writer(monkeypatch)
    _noise_png(export_storage / "uploads" / "start.png", 64, 36)
    _noise_png(export_storage / "uploads" / "end.png", 64, 36)
    project = make_project(doc=_doc(core, make_doc))

    response = _write(client, project["id"], _body())

    assert response.json()["data"]["images_dropped"] == 0
    assert writer.calls[0]["media"] == [{"value": "uploads/start.png", "media_type": "image"}, {"value": "uploads/end.png", "media_type": "image"}]


def test_a_large_transparent_frame_is_shrunk_on_a_white_ground(core, monkeypatch, export_storage):
    import os

    from PIL import Image

    width, height = 1800, 1200
    picture = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3)).convert("RGBA")
    alpha = Image.new("L", (width, height), 255)
    alpha.paste(0, (0, 0, 300, 300))
    picture.putalpha(alpha)
    source = export_storage / "uploads" / "clear.png"
    source.parent.mkdir(parents=True)
    picture.save(source, "PNG")
    assert source.stat().st_size > prompt_writer.MAX_IMAGE_BYTES
    user = core.users["user-1"]

    sent, dropped = prompt_writer.fitted(user, [{"value": "uploads/clear.png", "media_type": "image", "role": "first"}], export_storage / "work")

    assert dropped == 0
    with Image.open(export_storage / sent[0]["value"]) as shrunk:
        assert shrunk.mode == "RGB"
        assert max(shrunk.size) == prompt_writer.IMAGE_EDGE
        red, green, blue = shrunk.getpixel((20, 20))
        assert min(red, green, blue) >= 240


def test_a_frame_past_the_pixel_bound_is_left_out_without_being_decoded(core, monkeypatch, export_storage):
    from PIL import Image

    _noise_png(export_storage / "uploads" / "start.png")
    monkeypatch.setattr(prompt_writer, "MAX_PIXELS", 1_000_000)
    loads = []
    load = Image.Image.load
    monkeypatch.setattr(Image.Image, "load", lambda self, *args: loads.append(self.size) or load(self, *args))
    user = core.users["user-1"]

    sent, dropped = prompt_writer.fitted(user, [{"value": "uploads/start.png", "media_type": "image", "role": "first"}], export_storage / "work")

    assert (sent, dropped) == ([], 1)
    assert loads == []


def test_a_small_frame_past_the_pixel_bound_is_left_out_without_being_decoded(core, monkeypatch, export_storage):
    from PIL import Image, ImageFile

    width, height = 8000, 6000
    assert width * height > prompt_writer.MAX_PIXELS
    source = export_storage / "uploads" / "flat.png"
    source.parent.mkdir(parents=True)
    Image.new("1", (width, height)).save(source, "PNG")
    assert source.stat().st_size <= prompt_writer.MAX_IMAGE_BYTES
    loads = []
    image_load = Image.Image.load
    file_load = ImageFile.ImageFile.load
    monkeypatch.setattr(Image.Image, "load", lambda self, *args: loads.append(self.size) or image_load(self, *args))
    monkeypatch.setattr(ImageFile.ImageFile, "load", lambda self, *args: loads.append(self.size) or file_load(self, *args))
    user = core.users["user-1"]

    sent, dropped = prompt_writer.fitted(user, [{"value": "uploads/flat.png", "media_type": "image", "role": "first"}], export_storage / "work")

    assert (sent, dropped) == ([], 1)
    assert loads == []


def test_a_large_sixteen_bit_frame_is_shrunk_with_its_tones_scaled_not_clipped(core, monkeypatch, export_storage):
    import os

    from PIL import Image, ImageStat

    width, height = 2000, 1500
    source = export_storage / "uploads" / "deep.png"
    source.parent.mkdir(parents=True)
    Image.frombytes("I;16", (width, height), os.urandom(width * height * 2)).save(source, "PNG")
    assert source.stat().st_size > prompt_writer.MAX_IMAGE_BYTES
    user = core.users["user-1"]

    sent, dropped = prompt_writer.fitted(user, [{"value": "uploads/deep.png", "media_type": "image", "role": "first"}], export_storage / "work")

    assert dropped == 0
    with Image.open(export_storage / sent[0]["value"]) as shrunk:
        assert shrunk.mode == "RGB"
        assert max(shrunk.size) == prompt_writer.IMAGE_EDGE
        assert 100 < ImageStat.Stat(shrunk).mean[0] < 155


def test_a_large_jpeg_frame_is_decoded_reduced(tmp_path, monkeypatch):
    import os

    from PIL import Image, JpegImagePlugin

    source = tmp_path / "big.jpg"
    Image.frombytes("RGB", (3000, 2000), os.urandom(3000 * 2000 * 3)).save(source, "JPEG", quality=95)
    asked = []
    draft = JpegImagePlugin.JpegImageFile.draft
    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", lambda self, mode, size: asked.append((mode, size)) or draft(self, mode, size))

    prompt_writer._shrunk(source, tmp_path / "small.jpg")

    assert asked and asked[0] == ("RGB", (prompt_writer.IMAGE_EDGE, prompt_writer.IMAGE_EDGE))
    with Image.open(tmp_path / "small.jpg") as small:
        assert max(small.size) == prompt_writer.IMAGE_EDGE


@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        ("The camera holds on the quay:\nthe fisherman lights his lantern.", "The camera holds on the quay:\nthe fisherman lights his lantern."),
        ("Here we see the quay:\nthe fisherman waits.", "Here we see the quay:\nthe fisherman waits."),
        ("At dusk:\nthe fisherman waits.", "At dusk:\nthe fisherman waits."),
        ("Below is the rewritten prompt:\nThe fisherman waits.", "The fisherman waits."),
        ("Sure! Here's the shot prompt for you:\n\nThe fisherman waits.", "The fisherman waits."),
        ("Revised prompt:\nThe fisherman waits.", "The fisherman waits."),
    ],
)
def test_only_a_real_introduction_line_is_taken_for_a_preamble(reply, kept):
    assert prompt_writer.cleaned(reply) == kept


def test_the_route_refuses_a_second_writing_of_the_same_user_while_the_first_runs(core, client, make_doc, make_project, monkeypatch):
    import threading
    import time

    core.use_h3()
    writer = Writer(monkeypatch, delay=1.0)
    project = make_project(doc=_doc(core, make_doc))
    answers = {}

    def first():
        answers["first"] = _write(client, project["id"], _body())

    running = threading.Thread(target=first)
    running.start()
    for _ in range(200):
        if writer.calls:
            break
        time.sleep(0.01)
    second = _write(client, project["id"], _body(request="another"))
    running.join(10)

    assert second.status_code == 409
    assert second.json()["detail"]["error"] == "write_busy"
    assert answers["first"].status_code == 200
    assert [call["instruction"].split("\n", 1)[0] for call in writer.calls] == ["she lifts the lantern"]
    assert _write(client, project["id"], _body()).status_code == 200


def test_the_route_stops_the_language_model_call_when_its_request_disconnects(core, make_doc, make_project, monkeypatch):
    from fastapi import HTTPException

    from backend import routes_prompts

    core.use_h3()
    writer = Writer(monkeypatch, delay=30.0)
    monkeypatch.setattr(prompt_writer, "POLL_S", 0.02)
    project = make_project(doc=_doc(core, make_doc))
    asks = []

    class Leaving:
        async def is_disconnected(self):
            asks.append(True)
            return len(asks) >= 3

    async def call():
        return await routes_prompts.write_prompt(project["id"], "s1", Leaving(), body=_body(), user=core.users["user-1"])

    with pytest.raises(HTTPException) as left:
        asyncio.run(asyncio.wait_for(call(), 10))

    assert (left.value.status_code, left.value.detail["error"]) == (409, "write_cancelled")
    assert writer.cancelled == ["user-1"]
    assert prompt_writer.writing == set()
