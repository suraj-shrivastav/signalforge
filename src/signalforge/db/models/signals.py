"""Signals: normalised items fetched from sources (PRD §33, §34).

One row per canonical URL. Rows are immutable artifacts, so a refetch of a known
URL is ignored rather than updated.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class Signal(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_signals_canonical_url"),
        Index("ix_signals_content_hash", "content_hash"),
        # Serves the keyset pagination order: newest first, id as tiebreaker.
        Index("ix_signals_published_at_id", "published_at", "id"),
    )

    source: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(32))
    canonical_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text, default="")
    # Promoted to columns only when queried or filtered (PRD §33); until then JSONB.
    entities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    topics: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # "metadata" is reserved on declarative classes, hence the attribute name.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    # The stage run that fetched it. SET NULL: deleting a run must not delete evidence.
    produced_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stage_runs.id", ondelete="SET NULL"), default=None
    )
