import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.projects import DOC_SCHEMA, MAX_DOC_BYTES, DocError, canonical, migrate, summary, validate_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def starter():
    return _fixture("starter_doc")


def _audio_asset(**fields):
    return {
        "id": "01M535B4GTAUDIO00000000000",
        "kind": "audio",
        "name": "Wind on the ridge",
        "src": None,
        "origin": None,
        "srcDur": 12.0,
        "width": None,
        "height": None,
        "fps": None,
        "res": None,
        "generated": True,
        "quality": None,
        "resultId": None,
        "role": "Ambiance",
        **fields,
    }


def _video_asset(**fields):
    return {
        "id": "01M535B4GTVIDEO00000000000",
        "kind": "video",
        "name": "Ridge.mov",
        "src": "/api/media/uploads/ridge.mov",
        "origin": {"kind": "library", "itemId": "01M535B4GTUPLOAD000000000"},
        "srcDur": 12.5,
        "width": 1920,
        "height": 1080,
        "fps": 25,
        "res": "1920×1080",
        "generated": False,
        "quality": None,
        "resultId": None,
        "role": None,
        **fields,
    }


def _splat_scene(**fields):
    return {
        "id": "01M535B4GTSCENE00000000000",
        "kind": "splat",
        "name": "Ridge",
        "sourceAssetId": "01M535B4GTVIDEO00000000000",
        "sourceTime": 2.5,
        "status": "done",
        "progress": 100,
        "jobId": "01M535B4GTJOB0000000000000",
        "fileId": "01M535B4GTFILE20000000000",
        "count": 524288,
        "view": {"fov": 48.5, "aspect": 1.7778, "depth": 4.0},
        "error": None,
        **fields,
    }


def _rich(doc):
    clip = doc["clips"][0]
    doc["clips"][1].update(assetId="gen-01M535B4GTRESULT00000000", take="01M535B4GTRESULT00000000", stage="draft", flag="favori")
    doc["clips"][2]["flag"] = "rejet"
    doc["audio"].append(
        {
            "id": "01M535B4GTAUDIOCLIP0000000",
            "assetId": "01M535B4GTAUDIO00000000000",
            "lane": "A3",
            "start": 2,
            "dur": 30.5,
            "srcIn": 0,
            "fadeIn": 0.5,
            "fadeOut": 0.8,
            "gain": -6,
        }
    )
    doc["frames"].append(
        {
            "id": "01M535B4GTFRAME00000000000",
            "shotId": clip["id"],
            "time": 1.2,
            "assetId": "01M535B4GTVIDEO00000000000",
            "role": "first",
            "strength": 100,
        }
    )
    doc["references"] += [
        {
            "id": "01M535B4GTREF0000000000000",
            "name": "Hiker",
            "space": "identite",
            "type": "Personnage",
            "assetId": None,
            "role": "Identité",
            "scope": {"type": "global"},
        },
        {
            "id": "01M535B4GTREF1000000000000",
            "name": "Hut",
            "space": "decors3d",
            "type": "Capture 3D",
            "assetId": "01M535B4GTVIDEO00000000000",
            "role": "Décor",
            "scope": {"type": "shot", "shotId": clip["id"]},
        },
        {
            "id": "01M535B4GTREF2000000000000",
            "name": "Path",
            "space": "mouvement",
            "type": "Trajectoire",
            "assetId": None,
            "role": "Mouvement",
            "scope": None,
        },
        {
            "id": "01M535B4GTCONTROL000000000",
            "name": "Guide 3D",
            "space": "mouvement",
            "type": "Control video",
            "assetId": "01M535B4GTVIDEO00000000000",
            "role": "Mouvement",
            "scope": {"type": "shot", "shotId": clip["id"]},
        },
    ]
    doc["lanes"][0]["inserts"].append({"type": "filter", "on": True, "cutoff": 8000})
    doc["profiles"].append({"id": "01M535B4GTPROFILE000000000", "name": "Profile 1", "weights": dict(doc["hybrid"])})
    doc["engine"]["loras"].append({"name": "Film grain", "weight": 0.55})
    doc["assets"] += [_audio_asset(), _video_asset()]
    return doc


