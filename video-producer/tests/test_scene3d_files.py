import math
import os
import struct
import time

import pytest

from backend import core_bridge
from backend.core_bridge import generate_ulid
from backend.scene3d import files, formats, storage
from backend.scene3d.formats import FormatError

BASE = "/api/plugins/video-producer"
PROPERTIES = ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_a_3dgs_ply_gives_its_gaussian_count_and_the_source_view_of_its_header_comment(tmp_path, samples):
    probe = formats.probe("ply", _write(tmp_path, "scene.ply", samples.ply(count=5)))

    assert (probe.format, probe.count) == ("ply", 5)
    assert probe.view == {"fov": 48.5, "aspect": 1.7778, "depth": 4.0}


@pytest.mark.parametrize(
    "comment",
    [None, "made by another tool", "potionui_view fov_y=48.5 aspect=1.7778 convention=opencv", "potionui_view fov_y=-3 aspect=1.5 depth=4", "potionui_view fov_y=nan aspect=1.5 depth=4"],
)
def test_a_ply_without_a_complete_potionui_view_comment_has_no_view(tmp_path, samples, comment):
    probe = formats.probe("ply", _write(tmp_path, "scene.ply", samples.ply(comment=comment)))

    assert probe.count == 2 and probe.view is None


def test_a_ply_may_carry_more_properties_than_the_3dgs_ones(tmp_path, samples):
    properties = (*PROPERTIES[:3], "nx", "ny", "nz", *PROPERTIES[3:], "f_rest_0")

    assert formats.probe("ply", _write(tmp_path, "scene.ply", samples.ply(count=3, properties=properties))).count == 3


@pytest.mark.parametrize(
    "build, message",
    [
        (lambda s: b"not a ply at all", "not a PLY file"),
        (lambda s: s.ply(header_format="ascii"), "not binary_little_endian"),
        (lambda s: s.ply(header_format="binary_big_endian"), "not binary_little_endian"),
        (lambda s: s.ply(properties=PROPERTIES[:-1]), "missing rot_3"),
        (lambda s: s.ply(count=0), "no Gaussians"),
        (lambda s: s.ply(short=True), "truncated"),
        (lambda s: s.ply().replace(b"element vertex 2", b"element face 2"), "first element is not vertex"),
        (lambda s: s.ply().replace(b"property float x", b"property list uchar int x"), "list property"),
        (lambda s: s.ply().replace(b"property float x", b"property double x"), "must be float"),
    ],
)
def test_a_file_that_is_not_a_binary_3dgs_ply_is_refused_by_the_core_probe_without_its_path(tmp_path, samples, build, message):
    with pytest.raises(FormatError) as caught:
        formats.probe("ply", _write(tmp_path, "scene.ply", build(samples)))

    assert message in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_the_splat_formats_are_read_by_the_core_probe(tmp_path, monkeypatch):
    asked = []

    def probe_splat(path):
        asked.append(path.name)
        return {"format": "ply", "count": 9, "view": {"fov_y": 50.0, "aspect": 1.5, "depth": 3.0, "width": 96, "height": 64, "convention": "opencv"}}

    monkeypatch.setattr(core_bridge, "probe_splat", probe_splat)

    assert formats.probe("ply", _write(tmp_path, "set.ply", b"anything")) == formats.Probe(format="ply", count=9, view={"fov": 50.0, "aspect": 1.5, "depth": 3.0})
    assert asked == ["set.ply"]
    with pytest.raises(FormatError, match="not a .spz splat"):
        formats.probe("spz", _write(tmp_path, "set.spz", b"anything"))


def test_an_spz_file_gives_the_count_of_its_header(tmp_path, samples):
    assert formats.probe("spz", _write(tmp_path, "scene.spz", samples.spz(count=7))) == formats.Probe(format="spz", count=7)


@pytest.mark.parametrize(
    "build, message",
    [
        (lambda s: s.splat(), "not gzip"),
        (lambda s: s.spz(magic=b"SPLT"), "bad magic"),
        (lambda s: s.spz()[:12], "does not decompress"),
        (lambda s: s.spz(count=0), "no Gaussians"),
    ],
)
def test_an_spz_file_must_be_gzip_with_the_ngsp_magic(tmp_path, samples, build, message):
    with pytest.raises(FormatError) as caught:
        formats.probe("spz", _write(tmp_path, "scene.spz", build(samples)))

    assert message in str(caught.value)


