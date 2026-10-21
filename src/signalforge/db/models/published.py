"""Published articles: an immutable snapshot of an approved draft, plus its SEO fields."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, TimestampsMixin, UUIDPrimaryKeyMixin


class PublishedArticleRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin):
    __tablename__ = "published_articles"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_published_articles_card_id"),
        UniqueConstraint("slug", name="uq_published_articles_slug"),
        CheckConstraint("status IN ('published', 'unpublished')", name="status_allowed"),
        Index("ix_published_articles_published_at", "published_at"),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic_cards.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="published", server_default="published")
    template: Mapped[str] = mapped_column(String(32))
    seo_title: Mapped[str] = mapped_column(Text)
    meta_description: Mapped[str] = mapped_column(Text)
    byline: Mapped[str] = mapped_column(String(120))
    process_note: Mapped[str] = mapped_column(Text)
    editor_analysis: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The approved ArticleBody at publish time. Later edits to the draft do not change it.
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
