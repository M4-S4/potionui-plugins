import asyncio
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


def test_the_hashes_can_be_read_from_the_named_modes_only(monkeypatch):
    template = _template(
        [[_field("upscale_model", recommendations=[{"sha256": "a" * 64}])]],
        [[_field("upscale_model", recommendations=[{"sha256": "b" * 64}])]],
    )
    _hashes(monkeypatch, template)

    assert core_bridge.preset_model_hashes("01ABC", ["upscale_model"], modes=["mode-1"]) == {"upscale_model": {"b" * 64}}
    assert core_bridge.preset_model_hashes("01ABC", ["upscale_model"], modes=["upscale"]) == {"upscale_model": set()}


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


def test_resolve_media_relays_the_reference_to_the_core_as_the_user(monkeypatch):
    asked = []
    answer = {"value": "uploads/a.png", "media_type": "image", "original_filename": "a.png", "origin": None}

    def resolve_media_ref(user, ref):
        asked.append((user, ref))
        return answer

    monkeypatch.setattr(core_bridge, "api_generation", SimpleNamespace(resolve_media_ref=resolve_media_ref))
    user = SimpleNamespace(id="user-1")
    ref = {"kind": "library", "item_id": "i-1"}

    resolved = core_bridge.resolve_media(user, ref)

    assert resolved == answer and resolved is not answer
    assert asked == [(user, ref)]


def test_resolve_media_lets_the_core_refusal_through(monkeypatch):
    def resolve_media_ref(user, ref):
        raise core_bridge.MediaRefError("not_found", "The referenced media is not available")

    monkeypatch.setattr(core_bridge, "api_generation", SimpleNamespace(resolve_media_ref=resolve_media_ref))

    with pytest.raises(core_bridge.MediaRefError) as caught:
        core_bridge.resolve_media(SimpleNamespace(id="user-1"), {"kind": "library", "item_id": "i-1"})

    assert caught.value.code == "not_found"


def test_the_media_ref_error_is_the_one_the_core_raises():
    from src.plugin_api.generation import MediaRefError

    assert core_bridge.MediaRefError is MediaRefError
    assert "MediaRefError" in core_bridge.__all__ and "resolve_media" in core_bridge.__all__


def test_every_name_the_bridge_exports_exists():
    assert all(hasattr(core_bridge, name) for name in core_bridge.__all__)


def test_get_user_asks_the_core_for_the_user_with_that_id(monkeypatch):
    user = SimpleNamespace(id="user-1")
    monkeypatch.setattr(core_bridge, "api_identity", SimpleNamespace(get_user=lambda user_id: user if user_id == "user-1" else None))

    assert core_bridge.get_user("user-1") is user
    assert core_bridge.get_user("user-9") is None


def test_bind_director_media_promotes_a_text_document_to_image_to_video():
    request = {
        "preset_id": "p",
        "form_data": {"video_director": {"schema_version": 1, "mode": "t2v", "settings": {}, "segments": [{"id": "seg-1"}], "media": []}},
    }

    bound = core_bridge.bind_director_media(request, "first", {"value": "uploads/a.png", "media_type": "image"}, promote=True)

    assert bound["form_data"]["video_director"]["mode"] == "i2v"
    assert bound["form_data"]["video_director"]["media"][0]["media"]["path"] == "uploads/a.png"
    assert request["form_data"]["video_director"]["mode"] == "t2v"