def _gaussian(position=(0.5, -0.2, 3.0), scale=(0.01, 0.01, 0.02)):
    return struct.pack("<6f", *position, *scale) + bytes([200, 120, 40, 255, 128, 128, 128, 255])


def test_a_splat_file_holds_32_bytes_per_gaussian(tmp_path, samples):
    assert formats.probe("splat", _write(tmp_path, "scene.splat", samples.splat(count=4))).count == 4
    assert formats.probe("splat", _write(tmp_path, "real.splat", _gaussian() * 3)) == formats.Probe(format="splat", count=3)
    for size in (0, 33):
        with pytest.raises(FormatError):
            formats.probe("splat", _write(tmp_path, f"scene-{size}.splat", bytes(size)))


@pytest.mark.parametrize("record", [_gaussian(position=(math.nan, 0, 1)), _gaussian(scale=(0.1, math.inf, 0.1)), bytes(12) + bytes.fromhex("ffffff7f") + bytes(16)])
def test_a_splat_file_whose_first_gaussians_have_a_position_or_a_scale_that_is_not_finite_is_refused(tmp_path, record):
    with pytest.raises(FormatError, match="not a finite number"):
        formats.probe("splat", _write(tmp_path, "scene.splat", _gaussian() * 2 + record))

@pytest.mark.parametrize("error", [RecursionError("maximum recursion depth exceeded"), ValueError("bad value")])
def test_a_recursion_or_value_error_while_reading_a_scene_file_is_a_format_error(tmp_path, samples, monkeypatch, error):
    def probe_splat(fmt, path):
        raise error

    monkeypatch.setattr(formats, "probe_splat", probe_splat)

    with pytest.raises(FormatError, match="not a .ply file that can be read"):
        formats.probe("ply", _write(tmp_path, "set.ply", samples.ply()))


@pytest.mark.parametrize("name, fmt", [("Scene.PLY", "ply"), ("a.b.spz", "spz"), ("x.splat", "splat"), ("set.glb", None), ("set.gltf", None), ("ply", None), ("", None)])
def test_the_format_of_a_file_comes_from_its_extension(name, fmt):
    assert formats.format_of(name) == fmt


@pytest.fixture
def project(make_project, export_storage):
    return make_project()


def _url(project_id, file_id):
    return f"{BASE}/projects/{project_id}/scene-files/{file_id}"


def test_a_stored_scene_file_is_served_back_through_its_project(client, project, samples, export_storage):
    file_id = _stored(project["id"], samples, days=0)

    response = client.get(_url(project["id"], file_id))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == samples.ply()


def test_another_user_cannot_read_the_scene_files_of_a_project(app, client, project, samples, make_user):
    from src.plugin_api import AccountType, get_current_active_user

    file_id = _stored(project["id"], samples, days=0)
    app.dependency_overrides[get_current_active_user] = lambda: make_user(user_id="user-2")

    assert client.get(_url(project["id"], file_id)).json()["detail"]["error"] == "project_not_found"
    app.dependency_overrides[get_current_active_user] = lambda: make_user(AccountType.ADMIN, user_id="admin-1")
    assert client.get(_url(project["id"], file_id)).status_code == 200


def test_a_scene_file_is_read_only_through_its_own_project(client, project, make_project, samples):
    other = make_project()
    file_id = _stored(project["id"], samples, days=0)

    assert client.get(_url(other["id"], file_id)).json()["detail"]["error"] == "file_not_found"
    assert client.get(_url(project["id"], "01M5NOTAFILE00000000000000")).status_code == 404
    files.path_of(files.get_file(file_id)).unlink()
    assert client.get(_url(project["id"], file_id)).json()["detail"]["error"] == "file_not_found"


UNLIMITED = {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}


@pytest.fixture
def plan(monkeypatch):
    statuses = {}

    def limit_status(user_id, kind):
        return {**UNLIMITED, **statuses.get(kind, {})}

    monkeypatch.setattr(core_bridge, "limit_status", limit_status)
    return statuses


def _refusal(project_id, owner_id, incoming):
    with pytest.raises(storage.SceneError) as caught:
        files.ensure_room(project_id, owner_id, incoming)
    return caught.value


