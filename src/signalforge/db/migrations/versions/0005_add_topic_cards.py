"""add topic cards and editor decisions

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
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
        "topic_cards",
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("stage_run_id", sa.Uuid(), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("what_happened", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("novelty", sa.Float(), nullable=False),
        sa.Column("signal_strength", sa.Float(), nullable=False),
        sa.Column("coverage_gap", sa.Text(), nullable=False),
        sa.Column("suggested_angle", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("evergreen_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("risk_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("wildcard", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        *_common_columns(),
        sa.ForeignKeyConstraint(
            ["llm_call_id"], ["llm_calls.id"], name="fk_topic_cards_llm_call_id_llm_calls"
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name="fk_topic_cards_signal_id_signals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"], ["stage_runs.id"], name="fk_topic_cards_stage_run_id_stage_runs"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_topic_cards"),
        sa.UniqueConstraint("signal_id", "prompt_version", name="uq_topic_cards_signal_prompt"),
    )
    op.create_index("ix_topic_cards_score", "topic_cards", [sa.text("score DESC")])
    op.create_table(
        "editor_decisions",
        sa.Column("topic_card_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column(
            "reason_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("decision_ms", sa.Integer(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_common_columns(),
        sa.CheckConstraint(
            "decision IN ('accepted', 'rejected', 'snoozed')",
            name=op.f("ck_editor_decisions_decision_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["topic_card_id"],
            ["topic_cards.id"],
            name="fk_editor_decisions_topic_card_id_topic_cards",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_editor_decisions"),
    )
    op.create_index(
        "ix_editor_decisions_topic_card_id_decided_at",
        "editor_decisions",
        ["topic_card_id", sa.text("decided_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_editor_decisions_topic_card_id_decided_at", table_name="editor_decisions")
    op.drop_table("editor_decisions")
    op.drop_index("ix_topic_cards_score", table_name="topic_cards")
    op.drop_table("topic_cards")