def _error(doc):
    with pytest.raises(DocError) as caught:
        validate_doc(doc)
    return caught.value


def test_the_schema_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(DOC_SCHEMA)
    assert DOC_SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("name", ["starter_doc", "empty_doc"])
def test_the_documents_the_editor_starts_from_are_valid(name):
    doc = _fixture(name)

    assert validate_doc(doc) == canonical(doc)


def test_a_document_using_every_collection_is_valid(starter):
    validate_doc(_rich(starter))


def test_the_reference_project_is_valid_and_current():
    doc = _fixture("exports/reference-project")["doc"]

    assert validate_doc(doc) == canonical(doc)
    assert migrate(doc) is doc
    assert not {"scenes", "controls", "plans3d"} & set(doc)


def test_an_audio_asset_and_a_video_asset_without_audio_fields_are_valid(starter):
    starter["assets"] = [
        _audio_asset(role="Dialogue", src="/api/media/uploads/line.wav", generated=False),
        _video_asset(
            id="gen-01M535B4GTRESULT00000000",
            src=None,
            origin={"kind": "history", "generationId": "01M535GENERATION000000000", "fileId": "01M535FILE00000000000000"},
            generated=True,
            quality="final",
            resultId="01M535B4GTRESULT00000000",
            width=None,
            height=None,
            fps=None,
            res=None,
            srcDur=None,
        ),
    ]

    validate_doc(starter)


@pytest.mark.parametrize(
    "path, value",
    [
        (["clips", 0, "assetId"], None),
        (["clips", 0, "take"], None),
        (["clips", 0, "flag"], None),
        (["prompts", 0, "shotId"], None),
        (["engine", "seed"], None),
        (["engine", "steps"], None),
        (["engine", "guidance"], None),
        (["engine", "variants"], None),
    ],
)
def test_null_is_accepted_where_the_editor_leaves_a_value_out(starter, path, value):
    target = starter
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    validate_doc(starter)


@pytest.mark.parametrize(
    "engine",
    [
        {},
        {"preset": "01KX47WANVIDEO0000000000TV"},
        {"preset": "01M3SV8HJTGT3JPPH2BA5MP6PR", "model": "cm-veo"},
        {"preset": None, "model": None},
        {"backend": "b-local"},
        {"backend": "cloud"},
    ],
)
def test_the_engine_may_name_a_backend_a_preset_and_a_cloud_model(starter, engine):
    starter["engine"].update(engine)

    validate_doc(starter)


@pytest.mark.parametrize(
    "engine, path",
    [({"preset": 3}, "$.engine.preset"), ({"model": ["cm-veo"]}, "$.engine.model"), ({"backend": None}, "$.engine.backend")],
)
def test_the_engine_preset_and_model_are_text_or_null(starter, engine, path):
    starter["engine"].update(engine)

    assert str(_error(starter)).startswith(f"{path}: ")


def test_the_schema_no_longer_holds_the_simulated_takes(starter):
    starter["results"] = []

    assert "results" not in DOC_SCHEMA["properties"]
    assert str(_error(starter)) == "$: Additional properties are not allowed ('results' was unexpected)"


LEGACY_RESULT = {
    "id": "01M535B4GTRESULT00000000",
    "clipId": "c1",
    "quality": "draft",
    "variant": "A",
    "assetId": None,
    "look": "warm",
    "status": "chosen",
    "seed": 48121,
    "created": "12:04",
    "range": [5, 10],
    "local": "A slow climb",
    "parent": None,
    "profile": "FL2VA",
    "mode": "Génération IA",
    "backend": "local",
}


def test_migrating_a_document_drops_the_simulated_takes_and_keeps_the_rest(starter):
    legacy = {**copy.deepcopy(starter), "results": [LEGACY_RESULT]}

    migrated = migrate(legacy)

    assert migrated == starter and "results" in legacy
    assert validate_doc(migrated) == canonical(starter)


@pytest.mark.parametrize("doc", [None, [], "doc", 3])
def test_migrating_leaves_a_value_that_is_not_an_object_alone(doc):
    assert migrate(doc) is doc


def test_migrating_a_current_document_returns_it_as_it_is(starter):
    assert migrate(starter) is starter


