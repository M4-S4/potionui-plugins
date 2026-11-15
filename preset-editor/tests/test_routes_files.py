from pathlib import Path

import asyncio
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import drafts, files, paths, routes_files
from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user
from tests.test_scaffold import FAMILY

DRAFTS_URL = "/api/plugins/preset-editor/drafts"
ADMIN = User(id="admin-1", username="admin", email="admin@test.com", password_hash="x", account_type=AccountType.ADMIN)


@pytest.fixture
def client(core):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_user] = lambda: ADMIN
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def draft(client):
    body = {"mode": "copy", "from_id": "fixture-minimal-native", "name": "My copy", "model_dir": "MyModel", "variant_dir": "v1"}
    return client.post(DRAFTS_URL, json=body).json()["data"]


def _file_url(draft, path):
    return f"{DRAFTS_URL}/{draft['draft_id']}/files/{path}"


def test_a_text_file_is_read_with_its_etag(client, draft, roots):
    response = client.get(_file_url(draft, "modes/txt2img/form.yml"))

    assert response.status_code == 200
    data = response.json()["data"]
    expected = (drafts.load(roots, draft["draft_id"]).dir / "modes" / "txt2img" / "form.yml").read_bytes()
    assert (data["path"], data["content"], data["etag"], data["size"]) == ("modes/txt2img/form.yml", expected.decode(), files.etag_of(expected), len(expected))


def test_writing_needs_the_etag_and_returns_the_next_one_with_a_lint(client, draft, core, roots):
    current = client.get(_file_url(draft, "preset.yml")).json()["data"]

    refused = client.put(_file_url(draft, "preset.yml"), json={"content": "schema: 1\n"})
    assert refused.status_code == 428
    assert refused.json()["detail"]["etag"] == current["etag"]

    written = client.put(_file_url(draft, "preset.yml"), json={"content": current["content"] + "tags: [x]\n"}, headers={"If-Match": current["etag"]})
    assert written.status_code == 200, written.text
    data = written.json()["data"]
    assert data["etag"] != current["etag"] and data["lint"] == {"errors": [], "warnings": ["[WARNING] preset.yml: no tests.yml"]}
    assert core.lint_calls[-1] == drafts.load(roots, draft["draft_id"]).dir

    stale = client.put(_file_url(draft, "preset.yml"), json={"content": "other\n"}, headers={"If-Match": current["etag"]})
    assert stale.status_code == 412
    assert stale.json()["detail"]["etag"] == data["etag"]
    assert stale.json()["detail"]["content"].endswith("tags: [x]\n")


def test_a_new_file_is_created_without_an_etag(client, draft):
    response = client.put(_file_url(draft, "modes/txt2img/tabs/extra.yml"), json={"content": "fields: []\n"})

    assert response.status_code == 200, response.text
    assert client.get(_file_url(draft, "modes/txt2img/tabs/extra.yml")).json()["data"]["content"] == "fields: []\n"


@pytest.mark.parametrize("path, status, code", [("modes\\x.yml", 400, "invalid_path"), ("public/cover.png", 400, "not_text"), ("modes/nope.yml", 404, "not_found")])
def test_bad_reads_are_refused(client, draft, path, status, code):
    response = client.get(_file_url(draft, path))

    assert response.status_code == status and response.json()["detail"]["error"] == code


def test_deleting_a_file_updates_the_tree_and_never_touches_the_manifest(client, draft):
    assert client.put(_file_url(draft, "modes/txt2img/tabs/extra.yml"), json={"content": "fields: []\n"}).status_code == 200

    response = client.delete(_file_url(draft, "modes/txt2img/tabs/extra.yml"))

    assert response.status_code == 200
    assert "modes/txt2img/tabs/extra.yml" not in [f["path"] for f in response.json()["data"]["files"]]
    assert response.json()["data"]["lint"]["errors"] == []
    assert client.delete(_file_url(draft, "preset.yml")).status_code == 400
    assert client.delete(_file_url(draft, "modes/txt2img/tabs/extra.yml")).status_code == 404


