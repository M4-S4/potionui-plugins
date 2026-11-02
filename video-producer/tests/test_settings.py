from pathlib import Path

import pytest
import yaml

from backend.settings import (
    DEFAULTS,
    DRAFT_RESOLUTIONS,
    LOCALES,
    all_settings,
    get_setting,
    last_project_id,
    parse_locale,
    parse_setting,
    set_last_project_id,
    set_user_locale,
    user_locale,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _manifest_settings():
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yml").read_text(encoding="utf-8"))
    return {spec["name"]: spec for spec in manifest["settings"]}


def test_the_defaults_and_options_match_the_manifest():
    specs = _manifest_settings()

    assert set(specs) == set(DEFAULTS)
    for key, spec in specs.items():
        assert parse_setting(key, spec["default"]) == DEFAULTS[key], key
    assert [option["value"] for option in specs["draft_resolution"]["options"]] == list(DRAFT_RESOLUTIONS)
    for option in specs["draft_resolution"]["options"]:
        assert parse_setting("draft_resolution", option["value"]) == option["value"]


def test_the_defaults_are_the_documented_ones():
    assert DEFAULTS == {
        "draft_resolution": "832x480",
        "max_parallel_jobs": 2,
        "export_dir_quota_mb": 2048,
        "versions_kept": 50,
    }


@pytest.mark.parametrize("raw", [None, "", "   ", "\n"])
@pytest.mark.parametrize("key", sorted(DEFAULTS))
def test_an_unset_setting_is_its_default(key, raw):
    assert parse_setting(key, raw) == DEFAULTS[key]


@pytest.mark.parametrize(
    "key, raw, value",
    [
        ("draft_resolution", "832x480", "832x480"),
        ("draft_resolution", "960x544", "960x544"),
        ("draft_resolution", "1280x720", "1280x720"),
        ("draft_resolution", " 1280X720 ", "1280x720"),
        ("draft_resolution", "640x480", "832x480"),
        ("draft_resolution", "1920x1080", "832x480"),
        ("draft_resolution", "720p", "832x480"),
        ("draft_resolution", 720, "832x480"),
        ("max_parallel_jobs", "1", 1),
        ("max_parallel_jobs", "4", 4),
        ("max_parallel_jobs", " 8 ", 8),
        ("max_parallel_jobs", "16", 16),
        ("max_parallel_jobs", 3, 3),
        ("max_parallel_jobs", 3.0, 3),
        ("max_parallel_jobs", "4.0", 4),
        ("max_parallel_jobs", "0", 1),
        ("max_parallel_jobs", "-5", 1),
        ("max_parallel_jobs", "17", 16),
        ("max_parallel_jobs", "1000", 16),
        ("max_parallel_jobs", "2.5", 2),
        ("max_parallel_jobs", "many", 2),
        ("max_parallel_jobs", "nan", 2),
        ("max_parallel_jobs", "inf", 2),
        ("max_parallel_jobs", "-inf", 2),
        ("max_parallel_jobs", "1e400", 2),
        ("max_parallel_jobs", True, 2),
        ("max_parallel_jobs", [3], 2),
        ("export_dir_quota_mb", "1", 1),
        ("export_dir_quota_mb", "512", 512),
        ("export_dir_quota_mb", "1048576", 1048576),
        ("export_dir_quota_mb", " 4096 ", 4096),
        ("export_dir_quota_mb", 1024, 1024),
        ("export_dir_quota_mb", "0", 1),
        ("export_dir_quota_mb", "-1", 1),
        ("export_dir_quota_mb", "1048577", 1048576),
        ("export_dir_quota_mb", "99999999999", 1048576),
        ("export_dir_quota_mb", "1e3", 1000),
        ("export_dir_quota_mb", "1.5", 2048),
        ("export_dir_quota_mb", "2 GB", 2048),
        ("export_dir_quota_mb", "nan", 2048),
        ("export_dir_quota_mb", {"mb": 5}, 2048),
        ("versions_kept", "5", 5),
        ("versions_kept", "50", 50),
        ("versions_kept", " 120 ", 120),
        ("versions_kept", "500", 500),
        ("versions_kept", 7, 7),
        ("versions_kept", "4", 5),
        ("versions_kept", "0", 5),
        ("versions_kept", "-3", 5),
        ("versions_kept", "501", 500),
        ("versions_kept", "1e6", 500),
        ("versions_kept", "7.5", 50),
        ("versions_kept", "all", 50),
        ("versions_kept", "nan", 50),
    ],
)
def test_a_stored_setting_is_parsed_clamped_or_replaced_by_its_default(key, raw, value):
    assert parse_setting(key, raw) == value


def test_parsed_integers_are_ints_not_floats():
    assert type(parse_setting("max_parallel_jobs", "4.0")) is int
    assert type(parse_setting("export_dir_quota_mb", 512.0)) is int


@pytest.mark.parametrize("key", ["", "locale", "Draft_Resolution", "unknown"])
def test_an_unknown_key_raises_a_key_error(key):
    with pytest.raises(KeyError, match="video-producer has no setting"):
        parse_setting(key, "1")


def test_an_unknown_key_raises_even_when_the_value_is_unset():
    with pytest.raises(KeyError):
        parse_setting("unknown", None)


def test_get_setting_reads_the_admin_value_and_types_it(store):
    store[("max_parallel_jobs", None)] = "6"

    assert get_setting("max_parallel_jobs") == 6
    assert store.calls == [("get", "max_parallel_jobs", None)]


def test_get_setting_of_an_unset_setting_is_its_default(store):
    assert get_setting("draft_resolution") == "832x480"


def test_get_setting_of_an_unknown_key_raises(store):
    with pytest.raises(KeyError):
        get_setting("unknown")


def test_all_settings_are_the_defaults_when_nothing_is_stored(store):
    assert all_settings() == DEFAULTS
    assert all_settings() is not DEFAULTS


def test_all_settings_type_each_stored_value(store):
    store.update(
        {
            ("draft_resolution", None): "960x544",
            ("max_parallel_jobs", None): "3",
            ("export_dir_quota_mb", None): "100",
            ("versions_kept", None): "20",
        }
    )

    assert all_settings() == {
        "draft_resolution": "960x544",
        "max_parallel_jobs": 3,
        "export_dir_quota_mb": 100,
        "versions_kept": 20,
    }


def test_all_settings_replace_only_the_invalid_values(store):
    store.update({("draft_resolution", None): "bad", ("max_parallel_jobs", None): "5", ("export_dir_quota_mb", None): "x"})

    assert all_settings() == {
        "draft_resolution": "832x480",
        "max_parallel_jobs": 5,
        "export_dir_quota_mb": 2048,
        "versions_kept": 50,
    }


def test_all_settings_read_every_key_once_for_the_admin(store):
    all_settings()

    assert sorted(store.calls) == [("get", key, None) for key in sorted(DEFAULTS)]


def test_all_settings_never_include_the_locale(store):
    store[("locale", None)] = "fr"

    assert "locale" not in all_settings()


def test_the_locales_are_english_and_french():
    assert LOCALES == ("en", "fr")


@pytest.mark.parametrize(
    "raw, locale",
    [
        ("en", "en"),
        ("fr", "fr"),
        (" FR ", "fr"),
        ("En", "en"),
        ("de", None),
        ("", None),
        ("en-US", None),
        (None, None),
        (5, None),
    ],
)
def test_parse_locale_keeps_a_supported_code_only(raw, locale):
    assert parse_locale(raw) == locale


def test_user_locale_is_none_when_the_user_never_chose_one(store):
    assert user_locale("user-1") is None
    assert store.calls == [("get", "locale", "user-1")]


def test_user_locale_reads_the_locale_of_that_user(store):
    store.update({("locale", "user-1"): "fr", ("locale", "user-2"): "en", ("locale", None): "en"})

    assert user_locale("user-1") == "fr"
    assert user_locale("user-2") == "en"
    assert user_locale("user-3") is None
    assert store.calls == [("get", "locale", "user-1"), ("get", "locale", "user-2"), ("get", "locale", "user-3")]


def test_user_locale_ignores_a_stored_locale_it_does_not_support(store):
    store[("locale", "user-1")] = "de"

    assert user_locale("user-1") is None


@pytest.mark.parametrize("locale", ["en", "fr"])
def test_set_user_locale_saves_it_for_that_user_and_returns_it(store, locale):
    assert set_user_locale("user-1", locale) == locale

    assert store == {("locale", "user-1"): locale}
    assert store.calls == [("set", "locale", locale, "user-1")]
    assert user_locale("user-1") == locale


@pytest.mark.parametrize("locale", ["de", "FR", " fr", "fr ", "", "en-US", None, 3, True, ["fr"], {"fr": 1}])
def test_set_user_locale_refuses_an_unsupported_one_and_saves_nothing(store, locale):
    with pytest.raises(ValueError):
        set_user_locale("user-1", locale)

    assert store == {}
    assert store.calls == []


def test_all_settings_never_include_the_last_project(store):
    store[("last_project_id", None)] = "01PROJECT"

    assert "last_project_id" not in all_settings()


def test_last_project_id_is_none_when_the_user_never_opened_one(store):
    assert last_project_id("user-1") is None
    assert store.calls == [("get", "last_project_id", "user-1")]


@pytest.mark.parametrize("stored", [None, ""])
def test_an_empty_stored_last_project_id_is_none(store, stored):
    store[("last_project_id", "user-1")] = stored

    assert last_project_id("user-1") is None


def test_last_project_id_is_kept_per_user(store):
    set_last_project_id("user-1", "01PROJECTA")
    set_last_project_id("user-2", "01PROJECTB")

    assert last_project_id("user-1") == "01PROJECTA"
    assert last_project_id("user-2") == "01PROJECTB"
    assert last_project_id("user-3") is None
    assert store.calls[:2] == [
        ("set", "last_project_id", "01PROJECTA", "user-1"),
        ("set", "last_project_id", "01PROJECTB", "user-2"),
    ]


def test_set_last_project_id_to_none_forgets_it(store):
    set_last_project_id("user-1", "01PROJECTA")

    set_last_project_id("user-1", None)

    assert last_project_id("user-1") is None
    assert store == {("last_project_id", "user-1"): None}
