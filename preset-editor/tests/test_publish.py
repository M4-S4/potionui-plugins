import os
import shutil
from pathlib import Path

import pytest

from backend import drafts, history, paths, publish
from tests.conftest import FIXTURES, read_id

NATIVE = FIXTURES / "minimal-native"


def _draft(roots, preset_id="copy-one", target="MyModel/v1", name="Copy one"):
    return drafts.create_copy(
        roots, source_dir=NATIVE, preset_id=preset_id, name=name, target_dir=target, created_by="u", source="copy_of:x"
    )


def _catalog_entry(preset_id, kind, path, plugin_id=None):
    return {"id": preset_id, "origin": {"kind": kind, "plugin_id": plugin_id, "path": path}}


def test_ids_on_disk_scans_every_root_and_skips_broken_manifests(roots, marketplace, tmp_path):
    roots.ensure()
    shutil.copytree(NATIVE, roots.local_presets / "Local" / "v1")
    broken = roots.local_presets / "Broken"
    broken.mkdir()
    (broken / "preset.yml").write_text("- not: [a mapping", encoding="utf-8")

    found = publish.ids_on_disk([marketplace, roots.local_presets, tmp_path / "missing"])

    assert found == {
        "fixture-minimal-native": [
            (marketplace / "Fixture" / "native").resolve(), (roots.local_presets / "Local" / "v1").resolve(),
        ]
    }


def test_an_id_used_by_another_root_is_refused_before_writing(roots, marketplace):
    with pytest.raises(publish.PublishError) as failure:
        publish.check_collisions(
            roots, preset_id="fixture-minimal-native", target_dir="MyModel/v1",
            catalog=[_catalog_entry("fixture-minimal-native", "marketplace", "Fixture/native")], disk_roots=[marketplace],
        )
    assert failure.value.code == "id_in_use" and "marketplace" in failure.value.message


def test_an_id_of_a_plugin_preset_names_the_plugin(roots):
    with pytest.raises(publish.PublishError) as failure:
        publish.check_collisions(
            roots, preset_id="rtx", target_dir="M/v", catalog=[_catalog_entry("rtx", "plugin", "RTX", "nvidia-rtx-upscale")], disk_roots=[],
        )
    assert "plugin 'nvidia-rtx-upscale'" in failure.value.message


def test_an_id_only_present_on_disk_in_an_unloaded_preset_is_refused(roots, marketplace):
    with pytest.raises(publish.PublishError) as failure:
        publish.check_collisions(roots, preset_id="fixture-minimal-native", target_dir="MyModel/v1", catalog=[], disk_roots=[marketplace])
    assert failure.value.code == "id_in_use" and "Fixture" in failure.value.message


def test_republishing_the_same_local_preset_is_allowed(roots):
    roots.ensure()
    shutil.copytree(NATIVE, roots.local_presets / "MyModel" / "v1")

    publish.check_collisions(
        roots, preset_id="fixture-minimal-native", target_dir="MyModel/v1",
        catalog=[_catalog_entry("fixture-minimal-native", "local", "MyModel/v1")], disk_roots=[roots.local_presets],
    )


def test_a_folder_holding_another_preset_is_refused(roots):
    roots.ensure()
    shutil.copytree(NATIVE, roots.local_presets / "MyModel" / "v1")

    with pytest.raises(publish.PublishError) as failure:
        publish.check_collisions(roots, preset_id="other-id", target_dir="MyModel/v1", catalog=[], disk_roots=[])
    assert failure.value.code == "target_in_use"


def test_swap_puts_a_new_preset_in_place_without_a_backup(roots):
    roots.ensure()
    staging = publish.stage(roots, NATIVE)
    target = roots.local_presets / "MyModel" / "v1"

    assert publish.swap(target, staging, roots.staging) is None
    assert read_id(target) == "fixture-minimal-native"
    assert not staging.exists()


