from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.artifacts.topic_card import ArticleFormat, RiskFlag, TopicCard
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.ops import StageRun, StageRunStatus
from signalforge.db.repositories.cards import CardRepository
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
        stage="card",
        entity_id=signals[0].id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.RUNNING,
    )
    session.add(run)
    session.flush()
    return signals, run


def card(signal: RawSignal, version: str = "card-v1", novelty: float = 0.5) -> TopicCard:
    return TopicCard(
        signal_id=signal.id,
        what_happened="w",
        why_it_matters="m",
        novelty=novelty,
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


SINCE = datetime(2000, 1, 1, tzinfo=UTC)


def make_cards(
    session: Session, count: int, novelty: Callable[[int], float] = lambda _n: 0.5
) -> list[TopicCardRow]:
    """Cards with score n/count; returned highest score first."""
    signals, run = seed(session, count)
    repo = CardRepository(session)
    for n, signal in enumerate(signals):
        repo.insert(
            card(signal, novelty=novelty(n)), stage_run_id=run.id, llm_call_id=None, score=n / count
        )
    session.flush()
    return list(session.query(TopicCardRow).order_by(TopicCardRow.score.desc()))


def test_queue_splits_top_and_wildcards(db_session: Session) -> None:
    # The two lowest-scored cards are the most novel, so they become the wildcards.
    rows = make_cards(db_session, 20, novelty=lambda n: 0.99 if n < 2 else 0.1)
    before = [(r.id, r.score, r.wildcard) for r in rows]
    items = CardRepository(db_session).queue(prompt_version="card-v1", since=SINCE)
    assert len(items) == 15
    assert [i.card.id for i in items[:13]] == [r.id for r in rows[:13]]
    assert [i.wildcard for i in items] == [False] * 13 + [True] * 2
    assert {i.card.id for i in items[13:]} == {r.id for r in rows[-2:]}
    assert items[0].signal_title.startswith("Title")
    # The wildcard flag is transient: queue() never writes it (or anything else).
    db_session.expire_all()
    after = db_session.query(TopicCardRow).order_by(TopicCardRow.score.desc()).all()
    assert [(r.id, r.score, r.wildcard) for r in after] == before
    assert not any(r.wildcard for r in after)


def test_decisions_filter_and_snooze(db_session: Session) -> None:
    rows = make_cards(db_session, 4)
    repo = CardRepository(db_session)
    repo.add_decision(rows[0].id, "accepted", [], "", None)
    repo.add_decision(rows[1].id, "rejected", [], "", None)
    repo.add_decision(rows[2].id, "snoozed", [], "", None)
    items = repo.queue(prompt_version="card-v1", since=SINCE)
    assert {i.card.id for i in items} == {rows[2].id, rows[3].id}
    assert {i.status for i in items if i.card.id == rows[2].id} == {"snoozed"}


def test_latest_decision_wins_with_explicit_times(db_session: Session) -> None:
    rows = make_cards(db_session, 2)
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    later_accept, later_snooze = rows[0], rows[1]
    for row, first, second, at in (
        (later_accept, "snoozed", "accepted", (t0, t1)),
        (later_snooze, "accepted", "snoozed", (t0, t1)),
    ):
        for decision, decided_at in zip((first, second), at, strict=True):
            db_session.add(
                EditorDecisionRow(
                    topic_card_id=row.id,
                    decision=decision,
                    reason_tags=[],
                    note="",
                    decision_ms=None,
                    decided_at=decided_at,
                )
            )
    db_session.flush()
    items = CardRepository(db_session).queue(prompt_version="card-v1", since=SINCE)
    assert [i.card.id for i in items] == [later_snooze.id]
    assert items[0].status == "snoozed"


def test_since_and_validation(db_session: Session) -> None:
    make_cards(db_session, 2)
    repo = CardRepository(db_session)
    assert repo.queue(prompt_version="card-v1", since=datetime.now(UTC) + timedelta(days=1)) == []
    with pytest.raises(ArtifactValidationError):
        repo.queue(prompt_version="card-v1", since=BASE.replace(tzinfo=None))
    with pytest.raises(ArtifactValidationError):
        repo.queue(prompt_version="card-v1", limit=0, since=SINCE)


def test_decision_stats_latest_per_card_and_waiting(db_session: Session) -> None:
    rows = make_cards(db_session, 5)
    t0 = datetime(2026, 9, 1, tzinfo=UTC)

    def decide(row: TopicCardRow, decision: str, at: datetime, tags: list[str], ms: int) -> None:
        db_session.add(
            EditorDecisionRow(
                topic_card_id=row.id,
                decision=decision,
                reason_tags=tags,
                note="",
                decision_ms=ms,
                decided_at=at,
            )
        )

    decide(rows[0], "snoozed", t0, [], 100)
    decide(rows[0], "accepted", t0 + timedelta(hours=1), ["timely"], 200)  # latest wins
    decide(rows[1], "rejected", t0, ["stale"], 300)
    decide(rows[2], "snoozed", t0, [], 400)
    db_session.flush()
    stats = CardRepository(db_session).decision_stats(SINCE, prompt_version="card-v1")
    assert stats.cards_created == 5
    assert sorted(d for d, _, _ in stats.decisions) == ["accepted", "rejected", "snoozed"]
    by_decision = {d: (tags, ms) for d, tags, ms in stats.decisions}
    assert by_decision["accepted"] == (["timely"], 200)
    # 2 undecided + 1 snoozed
    assert stats.waiting == 3
    future = CardRepository(db_session).decision_stats(
        datetime.now(UTC) + timedelta(days=1), prompt_version="card-v1"
    )
    assert (future.cards_created, future.decisions, future.waiting) == (0, [], 0)
    with pytest.raises(ArtifactValidationError):
        CardRepository(db_session).decision_stats(
            BASE.replace(tzinfo=None), prompt_version="card-v1"
        )


def test_queue_and_stats_ignore_other_prompt_version(db_session: Session) -> None:
    signals, run = seed(db_session, 2)
    repo = CardRepository(db_session)
    repo.insert(card(signals[0], "card-v1"), stage_run_id=run.id, llm_call_id=None, score=0.5)
    repo.insert(card(signals[1], "card-v2"), stage_run_id=run.id, llm_call_id=None, score=0.5)
    db_session.flush()
    items = repo.queue(prompt_version="card-v2", since=SINCE)
    assert [i.card.prompt_version for i in items] == ["card-v2"]
    assert repo.decision_stats(SINCE, prompt_version="card-v2").cards_created == 1
