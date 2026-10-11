"""Test doubles for the download flow: normalised details, principals, a fake source, and
`FakeCore`, the core as `backend.core_bridge` shows it (download queue, model index,
assignment, provider fetch, attributes, notifications, group members, plan limits), plus the
users `src.plugin_api.get_user` / `list_user_ids` know and the `LimitEvents` ledger,
installed with `monkeypatch`.
"""

import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend import core_bridge, limits, permissions, sources
from backend.permissions import ADMIN_GRANT, Grant, Params, Principal
from backend.schema import File, Image, License, ModelDetail, Version
from backend.sources import UnknownSource
from src.plugin_api import AccountType, User

SHA = "a" * 64
OTHER_SHA = "b" * 64
URL = "https://civitai.com/api/download/models/135867"
FP16_URL = "https://civitai.com/api/download/models/135867?type=Model&format=SafeTensor&fp=fp16"
HF_URL = "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/transformer/flux1-dev.safetensors"
GIB = 1024 ** 3
SAFE_IMAGE = "https://image.civitai.com/safe.jpeg"
NSFW_IMAGE = "https://image.civitai.com/nsfw.jpeg"

#: The request view of `USER_GRANT`: the same two sources, every type, no size limit.
REQUEST_PARAMS = Params(sources=frozenset({"civitai", "huggingface"}))

USER_GRANT = Grant(
    capabilities=frozenset({"browse", "request", "download"}),
    sources=frozenset({"civitai", "huggingface"}),
    model_types=frozenset(),
    max_file_gb=None,
    assign_to="user",
    allow_remote=False,
    unrestricted=False,
    request_params=REQUEST_PARAMS,
)


def requesting(**params: Any) -> Params:
    """`REQUEST_PARAMS` with some values changed, for `principal(request_params=...)`."""
    return replace(REQUEST_PARAMS, **params)


def user(user_id: str = "user-1", *, admin: bool = False) -> User:
    return User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@test.com",
        password_hash="hash",
        account_type=AccountType.ADMIN if admin else AccountType.USER,
    )


def principal(user_id: str = "user-1", **grant: Any) -> Principal:
    """A non-admin with `download` and `request` on CivitAI and Hugging Face; `grant` overrides
    `USER_GRANT` fields (`request_params=requesting(...)` for the request view)."""
    return Principal(user=user(user_id), grant=replace(USER_GRANT, **grant))


def admin(user_id: str = "admin-1") -> Principal:
    return Principal(user=user(user_id, admin=True), grant=ADMIN_GRANT)


def civitai_detail(*, nsfw: bool = False, version_nsfw: bool = False, poi: bool = False) -> ModelDetail:
    """A CivitAI LoRA with one version, a safe and an NSFW preview, and two files."""
    return ModelDetail(
        source="civitai",
        id="122359",
        name="Detail Tweaker XL",
        type="LORA",
        mb_type="lora",
        creator="someone",
        description_html="<p>Adds detail.</p>",
        license=License(summary="CreativeML Open RAIL++-M; no selling"),
        source_url="https://civitai.com/models/122359",
        nsfw=nsfw,
        poi=poi,
        versions=[
            Version(
                id="135867",
                name="v1.0",
                base_model="SDXL 1.0",
                trigger_words=["detailed"],
                nsfw=version_nsfw,
                images=[
                    Image(url=SAFE_IMAGE, nsfw=False, nsfw_level=1, id="1"),
                    Image(url=NSFW_IMAGE, blurhash="LKO2?U%2Tw=w", nsfw=True, nsfw_level=8, id="2"),
                ],
                files=[
                    File(
                        id="1001",
                        name="add-detail-xl.safetensors",
                        size_bytes=228_000_000,
                        sha256=SHA,
                        format="SafeTensor",
                        primary=True,
                        download_url=URL,
                        auth_provider_id="civitai",
                    ),
                    File(
                        id="1002",
                        name="add-detail-xl-fp16.safetensors",
                        size_bytes=3 * GIB,
                        sha256=OTHER_SHA,
                        download_url=FP16_URL,
                        auth_provider_id="civitai",
                    ),
                ],
            )
        ],
    )


