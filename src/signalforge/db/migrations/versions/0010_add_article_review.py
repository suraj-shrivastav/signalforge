"""add article draft review state

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article_drafts",
        sa.Column("review_status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column(
        "article_drafts", sa.Column("review_note", sa.Text(), server_default="", nullable=False)
    )
    op.add_column(
        "article_drafts", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "article_drafts",
        sa.Column(
            "review_log",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_article_drafts_review_status_allowed"),
        "article_drafts",
        "review_status IN ('pending', 'approved', 'revise', 'rejected')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_article_drafts_review_status_allowed"), "article_drafts")
    op.drop_column("article_drafts", "review_log")
    op.drop_column("article_drafts", "reviewed_at")
    op.drop_column("article_drafts", "review_note")
    op.drop_column("article_drafts", "review_status")
