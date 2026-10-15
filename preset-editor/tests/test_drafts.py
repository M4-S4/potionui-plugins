import json

import pytest

from backend import drafts, paths
from tests.conftest import FIXTURES, read_id

NATIVE = FIXTURES / "minimal-native"


def test_rewrite_top_level_replaces_the_first_top_level_line_and_keeps_the_rest():
    text = '# header\nschema: 1\nid: "old"\nname: "Old name" # trailing\nvars:\n  id: nested\nmodes:\n  - txt2img\n'

    result = drafts.rewrite_top_level(text, {"id": "new-id", "name": "Plain name"})

    assert result == '# header\nschema: 1\nid: "new-id"\nname: "Plain name"\nvars:\n  id: nested\nmodes:\n  - txt2img\n'


def test_rewrite_top_level_quotes_special_characters_so_yaml_reads_them_back():
    import yaml

    name = 'Quote "me", back\\slash, é and #hash: colon'

    result = drafts.rewrite_top_level('schema: 1\nid: "old"\nname: "x"\n', {"id": "new-id", "name": name})

    assert yaml.safe_load(result) == {"schema": 1, "id": "new-id", "name": name}
    assert result.splitlines()[1] == 'id: "new-id"'


def test_rewrite_top_level_appends_a_missing_key_and_a_final_newline():
    assert drafts.rewrite_top_level("schema: 1", {"name": "N"}) == 'schema: 1\nname: "N"\n'


def test_create_copy_rewrites_id_and_name_and_leaves_the_rest_byte_identical(roots):
    draft = drafts.create_copy(
        roots, source_dir=NATIVE, preset_id="copy-one", name="Copy one", target_dir="My/v1", created_by="u1",
        source="copy_of:fixture-minimal-native",
    )

    assert paths.DRAFT_ID_RE.match(draft.draft_id)
    assert draft.dir == roots.drafts / draft.draft_id
    assert read_id(draft.dir) == "copy-one"
    manifest = (draft.dir / "preset.yml").read_text(encoding="utf-8")
    original = (NATIVE / "preset.yml").read_text(encoding="utf-8")
    assert manifest.replace('id: "copy-one"', 'id: "fixture-minimal-native"').replace('name: "Copy one"', 'name: "Minimal native"') == original
    for relative in ("modes/txt2img/form.yml", "modes/txt2img/pipeline.yml", "modes/txt2img/tabs/main.yml"):
        assert (draft.dir / relative).read_bytes() == (NATIVE / relative).read_bytes()
    meta = json.loads((draft.dir / drafts.META_FILE).read_text(encoding="utf-8"))
    assert meta == draft.to_dict()
    assert (meta["preset_id"], meta["name"], meta["source"], meta["target_dir"], meta["created_by"]) == (
        "copy-one", "Copy one", "copy_of:fixture-minimal-native", "My/v1", "u1",
    )
    assert meta["published_at"] is None and meta["last_lint"] is None
    assert meta["created_at"].endswith("Z") and meta["updated_at"] >= meta["created_at"]


def test_create_edit_keeps_the_manifest_untouched(roots):
    draft = drafts.create_edit(roots, source_dir=NATIVE, preset_id="fixture-minimal-native", name="Minimal native", target_dir="Fixture/native", created_by="u1")

    assert (draft.dir / "preset.yml").read_bytes() == (NATIVE / "preset.yml").read_bytes()
    assert draft.source == "edit_of:fixture-minimal-native"


def test_a_copy_never_carries_the_private_files_of_its_source(roots, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "preset.yml").write_text('schema: 1\nid: "src"\nname: "Src"\n', encoding="utf-8")
    (source / drafts.META_FILE).write_text("{}", encoding="utf-8")
    (source / drafts.HISTORY_META_FILE).write_text("{}", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.pyc").write_bytes(b"")

    draft = drafts.create_copy(roots, source_dir=source, preset_id="dst", name="Dst", target_dir="D", created_by="u", source="copy_of:src")

    assert sorted(p.name for p in draft.dir.iterdir()) == [drafts.META_FILE, "preset.yml"]
    assert drafts.file_tree(draft.dir) == [{"path": "preset.yml", "size": (draft.dir / "preset.yml").stat().st_size}]


@pytest.mark.parametrize("preset_id, target", [("no", "My/v1"), ("ok-id", "a/b/c")])
def test_create_refuses_a_bad_id_or_target_before_copying(roots, preset_id, target):
    with pytest.raises(ValueError):
        drafts.create_copy(roots, source_dir=NATIVE, preset_id=preset_id, name="N", target_dir=target, created_by="u", source="s")
    assert not roots.drafts.exists() or list(roots.drafts.iterdir()) == []


def test_create_refuses_a_source_without_a_manifest(roots, tmp_path):
    with pytest.raises(drafts.DraftError) as failure:
        drafts.create_copy(roots, source_dir=tmp_path, preset_id="x-id", name="N", target_dir="M", created_by="u", source="s")
    assert failure.value.code == "invalid_preset"


def test_load_list_and_delete_round_trip(roots):
    first = drafts.create_copy(roots, source_dir=NATIVE, preset_id="one", name="One", target_dir="M/a", created_by="u", source="s")
    second = drafts.create_copy(roots, source_dir=NATIVE, preset_id="two", name="Two", target_dir="M/b", created_by="u", source="s")
    (roots.drafts / "not-a-draft").mkdir()

    assert drafts.load(roots, first.draft_id) == first
    expected = sorted([first, second], key=lambda d: (d.created_at, d.draft_id), reverse=True)
    assert [d.draft_id for d in drafts.list_drafts(roots)] == [d.draft_id for d in expected]
    drafts.delete(roots, first.draft_id)
    assert [d.draft_id for d in drafts.list_drafts(roots)] == [second.draft_id]
    for missing in (first.draft_id, "../escape", "nope"):
        with pytest.raises(drafts.DraftError) as failure:
            drafts.load(roots, missing)
        assert failure.value.code == "not_found"


def test_lint_and_publication_are_recorded_in_the_metadata(roots):
    draft = drafts.create_copy(roots, source_dir=NATIVE, preset_id="one", name="One", target_dir="M/a", created_by="u", source="s")

    drafts.record_lint(draft, ["[ERROR] x"], [])
    drafts.mark_published(draft)

    stored = drafts.load(roots, draft.draft_id)
    assert stored.last_lint["errors"] == ["[ERROR] x"] and stored.last_lint["warnings"] == []
    assert stored.last_lint["at"].endswith("Z") and stored.published_at.endswith("Z")


def test_file_tree_lists_files_in_order_with_their_size(roots):
    draft = drafts.create_copy(roots, source_dir=NATIVE, preset_id="one", name="One", target_dir="M/a", created_by="u", source="s")

    tree = drafts.file_tree(draft.dir)

    assert [entry["path"] for entry in tree] == [
        "modes/txt2img/form.yml", "modes/txt2img/pipeline.yml", "modes/txt2img/tabs/main.yml", "preset.yml",
    ]
    assert all(entry["size"] > 0 for entry in tree)