def test_the_generation_calls_go_to_the_core_as_the_user(monkeypatch):
    calls = []

    async def submit_generation(user, request):
        calls.append(("submit", user.id, request))
        return {"generation_id": "gen-1", "status": "pending", "queue_position": 2}

    async def preview_memory(user, request):
        calls.append(("preview", user.id, request))
        return {"estimate": {}}

    async def cancel_generation(user, generation_id):
        calls.append(("cancel", user.id, generation_id))
        return 1

    def list_generation_files(user, generation_id):
        calls.append(("files", user.id, generation_id))
        return [{"id": "f-1"}]

    monkeypatch.setattr(
        core_bridge,
        "api_generation",
        SimpleNamespace(
            submit_generation=submit_generation,
            preview_memory=preview_memory,
            cancel_generation=cancel_generation,
            list_generation_files=list_generation_files,
        ),
    )
    user = SimpleNamespace(id="user-1")
    request = {"preset_id": "p"}

    assert asyncio.run(core_bridge.submit_generation(user, request)) == {"generation_id": "gen-1", "status": "pending", "queue_position": 2}
    assert asyncio.run(core_bridge.preview_memory(user, request)) == {"estimate": {}}
    assert asyncio.run(core_bridge.cancel_generation(user, "gen-1")) is True
    assert core_bridge.list_generation_files(user, "gen-1") == [{"id": "f-1"}]
    assert [call[:2] for call in calls] == [("submit", "user-1"), ("preview", "user-1"), ("cancel", "user-1"), ("files", "user-1")]
    assert calls[0][2] == request and calls[0][2] is not request


class _Row:
    def __init__(self, **values):
        self.values = values

    def to_dict(self):
        return dict(self.values)


def test_the_state_of_a_live_generation_is_completed_from_its_stored_row(monkeypatch):
    monkeypatch.setattr(
        core_bridge,
        "api_generation",
        SimpleNamespace(generation_state=lambda user, generation_id: {"id": generation_id, "status": "running", "progress": 0.5}),
    )
    row = _Row(
        backend_id="b-local",
        started_at="2026-10-17T10:00:00+00:00",
        duration_ms=None,
        error_code=None,
        error_user_message=None,
        error_message=None,
    )
    row.error_detail = "RuntimeError: boom"
    _container(monkeypatch, generation_repository=SimpleNamespace(get_by_id={"gen-1": row}.get))

    assert core_bridge.generation_state(SimpleNamespace(id="user-1"), "gen-1") == {
        "id": "gen-1",
        "status": "running",
        "progress": 0.5,
        "backend_id": "b-local",
        "started_at": "2026-10-17T10:00:00+00:00",
        "duration_ms": None,
        "error_code": None,
        "error_user_message": None,
        "error_message": None,
        "error_detail": "RuntimeError: boom",
    }


def test_the_state_of_a_stored_generation_needs_no_second_read(monkeypatch):
    stored = {
        "id": "gen-1",
        "status": "completed",
        "backend_id": "b",
        "started_at": None,
        "duration_ms": 61000,
        "error_code": None,
        "error_user_message": None,
        "error_message": None,
        "error_detail": None,
    }
    monkeypatch.setattr(core_bridge, "api_generation", SimpleNamespace(generation_state=lambda user, generation_id: stored))
    _container(monkeypatch, generation_repository=SimpleNamespace(get_by_id=_raise("must not be asked")))

    assert core_bridge.generation_state(SimpleNamespace(id="user-1"), "gen-1") == stored


def test_a_stored_row_that_cannot_be_read_leaves_its_keys_empty(monkeypatch, caplog):
    monkeypatch.setattr(core_bridge, "api_generation", SimpleNamespace(generation_state=lambda user, generation_id: {"status": "pending"}))
    _container(monkeypatch, generation_repository=SimpleNamespace(get_by_id=_raise("database is locked")))

    state = core_bridge.generation_state(SimpleNamespace(id="user-1"), "gen-1")

    assert state == {
        "status": "pending",
        "backend_id": None,
        "started_at": None,
        "duration_ms": None,
        "error_code": None,
        "error_user_message": None,
        "error_message": None,
        "error_detail": None,
    }
    assert "Could not read the stored row of generation gen-1" in caplog.text


def test_limit_events_are_recorded_and_refunded_without_ever_raising(monkeypatch, caplog):
    calls = []

    class Events:
        @staticmethod
        def record(user_id, kind, units=1, ref_id=None):
            calls.append(("record", user_id, kind, units, ref_id))
            return "event-1"

        @staticmethod
        def refund(ref_id):
            calls.append(("refund", ref_id))
            return 2

    monkeypatch.setattr(core_bridge, "LimitEvents", Events)

    assert core_bridge.record_limit_event("user-1", "video-producer.gpu_minutes", 1.5, "video-producer:t-1") is True
    assert core_bridge.refund_limit_event("video-producer:t-1") == 2
    assert calls == [("record", "user-1", "video-producer.gpu_minutes", 1.5, "video-producer:t-1"), ("refund", "video-producer:t-1")]

    monkeypatch.setattr(core_bridge, "LimitEvents", SimpleNamespace(record=_raise("no container"), refund=_raise("no container")))
    assert core_bridge.record_limit_event("user-1", "k", 1.0, "r") is False
    assert core_bridge.refund_limit_event("r") == 0
    assert "Could not record 1.0 units of k under r" in caplog.text
    assert "Could not refund the usage recorded under r" in caplog.text


