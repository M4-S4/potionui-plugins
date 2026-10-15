import io
import shutil

import pytest
import yaml
from PIL import Image

from backend import files, media
from tests.conftest import FIXTURES

NATIVE = FIXTURES / "minimal-native"


def _png(width=1600, height=900, color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def draft_dir(tmp_path):
    target = tmp_path / "draft"
    shutil.copytree(NATIVE, target)
    return target


def _manifest(draft_dir):
    return (draft_dir / "preset.yml").read_text(encoding="utf-8")


def test_a_cover_image_is_downscaled_to_webp_and_declared_in_the_manifest(draft_dir):
    before = _manifest(draft_dir)

    stored = media.store(draft_dir, "cover", "My Cover.PNG", _png())
    declared = media.set_cover(draft_dir, stored["path"])

    assert stored["path"] == "public/cover.webp" and stored["role"] == "cover"
    with Image.open(draft_dir / "public" / "cover.webp") as image:
        assert image.format == "WEBP" and max(image.size) == 1024
    assert declared == {"cover": "public/cover.webp"}
    after = _manifest(draft_dir)
    assert after.startswith(before.rstrip("\n") + "\n")
    assert yaml.safe_load(after)["media"] == {"cover": "public/cover.webp"}


def test_gallery_items_keep_their_file_name_caption_and_mode(draft_dir):
    first = media.store(draft_dir, "gallery", "Potion bottle.jpg", _png(800, 800))
    second = media.store(draft_dir, "gallery", "Potion bottle.jpg", _png(800, 800))
    media.add_gallery_item(draft_dir, first["path"], caption="A bottle", mode="txt2img")
    declared = media.add_gallery_item(draft_dir, second["path"])

    assert (first["path"], second["path"]) == ("public/examples/Potion-bottle.webp", "public/examples/Potion-bottle-2.webp")
    assert declared["gallery"] == [
        {"src": "public/examples/Potion-bottle.webp", "caption": "A bottle", "mode": "txt2img"},
        {"src": "public/examples/Potion-bottle-2.webp"},
    ]
    assert yaml.safe_load(_manifest(draft_dir))["media"]["gallery"][0]["caption"] == "A bottle"


def test_a_video_is_stored_as_is_and_a_cover_video_replaces_the_cover_image(draft_dir):
    media.set_cover(draft_dir, media.store(draft_dir, "cover", "c.png", _png())["path"])

    stored = media.store(draft_dir, "cover", "clip.MP4", b"\x00\x00\x00\x18ftypmp42" + b"x" * 100)
    media.set_cover(draft_dir, stored["path"])

    assert stored["path"] == "public/cover.mp4"
    assert not (draft_dir / "public" / "cover.webp").exists()
    assert yaml.safe_load(_manifest(draft_dir))["media"] == {"cover": "public/cover.mp4"}


@pytest.mark.parametrize(
    "role, name, data, code",
    [
        ("cover", "notes.yml", b"x", "not_media"),
        ("cover", "broken.png", b"not an image", "not_media"),
        ("gallery", "empty.png", b"", "invalid_request"),
        ("gallery", "huge.png", b"x" * (media.MAX_UPLOAD_BYTES + 1), "too_large"),
        ("style", "a.png", b"x", "invalid_request"),
    ],
)
def test_bad_uploads_are_refused_before_writing(draft_dir, role, name, data, code):
    with pytest.raises(files.FilesError) as failure:
        media.store(draft_dir, role, name, data)
    assert failure.value.code == code
    assert not (draft_dir / "public").exists()


def test_remove_deletes_the_file_and_its_references(draft_dir):
    cover = media.store(draft_dir, "cover", "c.png", _png())
    media.set_cover(draft_dir, cover["path"])
    item = media.store(draft_dir, "gallery", "g.png", _png(600, 600))
    media.add_gallery_item(draft_dir, item["path"], caption="g")

    media.remove(draft_dir, cover["path"])
    assert yaml.safe_load(_manifest(draft_dir))["media"] == {"gallery": [{"src": "public/examples/g.webp", "caption": "g"}]}

    media.remove(draft_dir, item["path"])
    assert "media" not in yaml.safe_load(_manifest(draft_dir))
    assert not (draft_dir / "public" / "examples").exists() and (draft_dir / "public").is_dir()
    with pytest.raises(files.FilesError) as failure:
        media.remove(draft_dir, item["path"])
    assert failure.value.code == "not_found"


def test_declare_only_references_files_that_are_there(draft_dir):
    cover = media.store(draft_dir, "cover", "c.png", _png())["path"]
    item = media.store(draft_dir, "gallery", "g.png", _png(600, 600))["path"]

    declared = media.declare(draft_dir, cover=item, gallery=[{"src": cover, "caption": "x" * 300, "seed": "4"}, {"src": item}])
    assert declared == {"cover": item, "gallery": [{"src": cover, "caption": "x" * 200, "seed": 4}, {"src": item}]}
    assert media.declare(draft_dir, cover=None)["gallery"][1] == {"src": item}
    assert media.declare(draft_dir, gallery=[]) == {}

    for bad in ({"cover": "public/missing.webp"}, {"gallery": [{"src": "preset.yml"}]}, {"gallery": [{"src": item}, {"src": item}]}):
        with pytest.raises(files.FilesError):
            media.declare(draft_dir, **bad)
    assert "media" not in yaml.safe_load(_manifest(draft_dir))


def test_listing_describes_every_public_media_with_its_roles(draft_dir):
    media.set_cover(draft_dir, media.store(draft_dir, "cover", "c.png", _png())["path"])
    item = media.store(draft_dir, "gallery", "g.png", _png(600, 600))
    media.add_gallery_item(draft_dir, item["path"], caption="g", mode="txt2img")
    (draft_dir / "public" / "loose.webp").write_bytes(b"RIFF")
    (draft_dir / "public" / "notes.md").write_text("x", encoding="utf-8")
    (draft_dir / "public" / "styles").mkdir()
    (draft_dir / "public" / "styles" / "noir.webp").write_bytes(b"RIFF")

    listed = media.listing(draft_dir)

    assert listed["cover"] == "public/cover.webp"
    assert [entry["path"] for entry in listed["files"]] == ["public/cover.webp", "public/examples/g.webp", "public/loose.webp", "public/styles/noir.webp"]
    assert [entry["roles"] for entry in listed["files"]] == [["cover"], ["gallery"], [], ["style"]]
    assert listed["files"][1]["gallery"] == {"src": "public/examples/g.webp", "caption": "g", "mode": "txt2img"}
    assert all(entry["over_budget"] is False for entry in listed["files"])
    assert listed["files"][0]["kind"] == "image"


def test_public_path_only_resolves_media_under_public(draft_dir):
    (draft_dir / "public").mkdir()
    (draft_dir / "public" / "a.png").write_bytes(b"x")
    assert media.public_path(draft_dir, "public/a.png") == (draft_dir / "public" / "a.png").resolve()
    for bad in ("preset.yml", "public/notes.md", "modes/txt2img/form.yml", "../x"):
        with pytest.raises(files.FilesError):
            media.public_path(draft_dir, bad)


def test_the_media_block_replaces_only_itself_in_the_manifest():
    text = 'schema: 1\nid: "x"\nmedia:\n  cover: public/old.webp\n  gallery:\n    - src: public/a.webp\n\nmodes:\n  - txt2img\n'

    replaced = files.replace_top_level_block(text, "media", "media:\n  cover: public/new.webp")
    assert replaced == 'schema: 1\nid: "x"\nmedia:\n  cover: public/new.webp\n\nmodes:\n  - txt2img\n'

    removed = files.replace_top_level_block(text, "media", None)
    assert removed == 'schema: 1\nid: "x"\nmodes:\n  - txt2img\n'

    appended = files.replace_top_level_block('schema: 1\nmodes:\n  - txt2img\n', "media", "media:\n  cover: public/c.webp")
    assert appended == 'schema: 1\nmodes:\n  - txt2img\nmedia:\n  cover: public/c.webp\n'

    assert files.replace_top_level_block('schema: 1\n', "media", None) == 'schema: 1\n'
    assert files.top_level_block_span('a: 1\n# media: 2\nmedia:\n  x: 1\n', "media") == (16, 30)
