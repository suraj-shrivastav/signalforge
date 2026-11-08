"""Sufficiency gate and the one bounded extra research round."""

import uuid
from types import SimpleNamespace
from typing import Any

from signalforge.core.artifacts.research import ResearchClaim, ResearchStatus
from signalforge.core.errors import BudgetExceededError
from signalforge.stages.research import _process_card
from signalforge.stages.research_gate import gap_queries, is_sufficient


def _claims(*texts: str) -> list[ResearchClaim]:
    return [ResearchClaim(text=t, evidence_span="e", document_indices=(0,)) for t in texts]


def test_two_claims_is_insufficient() -> None:
    assert not is_sufficient(_claims("a 1", "b 2"), 3, True)


def test_no_digit_is_insufficient() -> None:
    assert not is_sufficient(_claims("a", "b", "c"), 3, True)


def test_one_document_is_insufficient() -> None:
    assert not is_sufficient(_claims("a 1", "b", "c"), 1, False)


def test_two_documents_pass() -> None:
    assert is_sufficient(_claims("a 1", "b", "c"), 2, False)


def test_full_text_primary_passes_alone() -> None:
    assert is_sufficient(_claims("a 1", "b", "c"), 1, True)


def test_gap_queries_format() -> None:
    assert gap_queries("Foo") == ("Foo benchmark results", "Foo limitations criticism")


def _page(tag: str) -> str:
    body = f"<p>Fact {tag}: the model scores 91 percent on test {tag}.</p>" * 30
    return f"<html><body><article>{body}</article></body></html>"


class _Fetcher:
    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:  # noqa: ARG002
        return _page(url.rsplit("/", 1)[-1])


class _Search:
    """Results keyed by the last word of the query: query, results or criticism."""

    def __init__(self, urls: dict[str, list[str]]) -> None:
        self.urls = urls
        self.queries: list[str] = []

    def search(self, query: str, max_results: int = 5) -> list[Any]:
        self.queries.append(query)
        out = self.urls.get(query.split(" ")[-1], [])[:max_results]
        return [SimpleNamespace(url=u, title=u) for u in out]


class _Gateway:
    """One claim per document, with a digit unless ``digits`` is False."""

    def __init__(self, digits: bool = True, fail_after: int | None = None) -> None:
        self.digits = digits
        self.fail_after = fail_after
        self.calls = 0

    def complete_json(self, **kwargs: Any) -> Any:
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise BudgetExceededError("over")
        self.calls += 1
        tag = kwargs["user"].split("Fact ")[1].split(":")[0]
        span = f"Fact {tag}: the model scores 91 percent on test {tag}."
        plain = "".join(chr(ord("a") + int(c)) if c.isdigit() else c for c in tag)
        text = f"claim {plain} 91" if self.digits else f"claim {plain}"
        return kwargs["schema"](claims=[{"text": text, "evidence_span": span}])

    def embed(self, **kwargs: Any) -> Any:
        n = len(kwargs["texts"])
        return [tuple(1.0 if i == j else 0.0 for j in range(n)) for i in range(n)]


def _run(search: _Search, gateway: _Gateway) -> tuple[Any, str | None]:
    card = SimpleNamespace(id=uuid.uuid4(), what_happened="main query", why_it_matters="why")
    signal = SimpleNamespace(canonical_url="https://ex.com/p0", title="Title", source="rss")
    return _process_card(
        gateway,  # type: ignore[arg-type]
        _Fetcher(),
        search,
        card,  # type: ignore[arg-type]
        signal,  # type: ignore[arg-type]
        uuid.uuid4(),
    )


def test_sufficient_first_pass_skips_extra_round() -> None:
    search = _Search({"query": ["https://a.com/s1", "https://a.com/s2"]})
    package, why = _run(search, _Gateway())
    assert why is None
    assert package.status is ResearchStatus.RESEARCHED
    assert search.queries == ["main query"]


def test_extra_round_fixes_thin_package() -> None:
    search = _Search(
        {"query": ["https://a.com/s1"], "results": ["https://b.com/g1", "https://b.com/g2"]}
    )
    package, why = _run(search, _Gateway())
    assert why is None
    assert package.status is ResearchStatus.RESEARCHED
    assert search.queries == [
        "main query",
        "Title benchmark results",
        "Title limitations criticism",
    ]
    assert len(package.documents) == 4


def test_still_thin_is_needs_more_info_and_runs_once() -> None:
    search = _Search({"query": ["https://a.com/s1"]})
    package, why = _run(search, _Gateway(digits=False))
    assert package.status is ResearchStatus.NEEDS_MORE_INFO
    assert why is not None
    assert why.startswith("thin: 2 claims, 2 documents, numeric claim: no, full text: no")
    assert len(search.queries) == 3


def test_extra_round_adds_at_most_four_documents() -> None:
    search = _Search(
        {
            "results": ["https://c.com/x0", "https://c.com/x1", "https://c.com/x2"],
            "criticism": ["https://d.com/y0", "https://d.com/y1", "https://d.com/y2"],
        }
    )
    package, _ = _run(search, _Gateway(digits=False))
    assert len(package.documents) == 1 + 4


def test_document_cap_of_eight_respected() -> None:
    search = _Search(
        {
            "query": [f"https://a.com/s{i}" for i in range(4)],
            "results": ["https://b.com/g0", "https://b.com/g1"],
            "criticism": ["https://b.com/h0", "https://b.com/h1"],
        }
    )
    package, _ = _run(search, _Gateway(digits=False))
    assert len(package.documents) == 8


def test_budget_error_in_extra_round_is_budget() -> None:
    search = _Search({"query": ["https://a.com/s1"], "results": ["https://b.com/g1"]})
    package, why = _run(search, _Gateway(fail_after=2))
    assert package.status is ResearchStatus.FAILED
    assert why is not None
    assert why.startswith("budget: ")
