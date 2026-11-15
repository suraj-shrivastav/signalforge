"""add pipeline controls (kill switch and slot lease)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = op.create_table(
        "pipeline_controls",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("paused_reason", sa.Text(), nullable=True),
        sa.Column("paused_by", sa.String(length=32), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slot", sa.String(length=16), nullable=True),
        sa.Column("slot_status", sa.String(length=16), nullable=True),
        sa.Column("slot_failures", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("slot_lease_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("id = 1", name=op.f("ck_pipeline_controls_singleton")),
        sa.CheckConstraint(
            "slot_status IS NULL OR slot_status IN ('running', 'done', 'failed')",
            name=op.f("ck_pipeline_controls_slot_status_allowed"),
        ),
        sa.CheckConstraint(
            "slot_failures >= 0", name=op.f("ck_pipeline_controls_slot_failures_non_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_controls")),
    )
    # Seed the singleton so readers never race to create it.
    op.bulk_insert(table, [{"id": 1, "paused": False, "slot_failures": 0}])


def downgrade() -> None:
    op.drop_table("pipeline_controls")
