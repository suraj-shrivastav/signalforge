"""Topic cards and the editor's decisions on them."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class TopicCardRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "topic_cards"
    __table_args__ = (
        UniqueConstraint("signal_id", "prompt_version", name="uq_topic_cards_signal_prompt"),
        Index("ix_topic_cards_score", text("score DESC")),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    stage_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stage_runs.id"))
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"), default=None)
    what_happened: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    novelty: Mapped[float] = mapped_column(Float)
    signal_strength: Mapped[float] = mapped_column(Float)
    coverage_gap: Mapped[str] = mapped_column(Text)
    suggested_angle: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(16))
    evergreen_score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default=text("0"))
    wildcard: Mapped[bool] = mapped_column(default=False, server_default=false())
    prompt_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))


class EditorDecisionRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "editor_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('accepted', 'rejected', 'snoozed')", name="decision_allowed"),
        Index(
            "ix_editor_decisions_topic_card_id_decided_at", "topic_card_id", text("decided_at DESC")
        ),
    )

    topic_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topic_cards.id", ondelete="CASCADE")
    )
    decision: Mapped[str] = mapped_column(String(16))
    reason_tags: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    decision_ms: Mapped[int | None] = mapped_column(default=None)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
