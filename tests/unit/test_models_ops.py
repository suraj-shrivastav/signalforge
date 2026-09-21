"""Schema-level guarantees for the ops tables. Asserted on metadata, so no database."""

from decimal import Decimal
from typing import cast

import sqlalchemy as sa

from signalforge.db.base import Base
from signalforge.db.models import LLMCall, StageRun, StageRunStatus

# __table__ is typed as FromClause; these are Tables and the tests need Table APIs.
STAGE_RUNS = cast(sa.Table, StageRun.__table__)
LLM_CALLS = cast(sa.Table, LLMCall.__table__)


def named_objects(table: sa.Table) -> set[str]:
    """Names of every constraint and index on a table."""
    constraints = {str(c.name) for c in table.constraints if c.name is not None}
    indexes = {str(i.name) for i in table.indexes if i.name is not None}
    return constraints | indexes


def test_idempotency_key_is_unique() -> None:
    """PRD §29: an identical key must return the cached result, not run twice."""
    unique = next(
        c
        for c in STAGE_RUNS.constraints
        if isinstance(c, sa.UniqueConstraint) and c.name == "uq_stage_runs_idempotency_key"
    )

    assert [col.name for col in unique.columns] == [
        "stage",
        "entity_id",
        "input_hash",
        "stage_config_hash",
    ]


def test_status_is_constrained_at_the_database_level() -> None:
    """A bare VARCHAR would let an invalid status insert cleanly (PRD §34)."""
    status = cast(sa.Enum, STAGE_RUNS.c.status.type)

    assert status.create_constraint is True
    assert status.native_enum is False


def test_status_stores_lowercase_values_not_member_names() -> None:
    status = cast(sa.Enum, STAGE_RUNS.c.status.type)

    assert set(status.enums) == {"running", "succeeded", "failed"}


def test_stage_run_status_has_no_job_states() -> None:
    """Job state belongs to the queue, not to stage runs (PRD §28)."""
    values = {member.value for member in StageRunStatus}

    assert values == {"running", "succeeded", "failed"}
    assert values.isdisjoint({"queued", "leased", "retrying", "dead_lettered"})


def test_retry_count_cannot_go_negative() -> None:
    assert "ck_stage_runs_retry_count_non_negative" in named_objects(STAGE_RUNS)


def test_cost_cannot_go_negative() -> None:
    assert "ck_llm_calls_cost_non_negative" in named_objects(LLM_CALLS)


def test_cost_is_exact_not_floating_point() -> None:
    """Costs are summed against a budget, so drift is not acceptable (PRD §12)."""
    cost = cast(sa.Numeric[Decimal], LLM_CALLS.c.cost_usd.type)

    assert cost.asdecimal is True
    assert LLMCall(cost_usd=Decimal("0.000001")).cost_usd == Decimal("0.000001")


def test_llm_calls_cascade_when_a_stage_run_is_deleted() -> None:
    foreign_key = next(iter(LLM_CALLS.c.stage_run_id.foreign_keys))

    assert foreign_key.column is STAGE_RUNS.c.id
    assert foreign_key.ondelete == "CASCADE"


def test_model_family_is_a_column_not_a_derived_value() -> None:
    """Verification requires writer family != judge family (PRD FR-08)."""
    assert "model_family" in LLM_CALLS.c
    assert LLM_CALLS.c.model_family.nullable is False


def test_both_tables_carry_uuid_keys_and_timestamps() -> None:
    for table in (STAGE_RUNS, LLM_CALLS):
        assert isinstance(table.c.id.type, sa.Uuid)
        assert table.c.id.primary_key
        for column in ("created_at", "updated_at"):
            assert cast(sa.DateTime, table.c[column].type).timezone is True


def test_entity_lookups_are_indexed() -> None:
    """The dashboard lists runs per entity; an unindexed scan would not hold up."""
    assert "ix_stage_runs_entity_id_stage" in named_objects(STAGE_RUNS)


def test_tables_are_registered_for_autogenerate() -> None:
    """If a model is not on the metadata, Alembic silently omits it."""
    assert {"stage_runs", "llm_calls"} <= set(Base.metadata.tables)