def test_a_scene_file_past_the_project_cap_is_refused_with_storage_full(project, samples, monkeypatch, plan):
    file_id = _stored(project["id"], samples, days=0)
    size = files.get_file(file_id)["size"]
    assert files.PROJECT_MAX_BYTES == 20 * 1024 ** 3
    monkeypatch.setattr(files, "PROJECT_MAX_BYTES", size + 10)

    refused = _refusal(project["id"], "user-1", size)

    assert (refused.status_code, refused.error, refused.data) == (413, "storage_full", {"limit": size + 10, "used": size, "needed": size})
    files.ensure_room(project["id"], "user-1", 10)


def test_the_scene_files_of_the_owner_count_against_the_storage_plan(project, make_project, samples, plan):
    other = make_project()
    size = files.get_file(_stored(other["id"], samples, days=0))["size"]
    plan["storage_bytes"] = {"limit": 10**6, "used": 10**6 - 2 * size + 1, "remaining": 2 * size - 1}

    refused = _refusal(project["id"], "user-1", size)

    assert (refused.status_code, refused.error, refused.data) == (413, "storage_full", {"remaining": size - 1, "needed": size})


def test_an_exempt_or_unlimited_owner_only_meets_the_project_cap(project, plan):
    plan["storage_bytes"] = {"limit": 100, "used": None, "remaining": None, "exempt": True}

    files.ensure_room(project["id"], "user-1", 10**6)


def _scene(file_id):
    return {"id": f"scene-{file_id[-4:]}", "kind": "splatfile", "name": "set", "fileId": file_id, "format": "ply", "view": None}


def _stored(project_id, samples, days=2.0):
    from datetime import datetime, timedelta, timezone

    from src.plugin_api import db

    file_id = generate_ulid()
    folder = storage.project_folder(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    data = samples.ply()
    (folder / files.stored_name(file_id, "ply")).write_bytes(data)
    files.add_file(file_id, project_id, "user-1", "splat", "set.ply", len(data), formats.Probe(format="ply", count=2))
    created = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with db.get_cursor() as cursor:
        cursor.execute(f"UPDATE {files.FILES} SET created_at = ? WHERE id = ?", (created, file_id))
    return file_id


def test_the_sweep_deletes_the_scene_files_no_stored_version_cites_once_they_are_a_day_old(store, make_project, make_doc, export_storage, samples):
    from backend import projects, scene3d

    doc = make_doc()
    project = make_project(doc=doc)
    pid = project["id"]
    in_an_old_version, in_the_current_one, orphan = (_stored(pid, samples) for _ in range(3))
    fresh = _stored(pid, samples, days=0.9)
    projects.save_project(pid, {**doc, "scenes": [_scene(in_an_old_version)]}, 1)
    projects.save_project(pid, {**doc, "scenes": [_scene(in_the_current_one)]}, 2)
    folder = storage.project_folder(pid)
    stray_old, stray_new = folder / "01M5STRAYOLD00000000000000.ply", folder / "01M5STRAYNEW00000000000000.ply"
    for path in (stray_old, stray_new):
        path.write_bytes(b"x")
    day_ago = time.time() - 25 * 3600
    os.utime(stray_old, (day_ago, day_ago))

    assert scene3d.sweep() == 2

    assert sorted(found["id"] for found in files.list_project(pid)) == sorted([in_an_old_version, in_the_current_one, fresh])
    assert not (folder / files.stored_name(orphan, "ply")).exists() and not stray_old.exists()
    assert stray_new.exists() and (folder / files.stored_name(fresh, "ply")).exists()
    assert files.collect_orphans() == 0


def test_a_scene_file_whose_last_citing_version_was_pruned_is_collected(store, make_project, make_doc, export_storage, samples):
    from backend import projects

    doc = make_doc()
    project = make_project(doc=doc)
    cited = _stored(project["id"], samples)
    projects.save_project(project["id"], {**doc, "scenes": [_scene(cited)]}, 1)
    projects.save_project(project["id"], doc, 2)
    assert files.collect_orphans() == 0

    from src.plugin_api import db

    with db.get_cursor() as cursor:
        cursor.execute(f"DELETE FROM {projects.VERSIONS} WHERE project_id = ? AND version = 2", (project["id"],))

    assert files.collect_orphans() == 1
    assert files.get_file(cited) is None