def test_a_pipeline_that_another_mode_takes_is_not_deleted(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    pointer = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "pipeline.yml"
    pointer.write_text("pipeline_from: txt2img\n", encoding="utf-8")
    shared = pointer.parent.parent / "txt2img" / "pipeline.yml"

    refused = client.delete(_file_url(draft, "modes/txt2img/pipeline.yml"))

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["modes/img2img/pipeline.yml"]
    assert refused.json()["detail"]["message"] == (
        "modes/txt2img/pipeline.yml cannot be deleted: modes/img2img/pipeline.yml takes its pipeline from it. Point it elsewhere, or remove that line, first."
    )
    assert shared.is_file()
    pointer.write_text("pipeline: []\n", encoding="utf-8")
    assert client.delete(_file_url(draft, "modes/txt2img/pipeline.yml")).status_code == 200


def test_a_file_that_another_file_loads_is_not_deleted(client, draft, roots):
    tab = drafts.load(roots, draft["draft_id"]).dir / "modes" / "txt2img" / "tabs" / "main.yml"

    refused = client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml"))

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["modes/txt2img/form.yml"]
    assert refused.json()["detail"]["message"] == (
        "modes/txt2img/tabs/main.yml cannot be deleted: modes/txt2img/form.yml loads it. Point it elsewhere, or remove that line, first."
    )
    assert tab.is_file()


def test_a_file_whose_path_only_starts_another_cited_path_is_deleted(client, draft, roots):
    assert client.put(_file_url(draft, "modes/txt2img/tabs/main.y.yml"), json={"content": "fields: []\n"}).status_code == 200
    form = drafts.load(roots, draft["draft_id"]).dir / "modes" / "txt2img" / "form.yml"
    form.write_text(form.read_text(encoding="utf-8") + 'note: "{{ paths.preset }}/modes/txt2img/tabs/main.y.yml.bak"\n', encoding="utf-8")

    assert client.delete(_file_url(draft, "modes/txt2img/tabs/main.y.yml")).status_code == 200


def test_a_mode_is_added_from_the_skeleton_and_removed_with_its_folder(client, draft, roots):
    added = client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})

    assert added.status_code == 201, added.text
    data = added.json()["data"]
    assert data["modes"] == ["txt2img", "img2img"]
    assert "modes/img2img/tabs/main.yml" in [f["path"] for f in data["files"]]
    manifest = drafts.load(roots, draft["draft_id"]).dir / "preset.yml"
    assert files.manifest_modes(manifest.read_text(encoding="utf-8")) == ["txt2img", "img2img"]
    assert client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"}).status_code == 409
    assert client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "Bad Name"}).status_code == 422

    removed = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img")

    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["modes"] == ["txt2img"]
    assert not (manifest.parent / "modes" / "img2img").exists()
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img").status_code == 409
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/nope").status_code == 404


