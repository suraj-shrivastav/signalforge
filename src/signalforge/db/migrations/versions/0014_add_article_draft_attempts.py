"""add article draft attempts

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article_drafts",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("article_drafts", "attempts")