def test_a_missing_assets_collection_is_refused_with_its_path(starter):
    del starter["assets"]

    error = _error(starter)

    assert error.code == "invalid_doc"
    assert str(error) == "$: 'assets' is a required property"


@pytest.mark.parametrize(
    "mutate, path, reason",
    [
        (lambda d: d.update(theme="dark"), "$", "'theme' was unexpected"),
        (lambda d: d["clips"][0].update(extra=1), "$.clips[0]", "'extra' was unexpected"),
        (lambda d: d["lanes"][0]["inserts"][0].update(cutoff=8000), "$.lanes[0].inserts[0]", "'cutoff' was unexpected"),
        (lambda d: d["engine"]["post"].update(sharpen=True), "$.engine.post", "'sharpen' was unexpected"),
        (lambda d: d["clips"][2].update(start="10"), "$.clips[2].start", "'10' is not of type 'number'"),
        (lambda d: d["clips"][0].update(stage="done"), "$.clips[0].stage", "'done' is not one of"),
        (lambda d: d["clips"][0].update(flag="maybe"), "$.clips[0].flag", "'maybe' is not one of"),
        (lambda d: d["lanes"][0].update(mute="no"), "$.lanes[0].mute", "'no' is not of type 'boolean'"),
        (lambda d: d.update(fps=True), "$.fps", "True is not of type 'number'"),
        (lambda d: d["clips"][1].update(id=""), "$.clips[1].id", "should be non-empty"),
        (lambda d: d["titles"][0].update(id=""), "$.titles[0].id", "should be non-empty"),
        (lambda d: d["clips"][0].update(assetId=""), "$.clips[0].assetId", "should be non-empty"),
        (lambda d: d["prompts"][0].pop("text"), "$.prompts[0]", "'text' is a required property"),
        (lambda d: d.update(clips={}), "$.clips", "{} is not of type 'array'"),
        (lambda d: d["markers"].append({"id": "m", "time": 1, "label": "x"}), "$.markers[1]", "'kind' is a required"),
    ],
)
def test_an_invalid_document_names_the_json_path_at_fault(starter, mutate, path, reason):
    mutate(starter)

    error = _error(starter)

    assert error.code == "invalid_doc"
    assert str(error).startswith(f"{path}: ")
    assert reason in str(error)


@pytest.mark.parametrize(
    "asset, path",
    [
        (_audio_asset(kind="text"), "$.assets[0].kind"),
        (_audio_asset(role="Voix"), "$.assets[0].role"),
        ({**_audio_asset(), "synth": "wind"}, "$.assets[0]"),
        ({**_audio_asset(), "lipSync": None}, "$.assets[0]"),
        (_audio_asset(quality="preview"), "$.assets[0].quality"),
        (_video_asset(width=19.5), "$.assets[0].width"),
        (_video_asset(id=""), "$.assets[0].id"),
        (_video_asset(origin={"kind": "history", "generationId": "g"}), "$.assets[0].origin"),
        (_video_asset(origin={"kind": "library", "item_id": "i"}), "$.assets[0].origin"),
        (_video_asset(origin={"kind": "url", "href": "x"}), "$.assets[0].origin.kind"),
        ({key: value for key, value in _video_asset().items() if key != "role"}, "$.assets[0]"),
        ({**_video_asset(), "tags": []}, "$.assets[0]"),
    ],
)
def test_an_asset_outside_the_contract_is_refused(starter, asset, path):
    starter["assets"] = [asset]

    assert str(_error(starter)).startswith(f"{path}: ")


@pytest.mark.parametrize(
    "scene",
    [
        _splat_scene(),
        {"id": "s", "kind": "splatfile", "name": "set.spz", "fileId": "f", "format": "spz", "view": None},
        {"id": "s", "kind": "glb", "name": "hut.glb", "fileId": "f", "cameras": []},
        {"id": "s", "kind": "sample", "name": "Sample"},
    ],
)
def test_a_3d_scene_of_any_kind_is_no_longer_part_of_the_schema_and_the_migration_drops_it(starter, scene):
    starter["scenes"] = [scene]

    assert _error(starter).code == "invalid_doc"
    migrated = migrate(starter)
    assert "scenes" not in migrated
    validate_doc(migrated)


