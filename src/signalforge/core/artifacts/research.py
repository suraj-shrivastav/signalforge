"""ResearchPackage: fetched sources and extracted claims for one accepted topic card (FR-06)."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from signalforge.core.artifacts.base import Artifact


class ResearchStatus(StrEnum):
    """Mirrors the ``research_packages.status`` check constraint."""

    RESEARCHING = "researching"
    RESEARCHED = "researched"
    NEEDS_MORE_INFO = "needs_more_info"
    FAILED = "failed"


class ClaimStatus(StrEnum):
    """The product's single claim-status enum."""

    VERIFIED = "verified"
    SUPPORTED = "supported"
    UNCERTAIN = "uncertain"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


class ResearchDocument(BaseModel):
    """One fetched source, nested inside a ``ResearchPackage``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    is_primary: bool
    raw_text_ref: str = Field(
        min_length=1,
        description=(
            "Opaque deterministic id for the fetched text. Raw text is not persisted in V1 "
            "and no store resolves this ref yet."
        ),
    )
    fetched_at: datetime


class ResearchClaim(BaseModel):
    """One extracted claim, citing documents by their index in ``ResearchPackage.documents``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    document_indices: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)
    status: ClaimStatus = ClaimStatus.UNVERIFIED


class ResearchPackage(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    card_id: UUID
    status: ResearchStatus = ResearchStatus.RESEARCHING
    documents: tuple[ResearchDocument, ...] = ()
    claims: tuple[ResearchClaim, ...] = ()
    gaps_and_disagreements: str = ""
