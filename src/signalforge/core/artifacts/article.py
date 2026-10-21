"""ArticleDraft: a templated draft with per-claim status for one researched card (FR-07/FR-08)."""

from enum import StrEnum
from typing import Annotated, ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from signalforge.core.artifacts.base import Artifact
from signalforge.core.artifacts.research import ClaimStatus


class DraftStatus(StrEnum):
    """Mirrors the ``article_drafts.status`` check constraint."""

    DRAFTING = "drafting"
    DRAFTED = "drafted"
    NEEDS_MORE_INFO = "needs_more_info"
    FAILED = "failed"


class ArticleTemplate(StrEnum):
    """The four V1 templates; mirrors the ``article_drafts.template`` check constraint."""

    NEWS_BRIEF = "news_brief"
    EXPLAINER = "explainer"
    PAPER_BREAKDOWN = "paper_breakdown"
    COMPARISON = "comparison"


class FlagKind(StrEnum):
    """Why a sentence needs the editor's attention."""

    UNCITED = "uncited"
    NUMBER = "number"
    UNSUPPORTED = "unsupported"


class ArticleFlag(BaseModel):
    """One sentence the checks could not ground. ``section`` and ``paragraph`` locate it;
    -1 for both means the dek."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section: int = Field(ge=-1)
    paragraph: int = Field(ge=-1)
    text: str = Field(min_length=1)
    kind: FlagKind
    detail: str = ""


class ArticleSection(BaseModel):
    """One titled section; same shape the web draft preview renders."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    heading: str = Field(min_length=1)
    paragraphs: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    # Per paragraph, indices into ``ArticleBody.claims`` that its sentences rest on.
    # Empty on drafts written before sentence-level grounding (schema v1).
    citations: tuple[tuple[Annotated[int, Field(ge=0)], ...], ...] = ()

    @model_validator(mode="after")
    def _citations_align(self) -> Self:
        if self.citations and len(self.citations) != len(self.paragraphs):
            raise ValueError("citations must have one entry per paragraph")
        return self


class ArticleClaim(BaseModel):
    """One draft claim, citing documents by their index in ``ResearchPackage.documents``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    document_indices: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)
    status: ClaimStatus = ClaimStatus.UNVERIFIED


class ArticleSource(BaseModel):
    """One reader-facing source, listed once at article level rather than per claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class ArticleCover(BaseModel):
    """Cover slot; without ``src`` the reader site renders a deterministic fallback."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    src: str | None = None
    alt: str = Field(min_length=1)
    credit: str | None = None


class ArticleBody(BaseModel):
    """The structured shape every template outputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    dek: str = Field(min_length=1)
    sections: tuple[ArticleSection, ...] = Field(min_length=1)
    claims: tuple[ArticleClaim, ...] = ()
    sources: tuple[ArticleSource, ...] = ()
    cover: ArticleCover
    # Sentences the checks could not ground. Empty on drafts written before flagging.
    flags: tuple[ArticleFlag, ...] = ()


class ArticleDraft(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 2

    card_id: UUID
    status: DraftStatus = DraftStatus.DRAFTING
    template: ArticleTemplate
    draft: ArticleBody | None = Field(
        default=None, description="None when the card failed before a draft existed."
    )
    review_summary: str = ""

    @model_validator(mode="after")
    def _drafted_has_body(self) -> Self:
        if self.status is DraftStatus.DRAFTED and self.draft is None:
            raise ValueError("a drafted ArticleDraft must carry a draft body")
        return self
