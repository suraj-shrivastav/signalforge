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
from signalforge.llm.providers import FakeProvider, ProviderReply
from signalforge.llm.roles import ModelSpec
from signalforge.stages.research import ROLE, run_research

pytestmark = pytest.mark.integration

PRIMARY_TEXT = (
    "<html><body><article><h1>Model release</h1>"
    "<p>The model beats the prior best by a wide margin in every benchmark tested.</p>"
    "<p>Researchers confirmed the results across multiple independent evaluation runs "
    "conducted over several weeks.</p></article></body></html>"
)
DEFAULT_LIMITS = BudgetLimits(max_cost_usd=Decimal("1"))


def claims_reply(span: str, text: str = "claim") -> str:
    return json.dumps({"claims": [{"text": text, "evidence_span": span}]})


class FakeFetcher:
    def __init__(self, pages: dict[str, str | Exception]) -> None:
        self._pages = pages

    def fetch_html(self, url: str) -> str:
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
    provider = FakeProvider(replies)

    def make(session: Session, budget: Budget) -> LLMGateway:
        return LLMGateway(provider, {ROLE: ModelSpec("acme/m", "acme")}, budget, session)

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
    fetcher = FakeFetcher({"https://example.com/article": PRIMARY_TEXT})
    result = run_research(
        db_session,
        gateway_factory([claims_reply("beats the prior best by a wide margin")]),
        fetcher,
        FakeSearch([]),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.status == "researched"
    assert len(row.claims) == 1


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
    fetcher = FakeFetcher({"https://example.com/article": PRIMARY_TEXT})
    result = run_research(
        db_session,
        gateway_factory([claims_reply("beats the prior best")]),
        fetcher,
        FakeSearch(ProviderRejectedError("search down")),
        budget_limits=DEFAULT_LIMITS,
    )
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.status == "researched"


class _PricedProvider:
    name = "priced-fake"

    def chat(
        self, model: str, messages: list[dict[str, str]], *, json_mode: bool, timeout_s: float
    ) -> ProviderReply:
        return ProviderReply(
            claims_reply("beats the prior best"), input_tokens=100, output_tokens=50, latency_ms=1
        )


def test_written_row_has_nonzero_cost_calls_tokens(db_session: Session) -> None:
    card = seed_card(db_session)
    fetcher = FakeFetcher({"https://example.com/article": PRIMARY_TEXT})

    def make(session: Session, budget: Budget) -> LLMGateway:
        return LLMGateway(_PricedProvider(), {ROLE: ModelSpec("acme/m", "acme")}, budget, session)

    result = run_research(db_session, make, fetcher, FakeSearch([]), budget_limits=DEFAULT_LIMITS)
    assert result.researched == 1
    row = row_for(db_session, card.id)
    assert row.calls > 0
    assert row.tokens > 0
    assert row.cost_usd >= Decimal("0")