FRAME_ITEM = {"id": "f", "shotId": None, "time": 0, "assetId": None, "role": "first", "strength": 100}


def test_the_scene_of_a_frame_is_no_longer_part_of_the_schema_and_the_migration_forgets_it(starter):
    starter["frames"] = [{**FRAME_ITEM, "sceneId": "01M535B4GTSCENE00000000000"}, {**FRAME_ITEM, "id": "g", "sceneId": None}, {**FRAME_ITEM, "id": "h"}]
    before = copy.deepcopy(starter)

    assert _error(starter).code == "invalid_doc"
    migrated = migrate(starter)

    assert starter == before
    assert migrated["frames"] == [FRAME_ITEM, {**FRAME_ITEM, "id": "g"}, {**FRAME_ITEM, "id": "h"}]
    assert migrated["frames"][2] is starter["frames"][2]
    validate_doc(migrated)
    assert migrate(migrated) is migrated


LEGACY_SCENES = [
    {"id": "sc-sample", "kind": "sample", "name": "Sample set"},
    {"id": "sc-file", "kind": "file", "name": "set.ply", "file": "C:/scenes/set.ply"},
    {"id": "sc-glb", "kind": "glb", "name": "hut.glb", "fileId": "01M535B4GTFILE10000000000", "cameras": [{"name": "camera", "animated": True, "duration": 4.5}]},
]


def test_migrating_drops_every_3d_scene_simulated_imported_or_built_and_the_3d_shots_with_their_old_keyframes(starter):
    legacy = copy.deepcopy(starter)
    legacy["scenes"] = [*LEGACY_SCENES, _splat_scene()]
    legacy["plans3d"] = [
        {
            "id": "p1",
            "shotId": None,
            "sceneId": "sc-sample",
            "name": "Orbit",
            "start": 0,
            "dur": 5,
            "keyframes": [{"id": "p1-k0", "t": 0, "az": 90, "el": 30, "dist": 10, "focal": 30, "height": 1.5}],
        }
    ]
    before = copy.deepcopy(legacy)

    migrated = migrate(legacy)

    assert legacy == before
    assert "scenes" not in migrated and "plans3d" not in migrated
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_migrating_drops_the_3d_captures_without_an_image_and_keeps_the_other_frames(starter):
    starter["frames"] = [
        {"id": "f1", "shotId": None, "time": 1, "assetId": None, "role": "Capture 3D", "strength": 80},
        {"id": "f2", "shotId": None, "time": 2, "assetId": "a", "role": "Capture 3D", "strength": 80},
        {"id": "f3", "shotId": None, "time": 3, "assetId": None, "role": "Transition", "strength": 75},
    ]

    migrated = migrate(starter)

    assert [frame["id"] for frame in migrated["frames"]] == ["f2", "f3"]
    assert len(starter["frames"]) == 3
    assert migrate(migrated) is migrated


