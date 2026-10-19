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
        "synth": "wind",
        "transcript": None,
        "character": None,
        "lipSync": None,
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
        "synth": None,
        "transcript": None,
        "character": None,
        "lipSync": None,
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
            "sceneId": "01M535B4GTSCENE00000000000",
        }
    )
    doc["controls"].append(
        {
            "id": "01M535B4GTCONTROL000000000",
            "shotId": None,
            "name": "Guide 3D",
            "start": 0,
            "dur": 5,
            "guidance": 65,
            "source": "scene3d",
            "stale": True,
            "planId": "01M535B4GTPLAN000000000000",
            "assetId": "01M535B4GTVIDEO00000000000",
        }
    )
    doc["scenes"] += [
        _splat_scene(),
        {"id": "01M535B4GTSCENEFILE0000000", "kind": "splatfile", "name": "set.spz", "fileId": "01M535B4GTFILE00000000000", "format": "spz", "view": None},
        {
            "id": "01M535B4GTSCENEGLB00000000",
            "kind": "glb",
            "name": "hut.glb",
            "fileId": "01M535B4GTFILE10000000000",
            "cameras": [{"name": "camera", "animated": True, "duration": 4.5}, {"name": "still", "animated": False, "duration": None}],
        },
    ]
    doc["plans3d"].append(
        {
            "id": "01M535B4GTPLAN000000000000",
            "shotId": clip["id"],
            "sceneId": "01M535B4GTSCENE00000000000",
            "name": "Orbit",
            "start": 0,
            "dur": 5,
            "source": "trajectory",
            "preset": "orbit",
            "amount": 10,
            "camera": None,
            "keyframes": [
                {"id": "01M535B4GTKEY0000000000000", "t": 0, "pos": [-0.7, 0, 0], "target": [0, 0, -4], "focal": 30, "roll": 0},
                {"id": "01M535B4GTKEY1000000000000", "t": 5, "pos": [0.7, 0, 0], "target": [0, 0, -4], "focal": 30, "roll": 0},
            ],
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
            "role": "Décor 3D",
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
    ]
    doc["lanes"][0]["inserts"].append({"type": "filter", "on": True, "cutoff": 8000})
    doc["lanes"][1]["automation"] = "write"
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


def test_the_reference_project_with_its_splat_scene_plan_3d_and_guide_is_valid_and_current():
    doc = _fixture("exports/reference-project")["doc"]

    assert validate_doc(doc) == canonical(doc)
    assert migrate(doc) is doc
    assert [scene["kind"] for scene in doc["scenes"]] == ["splat"]
    assert doc["plans3d"][0]["sceneId"] == doc["scenes"][0]["id"]
    assert doc["controls"][0]["planId"] == doc["plans3d"][0]["id"]


def test_an_audio_asset_from_sound_design_and_a_video_asset_without_audio_fields_are_valid(starter):
    starter["assets"] = [
        _audio_asset(
            synth="voice",
            role="Dialogue",
            transcript="We camp here tonight.",
            character="Lena",
            lipSync=True,
        ),
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
        (_audio_asset(synth="rain"), "$.assets[0].synth"),
        (_audio_asset(role="Voix"), "$.assets[0].role"),
        (_audio_asset(lipSync="yes"), "$.assets[0].lipSync"),
        (_audio_asset(quality="preview"), "$.assets[0].quality"),
        (_video_asset(width=19.5), "$.assets[0].width"),
        (_video_asset(id=""), "$.assets[0].id"),
        (_video_asset(origin={"kind": "history", "generationId": "g"}), "$.assets[0].origin"),
        (_video_asset(origin={"kind": "library", "item_id": "i"}), "$.assets[0].origin"),
        (_video_asset(origin={"kind": "url", "href": "x"}), "$.assets[0].origin.kind"),
        ({key: value for key, value in _video_asset().items() if key != "transcript"}, "$.assets[0]"),
        ({**_video_asset(), "tags": []}, "$.assets[0]"),
    ],
)
def test_an_asset_outside_the_contract_is_refused(starter, asset, path):
    starter["assets"] = [asset]

    assert str(_error(starter)).startswith(f"{path}: ")