def test_the_cost_of_a_cloud_run_is_asked_of_the_core(monkeypatch):
    asked = []

    def estimate_cloud_cost(user, model_id, shots):
        asked.append((user.id, model_id, shots))
        return {"known": True, "total_usd": "0.50"}

    monkeypatch.setattr(core_bridge, "api_cloud", SimpleNamespace(estimate_cloud_cost=estimate_cloud_cost))
    shots = ({"task": "txt2video", "params": {"duration_s": 4}},)

    assert core_bridge.estimate_cloud_cost(SimpleNamespace(id="admin-1"), "cm-1", shots) == {"known": True, "total_usd": "0.50"}
    assert asked == [("admin-1", "cm-1", [{"task": "txt2video", "params": {"duration_s": 4}}])]


def _entry(slug, outputs=("video",), model_id="cm-1", **spec):
    return SimpleNamespace(
        slug=slug,
        label=slug.title(),
        provider_model_id=f"vendor/{slug}",
        tasks=["txt2video", "img2video"],
        outputs=list(outputs),
        model_id=model_id,
        spec=SimpleNamespace(
            typical_seconds=spec.get("typical_seconds", 60),
            max_seconds=spec.get("max_seconds", 300),
            params=spec.get("params", ()),
            inputs=spec.get("inputs", ()),
        ),
    )


def test_the_cloud_video_models_of_a_backend_are_the_enabled_entries_with_a_catalog_model(monkeypatch):
    entries = [_entry("veo"), _entry("flux", outputs=("image",)), _entry("orphan", model_id=None)]
    _container(monkeypatch, cloud_catalog=SimpleNamespace(repository=SimpleNamespace(list_enabled=lambda backend_id: entries)))

    assert core_bridge.cloud_video_models("b-cloud") == [
        {
            "id": "cm-1",
            "name": "Veo",
            "provider_model_id": "vendor/veo",
            "tasks": ["img2video", "txt2video"],
            "typical_seconds": 60,
            "max_seconds": 300,
            "inputs": [],
        }
    ]


def test_a_cloud_model_comes_with_its_parameters_and_media_inputs(monkeypatch):
    param = SimpleNamespace(
        name="duration_s", kind="enum", values=(4, 8), minimum=None, maximum=None, step=None, default=8, tasks=frozenset({"txt2video"})
    )
    media = SimpleNamespace(role="first_frame", tasks=frozenset({"img2video"}))
    entry = _entry("veo", params=(param,), inputs=(media,))
    resolved = {"cm-1": SimpleNamespace(entry=entry, spec=entry.spec, backend_id="b-cloud")}
    _container(monkeypatch, cloud_capabilities=SimpleNamespace(resolve=resolved.get))

    model = core_bridge.cloud_model("cm-1")

    assert model["backend_id"] == "b-cloud" and model["name"] == "Veo"
    assert model["params"] == [
        {"name": "duration_s", "kind": "enum", "values": [4, 8], "minimum": None, "maximum": None, "step": None, "default": 8, "tasks": ["txt2video"]}
    ]
    assert model["inputs"] == [{"role": "first_frame", "tasks": ["img2video"]}]
    assert core_bridge.cloud_model("cm-9") is None


def test_a_cloud_model_that_makes_no_video_is_none(monkeypatch):
    entry = _entry("flux", outputs=("image",))
    _container(monkeypatch, cloud_capabilities=SimpleNamespace(resolve=lambda model_id: SimpleNamespace(entry=entry, spec=entry.spec)))

    assert core_bridge.cloud_model("cm-1") is None