def test_migrating_drops_every_control_video_once_each_3d_guide_with_a_video_is_a_mouvement_reference(starter):
    rich = _rich(starter)
    shot = rich["clips"][0]["id"]
    video = "01M535B4GTVIDEO00000000000"
    converted = _control("01M535B4GTCONTROL000000000", video, shot_id=shot)
    simulated = _control("simulated", None)
    rich["controls"] = [
        simulated,
        converted,
        {k: v for k, v in simulated.items() if k not in ("planId", "assetId")},
        {**simulated, "id": "planned", "planId": "01M535B4GTPLAN000000000000"},
        _control("rendered", video, shot_id=shot),
        {**simulated, "id": "empty", "planId": "", "assetId": ""},
        _control("imported", video, shot_id=shot, source="import"),
    ]
    rich["plans3d"] = [{"id": "01M535B4GTPLAN000000000000", "shotId": shot, "sceneId": None, "name": "Orbit", "start": 0, "dur": 5, "keyframes": []}]
    before = copy.deepcopy(rich)

    migrated = migrate(rich)

    assert rich == before
    assert "controls" not in migrated and "plans3d" not in migrated
    assert [(r["id"], r["type"]) for r in migrated["references"] if r["space"] == "mouvement"] == [
        ("01M535B4GTREF2000000000000", "Trajectoire"),
        ("01M535B4GTCONTROL000000000", "Control video"),
        ("rendered", "Control video"),
    ]
    assert migrated["references"][-1] == {"id": "rendered", "name": "Guide rendered", "space": "mouvement", "type": "Control video", "assetId": video, "role": "Mouvement", "scope": {"type": "shot", "shotId": shot}}
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_migrating_turns_the_retired_3d_set_references_into_captures_when_they_have_an_image_and_drops_the_others(starter):
    rich = _rich(starter)
    hut = rich["references"][1]

    def reference(reference_id, space, kind, asset_id):
        return {**hut, "id": reference_id, "space": space, "type": kind, "assetId": asset_id}

    rich["references"] = [
        reference("typographic", "decors3d", "Scène d’essai", "01M535B4GTVIDEO00000000000"),
        reference("straight", "decors3d", "Scène d'essai", "01M535B4GTVIDEO00000000000"),
        reference("splat", "decors3d", "Gaussian Splat", "01M535B4GTVIDEO00000000000"),
        reference("empty-typographic", "decors3d", "Scène d’essai", None),
        reference("empty-straight", "decors3d", "Scène d'essai", None),
        reference("empty-splat", "decors3d", "Gaussian Splat", None),
        reference("other-set", "decors3d", "Photo", None),
        reference("other-space", "identite", "Gaussian Splat", None),
        hut,
    ]
    before = copy.deepcopy(rich)

    migrated = migrate(rich)

    assert rich == before
    assert [(item["id"], item["type"]) for item in migrated["references"]] == [
        ("typographic", "Capture 3D"),
        ("straight", "Capture 3D"),
        ("splat", "Capture 3D"),
        ("other-set", "Photo"),
        ("other-space", "Gaussian Splat"),
        (hut["id"], "Capture 3D"),
    ]
    assert migrated["references"][0] == {**rich["references"][0], "type": "Capture 3D"}
    assert migrated["references"][-1] is hut
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def _control(control_id, asset_id, shot_id=None, start=0, dur=5, source="scene3d"):
    return {
        "id": control_id,
        "shotId": shot_id,
        "name": f"Guide {control_id}",
        "start": start,
        "dur": dur,
        "guidance": 65,
        "source": source,
        "stale": False,
        "planId": None,
        "assetId": asset_id,
    }


def test_migrating_adds_the_video_of_each_3d_guide_once_as_a_mouvement_reference_of_the_shot_it_covers(starter):
    video = "01M535B4GTVIDEO00000000000"
    starter["assets"] = [
        {**_audio_asset(), "id": video, "kind": "video", "role": None},
        {**_audio_asset(), "id": "still", "kind": "image", "role": None},
    ]
    second = starter["clips"][1]["id"]
    starter["controls"] = [
        _control("linked", video, shot_id=second),
        _control("overlapping", video, start=4, dur=4),
        _control("imported", video, source="import"),
        _control("picture", "still"),
        _control("gone", "missing"),
        _control("outside", video, start=90, dur=4),
        _control("unknown-shot", video, shot_id="nowhere"),
        _control("already", video),
    ]
    starter["references"] = [{"id": "already", "name": "Mine", "space": "identite", "type": "Personnage", "assetId": video, "role": "Identité", "scope": None}]
    before = copy.deepcopy(starter)

    migrated = migrate(starter)

    assert starter == before
    assert "controls" not in migrated
    assert migrated["references"][0] is starter["references"][0]
    assert migrated["references"][1:] == [
        {"id": "linked", "name": "Guide linked", "space": "mouvement", "type": "Control video", "assetId": video, "role": "Mouvement", "scope": {"type": "shot", "shotId": second}},
        {"id": "overlapping", "name": "Guide overlapping", "space": "mouvement", "type": "Control video", "assetId": video, "role": "Mouvement", "scope": {"type": "shot", "shotId": second}},
    ]
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_a_stored_project_is_read_through_the_migration(project_db, store, starter):
    from backend import projects

    starter["controls"] = [{"id": "c", "shotId": None, "name": "Guide 3D", "start": 0, "dur": 4, "guidance": 65, "source": "scene3d", "stale": False}]
    starter["references"] = [{"id": "r", "name": "Set", "space": "decors3d", "type": "Scène d’essai", "assetId": "a", "role": "Décor 3D", "scope": None}]
    created = projects.create_project("user-1", starter)

    stored = projects.get_project(created["id"])["doc"]

    assert "controls" not in stored
    assert (stored["references"][0]["type"], stored["references"][0]["role"]) == ("Capture 3D", "Décor")


