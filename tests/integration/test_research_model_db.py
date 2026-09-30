from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.db.models import ResearchPackageRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration


def seed_card(session: Session) -> TopicCardRow:
    signal = RawSignal(
        source="hackernews",
        source_type="community",
        canonical_url="https://example.com/research",
        title="Title",
        published_at=datetime.now(UTC),
    )
    SignalRepository(session).insert_new([signal])
    run = StageRun(
        stage="card",
        entity_id=signal.id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.RUNNING,
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


def test_insert_applies_defaults(db_session: Session) -> None:
    card = seed_card(db_session)
    row = ResearchPackageRow(card_id=card.id)
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)
    assert row.status == "researching"
    assert row.documents == []
    assert row.claims == []
    assert row.gaps_and_disagreements == ""
    assert row.cost_usd == Decimal("0")
    assert (row.calls, row.tokens, row.schema_version) == (0, 0, 1)


def test_server_defaults_cover_raw_inserts(db_session: Session) -> None:
    card = seed_card(db_session)
    db_session.execute(
        text("INSERT INTO research_packages (id, card_id, schema_version) VALUES (:id, :card, 1)"),
        {"id": uuid4(), "card": card.id},
    )
    row = db_session.execute(
        text(
            "SELECT status, documents, claims, gaps_and_disagreements, cost_usd, calls, tokens"
            " FROM research_packages WHERE card_id = :card"
        ),
        {"card": card.id},
    ).one()
    assert tuple(row) == ("researching", [], [], "", Decimal("0"), 0, 0)


def test_one_package_per_card(db_session: Session) -> None:
    card = seed_card(db_session)
    db_session.add(ResearchPackageRow(card_id=card.id))
    db_session.flush()
    db_session.add(ResearchPackageRow(card_id=card.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unknown_status_rejected(db_session: Session) -> None:
    card = seed_card(db_session)
    db_session.add(ResearchPackageRow(card_id=card.id, status="done"))
    with pytest.raises(IntegrityError):
        db_session.flush()
