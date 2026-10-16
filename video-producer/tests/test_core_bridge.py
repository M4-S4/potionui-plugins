import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend import core_bridge
from backend.core_bridge import PresetState
from src.plugin_api.limits import LimitStatus

LOGGER = "plugins.video-producer"


_ModelFileUnavailable = type("ModelFileUnavailable", (Exception,), {})


def _container(monkeypatch, **parts):
    container = SimpleNamespace(**parts)
    monkeypatch.setattr(core_bridge, "api_hooks", SimpleNamespace(get_container=lambda: container))
    return container


def _raise(message):
    def raiser(*args, **kwargs):
        raise RuntimeError(message)

    return raiser


def test_a_plugin_setting_that_was_never_stored_is_none(monkeypatch):
    class Repository:
        def get_plugin_setting(self, plugin_id, key, user_id=None):
            return None

    monkeypatch.setattr(core_bridge, "PluginRepository", Repository)

    assert core_bridge.get_plugin_setting("max_parallel_jobs") is None


def test_a_plugin_setting_is_read_and_written_under_the_plugin_id_for_the_asked_user(monkeypatch):
    calls = []

    class Repository:
        def get_plugin_setting(self, plugin_id, key, user_id=None):
            calls.append(("get", plugin_id, key, user_id))
            return SimpleNamespace(setting_value="fr")

        def set_plugin_setting(self, plugin_id, key, value, user_id=None):
            calls.append(("set", plugin_id, key, value, user_id))

    monkeypatch.setattr(core_bridge, "PluginRepository", Repository)

    assert core_bridge.get_plugin_setting("locale", user_id="user-1") == "fr"
    assert core_bridge.get_plugin_setting("max_parallel_jobs") == "fr"
    core_bridge.set_plugin_setting("locale", "en", user_id="user-1")
    core_bridge.set_plugin_setting("max_parallel_jobs", "4")

    assert calls == [
        ("get", "video-producer", "locale", "user-1"),
        ("get", "video-producer", "max_parallel_jobs", None),
        ("set", "video-producer", "locale", "en", "user-1"),
        ("set", "video-producer", "max_parallel_jobs", "4", None),
    ]


def test_limit_status_flattens_the_core_status(monkeypatch):
    asked = []

    def limit_status(user_id, kind):
        asked.append((user_id, kind))
        return LimitStatus(kind=kind, limit=120, used=30, resets_at=datetime(2026, 11, 1, tzinfo=timezone.utc))

    monkeypatch.setattr(core_bridge.api_limits, "limit_status", limit_status)

    assert core_bridge.limit_status("user-1", "video-producer.gpu_minutes") == {
        "limit": 120,
        "used": 30,
        "remaining": 90.0,
        "exempt": False,
        "resets_at": "2026-11-01T00:00:00+00:00",
    }
    assert asked == [("user-1", "video-producer.gpu_minutes")]


def test_limit_status_without_a_reset_has_none(monkeypatch):
    monkeypatch.setattr(core_bridge.api_limits, "limit_status", lambda user_id, kind: LimitStatus(kind=kind))

    assert core_bridge.limit_status("user-1", "k")["resets_at"] is None


def test_limit_status_converts_the_reset_to_utc(monkeypatch):
    reset = datetime(2026, 11, 1, 1, 30, tzinfo=timezone(timedelta(hours=-5)))
    monkeypatch.setattr(core_bridge.api_limits, "limit_status", lambda user_id, kind: LimitStatus(kind=kind, resets_at=reset))

    assert core_bridge.limit_status("user-1", "k")["resets_at"] == "2026-11-01T06:30:00+00:00"


def test_limit_status_is_unlimited_and_logged_when_the_core_cannot_answer(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge.api_limits, "limit_status", _raise("AppContainer not initialized yet"))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        status = core_bridge.limit_status("user-1", "video-producer.gpu_minutes")

    assert status == {"limit": None, "used": None, "remaining": None, "exempt": False, "resets_at": None}
    assert "treating it as unlimited" in caplog.text


