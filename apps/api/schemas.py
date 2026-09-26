from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.signals import Signal


class AssessmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_relevant: bool
    relevance_score: float
    category: str
    summary: str
    why_it_matters: str


class SignalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source: str
    source_type: str
    canonical_url: str
    title: str
    published_at: datetime
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    assessment: AssessmentOut | None = None

    @classmethod
    def from_row(cls, row: Signal, assessment: SignalAssessmentRow | None = None) -> "SignalOut":
        return cls(
            id=row.id,
            source=row.source,
            source_type=row.source_type,
            canonical_url=row.canonical_url,
            title=row.title,
            published_at=row.published_at,
            summary=row.summary,
            metadata=row.metadata_,
            assessment=AssessmentOut(
                is_relevant=assessment.is_relevant,
                relevance_score=assessment.relevance_score,
                category=assessment.category,
                summary=assessment.summary,
                why_it_matters=assessment.why_it_matters,
            )
            if assessment
            else None,
        )


class SignalListOut(BaseModel):
    items: list[SignalOut]
    next_cursor: str | None
