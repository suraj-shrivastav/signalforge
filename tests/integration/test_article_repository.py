from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleCover,
    ArticleDraft,
    ArticleSection,
    ArticleTemplate,
    DraftStatus,
)
from signalforge.core.artifacts.research import ResearchPackage, ResearchStatus
from signalforge.core.artifacts.signal import RawSignal
from signalforge.db.models import ArticleDraftRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.db.repositories.research import ResearchRepository
from signalforge.db.repositories.signals import SignalRepository

pytestmark = pytest.mark.integration


def seed_researched(session: Session, url: str, status: ResearchStatus) -> UUID:
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
    pkg = ResearchPackage(card_id=card.id, status=status)
    assert ResearchRepository(session).insert(pkg, cost_usd=Decimal("0"), calls=0, tokens=0)
    return card.id


def drafted(card_id: UUID) -> ArticleDraft:
    body = ArticleBody(
        title="Title",
        dek="Dek",
        sections=(ArticleSection(heading="H", paragraphs=("P",)),),
        cover=ArticleCover(alt="Cover"),
    )
    return ArticleDraft(
        card_id=card_id,
        status=DraftStatus.DRAFTED,
        template=ArticleTemplate.EXPLAINER,
        draft=body,
        review_summary="ok",
    )


def test_researched_undrafted_is_returned_with_signal_and_package(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a1", ResearchStatus.RESEARCHED)
    rows = ArticleDraftRepository(db_session).list_researched_undrafted(10)
    assert [(c.id, s.id == c.signal_id, p.card_id) for c, s, p in rows] == [
        (card_id, True, card_id)
    ]


@pytest.mark.parametrize("status", [ResearchStatus.NEEDS_MORE_INFO, ResearchStatus.FAILED])
def test_unfinished_package_not_returned(db_session: Session, status: ResearchStatus) -> None:
    seed_researched(db_session, "https://example.com/a2", status)
    assert ArticleDraftRepository(db_session).list_researched_undrafted(10) == []


def test_card_with_existing_draft_not_returned(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a3", ResearchStatus.RESEARCHED)
    repo = ArticleDraftRepository(db_session)
    assert repo.insert(drafted(card_id), cost_usd=Decimal("0"), calls=0, tokens=0)
    assert repo.list_researched_undrafted(10) == []


def test_limit_is_respected(db_session: Session) -> None:
    for n in range(3):
        seed_researched(db_session, f"https://example.com/a4-{n}", ResearchStatus.RESEARCHED)
    assert len(ArticleDraftRepository(db_session).list_researched_undrafted(2)) == 2


def test_insert_writes_draft_and_totals(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a5", ResearchStatus.RESEARCHED)
    inserted = ArticleDraftRepository(db_session).insert(
        drafted(card_id), cost_usd=Decimal("0.25"), calls=2, tokens=900
    )
    assert inserted is True
    row = db_session.query(ArticleDraftRow).filter_by(card_id=card_id).one()
    assert (row.status, row.template, row.review_summary) == ("drafted", "explainer", "ok")
    assert row.draft["title"] == "Title"
    assert row.draft["sections"] == [{"heading": "H", "paragraphs": ["P"]}]
    assert (row.cost_usd, row.calls, row.tokens) == (Decimal("0.25"), 2, 900)


def test_insert_without_body_stores_empty_object(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a6", ResearchStatus.RESEARCHED)
    failed = ArticleDraft(
        card_id=card_id, status=DraftStatus.FAILED, template=ArticleTemplate.NEWS_BRIEF
    )
    assert ArticleDraftRepository(db_session).insert(
        failed, cost_usd=Decimal("0"), calls=0, tokens=0
    )
    row = db_session.query(ArticleDraftRow).filter_by(card_id=card_id).one()
    assert (row.status, row.draft) == ("failed", {})


def test_get_returns_row_or_none(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a8", ResearchStatus.RESEARCHED)
    repo = ArticleDraftRepository(db_session)
    assert repo.get(card_id) is None
    repo.insert(drafted(card_id), cost_usd=Decimal("0"), calls=0, tokens=0)
    found = repo.get(card_id)
    assert found is not None
    assert found.draft["title"] == "Title"


def test_list_recent_returns_drafts_with_signal_title(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a9", ResearchStatus.RESEARCHED)
    repo = ArticleDraftRepository(db_session)
    repo.insert(drafted(card_id), cost_usd=Decimal("0"), calls=0, tokens=0)
    rows = repo.list_recent(100)
    assert (card_id, "Title") in [(row.card_id, title) for row, title in rows]
    assert len(repo.list_recent(1)) == 1


def test_insert_duplicate_card_id_returns_false(db_session: Session) -> None:
    card_id = seed_researched(db_session, "https://example.com/a7", ResearchStatus.RESEARCHED)
    repo = ArticleDraftRepository(db_session)
    assert repo.insert(drafted(card_id), cost_usd=Decimal("0"), calls=0, tokens=0) is True
    assert repo.insert(drafted(card_id), cost_usd=Decimal("0"), calls=0, tokens=0) is False
    assert db_session.query(ArticleDraftRow).filter_by(card_id=card_id).count() == 1