@pytest.mark.parametrize(
    "item, path",
    [
        ({"id": "s", "kind": "file", "name": "set.ply", "file": "C:/set.ply"}, "$.scenes[0].kind"),
        ({"id": "s", "kind": "sample", "name": "Sample"}, "$.scenes[0].kind"),
        ({"id": "s", "kind": "url", "name": "Sample"}, "$.scenes[0].kind"),
        ({key: value for key, value in _splat_scene().items() if key != "view"}, "$.scenes[0]"),
        (_splat_scene(status="cancelled"), "$.scenes[0].status"),
        (_splat_scene(count=1.5), "$.scenes[0].count"),
        (_splat_scene(view={"fov": 50, "aspect": 1.5}), "$.scenes[0].view"),
        (_splat_scene(view={"fov": 50, "aspect": 1.5, "depth": 4, "width": 832}), "$.scenes[0].view"),
        ({"id": "s", "kind": "splatfile", "name": "set.ply", "fileId": "f", "format": "obj", "view": None}, "$.scenes[0].format"),
        ({"id": "s", "kind": "splatfile", "name": "set.ply", "fileId": None, "format": "ply", "view": None}, "$.scenes[0].fileId"),
        (
            {"id": "s", "kind": "glb", "name": "hut.glb", "fileId": "f", "cameras": [{"name": "camera", "animated": "yes", "duration": None}]},
            "$.scenes[0].cameras[0].animated",
        ),
        ({"id": "s", "kind": "glb", "name": "hut.glb", "fileId": "f"}, "$.scenes[0]"),
    ],
)
def test_a_scene_follows_its_kind(starter, item, path):
    starter["scenes"] = [item]

    assert str(_error(starter)).startswith(f"{path}: ")


@pytest.mark.parametrize(
    "scene",
    [
        _splat_scene(status="queued", progress=0, fileId=None, count=None, view=None),
        _splat_scene(
            status="failed", sourceAssetId=None, sourceTime=None, jobId=None, fileId=None, count=None, view=None, error="The GPU ran out of memory."
        ),
        {"id": "s", "kind": "splatfile", "name": "set.splat", "fileId": "f", "format": "splat", "view": {"fov": 50, "aspect": 0.5625, "depth": 3}},
        {"id": "s", "kind": "glb", "name": "hut.glb", "fileId": "f", "cameras": []},
    ],
)
def test_each_scene_kind_of_the_contract_is_valid(starter, scene):
    starter["scenes"] = [scene]

    validate_doc(starter)


def _plan(**fields):
    return {
        "id": "p",
        "shotId": None,
        "sceneId": None,
        "name": "Plan",
        "start": 0,
        "dur": 4,
        "keyframes": [{"id": "k", "t": 0, "pos": [0, 1.5, 8], "target": [0, 1.5, 0], "focal": 35, "roll": 0}],
        **fields,
    }


def _key(**fields):
    return {"id": "k", "t": 0, "pos": [0, 1, 2], "target": [0, 0, 0], "focal": 35, "roll": 0, **fields}


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"source": "manual", "preset": None, "amount": None, "camera": None},
        {"source": "trajectory", "preset": "crane", "amount": 12.5, "camera": None},
        {"source": "blender", "preset": None, "amount": None, "camera": "camera"},
    ],
)
def test_a_plan_3d_may_say_where_its_keyframes_come_from(starter, fields):
    starter["plans3d"] = [_plan(**fields)]

    validate_doc(starter)


@pytest.mark.parametrize(
    "plan, path",
    [
        (_plan(source="sample"), "$.plans3d[0].source"),
        (_plan(preset="spiral"), "$.plans3d[0].preset"),
        (_plan(amount="10"), "$.plans3d[0].amount"),
        (_plan(camera=3), "$.plans3d[0].camera"),
        (_plan(keyframes=[_key(pos=[0, 1])]), "$.plans3d[0].keyframes[0].pos"),
        (_plan(keyframes=[_key(pos=[0, 1, 2, 3])]), "$.plans3d[0].keyframes[0].pos"),
        (_plan(keyframes=[_key(target=[0, "0", 0])]), "$.plans3d[0].keyframes[0].target[1]"),
        (_plan(keyframes=[{key: value for key, value in _key().items() if key != "roll"}]), "$.plans3d[0].keyframes[0]"),
        (_plan(keyframes=[{"id": "k", "t": 0, "az": 0, "el": 0, "dist": 8, "focal": 35, "height": 1.5, "roll": 0}]), "$.plans3d[0].keyframes[0]"),
    ],
)
def test_a_plan_3d_outside_the_contract_is_refused(starter, plan, path):
    starter["plans3d"] = [plan]

    assert str(_error(starter)).startswith(f"{path}: ")


FRAME_ITEM = {"id": "f", "shotId": None, "time": 0, "assetId": None, "role": "first", "strength": 100}
CONTROL_ITEM = {"id": "c", "shotId": None, "name": "", "start": 0, "dur": 4, "guidance": 65, "source": "scene3d", "stale": False}


@pytest.mark.parametrize(
    "collection, item, key, wrong",
    [("frames", FRAME_ITEM, "sceneId", ""), ("controls", CONTROL_ITEM, "planId", 3), ("controls", CONTROL_ITEM, "assetId", "")],
)
def test_the_scene_of_a_frame_and_the_plan_and_video_of_a_control_are_optional_ids_or_null(starter, collection, item, key, wrong):
    starter[collection] = [dict(item)]
    validate_doc(starter)

    for value, valid in ((wrong, False), (None, True), ("01M535B4GTID", True)):
        starter[collection][0][key] = value
        if valid:
            validate_doc(starter)
        else:
            assert str(_error(starter)).startswith(f"$.{collection}[0].{key}: ")


