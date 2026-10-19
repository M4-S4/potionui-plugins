import math
import struct

import pytest

from backend import core_bridge
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

    assert (probe.format, probe.count, probe.cameras) == ("ply", 5, None)
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


BLENDER_SCENE = {
    "asset": {"version": "2.0"},
    "nodes": [
        {"name": "camera", "camera": 0},
        {"name": "rig", "children": [2]},
        {"camera": 1},
        {"name": "still", "camera": 2},
        {"name": "set", "mesh": 0},
        {"camera": 9},
    ],
    "cameras": [
        {"type": "perspective", "perspective": {"yfov": 0.6, "znear": 0.1}},
        {"name": "crane-cam", "type": "perspective", "perspective": {"yfov": 0.7, "znear": 0.1}},
        {"type": "perspective", "perspective": {"yfov": 0.5, "znear": 0.1}},
    ],
    "accessors": [{"max": [4.5]}, {"max": [2.0]}, {"count": 3}],
    "animations": [
        {"channels": [{"sampler": 0, "target": {"node": 0, "path": "translation"}}, {"sampler": 1, "target": {"node": 0, "path": "rotation"}}],
         "samplers": [{"input": 0}, {"input": 1}]},
        {"channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}, {"sampler": 1, "target": {"node": 3, "path": "weights"}}],
         "samplers": [{"input": 2}, {"input": 0}]},
    ],
}


def test_a_glb_lists_its_cameras_and_whether_an_animation_moves_them_or_their_parent(tmp_path, samples):
    probe = formats.probe("glb", _write(tmp_path, "set.glb", samples.glb(BLENDER_SCENE)))

    assert (probe.format, probe.count, probe.view) == ("glb", None, None)
    assert probe.cameras == [
        {"name": "camera", "animated": True, "duration": 4.5},
        {"name": "crane-cam", "animated": True, "duration": None},
        {"name": "still", "animated": False, "duration": None},
        {"name": "camera-5", "animated": False, "duration": None},
    ]


def test_a_glb_without_camera_has_an_empty_camera_list(tmp_path, samples):
    assert formats.probe("glb", _write(tmp_path, "set.glb", samples.glb({"asset": {"version": "2.0"}}))).cameras == []


@pytest.mark.parametrize(
    "build, message",
    [
        (lambda s: b"PK\x03\x04" + bytes(40), "not a binary glTF"),
        (lambda s: s.glb({"asset": {}}, version=1), "version 1"),
        (lambda s: s.glb({"asset": {}}) + b"tail", "cut short"),
        (lambda s: s.glb({"asset": {}})[:-4], "cut short"),
        (lambda s: s.glb([1, 2]), "not an object"),
        (lambda s: s.glb({"asset": {}}).replace(b'{"asset"', b'{"asset"'.replace(b"{", b"[")), "cannot be read"),
    ],
)
def test_a_file_that_is_not_a_gltf_2_binary_is_refused(tmp_path, samples, build, message):
    with pytest.raises(FormatError) as caught:
        formats.probe("glb", _write(tmp_path, "set.glb", build(samples)))

    assert message in str(caught.value)


@pytest.mark.parametrize("name, fmt", [("Scene.PLY", "ply"), ("a.b.spz", "spz"), ("x.splat", "splat"), ("set.glb", "glb"), ("set.gltf", None), ("ply", None), ("", None)])
def test_the_format_of_a_file_comes_from_its_extension(name, fmt):
    assert formats.format_of(name) == fmt


@pytest.fixture
def project(make_project, export_storage):
    return make_project()


def _upload(client, project_id, name, data, kind="splat"):
    return client.post(f"{BASE}/projects/{project_id}/scene-files", files={"file": (name, data, "application/octet-stream")}, data={"kind": kind})


def test_an_uploaded_ply_is_stored_under_its_id_with_its_count_and_view_and_served_back(client, project, samples, export_storage):
    data = samples.ply(count=3)

    response = _upload(client, project["id"], "Ridge scan.ply", data)

    assert response.status_code == 201, response.text
    stored = response.json()["data"]["file"]
    assert stored == {
        "id": stored["id"],
        "kind": "splat",
        "format": "ply",
        "name": "Ridge scan.ply",
        "size": len(data),
        "count": 3,
        "view": {"fov": 48.5, "aspect": 1.7778, "depth": 4.0},
        "cameras": None,
        "url": f"{BASE}/projects/{project['id']}/scene-files/{stored['id']}",
        "created_at": stored["created_at"],
    }
    folder = export_storage / "video_producer" / "scenes" / project["id"]
    assert sorted(path.name for path in folder.iterdir()) == [f"{stored['id']}.ply", "work"]
    assert list((folder / "work").iterdir()) == []
    served = client.get(stored["url"])
    assert served.status_code == 200 and served.content == data
    assert served.headers["content-type"] == "application/octet-stream"


