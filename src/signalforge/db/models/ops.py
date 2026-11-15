"""Operational tables: what ran, and what it cost.

``stage_runs`` is the provenance spine (PRD §30): every business-state transition
writes one, and its unique key is what makes stage execution idempotent (PRD §29).
``llm_calls`` hangs off it so cost and latency roll up per stage, per entity and
per article, which is the Phase 1 exit criterion and the primary cost metric.

Deliberately absent: job state. ``queued``/``leased``/``retrying``/
``dead_lettered`` belong to the queue, not here (PRD §28). A stage run records
what a stage *did*; conflating the two is how a failed job ends up corrupting
business state.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from signalforge.db.base import Base, TimestampsMixin, UUIDPrimaryKeyMixin


class StageRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# native_enum=False stores a VARCHAR plus a CHECK constraint. PostgreSQL enum
# types cannot have values removed or reordered, which turns any later change to
# this list into a table rewrite.
STAGE_RUN_STATUS = Enum(
    StageRunStatus,
    native_enum=False,
    # Without this the column is a bare VARCHAR: SQLAlchemy defaults
    # create_constraint to False, so an invalid status would insert cleanly.
    create_constraint=True,
    length=16,
    name="stage_run_status",
    # Store the lowercase values, not the member names, so the column matches the
    # enum used everywhere else and stays readable in SQL.
    values_callable=lambda enum: [member.value for member in enum],
)


class StageRun(Base, UUIDPrimaryKeyMixin, TimestampsMixin):
    __tablename__ = "stage_runs"
    __table_args__ = (
        # PRD §29: re-running with an identical key returns the cached result,
        # because LLM output is not deterministic.
        UniqueConstraint(
            "stage",
            "entity_id",
            "input_hash",
            "stage_config_hash",
            name="uq_stage_runs_idempotency_key",
        ),
        Index("ix_stage_runs_entity_id_stage", "entity_id", "stage"),
        # Named without a prefix: the metadata naming convention adds "ck_<table>_".
        CheckConstraint("retry_count >= 0", name="retry_count_non_negative"),
    )

    stage: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID]
    input_hash: Mapped[str] = mapped_column(String(64))
    # Scoped to what this stage depends on, never a global config version: an
    # unrelated tweak must not rerun everything (PRD §29).
    stage_config_hash: Mapped[str] = mapped_column(String(64))

    status: Mapped[StageRunStatus] = mapped_column(STAGE_RUN_STATUS)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    retry_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    input_artifact_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    output_artifact_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    output_schema_version: Mapped[int | None] = mapped_column(default=None)

    llm_calls: Mapped[list["LLMCall"]] = relationship(
        back_populates="stage_run", cascade="all, delete-orphan"
    )


class LLMCall(Base, UUIDPrimaryKeyMixin, TimestampsMixin):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_role_model", "role", "model"),
        CheckConstraint("cost_usd >= 0", name="cost_non_negative"),
    )

    stage_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stage_runs.id", ondelete="CASCADE"))

    # Stages request a role; the gateway resolves the model. Both are recorded so
    # a routing change is visible in history.
    role: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    # Verification requires writer family != judge family, so the family is a
    # first-class column rather than something parsed out of the model id later.
    model_family: Mapped[str] = mapped_column(String(64))

    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cached_tokens: Mapped[int] = mapped_column(default=0)
    # Numeric, not float: costs are summed against a budget and must not drift.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(default=0)

    succeeded: Mapped[bool] = mapped_column(default=True)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    stage_run: Mapped[StageRun] = relationship(back_populates="llm_calls")


class PipelineControl(Base, TimestampsMixin):
    """One row (id 1): the kill switch and the 6-hour slot lease. Seeded by migration 0013."""

    __tablename__ = "pipeline_controls"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "slot_status IS NULL OR slot_status IN ('running', 'done', 'failed')",
            name="slot_status_allowed",
        ),
        CheckConstraint("slot_failures >= 0", name="slot_failures_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    paused_reason: Mapped[str | None] = mapped_column(Text, default=None)
    paused_by: Mapped[str | None] = mapped_column(String(32), default=None)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set by a circuit breaker: the pause lifts by itself after this. NULL for a manual pause.
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    slot: Mapped[str | None] = mapped_column(String(16), default=None)
    slot_status: Mapped[str | None] = mapped_column(String(16), default=None)
    slot_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    slot_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    slot_holder: Mapped[str | None] = mapped_column(String(64), default=None)
