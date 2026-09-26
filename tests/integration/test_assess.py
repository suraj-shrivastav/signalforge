import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.core.errors import ProviderRejectedError
from signalforge.db.models import StageRun, StageRunStatus
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.repositories.signals import SignalRepository
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider
from signalforge.llm.roles import ModelSpec
from signalforge.stages.assess import run_assess

pytestmark = pytest.mark.integration

BASE = datetime(2026, 9, 24, tzinfo=UTC)


def good(relevant: bool = True) -> str:
    return json.dumps(
        {
            "is_relevant": relevant,
            "relevance_score": 0.8,
            "category": "research",
            "summary": "s",
            "why_it_matters": "w",
        }
    )


def seed(session: Session, count: int) -> None:
    SignalRepository(session).insert_new(
        [
            RawSignal(
                source="hackernews",
                source_type="community",
                canonical_url=f"https://example.com/assess/{uuid.uuid4()}",
                title=f"T{n}",
                published_at=BASE + timedelta(minutes=n),
            )
            for n in range(count)
        ]
    )


def factory(replies: list[str], max_cost: str = "1") -> Callable[[Session], LLMGateway]:
    provider = FakeProvider(replies)

    def make(session: Session) -> LLMGateway:
        budget = Budget(BudgetScope.TOPIC, BudgetLimits(max_cost_usd=Decimal(max_cost)))
        return LLMGateway(
            provider, {"relevance_filter": ModelSpec("acme/m", "acme")}, budget, session
        )

    return make


def test_assess_stores_and_rerun_is_noop(db_session: Session) -> None:
    seed(db_session, 2)
    first = run_assess(db_session, factory([good(), good(False)]), limit=2)
    assert (first.considered, first.assessed, first.relevant, first.failed) == (2, 2, 1, 0)
    assert db_session.scalars(select(SignalAssessmentRow)).all()
    again = run_assess(db_session, factory([]), limit=2)
    # Other rows in a shared DB may exist; ours are all assessed.
    assert again.assessed == 0


def test_invalid_reply_skipped_others_proceed(db_session: Session) -> None:
    seed(db_session, 2)
    result = run_assess(db_session, factory(["nope", "nope", good()]), limit=2)
    assert (result.assessed, result.failed) == (1, 1)


def test_budget_exhaustion_stops_cleanly(db_session: Session) -> None:
    seed(db_session, 2)
    result = run_assess(db_session, factory([good()], max_cost="0"), limit=2)
    assert result.stopped_on_budget
    assert result.assessed == 0
    run = db_session.get(StageRun, result.stage_run_id)
    assert run is not None
    assert run.status == StageRunStatus.SUCCEEDED


def test_provider_failure_marks_run_failed(db_session: Session) -> None:
    seed(db_session, 1)
    with pytest.raises(ProviderRejectedError):
        run_assess(db_session, factory([]), limit=1)
    run = db_session.scalars(select(StageRun).where(StageRun.stage == "assess")).one()
    assert run.status == StageRunStatus.FAILED
