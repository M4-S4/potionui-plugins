import importlib
import importlib.util
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.features.downloads.models import Download, DownloadStatus
from src.features.models.locator import ModelFileUnavailable
from src.features.models.records import Model

PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "content" / "plugins" / "marketplace" / "model-browser"
PACKAGE = "model_browser"

_SHA = "ab" * 32
_URL = "https://civitai.com/api/download/models/135867"
_PATH = "/app/models/loras/add-detail-xl.safetensors"
_MODEL_KEYS = {"id", "sha256", "is_available", "created_at", "filename", "model_type"}


@pytest.fixture(autouse=True)
def plugin_modules_removed_afterwards():
    modules, path = set(sys.modules), list(sys.path)
    try:
        yield
    finally:
        for name in set(sys.modules) - modules:
            if name.split(".")[0] == PACKAGE:
                del sys.modules[name]
        sys.path[:] = path


def _load(name):
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{PACKAGE}.{name}")


@pytest.fixture
def core_bridge():
    return _load("backend.core_bridge")


def _stand_in(real, answer=None):
    signature = inspect.signature(real)
    calls = []

    def respond(args, kwargs):
        arguments = dict(signature.bind(*args, **kwargs).arguments)
        calls.append(arguments)
        return answer(**arguments) if callable(answer) else answer

    if inspect.iscoroutinefunction(real):
        async def stand_in(*args, **kwargs):
            return respond(args, kwargs)

    else:
        def stand_in(*args, **kwargs):
            return respond(args, kwargs)

    stand_in.calls = calls
    return stand_in


def _replace(monkeypatch, module, name, answer=None):
    stand_in = _stand_in(getattr(module, name), answer)
    monkeypatch.setattr(module, name, stand_in)
    return stand_in


def _raise(exception):
    def answer(**arguments):
        raise exception

    return answer


def _download(**fields):
    values = dict(
        id="dl-1",
        url=_URL,
        destination_path=_PATH,
        filename="add-detail-xl.safetensors",
        status=DownloadStatus.PENDING,
        checksum_sha256=_SHA,
        provider_id="civitai",
        tags=["model-browser", "model-browser:civitai"],
        created_by="user-1",
    )
    values.update(fields)
    return Download(**values).to_dict()


async def test_queue_model_download_passes_every_argument_and_returns_the_download(monkeypatch, core_bridge):
    queue = _replace(monkeypatch, core_bridge.api_downloads, "queue_model_download", _download())

    download = await core_bridge.queue_model_download(
        _URL,
        filename="add-detail-xl.safetensors",
        model_type="lora",
        subdir="sdxl",
        tags=("model-browser", "model-browser:civitai"),
        checksum_sha256=_SHA,
        provider_id="civitai",
        created_by="user-1",
        destination_backend_id="worker-1",
    )

    assert queue.calls == [
        {
            "url": _URL,
            "filename": "add-detail-xl.safetensors",
            "model_type": "lora",
            "subdir": "sdxl",
            "tags": ["model-browser", "model-browser:civitai"],
            "checksum_sha256": _SHA,
            "provider_id": "civitai",
            "created_by": "user-1",
            "destination_backend_id": "worker-1",
        }
    ]
    assert download == _download()


def test_get_download_is_the_exports_answer_and_asks_nothing_without_an_id(monkeypatch, core_bridge):
    downloads = {"dl-1": _download(status=DownloadStatus.COMPLETED)}
    get = _replace(monkeypatch, core_bridge.api_downloads, "get_download", lambda download_id: downloads.get(download_id))

    assert core_bridge.get_download("dl-1")["status"] == "completed"
    assert core_bridge.get_download("dl-404") is None
    assert core_bridge.get_download(None) is None
    assert core_bridge.get_download("") is None
    assert get.calls == [{"download_id": "dl-1"}, {"download_id": "dl-404"}]


def _admin_payload(**fields):
    values = dict(
        id="model-1",
        filename="add-detail-xl.safetensors",
        file_size=228_000_000,
        sha256=_SHA,
        model_type="lora",
        created_at=datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc),
        description="Adds detail.",
        prompting_guidance="Keep it under 0.8",
        model_metadata={"strength": 0.8},
        location={"root_id": "root-1", "rel_path": "loras/add-detail-xl.safetensors"},
        copies=2,
    )
    values.update(fields)
    return Model(**values).to_dict(include_providers=False, admin=True)


def _assert_trimmed(found, payload):
    assert set(found) == _MODEL_KEYS
    assert found == {key: payload[key] for key in _MODEL_KEYS}
    assert {"location", "copies", "file_size", "prompting_guidance", "model_metadata"} <= set(payload)
    assert found["created_at"] == "2026-10-11T10:00:00+00:00" and found["sha256"] == _SHA


def test_find_model_by_sha256_asks_for_the_admin_payload_and_hands_on_only_the_model_keys(monkeypatch, core_bridge):
    payload = _admin_payload()
    lookup = _replace(
        monkeypatch,
        core_bridge.api_models,
        "model_for_sha256",
        lambda sha256, admin=False: payload if sha256.strip().lower() == _SHA else None,
    )

    found = core_bridge.find_model_by_sha256(" " + _SHA.upper())

    _assert_trimmed(found, payload)
    assert lookup.calls == [{"sha256": " " + _SHA.upper(), "admin": True}]
    assert core_bridge.find_model_by_sha256("cd" * 32) is None
    assert core_bridge.find_model_by_sha256("") is None
    assert len(lookup.calls) == 2


def test_find_model_by_path_asks_for_the_admin_payload_and_hands_on_only_the_model_keys(monkeypatch, core_bridge):
    payload = _admin_payload(is_available=False)
    lookup = _replace(
        monkeypatch, core_bridge.api_models, "model_for_path", lambda path, admin=False: payload if path == _PATH else None
    )

    found = core_bridge.find_model_by_path(_PATH)

    _assert_trimmed(found, payload)
    assert found["is_available"] is False
    assert lookup.calls == [{"path": _PATH, "admin": True}]
    assert core_bridge.find_model_by_path("/app/models/loras/other.safetensors") is None
    assert core_bridge.find_model_by_path("") is None
    assert len(lookup.calls) == 2


def test_find_model_by_id_reads_the_model_at_its_file(monkeypatch, core_bridge):
    payload = _admin_payload()
    file = Path(_PATH)
    resolve = _replace(monkeypatch, core_bridge.api_models, "resolve_model_file", lambda model_id: file)
    lookup = _replace(
        monkeypatch, core_bridge.api_models, "model_for_path", lambda path, admin=False: payload if path == str(file) else None
    )

    found = core_bridge.find_model_by_id("model-1")

    _assert_trimmed(found, payload)
    assert resolve.calls == [{"model_id": "model-1"}]
    assert lookup.calls == [{"path": str(file), "admin": True}]


@pytest.mark.parametrize(
    "reason", ["model 'model-1' has no known location", "is on 'NAS' (offline)"], ids=["unknown-model", "no-file"]
)
def test_find_model_by_id_is_none_for_a_model_without_a_present_file(monkeypatch, core_bridge, reason):
    _replace(monkeypatch, core_bridge.api_models, "resolve_model_file", _raise(ModelFileUnavailable(reason)))
    lookup = _replace(monkeypatch, core_bridge.api_models, "model_for_path", _admin_payload())

    assert core_bridge.find_model_by_id("model-1") is None
    assert core_bridge.find_model_by_id("") is None
    assert lookup.calls == []
