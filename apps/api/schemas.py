from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from signalforge.db.models.signals import Signal


class SignalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source: str
    source_type: str
    canonical_url: str
    title: str
    published_at: datetime
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Signal) -> "SignalOut":
        return cls(
            id=row.id,
            source=row.source,
            source_type=row.source_type,
            canonical_url=row.canonical_url,
            title=row.title,
            published_at=row.published_at,
            summary=row.summary,
            metadata=row.metadata_,
        )


class SignalListOut(BaseModel):
    items: list[SignalOut]
    next_cursor: str | None
