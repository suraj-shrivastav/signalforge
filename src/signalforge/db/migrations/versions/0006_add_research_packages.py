"""add research packages

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "research_packages",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="researching", nullable=False),
        sa.Column(
            "documents",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("gaps_and_disagreements", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=12, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("calls", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_common_columns(),
        sa.CheckConstraint(
            "status IN ('researching', 'researched', 'needs_more_info', 'failed')",
            name=op.f("ck_research_packages_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["topic_cards.id"],
            name="fk_research_packages_card_id_topic_cards",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_packages"),
        sa.UniqueConstraint("card_id", name="uq_research_packages_card_id"),
    )


def downgrade() -> None:
    op.drop_table("research_packages")