def test_notify_sends_a_plugin_notification_to_the_user(monkeypatch):
    sent = []
    monkeypatch.setattr(core_bridge.api_notifications, "notify", lambda **kwargs: sent.append(kwargs))
    metadata = {"take_id": "t-1"}

    core_bridge.notify(
        user_id="user-1",
        notification_type="video-producer.take_done",
        title="Take ready",
        message="Shot 3 is ready.",
        level="success",
        metadata=metadata,
    )

    assert sent == [
        {
            "source": "video-producer",
            "title": "Take ready",
            "message": "Shot 3 is ready.",
            "user_id": "user-1",
            "type": "video-producer.take_done",
            "level": "success",
            "category": "plugin",
            "metadata": {"take_id": "t-1"},
        }
    ]
    assert sent[0]["metadata"] is not metadata


def test_notify_sends_no_metadata_when_there_is_none(monkeypatch):
    sent = []
    monkeypatch.setattr(core_bridge.api_notifications, "notify", lambda **kwargs: sent.append(kwargs))

    core_bridge.notify(user_id="user-1", notification_type="video-producer.take_failed", title="Take failed", metadata={})

    assert sent[0]["metadata"] is None
    assert (sent[0]["message"], sent[0]["level"]) == ("", "info")


@pytest.mark.parametrize("user_id", ["", None])
def test_notify_without_a_user_sends_nothing(monkeypatch, caplog, user_id):
    sent = []
    monkeypatch.setattr(core_bridge.api_notifications, "notify", lambda **kwargs: sent.append(kwargs))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        core_bridge.notify(user_id=user_id, notification_type="video-producer.take_done", title="x")

    assert sent == []
    assert "no user to notify" in caplog.text


def test_notify_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge.api_notifications, "notify", _raise("notifications are down"))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        core_bridge.notify(user_id="user-1", notification_type="video-producer.take_done", title="x")

    assert "Could not send" in caplog.text


def test_find_ffmpeg_asks_the_core(monkeypatch):
    monkeypatch.setattr(core_bridge.api_media, "find_ffmpeg", lambda: "/opt/ffmpeg")

    assert core_bridge.find_ffmpeg() == "/opt/ffmpeg"


def test_run_on_app_loop_hands_the_coroutine_to_the_core(monkeypatch):
    handed = []
    marker = object()
    monkeypatch.setattr(core_bridge.api_hooks, "run_on_app_loop", lambda coro: handed.append(coro) or marker)

    assert core_bridge.run_on_app_loop("coroutine") is marker
    assert handed == ["coroutine"]


def test_enabled_backends_are_the_entries_of_list_backends_as_they_come(monkeypatch):
    entries = [
        {
            "id": "b-1",
            "name": "This machine",
            "engine": "native",
            "driver": "native.local",
            "is_default": True,
            "execution_device": "this_host_gpu",
            "max_concurrent_runs": 1,
            "vram_total_gb": 24.0,
            "vram_free_gb": 20.5,
        },
        {
            "id": "b-2",
            "name": "OpenRouter",
            "engine": "cloud",
            "driver": "cloud.openrouter",
            "is_default": False,
            "has_api_key": True,
            "execution_device": "unestablished",
            "max_concurrent_runs": None,
            "vram_total_gb": None,
            "vram_free_gb": None,
        },
    ]
    monkeypatch.setattr(core_bridge, "api_backends", SimpleNamespace(list_backends=lambda: entries))
    _container(monkeypatch)

    assert core_bridge.enabled_backends() == entries


def test_list_presets_asks_the_core_for_the_presets_of_that_user(monkeypatch):
    asked = []
    described = [SimpleNamespace(id="01ABC")]
    monkeypatch.setattr(
        core_bridge, "api_presets", SimpleNamespace(list_presets=lambda user: asked.append(user) or described)
    )
    user = SimpleNamespace(id="user-1")

    assert core_bridge.list_presets(user) is described
    assert asked == [user]


