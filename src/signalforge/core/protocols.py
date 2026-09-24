"""Plugin seams. Implementations live in ``plugins/``; ``core`` never imports them."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from signalforge.core.artifacts.signal import RawSignal


@runtime_checkable
class Source(Protocol):
    """A place signals come from (PRD §24)."""

    name: str
    source_type: str

    def fetch(self, since: datetime) -> Iterable[RawSignal]:
        """Return signals published after ``since``.

        Raises a :class:`signalforge.core.errors.SignalForgeError` on failure, and
        never returns partial results silently.
        """
        ...
