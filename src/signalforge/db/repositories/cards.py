import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.topic_card import TopicCard
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.signals import Signal
from signalforge.db.repositories.assessments import latest_assessment


@dataclass(frozen=True)
class QueueItem:
    card: TopicCardRow
    signal_title: str
    source: str
    canonical_url: str
    wildcard: bool
    status: str  # "proposed" or "snoozed"


def _ranked(items: Sequence[QueueItem], *, novelty_first: bool = False) -> list[QueueItem]:
    """Stable total order: score desc, newest first, id; optionally novelty desc before all."""
    ordered = sorted(items, key=lambda i: str(i.card.id))
    ordered.sort(key=lambda i: i.card.created_at, reverse=True)
    ordered.sort(key=lambda i: i.card.score, reverse=True)
    if novelty_first:
        ordered.sort(key=lambda i: i.card.novelty, reverse=True)
    return ordered


def _validate(limit: int, wildcard_slots: int) -> None:
    if limit < 1:
        raise ArtifactValidationError("limit must be at least 1")
    if not 0 <= wildcard_slots <= limit:
        raise ArtifactValidationError("wildcard_slots must be between 0 and limit")


def select_queue(items: Sequence[QueueItem], limit: int, wildcard_slots: int) -> list[QueueItem]:
    """Top ``limit - wildcard_slots`` by score, then the most novel leftovers as wildcards."""
    _validate(limit, wildcard_slots)
    ranked = _ranked(items)
    top = ranked[: limit - wildcard_slots]
    rest = _ranked(ranked[len(top) :], novelty_first=True)
    wild = [replace(item, wildcard=True) for item in rest[:wildcard_slots]]
    return [*top, *wild]


class CardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(
        self,
        card: TopicCard,
        *,
        stage_run_id: uuid.UUID,
        llm_call_id: uuid.UUID | None,
        score: float,
    ) -> bool:
        """Insert unless this signal already has a card for the prompt version."""
        statement = (
            insert(TopicCardRow)
            .values(
                id=card.id,
                schema_version=card.schema_version,
                signal_id=card.signal_id,
                stage_run_id=stage_run_id,
                llm_call_id=llm_call_id,
                what_happened=card.what_happened,
                why_it_matters=card.why_it_matters,
                novelty=card.novelty,
                signal_strength=card.signal_strength,
                coverage_gap=card.coverage_gap,
                suggested_angle=card.suggested_angle,
                format=card.format.value,
                evergreen_score=card.evergreen_score,
                confidence=card.confidence,
                risk_flags=[flag.value for flag in card.risk_flags],
                score=score,
                prompt_version=card.prompt_version,
                model=card.model,
            )
            .on_conflict_do_nothing(index_elements=["signal_id", "prompt_version"])
            .returning(TopicCardRow.id)
        )
        return self._session.execute(statement).first() is not None

    def list_uncarded(
        self, prompt_version: str, limit: int
    ) -> list[tuple[Signal, SignalAssessmentRow]]:
        """Relevant signals with no card for this prompt version, newest first."""
        assessment = latest_assessment()
        carded = select(TopicCardRow.signal_id).where(TopicCardRow.prompt_version == prompt_version)
        query = (
            select(Signal, assessment)
            .join(assessment, assessment.signal_id == Signal.id)
            .where(assessment.is_relevant.is_(True), Signal.id.not_in(carded))
            .order_by(Signal.published_at.desc(), Signal.id.desc())
            .limit(limit)
        )
        return [(signal, found) for signal, found in self._session.execute(query).all()]

    def exists(self, card_id: uuid.UUID) -> bool:
        return self._session.get(TopicCardRow, card_id) is not None

    def add_decision(
        self,
        card_id: uuid.UUID,
        decision: str,
        reason_tags: Sequence[str],
        note: str,
        decision_ms: int | None,
    ) -> EditorDecisionRow:
        """Record a decision. The DB CHECK rejects values outside the allowed set."""
        row = EditorDecisionRow(
            topic_card_id=card_id,
            decision=decision,
            reason_tags=list(reason_tags),
            note=note,
            decision_ms=decision_ms,
            # Python-side: now() is constant within a transaction, so it cannot order decisions.
            decided_at=datetime.now(UTC),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def latest_decision(self, card_id: uuid.UUID) -> EditorDecisionRow | None:
        query = (
            select(EditorDecisionRow)
            .where(EditorDecisionRow.topic_card_id == card_id)
            .order_by(EditorDecisionRow.decided_at.desc(), EditorDecisionRow.created_at.desc())
            .limit(1)
        )
        return self._session.scalars(query).first()

    def queue(
        self, *, limit: int = 15, wildcard_slots: int = 2, since: datetime
    ) -> list[QueueItem]:
        """Cards awaiting a decision (none yet, or snoozed) created at or after ``since``."""
        if since.tzinfo is None:
            raise ArtifactValidationError("since must be timezone-aware")
        _validate(limit, wildcard_slots)
        latest = (
            select(EditorDecisionRow.topic_card_id, EditorDecisionRow.decision)
            .distinct(EditorDecisionRow.topic_card_id)
            .order_by(
                EditorDecisionRow.topic_card_id,
                EditorDecisionRow.decided_at.desc(),
                EditorDecisionRow.created_at.desc(),
            )
            .subquery()
        )
        query = (
            select(TopicCardRow, Signal, latest.c.decision)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .outerjoin(latest, latest.c.topic_card_id == TopicCardRow.id)
            .where(
                TopicCardRow.created_at >= since,
                or_(latest.c.decision.is_(None), latest.c.decision == "snoozed"),
            )
        )
        items = [
            QueueItem(
                card=row,
                signal_title=signal.title,
                source=signal.source,
                canonical_url=signal.canonical_url,
                wildcard=False,
                status="snoozed" if decision == "snoozed" else "proposed",
            )
            for row, signal, decision in self._session.execute(query).all()
        ]
        return select_queue(items, limit, wildcard_slots)
