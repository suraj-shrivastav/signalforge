import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.topic_card import TopicCard
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.signals import Signal
from signalforge.db.repositories.assessments import latest_assessment


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
