# ruff: noqa: ARG002
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.budget import Budget, BudgetLimits
from signalforge.core.errors import ProviderRejectedError
from signalforge.core.protocols import SearchResult
from signalforge.db.models import ResearchPackageRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.research import ResearchRepository
from signalforge.db.repositories.signals import SignalRepository
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import EmbeddingReply, FakeProvider, ProviderReply
from signalforge.llm.roles import ModelSpec
from signalforge.stages.research import EMBEDDING_ROLE, ROLE, run_research

pytestmark = pytest.mark.integration

PRIMARY_TEXT = (
    "<html><body><article><h1>Model release</h1>"
    "<p>The model beats the prior best by a wide margin in every benchmark tested.</p>"
    "<p>Researchers confirmed the results across multiple independent evaluation runs "
    "conducted over several weeks.</p></article></body></html>"
)
SECONDARY_TEXT = (
    "<html><body><article><h1>Coverage</h1>"
    "<p>Reviewers said the model beats the prior best by a wide margin on the public "
    "leaderboard, according to an independent write-up published this week.</p>"
    "</article></body></html>"
)
PAPER_TEXT = (
    "<html><head><title>The Paper Title</title></head><body><article><h1>Method</h1>"
    "<p>We train the model with a two-stage curriculum and report that it beats the prior "
    "best by a wide margin on five held-out evaluation suites.</p></article></body></html>"
)
DEFAULT_LIMITS = BudgetLimits(max_cost_usd=Decimal("1"))


def claims_reply(span: str, text: str = "claim") -> str:
    return json.dumps({"claims": [{"text": text, "evidence_span": span}]})


def rich_reply(span: str, text: str = "claim") -> str:
    """Three claims, one with a digit, so the research gate (MIN_CLAIMS, numeric) passes."""
    return json.dumps(
        {
            "claims": [
                {"text": text, "evidence_span": span},
                {"text": "second claim, 2 runs", "evidence_span": "every benchmark tested"},
                {
                    "text": "third claim",
                    "evidence_span": "across multiple independent evaluation runs",
                },
            ]
        }
    )


