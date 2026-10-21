"""add published articles

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "published_articles",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="published", nullable=False),
        sa.Column("template", sa.String(length=32), nullable=False),
        sa.Column("seo_title", sa.Text(), nullable=False),
        sa.Column("meta_description", sa.Text(), nullable=False),
        sa.Column("byline", sa.String(length=120), nullable=False),
        sa.Column("process_note", sa.Text(), nullable=False),
        sa.Column("editor_analysis", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "status IN ('published', 'unpublished')",
            name=op.f("ck_published_articles_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["card_id"],
            ["topic_cards.id"],
            name="fk_published_articles_card_id_topic_cards",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_published_articles"),
        sa.UniqueConstraint("card_id", name="uq_published_articles_card_id"),
        sa.UniqueConstraint("slug", name="uq_published_articles_slug"),
    )
    op.create_index("ix_published_articles_published_at", "published_articles", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_published_articles_published_at", table_name="published_articles")
    op.drop_table("published_articles")