def test_enabled_cloud_video_models_counts_the_entries_with_a_video_output(monkeypatch):
    asked = []
    entries = [
        SimpleNamespace(outputs=["image"]),
        SimpleNamespace(outputs=["image", "video"]),
        SimpleNamespace(outputs=["video"]),
        SimpleNamespace(outputs=None),
        SimpleNamespace(outputs=[]),
    ]
    repository = SimpleNamespace(list_enabled=lambda backend_id: asked.append(backend_id) or entries)
    _container(monkeypatch, cloud_catalog=SimpleNamespace(repository=repository))

    assert core_bridge.enabled_cloud_video_models("c-1") == 2
    assert asked == ["c-1"]


def _presets(monkeypatch, name="Wan", installed=True, summary=None, groups=0):
    monkeypatch.setattr(
        core_bridge,
        "api_presets",
        SimpleNamespace(describe_preset=lambda preset_id: None if name is None else SimpleNamespace(name=name)),
    )
    db_repo = SimpleNamespace(
        is_preset_installed=lambda preset_id: installed,
        get_preset_assignment_summary=lambda preset_id: summary,
    )
    group_repo = SimpleNamespace(get_group_count_for_preset=lambda preset_id: groups)
    _container(monkeypatch, preset_collaborators=SimpleNamespace(db_repo=db_repo, group_repo=group_repo))


def test_a_preset_the_core_does_not_know_is_not_loaded(monkeypatch):
    _presets(monkeypatch, name=None)

    assert core_bridge.preset_state("01ABC") == PresetState(
        id="01ABC", name="01ABC", loaded=False, installed=False, assigned=False
    )


def test_a_loaded_preset_that_is_not_installed_is_never_assigned(monkeypatch):
    _presets(monkeypatch, installed=False, summary={"total_assignments": 4}, groups=2)

    assert core_bridge.preset_state("01ABC") == PresetState(
        id="01ABC", name="Wan", loaded=True, installed=False, assigned=False
    )


def test_an_installed_preset_assigned_to_users_is_assigned(monkeypatch):
    _presets(monkeypatch, summary={"total_assignments": 2})

    assert core_bridge.preset_state("01ABC") == PresetState(id="01ABC", name="Wan", loaded=True, installed=True, assigned=True)


def test_an_installed_preset_assigned_to_a_group_only_is_assigned(monkeypatch):
    _presets(monkeypatch, summary={"total_assignments": 0}, groups=1)

    assert core_bridge.preset_state("01ABC").assigned is True


@pytest.mark.parametrize("summary", [None, {}, {"total_assignments": 0}, {"total_assignments": None}])
def test_an_installed_preset_with_no_assignment_is_not_assigned(monkeypatch, summary):
    _presets(monkeypatch, summary=summary, groups=0)

    state = core_bridge.preset_state("01ABC")

    assert (state.loaded, state.installed, state.assigned) == (True, True, False)


def _field(name, type="model", recommendations=None, children=None):
    configuration = None if recommendations is None else {"recommendations": recommendations}
    return SimpleNamespace(name=name, type=type, configuration=configuration, children=children)


def _template(*modes):
    return SimpleNamespace(
        modes={f"mode-{index}": SimpleNamespace(forms=[SimpleNamespace(fields=fields) for fields in forms])
               for index, forms in enumerate(modes)}
    )


def _hashes(monkeypatch, template, preset_id="01ABC"):
    repository = SimpleNamespace(find_preset_by_id=lambda requested: template if requested == preset_id else None)
    _container(monkeypatch, file_preset_repository=repository)


def test_the_recommended_hashes_are_grouped_by_the_named_model_fields(monkeypatch):
    template = _template(
        [[_field("model", recommendations=[{"sha256": "A" * 64}, {"sha256": " " + "b" * 64 + " "}]),
          _field("vae", recommendations=[{"sha256": "c" * 64}])]],
    )
    _hashes(monkeypatch, template)

    assert core_bridge.preset_model_hashes("01ABC", ["model", "text_encoder"]) == {
        "model": {"a" * 64, "b" * 64},
        "text_encoder": set(),
    }


