"""Failure classes for research: the prefix of ``failure_reason`` (e.g. ``blocked: ...``)."""

from enum import StrEnum

_MAX_REASON_CHARS = 500


class FailureClass(StrEnum):
    BLOCKED = "blocked"
    EMPTY = "empty"
    NO_CLAIMS = "no_claims"
    THIN = "thin"
    BUDGET = "budget"
    ERROR = "error"


def reason(kind: FailureClass, text: str) -> str:
    """``"<class>: <text>"`` cut to 500 characters."""
    return f"{kind.value}: {text}"[:_MAX_REASON_CHARS]