def _form_field(name, type="select", required=False, default=None, configuration=None, children=None):
    return SimpleNamespace(name=name, type=type, required=required, default=default, configuration=configuration, children=children)


def _form(name, fields, default=False, order=0):
    return SimpleNamespace(name=name, fields=fields, default=default, order=order)


def _templates(monkeypatch, template, shared):
    repository = SimpleNamespace(
        find_preset_by_id=lambda preset_id: template if preset_id == "01ABC" else None,
        preset_loader=SimpleNamespace(shared_path=shared),
    )
    _container(monkeypatch, file_preset_repository=repository)


def test_the_fields_of_a_mode_carry_their_options_and_recommended_files(monkeypatch, tmp_path):
    (tmp_path / "preset" / "files").mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "preset" / "files" / "sizes.yml").write_text(
        '- { value: "1344x768", description: "Widescreen" }\n- "768x768"\n', encoding="utf-8"
    )
    (tmp_path / "shared" / "more.yml").write_text('options:\n  - { value: "640x640" }\n  - { value: "768x768" }\n', encoding="utf-8")
    resolution = _form_field(
        "resolution",
        type="resolution",
        default="1344x768",
        configuration={
            "files": [
                {"path": "{{ paths.preset }}/files/sizes.yml"},
                {"path": "{{paths._shared}}/more.yml"},
                {"path": "{{ paths.preset }}/files/missing.yml"},
            ]
        },
    )
    model = _form_field(
        "model",
        type="model",
        required=True,
        configuration={
            "recommendations": [
                {"name": "dit.safetensors", "sha256": " ABC ", "link": "https://hf.co/x/dit.safetensors?download=1"},
                {"name": "Human label", "link": "https://hf.co/x/other_fp16.safetensors"},
                {"name": "No file"},
                "not a mapping",
            ]
        },
    )
    target = _form_field("target", configuration={"options": [{"label": "HD", "value": "hd"}, "2k", {"label": "none"}]})
    section = _form_field(None, type="section", children=[resolution, _form_field(None, type="row", children=[model])])
    quick = _form("quick", [_form_field("target", type="slider")], order=0)
    full = _form("full", [section, target], default=True, order=1)
    template = SimpleNamespace(path=str(tmp_path / "preset"), modes={"video": SimpleNamespace(forms=[quick, full])})
    _templates(monkeypatch, template, tmp_path / "shared")

    fields = core_bridge.preset_form_fields("01ABC", "video")

    assert list(fields) == ["resolution", "model", "target"]
    assert fields["resolution"] == {
        "type": "resolution",
        "required": False,
        "default": "1344x768",
        "options": [
            {"value": "1344x768", "label": "Widescreen"},
            {"value": "768x768", "label": "768x768"},
            {"value": "640x640", "label": "640x640"},
        ],
        "recommendations": [],
        "label": None,
        "group": [],
        "audience": "simple",
        "hidden": False,
        "gate": None,
        "limits": {},
        "reactions": [],
        "bound": False,
    }
    assert fields["model"]["recommendations"] == [
        {"sha256": "abc", "filename": "dit.safetensors"},
        {"sha256": None, "filename": "other_fp16.safetensors"},
    ]
    assert fields["model"]["required"] is True
    assert fields["target"]["type"] == "select"
    assert fields["target"]["options"] == [{"value": "hd", "label": "HD"}, {"value": "2k", "label": "2k"}]


def _described(name, type="slider", **attributes):
    return SimpleNamespace(
        name=name,
        type=type,
        required=attributes.pop("required", False),
        default=attributes.pop("default", None),
        configuration=attributes.pop("configuration", None),
        children=attributes.pop("children", None),
        **attributes,
    )