LEGACY_SCENES = [
    {"id": "sc-sample", "kind": "sample", "name": "Sample set"},
    {"id": "sc-file", "kind": "file", "name": "set.ply", "file": "C:/scenes/set.ply"},
]


def _legacy_plan(plan_id, scene_id):
    return {
        "id": plan_id,
        "shotId": None,
        "sceneId": scene_id,
        "name": "Orbit",
        "start": 0,
        "dur": 5,
        "keyframes": [
            {"id": f"{plan_id}-k0", "t": 0, "az": 90, "el": 30, "dist": 10, "focal": 30, "height": 1.5},
            {"id": f"{plan_id}-k1", "t": 5, "az": 0, "el": 0, "dist": 13, "focal": 50, "height": 0},
        ],
    }


def test_migrating_drops_the_simulated_scenes_unlinks_their_plans_and_turns_orbit_keyframes_into_positions(starter):
    legacy = copy.deepcopy(starter)
    legacy["scenes"] = [*LEGACY_SCENES, _splat_scene()]
    legacy["plans3d"] = [_legacy_plan("p1", "sc-sample"), _legacy_plan("p2", "sc-file"), _legacy_plan("p3", "01M535B4GTSCENE00000000000")]
    before = copy.deepcopy(legacy)

    migrated = migrate(legacy)

    assert legacy == before
    assert migrated["scenes"] == [_splat_scene()]
    assert [plan["sceneId"] for plan in migrated["plans3d"]] == [None, None, "01M535B4GTSCENE00000000000"]
    assert migrated["plans3d"][0]["keyframes"] == [
        {"id": "p1-k0", "t": 0, "pos": [8.660254, 6.5, 0.0], "target": [0, 1.5, 0], "focal": 30, "roll": 0},
        {"id": "p1-k1", "t": 5, "pos": [0.0, 0.0, 13.0], "target": [0, 0, 0], "focal": 50, "roll": 0},
    ]
    assert [key["pos"] for key in migrated["plans3d"][2]["keyframes"]] == [[8.660254, 6.5, 0.0], [0.0, 0.0, 13.0]]
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


def test_migrating_drops_the_simulated_3d_guides_and_keeps_those_with_a_3d_shot_or_a_video(starter):
    rich = _rich(starter)
    guide = rich["controls"][0]
    simulated = {**guide, "id": "simulated", "planId": None, "assetId": None}
    legacy = {key: value for key, value in simulated.items() if key not in ("planId", "assetId")}
    legacy["id"] = "legacy"
    imported = {**simulated, "id": "imported", "source": "import"}
    rich["controls"] = [
        simulated,
        guide,
        legacy,
        {**simulated, "id": "planned", "planId": "01M535B4GTPLAN000000000000"},
        {**simulated, "id": "rendered", "assetId": "01M535B4GTVIDEO00000000000"},
        {**simulated, "id": "empty", "planId": "", "assetId": ""},
        imported,
    ]
    before = copy.deepcopy(rich)

    migrated = migrate(rich)

    assert rich == before
    assert [control["id"] for control in migrated["controls"]] == ["01M535B4GTCONTROL000000000", "planned", "rendered", "imported"]
    assert migrated["controls"][0] is guide
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


def test_a_stored_project_is_read_through_the_migration(project_db, store, starter):
    from backend import projects

    starter["controls"] = [{"id": "c", "shotId": None, "name": "Guide 3D", "start": 0, "dur": 4, "guidance": 65, "source": "scene3d", "stale": False}]
    starter["references"] = [{"id": "r", "name": "Set", "space": "decors3d", "type": "Scène d’essai", "assetId": "a", "role": "Décor 3D", "scope": None}]
    created = projects.create_project("user-1", starter)

    stored = projects.get_project(created["id"])["doc"]

    assert stored["controls"] == [] and stored["references"][0]["type"] == "Capture 3D"


def test_migrating_the_document_of_a_user_with_scenes_and_empty_plans_3d_keeps_it_as_it_is(starter):
    starter["scenes"] = []
    starter["plans3d"] = []

    assert migrate(starter) is starter
    validate_doc(starter)


def test_migrating_a_document_already_in_the_new_shape_returns_it_as_it_is(starter):
    rich = _rich(starter)

    assert migrate(rich) is rich


def test_migrating_leaves_malformed_scene_collections_to_the_validation(starter):
    starter["scenes"] = {"kind": "sample"}
    starter["plans3d"] = [3, {"id": "p", "keyframes": "none"}]

    assert migrate(starter) is starter


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
