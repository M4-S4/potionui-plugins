"""Starting a download for a user (PLAN.md §7.4, steps 1 to 4): checks, then the core queue.

`start_download(principal, request)` is what `POST /downloads` runs. It is two steps, which
the request routes also use on their own (`routes_requests.py`): `prepare_download` checks,
`queue_prepared` queues.
1. checks (`prepare_download`), against one view of the requester's grant (`purpose`: the
   download view for a direct download, the request view for a request; `Grant.params`),
   in this order: the source is allowed and enabled; the detail, filtered for the
   requester's NSFW context, still holds the version and the file (else 404: a user who may
   not see a model never downloads it); the PotionUI type (the request's, else the detail's
   `mb_type`) exists and is allowed; the file fits `max_file_gb`; a remote destination needs
   `allow_remote` (never for a request); the download URL passes
   `security.is_allowed_download_url`; a target group needs `assign_to == "group"` and must
   be one of the requester's groups (any group for an admin);
2. one row per file (`pending.key_for`): a file already on its way answers that row
   (`already_queued`, nothing queued twice); a finished row (`failed`, `enriched`) is replaced;
   a file whose SHA256 is already indexed is not downloaded again: its row starts at
   `indexed` and the watcher assigns and enriches it (`already_installed`);
3. otherwise the requester's plan quota is checked (`limits.check_quota`: 403
   `limit_exceeded`), the row is written (`queued`, with a fresh `limit_ref_id`), then the
   file is put on the core queue, and once it is there one event per quota kind is recorded
   for the requester (`limits.record`). A refusal from the core deletes the row.

A request is checked with `purpose="request"` when it is made (the messages then speak of
requesting), and approving it runs the same two steps for the requester, `on_behalf` of the
approver (`prepare_download(..., purpose="request", on_behalf=True)`): the messages speak of
the requester, and a model or version the requester's NSFW context hides is a 403
`not_visible_to_requester` rather than a 404. The core download is then created by the
approver (`created_by`), and the answer shows the row as the approver may see it.

Where the file lands: the type's folder, then `subdir`, then `filename`. Without a
`filename` in the request, the file keeps its own name, and the folders of a nested
source path (Hugging Face `unet/x.safetensors`) are appended to `subdir`; a `filename`
given in the request must be one plain name keeping the file's extension.

Who sees the model (`assign_to` of the row): `group:<id>` when a group was picked,
otherwise `user:<requester id>`, or `none` for an admin, who sees every model already.
"""

import asyncio
import logging
import posixpath
import sqlite3
from dataclasses import dataclass, replace
from typing import Annotated, Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, BeforeValidator, Field, ValidationError, field_validator

from src.plugin_api.models import MODEL_TYPES

from . import core_bridge, limits, nsfw, nsfw_filter, pending, security, sources
from .core_bridge import CoreBridgeError
from .pending import PendingRow
from .permissions import PURPOSES, Principal
from .routes_sources import MAX_MODEL_ID_LENGTH
from .schema import File, ModelDetail, NsfwContext, Version
from .sources import UnknownSource

logger = logging.getLogger("plugins.model-browser")

GIB = 1024 ** 3
#: Tags every download this plugin queues carries, plus `model-browser:<source>`.
DOWNLOAD_TAG = "model-browser"
MAX_ID_LENGTH = 200
#: Hugging Face file ids are repository paths.
MAX_FILE_ID_LENGTH = 1024
MAX_SUBDIR_LENGTH = 255
MAX_FILENAME_LENGTH = 255

#: The fields of a core download a non-admin receives: not where it lands on the
#: server's disk, nor its URL (the core hides the same from non-admins on models).
PUBLIC_DOWNLOAD_FIELDS = (
    "id",
    "status",
    "progress",
    "total_bytes",
    "downloaded_bytes",
    "speed_bytes_per_sec",
    "error_message",
    "filename",
    "retry_count",
    "created_at",
    "started_at",
    "completed_at",
)


