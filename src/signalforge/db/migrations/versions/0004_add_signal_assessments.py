"""add signal assessments

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_assessments",
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["llm_calls.id"],
            name="fk_signal_assessments_llm_call_id_llm_calls",
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name="fk_signal_assessments_signal_id_signals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"],
            ["stage_runs.id"],
            name="fk_signal_assessments_stage_run_id_stage_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_signal_assessments"),
        sa.UniqueConstraint(
            "signal_id", "prompt_version", name="uq_signal_assessments_signal_prompt"
        ),
    )
    op.create_index(
        "ix_signal_assessments_is_relevant_relevance_score",
        "signal_assessments",
        ["is_relevant", "relevance_score"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_assessments_is_relevant_relevance_score", table_name="signal_assessments"
    )
    op.drop_table("signal_assessments")