def test_swap_moves_the_previous_version_aside(roots):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)
    (target / "marker.txt").write_text("old", encoding="utf-8")
    staging = publish.stage(roots, NATIVE)

    backup = publish.swap(target, staging, roots.staging)

    assert backup.parent == roots.staging and (backup / "marker.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "marker.txt").exists() and read_id(target) == "fixture-minimal-native"


def test_a_failed_second_rename_restores_the_previous_version(roots, monkeypatch):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)
    (target / "marker.txt").write_text("old", encoding="utf-8")
    staging = publish.stage(roots, NATIVE)
    real_replace, calls = os.replace, []

    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) == 2:
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(publish.os, "replace", replace)

    with pytest.raises(publish.PublishError) as failure:
        publish.swap(target, staging, roots.staging)

    assert failure.value.code == "swap_failed" and "disk full" in failure.value.message
    assert (target / "marker.txt").read_text(encoding="utf-8") == "old"
    assert not staging.exists()
    assert list(roots.staging.iterdir()) == []


def test_a_failed_restore_keeps_the_backup_and_names_it(roots, monkeypatch):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)
    staging = publish.stage(roots, NATIVE)
    real_replace, calls = os.replace, []

    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) >= 2:
            raise OSError("gone")
        real_replace(src, dst)

    monkeypatch.setattr(publish.os, "replace", replace)

    with pytest.raises(publish.PublishError) as failure:
        publish.swap(target, staging, roots.staging)

    backups = [entry for entry in roots.staging.iterdir() if entry.name.startswith("backup-")]
    assert len(backups) == 1 and str(backups[0]) in failure.value.message
    assert (backups[0] / "preset.yml").is_file() and not target.exists()


def _publish(roots, draft, depth=2):
    swapped = publish.publish_draft(roots, draft)
    return publish.commit_publish(roots, draft, swapped["backup"], history_depth=depth)


def test_publish_and_commit_archive_the_previous_version_and_rotate(roots, monkeypatch):
    stamps = iter(["20261015T100000.000001", "20261015T100000.000002", "20261015T100000.000003"])
    monkeypatch.setattr(history, "stamp_now", lambda: next(stamps))
    first = _draft(roots, name="First")

    swapped = publish.publish_draft(roots, first)
    assert (swapped["preset_id"], swapped["target_dir"], swapped["backup"]) == ("copy-one", "MyModel/v1", None)
    assert swapped["target"] == roots.local_presets / "MyModel" / "v1"
    assert publish.commit_publish(roots, first, None, history_depth=2) is None
    assert history.list_entries(roots, "copy-one") == []

    for name, expected in (("Second", "20261015T100000.000001"), ("Third", "20261015T100000.000002"), ("Fourth", "20261015T100000.000003")):
        assert _publish(roots, _draft(roots, name=name)) == expected

    target = roots.local_presets / "MyModel" / "v1"
    assert '"Fourth"' in (target / "preset.yml").read_text(encoding="utf-8")
    assert [(e["stamp"], e["name"]) for e in history.list_entries(roots, "copy-one")] == [
        ("20261015T100000.000003", "Third"), ("20261015T100000.000002", "Second"),
    ]
    assert [entry.name for entry in roots.staging.iterdir()] == []


def test_rollback_of_a_first_publication_removes_the_folder_and_its_empty_parent(roots):
    swapped = publish.publish_draft(roots, _draft(roots))

    publish.rollback_publish(roots, swapped["target"], swapped["backup"])

    assert not (roots.local_presets / "MyModel").exists() and roots.local_presets.is_dir()
    assert list(roots.staging.iterdir()) == []


def test_rollback_of_a_republication_puts_the_backup_back(roots):
    _publish(roots, _draft(roots, name="First"))
    swapped = publish.publish_draft(roots, _draft(roots, name="Second"))
    assert '"Second"' in (swapped["target"] / "preset.yml").read_text(encoding="utf-8")

    publish.rollback_publish(roots, swapped["target"], swapped["backup"])

    assert '"First"' in (roots.local_presets / "MyModel" / "v1" / "preset.yml").read_text(encoding="utf-8")
    assert list(roots.staging.iterdir()) == []
    assert history.list_entries(roots, "copy-one") == []


