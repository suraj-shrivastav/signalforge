"""Plugin seams. Implementations live in ``plugins/``; ``core`` never imports them."""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

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


class SearchResult(BaseModel):
    """One search hit: a page worth fetching, not evidence in itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    title: str


@runtime_checkable
class SearchProvider(Protocol):
    """Finds secondary sources for the research stage (PRD §24)."""

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        """Return at most ``max_results`` hits for ``query``.

        Raises a :class:`signalforge.core.errors.SignalForgeError` on failure.
        """
        ...


@runtime_checkable
class PageFetcher(Protocol):
    """Fetches one web page's HTML (PRD §24 search layer)."""

    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:
        """Return the decoded HTML body of ``url``.

        ``max_attempts=1`` asks for a single request with no retries (None keeps the default).

        Raises a :class:`signalforge.core.errors.SignalForgeError` on any failure,
        including a refused (unsafe or robots-disallowed) URL.
        """
        ...