def test_the_fields_of_a_mode_carry_their_label_groups_audience_gate_limits_and_reactions(monkeypatch, tmp_path):
    steps = _described(
        "steps",
        label="Steps",
        default=24,
        configuration={"min": 1, "max": 100, "step": 1, "placeholder": "x"},
        reactions=[{"when": {"field": "speed_profile", "equals": "distilled"}, "then": {"set_value": 8, "set_disabled": False, "update_options": []}}],
    )
    sampler = _described("sampler", type="sampler", label="Sampler", configuration={"family": "ltx", "exclude": ["lcm"]})
    loras = _described(
        "loras", type="lora_picker", configuration={"model_type": "lora", "strength_min": -10.0, "strength_max": 10.0, "max_items": 10}
    )
    hidden = _described("i2v_model", type="model", visible=None)
    strength = _described("detail", label="Detail strength", default=0.5)
    gate = _described("detailer", type="gate", label="Detailer", default=False, children=[strength])
    advanced = _described(None, type="tab", label="Advanced", audience="advanced", children=[
        _described(None, type="section", label="Sampling", children=[steps, _described(None, type="row", children=[sampler])]),
        gate,
    ])
    i2v_tab = _described(None, type="tab", label="I2V", visible=False, children=[hidden])
    lora_tab = _described(None, type="tab", label="LoRA", children=[loras])
    director = _described("video_director_only", type="checkbox", hidden_when_video_director=True)
    bound = _described("generate_audio", type="checkbox", capability={"model_field": "model", "param": "generate_audio"})
    form = _form("custom", [_described(None, type="tabs", children=[advanced, i2v_tab, lora_tab]), director, bound], default=True)
    template = SimpleNamespace(path=str(tmp_path), modes={"video": SimpleNamespace(forms=[form])})
    _templates(monkeypatch, template, tmp_path)
    asked = []

    def registry(kind, configuration):
        asked.append((kind, dict(configuration)))
        return [{"value": "euler", "label": "Euler"}, {"value": "euler_ancestral", "label": "Euler ancestral"}]

    monkeypatch.setattr(core_bridge, "_registry_options", registry)

    fields = core_bridge.preset_form_fields("01ABC", "video")

    assert list(fields) == ["steps", "sampler", "detailer", "detail", "i2v_model", "loras", "video_director_only", "generate_audio"]
    assert {key: fields["steps"][key] for key in ("label", "group", "audience", "hidden", "gate", "limits", "default")} == {
        "label": "Steps",
        "group": ["Advanced", "Sampling"],
        "audience": "advanced",
        "hidden": False,
        "gate": None,
        "limits": {"min": 1, "max": 100, "step": 1},
        "default": 24,
    }
    assert fields["steps"]["reactions"] == [
        {"when": {"field": "speed_profile", "equals": "distilled"}, "then": {"set_value": 8, "set_disabled": False}}
    ]
    assert fields["sampler"]["options"] == [{"value": "euler", "label": "Euler"}, {"value": "euler_ancestral", "label": "Euler ancestral"}]
    assert asked == [("sampler", {"family": "ltx", "exclude": ["lcm"]})]
    assert (fields["detailer"]["gate"], fields["detail"]["gate"], fields["detail"]["group"]) == (None, "detailer", ["Advanced"])
    assert fields["i2v_model"]["hidden"] is True
    assert fields["loras"]["limits"] == {"strength_min": -10.0, "strength_max": 10.0, "max_items": 10, "model_type": "lora"}
    assert (fields["loras"]["audience"], fields["loras"]["group"]) == ("simple", ["LoRA"])
    assert fields["video_director_only"]["hidden"] is True
    assert (fields["generate_audio"]["bound"], fields["steps"]["bound"]) == (True, False)


def test_the_options_of_a_sampler_come_from_the_registry_and_none_when_it_cannot_be_read(monkeypatch):
    calls = []

    class Registry:
        def __init__(self, name):
            self.name = name

        def select(self, family=None, include=None, exclude=None):
            calls.append((self.name, family, include, exclude))
            if self.name == "broken":
                raise RuntimeError("no registry")
            return [SimpleNamespace(key="euler", label="Euler"), SimpleNamespace(key="beta", label=None)]

    import src.plugin_api as plugin_api

    monkeypatch.setattr(
        plugin_api, "sampling", SimpleNamespace(sampler_registry=Registry("samplers"), schedule_registry=Registry("broken")), raising=False
    )
    monkeypatch.setitem(__import__("sys").modules, "src.plugin_api.sampling", plugin_api.sampling)

    assert core_bridge._registry_options("sampler", {"family": "wan", "include": ["euler"]}) == [
        {"value": "euler", "label": "Euler"},
        {"value": "beta", "label": "beta"},
    ]
    assert core_bridge._registry_options("schedule", {}) == []
    assert calls == [("samplers", "wan", ["euler"], None), ("broken", None, None, None)]


