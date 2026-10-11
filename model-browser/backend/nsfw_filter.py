"""Per-user NSFW filtering of normalised results (PLAN.md §5.2).

The sources already marked what is NSFW when they normalised a payload, from the
admin's `nsfw_max_level` (a rule for every user):
- an image is NSFW when its level is above `max_level`;
- a model or version is NSFW when the source flags it, or when none of its images is at
  or below `max_level`;
- an item's thumbnail is its first safe image (an NSFW image only when there is no other).

This module applies one user's `NsfwContext` to those objects, on every request, so the
raw cache is shared by every user without leaks. The mode applied is `ctx.mode`, never
looser than the ceiling (`hide` under `blocked`, at most `blur` under `blur`):
- `hide`: NSFW items are dropped, NSFW versions and images are dropped from what remains;
- `blur`: everything stays, but no NSFW image keeps its `url` (blurhash, sizes and level
  stay), thumbnails included; `nsfw_media` hands the urls out on demand;
- `show`: untouched.
In every mode, `ctx.hide_poi` drops the models (and images) that depict real people.

Pure functions: inputs are never modified, filtered copies are returned.
"""

from typing import List, Optional

from .schema import Image, ModelDetail, NsfwContext, NsfwMode, SearchItem, SearchPage, Version


class NsfwForbidden(Exception):
    """The user's ceiling is `blocked`: NSFW media is never sent to them."""


def display_mode(ctx: NsfwContext) -> NsfwMode:
    """The mode actually applied: `ctx.mode`, pulled down to what the ceiling allows."""
    if ctx.ceiling == "blocked":
        return "hide"
    if ctx.ceiling == "blur" and ctx.mode == "show":
        return "blur"
    if ctx.mode in ("show", "blur", "hide"):
        return ctx.mode
    return "hide"


def filter_image(image: Image, ctx: NsfwContext) -> Optional[Image]:
    """The image as this user may receive it: unchanged, without its url (blur), or None (dropped)."""
    if ctx.hide_poi and image.poi:
        return None
    if not image.nsfw:
        return image
    mode = display_mode(ctx)
    if mode == "hide":
        return None
    if mode == "blur":
        return image if image.url is None else image.model_copy(update={"url": None})
    return image


def _filter_images(images: List[Image], ctx: NsfwContext) -> List[Image]:
    return [kept for kept in (filter_image(image, ctx) for image in images) if kept is not None]


def filter_item(item: SearchItem, ctx: NsfwContext) -> Optional[SearchItem]:
    """One search result as this user may receive it, or None when it must not be listed."""
    if ctx.hide_poi and item.poi:
        return None
    if item.nsfw and display_mode(ctx) == "hide":
        return None
    if item.thumbnail is None:
        return item
    thumbnail = filter_image(item.thumbnail, ctx)
    if thumbnail is item.thumbnail:
        return item
    return item.model_copy(update={"thumbnail": thumbnail})


def filter_page(page: SearchPage, ctx: NsfwContext) -> SearchPage:
    """The page with the items this user may see, each filtered; the cursor is kept."""
    items = [kept for kept in (filter_item(item, ctx) for item in page.items) if kept is not None]
    return page.model_copy(update={"items": items})


def filter_version(version: Version, ctx: NsfwContext) -> Optional[Version]:
    """A version as this user may receive it, or None (an NSFW version in `hide`)."""
    if version.nsfw and display_mode(ctx) == "hide":
        return None
    return version.model_copy(update={"images": _filter_images(version.images, ctx)})


def filter_detail(detail: ModelDetail, ctx: NsfwContext) -> Optional[ModelDetail]:
    """The model as this user may receive it, or None when it must not be shown at all (404)."""
    if ctx.hide_poi and detail.poi:
        return None
    if detail.nsfw and display_mode(ctx) == "hide":
        return None
    versions = [kept for kept in (filter_version(version, ctx) for version in detail.versions) if kept is not None]
    return detail.model_copy(update={"versions": versions})


def nsfw_media(detail: ModelDetail, ctx: NsfwContext) -> List[Image]:
    """The NSFW images of a model, with their urls, in version and image order (the "reveal" click).

    Raises `NsfwForbidden` when the user's ceiling is `blocked`. Images of real people are
    left out when `ctx.hide_poi`; duplicates (same url) are listed once.
    """
    if ctx.ceiling == "blocked":
        raise NsfwForbidden("NSFW media is not available to this user")
    seen = set()
    images: List[Image] = []
    for version in detail.versions:
        for image in version.images:
            if not image.nsfw or not image.url or image.url in seen:
                continue
            if ctx.hide_poi and image.poi:
                continue
            seen.add(image.url)
            images.append(image)
    return images
