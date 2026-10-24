import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

import pytest
from fastapi.routing import APIRoute

from backend import chain, core_bridge, presets, settings, takes, tracker
from backend.api import router
from backend.exports import jobs, video
from backend.scene3d import files as scene_files
from backend.scene3d import renders, storage
from backend.scene3d.formats import Probe
from src.plugin_api import get_current_active_user

BASE = "/api/plugins/video-producer"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
README = PLUGIN_ROOT / "README.md"
REFERENCE = PLUGIN_ROOT / "tests" / "fixtures" / "exports" / "reference-project.json"
SHOTS = [{"id": "s1", "start": 0, "dur": 4}, {"id": "s2", "start": 4, "dur": 4}]
ORDER = {"shots": ["s1"], "quality": "draft", "variants": 1, "preset_id": presets.WAN}
TAKE_FIELDS = ("shot_id", "generation_id", "file_id", "file_path", "status", "quality", "kind", "chosen")
LIVENESS = {"GET /health"}
DOCUMENTED = re.compile(r"`(GET|POST|PUT|DELETE|PATCH) (/[^`?\s]*)")
ANONYMOUS = "anonymous"
END_SHOT = "01M5R0CLIP0000000000000002"


def _shape(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def _documented():
    found, inside = set(), False
    for line in README.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            inside = line.strip() == "### Routes"
            continue
        if inside:
            found.update(f"{method} {_shape(path)}" for method, path in DOCUMENTED.findall(line))
    return found


def _api_routes():
    return {
        f"{method} {_shape(route.path.removeprefix(BASE))}": route
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


class Call(NamedTuple):
    path: str
    body: Any = None
    status: int = 200
    code: Optional[str] = None
    who: str = "user-1"
    check: Optional[Callable[[Any], bool]] = None
    files: Optional[dict] = None


class Route(NamedTuple):
    success: Callable[["World"], Call]
    denied: Callable[["World"], Call]
    invalid: Optional[Callable[["World"], Call]] = None


class World:
    def __init__(self, app, client, core, store, make_user, make_project, monkeypatch, samples):
        self.app, self.client, self.core, self.store, self.make_user = app, client, core, store, make_user
        self.samples = samples
        self.ply = samples.ply(count=2)
        self.jpeg = samples.data_url(samples.jpeg(), "jpeg")
        self.png = samples.data_url(samples.png(), "png")
        core.use_wan()
        core.use_seedvr2()
        core.use_splat()
        monkeypatch.setattr(video, "assemble", self._assemble)
        monkeypatch.setattr(core_bridge, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
        monkeypatch.setattr(core_bridge, "find_ffprobe", lambda: "/usr/bin/ffprobe")
        monkeypatch.setattr(core_bridge, "media_file_path", lambda kind, value: f"/srv/storage/{value}")
        monkeypatch.setattr(core_bridge, "enabled_backends", lambda: [])
        monkeypatch.setattr(core_bridge, "preset_driver", lambda preset_id: None)
        monkeypatch.setattr(core_bridge, "extract_frame", self._extract_frame)
        monkeypatch.setattr(core_bridge, "upload_item", self._upload_item)
        monkeypatch.setattr(core_bridge, "local_media_file", lambda kind, value, folder: Path(folder) / "source.mp4")
        monkeypatch.setattr(core_bridge, "probe_video", lambda path: None)
        monkeypatch.setattr(core_bridge, "save_user_media", self._save_user_media)
        monkeypatch.setattr(chain, "run", self._run)
        monkeypatch.setattr(core_bridge, "resolve_media", self._resolve_as_owner(core.resolve_media))
        core.add_media({"kind": "library", "item_id": "item-1"}, "uploads/still.png", media_type="image")
        core.add_media({"kind": "library", "item_id": "item-user-1"}, "uploads/upload.png", media_type="image")
        self.project = make_project(clips=SHOTS, assets=[{"id": "still", "kind": "image", "origin": {"kind": "library", "itemId": "item-1"}}])
        self.reference = self._reference(make_project)
        self.done = self.take("s1", "done")

    @staticmethod
    def _resolve_as_owner(resolve):
        def resolve_media(user, ref):
            if user.id != "user-1":
                raise core_bridge.MediaRefError("not_found", "The referenced media is not available")
            return resolve(user, ref)

        return resolve_media

    @staticmethod
    async def _extract_frame(user, ref, at="last"):
        return {"value": "uploads/frame.png", "media_type": "image", "original_filename": "frame.png", "origin": None}

    @staticmethod
    async def _run(command):
        Path(command[-1]).write_bytes(b"png")

    @staticmethod
    async def _save_user_media(user, path):
        return {"value": "uploads/frame.png", "media_type": "image", "original_filename": Path(path).name, "origin": None}

    @staticmethod
    async def _assemble(command, total, on_progress=None, on_process=None, cwd=None, code="ffmpeg_failed"):
        (Path(cwd) / command[-1]).write_bytes(b"mp4")

    @staticmethod
    def _upload_item(user_id, value):
        return {"item_id": f"item-{user_id}", "filename": "frame.png", "width": 832, "height": 480}

    def _reference(self, make_project):
        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        created = make_project(doc=reference["doc"])
        for take in reference["takes"]:
            takes.create_take({**{key: take[key] for key in TAKE_FIELDS}, "project_id": created["id"], "user_id": "user-1"})
        for upload in reference["uploads"]:
            self.core.add_media({"kind": "library", "item_id": upload["item_id"]}, upload["value"], media_type=upload["media_type"])
        return created

    @property
    def pid(self) -> str:
        return self.project["id"]

    def doc(self, name: Optional[str] = None):
        return {**self.project["doc"], **({"name": name} if name else {})}

    def take(self, shot_id: str, end: Optional[str] = None):
        response = self.client.post(f"{BASE}/projects/{self.pid}/generate", json={**ORDER, "shots": [shot_id]})
        assert response.status_code == 202, response.text
        (take,) = response.json()["data"]["takes"]
        generation_id = take["generation_id"]
        if end == "done":
            self.core.complete(generation_id)
            ref = {"kind": "history", "generation_id": generation_id, "file_id": f"file-{generation_id}"}
            self.core.add_media(ref, f"generations/2026-10-17/{generation_id}/1.mp4", "VIDEO")
        elif end == "failed":
            self.core.fail(generation_id)
        if end:
            asyncio.run(tracker.Tracker().tick())
        return takes.get_take(take["id"])

    def waiting(self):
        fields = {"project_id": self.pid, "shot_id": "s2", "user_id": "user-1", "quality": "draft", "kind": "render"}
        return [takes.create_take(fields) for _ in range(2)][-1]

    def scene_job(self) -> str:
        response = self.client.post(f"{BASE}/projects/{self.pid}/scenes/from-image", json={"sceneId": "sc-1", "assetId": "still", "time": None})
        assert response.status_code == 202, response.text
        return response.json()["data"]["job"]["id"]

    def scene_file(self) -> str:
        file_id = core_bridge.generate_ulid()
        folder = storage.project_folder(self.pid)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / scene_files.stored_name(file_id, "ply")).write_bytes(self.ply)
        scene_files.add_file(file_id, self.pid, "user-1", "splat", "set.ply", len(self.ply), Probe(format="ply", count=2))
        return file_id

    def render(self, done: bool = False) -> str:
        render = renders.create(self.pid, "user-1", 64, 36, 24.0, 1, "Guide")
        if done:
            renders.add_frames(render, 0, [self.samples.jpeg()])
        return render["id"]

    def job(self, done: bool = False) -> str:
        job = jobs.create_job(self.pid, "user-1", "web", "1080p")
        if done:
            folder = video.job_folder(job)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "cut_1080p.mp4").write_bytes(b"x" * 11)
            jobs.claim_next()
            jobs.settle(
                job["id"], "done", progress=100.0, step=None, file_name="cut_1080p.mp4", file_size=11,
                media_item_id="item-1", media_url="/api/media/uploads/u.mp4",
            )
        return job["id"]

    def footprint(self):
        from src.plugin_api import db

        with db.get_cursor() as cursor:
            cursor.execute("SELECT id, version, doc FROM video_producer_projects ORDER BY id")
            projects = [tuple(row) for row in cursor.fetchall()]
            cursor.execute("SELECT project_id, version, label FROM video_producer_versions ORDER BY project_id, version")
            versions = [tuple(row) for row in cursor.fetchall()]
            cursor.execute("SELECT id, status, chosen, flag, label, priority FROM video_producer_takes ORDER BY id")
            rows = [tuple(row) for row in cursor.fetchall()]
            cursor.execute("SELECT id, status FROM video_producer_export_jobs ORDER BY id")
            exports = [tuple(row) for row in cursor.fetchall()]
            cursor.execute("SELECT id, status FROM video_producer_scene_jobs ORDER BY id")
            scene_jobs = [tuple(row) for row in cursor.fetchall()]
            cursor.execute("SELECT id FROM video_producer_scene_files ORDER BY id")
            scenes = [tuple(row) for row in cursor.fetchall()]
        base = storage.scenes_base()
        disk = sorted(str(path.relative_to(base)) for path in base.rglob("*")) if base.exists() else []
        return projects, versions, rows, exports, scene_jobs, scenes, disk, dict(self.store), len(self.core.submitted), len(self.core.cancelled)

    def send(self, method: str, call: Call):
        if call.who == ANONYMOUS:
            self.app.dependency_overrides.pop(get_current_active_user, None)
        else:
            user = self.make_user(user_id=call.who)
            self.app.dependency_overrides[get_current_active_user] = lambda: user
        if call.files is not None:
            options = {"files": call.files, "data": call.body or {}}
        else:
            options = {} if call.body is None else {"json": call.body}
        return self.client.request(method, f"{BASE}{call.path}", **options)


def _data(response):
    return response.json()["data"]


def _list_scene_jobs(w):
    job_id = w.scene_job()
    return Call(f"/projects/{w.pid}/scenes/jobs", check=lambda r: [job["id"] for job in _data(r)["jobs"]] == [job_id])


def _upload(w, kind="splat", who="user-1", status=201, code=None, check=None):
    return Call(f"/projects/{w.pid}/scene-files", {"kind": kind}, status, code, who, check, files={"file": ("set.ply", w.ply, "application/octet-stream")})


def _get_me_of_another_user(w):
    settings.set_last_project_id("user-1", w.pid)
    return Call("/me", who="user-2", check=lambda r: _data(r)["last_project_id"] is None)


ROUTES = {
    "GET /projects": Route(
        success=lambda w: Call("/projects", check=lambda r: w.pid in [p["id"] for p in _data(r)["projects"]]),
        denied=lambda w: Call("/projects", who="user-2", check=lambda r: _data(r)["projects"] == []),
    ),
    "POST /projects": Route(
        success=lambda w: Call("/projects", {"doc": w.doc()}, 201, check=lambda r: _data(r)["project"]["version"] == 1),
        denied=lambda w: Call("/projects", {"doc": w.doc()}, 401, who=ANONYMOUS),
        invalid=lambda w: Call("/projects", {"doc": w.doc(), "name": 3}, 422, "invalid_request"),
    ),
    "GET /projects/{id}": Route(
        success=lambda w: Call(f"/projects/{w.pid}", check=lambda r: _data(r)["project"]["id"] == w.pid),
        denied=lambda w: Call(f"/projects/{w.pid}", status=404, code="project_not_found", who="user-2"),
    ),
    "PUT /projects/{id}": Route(
        success=lambda w: Call(
            f"/projects/{w.pid}", {"doc": w.doc("Renamed"), "version": 1, "label": "Assistant"},
            check=lambda r: _data(r)["project"]["version"] == 2,
        ),
        denied=lambda w: Call(f"/projects/{w.pid}", {"doc": w.doc("Taken"), "version": 1}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}", {"doc": w.doc("Renamed"), "version": "1"}, 422, "invalid_request"),
    ),
    "DELETE /projects/{id}": Route(
        success=lambda w: Call(f"/projects/{w.pid}", check=lambda r: _data(r) == {"deleted": w.pid}),
        denied=lambda w: Call(f"/projects/{w.pid}", status=404, code="project_not_found", who="user-2"),
    ),
    "GET /projects/{id}/versions": Route(
        success=lambda w: Call(f"/projects/{w.pid}/versions", check=lambda r: [v["version"] for v in _data(r)["versions"]] == [1]),
        denied=lambda w: Call(f"/projects/{w.pid}/versions", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/versions/{version}/restore": Route(
        success=lambda w: Call(f"/projects/{w.pid}/versions/1/restore", check=lambda r: _data(r)["project"]["version"] == 2),
        denied=lambda w: Call(f"/projects/{w.pid}/versions/1/restore", status=404, code="project_not_found", who="user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/versions/latest/restore", status=404, code="version_not_found"),
    ),
    "POST /media/resolve": Route(
        success=lambda w: Call(
            "/media/resolve", {"origin": {"kind": "library", "itemId": "item-1"}},
            check=lambda r: _data(r)["media"]["url"] == "/api/media/uploads/still.png",
        ),
        denied=lambda w: Call("/media/resolve", {"origin": {"kind": "library", "itemId": "item-1"}}, 404, "media_not_found", "user-2"),
        invalid=lambda w: Call("/media/resolve", {"origin": "library"}, 422, "invalid_request"),
    ),
    "POST /media/uploaded": Route(
        success=lambda w: Call("/media/uploaded", {"filename": "upload.png"}, check=lambda r: _data(r)["media"]["origin"] == {"kind": "library", "itemId": "item-user-1"}),
        denied=lambda w: Call("/media/uploaded", {"filename": "upload.png"}, 404, "media_not_found", "user-2"),
        invalid=lambda w: Call("/media/uploaded", {"filename": "uploads/upload.png"}, 422, "invalid_request"),
    ),
    "GET /projects/{id}/takes": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes", check=lambda r: w.done["id"] in [t["id"] for t in _data(r)["takes"]]),
        denied=lambda w: Call(f"/projects/{w.pid}/takes", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/estimate": Route(
        success=lambda w: Call(f"/projects/{w.pid}/estimate", ORDER, check=lambda r: _data(r)["blocks"] == []),
        denied=lambda w: Call(f"/projects/{w.pid}/estimate", ORDER, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/estimate", {**ORDER, "variants": 0}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/generate": Route(
        success=lambda w: Call(f"/projects/{w.pid}/generate", ORDER, 202, check=lambda r: len(_data(r)["takes"]) == 1),
        denied=lambda w: Call(f"/projects/{w.pid}/generate", ORDER, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/generate", {**ORDER, "quality": "best"}, 422, "invalid_request"),
    ),
    "GET /projects/{id}/queue": Route(
        success=lambda w: Call(f"/projects/{w.pid}/queue", check=lambda r: _data(r)["slots"]["max"] == 2),
        denied=lambda w: Call(f"/projects/{w.pid}/queue", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/takes/{take}/label": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/label", {"label": "candidate"}, check=lambda r: _data(r)["take"]["label"] == "candidate"),
        denied=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/label", {"label": "final"}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/label", {"label": "keep"}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/takes/{take}/prioritize": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes/{w.waiting()['id']}/prioritize", check=lambda r: _data(r)["take"]["priority"] == 1),
        denied=lambda w: Call(f"/projects/{w.pid}/takes/{w.waiting()['id']}/prioritize", status=404, code="project_not_found", who="user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/prioritize", status=409, code="take_not_queued"),
    ),
    "POST /projects/{id}/takes/{take}/choose": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/choose", {"chosen": True}, check=lambda r: _data(r)["take"]["chosen"]),
        denied=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/choose", {"chosen": True}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/choose", {"chosen": "yes"}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/takes/{take}/flag": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/flag", {"flag": "keep"}, check=lambda r: _data(r)["take"]["flag"] == "keep"),
        denied=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/flag", {"flag": "keep"}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/flag", {"flag": "favori"}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/takes/{take}/final": Route(
        success=lambda w: Call(
            f"/projects/{w.pid}/takes/{w.done['id']}/final", {"method": "upscale", "target": "fhd1080"}, 202,
            check=lambda r: (_data(r)["take"]["kind"], _data(r)["take"]["parent_take_id"]) == ("upscale", w.done["id"]),
        ),
        denied=lambda w: Call(
            f"/projects/{w.pid}/takes/{w.done['id']}/final", {"method": "upscale", "target": "fhd1080"}, 404, "project_not_found", "user-2"
        ),
        invalid=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}/final", {"method": "upscale", "target": "8k"}, 422, "invalid_request"),
    ),
    "DELETE /projects/{id}/takes/{take}": Route(
        success=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}", check=lambda r: _data(r) == {"deleted": w.done["id"]}),
        denied=lambda w: Call(f"/projects/{w.pid}/takes/{w.done['id']}", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /takes/{take}/cancel": Route(
        success=lambda w: Call(f"/takes/{w.take('s2')['id']}/cancel", check=lambda r: _data(r)["take"]["status"] == "cancelled"),
        denied=lambda w: Call(f"/takes/{w.take('s2')['id']}/cancel", status=404, code="take_not_found", who="user-2"),
    ),
    "POST /takes/{take}/retry": Route(
        success=lambda w: Call(f"/takes/{w.take('s2', 'failed')['id']}/retry", status=202, check=lambda r: _data(r)["take"]["shot_id"] == "s2"),
        denied=lambda w: Call(f"/takes/{w.take('s2', 'failed')['id']}/retry", status=404, code="take_not_found", who="user-2"),
    ),
    "GET /projects/{id}/exports/{format}": Route(
        success=lambda w: Call(
            f"/projects/{w.reference['id']}/exports/fcpxml?media=name",
            check=lambda r: r.headers["content-type"].startswith("application/xml"),
        ),
        denied=lambda w: Call(f"/projects/{w.reference['id']}/exports/fcpxml", status=404, code="project_not_found", who="user-2"),
        invalid=lambda w: Call(f"/projects/{w.reference['id']}/exports/mov", status=422, code="invalid_request"),
    ),
    "GET /projects/{id}/exports": Route(
        success=lambda w: Call(f"/projects/{w.pid}/exports", check=lambda r: _data(r)["jobs"] == []),
        denied=lambda w: Call(f"/projects/{w.pid}/exports", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/exports/video": Route(
        success=lambda w: Call(
            f"/projects/{w.reference['id']}/exports/video", {"format": "web"}, 202,
            check=lambda r: _data(r)["job"]["status"] == "queued",
        ),
        denied=lambda w: Call(f"/projects/{w.reference['id']}/exports/video", {"format": "web"}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.reference['id']}/exports/video", {"format": "mov"}, 422, "invalid_request"),
    ),
    "GET /exports/{job}": Route(
        success=lambda w: Call(f"/exports/{w.job()}", check=lambda r: _data(r)["job"]["status"] == "queued"),
        denied=lambda w: Call(f"/exports/{w.job()}", status=404, code="job_not_found", who="user-2"),
    ),
    "GET /exports/{job}/file": Route(
        success=lambda w: Call(f"/exports/{w.job(done=True)}/file", check=lambda r: r.headers["content-type"] == "video/mp4"),
        denied=lambda w: Call(f"/exports/{w.job(done=True)}/file", status=404, code="job_not_found", who="user-2"),
    ),
    "DELETE /exports/{job}": Route(
        success=lambda w: Call(f"/exports/{w.job()}", check=lambda r: _data(r)["job"]["status"] == "cancelled"),
        denied=lambda w: Call(f"/exports/{w.job()}", status=404, code="job_not_found", who="user-2"),
    ),
    "POST /projects/{id}/shots/{shot}/seam-frame": Route(
        success=lambda w: Call(f"/projects/{w.pid}/shots/s2/seam-frame", check=lambda r: _data(r)["media"]["item_id"] == "item-user-1"),
        denied=lambda w: Call(f"/projects/{w.pid}/shots/s2/seam-frame", status=404, code="project_not_found", who="user-2"),
        invalid=lambda w: Call(
            f"/projects/{w.pid}/shots/s2/seam-frame", {"source": {"take_id": w.done["id"], "at": -1}}, 422, "invalid_request"
        ),
    ),
    "POST /projects/{id}/shots/{shot}/end-frame": Route(
        success=lambda w: Call(
            f"/projects/{w.reference['id']}/shots/{END_SHOT}/end-frame",
            check=lambda r: (_data(r)["source"]["at"], _data(r)["media"]["filename"]) == (4.6, "1-frame-4.6s.png"),
        ),
        denied=lambda w: Call(f"/projects/{w.reference['id']}/shots/{END_SHOT}/end-frame", status=404, code="project_not_found", who="user-2"),
        invalid=lambda w: Call(f"/projects/{w.reference['id']}/shots/nope/end-frame", status=404, code="shot_not_found"),
    ),
    "POST /projects/{id}/scenes/from-image": Route(
        success=lambda w: Call(
            f"/projects/{w.pid}/scenes/from-image", {"sceneId": "sc-1", "assetId": "still", "time": None, "name": "Still"}, 202,
            check=lambda r: _data(r)["job"]["status"] == "queued",
        ),
        denied=lambda w: Call(f"/projects/{w.pid}/scenes/from-image", {"sceneId": "sc-1", "assetId": "still", "time": None}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/scenes/from-image", {"sceneId": "sc-1", "assetId": "still", "time": -1}, 422, "invalid_request"),
    ),
    "GET /projects/{id}/scenes/jobs": Route(
        success=_list_scene_jobs,
        denied=lambda w: Call(f"/projects/{w.pid}/scenes/jobs", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/scenes/jobs/{job}/cancel": Route(
        success=lambda w: Call(f"/projects/{w.pid}/scenes/jobs/{w.scene_job()}/cancel", check=lambda r: _data(r)["job"]["status"] == "cancelled"),
        denied=lambda w: Call(f"/projects/{w.pid}/scenes/jobs/{w.scene_job()}/cancel", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/scene-files": Route(
        success=lambda w: _upload(w, check=lambda r: (_data(r)["file"]["format"], _data(r)["file"]["count"]) == ("ply", 2)),
        denied=lambda w: _upload(w, who="user-2", status=404, code="project_not_found"),
        invalid=lambda w: _upload(w, kind="mesh", status=422, code="invalid_request"),
    ),
    "GET /projects/{id}/scene-files/{file}": Route(
        success=lambda w: Call(f"/projects/{w.pid}/scene-files/{w.scene_file()}", check=lambda r: r.content == w.ply),
        denied=lambda w: Call(f"/projects/{w.pid}/scene-files/{w.scene_file()}", status=404, code="project_not_found", who="user-2"),
    ),
    "POST /projects/{id}/captures": Route(
        success=lambda w: Call(f"/projects/{w.pid}/captures", {"png": w.png, "name": "Capture"}, check=lambda r: _data(r)["media"]["item_id"] == "item-user-1"),
        denied=lambda w: Call(f"/projects/{w.pid}/captures", {"png": w.png, "name": "Capture"}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/captures", {"png": w.jpeg, "name": "Capture"}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/renders": Route(
        success=lambda w: Call(f"/projects/{w.pid}/renders", {"width": 64, "height": 36, "fps": 24, "frames": 2}, 201, check=lambda r: _data(r)["render"]["frames"] == 2),
        denied=lambda w: Call(f"/projects/{w.pid}/renders", {"width": 64, "height": 36, "fps": 24, "frames": 2}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/renders", {"width": 63, "height": 36, "fps": 24, "frames": 2}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/renders/{render}/frames": Route(
        success=lambda w: Call(f"/projects/{w.pid}/renders/{w.render()}/frames", {"start": 0, "images": [w.jpeg]}, check=lambda r: _data(r) == {"received": 1}),
        denied=lambda w: Call(f"/projects/{w.pid}/renders/{w.render()}/frames", {"start": 0, "images": [w.jpeg]}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call(f"/projects/{w.pid}/renders/{w.render()}/frames", {"start": 0, "images": [w.png]}, 422, "invalid_request"),
    ),
    "POST /projects/{id}/renders/{render}/finish": Route(
        success=lambda w: Call(f"/projects/{w.pid}/renders/{w.render(done=True)}/finish", check=lambda r: _data(r)["media"]["media_type"] == "video"),
        denied=lambda w: Call(f"/projects/{w.pid}/renders/{w.render(done=True)}/finish", status=404, code="project_not_found", who="user-2"),
    ),
    "DELETE /projects/{id}/renders/{render}": Route(
        success=lambda w: Call(f"/projects/{w.pid}/renders/{w.render()}", check=lambda r: _data(r) == {}),
        denied=lambda w: Call(f"/projects/{w.pid}/renders/{w.render()}", status=404, code="project_not_found", who="user-2"),
    ),
    "GET /me": Route(
        success=lambda w: Call("/me", check=lambda r: _data(r)["plugin"]["id"] == "video-producer"),
        denied=_get_me_of_another_user,
    ),
    "PUT /me": Route(
        success=lambda w: Call("/me", {"locale": "fr"}, check=lambda r: _data(r)["locale"] == "fr"),
        denied=lambda w: Call("/me", {"last_project_id": w.pid}, 404, "project_not_found", "user-2"),
        invalid=lambda w: Call("/me", {"locale": "de"}, 422, "invalid_locale"),
    ),
}


@pytest.fixture
def world(app, client, core, store, export_storage, media_store, make_user, make_project, monkeypatch, samples):
    return World(app, client, core, store, make_user, make_project, monkeypatch, samples)


def _check(response, call):
    assert response.status_code == call.status, response.text
    if call.code is not None:
        assert response.json()["detail"]["error"] == call.code
    if call.check is not None:
        assert call.check(response)


def test_the_readme_lists_every_route_the_api_serves():
    assert _documented() - LIVENESS == set(_api_routes()) - LIVENESS


def test_every_documented_route_has_a_success_a_refusal_and_an_invalid_request_case():
    shaped = {_shape(key): route for key, route in ROUTES.items()}
    with_body = {key for key, route in _api_routes().items() if route.body_field is not None}

    assert set(shaped) == _documented() - LIVENESS
    assert with_body <= set(shaped)
    assert sorted(key for key in with_body if shaped[key].invalid is None) == []


@pytest.mark.parametrize("key", sorted(ROUTES))
def test_each_route_succeeds_for_the_owner_of_the_project(world, key):
    method, _ = key.split(" ", 1)
    call = ROUTES[key].success(world)

    _check(world.send(method, call), call)


@pytest.mark.parametrize("key", sorted(ROUTES))
def test_each_route_refuses_another_user_and_changes_nothing(world, key):
    method, _ = key.split(" ", 1)
    call = ROUTES[key].denied(world)
    before = world.footprint()

    response = world.send(method, call)

    _check(response, call)
    assert call.who != "user-1"
    assert world.footprint() == before


@pytest.mark.parametrize("key", sorted(key for key, route in ROUTES.items() if route.invalid is not None))
def test_each_route_refuses_an_invalid_body_or_parameter_and_changes_nothing(world, key):
    method, _ = key.split(" ", 1)
    call = ROUTES[key].invalid(world)
    before = world.footprint()

    response = world.send(method, call)

    _check(response, call)
    assert world.footprint() == before


@pytest.mark.parametrize("key", sorted(ROUTES))
def test_each_route_needs_a_signed_in_user(world, key):
    method, _ = key.split(" ", 1)
    call = ROUTES[key].success(world)
    before = world.footprint()

    response = world.send(method, call._replace(who=ANONYMOUS))

    assert response.status_code == 401
    assert world.footprint() == before
