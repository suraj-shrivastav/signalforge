"""A topic the owner asks for: a URL, or plain text that is searched for a source page.

The page becomes a signal like any ingested one (source ``manual``) and then goes through
assess and cards on its own. Pure helpers here; the job that runs them is in
``apps/worker/topic.py``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.errors import SignalForgeError
from signalforge.core.protocols import PageFetcher, SearchProvider, SearchResult
from signalforge.stages.research_extraction import extract_clean_text, page_title

MANUAL_SOURCE = "manual"
MIN_TEXT_CHARS = 400
# A hot topic is accepted and scored above any card the editor sees (scores are 0 to 1), so the
# best-first research queue takes it next.
HOT_SCORE = 10.0
_SUMMARY_CHARS = 600
_SEARCH_RESULTS = 6


class TopicError(Exception):
    """The topic cannot be used. ``message`` is safe to show the owner."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class TopicPage:
    url: str
    title: str
    text: str


def read_page(fetcher: PageFetcher, url: str, fallback_title: str = "") -> TopicPage:
    """Fetch one page and keep its readable text. Raises TopicError when it has none."""
    try:
        html = fetcher.fetch_html(url)
    except SignalForgeError as exc:
        raise TopicError("The page could not be fetched") from exc
    text = extract_clean_text(html)
    if text is None or len(text) < MIN_TEXT_CHARS:
        raise TopicError("The page has no readable article text")
    title = (page_title(html) or fallback_title or url).strip()
    return TopicPage(url=url, title=title, text=text)


def find_page(
    search: SearchProvider,
    fetcher: PageFetcher,
    query: str,
    is_known: Callable[[str], bool],
) -> tuple[TopicPage, list[SearchResult]]:
    """Search for ``query`` and read the first usable result. Returns it and the other hits.

    A hit whose URL is already a signal is skipped so the same page is not added twice.
    """
    try:
        results = search.search(query, max_results=_SEARCH_RESULTS)
    except SignalForgeError as exc:
        raise TopicError("Search failed or is not configured") from exc
    if not results:
        raise TopicError("Search found nothing for that topic")
    for i, hit in enumerate(results):
        if is_known(hit.url):
            continue
        try:
            page = read_page(fetcher, hit.url, hit.title)
        except TopicError:
            continue
        return page, results[:i] + results[i + 1 :]
    raise TopicError("None of the search results could be read, or all are already known")


def to_signal(page: TopicPage, *, note: str, hot: bool, now: datetime | None = None) -> RawSignal:
    return RawSignal(
        source=MANUAL_SOURCE,
        source_type=MANUAL_SOURCE,
        canonical_url=page.url,
        title=page.title,
        published_at=now or datetime.now(UTC),
        summary=page.text[:_SUMMARY_CHARS],
        metadata={"note": note, "hot": hot},
    )