def test_migrating_turns_the_3d_set_role_into_the_set_role_whatever_the_family_and_keeps_the_other_roles(starter):
    def reference(reference_id, space, role):
        return {"id": reference_id, "name": reference_id, "space": space, "type": "Capture 3D", "assetId": "a", "role": role, "scope": None}

    starter["references"] = [
        reference("set3d", "decors3d", "Décor 3D"),
        reference("identity-set3d", "identite", "Décor 3D"),
        reference("set", "decors3d", "Décor"),
        reference("identity", "identite", "Identité"),
        reference("empty", "decors3d", ""),
    ]
    before = copy.deepcopy(starter)

    migrated = migrate(starter)

    assert starter == before
    assert [(item["id"], item["space"], item["role"]) for item in migrated["references"]] == [
        ("set3d", "decors3d", "Décor"),
        ("identity-set3d", "identite", "Décor"),
        ("set", "decors3d", "Décor"),
        ("identity", "identite", "Identité"),
        ("empty", "decors3d", ""),
    ]
    assert migrated["references"][2] is starter["references"][2]
    validate_doc(migrated)
    assert migrate(migrated) is migrated


def test_migrating_a_document_with_empty_3d_scenes_shots_and_control_videos_drops_the_three_keys_and_nothing_else(starter):
    assert migrate(starter) is starter
    assert migrate({**starter, "scenes": [], "plans3d": [], "controls": []}) == starter
    validate_doc(starter)


@pytest.mark.parametrize("key", ["controls", "plans3d", "scenes"])
def test_the_3d_scenes_shots_and_control_videos_are_no_longer_part_of_the_schema_and_the_migration_drops_them(starter, key):
    starter[key] = []

    assert _error(starter).code == "invalid_doc"
    assert key not in migrate(starter)
    validate_doc(migrate(starter))


def test_a_project_stored_without_any_3d_key_is_read_and_saved_as_it_is(project_db, store, starter):
    from backend import projects

    created = projects.create_project("user-1", starter)
    starter["synopsis"] = "Two hikers climb at dawn."
    saved = projects.save_project(created["id"], starter, created["version"])

    assert saved["version"] == 2
    assert projects.get_project(created["id"])["doc"] == starter


def test_an_older_project_is_stored_without_its_3d_scenes_shots_and_control_videos_its_frames_without_their_scene_and_its_guide_as_a_mouvement_reference(project_db, store):
    from backend import projects

    doc = _fixture("exports/reference-project")["doc"]
    shot = doc["clips"][2]["id"]
    video = next(asset["id"] for asset in doc["assets"] if asset["kind"] == "video" and not asset["id"].startswith("gen-"))
    scene = _splat_scene()
    older = {
        **doc,
        "scenes": [scene],
        "frames": [*doc["frames"], {**FRAME_ITEM, "shotId": shot, "sceneId": scene["id"]}],
        "plans3d": [{"id": "plan", "shotId": shot, "sceneId": scene["id"], "name": "Orbit", "start": 9.2, "dur": 3, "keyframes": []}],
        "controls": [_control("guide", video, shot_id=shot), _control("simulated", None)],
    }
    created = projects.create_project("user-1", older)
    stored = projects.get_project(created["id"])["doc"]

    assert not {"scenes", "controls", "plans3d"} & set(stored)
    assert stored["frames"] == [*doc["frames"], {**FRAME_ITEM, "shotId": shot}]
    assert stored["references"] == [
        *doc["references"],
        {"id": "guide", "name": "Guide guide", "space": "mouvement", "type": "Control video", "assetId": video, "role": "Mouvement", "scope": {"type": "shot", "shotId": shot}},
    ]


