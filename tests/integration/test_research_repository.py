from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import ResearchDocument, ResearchPackage, ResearchStatus
from signalforge.core.artifacts.signal import RawSignal
from signalforge.db.models import ResearchPackageRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.research import ResearchRepository
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration


def seed_card(session: Session, url: str = "https://example.com/research") -> TopicCardRow:
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


def package(card_id: UUID) -> ResearchPackage:
    return ResearchPackage(
        card_id=card_id,
        status=ResearchStatus.RESEARCHED,
        documents=(
            ResearchDocument(
                url="https://example.com/doc",
                title="Doc",
                source_label="example",
                is_primary=True,
                raw_text_ref="ref-1",
                text="Doc body.",
                fetched_at=datetime.now(UTC),
            ),
        ),
        gaps_and_disagreements="none",
    )


def test_accepted_no_package_is_returned(db_session: Session) -> None:
    card = seed_card(db_session)
    CardRepository(db_session).add_decision(card.id, "accepted", [], "", None)
    rows = ResearchRepository(db_session).list_accepted_unresearched(10)
    assert [c.id for c, _ in rows] == [card.id]


def test_accepted_then_rejected_not_returned(db_session: Session) -> None:
    card = seed_card(db_session)
    repo = CardRepository(db_session)
    repo.add_decision(card.id, "accepted", [], "", None)
    repo.add_decision(card.id, "rejected", [], "", None)
    rows = ResearchRepository(db_session).list_accepted_unresearched(10)
    assert rows == []


def test_accepted_with_existing_package_not_returned(db_session: Session) -> None:
    card = seed_card(db_session)
    CardRepository(db_session).add_decision(card.id, "accepted", [], "", None)
    assert ResearchRepository(db_session).insert(
        package(card.id), cost_usd=Decimal("0"), calls=0, tokens=0
    )
    rows = ResearchRepository(db_session).list_accepted_unresearched(10)
    assert rows == []


def test_rejected_only_not_returned(db_session: Session) -> None:
    card = seed_card(db_session)
    CardRepository(db_session).add_decision(card.id, "rejected", [], "", None)
    rows = ResearchRepository(db_session).list_accepted_unresearched(10)
    assert rows == []


def test_limit_is_respected(db_session: Session) -> None:
    repo = CardRepository(db_session)
    for n in range(3):
        card = seed_card(db_session, url=f"https://example.com/research-{n}")
        repo.add_decision(card.id, "accepted", [], "", None)
    rows = ResearchRepository(db_session).list_accepted_unresearched(2)
    assert len(rows) == 2


def test_insert_fresh_card_id_and_readback(db_session: Session) -> None:
    card = seed_card(db_session)
    pkg = package(card.id)
    inserted = ResearchRepository(db_session).insert(
        pkg, cost_usd=Decimal("1.5"), calls=3, tokens=100
    )
    assert inserted is True
    row = db_session.query(ResearchPackageRow).filter_by(card_id=card.id).one()
    assert row.status == "researched"
    assert row.documents[0]["url"] == "https://example.com/doc"
    assert row.claims == []
    assert row.cost_usd == Decimal("1.5")
    assert row.calls == 3
    assert row.tokens == 100


def test_insert_duplicate_card_id_returns_false(db_session: Session) -> None:
    card = seed_card(db_session)
    repo = ResearchRepository(db_session)
    first = repo.insert(package(card.id), cost_usd=Decimal("0"), calls=0, tokens=0)
    second_package = package(card.id)
    second = repo.insert(second_package, cost_usd=Decimal("0"), calls=0, tokens=0)
    assert first is True
    assert second is False
    count = db_session.query(ResearchPackageRow).filter_by(card_id=card.id).count()
    assert count == 1