def test_an_unknown_preset_or_mode_has_no_fields(monkeypatch, tmp_path):
    template = SimpleNamespace(path=str(tmp_path), modes={"video": SimpleNamespace(forms=[])})
    _templates(monkeypatch, template, tmp_path)

    assert core_bridge.preset_form_fields("01ABC", "video") == {}
    assert core_bridge.preset_form_fields("01ABC", "refs") is None
    assert core_bridge.preset_form_fields("01XYZ", "video") is None


def test_an_installed_model_is_found_by_file_name_too(monkeypatch):
    monkeypatch.setattr(
        core_bridge,
        "api_models",
        SimpleNamespace(
            model_for_sha256=lambda sha256: {"id": "m-1"} if sha256 == "abc" else None,
            model_for_path=lambda path: {"id": "m-2"} if path == "pos_emb.pt" else None,
            resolve_model_file=lambda model_id: "file",
        ),
    )

    assert core_bridge.installed_model_id("abc") == "m-1"
    assert core_bridge.installed_model_id("def") is None
    assert core_bridge.installed_model_for_file("pos_emb.pt") == "m-2"
    assert core_bridge.installed_model_for_file("other.pt") is None


def test_the_driver_of_a_preset_is_read_from_its_template(monkeypatch):
    templates = {"01CLOUD": SimpleNamespace(driver="cloud.openrouter"), "01NATIVE": SimpleNamespace(driver=None)}
    _container(monkeypatch, file_preset_repository=SimpleNamespace(find_preset_by_id=templates.get))

    assert core_bridge.preset_driver("01CLOUD") == "cloud.openrouter"
    assert core_bridge.preset_driver("01NATIVE") is None
    assert core_bridge.preset_driver("01NONE") is None


class _Driver:
    def __init__(self, root=None, blobs=None, break_after=None):
        self.root = root
        self.blobs = blobs or {}
        self.break_after = break_after
        self.chunk_sizes = []

    def local_path(self, key):
        return None if self.root is None else self.root / key

    def exists(self, key):
        return key in self.blobs

    def get_stream(self, key, chunk_size=65536):
        self.chunk_sizes.append(chunk_size)
        data = self.blobs[key]
        for number, offset in enumerate(range(0, len(data), 1000)):
            if self.break_after is not None and number >= self.break_after:
                raise ConnectionError("the object store dropped the connection")
            yield data[offset : offset + 1000]


def _media_container(monkeypatch, history, library, uploads=None):
    repository = SimpleNamespace(get_by_filename=lambda name, user_id: (uploads or {}).get((name, user_id)))
    _container(
        monkeypatch,
        file_service=SimpleNamespace(storage_driver=history),
        media_store=SimpleNamespace(storage_driver=library, upload_repo=repository),
    )


def test_media_file_path_is_the_absolute_local_path_of_a_key_or_none_on_object_storage(monkeypatch, tmp_path):
    _media_container(monkeypatch, _Driver(tmp_path / "history"), _Driver())

    assert core_bridge.media_file_path("history", "generations/d/g/1.mp4") == str((tmp_path / "history" / "generations/d/g/1.mp4").resolve())
    assert core_bridge.media_file_path("library", "uploads/a.mp4") is None


def test_local_media_file_uses_the_local_file_or_copies_the_bytes_into_the_folder(monkeypatch, tmp_path):
    root = tmp_path / "storage"
    (root / "generations").mkdir(parents=True)
    (root / "generations" / "1.mp4").write_bytes(b"video")
    _media_container(monkeypatch, _Driver(root), _Driver(blobs={"uploads/a.wav": b"sound"}))
    folder = tmp_path / "job"
    folder.mkdir()

    assert core_bridge.local_media_file("history", "generations/1.mp4", folder) == root / "generations" / "1.mp4"
    assert core_bridge.local_media_file("history", "generations/missing.mp4", folder) is None
    copied = core_bridge.local_media_file("library", "uploads/a.wav", folder)
    assert copied.parent == folder and copied.read_bytes() == b"sound"
    assert core_bridge.local_media_file("library", "uploads/gone.wav", folder) is None


