"""RawSignal: what a source plugin emits, before any judgement is applied (PRD §33)."""

from datetime import datetime
from typing import Any, ClassVar, Self

from pydantic import Field, field_validator, model_validator

from signalforge.core.artifacts.base import Artifact
from signalforge.core.canonical import canonical_url, content_hash


class RawSignal(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    source: str = Field(min_length=1, max_length=64)
    # ponytail: free text for now, becomes an enum when a second source type exists.
    source_type: str = Field(min_length=1, max_length=32)
    canonical_url: str
    title: str = Field(min_length=1)
    published_at: datetime
    summary: str = ""
    entities: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("title", "summary", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("canonical_url")
    @classmethod
    def _canonicalise(cls, value: str) -> str:
        return canonical_url(value)

    @field_validator("published_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _fill_content_hash(self) -> Self:
        if not self.content_hash:
            # Frozen model: object.__setattr__ is the sanctioned way to finish construction.
            object.__setattr__(self, "content_hash", content_hash(self.title, self.summary))
        return self
