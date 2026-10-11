"""The NSFW ceiling and display mode that apply to one user (PLAN.md §5.1).

Three layers, strictest wins:
1. the core's content policy for the user (instance setting, made stricter by their
   groups; `restricted_content` forces `blocked`) - `core_bridge.effective_policy`;
2. the plugin's own `nsfw_ceiling` setting, which can only tighten (`inherit`, `blur`, `blocked`);
3. the user's display preference, the core's `media_nsfw_filter_mode` (`show`, `blur`, `hide`),
   bounded by the resulting ceiling.

`compute_nsfw` is pure so the whole matrix is unit-testable; `resolve_nsfw` feeds it from
the core and the settings. The per-item filtering lives in `backend/nsfw_filter.py`.
"""

from typing import Tuple

from src.plugin_api import User

from . import core_bridge, settings
from .schema import NsfwCeiling, NsfwContext, NsfwMode

#: Ceilings from the least to the most restrictive; `blocked` beats `blur` beats `allowed`.
_CEILING_RANK = {"allowed": 0, "blur": 1, "blocked": 2}

#: Display modes a user may pick under each ceiling (PLAN.md §5.1 table).
ALLOWED_MODES = {
    "allowed": ("blur", "show", "hide"),
    "blur": ("blur", "hide"),
    "blocked": ("hide",),
}


def effective_ceiling(core_policy: str, ceiling_setting: str) -> NsfwCeiling:
    """The stricter of the core policy and the plugin ceiling (`inherit` defers to the core)."""
    core = core_policy if core_policy in _CEILING_RANK else "blocked"
    if ceiling_setting in ("blur", "blocked") and _CEILING_RANK[ceiling_setting] > _CEILING_RANK[core]:
        return ceiling_setting  # type: ignore[return-value]
    return core  # type: ignore[return-value]


def bounded_mode(ceiling: NsfwCeiling, user_mode: str) -> NsfwMode:
    """The user's display mode, pulled down to what the ceiling allows."""
    allowed: Tuple[str, ...] = ALLOWED_MODES[ceiling]
    if user_mode in allowed:
        return user_mode  # type: ignore[return-value]
    if ceiling == "blocked":
        return "hide"
    return "blur"


def compute_nsfw(
    core_policy: str,
    ceiling_setting: str,
    user_mode: str,
    max_level: int,
    hide_poi: bool,
) -> NsfwContext:
    """Pure assembly of the context from its five inputs."""
    ceiling = effective_ceiling(core_policy, ceiling_setting)
    return NsfwContext(
        ceiling=ceiling,
        mode=bounded_mode(ceiling, user_mode),
        allowed_modes=ALLOWED_MODES[ceiling],
        max_level=max_level,
        hide_poi=hide_poi,
    )


def resolve_nsfw(user: User) -> NsfwContext:
    """The context for a signed-in user, from the core policy, the plugin settings and the user's preference."""
    return compute_nsfw(
        core_policy=core_bridge.effective_policy(user.id),
        ceiling_setting=settings.get_setting("nsfw_ceiling"),
        user_mode=settings.user_nsfw_mode(user.id),
        max_level=settings.get_setting("nsfw_max_level"),
        hide_poi=settings.get_setting("hide_poi"),
    )