def test_delete_local_preset_archives_removes_and_prunes_the_empty_model_folder(roots, monkeypatch):
    monkeypatch.setattr(history, "stamp_now", lambda: "20261015T100000.000009")
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)

    stamp = publish.delete_local_preset(roots, preset_dir=target, preset_id="fixture-minimal-native", target_dir="MyModel/v1", history_depth=5)

    assert stamp == "20261015T100000.000009"
    assert not (roots.local_presets / "MyModel").exists() and roots.local_presets.is_dir()
    assert [e["reason"] for e in history.list_entries(roots, "fixture-minimal-native")] == ["delete"]


def test_delete_with_a_relative_preset_path_never_removes_the_local_root(roots, tmp_path, monkeypatch):
    roots.ensure()
    shutil.copytree(NATIVE, roots.local_presets / "MyModel" / "v1")
    monkeypatch.chdir(tmp_path)
    relative_preset = Path("content") / "presets" / "local" / "MyModel" / "v1"
    relative_roots = paths.Roots(
        drafts=roots.drafts, history=roots.history, staging=roots.staging, local_presets=Path("content") / "presets" / "local"
    )

    publish.delete_local_preset(relative_roots, preset_dir=relative_preset, preset_id="fixture-minimal-native", target_dir="MyModel/v1", history_depth=5)

    assert roots.local_presets.is_dir()
    assert not (roots.local_presets / "MyModel").exists()


def test_delete_keeps_a_model_folder_that_still_holds_another_variant(roots):
    roots.ensure()
    shutil.copytree(NATIVE, roots.local_presets / "MyModel" / "v1")
    shutil.copytree(NATIVE, roots.local_presets / "MyModel" / "v2")

    publish.delete_local_preset(roots, preset_dir=roots.local_presets / "MyModel" / "v1", preset_id="fixture-minimal-native", target_dir="MyModel/v1", history_depth=5)

    assert (roots.local_presets / "MyModel" / "v2" / "preset.yml").is_file()


def test_delete_refuses_a_folder_that_holds_another_preset_before_archiving_anything(roots):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)

    with pytest.raises(publish.PublishError) as failure:
        publish.delete_local_preset(roots, preset_dir=target, preset_id="a-mirror-id", target_dir="MyModel/v1", history_depth=5)

    assert failure.value.code == "not_its_folder"
    assert read_id(target) == "fixture-minimal-native"
    assert history.list_entries(roots, "a-mirror-id") == []


@pytest.mark.parametrize("target_dir", ["", "/abs/v1", "MyModel/../MyModel/v1"])
def test_delete_refuses_a_folder_it_cannot_place_under_the_local_presets(roots, target_dir):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1"
    shutil.copytree(NATIVE, target)

    with pytest.raises(publish.PublishError) as failure:
        publish.delete_local_preset(roots, preset_dir=target, preset_id="fixture-minimal-native", target_dir=target_dir, history_depth=5)

    assert failure.value.code == "not_its_folder"
    assert (target / "preset.yml").is_file()


def test_delete_refuses_a_preset_reached_through_a_link_and_leaves_the_linked_folder(roots, tmp_path):
    roots.ensure()
    elsewhere = tmp_path / "elsewhere" / "MyModel"
    shutil.copytree(NATIVE, elsewhere / "v1")
    try:
        os.symlink(elsewhere, roots.local_presets / "MyModel", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system cannot create a directory link")

    with pytest.raises(publish.PublishError) as failure:
        publish.delete_local_preset(
            roots, preset_dir=roots.local_presets / "MyModel" / "v1", preset_id="fixture-minimal-native", target_dir="MyModel/v1",
            history_depth=5,
        )

    assert failure.value.code == "linked_folder"
    assert (elsewhere / "v1" / "preset.yml").is_file()
    assert history.list_entries(roots, "fixture-minimal-native") == []


def test_delete_accepts_a_preset_three_folders_deep(roots):
    roots.ensure()
    target = roots.local_presets / "MyModel" / "v1" / "fast"
    shutil.copytree(NATIVE, target)

    publish.delete_local_preset(roots, preset_dir=target, preset_id="fixture-minimal-native", target_dir="MyModel/v1/fast", history_depth=5)

    assert not (roots.local_presets / "MyModel").exists()