def hf_detail() -> ModelDetail:
    """A gated Hugging Face repo read anonymously: nested file paths, no hashes."""
    return ModelDetail(
        source="huggingface",
        id="black-forest-labs/FLUX.1-dev",
        name="FLUX.1-dev",
        type="text-to-image",
        mb_type="diffusion_model",
        source_url="https://huggingface.co/black-forest-labs/FLUX.1-dev",
        gated=True,
        versions=[
            Version(
                id="main",
                name="main",
                base_model="flux",
                files=[
                    File(
                        id="transformer/flux1-dev.safetensors",
                        name="transformer/flux1-dev.safetensors",
                        size_bytes=23 * GIB,
                        download_url=HF_URL,
                        auth_provider_id="huggingface",
                    ),
                    File(
                        id="ae.safetensors",
                        name="ae.safetensors",
                        size_bytes=335_000_000,
                        download_url="https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors",
                        auth_provider_id="huggingface",
                    ),
                ],
            )
        ],
    )


def body(**overrides: Any) -> Dict[str, Any]:
    """A `POST /downloads` body for the primary file of `civitai_detail()`."""
    values: Dict[str, Any] = {"source": "civitai", "model_id": "122359", "version_id": "135867", "file_id": "1001"}
    values.update(overrides)
    return values


class FakeSource:
    def __init__(self, source_id: str, detail: ModelDetail) -> None:
        self.id = source_id
        self.label = source_id
        self.detail_value = detail
        self.error: Optional[BaseException] = None
        self.calls: List[Tuple[str, Optional[int]]] = []

    async def detail(self, model_id: str, *, max_level: Optional[int] = None) -> ModelDetail:
        self.calls.append((model_id, max_level))
        if self.error is not None:
            raise self.error
        return self.detail_value


def install_sources(monkeypatch, *fakes: FakeSource) -> Dict[str, FakeSource]:
    """`sources.get_source` answering these fakes; any other id is unknown."""
    by_id = {fake.id: fake for fake in fakes}

    def get_source(source_id: str):
        if source_id not in by_id:
            raise UnknownSource(source_id)
        return by_id[source_id]

    monkeypatch.setattr(sources, "get_source", get_source)
    return by_id


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def model(model_id: str = "model-1", sha256: Optional[str] = SHA, *, created: str = "later", **fields: Any) -> Dict[str, Any]:
    """An indexed model as `core_bridge.find_model_by_*` returns it. `created`: "later" (after any
    row written now), "long_ago", or an ISO timestamp."""
    if created == "later":
        created = iso(datetime.now(timezone.utc) + timedelta(minutes=5))
    elif created == "long_ago":
        created = "2020-01-01T00:00:00+00:00"
    values = {
        "id": model_id,
        "sha256": sha256,
        "filename": "add-detail-xl.safetensors",
        "model_type": "lora",
        "model_metadata": {},
        "created_at": created,
        "is_available": True,
    }
    values.update(fields)
    return values


def unlimited(kind: str) -> Dict[str, Any]:
    """`core_bridge.limit_status` for a user without a limit of this kind."""
    return {"kind": kind, "limit": None, "used": None, "exempt": False, "resets_at": None, "contact_line": ""}


def limited(kind: str, limit: float, used: float, **fields: Any) -> Dict[str, Any]:
    """`core_bridge.limit_status` for a user with this limit and usage, resetting on Nov 1."""
    values = {
        "kind": kind,
        "limit": limit,
        "used": used,
        "exempt": False,
        "resets_at": "2026-11-01T00:00:00+00:00",
        "contact_line": "Ask your admin for more.",
    }
    values.update(fields)
    return values


