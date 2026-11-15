"""Article drafts: a templated draft with per-claim status for a researched topic card."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class ArticleDraftRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "article_drafts"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_article_drafts_card_id"),
        CheckConstraint(
            "status IN ('drafting', 'drafted', 'needs_more_info', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint(
            "template IN ('news_brief', 'explainer', 'paper_breakdown', 'comparison')",
            name="template_allowed",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'revise', 'rejected')",
            name="review_status_allowed",
        ),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic_cards.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="drafting", server_default="drafting")
    template: Mapped[str] = mapped_column(String(32))
    draft: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    review_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Editor review: the editor's decision on the draft, and an audit trail of edits.
    review_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    review_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_log: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # Why the card failed (typed error text, no secrets); NULL unless status is 'failed'.
    failure_reason: Mapped[str | None] = mapped_column(Text, default=None)
    # Draft runs on this card so far; at MAX_DRAFT_ATTEMPTS a failed draft is closed.
    attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), server_default=text("0")
    )
    calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
