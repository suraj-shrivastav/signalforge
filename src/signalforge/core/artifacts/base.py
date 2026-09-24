"""The base every typed, versioned artifact inherits from.

Each pipeline stage reads one artifact and writes another (PRD §33). Artifacts
carry the lineage needed to answer "why was this article published?" and "what
evidence produced this sentence?", so provenance is a property of the data rather
than something stages remember to log.

Two rules are enforced here rather than per-subclass:

- **Immutable.** An artifact is a record of what a stage produced. Mutating one
  after the fact would silently invalidate any digest already derived from it.
- **Closed to unknown fields.** Artifacts are built from LLM and plugin output,
  so an unexpected key is a validation failure, never something to absorb.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, ClassVar, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Excluded from the digest: identity and bookkeeping, not meaning. Two artifacts
# describing the same thing must hash equally even though they were produced by
# different runs at different times, otherwise stage idempotency (PRD §29) would
# never hit its cache.
VOLATILE_FIELDS: frozenset[str] = frozenset({"id", "created_at", "produced_by"})


class Artifact(BaseModel):
    """Base for all artifacts. Subclasses bump ``SCHEMA_VERSION`` on any change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    id: UUID = Field(default_factory=uuid4)
    schema_version: int = Field(default=0, ge=1, validate_default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    produced_by: UUID | None = Field(
        default=None, description="stage_run that produced this artifact"
    )
    parent_ids: tuple[UUID, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _stamp_schema_version(cls, data: Any) -> Any:
        """Default to the subclass's version, but keep an explicit one when reloading.

        Historical rows carry the version they were written with, so old runs stay
        readable after a schema bump (PRD §32).
        """
        if isinstance(data, dict) and not data.get("schema_version"):
            return {**data, "schema_version": cls.SCHEMA_VERSION}
        return data

    @property
    def is_current_schema(self) -> bool:
        """False for an artifact loaded from an older schema version."""
        return self.schema_version == self.SCHEMA_VERSION

    def canonical_digest(self) -> str:
        """Stable hash of this artifact's meaning, used as a stage ``input_hash``.

        Excludes :data:`VOLATILE_FIELDS` and includes the class name, so two
        different artifact types holding identical payloads do not collide.
        """
        payload = self.model_dump(mode="json", exclude=set(VOLATILE_FIELDS))
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(f"{type(self).__name__}:{encoded}".encode()).hexdigest()

    def derive(
        self, *, produced_by: UUID | None = None, parents: "tuple[Artifact, ...]" = ()
    ) -> Self:
        """Return a copy stamped with its lineage. The original is left untouched."""
        return self.model_copy(
            update={
                "produced_by": produced_by if produced_by is not None else self.produced_by,
                "parent_ids": tuple(parent.id for parent in parents) or self.parent_ids,
            }
        )