class FakeCore:
    """What `backend.core_bridge` would get from PotionUI, in memory. `install()` puts it in place,
    with the users `permissions` looks up and the `LimitEvents` ledger `limits` writes to."""

    PATCHED = (
        "queue_model_download",
        "get_download",
        "find_model_by_sha256",
        "find_model_by_path",
        "visible_model_ids",
        "user_groups",
        "list_groups",
        "group_member_ids",
        "assign_to_user",
        "assign_to_group",
        "run_provider_fetch",
        "write_attributes",
        "notify",
        "limit_status",
    )

    def __init__(self) -> None:
        self.calls: List[Tuple[Any, ...]] = []
        self.queued: List[Dict[str, Any]] = []
        self.downloads: Dict[str, Dict[str, Any]] = {}
        self.models_by_sha: Dict[str, Dict[str, Any]] = {}
        self.models_by_path: Dict[str, Dict[str, Any]] = {}
        self.visible: Dict[str, List[str]] = {}
        self.memberships: Dict[str, List[str]] = {}
        self.group_ids: List[str] = ["all_admins", "all_users", "artists", "testers"]
        self.queue_error: Optional[BaseException] = None
        self.download_error: Optional[BaseException] = None
        self.assign_user_error: Optional[BaseException] = None
        self.assign_group_error: Optional[BaseException] = None
        self.fetch_results: Dict[str, Dict[str, Any]] = {}
        self.fetch_errors: Dict[str, BaseException] = {}
        self.attributes_error: Optional[BaseException] = None
        self.notifications: List[Dict[str, Any]] = []
        #: Users by id, for `get_user` and `list_user_ids`.
        self.users: Dict[str, User] = {}
        #: The acting admin's id (or None) of each `assign_to_group` call, in order.
        self.group_admins: List[Optional[str]] = []
        #: `(user_id, kind)` -> what `limit_status` answers; unlimited otherwise.
        self.limits: Dict[Tuple[str, str], Dict[str, Any]] = {}
        #: `LimitEvents.record` calls, as `(user_id, kind, units, ref_id)`, and `refund` ref ids.
        self.limit_events: List[Tuple[str, str, float, Optional[str]]] = []
        self.refunds: List[str] = []
        self._downloads_made = 0

    def install(self, monkeypatch) -> "FakeCore":
        for name in self.PATCHED:
            monkeypatch.setattr(core_bridge, name, getattr(self, name))
        monkeypatch.setattr(permissions, "get_user", self.get_user)
        monkeypatch.setattr(permissions, "list_user_ids", self.list_user_ids)
        monkeypatch.setattr(
            limits,
            "LimitEvents",
            SimpleNamespace(record=self.record_limit_event, refund=self.refund_limit_events),
        )
        return self

    def add_user(self, user_id: str, *, admin: bool = False, groups: Sequence[str] = ()) -> User:
        """A user `get_user` knows, member of `groups` (for `user_groups` and `group_member_ids`)."""
        account = user(user_id, admin=admin)
        self.users[user_id] = account
        if groups:
            self.memberships[user_id] = list(groups)
        return account

    def names(self) -> List[str]:
        return [call[0] for call in self.calls]

    def calls_to(self, name: str) -> List[Tuple[Any, ...]]:
        return [call[1:] for call in self.calls if call[0] == name]

    # Download queue

    async def queue_model_download(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(("queue_model_download", url))
        self.queued.append({"url": url, **kwargs})
        if self.queue_error is not None:
            raise self.queue_error
        self._downloads_made += 1
        download_id = f"dl-{self._downloads_made}"
        self.downloads[download_id] = {
            "id": download_id,
            "type": "model",
            "url": url,
            "destination_path": f"/app/models/{kwargs.get('model_type')}/{kwargs.get('filename')}",
            "filename": kwargs.get("filename"),
            "status": "pending",
            "progress": 0.0,
            "total_bytes": None,
            "downloaded_bytes": 0,
            "speed_bytes_per_sec": None,
            "error_message": None,
            "provider_id": kwargs.get("provider_id"),
            "tags": list(kwargs.get("tags") or []),
            "checksum_sha256": kwargs.get("checksum_sha256"),
            "retry_count": 0,
            "destination_backend_id": kwargs.get("destination_backend_id"),
            "created_at": "2026-10-11T10:00:00+00:00",
            "started_at": None,
            "completed_at": None,
            "created_by": kwargs.get("created_by"),
        }
        return copy.deepcopy(self.downloads[download_id])

    def add_download(self, download_id: str, status: str = "pending", **fields: Any) -> Dict[str, Any]:
        download = {
            "id": download_id,
            "status": status,
            "destination_path": f"/app/models/loras/{download_id}.safetensors",
            "error_message": None,
            "destination_backend_id": None,
        }
        download.update(fields)
        self.downloads[download_id] = download
        return download

    def get_download(self, download_id: Optional[str]) -> Optional[Dict[str, Any]]:
        self.calls.append(("get_download", download_id))
        if self.download_error is not None:
            raise self.download_error
        download = self.downloads.get(download_id)
        return copy.deepcopy(download) if download is not None else None

    # Model index

    def find_model_by_sha256(self, sha256: str) -> Optional[Dict[str, Any]]:
        self.calls.append(("find_model_by_sha256", sha256))
        found = self.models_by_sha.get(sha256.lower())
        return dict(found) if found is not None else None

    def find_model_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        self.calls.append(("find_model_by_path", path))
        found = self.models_by_path.get(path)
        return dict(found) if found is not None else None

    def visible_model_ids(self, user_id: str) -> List[str]:
        self.calls.append(("visible_model_ids", user_id))
        return list(self.visible.get(user_id, []))

    # Groups and assignment

    def _group(self, group_id: str) -> Dict[str, Any]:
        return {"id": group_id, "name": group_id.title(), "is_system": group_id.startswith("all_"), "content_policy": None}

    def user_groups(self, user_id: str) -> List[Dict[str, Any]]:
        self.calls.append(("user_groups", user_id))
        return [self._group(group_id) for group_id in self.memberships.get(user_id, [])]

    def list_groups(self) -> List[Dict[str, Any]]:
        self.calls.append(("list_groups",))
        return [self._group(group_id) for group_id in self.group_ids]

    def group_member_ids(self, group_id: str) -> List[str]:
        self.calls.append(("group_member_ids", group_id))
        return [user_id for user_id, groups in self.memberships.items() if group_id in groups]

    def assign_to_user(self, model_id: str, user_id: str) -> bool:
        self.calls.append(("assign_to_user", model_id, user_id))
        if self.assign_user_error is not None:
            raise self.assign_user_error
        return True

    def assign_to_group(self, group_id: str, model_ids: Sequence[str], acting_admin: Any = None) -> List[str]:
        self.calls.append(("assign_to_group", group_id, list(model_ids)))
        self.group_admins.append(getattr(acting_admin, "id", None))
        if self.assign_group_error is not None:
            raise self.assign_group_error
        return list(model_ids)

    # Users

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def list_user_ids(self) -> List[str]:
        return list(self.users)

    # Plan limits

    def limit_status(self, user_id: str, kind: str) -> Dict[str, Any]:
        self.calls.append(("limit_status", user_id, kind))
        return dict(self.limits.get((user_id, kind), unlimited(kind)))

    def record_limit_event(self, user_id: str, kind: str, units: float = 1, ref_id: Optional[str] = None) -> str:
        self.limit_events.append((user_id, kind, units, ref_id))
        return f"event-{len(self.limit_events)}"

    def refund_limit_events(self, ref_id: str) -> int:
        self.refunds.append(ref_id)
        return sum(1 for event in self.limit_events if event[3] == ref_id)

    # Enrichment

    async def run_provider_fetch(self, provider: str, model_ids: Sequence[str]) -> Dict[str, Any]:
        self.calls.append(("run_provider_fetch", provider, list(model_ids)))
        if provider in self.fetch_errors:
            raise self.fetch_errors[provider]
        return dict(self.fetch_results.get(provider, {"successful": len(model_ids), "failed": 0}))

    def write_attributes(self, model_id: str, values: Dict[str, Any]) -> None:
        self.calls.append(("write_attributes", model_id, dict(values)))
        if self.attributes_error is not None:
            raise self.attributes_error

    def notify(self, **kwargs: Any) -> None:
        self.calls.append(("notify", kwargs.get("notification_type")))
        self.notifications.append(kwargs)
