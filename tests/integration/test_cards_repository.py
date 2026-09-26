from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from signalforge.core.artifacts.assessment import Category, SignalAssessment
from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.artifacts.topic_card import ArticleFormat, RiskFlag, TopicCard
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.db.repositories.assessments import AssessmentRepository
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration

BASE = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)  # inside the card lookback


def seed(session: Session, count: int) -> tuple[list[RawSignal], StageRun]:
    signals = [
        RawSignal(
            source="hackernews",
            source_type="community",
            canonical_url=f"https://example.com/{n}",
            title=f"Title {n}",
            published_at=BASE + timedelta(minutes=n),
        )
        for n in range(count)
    ]
    SignalRepository(session).insert_new(signals)
    run = StageRun(
        stage="card",
        entity_id=signals[0].id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.RUNNING,
    )
    session.add(run)
    session.flush()
    return signals, run


def assess(session: Session, signal: RawSignal, run: StageRun, *, relevant: bool) -> None:
    AssessmentRepository(session).insert(
        SignalAssessment(
            signal_id=signal.id,
            is_relevant=relevant,
            relevance_score=0.9,
            category=Category.RESEARCH,
            summary="s",
            why_it_matters="w",
            prompt_version="assess-v1",
            model="m",
        ),
        run.id,
        None,
    )


def card(signal: RawSignal, version: str = "card-v1") -> TopicCard:
    return TopicCard(
        signal_id=signal.id,
        what_happened="w",
        why_it_matters="m",
        novelty=0.5,
        signal_strength=0.5,
        coverage_gap="",
        suggested_angle="a",
        format=ArticleFormat.EXPLAINER,
        evergreen_score=0.5,
        confidence=0.5,
        risk_flags=(RiskFlag.HYPE,),
        prompt_version=version,
        model="m",
    )


def test_insert_once_then_conflict(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    repo = CardRepository(db_session)
    assert repo.insert(card(signals[0]), stage_run_id=run.id, llm_call_id=None, score=0.5) is True
    assert repo.insert(card(signals[0]), stage_run_id=run.id, llm_call_id=None, score=0.5) is False


def test_list_uncarded_only_relevant_without_card(db_session: Session) -> None:
    signals, run = seed(db_session, 3)
    assess(db_session, signals[0], run, relevant=True)
    assess(db_session, signals[1], run, relevant=True)
    assess(db_session, signals[2], run, relevant=False)
    repo = CardRepository(db_session)
    repo.insert(card(signals[1]), stage_run_id=run.id, llm_call_id=None, score=0.5)
    rows = repo.list_uncarded("card-v1", 10)
    assert [s.id for s, _ in rows] == [signals[0].id]
    assert rows[0][1].is_relevant is True
    assert [s.id for s, _ in repo.list_uncarded("card-v2", 10)] == [signals[1].id, signals[0].id]


def test_latest_decision_is_newest(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    repo = CardRepository(db_session)
    repo.insert(card(signals[0]), stage_run_id=run.id, llm_call_id=None, score=0.5)
    row = db_session.query(TopicCardRow).one()
    assert repo.latest_decision(row.id) is None
    repo.add_decision(row.id, "snoozed", [], "", None)
    repo.add_decision(row.id, "accepted", ["good"], "ok", 1200)
    latest = repo.latest_decision(row.id)
    assert latest is not None
    assert latest.decision == "accepted"


def test_invalid_decision_rejected(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    repo = CardRepository(db_session)
    repo.insert(card(signals[0]), stage_run_id=run.id, llm_call_id=None, score=0.5)
    row = db_session.query(TopicCardRow).one()
    with pytest.raises(IntegrityError):
        repo.add_decision(row.id, "maybe", [], "", None)


def test_list_uncarded_respects_lookback(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    assess(db_session, signals[0], run, relevant=True)
    repo = CardRepository(db_session)
    assert repo.list_uncarded("card-v1", 10, published_within_days=2)
    assert repo.list_uncarded("card-v1", 10, published_within_days=0) == []