def test_the_hashes_of_every_mode_and_form_are_merged_and_deduplicated(monkeypatch):
    template = _template(
        [[_field("model", recommendations=[{"sha256": "a" * 64}])], [_field("model", recommendations=[{"sha256": "b" * 64}])]],
        [[_field("model", recommendations=[{"sha256": "a" * 64}])]],
    )
    _hashes(monkeypatch, template)

    assert core_bridge.preset_model_hashes("01ABC", ["model"]) == {"model": {"a" * 64, "b" * 64}}


def test_the_hashes_of_nested_fields_are_found(monkeypatch):
    inner = _field("text_encoder", recommendations=[{"sha256": "d" * 64}])
    group = _field("advanced", type="group", children=[_field("wrapper", type="group", children=[inner])])
    _hashes(monkeypatch, _template([[group]]))

    assert core_bridge.preset_model_hashes("01ABC", ["text_encoder"]) == {"text_encoder": {"d" * 64}}


def test_only_model_fields_with_a_usable_sha256_count(monkeypatch):
    fields = [
        _field("model", type="select", recommendations=[{"sha256": "a" * 64}]),
        _field("text_encoder", recommendations=[{"sha256": ""}, {"sha256": None}, {"name": "no hash"}, "not a mapping"]),
        _field("video_vae", recommendations=None),
        _field("audio_vae", recommendations=[]),
    ]
    _hashes(monkeypatch, _template([fields]))

    assert core_bridge.preset_model_hashes("01ABC", ["model", "text_encoder", "video_vae", "audio_vae"]) == {
        "model": set(),
        "text_encoder": set(),
        "video_vae": set(),
        "audio_vae": set(),
    }


def test_a_preset_without_template_has_no_hashes(monkeypatch):
    _hashes(monkeypatch, None)

    assert core_bridge.preset_model_hashes("01ABC", ["model", "vae"]) == {"model": set(), "vae": set()}


def test_a_template_without_modes_has_no_hashes(monkeypatch):
    _hashes(monkeypatch, SimpleNamespace(modes=None))

    assert core_bridge.preset_model_hashes("01ABC", ["model"]) == {"model": set()}


def test_a_model_file_is_present_when_the_catalog_resolves_it(monkeypatch):
    resolved = []
    monkeypatch.setattr(
        core_bridge,
        "api_models",
        SimpleNamespace(
            model_for_sha256=lambda sha256: {"id": "m-1"},
            resolve_model_file=lambda model_id: resolved.append(model_id) or "file",
        ),
    )

    assert core_bridge.model_file_present("a" * 64) is True
    assert resolved == ["m-1"]


@pytest.mark.parametrize("model", [None, {}, {"id": ""}, {"name": "no id"}])
def test_a_model_the_catalog_does_not_hold_is_not_present(monkeypatch, model):
    monkeypatch.setattr(
        core_bridge,
        "api_models",
        SimpleNamespace(model_for_sha256=lambda sha256: model, resolve_model_file=_raise("must not be asked")),
    )

    assert core_bridge.model_file_present("a" * 64) is False


def test_a_model_whose_file_is_unavailable_is_not_present(monkeypatch):
    def unavailable(model_id):
        raise _ModelFileUnavailable("gone")

    monkeypatch.setattr(
        core_bridge, "api_models", SimpleNamespace(model_for_sha256=lambda sha256: {"id": "m-1"}, resolve_model_file=unavailable)
    )

    assert core_bridge.model_file_present("a" * 64) is False


def test_any_other_error_resolving_a_model_file_is_not_hidden(monkeypatch):
    monkeypatch.setattr(
        core_bridge,
        "api_models",
        SimpleNamespace(model_for_sha256=lambda sha256: {"id": "m-1"}, resolve_model_file=_raise("disk error")),
    )

    with pytest.raises(RuntimeError, match="disk error"):
        core_bridge.model_file_present("a" * 64)
