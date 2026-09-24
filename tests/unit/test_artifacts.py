"""Artifact invariants. The digest feeds stage idempotency, so it is a critical path."""

from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import ValidationError

from signalforge.core.artifacts import Artifact


class Sample(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    title: str
    score: int = 0


class SampleV2(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 2

    title: str
    score: int = 0


class Other(Artifact):
    """Same payload shape as Sample, different type."""

    title: str
    score: int = 0


def test_identity_and_timestamp_are_generated() -> None:
    artifact = Sample(title="a")

    assert artifact.id is not None
    assert artifact.created_at.tzinfo is not None, "timestamps must be timezone-aware"


def test_schema_version_defaults_to_the_subclass_version() -> None:
    assert Sample(title="a").schema_version == 1
    assert SampleV2(title="a").schema_version == 2


def test_an_explicit_older_version_is_preserved() -> None:
    """Rows written before a bump must stay readable (PRD §32)."""
    loaded = SampleV2(title="a", schema_version=1)

    assert loaded.schema_version == 1
    assert loaded.is_current_schema is False
    assert SampleV2(title="a").is_current_schema is True


def test_artifacts_are_immutable() -> None:
    artifact = Sample(title="a")

    with pytest.raises(ValidationError):
        artifact.title = "b"


def test_unknown_fields_are_rejected() -> None:
    """Artifacts are built from LLM and plugin output; extra keys are failures."""
    with pytest.raises(ValidationError):
        Sample(title="a", hallucinated="nonsense")  # type: ignore[call-arg]


def test_digest_ignores_identity_and_bookkeeping() -> None:
    """Otherwise idempotency would never hit its cache (PRD §29)."""
    first = Sample(title="a", score=1)
    second = Sample(
        title="a",
        score=1,
        id=uuid4(),
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        produced_by=uuid4(),
    )

    assert first.canonical_digest() == second.canonical_digest()


def test_digest_changes_with_meaningful_content() -> None:
    assert Sample(title="a").canonical_digest() != Sample(title="b").canonical_digest()


def test_digest_changes_with_lineage() -> None:
    parent = Sample(title="parent")
    child = Sample(title="a").derive(parents=(parent,))

    assert child.canonical_digest() != Sample(title="a").canonical_digest()


def test_digest_is_type_scoped() -> None:
    """Identical payloads of different types must not collide."""
    assert Sample(title="a").canonical_digest() != Other(title="a").canonical_digest()


def test_digest_changes_with_schema_version() -> None:
    assert Sample(title="a").canonical_digest() != SampleV2(title="a").canonical_digest()


def test_digest_is_stable_across_field_ordering() -> None:
    assert (
        Sample(title="a", score=2).canonical_digest()
        == Sample(score=2, title="a").canonical_digest()
    )


def test_derive_records_lineage_without_mutating_the_original() -> None:
    parents = (Sample(title="p1"), Sample(title="p2"))
    run_id = uuid4()
    original = Sample(title="a")

    derived = original.derive(produced_by=run_id, parents=parents)

    assert derived.produced_by == run_id
    assert derived.parent_ids == (parents[0].id, parents[1].id)
    assert original.produced_by is None
    assert original.parent_ids == ()


def test_derive_keeps_existing_lineage_when_given_nothing() -> None:
    run_id = uuid4()
    artifact = Sample(title="a").derive(produced_by=run_id, parents=(Sample(title="p"),))

    unchanged = artifact.derive()

    assert unchanged.produced_by == run_id
    assert unchanged.parent_ids == artifact.parent_ids


def test_round_trip_through_json_preserves_the_digest() -> None:
    """Artifacts are stored as JSONB and reloaded; the digest must survive."""
    artifact = Sample(title="a", score=3).derive(parents=(Sample(title="p"),))

    reloaded = Sample.model_validate_json(artifact.model_dump_json())

    assert reloaded.canonical_digest() == artifact.canonical_digest()
    assert reloaded.id == artifact.id