class DownloadError(Exception):
    """A refused download, with the HTTP status and the error code the route answers with.

    `extra`: more fields for the error body (the quota refusal's kind, usage and limit).
    """

    def __init__(self, status: int, code: str, message: str, extra: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra: Dict[str, Any] = dict(extra or {})


def _forbidden(message: str) -> DownloadError:
    return DownloadError(403, "forbidden", message)


def _not_found(message: str) -> DownloadError:
    return DownloadError(404, "not_found", message)


def _invalid(message: str) -> DownloadError:
    return DownloadError(400, "invalid_request", message)


# The request ----------------------------------------------------------------------


def _text(value: Any) -> Any:
    """An id sent as a JSON number (CivitAI ids) becomes its text; other values go on to validation."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _optional_text(value: Any) -> Any:
    """`_text`, and an empty or blank string means "not given"."""
    value = _text(value)
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _bad_char(text: str) -> bool:
    return any(ord(char) < 0x20 or ord(char) == 0x7F or char == "\\" for char in text)


def path_segments(value: str) -> List[str]:
    """The folders of a relative path, refusing anything that could leave its parent.

    Raises ValueError for an absolute path, an empty, `.` or `..` segment, a backslash,
    a drive (`:`) or a control character.
    """
    if _bad_char(value) or ":" in value:
        raise ValueError("must not contain a backslash, a colon or a control character")
    if value.startswith("/"):
        raise ValueError("must be a relative path")
    segments = value.strip("/").split("/")
    for segment in segments:
        if segment.strip() in ("", ".", ".."):
            raise ValueError("must be a relative path with no empty, '.' or '..' segment")
    return segments


def plain_name(value: str) -> str:
    """A file name of one segment, as given; ValueError otherwise."""
    if "/" in value or _bad_char(value) or ":" in value:
        raise ValueError("must be a plain file name, without a folder, a colon or a control character")
    if value.strip() in ("", ".", ".."):
        raise ValueError("must be a file name")
    return value


class FileRef(BaseModel):
    """One file of one model at a source, and the PotionUI type to download it as: what a
    download and a request (`POST /requests`) both name."""

    source: str = Field(min_length=1, max_length=64)
    model_id: Annotated[str, BeforeValidator(_text)] = Field(min_length=1, max_length=MAX_MODEL_ID_LENGTH)
    version_id: Annotated[str, BeforeValidator(_text)] = Field(min_length=1, max_length=MAX_ID_LENGTH)
    file_id: Annotated[str, BeforeValidator(_text)] = Field(min_length=1, max_length=MAX_FILE_ID_LENGTH)
    #: A PotionUI model type; the detail's `mb_type` when left out.
    model_type: Annotated[Optional[str], BeforeValidator(_optional_text)] = None

    @field_validator("model_id")
    @classmethod
    def _model_id(cls, value: str) -> str:
        # The same rule as the detail routes (`routes_sources._model_id`).
        if value.startswith("/") or ".." in value or _bad_char(value):
            raise ValueError("is not a valid model id")
        return value

    @field_validator("version_id", "file_id")
    @classmethod
    def _id(cls, value: str) -> str:
        if _bad_char(value):
            raise ValueError("must not contain a backslash or a control character")
        return value

    @field_validator("model_type")
    @classmethod
    def _model_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in MODEL_TYPES:
            raise ValueError(f"unknown model type '{value[:64]}'")
        return value


class DownloadRequest(FileRef):
    """The body of `POST /downloads`."""

    #: Folder under the type's folder, relative.
    subdir: Annotated[Optional[str], BeforeValidator(_optional_text)] = Field(None, max_length=MAX_SUBDIR_LENGTH)
    #: The file's name on disk; the source's when left out.
    filename: Annotated[Optional[str], BeforeValidator(_optional_text)] = Field(None, max_length=MAX_FILENAME_LENGTH)
    #: A `native.remote` backend to download to instead of this server (needs `allow_remote`).
    destination_backend_id: Annotated[Optional[str], BeforeValidator(_optional_text)] = Field(
        None, max_length=MAX_ID_LENGTH
    )
    #: One of the requester's user groups to assign the model to (needs `assign_to == "group"`).
    assign_group_id: Annotated[Optional[str], BeforeValidator(_optional_text)] = Field(None, max_length=MAX_ID_LENGTH)

    @field_validator("subdir")
    @classmethod
    def _subdir(cls, value: Optional[str]) -> Optional[str]:
        return "/".join(path_segments(value.strip())) if value is not None else None

    @field_validator("filename")
    @classmethod
    def _filename(cls, value: Optional[str]) -> Optional[str]:
        return plain_name(value.strip()) if value is not None else None

    @field_validator("destination_backend_id", "assign_group_id")
    @classmethod
    def _plain_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and _bad_char(value):
            raise ValueError("must not contain a backslash or a control character")
        return value.strip() if value is not None else None


def describe_validation_error(error: ValidationError, what: str = "download") -> str:
    """A validation error on one line: `Invalid download: subdir: Value error, must be a relative path ...; ...`."""
    problems = []
    for item in error.errors(include_url=False):
        where = ".".join(str(part) for part in item["loc"])
        problems.append(f"{where}: {item['msg']}" if where else item["msg"])
    return f"Invalid {what}: " + "; ".join(problems)


# What the routes send back --------------------------------------------------------


def public_download(download: Optional[Mapping[str, Any]], *, admin: bool) -> Optional[Dict[str, Any]]:
    """A core download as this viewer may receive it: everything for an admin, `PUBLIC_DOWNLOAD_FIELDS` otherwise."""
    if download is None:
        return None
    if admin:
        return dict(download)
    return {name: download.get(name) for name in PUBLIC_DOWNLOAD_FIELDS}


def info_for_viewer(info: Mapping[str, Any], ctx: NsfwContext) -> Dict[str, Any]:
    """A pending row's `info` with its images filtered for the viewer's NSFW context.

    The row was written for its requester; another viewer (an admin, an `approve` holder)
    or the requester under a stricter policy since gets each image as `nsfw_filter`
    would hand it to them. A model the viewer may not see at all keeps its name and
    file, loses its images and description, and is marked `hidden`.
    """
    result = dict(info)
    model = info.get("model")
    if not isinstance(model, Mapping):
        return result
    try:
        detail = ModelDetail.model_validate(model)
    except ValidationError:
        result["model"] = None
        return result
    mode = nsfw_filter.display_mode(ctx)
    hidden = (detail.nsfw and mode == "hide") or (ctx.hide_poi and detail.poi)
    versions = []
    for version in detail.versions:
        kept = [] if hidden else [nsfw_filter.filter_image(image, ctx) for image in version.images]
        versions.append(version.model_copy(update={"images": [image for image in kept if image is not None]}))
    update: Dict[str, Any] = {"versions": versions}
    if hidden:
        update["description_html"] = None
        result["hidden"] = True
    result["model"] = detail.model_copy(update=update).model_dump(mode="json")
    return result


def row_for_viewer(row: PendingRow, ctx: NsfwContext) -> Dict[str, Any]:
    """`row.to_json()` as the routes send it: `info` filtered for the viewer (`info_for_viewer`),
    and without the model's `description_html` (up to 64 KB a row, for a list the page polls;
    the table keeps it for the provider)."""
    data = row.to_json()
    info = info_for_viewer(row.info, ctx)
    if isinstance(info.get("model"), dict):
        info["model"] = {**info["model"], "description_html": None}
    data["info"] = info
    return data


# The flow -------------------------------------------------------------------------


def pending_info(detail: ModelDetail, version: Version, file: File, mb_type: str) -> Dict[str, Any]:
    """The `info` of a pending row, the contract with the `model-browser` provider.

    `{"model": <ModelDetail as JSON, `versions` cut down to the chosen version and its
    `files` to the chosen file; the version's images kept with their nsfw flags>,
    "version_id", "file_id", "mb_type": <the PotionUI type downloaded as>}`. The detail is
    the one filtered for the requester: nothing they could not see is stored for them.
    """
    chosen = version.model_copy(update={"files": [file]})
    model = detail.model_copy(update={"versions": [chosen]})
    return {"model": model.model_dump(mode="json"), "version_id": version.id, "file_id": file.id, "mb_type": mb_type}


def destination(request: DownloadRequest, file: File) -> Tuple[Optional[str], str]:
    """`(subdir, filename)` for the core queue (see the module docstring)."""
    source_name = file.name.replace("\\", "/")
    folders, _, base_name = source_name.strip("/").rpartition("/")
    if request.filename is not None:
        filename, extra = request.filename, []
        wanted = posixpath.splitext(base_name)[1].lower()
        if wanted and posixpath.splitext(filename)[1].lower() != wanted:
            raise _invalid(f"The file name must keep the '{wanted}' extension of the file")
    else:
        try:
            filename = plain_name(base_name)
            extra = path_segments(folders) if folders else []
        except ValueError:
            raise _invalid("This file's name cannot be used as it is: choose a file name") from None
    subdir_parts = (request.subdir.split("/") if request.subdir else []) + extra
    subdir = "/".join(subdir_parts) or None
    if subdir is not None and len(subdir) > MAX_SUBDIR_LENGTH:
        raise _invalid("The folder is too long")
    return subdir, filename


async def _assign_target(
    principal: Principal, group_id: Optional[str], *, purpose: str = "download", on_behalf: bool = False
) -> str:
    """The row's `assign_to` for this requester and the group picked for them, if any, as the
    `assign_to` of the view of `purpose` allows.

    `on_behalf`: an approver picked the group, among the requester's.
    """
    user, grant = principal.user, principal.grant
    if group_id is None:
        return "none" if principal.is_admin else f"user:{user.id}"
    if principal.is_admin:
        groups = await asyncio.to_thread(core_bridge.list_groups)
        if group_id not in {group["id"] for group in groups}:
            raise _invalid(f"There is no user group with the id '{group_id}'")
        return f"group:{group_id}"
    noun = "request" if purpose == "request" else "download"
    if grant.params(purpose).assign_to != "group":
        if on_behalf:
            raise _forbidden(
                f"The requester's {noun}s are assigned to them: their permissions do not let you pick a group"
            )
        raise _forbidden(f"Your {noun}s are assigned to you: your permissions do not let you pick a group")
    groups = await asyncio.to_thread(core_bridge.user_groups, user.id)
    if group_id not in {group["id"] for group in groups}:
        if on_behalf:
            raise _forbidden(f"A {noun} can only be assigned to one of the requester's groups")
        raise _forbidden(f"You can only assign a {noun} to one of your own groups")
    return f"group:{group_id}"


def _answer(
    row: PendingRow,
    download: Optional[Mapping[str, Any]],
    ctx: NsfwContext,
    *,
    admin: bool,
    already_installed: bool = False,
    already_queued: bool = False,
) -> Dict[str, Any]:
    return {
        "pending": row_for_viewer(row, ctx),
        "download": public_download(download, admin=admin),
        "already_installed": already_installed,
        "already_queued": already_queued,
    }


async def _existing_download(row: PendingRow) -> Optional[Dict[str, Any]]:
    if not row.download_id:
        return None
    try:
        return await asyncio.to_thread(core_bridge.get_download, row.download_id)
    except Exception:
        logger.warning("[MODEL-BROWSER] Could not read download %s", row.download_id, exc_info=True)
        return None


#: The error code of a request the requester may no longer see (approval only).
NOT_VISIBLE_TO_REQUESTER = "not_visible_to_requester"


def _not_visible() -> DownloadError:
    return DownloadError(
        403, NOT_VISIBLE_TO_REQUESTER, "The requester may not see this model: their content settings hide it"
    )


@dataclass(frozen=True)
class Prepared:
    """A download that passed its checks (`prepare_download`), for `queue_prepared`."""

    #: Who the file is for: the requester.
    principal: Principal
    request: DownloadRequest
    #: The requester's NSFW context.
    ctx: NsfwContext
    #: The detail as the requester may see it, and the chosen version and file.
    detail: ModelDetail
    version: Version
    file: File
    model_type: str
    #: The pending row's `assign_to`.
    assign_to: str
    subdir: Optional[str]
    filename: str
    #: An approver acts on the requester's request.
    on_behalf: bool = False
    #: The view of the grant the file was checked against: "download" or "request".
    purpose: str = "download"


async def prepare_download(
    principal: Principal, request: DownloadRequest, *, purpose: str = "download", on_behalf: bool = False
) -> Prepared:
    """Step 1: check that the file may be downloaded for `principal` (see the module docstring).

    `purpose`: "download" checks the grant's download view (`POST /downloads`), "request" its
    request view (a request, made or approved); the messages say "downloading" or
    "requesting". `on_behalf`: an approver asks for it on `principal`'s request; the messages
    then speak of the requester, and a model or version their NSFW context hides is a 403
    `not_visible_to_requester`. Raises `DownloadError` for a refusal, and the sources'
    `SourceError` when the source cannot be read.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}")
    user, grant = principal.user, principal.grant
    params = grant.params(purpose)
    asking = purpose == "request"
    whose = "The requester's" if on_behalf else "Your"
    if not grant.allows_source(request.source, purpose):
        what = "requesting models from" if asking else "downloads from"
        raise _forbidden(f"{whose} permissions do not allow {what} '{request.source[:64]}'")
    try:
        source = sources.get_source(request.source)
    except UnknownSource:
        raise DownloadError(404, "unknown_source", f"Unknown source '{request.source[:64]}'") from None
    ctx = await asyncio.to_thread(nsfw.resolve_nsfw, user)
    raw = await source.detail(request.model_id, max_level=ctx.max_level)
    detail = nsfw_filter.filter_detail(raw, ctx)
    if detail is None:
        raise _not_visible() if on_behalf else _not_found("Model not found")
    version = next((version for version in detail.versions if version.id == request.version_id), None)
    if version is None:
        if on_behalf and any(hidden.id == request.version_id for hidden in raw.versions):
            raise _not_visible()
        raise _not_found("Version not found")
    file = next((file for file in version.files if file.id == request.file_id), None)
    if file is None:
        raise _not_found("File not found")
    model_type = request.model_type or detail.mb_type
    if not model_type:
        raise _invalid("Choose the model type to download this file as")
    if model_type not in MODEL_TYPES:
        raise _invalid(f"Unknown model type '{model_type}'")
    if not grant.allows_type(model_type, purpose):
        verb = "requesting" if asking else "downloading"
        raise _forbidden(f"{whose} permissions do not allow {verb} '{model_type}' models")
    max_gb = None if grant.unrestricted else params.max_file_gb
    if max_gb is not None and file.size_bytes is not None and file.size_bytes > max_gb * GIB:
        allowed = f"requesting files of at most {max_gb:g} GB" if asking else f"at most {max_gb:g} GB"
        raise _forbidden(f"This file is {file.size_bytes / GIB:.2f} GB: {whose.lower()} permissions allow {allowed}")
    if request.destination_backend_id and (asking or not params.allow_remote):
        if asking:
            raise _forbidden("A request cannot choose a remote destination: the file is downloaded to this server")
        raise _forbidden(f"{whose} permissions do not allow downloading to a remote backend")
    if not security.is_allowed_download_url(request.source, file.download_url):
        raise _forbidden("This file's download address is not one the plugin downloads from")
    assign_to = await _assign_target(principal, request.assign_group_id, purpose=purpose, on_behalf=on_behalf)
    subdir, filename = destination(request, file)
    return Prepared(
        principal=principal,
        request=request,
        ctx=ctx,
        detail=detail,
        version=version,
        file=file,
        model_type=model_type,
        assign_to=assign_to,
        subdir=subdir,
        filename=filename,
        on_behalf=on_behalf,
        purpose=purpose,
    )