def test_a_mode_whose_files_another_mode_loads_is_kept(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    form = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "form.yml"
    form.write_text(form.read_text(encoding="utf-8").replace("modes/img2img/tabs/main.yml", "modes/txt2img/tabs/main.yml"), encoding="utf-8")

    refused = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img")

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["modes/img2img/form.yml"]
    assert refused.json()["detail"]["message"] == (
        "The mode txt2img cannot be removed: modes/img2img/form.yml loads one of its files. Point it elsewhere, or remove that line, first."
    )
    assert (form.parent.parent / "txt2img" / "tabs" / "main.yml").is_file()
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img").status_code == 200


def test_a_mode_whose_pipeline_another_mode_takes_is_kept(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    pointer = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "pipeline.yml"
    pointer.write_text("pipeline_from: txt2img\n", encoding="utf-8")

    refused = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img")

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["modes/img2img/pipeline.yml"]
    assert refused.json()["detail"]["message"] == (
        "The mode txt2img cannot be removed: modes/img2img/pipeline.yml takes its pipeline from it. Point it elsewhere, or remove that line, first."
    )
    assert (pointer.parent.parent / "txt2img" / "pipeline.yml").is_file()
    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img").status_code == 200


def test_a_pipeline_that_only_mentions_pipeline_from_does_not_keep_a_mode(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    other = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "pipeline.yml"
    other.write_text("pipeline_from: img2img_other\n", encoding="utf-8")
    (other.parent / "tabs" / "main.yml").write_text("# pipeline_from: txt2img\nfields: []\n", encoding="utf-8")

    assert client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img").status_code == 200


def test_a_family_mode_is_added_with_the_family_tabs(client, draft):
    body = {"mode": "img2img", "family": {**FAMILY.__dict__, "model_slots": list(FAMILY.model_slots), "sampler_choices": list(FAMILY.sampler_choices)}}

    response = client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json=body)

    assert response.status_code == 201, response.text
    assert "modes/img2img/tabs/lora.yml" in [f["path"] for f in response.json()["data"]["files"]]


def test_a_blank_native_draft_is_scaffolded(client, roots):
    body = {"mode": "blank", "name": "Fresh", "model_dir": "Fresh", "variant_dir": "v1", "modes": ["txt2img", "img2img"]}

    response = client.post(DRAFTS_URL, json=body)

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["source"] == "blank" and paths.DRAFT_ID_RE.match(data["preset_id"])
    assert [f["path"] for f in data["files"]] == [
        "description.md", "modes/img2img/form.yml", "modes/img2img/pipeline.yml", "modes/img2img/tabs/main.yml",
        "modes/txt2img/form.yml", "modes/txt2img/pipeline.yml", "modes/txt2img/tabs/main.yml", "preset.yml",
    ]
    header = drafts.read_header(drafts.load(roots, data["draft_id"]).dir)
    assert (header["id"], header["name"], header["engine"], header["category"], header["modes"]) == (data["preset_id"], "Fresh", "native", "image", ["txt2img", "img2img"])


def test_a_blank_cloud_draft_needs_a_driver_and_known_modes(client):
    base = {"mode": "blank", "name": "Cloud", "model_dir": "Cloud", "engine": "cloud", "modes": ["txt2video"]}

    assert client.post(DRAFTS_URL, json=base).status_code == 422
    assert client.post(DRAFTS_URL, json={**base, "driver": "cloud.openrouter", "modes": ["nope"]}).status_code == 422
    assert client.post(DRAFTS_URL, json={**base, "driver": "native.x"}).status_code == 422

    response = client.post(DRAFTS_URL, json={**base, "driver": "cloud.openrouter"})

    assert response.status_code == 201, response.text
    paths_written = [f["path"] for f in response.json()["data"]["files"]]
    assert paths_written == ["description.md", "modes/txt2video/form.yml", "modes/txt2video/pipeline.yml", "preset.yml"]


def test_a_blank_family_draft_gets_the_family_tabs(client):
    family = {**FAMILY.__dict__, "model_slots": list(FAMILY.model_slots), "sampler_choices": list(FAMILY.sampler_choices)}
    body = {"mode": "blank", "name": "Z", "model_dir": "ZImage", "modes": ["txt2img"], "family": family}

    response = client.post(DRAFTS_URL, json=body)

    assert response.status_code == 201, response.text
    assert "modes/txt2img/tabs/generation.yml" in [f["path"] for f in response.json()["data"]["files"]]
    assert client.post(DRAFTS_URL, json={**body, "engine": "comfyui"}).status_code == 422


def test_the_shared_reference_lists_the_fragments_and_the_cloud_blocks(client, tmp_path, monkeypatch):
    shared = tmp_path / "_shared"
    (shared / "resolutions").mkdir(parents=True)
    (shared / "resolutions" / "sdxl.yml").write_text("options: []\n", encoding="utf-8")
    (shared / "cloud" / "tabs").mkdir(parents=True)
    (shared / "cloud" / "tabs" / "image.yml").write_text("fields: []\n", encoding="utf-8")
    (shared / "notes.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(paths, "SHARED_DIR", shared)

    data = client.get("/api/plugins/preset-editor/reference/shared").json()["data"]

    assert data["root"] == "{{ paths._shared }}"
    assert data["files"] == ["cloud/tabs/image.yml", "resolutions/sdxl.yml"]
    assert "tabs/image.yml" in data["cloud_blocks"] and "models/txt2img.yml" in data["cloud_blocks"]


def _lint_by_modes(core):
    async def lint_async(path):
        core.lint_calls.append(Path(path))
        manifest = (Path(path) / "preset.yml").read_text(encoding="utf-8")
        listed = "- img2img" in manifest
        where = Path(path).as_posix() if len(core.lint_calls) % 2 else str(Path(path))
        errors = [] if listed or "simple_modes: [img2img]" not in manifest else [
            f"[ERROR] {where}/preset.yml: vars.video_director.simple_modes.img2img: not a mode of this preset"
        ]
        return errors, [f"[WARNING] {where}/preset.yml: no tests.yml", "[WARNING] preset.yml: no cover"]

    return lint_async


def test_the_removal_check_names_the_lint_errors_a_removal_would_add(client, draft, roots, core, monkeypatch):
    from backend import core_bridge

    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    manifest = drafts.load(roots, draft["draft_id"]).dir / "preset.yml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "vars:\n  video_director:\n    simple_modes: [img2img]\n", encoding="utf-8")
    before = manifest.read_bytes()
    monkeypatch.setattr(core_bridge, "lint_async", _lint_by_modes(core))

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img/removal")

    assert check.status_code == 200, check.text
    assert check.json()["data"] == {
        "mode": "img2img",
        "allowed": True,
        "message": "",
        "citing": [],
        "pointers": [],
        "loaders": [],
        "errors": ["[ERROR] preset.yml: vars.video_director.simple_modes.img2img: not a mode of this preset"],
        "warnings": [],
    }
    assert manifest.read_bytes() == before
    assert (manifest.parent / "modes" / "img2img" / "form.yml").is_file()
    assert core.lint_calls[-2] == manifest.parent
    assert core.lint_calls[-1] != manifest.parent
    assert not core.lint_calls[-1].exists()


def test_the_removal_check_of_a_mode_nothing_names_adds_no_error(client, draft, core, monkeypatch):
    from backend import core_bridge

    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    monkeypatch.setattr(core_bridge, "lint_async", _lint_by_modes(core))

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img/removal")

    assert check.json()["data"]["allowed"] is True
    assert check.json()["data"]["errors"] == []


def test_the_removal_check_gives_the_refusal_of_a_cited_mode(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    pointer = drafts.load(roots, draft["draft_id"]).dir / "modes" / "img2img" / "pipeline.yml"
    pointer.write_text("pipeline_from: txt2img\n", encoding="utf-8")

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img/removal")

    assert check.status_code == 200
    assert check.json()["data"]["allowed"] is False
    assert check.json()["data"]["citing"] == ["modes/img2img/pipeline.yml"]
    removal = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/txt2img")
    assert check.json()["data"]["message"] == removal.json()["detail"]["message"]


@pytest.mark.parametrize("mode, status", [("nope", 404), ("txt2img", 409), ("Bad", 400)])
def test_the_removal_check_refuses_what_the_removal_refuses(client, draft, mode, status):
    assert client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/{mode}/removal").status_code == status


DEEP = "[" * 5000 + "]" * 5000


def test_a_file_deletion_runs_off_the_event_loop(client, draft, monkeypatch):
    seen = []
    original = files.delete_file

    def recording(*args):
        try:
            asyncio.get_running_loop()
            seen.append("event loop")
        except RuntimeError:
            seen.append("thread")
        return original(*args)

    monkeypatch.setattr(files, "delete_file", recording)
    assert client.put(_file_url(draft, "modes/txt2img/tabs/extra.yml"), json={"content": "fields: []\n"}).status_code == 200

    assert client.delete(_file_url(draft, "modes/txt2img/tabs/extra.yml")).status_code == 200
    assert seen == ["thread"]


def test_a_yaml_nested_too_deep_never_makes_a_deletion_fail(client, draft, roots):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    folder = drafts.load(roots, draft["draft_id"]).dir
    (folder / "modes" / "img2img" / "pipeline.yml").write_text(f"pipeline_from: txt2img\nnested: {DEEP}\n", encoding="utf-8")
    (folder / "modes" / "img2img" / "form.yml").write_text(f'fields: "{{{{ paths.preset }}}}/modes/txt2img/tabs/main.yml"\nnested: {DEEP}\n', encoding="utf-8")

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/deletion", params={"path": "modes/txt2img/pipeline.yml"})
    tab = client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml"))
    pipeline = client.delete(_file_url(draft, "modes/txt2img/pipeline.yml"))

    assert check.status_code == 200 and check.json()["data"]["allowed"] is True
    assert tab.status_code == 409
    assert set(tab.json()["detail"]["citing"]) == {"modes/img2img/form.yml", "modes/txt2img/form.yml"}
    assert pipeline.status_code == 200


def test_a_yaml_file_over_the_text_budget_is_searched_as_text_up_to_the_budget(client, draft, roots):
    folder = drafts.load(roots, draft["draft_id"]).dir
    big = folder / "files" / "big.yml"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text('a: "{{ paths.preset }}/modes/txt2img/pipeline.yml"\npad: "' + "x" * files.MAX_TEXT_BYTES + '"\n', encoding="utf-8")
    beyond = folder / "files" / "beyond.yml"
    beyond.write_text('pad: "' + "x" * files.MAX_TEXT_BYTES + '"\na: "{{ paths.preset }}/modes/txt2img/pipeline.yml"\n', encoding="utf-8")
    form = folder / "modes" / "txt2img" / "form.yml"
    form.write_text("fields: []\n", encoding="utf-8")

    refused = client.delete(_file_url(draft, "modes/txt2img/pipeline.yml"))

    assert refused.status_code == 409
    assert refused.json()["detail"]["citing"] == ["files/big.yml"]


def test_a_reference_in_a_comment_does_not_keep_a_file(client, draft, roots):
    form = drafts.load(roots, draft["draft_id"]).dir / "modes" / "txt2img" / "form.yml"
    form.write_text('fields: []\n# children: "{{ paths.preset }}/modes/txt2img/tabs/main.yml"\n', encoding="utf-8")

    assert client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml")).status_code == 200


def test_the_deletion_check_says_beforehand_what_the_deletion_answers(client, draft):
    url = f"{DRAFTS_URL}/{draft['draft_id']}/deletion"

    refused = client.get(url, params={"path": "modes/txt2img/tabs/main.yml"})

    assert refused.status_code == 200
    assert refused.json()["data"] == {
        "path": "modes/txt2img/tabs/main.yml",
        "allowed": False,
        "message": "modes/txt2img/tabs/main.yml cannot be deleted: modes/txt2img/form.yml loads it. Point it elsewhere, or remove that line, first.",
        "citing": ["modes/txt2img/form.yml"],
        "pointers": [],
        "loaders": ["modes/txt2img/form.yml"],
    }
    assert client.delete(_file_url(draft, "modes/txt2img/tabs/main.yml")).json()["detail"]["message"] == refused.json()["data"]["message"]
    assert client.get(url, params={"path": "modes/txt2img/form.yml"}).json()["data"]["allowed"] is True
    assert client.get(url, params={"path": "nope.yml"}).status_code == 404
    assert client.get(url, params={"path": "preset.yml"}).status_code == 400
    assert client.get(url, params={"path": "../x.yml"}).status_code == 400
    assert client.get(url).status_code == 422


def test_a_draft_that_holds_a_link_is_never_copied_nor_cut(client, draft, roots, tmp_path):
    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    folder = drafts.load(roots, draft["draft_id"]).dir
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.yml").write_text("kept: true\n", encoding="utf-8")
    try:
        os.symlink(outside, folder / "modes" / "img2img" / "linked", target_is_directory=True)
    except OSError:
        pytest.skip("this system does not let the test create a link")

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img/removal")
    removal = client.delete(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img")

    assert check.status_code == 200
    assert check.json()["data"]["allowed"] is False
    assert check.json()["data"]["message"] == (
        "The mode img2img cannot be removed: the draft holds a link, modes/img2img/linked, and Preset Editor never works through a link."
    )
    assert removal.status_code == 409
    assert (outside / "keep.yml").is_file()
    assert (folder / "modes" / "img2img" / "form.yml").is_file()


def test_a_removal_check_whose_lint_fails_answers_a_clean_error(client, draft, monkeypatch):
    from backend import core_bridge

    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})

    async def failing(path):
        raise ValueError("the linter cannot read this")

    monkeypatch.setattr(core_bridge, "lint_async", failing)

    check = client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img/removal")

    assert check.status_code == 500
    assert check.json()["detail"] == {
        "success": False,
        "error": "check_failed",
        "message": "the lint of the draft without the mode img2img could not run (ValueError)",
    }


def test_the_removal_check_leaves_no_copy_behind_even_when_the_lint_fails(client, draft, monkeypatch, tmp_path):
    from backend import core_bridge

    client.post(f"{DRAFTS_URL}/{draft['draft_id']}/modes", json={"mode": "img2img"})
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(routes_files.tempfile, "tempdir", str(scratch))
    calls = []

    async def second_fails(path):
        calls.append(path)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return [], []

    monkeypatch.setattr(core_bridge, "lint_async", second_fails)

    assert client.get(f"{DRAFTS_URL}/{draft['draft_id']}/modes/img2img/removal").status_code == 500
    assert list(scratch.iterdir()) == []
    assert calls[1].name == calls[0].name and calls[1] != calls[0]


def test_lint_messages_drop_the_folder_in_every_form_and_a_mode_list_does_not_make_them_new():
    folder = Path("/srv/drafts/01ABC")
    windows = "\\srv\\drafts\\01ABC"

    assert routes_files._inside([
        "[ERROR] /srv/drafts/01ABC/preset.yml: a",
        f"[ERROR] {windows}\\preset.yml: b",
        "[WARNING] /srv/drafts/01ABC: c",
        f"[WARNING] '{windows}': d",
    ], folder) == [
        "[ERROR] preset.yml: a",
        "[ERROR] preset.yml: b",
        "[WARNING] <preset folder>: c",
        "[WARNING] '<preset folder>': d",
    ]
    before = ["[ERROR] preset.yml: tests.yml: case 'x': mode 'first_last' is not declared in preset.yml modes: ['extend', 'loop', 'video']"]
    after = [
        "[ERROR] preset.yml: tests.yml: case 'x': mode 'first_last' is not declared in preset.yml modes: ['extend', 'video']",
        "[ERROR] preset.yml: prompt_syntax.loop: 'loop' is not a mode of this preset",
    ]
    assert routes_files._added(before, after) == ["[ERROR] preset.yml: prompt_syntax.loop: 'loop' is not a mode of this preset"]
    assert routes_files._added(before, before + before) == before
