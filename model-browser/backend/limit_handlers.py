"""Handlers the core calls for the plugin's plan limit kinds (manifest `limit_kinds:`, PLAN.md §4.5).

The two kinds, `model-browser.downloads` and `model-browser.download_bytes`, are enforced by
the plugin, never by the core: the core only checks limits when a user submits a generation
or uploads a file (`enforce_at` must name one of those points), and neither has anything to
do with a model download. `never_applies` keeps the core from ever applying them there; the
plugin checks them itself before it queues a download (`backend/limits.py`).

The usage is what the plugin recorded in the core's limit ledger with `LimitEvents.record`
(one event per kind for each file queued for the user, refunded when the download fails):
`ledger_total` reads it back for the current window, for the plan editor, the users list and
the user's usage view, as for the plugin's own check (`plans.guard.measure`).

No import: the core loads this module on its own (`model_browser.backend.limit_handlers`).
"""

from typing import Any


def never_applies(request: Any) -> bool:
    """`applies_handler`: the core never enforces these kinds at a submit or an upload."""
    return False


def ledger_total(context: Any) -> float:
    """`measure_handler`: the user's recorded, unrefunded events of this kind in the current window."""
    return float(context.events.total())
