import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from signalforge.core.artifacts.assessment import SignalAssessment
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.signals import Signal


def latest_assessment() -> type[SignalAssessmentRow]:
    """Alias over each signal's latest assessment (highest prompt version present)."""
    latest = (
        select(SignalAssessmentRow)
        .distinct(SignalAssessmentRow.signal_id)
        .order_by(SignalAssessmentRow.signal_id, SignalAssessmentRow.prompt_version.desc())
        .subquery()
    )
    return aliased(SignalAssessmentRow, latest)


class AssessmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(
        self, assessment: SignalAssessment, stage_run_id: uuid.UUID, llm_call_id: uuid.UUID | None
    ) -> bool:
        """Insert unless this signal already has a row for the prompt version."""
        statement = (
            insert(SignalAssessmentRow)
            .values(
                id=assessment.id,
                schema_version=assessment.schema_version,
                signal_id=assessment.signal_id,
                stage_run_id=stage_run_id,
                llm_call_id=llm_call_id,
                is_relevant=assessment.is_relevant,
                relevance_score=assessment.relevance_score,
                category=assessment.category.value,
                summary=assessment.summary,
                why_it_matters=assessment.why_it_matters,
                prompt_version=assessment.prompt_version,
                model=assessment.model,
            )
            .on_conflict_do_nothing(index_elements=["signal_id", "prompt_version"])
            .returning(SignalAssessmentRow.id)
        )
        return self._session.execute(statement).first() is not None

    def list_unassessed(self, prompt_version: str, limit: int) -> list[Signal]:
        """Signals with no assessment for this prompt version, newest first."""
        assessed = select(SignalAssessmentRow.signal_id).where(
            SignalAssessmentRow.prompt_version == prompt_version
        )
        query = (
            select(Signal)
            .where(Signal.id.not_in(assessed))
            .order_by(Signal.published_at.desc(), Signal.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(query))
