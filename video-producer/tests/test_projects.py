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
        {"id": "01M535B4GTFRAME00000000000", "shotId": clip["id"], "time": 1.2, "assetId": None, "role": "Capture 3D", "strength": 80}
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
        }
    )
    doc["scenes"] += [
        {"id": "01M535B4GTSCENE00000000000", "kind": "sample", "name": "Sample set"},
        {"id": "01M535B4GTSCENEFILE0000000", "kind": "file", "name": "set.ply", "file": "C:/scenes/set.ply"},
    ]
    doc["plans3d"].append(
        {
            "id": "01M535B4GTPLAN000000000000",
            "shotId": clip["id"],
            "sceneId": None,
            "name": "Orbit",
            "start": 0,
            "dur": 5,
            "keyframes": [
                {"id": "01M535B4GTKEY0000000000000", "t": 0, "az": -60, "el": 20, "dist": 13, "focal": 30, "height": 1.5},
                {"id": "01M535B4GTKEY1000000000000", "t": 5, "az": 60, "el": 20, "dist": 13, "focal": 30, "height": 1.5},
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
            "type": "Gaussian Splat",
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
        ({"id": "s", "kind": "file", "name": "set.ply"}, "$.scenes[0]"),
        ({"id": "s", "kind": "sample", "name": "Sample", "file": "x"}, "$.scenes[0]"),
        ({"id": "s", "kind": "url", "name": "Sample"}, "$.scenes[0].kind"),
    ],
)
def test_a_scene_follows_its_kind(starter, item, path):
    starter["scenes"] = [item]

    assert str(_error(starter)).startswith(f"{path}: ")


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