@pytest.mark.parametrize("name, build, fmt, count", [("set.spz", lambda s: s.spz(count=9), "spz", 9), ("set.splat", lambda s: s.splat(count=3), "splat", 3)])
def test_an_uploaded_spz_or_splat_file_has_a_count_and_no_view(client, project, samples, name, build, fmt, count):
    stored = _upload(client, project["id"], name, build(samples)).json()["data"]["file"]

    assert (stored["format"], stored["count"], stored["view"], stored["cameras"]) == (fmt, count, None, None)


def test_an_uploaded_glb_lists_its_cameras_and_is_served_as_gltf_binary(client, project, samples):
    response = _upload(client, project["id"], "set.glb", samples.glb(BLENDER_SCENE), kind="glb")

    stored = response.json()["data"]["file"]
    assert response.status_code == 201
    assert (stored["kind"], stored["format"], stored["count"], stored["view"]) == ("glb", "glb", None, None)
    assert stored["cameras"][0] == {"name": "camera", "animated": True, "duration": 4.5}
    assert client.get(stored["url"]).headers["content-type"] == "model/gltf-binary"


@pytest.mark.parametrize(
    "name, kind, error",
    [("set.glb", "splat", "unsupported_format"), ("set.ply", "glb", "unsupported_format"), ("set.obj", "splat", "unsupported_format"), ("set.ply", "splat", "invalid_file")],
)
def test_an_upload_of_the_wrong_kind_or_content_is_refused_and_leaves_nothing(client, project, export_storage, name, kind, error):
    response = _upload(client, project["id"], name, b"glTF but not really, and not a ply either", kind=kind)

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == error
    assert files.list_project(project["id"]) == []
    work = storage.work_folder(project["id"])
    assert not work.exists() or list(work.iterdir()) == []


def test_an_upload_over_the_size_limit_is_refused_and_leaves_nothing(client, project, samples, monkeypatch):
    monkeypatch.setattr(files, "MAX_BYTES", 100)
    monkeypatch.setattr(files, "CHUNK", 64)

    response = _upload(client, project["id"], "big.ply", samples.ply(count=4))

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "file_too_large"
    assert files.list_project(project["id"]) == []
    assert list(storage.work_folder(project["id"]).iterdir()) == []


@pytest.mark.parametrize("data", [{}, {"kind": "mesh"}])
def test_an_upload_without_a_file_or_with_another_kind_is_an_invalid_request(client, project, data):
    if data:
        response = client.post(f"{BASE}/projects/{project['id']}/scene-files", files={"file": ("a.ply", b"x")}, data=data)
    else:
        response = client.post(f"{BASE}/projects/{project['id']}/scene-files", data={"kind": "splat"})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_request"


def test_another_user_cannot_upload_to_or_read_the_scene_files_of_a_project(app, client, project, samples, make_user):
    from src.plugin_api import AccountType, get_current_active_user

    stored = _upload(client, project["id"], "set.ply", samples.ply()).json()["data"]["file"]
    app.dependency_overrides[get_current_active_user] = lambda: make_user(user_id="user-2")

    assert _upload(client, project["id"], "set.ply", samples.ply()).status_code == 404
    assert client.get(stored["url"]).json()["detail"]["error"] == "project_not_found"
    app.dependency_overrides[get_current_active_user] = lambda: make_user(AccountType.ADMIN, user_id="admin-1")
    assert client.get(stored["url"]).status_code == 200
    admin = _upload(client, project["id"], "other.ply", samples.ply()).json()["data"]["file"]
    assert files.get_file(admin["id"])["user_id"] == "user-1"


def test_a_scene_file_is_read_only_through_its_own_project(client, project, make_project, samples):
    other = make_project()
    stored = _upload(client, project["id"], "set.ply", samples.ply()).json()["data"]["file"]

    assert client.get(f"{BASE}/projects/{other['id']}/scene-files/{stored['id']}").json()["detail"]["error"] == "file_not_found"
    assert client.get(f"{BASE}/projects/{project['id']}/scene-files/01M5NOTAFILE00000000000000").status_code == 404
    files.path_of(files.get_file(stored["id"])).unlink()
    assert client.get(stored["url"]).json()["detail"]["error"] == "file_not_found"
