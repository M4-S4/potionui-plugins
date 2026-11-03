import os
import shutil
from pathlib import Path

import pytest

from backend import files
from tests.conftest import FIXTURES

NATIVE = FIXTURES / "minimal-native"


@pytest.fixture
def draft_dir(tmp_path):
    target = tmp_path / "draft"
    shutil.copytree(NATIVE, target)
    return target


@pytest.mark.parametrize("value", ["", "/abs", "a/../b", "../x", "./x", ".hidden", "a\\b", "modes/.secret/x.yml", "a\x00b"])
def test_paths_outside_the_rules_are_refused(draft_dir, value):
    with pytest.raises(files.FilesError) as failure:
        files.resolve(draft_dir, value)
    assert failure.value.code == "invalid_path"


def test_a_symlink_inside_the_draft_is_never_followed(draft_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.yml").write_text("x: 1\n", encoding="utf-8")
    try:
        os.symlink(outside, draft_dir / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return

    with pytest.raises(files.FilesError) as failure:
        files.read_text(draft_dir, "link/secret.yml")
    assert failure.value.code == "invalid_path"


def test_read_text_gives_the_content_and_an_etag(draft_dir):
    result = files.read_text(draft_dir, "modes/txt2img/form.yml")

    assert result["path"] == "modes/txt2img/form.yml"
    assert result["content"] == (NATIVE / "modes" / "txt2img" / "form.yml").read_text(encoding="utf-8")
    assert result["etag"] == files.etag_of((NATIVE / "modes" / "txt2img" / "form.yml").read_bytes())
    assert result["size"] > 0


def test_the_files_citing_another_mode_are_found(draft_dir):
    (draft_dir / "modes" / "video" / "tabs").mkdir(parents=True)
    (draft_dir / "modes" / "video" / "tabs" / "lora.yml").write_text("fields: []\n", encoding="utf-8")
    (draft_dir / "modes" / "video" / "form.yml").write_text('children: "{{ paths.preset }}/modes/video/tabs/lora.yml"\n', encoding="utf-8")
    (draft_dir / "modes" / "extend").mkdir(parents=True)
    (draft_dir / "modes" / "extend" / "form.yml").write_text('children: "{{paths.preset}}/modes/video/tabs/lora.yml"\n', encoding="utf-8")
    (draft_dir / "files" / "form").mkdir(parents=True)
    (draft_dir / "files" / "form" / "models.yml").write_text('file: "{{ paths.preset }}/modes/videos/x.yml"\n', encoding="utf-8")

    assert files.citing_files(draft_dir, "video") == ["modes/extend/form.yml"]
    assert files.citing_files(draft_dir, "extend") == []


def test_only_text_files_outside_public_are_read(draft_dir):
    (draft_dir / "public").mkdir()
    (draft_dir / "public" / "cover.png").write_bytes(b"\x89PNG")
    (draft_dir / "public" / "notes.md").write_text("x", encoding="utf-8")
    for path in ("public/cover.png", "public/notes.md"):
        with pytest.raises(files.FilesError) as failure:
            files.read_text(draft_dir, path)
        assert failure.value.code == "not_text"
    with pytest.raises(files.FilesError) as failure:
        files.read_text(draft_dir, "modes/txt2img/nope.yml")
    assert failure.value.code == "not_found"


def test_a_file_over_the_budget_or_not_utf8_is_refused(draft_dir):
    (draft_dir / "big.md").write_bytes(b"x" * (files.MAX_TEXT_BYTES + 1))
    (draft_dir / "bin.txt").write_bytes(b"\xff\xfe\x00")
    assert files.read_text.__name__ == "read_text"
    with pytest.raises(files.FilesError) as failure:
        files.read_text(draft_dir, "big.md")
    assert failure.value.code == "too_large"
    with pytest.raises(files.FilesError) as failure:
        files.read_text(draft_dir, "bin.txt")
    assert failure.value.code == "not_text"


def test_write_text_needs_the_current_etag_and_gives_the_next_one(draft_dir):
    before = files.read_text(draft_dir, "preset.yml")

    written = files.write_text(draft_dir, "preset.yml", before["content"] + "tags: [x]\n", before["etag"])

    assert written["etag"] == files.read_text(draft_dir, "preset.yml")["etag"] != before["etag"]
    assert (draft_dir / "preset.yml").read_text(encoding="utf-8").endswith("tags: [x]\n")
    assert not list(draft_dir.glob(".*.writing"))


def test_a_stale_etag_is_refused_with_the_current_content(draft_dir):
    before = files.read_text(draft_dir, "preset.yml")
    files.write_text(draft_dir, "preset.yml", "schema: 1\n", before["etag"])

    with pytest.raises(files.FilesError) as failure:
        files.write_text(draft_dir, "preset.yml", "other\n", before["etag"])

    assert failure.value.code == "precondition_failed"
    assert failure.value.extra == {"etag": files.etag_of(b"schema: 1\n"), "content": "schema: 1\n"}
    assert (draft_dir / "preset.yml").read_text(encoding="utf-8") == "schema: 1\n"


def test_an_existing_file_needs_an_if_match_and_a_new_one_does_not(draft_dir):
    with pytest.raises(files.FilesError) as failure:
        files.write_text(draft_dir, "preset.yml", "x", None)
    assert failure.value.code == "precondition_required" and failure.value.extra["etag"]

    created = files.write_text(draft_dir, "modes/txt2img/tabs/extra.yml", "fields: []\n", None)

    assert created["etag"] == files.etag_of(b"fields: []\n")
    assert (draft_dir / "modes" / "txt2img" / "tabs" / "extra.yml").read_text(encoding="utf-8") == "fields: []\n"


def test_write_text_refuses_media_paths_and_oversize_content(draft_dir):
    with pytest.raises(files.FilesError) as failure:
        files.write_text(draft_dir, "public/cover.png", "x", None)
    assert failure.value.code == "not_text"
    with pytest.raises(files.FilesError) as failure:
        files.write_text(draft_dir, "notes.md", "x" * (files.MAX_TEXT_BYTES + 1), None)
    assert failure.value.code == "too_large"


def test_delete_file_removes_it_and_its_emptied_folders_but_never_the_manifest(draft_dir):
    files.delete_file(draft_dir, "modes/txt2img/tabs/main.yml")

    assert not (draft_dir / "modes" / "txt2img" / "tabs").exists()
    assert (draft_dir / "modes" / "txt2img" / "form.yml").is_file()
    with pytest.raises(files.FilesError) as failure:
        files.delete_file(draft_dir, "preset.yml")
    assert failure.value.code == "invalid_request"
    with pytest.raises(files.FilesError) as failure:
        files.delete_file(draft_dir, "modes/txt2img/tabs/main.yml")
    assert failure.value.code == "not_found"


@pytest.mark.parametrize("value", ["txt2img", "img2video", "a", "mode_2"])
def test_mode_names_follow_the_folder_rule(value):
    assert files.check_mode_name(value) == value


@pytest.mark.parametrize("value", ["", "Txt2Img", "2d", "a-b", "a b", "../x", "x" * 41])
def test_mode_names_outside_the_rule_are_refused(value):
    with pytest.raises(files.FilesError):
        files.check_mode_name(value)


BLOCK = 'schema: 1\nid: "x"\nmodes:\n  - txt2img\n  - "img2img"\ntags: []\n'
FLOW = 'schema: 1\nmodes: [txt2img, img2img]\ntags: []\n'


def test_manifest_modes_reads_block_and_flow_lists():
    assert files.manifest_modes(BLOCK) == ["txt2img", "img2img"]
    assert files.manifest_modes(FLOW) == ["txt2img", "img2img"]
    assert files.manifest_modes("schema: 1\n") == []


def test_add_mode_keeps_the_style_of_the_list_and_the_rest_of_the_text():
    assert files.add_mode_to_manifest(BLOCK, "edit") == 'schema: 1\nid: "x"\nmodes:\n  - txt2img\n  - "img2img"\n  - edit\ntags: []\n'
    assert files.add_mode_to_manifest(FLOW, "edit") == "schema: 1\nmodes: [txt2img, img2img, edit]\ntags: []\n"
    assert files.add_mode_to_manifest("schema: 1", "edit") == "schema: 1\nmodes:\n  - edit\n"
    assert files.add_mode_to_manifest(BLOCK, "txt2img") == BLOCK


def test_remove_mode_drops_the_item_and_leaves_the_rest():
    assert files.remove_mode_from_manifest(BLOCK, "img2img") == 'schema: 1\nid: "x"\nmodes:\n  - txt2img\ntags: []\n'
    assert files.remove_mode_from_manifest(BLOCK, "txt2img") == 'schema: 1\nid: "x"\nmodes:\n  - "img2img"\ntags: []\n'
    assert files.remove_mode_from_manifest(FLOW, "txt2img") == "schema: 1\nmodes: [img2img]\ntags: []\n"
    assert files.remove_mode_from_manifest(BLOCK, "nope") == BLOCK
