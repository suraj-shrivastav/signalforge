"""Research packages: fetched sources and extracted claims for an accepted topic card."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from signalforge.db.base import Base, SchemaVersionMixin, TimestampsMixin, UUIDPrimaryKeyMixin


class ResearchPackageRow(Base, UUIDPrimaryKeyMixin, TimestampsMixin, SchemaVersionMixin):
    __tablename__ = "research_packages"
    __table_args__ = (
        UniqueConstraint("card_id", name="uq_research_packages_card_id"),
        CheckConstraint(
            "status IN ('researching', 'researched', 'needs_more_info', 'failed')",
            name="status_allowed",
        ),
    )

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic_cards.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(
        String(32), default="researching", server_default="researching"
    )
    documents: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    claims: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    gaps_and_disagreements: Mapped[str] = mapped_column(Text, default="", server_default="")
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), server_default=text("0")
    )
    calls: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
