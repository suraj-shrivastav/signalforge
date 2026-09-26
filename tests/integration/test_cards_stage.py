import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.artifacts.topic_card import ArticleFormat, RiskFlag, TopicCard
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.core.errors import ProviderRejectedError
from signalforge.db.models import StageRun, StageRunStatus
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.repositories.signals import SignalRepository
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider
from signalforge.llm.roles import ModelSpec
from signalforge.plugins.rankers.rules import score
from signalforge.stages.assess import run_assess
from signalforge.stages.cards import run_cards

pytestmark = pytest.mark.integration

BASE = datetime(2026, 9, 24, tzinfo=UTC)
SPEC = ModelSpec("acme/m", "acme")


def draft(**over: object) -> str:
    body: dict[str, object] = {
        "what_happened": "w",
        "why_it_matters": "y",
        "novelty": 0.5,
        "signal_strength": 0.5,
        "coverage_gap": "",
        "suggested_angle": "a",
        "format": "explainer",
        "evergreen_score": 0.5,
        "confidence": 0.5,
        "risk_flags": ["hype"],
    }
    return json.dumps(body | over)


def factory(
    replies: list[str], max_cost: str = "1", roles: dict[str, ModelSpec] | None = None
) -> Callable[[Session], LLMGateway]:
    provider = FakeProvider(replies)

    def make(session: Session) -> LLMGateway:
        budget = Budget(BudgetScope.TOPIC, BudgetLimits(max_cost_usd=Decimal(max_cost)))
        return LLMGateway(
            provider,
            roles or {"relevance_filter": SPEC, "topic_card": SPEC},
            budget,
            session,
        )

    return make


def seed_assessed(session: Session, count: int) -> None:
    SignalRepository(session).insert_new(
        [
            RawSignal(
                source="hackernews",
                source_type="community",
                canonical_url=f"https://example.com/cards/{uuid.uuid4()}",
                title=f"T{n}",
                published_at=BASE + timedelta(days=3650, minutes=n),
            )
            for n in range(count)
        ]
    )
    verdict = json.dumps(
        {
            "is_relevant": True,
            "relevance_score": 0.9,
            "category": "research",
            "summary": "s",
            "why_it_matters": "w",
        }
    )
    run_assess(session, factory([verdict] * count), limit=count)


def test_creates_card_and_rerun_is_noop(db_session: Session) -> None:
    seed_assessed(db_session, 1)
    first = run_cards(db_session, factory([draft()]), limit=1)
    assert (first.considered, first.created, first.failed) == (1, 1, 0)
    row = db_session.scalars(select(TopicCardRow).where(TopicCardRow.model == "acme/m")).one()
    assert row.prompt_version == "card-v1"
    expected = TopicCard(
        signal_id=row.signal_id,
        what_happened="w",
        why_it_matters="y",
        novelty=0.5,
        signal_strength=0.5,
        coverage_gap="",
        suggested_angle="a",
        format=ArticleFormat.EXPLAINER,
        evergreen_score=0.5,
        confidence=0.5,
        risk_flags=(RiskFlag.HYPE,),
        prompt_version="card-v1",
        model="acme/m",
    )
    # Assessment relevance is 0.9 (seed_assessed); the stage must feed it to the real scorer.
    assert row.score == pytest.approx(score(0.9, expected))
    assert row.score > 0.0
    again = run_cards(db_session, factory([]), limit=1)
    assert again.created == 0


def test_out_of_range_reply_fails_others_proceed(db_session: Session) -> None:
    seed_assessed(db_session, 2)
    bad = draft(novelty=2)
    # Newest first: the first signal gets the bad reply (plus one gateway retry).
    result = run_cards(db_session, factory([bad, bad, draft()]), limit=2)
    assert (result.created, result.failed) == (1, 1)


def test_budget_exhaustion_stops_cleanly(db_session: Session) -> None:
    seed_assessed(db_session, 1)
    result = run_cards(db_session, factory([draft()], max_cost="0"), limit=1)
    assert result.stopped_on_budget
    assert result.created == 0
    run = db_session.scalars(
        select(StageRun).where(StageRun.stage == "cards").order_by(StageRun.started_at.desc())
    ).first()
    assert run is not None
    assert run.status == StageRunStatus.SUCCEEDED


def test_provider_failure_marks_run_failed(db_session: Session) -> None:
    seed_assessed(db_session, 1)
    with pytest.raises(ProviderRejectedError):
        run_cards(db_session, factory([]), limit=1)
    run = db_session.scalars(select(StageRun).where(StageRun.stage == "cards")).one()
    assert run.status == StageRunStatus.FAILED
