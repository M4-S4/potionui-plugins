"""Normalised shapes every source returns (PLAN.md §7.3), and the per-user NSFW context (§5).

Every source (`backend/sources/*`) turns its raw API payloads into these models; the
routes, the NSFW filter and the page only ever see these. Raw payloads live in the
cache, these objects are rebuilt per request so that per-user filtering never leaks
between users.

NSFW flags are set at normalisation time from the admin's `nsfw_max_level` setting
(a model-wide rule), then applied per user by `backend/nsfw_filter.py` from the
`NsfwContext` that `backend/nsfw.py` resolves (ceiling + display mode).
"""

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceId = Literal["civitai", "huggingface", "openmodeldb", "civarchive"]
NsfwCeiling = Literal["allowed", "blur", "blocked"]
NsfwMode = Literal["show", "blur", "hide"]


class NsfwContext(BaseModel):
    """What one user may see: the effective ceiling and their bounded display mode (PLAN.md §5.1)."""

    model_config = ConfigDict(frozen=True)

    ceiling: NsfwCeiling
    mode: NsfwMode
    allowed_modes: Tuple[NsfwMode, ...]
    #: Highest CivitAI `nsfwLevel` still treated as safe (PG=1, PG13=2, R=4, X=8).
    max_level: int = 2
    hide_poi: bool = False

    @property
    def blocked(self) -> bool:
        return self.ceiling == "blocked"


class Image(BaseModel):
    """A preview. `url` is None for an NSFW image sent to a user in blur or blocked mode."""

    url: Optional[str] = None
    blurhash: Optional[str] = None
    nsfw: bool = False
    nsfw_level: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    kind: Literal["image", "video"] = "image"
    poi: bool = False
    #: The source's id for the image when it has one (CivitAI image id): lets the page match
    #: the urls `nsfw-media` returns to the blurred images of a detail.
    id: Optional[str] = None


class File(BaseModel):
    id: str
    name: str
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    #: Container format as the source names it: SafeTensor, PickleTensor, GGUF, Diffusers ...
    format: Optional[str] = None
    #: fp16, fp8, bf16 ... when known.
    precision: Optional[str] = None
    #: The source's own file type: Model, VAE, Text Encoder, Training Data ...
    file_type: Optional[str] = None
    primary: bool = False
    download_url: str
    #: Marketplace provider that authenticates the download: "civitai", "huggingface" or None.
    auth_provider_id: Optional[str] = None


class Version(BaseModel):
    id: str
    name: str
    base_model: Optional[str] = None
    trigger_words: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    early_access: bool = False
    nsfw: bool = False
    images: List[Image] = Field(default_factory=list)
    files: List[File] = Field(default_factory=list)
    #: The source answered this version without its files and images: load
    #: `<model id>:<version id>` to get them (CivArchive). A partial version never carries any.
    partial: bool = False

    @model_validator(mode="after")
    def _partial_has_no_files_or_images(self) -> "Version":
        if self.partial and (self.files or self.images):
            raise ValueError("a partial version carries no files or images")
        return self


class License(BaseModel):
    """Licence as the source states it. CivitAI has no text, only the four flags (PLAN.md §8.1)."""

    summary: str
    commercial_use: Optional[List[str]] = None
    no_credit: Optional[bool] = None
    derivatives: Optional[bool] = None
    different_license: Optional[bool] = None
    url: Optional[str] = None


class Stats(BaseModel):
    downloads: Optional[int] = None
    likes: Optional[int] = None
    rating: Optional[float] = None


class SearchItem(BaseModel):
    source: SourceId
    id: str
    name: str
    #: The source's own type (LORA, Checkpoint, ...).
    type: str
    #: Proposed PotionUI model type (`backend/type_mapping.py`); None when not downloadable as a model.
    mb_type: Optional[str] = None
    base_model: Optional[str] = None
    base_models: List[str] = Field(default_factory=list)
    creator: Optional[str] = None
    nsfw: bool = False
    poi: bool = False
    early_access: bool = False
    #: Downloads need the source's credentials (Hugging Face gated repos): the page warns before downloading.
    gated: bool = False
    thumbnail: Optional[Image] = None
    stats: Stats = Field(default_factory=Stats)
    tags: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None
    #: Web page of the model on the source (`.red` for an NSFW CivitAI model).
    source_url: str
    #: Lower-case SHA256 of the primary file of the listed version, when the source gives it in
    #: list answers (CivitAI does, Hugging Face does not).
    primary_sha256: Optional[str] = None
    #: Whether that file is installed and visible to the caller, set per request by
    #: `GET /{source}/search` (`backend/installed.py`) on the items that have a `primary_sha256`;
    #: None when unknown (no hash, or the core could not answer).
    installed: Optional[bool] = None


class SearchPage(BaseModel):
    source: SourceId
    items: List[SearchItem]
    next_cursor: Optional[str] = None


class ModelDetail(BaseModel):
    source: SourceId
    id: str
    name: str
    type: str
    mb_type: Optional[str] = None
    creator: Optional[str] = None
    #: Sanitised HTML (`backend/security.py`), whatever the source sent.
    description_html: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    license: Optional[License] = None
    source_url: str
    nsfw: bool = False
    poi: bool = False
    gated: bool = False
    stats: Stats = Field(default_factory=Stats)
    versions: List[Version] = Field(default_factory=list)


class FilterOption(BaseModel):
    value: str
    label: str


class SourceInfo(BaseModel):
    """What `GET /sources` tells the page about one source and its filters."""

    id: SourceId
    label: str
    enabled: bool = True
    types: List[FilterOption] = Field(default_factory=list)
    base_models: List[FilterOption] = Field(default_factory=list)
    sorts: List[FilterOption] = Field(default_factory=list)
    periods: List[FilterOption] = Field(default_factory=list)
    #: One line for the search box, e.g. "#tag, @user, $#id1,id2 or a pasted model URL".
    search_help: Optional[str] = None
    #: Heading of the `types` filter in the page's filter popover ("Architecture" for OpenModelDB).
    types_label: str = "Types"
    #: Heading of the `base_models` filter ("Scale" for OpenModelDB).
    base_models_label: str = "Base model"
    #: What the `base_model` of an item or a version holds, the label of that line in the
    #: detail ("Architecture" for OpenModelDB, whose `base_model` reads "ESRGAN 4x").
    base_model_label: str = "Base model"
    #: A warning the page shows under the search help (CivArchive: an unofficial index); None for none.
    notice: Optional[str] = None
