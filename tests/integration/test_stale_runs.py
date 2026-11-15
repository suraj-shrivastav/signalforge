import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.db.models import (
    ArticleDraftRow,
    ResearchPackageRow,
    StageRun,
    StageRunStatus,
    TopicCardRow,
)
from signalforge.db.repositories.signals import SignalRepository
from signalforge.stale_runs import sweep_stale_runs

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
OLD = NOW - timedelta(hours=3)
FRESH = NOW - timedelta(minutes=5)


def _run(session: Session, started: datetime) -> StageRun:
    run = StageRun(
        stage="research", entity_id=uuid.uuid4(), input_hash=uuid.uuid4().hex,
        stage_config_hash="x", status=StageRunStatus.RUNNING, started_at=started,
    )  # fmt: skip
    session.add(run)
    session.flush()
    return run


def _card(session: Session) -> TopicCardRow:
    signal = RawSignal(
        source="hackernews",
        source_type="community",
        canonical_url=f"https://example.com/{uuid.uuid4()}",
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
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    card = TopicCardRow(
        signal_id=signal.id,
        stage_run_id=run.id,
        what_happened="w",
        why_it_matters="m",
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
    return card


def _age(
    session: Session,
    model: type[ResearchPackageRow] | type[ArticleDraftRow],
    row_id: uuid.UUID,
    at: datetime,
) -> None:
    # updated_at has an onupdate=now(), so set it explicitly after the insert.
    session.execute(update(model).where(model.id == row_id).values(updated_at=at))


def test_old_running_rows_fail_and_fresh_ones_stay(db_session: Session) -> None:
    old = _run(db_session, NOW - timedelta(hours=3))
    fresh = _run(db_session, NOW - timedelta(minutes=5))
    result = sweep_stale_runs(db_session, NOW)
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert result.stage_runs >= 1
    assert old.status == StageRunStatus.FAILED
    assert old.error == "interrupted: process restarted"
    assert fresh.status == StageRunStatus.RUNNING


def test_sweep_is_idempotent(db_session: Session) -> None:
    _run(db_session, NOW - timedelta(hours=3))
    sweep_stale_runs(db_session, NOW)
    assert sweep_stale_runs(db_session, NOW).stage_runs == 0


def test_old_researching_package_fails_and_fresh_one_stays(db_session: Session) -> None:
    old = ResearchPackageRow(card_id=_card(db_session).id)
    fresh = ResearchPackageRow(card_id=_card(db_session).id)
    db_session.add_all([old, fresh])
    db_session.flush()
    _age(db_session, ResearchPackageRow, old.id, OLD)
    _age(db_session, ResearchPackageRow, fresh.id, FRESH)
    result = sweep_stale_runs(db_session, NOW)
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert result.research >= 1
    assert (old.status, old.failure_reason) == ("failed", "interrupted")
    assert fresh.status == "researching"


def test_old_drafting_draft_fails_and_fresh_one_stays(db_session: Session) -> None:
    old = ArticleDraftRow(card_id=_card(db_session).id, template="explainer")
    fresh = ArticleDraftRow(card_id=_card(db_session).id, template="explainer")
    db_session.add_all([old, fresh])
    db_session.flush()
    _age(db_session, ArticleDraftRow, old.id, OLD)
    _age(db_session, ArticleDraftRow, fresh.id, FRESH)
    result = sweep_stale_runs(db_session, NOW)
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert result.drafts >= 1
    assert (old.status, old.failure_reason) == ("failed", "interrupted")
    assert fresh.status == "drafting"