def test_an_object_storage_source_is_streamed_into_the_folder_in_chunks_and_never_read_whole(monkeypatch, tmp_path):
    blob = bytes(range(256)) * 40
    library = _Driver(blobs={"uploads/big.mp4": blob})
    _media_container(monkeypatch, _Driver(), library)
    folder = tmp_path / "job"
    folder.mkdir()

    copied = core_bridge.local_media_file("library", "uploads/big.mp4", folder)

    assert copied == folder / f"{core_bridge.SOURCE_PREFIX}uploads_big.mp4" and copied.read_bytes() == blob
    assert library.chunk_sizes and library.chunk_sizes[0] >= 1 << 16


def test_a_stream_that_breaks_leaves_no_half_copy_in_the_folder(monkeypatch, tmp_path):
    library = _Driver(blobs={"uploads/big.mp4": b"x" * 5000}, break_after=2)
    _media_container(monkeypatch, _Driver(), library)
    folder = tmp_path / "job"
    folder.mkdir()

    with pytest.raises(ConnectionError):
        core_bridge.local_media_file("library", "uploads/big.mp4", folder)

    assert list(folder.iterdir()) == []


def test_upload_item_reads_the_library_item_of_an_uploads_key_of_the_user(monkeypatch):
    upload = SimpleNamespace(id="item-1", original_filename="cut.mp4", width=1920, height=1080)
    _media_container(monkeypatch, _Driver(), _Driver(), uploads={("0f0e.mp4", "user-1"): upload})

    assert core_bridge.upload_item("user-1", "uploads/0f0e.mp4") == {"item_id": "item-1", "filename": "cut.mp4", "width": 1920, "height": 1080}
    assert core_bridge.upload_item("user-2", "uploads/0f0e.mp4") is None


def test_storage_directory_is_the_applications_file_storage_directory_made_absolute(monkeypatch, tmp_path):
    class FakeSettings:
        def __init__(self, repository):
            self.repository = repository

        def get_file_storage_directory(self):
            return str(tmp_path / "storage")

    monkeypatch.setattr(core_bridge, "Settings", FakeSettings)
    monkeypatch.setattr(core_bridge, "SettingRepository", lambda: "repository")

    assert core_bridge.storage_directory() == (tmp_path / "storage").resolve()


async def test_extract_frame_and_save_user_media_go_to_the_core_as_the_user(monkeypatch, tmp_path):
    calls = []

    async def extract_frame(user, ref, at="last"):
        calls.append(("frame", user.id, ref, at))
        return {"value": "uploads/f.png", "media_type": "image", "original_filename": "f.png", "origin": None}

    async def save_user_media(user, path):
        calls.append(("save", user.id, path))
        return {"value": "uploads/v.mp4", "media_type": "video", "original_filename": "v.mp4", "origin": None}

    monkeypatch.setattr(core_bridge, "api_media", SimpleNamespace(extract_frame=extract_frame, save_user_media=save_user_media))
    user = SimpleNamespace(id="user-1")
    ref = {"kind": "history", "generation_id": "g", "file_id": "f"}

    frame = await core_bridge.extract_frame(user, ref, 2.5)
    saved = await core_bridge.save_user_media(user, str(tmp_path / "v.mp4"))

    assert frame["value"] == "uploads/f.png" and saved["value"] == "uploads/v.mp4"
    assert calls == [("frame", "user-1", ref, 2.5), ("save", "user-1", tmp_path / "v.mp4")]


def test_the_transcode_types_are_the_ones_the_core_exports():
    from src.plugin_api import media

    assert core_bridge.TranscodeSpec is media.TranscodeSpec
    assert core_bridge.VideoTranscodeError is media.VideoTranscodeError
    assert issubclass(core_bridge.FfmpegUnavailableError, core_bridge.VideoTranscodeError)
