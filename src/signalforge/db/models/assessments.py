"""Signal assessments: one LLM relevance judgement per (signal, prompt version)."""

import uuid

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class SignalAssessmentRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "signal_assessments"
    __table_args__ = (
        UniqueConstraint("signal_id", "prompt_version", name="uq_signal_assessments_signal_prompt"),
        Index(
            "ix_signal_assessments_is_relevant_relevance_score", "is_relevant", "relevance_score"
        ),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    stage_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stage_runs.id"))
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"), default=None)
    is_relevant: Mapped[bool]
    relevance_score: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
