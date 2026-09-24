"""add stage_runs and llm_calls

Ops tables from PRD §34. stage_runs carries the idempotency key (PRD §29) and
llm_calls hangs off it so cost rolls up per stage and per entity.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21 14:18:05.335664
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stage_runs",
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("stage_config_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "succeeded",
                "failed",
                name="stage_run_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("output_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("output_schema_version", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("retry_count >= 0", name=op.f("ck_stage_runs_retry_count_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_runs")),
        sa.UniqueConstraint(
            "stage",
            "entity_id",
            "input_hash",
            "stage_config_hash",
            name="uq_stage_runs_idempotency_key",
        ),
    )
    op.create_index(
        "ix_stage_runs_entity_id_stage", "stage_runs", ["entity_id", "stage"], unique=False
    )
    op.create_table(
        "llm_calls",
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.CheckConstraint("cost_usd >= 0", name=op.f("ck_llm_calls_cost_non_negative")),
        sa.ForeignKeyConstraint(
            ["stage_run_id"],
            ["stage_runs.id"],
            name=op.f("fk_llm_calls_stage_run_id_stage_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index("ix_llm_calls_role_model", "llm_calls", ["role", "model"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_calls_role_model", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index("ix_stage_runs_entity_id_stage", table_name="stage_runs")
    op.drop_table("stage_runs")