class _DistinctEmbeddingProvider(FakeProvider):
    """Orthogonal vectors per text, so no claims merge (the default embeds all alike)."""

    def embed(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply:
        vectors = [
            tuple(1.0 if j == i else 0.0 for j in range(len(texts))) for i in range(len(texts))
        ]
        return EmbeddingReply(vectors, input_tokens=0, latency_ms=0)


class FakeFetcher:
    def __init__(self, pages: dict[str, str | Exception]) -> None:
        self._pages = pages

    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:
        page = self._pages.get(url, "<html></html>")
        if isinstance(page, Exception):
            raise page
        return page


class FakeSearch:
    def __init__(self, results: list[SearchResult] | Exception | None = None) -> None:
        self._results = results

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        if isinstance(self._results, Exception):
            raise self._results
        return self._results or []


def gateway_factory(replies: list[str]) -> Callable[[Session, Budget], LLMGateway]:
    provider = _DistinctEmbeddingProvider(replies)

    def make(session: Session, budget: Budget) -> LLMGateway:
        roles = {ROLE: ModelSpec("acme/m", "acme"), EMBEDDING_ROLE: ModelSpec("acme/e", "acme")}
        return LLMGateway(provider, roles, budget, session)

    return make


def seed_card(session: Session, url: str = "https://example.com/article") -> TopicCardRow:
    signal = RawSignal(
        source="hackernews",
        source_type="community",
        canonical_url=url,
        title="Title",
        published_at=datetime.now(UTC),
    )
    SignalRepository(session).insert_new([signal])
    run = StageRun(
        stage="card",
        entity_id=signal.id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.SUCCEEDED,
    )
    session.add(run)
    session.flush()
    card = TopicCardRow(
        signal_id=signal.id,
        stage_run_id=run.id,
        what_happened="A new model shipped",
        why_it_matters="It matters",
        novelty=0.5,
        signal_strength=0.5,
        coverage_gap="",
        suggested_angle="a",
        format="explainer",
        evergreen_score=0.5,
        confidence=0.5,
        prompt_version="card-v1",
        model="m",
    )
    session.add(card)
    session.flush()
    CardRepository(session).add_decision(card.id, "accepted", [], "", None)
    return card


def row_for(session: Session, card_id: object) -> ResearchPackageRow:
    return session.query(ResearchPackageRow).filter_by(card_id=card_id).one()


def test_full_success(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher(
        {"https://example.com/article": PRIMARY_TEXT, "https://sec.example.com/": SECONDARY_TEXT}
    )
    span = "beats the prior best by a wide margin"
    result = run_research(
        db_session,
        gateway_factory([rich_reply(span), rich_reply(span)]),
        fetcher,
        FakeSearch([SearchResult(url="https://sec.example.com/", title="Coverage")]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.status == "researched"
    assert len(row.claims) == 4


def test_primary_fetch_error_needs_more_info(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher({"https://example.com/article": ProviderRejectedError("nope")})
    result = run_research(
        db_session, gateway_factory([]), fetcher, FakeSearch([]), budget_limits=DEFAULT_LIMITS
    )
    assert result.needs_more_info == 1
    row = row_for(db_session, card.id)
    assert row.status == "needs_more_info"
    assert row.documents == []


def test_span_not_found_needs_more_info(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher({"https://example.com/article": PRIMARY_TEXT})
    result = run_research(
        db_session,
        gateway_factory([claims_reply("this text is not in the document")]),
        fetcher,
        FakeSearch([]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.needs_more_info == 1
    row = row_for(db_session, card.id)
    assert len(row.documents) == 1
    assert row.claims == []


def test_budget_exceeded_marks_failed(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher({"https://example.com/article": PRIMARY_TEXT})
    result = run_research(
        db_session,
        gateway_factory([claims_reply("beats the prior best")]),
        fetcher,
        FakeSearch([]),
        budget_limits=BudgetLimits(max_cost_usd=Decimal("0")),
    )
    assert result.failed == 1
    row = row_for(db_session, card.id)
    assert row.status == "failed"
    assert row.documents == []
    assert row.claims == []


def test_already_researched_card_not_reconsidered(db_session: Session) -> None:
    card = seed_card(db_session)
    from signalforge.core.artifacts.research import ResearchPackage

    ResearchRepository(db_session).insert(
        ResearchPackage(card_id=card.id), cost_usd=Decimal("0"), calls=0, tokens=0
    )
    result = run_research(
        db_session,
        gateway_factory([]),
        FakeFetcher({}),
        FakeSearch([]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.considered == 0


def test_secondary_search_failure_does_not_fail_card(db_session: Session) -> None:
    card = seed_card(db_session)
    # Search is down, so the independent document is the paper the primary cites.
    primary = PRIMARY_TEXT.replace(
        "</article>", '<a href="https://arxiv.org/pdf/2609.02849v2">paper</a></article>'
    )
    fetcher = FakeFetcher(
        {
            "https://example.com/article": primary,
            "https://arxiv.org/html/2609.02849": ProviderRejectedError("404"),
            "https://arxiv.org/abs/2609.02849": PAPER_TEXT,
        }
    )
    span = "beats the prior best"
    result = run_research(
        db_session,
        gateway_factory([rich_reply(span), rich_reply(span)]),
        fetcher,
        FakeSearch(ProviderRejectedError("search down")),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.status == "researched"


def test_blank_secondary_title_falls_back_to_hostname(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher(
        {
            "https://example.com/article": PRIMARY_TEXT,
            "https://sec.example.com/": SECONDARY_TEXT,
        }
    )
    result = run_research(
        db_session,
        gateway_factory(
            [
                rich_reply("beats the prior best by a wide margin"),
                rich_reply("beats the prior best by a wide margin"),
            ]
        ),
        fetcher,
        FakeSearch([SearchResult(url="https://sec.example.com/", title="")]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.status == "researched"
    secondary = next(doc for doc in row.documents if not doc["is_primary"])
    assert secondary["title"] == "sec.example.com"


def test_claim_text_with_apostrophe_is_stored_unescaped(db_session: Session) -> None:
    card = seed_card(db_session)
    text = (
        "<html><body><article><h1>Model release</h1>"
        "<p>The model's accuracy improved significantly across every benchmark tested "
        "by the independent research team.</p></article></body></html>"
    )
    fetcher = FakeFetcher(
        {"https://example.com/article": text, "https://sec.example.com/": SECONDARY_TEXT}
    )
    result = run_research(
        db_session,
        gateway_factory(
            [
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "The model's accuracy improved significantly",
                                "evidence_span": "The model's accuracy improved significantly",
                            },
                            {
                                "text": "It held across 2 benchmarks",
                                "evidence_span": "across every benchmark tested",
                            },
                            {
                                "text": "A team ran it",
                                "evidence_span": "by the independent research team",
                            },
                        ]
                    }
                ),
                json.dumps({"claims": []}),
            ]
        ),
        fetcher,
        FakeSearch([SearchResult(url="https://sec.example.com/", title="Coverage")]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert len(row.claims) == 3
    assert row.claims[0]["text"] == "The model's accuracy improved significantly"
    assert "&#x27;" not in row.claims[0]["text"]
    assert "&quot;" not in row.claims[0]["text"]


class _PricedProvider:
    name = "priced-fake"

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        timeout_s: float,
        max_tokens: int | None = None,
    ) -> ProviderReply:
        return ProviderReply(
            rich_reply("beats the prior best"), input_tokens=100, output_tokens=50, latency_ms=1
        )

    def embed(self, model: str, texts: list[str], *, timeout_s: float) -> EmbeddingReply:
        vectors = [
            tuple(1.0 if j == i else 0.0 for j in range(len(texts))) for i in range(len(texts))
        ]
        return EmbeddingReply(vectors, input_tokens=10, latency_ms=1)


def test_written_row_has_nonzero_cost_calls_tokens(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher(
        {"https://example.com/article": PRIMARY_TEXT, "https://sec.example.com/": SECONDARY_TEXT}
    )

    def make(session: Session, budget: Budget) -> LLMGateway:
        roles = {ROLE: ModelSpec("acme/m", "acme"), EMBEDDING_ROLE: ModelSpec("acme/e", "acme")}
        return LLMGateway(_PricedProvider(), roles, budget, session)

    result = run_research(
        db_session,
        make,
        fetcher,
        FakeSearch([SearchResult(url="https://sec.example.com/", title="Coverage")]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.calls > 0
    assert row.tokens > 0
    assert row.cost_usd >= Decimal("0")


def test_cited_paper_is_fetched_as_a_document(db_session: Session) -> None:
    card = seed_card(db_session)
    primary = PRIMARY_TEXT.replace(
        "</article>", '<a href="https://arxiv.org/pdf/2609.02849v2">paper</a></article>'
    )
    fetcher = FakeFetcher(
        {
            "https://example.com/article": primary,
            # The full-text render is unavailable, so the abstract page is used.
            "https://arxiv.org/html/2609.02849": ProviderRejectedError("404"),
            "https://arxiv.org/abs/2609.02849": PAPER_TEXT,
        }
    )
    span = "beats the prior best by a wide margin"
    result = run_research(
        db_session,
        gateway_factory([rich_reply(span), rich_reply(span)]),
        fetcher,
        FakeSearch([SearchResult(url="https://arxiv.org/abs/2609.02849", title="dup")]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    docs = row_for(db_session, card.id).documents
    assert [(d["url"], d["source_label"], d["title"]) for d in docs[1:]] == [
        ("https://arxiv.org/abs/2609.02849", "arxiv.org", "The Paper Title")
    ]


def test_mirror_of_the_primary_is_dropped(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher(
        {"https://example.com/article": PRIMARY_TEXT, "https://mirror.example.net/": PRIMARY_TEXT}
    )
    result = run_research(
        db_session,
        gateway_factory([rich_reply("beats the prior best by a wide margin")]),
        fetcher,
        FakeSearch([SearchResult(url="https://mirror.example.net/", title="Mirror")]),
        budget_limits=DEFAULT_LIMITS,
    )
    # A mirror is not independent evidence, so the lone primary cannot pass the gate.
    assert result.needs_more_info == 1
    assert len(row_for(db_session, card.id).documents) == 1
