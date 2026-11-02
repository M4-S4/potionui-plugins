from typing import Any


def never_applies(request: Any) -> bool:
    """The core never enforces the kind; the plugin admits its own submits."""
    return False


def ledger_total(context: Any) -> float:
    """Usage is the total of the events the plugin recorded in the window."""
    return float(context.events.total())