def test_migrating_a_document_already_in_the_new_shape_returns_it_as_it_is(starter):
    rich = _rich(starter)

    assert migrate(rich) is rich


def test_migrating_drops_malformed_3d_scenes_shots_and_control_videos_instead_of_refusing_the_document(starter):
    migrated = migrate({**starter, "scenes": {"kind": "sample"}, "plans3d": [3, {"id": "p", "keyframes": "none"}], "controls": {"id": "c"}})

    assert migrated == starter
    validate_doc(migrated)


@pytest.mark.parametrize(
    "scope, path",
    [
        ({"type": "shot"}, "$.references[0].scope"),
        ({"type": "global", "shotId": "s"}, "$.references[0].scope"),
        ({"type": "range"}, "$.references[0].scope.type"),
        ("global", "$.references[0].scope"),
    ],
)
def test_a_reference_scope_is_null_global_or_one_shot(starter, scope, path):
    starter["references"] = [
        {"id": "r", "name": "Hiker", "space": "identite", "type": "Personnage", "assetId": None, "role": "Identité", "scope": scope}
    ]

    assert str(_error(starter)).startswith(f"{path}: ")


@pytest.mark.parametrize("doc", [[], "doc", 3, None])
def test_a_document_that_is_not_an_object_is_refused(doc):
    error = _error(doc)

    assert error.code == "invalid_doc"
    assert str(error).startswith("$: ")


def test_a_document_with_a_number_json_cannot_carry_is_refused(starter):
    starter["clips"][0]["dur"] = float("nan")

    error = _error(starter)

    assert error.code == "invalid_doc"
    assert str(error).startswith("$: ")


def test_a_document_over_four_mebibytes_is_too_large(starter):
    starter["synopsis"] = "x" * MAX_DOC_BYTES

    error = _error(starter)

    assert error.code == "doc_too_large"
    assert str(error).startswith("$: ")
    assert str(MAX_DOC_BYTES) in str(error)


def test_the_size_limit_counts_utf8_bytes_of_the_canonical_text(starter):
    starter["synopsis"] = ""
    room = MAX_DOC_BYTES - len(canonical(starter).encode("utf-8"))
    starter["synopsis"] = "x" * room

    validate_doc(starter)

    starter["synopsis"] = "é" * (room // 2 + 1)
    assert _error(starter).code == "doc_too_large"


def test_a_long_reason_is_cut_short(starter):
    starter["clips"] = {"clip": "x" * 5000}

    message = str(_error(starter))

    assert message.startswith("$.clips: ")
    assert len(message) < 400


def test_canonical_text_is_compact_sorted_and_keeps_non_ascii(starter):
    reordered = json.loads(json.dumps(starter, sort_keys=False))
    reordered = dict(reversed(list(reordered.items())))

    text = canonical(starter)

    assert text == canonical(reordered)
    assert text == canonical(json.loads(text))
    assert ", " not in text and ": " not in text
    assert text.startswith('{"aspect":"16:9","assets":[],"audio":[]')
    assert "{projet}_{fenêtre}_{variante}" in text


def test_canonical_text_changes_with_the_document(starter):
    changed = copy.deepcopy(starter)
    changed["clips"][0]["label"] = "Other"

    assert canonical(changed) != canonical(starter)


def test_summary_of_the_starter_counts_five_shots_over_twenty_five_seconds(starter):
    assert summary(starter) == {"shots": 5, "duration_s": 25}


def test_summary_of_an_empty_document_is_zero():
    assert summary(_fixture("empty_doc")) == {"shots": 0, "duration_s": 0}


def test_summary_running_time_is_the_last_end_of_clips_audio_and_titles(starter):
    rich = _rich(starter)

    assert summary(rich) == {"shots": 5, "duration_s": 32.5}

    rich["audio"].clear()
    rich["titles"][0].update(start=24, dur=3.5)
    assert summary(rich)["duration_s"] == 27.5


def test_summary_counts_titles_and_audio_without_any_shot():
    doc = _fixture("empty_doc")
    doc["titles"].append({"id": "t", "text": "End", "sub": "", "start": 2, "dur": 3})

    assert summary(doc) == {"shots": 0, "duration_s": 5}
