from pathlib import Path
from types import SimpleNamespace

from backend import core_bridge
from backend.exports import media

USER = SimpleNamespace(id="user-1")
FILES = [{"id": "f1", "file_path": "generations/g/a.mp4"}, {"id": "f2", "file_path": "generations/g/b.mp4"}]


def _bridge(monkeypatch, files=FILES):
    listed, paths, copies = [], [], []

    def list_generation_files(user, generation_id):
        listed.append((user.id, generation_id))
        return [dict(item) for item in files]

    def media_file_path(user, ref):
        paths.append((user.id, dict(ref)))
        return f"/storage/{ref['file_id']}"

    def local_media_file(user, ref, folder):
        copies.append((user.id, dict(ref)))
        return Path(folder) / (ref.get("file_id") or ref["item_id"])

    monkeypatch.setattr(core_bridge, "list_generation_files", list_generation_files)
    monkeypatch.setattr(core_bridge, "media_file_path", media_file_path)
    monkeypatch.setattr(core_bridge, "local_media_file", local_media_file)
    return listed, paths, copies


def test_a_take_with_its_file_id_is_read_by_that_reference_without_listing_its_generation(monkeypatch):
    listed, paths, _ = _bridge(monkeypatch)
    found = media.history_file({"generation_id": "g", "file_id": "f1", "file_path": "generations/g/a.mp4"})

    assert media.Resolver(USER).path(found) == "/storage/f1"
    assert paths == [("user-1", {"kind": "history", "generation_id": "g", "file_id": "f1"})]
    assert listed == []


def test_a_take_without_a_file_id_finds_its_file_among_the_files_of_its_generation_once(monkeypatch, tmp_path):
    listed, paths, copies = _bridge(monkeypatch)
    resolver = media.Resolver(USER)
    found = media.history_file({"generation_id": "g", "file_id": None, "file_path": "generations/g/b.mp4"})

    assert resolver.path(found) == "/storage/f2"
    assert resolver.local(found, tmp_path) == tmp_path / "f2"
    assert listed == [("user-1", "g")]
    assert paths == copies == [("user-1", {"kind": "history", "generation_id": "g", "file_id": "f2"})]


def test_a_take_whose_file_is_not_among_the_files_of_its_generation_has_no_file(monkeypatch, tmp_path):
    listed, paths, copies = _bridge(monkeypatch)
    resolver = media.Resolver(USER)
    found = media.history_file({"generation_id": "g", "file_id": None, "file_path": "generations/g/gone.mp4"})

    assert resolver.path(found) is None
    assert resolver.local(found, tmp_path) is None
    assert listed == [("user-1", "g")]
    assert paths == copies == []


def test_a_generation_that_cannot_be_listed_gives_its_take_no_file(monkeypatch):
    _, paths, _ = _bridge(monkeypatch)

    def refused(user, generation_id):
        raise LookupError(generation_id)

    monkeypatch.setattr(core_bridge, "list_generation_files", refused)
    found = media.history_file({"generation_id": "g", "file_path": "generations/g/a.mp4"})

    assert media.Resolver(USER).path(found) is None
    assert paths == []


def test_a_record_without_a_generation_has_no_reference_and_no_file(monkeypatch, tmp_path):
    listed, paths, copies = _bridge(monkeypatch)
    found = media.history_file({"generation_id": None, "file_id": "f1", "file_path": "generations/g/a.mp4"})

    assert found.ref is None
    assert media.Resolver(USER).path(found) is None
    assert media.Resolver(USER).local(found, tmp_path) is None
    assert listed == paths == copies == []


def test_a_library_media_is_read_by_the_reference_its_origin_resolves_through(monkeypatch, tmp_path):
    _, _, copies = _bridge(monkeypatch)
    ref = {"kind": "library", "item_id": "f1"}
    found = media.Found("a.wav", "library", "uploads/a.wav", ref)

    assert media.Resolver(USER).local(found, tmp_path) == tmp_path / "f1"
    assert copies == [("user-1", ref)]
