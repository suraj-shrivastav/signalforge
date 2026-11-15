"""Pure rules for the pipeline control row: is it paused, and which 6-hour slot is due."""

from datetime import datetime
from typing import Protocol

SLOT_HOURS = 6


class _Pausable(Protocol):
    paused: bool
    paused_until: datetime | None


def is_paused(row: _Pausable, now: datetime) -> bool:
    """A manual pause (no ``paused_until``) holds until resumed; a breaker pause expires."""
    if not row.paused:
        return False
    return row.paused_until is None or row.paused_until > now


def slot_id(now_local: datetime) -> str:
    """The 6-hour slot (00, 06, 12, 18 local) that ``now_local`` falls in."""
    hour = now_local.hour // SLOT_HOURS * SLOT_HOURS
    return f"{now_local:%Y-%m-%d}-{hour:02d}"
