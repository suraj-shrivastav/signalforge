from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.assessment import Category, SignalAssessment
from signalforge.core.artifacts.signal import RawSignal
from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.db.repositories.assessments import AssessmentRepository
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration

BASE = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


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
        stage="assess",
        entity_id=signals[0].id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.RUNNING,
    )
    session.add(run)
    session.flush()
    return signals, run


def assessment(signal: RawSignal, version: str = "assess-v1") -> SignalAssessment:
    return SignalAssessment(
        signal_id=signal.id,
        is_relevant=True,
        relevance_score=0.9,
        category=Category.RESEARCH,
        summary="s",
        why_it_matters="w",
        prompt_version=version,
        model="m",
    )


def test_insert_once_then_conflict(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    repo = AssessmentRepository(db_session)
    assert repo.insert(assessment(signals[0]), run.id, None) is True
    assert repo.insert(assessment(signals[0]), run.id, None) is False


def test_list_unassessed_excludes_assessed_and_limits(db_session: Session) -> None:
    signals, run = seed(db_session, 3)
    repo = AssessmentRepository(db_session)
    repo.insert(assessment(signals[2]), run.id, None)
    rows = repo.list_unassessed("assess-v1", 10)
    assert [r.id for r in rows] == [signals[1].id, signals[0].id]
    assert len(repo.list_unassessed("assess-v1", 1)) == 1


def test_new_prompt_version_makes_signal_unassessed(db_session: Session) -> None:
    signals, run = seed(db_session, 1)
    repo = AssessmentRepository(db_session)
    repo.insert(assessment(signals[0]), run.id, None)
    assert [r.id for r in repo.list_unassessed("assess-v2", 10)] == [signals[0].id]