def _check_quota(prepared: Prepared) -> None:
    """The requester's plan quota for one more file (`limits.check_quota`), as a `DownloadError`."""
    user = prepared.principal.user
    try:
        limits.check_quota(
            user.id, prepared.file.size_bytes, requester_name=user.username if prepared.on_behalf else None
        )
    except limits.QuotaExceeded as exc:
        raise DownloadError(403, "limit_exceeded", exc.message, extra=exc.payload()) from None


async def queue_prepared(
    prepared: Prepared,
    *,
    request_id: Optional[str] = None,
    created_by: Optional[str] = None,
    viewer_ctx: Optional[NsfwContext] = None,
    viewer_admin: Optional[bool] = None,
) -> Dict[str, Any]:
    """Steps 2 and 3: reuse the file's row, or check the quota and queue the file for the requester.

    `request_id`: the request the download comes from (kept on the row). `created_by`: who
    the core download is created by (the approver of a request; the requester by default).
    `viewer_ctx`, `viewer_admin`: who the answer is for (the approver; the requester by default).
    Returns what `start_download` returns.
    """
    user = prepared.principal.user
    detail, version, file = prepared.detail, prepared.version, prepared.file
    filename = prepared.filename
    ctx = viewer_ctx if viewer_ctx is not None else prepared.ctx
    admin = prepared.principal.is_admin if viewer_admin is None else viewer_admin

    # 2. One row per file.
    key = pending.key_for(file.sha256, file.download_url)
    existing = await asyncio.to_thread(pending.get, key)
    if existing is not None and not existing.finished:
        return _answer(existing, await _existing_download(existing), ctx, admin=admin, already_queued=True)
    if existing is not None:
        await asyncio.to_thread(pending.delete, key)  # failed or done: this download starts over

    row = PendingRow(
        sha256=key,
        source=detail.source,
        source_model_id=detail.id,
        source_version_id=version.id,
        file_name=filename,
        requested_by=user.id,
        assign_to=prepared.assign_to,
        request_id=request_id,
        info=pending_info(detail, version, file, prepared.model_type),
        status="queued",
    )

    if file.sha256:
        model = await asyncio.to_thread(core_bridge.find_model_by_sha256, file.sha256)
        if model is not None and model.get("is_available", True) is not False:
            inserted, raced = await _insert(replace(row, status="indexed", model_id=model["id"]))
            if raced:
                return _answer(inserted, await _existing_download(inserted), ctx, admin=admin, already_queued=True)
            logger.info("[MODEL-BROWSER] %s is already installed (model %s): assigning it only", filename, model["id"])
            return _answer(inserted, None, ctx, admin=admin, already_installed=True)

    # 3. Quota, then queue.
    await asyncio.to_thread(_check_quota, prepared)
    ref_id = limits.new_ref_id()
    inserted, raced = await _insert(replace(row, limit_ref_id=ref_id))
    if raced:
        return _answer(inserted, await _existing_download(inserted), ctx, admin=admin, already_queued=True)
    try:
        download = await core_bridge.queue_model_download(
            file.download_url,
            filename=filename,
            model_type=prepared.model_type,
            subdir=prepared.subdir,
            tags=[DOWNLOAD_TAG, f"{DOWNLOAD_TAG}:{detail.source}"],
            checksum_sha256=file.sha256 or None,
            provider_id=file.auth_provider_id,
            created_by=created_by or user.id,
            destination_backend_id=prepared.request.destination_backend_id,
        )
    except CoreBridgeError as exc:
        await asyncio.to_thread(pending.delete, key)
        logger.info("[MODEL-BROWSER] The core refused to queue %s (%s): %s", filename, exc.code, exc.message)
        raise DownloadError(409 if exc.code == "blocked" else 400, exc.code, exc.message) from None
    except Exception:
        await asyncio.to_thread(pending.delete, key)
        raise
    updated = await asyncio.to_thread(pending.update, key, download_id=download.get("id"))
    await asyncio.to_thread(limits.record, user.id, file.size_bytes, ref_id)
    logger.info(
        "[MODEL-BROWSER] Queued %s for %s (download %s, %s%s)",
        filename,
        user.username,
        download.get("id"),
        prepared.assign_to,
        f", approved by {created_by}" if created_by and created_by != user.id else "",
    )
    return _answer(updated or inserted, download, ctx, admin=admin)


async def start_download(
    principal: Principal, request: DownloadRequest, *, request_id: Optional[str] = None
) -> Dict[str, Any]:
    """Check, then queue (or reuse) the download of one file for `principal`
    (`prepare_download`, then `queue_prepared`).

    Returns `{"pending": <row, info filtered for the requester>, "download": <the core
    download (public fields for a non-admin), or None>, "already_installed": bool,
    "already_queued": bool}`. Raises `DownloadError` for a refusal (403 `limit_exceeded`
    with the quota's figures in `extra`), and the sources' `SourceError` when the source
    cannot be read.
    """
    return await queue_prepared(await prepare_download(principal, request), request_id=request_id)


async def _insert(row: PendingRow) -> Tuple[PendingRow, bool]:
    """`(row as stored, False)`, or `(the row another request stored first, True)` when the key was taken meanwhile."""
    try:
        return await asyncio.to_thread(pending.insert, row), False
    except sqlite3.IntegrityError:
        existing = await asyncio.to_thread(pending.get, row.sha256)
        if existing is None:
            raise
        return existing, True
