from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from signalforge.core.errors import ProviderUnavailableError
from signalforge.core.protocols import SearchResult
from signalforge.db.repositories.assessments import AssessmentRepository
from signalforge.db.repositories.cards import CardRepository
from signalforge.stages.manual_topic import (
    MANUAL_SOURCE,
    TopicError,
    find_page,
    read_page,
    to_signal,
)

ARTICLE_HTML = (
    "<html><head><title>Mamba 3 results</title></head><body><article>{}</article></body></html>"
)
BODY = "Mamba 3 reaches a new state of the art on long context tasks. " * 12


class Fetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:  # noqa: ARG002
        self.asked.append(url)
        if url not in self.pages:
            raise ProviderUnavailableError("down")
        return self.pages[url]


class Search:
    def __init__(self, results: list[SearchResult], fail: bool = False) -> None:
        self.results, self.fail = results, fail

    def search(self, _query: str, *, max_results: int) -> list[SearchResult]:
        if self.fail:
            raise ProviderUnavailableError("no key")
        return self.results[:max_results]


def hit(n: int) -> SearchResult:
    return SearchResult(url=f"https://example.com/{n}", title=f"Hit {n}")


def test_read_page_keeps_title_and_text() -> None:
    page = read_page(Fetcher({"https://e.com/a": ARTICLE_HTML.format(BODY)}), "https://e.com/a")
    assert page.title == "Mamba 3 results"
    assert "state of the art" in page.text


def test_read_page_refuses_thin_or_unreachable_pages() -> None:
    thin = Fetcher({"https://e.com/a": ARTICLE_HTML.format("Too short.")})
    with pytest.raises(TopicError, match="no readable"):
        read_page(thin, "https://e.com/a")
    with pytest.raises(TopicError, match="could not be fetched"):
        read_page(Fetcher({}), "https://e.com/missing")


def test_find_page_skips_known_and_unreadable_hits_and_returns_the_rest() -> None:
    good = ARTICLE_HTML.format(BODY)
    fetcher = Fetcher({"https://example.com/2": "<html></html>", "https://example.com/3": good})
    search = Search([hit(1), hit(2), hit(3), hit(4)])
    page, others = find_page(search, fetcher, "mamba 3", lambda url: url.endswith("/1"))
    assert page.url == "https://example.com/3"
    assert [o.url for o in others] == [
        "https://example.com/1",
        "https://example.com/2",
        "https://example.com/4",
    ]
    assert "https://example.com/1" not in fetcher.asked  # known: never fetched


def test_find_page_reports_a_search_failure_and_an_empty_result() -> None:
    with pytest.raises(TopicError, match="Search failed"):
        find_page(Search([], fail=True), Fetcher({}), "x y z", lambda _u: False)
    with pytest.raises(TopicError, match="found nothing"):
        find_page(Search([]), Fetcher({}), "x y z", lambda _u: False)
    with pytest.raises(TopicError, match="None of the search results"):
        find_page(Search([hit(1)]), Fetcher({}), "x y z", lambda _u: False)


def test_the_signal_is_a_manual_one_with_the_note_and_the_hot_flag() -> None:
    page = read_page(
        Fetcher({"https://e.com/a?utm_source=x": ARTICLE_HTML.format(BODY)}),
        "https://e.com/a?utm_source=x",
    )
    now = datetime(2026, 10, 25, tzinfo=UTC)
    signal = to_signal(page, note="cover this", hot=True, now=now)
    assert (signal.source, signal.source_type) == (MANUAL_SOURCE, MANUAL_SOURCE)
    assert signal.canonical_url == "https://e.com/a"
    assert signal.metadata == {"note": "cover this", "hot": True}
    assert signal.published_at == now
    assert len(signal.summary) <= 600


def _sql(query: Any) -> str:
    return str(query.compile())


def test_assess_and_cards_can_be_limited_to_one_signal() -> None:
    seen: list[Any] = []

    class Session:
        def scalars(self, query: Any) -> list[Any]:
            seen.append(query)
            return []

        def execute(self, query: Any) -> SimpleNamespace:
            seen.append(query)
            return SimpleNamespace(all=lambda: [])

    import uuid

    ids = [uuid.uuid4()]
    AssessmentRepository(Session()).list_unassessed("v", 1, only=ids)  # type: ignore[arg-type]
    CardRepository(Session()).list_uncarded("v", 1, only=ids)  # type: ignore[arg-type]
    AssessmentRepository(Session()).list_unassessed("v", 1)  # type: ignore[arg-type]
    narrowed, narrowed_cards, plain = (_sql(q) for q in seen)
    assert "signals.id IN" in narrowed
    assert "signals.id IN" in narrowed_cards
    assert "signals.id IN" not in plain
