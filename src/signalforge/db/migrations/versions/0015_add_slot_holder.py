"""add pipeline controls slot holder

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pipeline_controls",
        sa.Column("slot_holder", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_controls", "slot_holder")
