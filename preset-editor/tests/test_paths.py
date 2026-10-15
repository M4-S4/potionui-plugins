import os
from pathlib import Path

import pytest

from backend import paths


def test_default_roots_hang_off_the_storage_directory_and_the_core_preset_tree(monkeypatch):
    monkeypatch.setattr(paths, "storage_dir", lambda: Path("/srv/potionui/storage"))

    roots = paths.default_roots()

    assert roots.drafts == Path("/srv/potionui/storage/plugins/preset-editor/drafts")
    assert roots.history == Path("/srv/potionui/storage/plugins/preset-editor/history")
    assert roots.staging == Path("content/presets/.preset-editor/staging")
    assert roots.local_presets == Path("content/presets/local")


def test_roots_are_computed_once(monkeypatch):
    calls = []
    monkeypatch.setattr(paths, "_current", None)
    monkeypatch.setattr(paths, "storage_dir", lambda: calls.append(1) or Path("storage"))

    assert paths.roots() is paths.roots()
    assert calls == [1]


def test_ensure_creates_every_root(roots):
    roots.ensure()

    assert all(path.is_dir() for path in (roots.drafts, roots.history, roots.staging, roots.local_presets))


def test_clear_staging_removes_entries_but_keeps_the_folder(roots):
    roots.ensure()
    (roots.staging / "abandoned").mkdir()
    (roots.staging / "abandoned" / "preset.yml").write_text("schema: 1\n", encoding="utf-8")
    (roots.staging / "stray.tmp").write_text("", encoding="utf-8")

    assert paths.clear_staging(roots) == 2
    assert roots.staging.is_dir()
    assert list(roots.staging.iterdir()) == []


def test_clear_staging_unlinks_a_symlink_without_following_it(roots):
    roots.ensure()
    target = roots.drafts / "keep"
    target.mkdir(parents=True)
    (target / "preset.yml").write_text("schema: 1\n", encoding="utf-8")
    try:
        os.symlink(target, roots.staging / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        return

    assert paths.clear_staging(roots) == 1
    assert (target / "preset.yml").exists()


def test_clear_staging_without_a_staging_folder_does_nothing(roots):
    assert paths.clear_staging(roots) == 0


@pytest.mark.parametrize("value", ["abc", "01M4NGDDGASNZ1SFY7236C95QW", "field-catalog-all-fields", "a_b-C9"])
def test_preset_ids_follow_the_core_rule(value):
    assert paths.check_preset_id(value) == value


@pytest.mark.parametrize("value", ["ab", "a" * 65, "with space", "dots.not", "../x", "", None, 12])
def test_preset_ids_outside_the_core_rule_are_refused(value):
    with pytest.raises(ValueError):
        paths.check_preset_id(value)


def test_draft_ids_are_ulids_and_stamps_are_timestamps():
    assert paths.check_draft_id("01M4NGDDGASNZ1SFY7236C95QW") == "01M4NGDDGASNZ1SFY7236C95QW"
    assert paths.check_stamp("20261015T113000.123456") == "20261015T113000.123456"
    for bad in ("01m4ngddgasnz1sfy7236c95qw", "../etc", "01M4NGDDGASNZ1SFY7236C95Q"):
        with pytest.raises(ValueError):
            paths.check_draft_id(bad)
    for bad in ("2026-10-15", "20261015T113000", "../x", "20261015T113000.123456/x"):
        with pytest.raises(ValueError):
            paths.check_stamp(bad)


@pytest.mark.parametrize(
    "model, variant, expected",
    [("MyModel", "v1", "MyModel/v1"), ("MyModel", None, "MyModel"), (" Flux2 ", " official ", "Flux2/official"), ("a.b_c-d", "", "a.b_c-d")],
)
def test_target_dirs_are_one_or_two_plain_segments(model, variant, expected):
    assert paths.target_dir(model, variant) == expected
    assert paths.check_target_dir(expected) == expected


@pytest.mark.parametrize(
    "value", ["", "/abs", "a/b/c", "a//b", ".hidden", "..", "../x", "a/..", "with space", "a\\b", "x" * 65, "-lead"]
)
def test_target_dirs_outside_the_rule_are_refused(value):
    with pytest.raises(ValueError):
        paths.check_target_dir(value)


def test_the_validated_paths_stay_under_their_roots(roots):
    assert paths.draft_dir(roots, "01M4NGDDGASNZ1SFY7236C95QW") == roots.drafts / "01M4NGDDGASNZ1SFY7236C95QW"
    assert paths.local_preset_dir(roots, "MyModel/v1") == roots.local_presets / "MyModel" / "v1"
    assert paths.history_entry(roots, "my-preset", "20261015T113000.123456") == (
        roots.history / "my-preset" / "20261015T113000.123456"
    )
    with pytest.raises(ValueError):
        paths.draft_dir(roots, "../escape")
    with pytest.raises(ValueError):
        paths.history_root(roots, "../escape")
