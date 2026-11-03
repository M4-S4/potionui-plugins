import io
import stat
import zipfile

import pytest

from backend import archive
from backend.files import FilesError
from tests.conftest import FIXTURES

NATIVE = FIXTURES / "minimal-native"


def _zip(entries, **kwargs):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in entries:
            info = zipfile.ZipInfo(name)
            info.filename = name
            info.compress_type = zipfile.ZIP_DEFLATED
            if name in kwargs.get("links", ()):
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            out.writestr(info, data)
    return buffer.getvalue()


def _tree(directory):
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


def test_export_then_extract_gives_the_same_files_without_the_private_ones(tmp_path):
    source = tmp_path / "source"
    import shutil

    shutil.copytree(NATIVE, source)
    (source / ".preset-editor.json").write_text("{}", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.pyc").write_bytes(b"x")
    (source / "public").mkdir()
    (source / "public" / "cover.webp").write_bytes(b"RIFF")

    data = archive.export_dir(source)
    names = sorted(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert names == _tree(NATIVE) + ["public/cover.webp"]

    written = archive.extract(data, tmp_path / "out")
    assert sorted(written) == names
    assert _tree(tmp_path / "out") == names
    assert (tmp_path / "out" / "preset.yml").read_bytes() == (NATIVE / "preset.yml").read_bytes()


def test_a_single_top_folder_is_stripped_and_system_files_are_skipped(tmp_path):
    data = _zip([
        ("MyPreset/preset.yml", "schema: 1\n"),
        ("MyPreset/modes/txt2img/form.yml", "fields: []\n"),
        ("MyPreset/.DS_Store", b"x"),
        ("__MACOSX/MyPreset/._preset.yml", b"x"),
        ("MyPreset/modes/", b""),
    ])

    assert archive.extract(data, tmp_path / "out") == ["preset.yml", "modes/txt2img/form.yml"]
    assert _tree(tmp_path / "out") == ["modes/txt2img/form.yml", "preset.yml"]


@pytest.mark.parametrize(
    "entries, code, fragment",
    [
        ([("preset.yml", "a: 1\n"), ("../escape.yml", "x")], "invalid_request", "escape.yml"),
        ([("preset.yml", "a: 1\n"), ("/etc/passwd.txt", "x")], "invalid_request", "passwd"),
        ([("preset.yml", "a: 1\n"), ("modes\\x\\form.yml", "x")], "invalid_request", "form.yml"),
        ([("preset.yml", "a: 1\n"), ("public/.hidden.png", "x")], "invalid_request", "hidden"),
        ([("preset.yml", "a: 1\n"), ("tool.exe", "x")], "invalid_request", "tool.exe"),
        ([("modes/txt2img/form.yml", "fields: []\n")], "invalid_request", "preset.yml is missing"),
        ([("a/preset.yml", "a: 1\n"), ("b/preset.yml", "a: 2\n")], "invalid_request", "preset.yml is missing"),
        ([], "invalid_request", "no file"),
    ],
)
def test_hostile_or_malformed_archives_are_refused_before_writing(tmp_path, entries, code, fragment):
    with pytest.raises(FilesError) as failure:
        archive.extract(_zip(entries), tmp_path / "out")
    assert failure.value.code == code
    assert fragment in failure.value.message
    assert not (tmp_path / "out").exists()


def test_links_bombs_and_oversized_archives_are_refused(tmp_path, monkeypatch):
    with pytest.raises(FilesError) as linked:
        archive.extract(_zip([("preset.yml", "a: 1\n"), ("public/x.png", "target")], links=("public/x.png",)), tmp_path / "a")
    assert "is a link" in linked.value.message

    monkeypatch.setattr(archive, "MAX_EXTRACTED_BYTES", 10)
    with pytest.raises(FilesError) as big:
        archive.extract(_zip([("preset.yml", "a: 1\n"), ("notes.txt", "x" * 20)]), tmp_path / "b")
    assert big.value.code == "too_large"
    monkeypatch.setattr(archive, "MAX_EXTRACTED_BYTES", 256 * 1024 * 1024)

    monkeypatch.setattr(archive, "MAX_ENTRIES", 1)
    with pytest.raises(FilesError) as many:
        archive.extract(_zip([("preset.yml", "a: 1\n"), ("notes.txt", "x")]), tmp_path / "c")
    assert many.value.code == "too_large"
    monkeypatch.setattr(archive, "MAX_ENTRIES", 2000)

    bomb = _zip([("preset.yml", "a: 1\n"), ("notes.txt", "0" * (2 * 1024 * 1024))])
    with pytest.raises(FilesError) as inflated:
        archive.extract(bomb, tmp_path / "d")
    assert "inflates" in inflated.value.message

    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", 10)
    with pytest.raises(FilesError) as upload:
        archive.extract(_zip([("preset.yml", "a: 1\n")]), tmp_path / "e")
    assert upload.value.code == "too_large"

    with pytest.raises(FilesError) as garbage:
        archive.extract(b"not a zip", tmp_path / "f")
    assert garbage.value.message == "the file is not a zip archive"
    assert not any((tmp_path / name).exists() for name in "abcdef")


def test_the_declared_size_is_checked_again_while_extracting(tmp_path, monkeypatch):
    data = _zip([("preset.yml", "a: 1\n"), ("notes.txt", "y" * 50)])
    monkeypatch.setattr(archive, "_members", lambda zf: [info for info in zf.infolist()])
    monkeypatch.setattr(archive, "MAX_EXTRACTED_BYTES", 20)

    with pytest.raises(FilesError) as failure:
        archive.extract(data, tmp_path / "out")

    assert failure.value.code == "too_large"
    assert not (tmp_path / "out").exists()
