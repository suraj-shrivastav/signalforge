from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from signalforge.core.artifacts.article import ArticleBody
from signalforge.core.reason_tags import REASON_TAGS
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.signals import Signal


class AssessmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_relevant: bool
    relevance_score: float
    category: str
    summary: str
    why_it_matters: str


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
    assessment: AssessmentOut | None = None

    @classmethod
    def from_row(cls, row: Signal, assessment: SignalAssessmentRow | None = None) -> "SignalOut":
        return cls(
            id=row.id,
            source=row.source,
            source_type=row.source_type,
            canonical_url=row.canonical_url,
            title=row.title,
            published_at=row.published_at,
            summary=row.summary,
            metadata=row.metadata_,
            assessment=AssessmentOut(
                is_relevant=assessment.is_relevant,
                relevance_score=assessment.relevance_score,
                category=assessment.category,
                summary=assessment.summary,
                why_it_matters=assessment.why_it_matters,
            )
            if assessment
            else None,
        )


class SignalListOut(BaseModel):
    items: list[SignalOut]
    next_cursor: str | None


class QueueSignalOut(BaseModel):
    id: UUID
    title: str
    source: str
    canonical_url: str


class CardOut(BaseModel):
    id: UUID
    schema_version: int
    what_happened: str
    why_it_matters: str
    novelty: float
    signal_strength: float
    coverage_gap: str
    suggested_angle: str
    format: str
    evergreen_score: float
    confidence: float
    risk_flags: list[str]
    prompt_version: str
    model: str
    signal: QueueSignalOut
    score: float
    wildcard: bool
    status: Literal["proposed", "snoozed"]
    created_at: datetime


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected", "snoozed"]
    reason_tags: list[str] = Field(default_factory=list, max_length=9)
    note: str = Field(default="", max_length=500)
    decision_ms: int | None = Field(default=None, ge=0, le=3_600_000)

    @field_validator("reason_tags")
    @classmethod
    def _known_unique(cls, tags: list[str]) -> list[str]:
        if any(tag not in REASON_TAGS for tag in tags):
            raise ValueError("unknown reason tag")
        if len(set(tags)) != len(tags):
            raise ValueError("duplicate reason tags")
        return tags


class DecisionOut(BaseModel):
    id: UUID
    card_id: UUID
    decision: Literal["accepted", "rejected", "snoozed"]
    reason_tags: list[str]
    note: str
    decision_ms: int | None
    decided_at: datetime


class ArticleDraftOut(BaseModel):
    """Editor-only view: every field, including the review summary and spend."""

    card_id: UUID
    status: Literal["drafting", "drafted", "needs_more_info", "failed"]
    template: Literal["news_brief", "explainer", "paper_breakdown", "comparison"]
    draft: ArticleBody | None
    review_summary: str
    failure_reason: str | None = None
    cost_usd: Decimal
    calls: int
    tokens: int
    created_at: datetime


class ArticleDraftSummaryOut(BaseModel):
    """Editor-only list row: enough to pick a draft to open."""

    card_id: UUID
    status: Literal["drafting", "drafted", "needs_more_info", "failed"]
    template: Literal["news_brief", "explainer", "paper_breakdown", "comparison"]
    title: str
    signal_title: str
    claim_counts: dict[str, int]
    created_at: datetime


class PublicSectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    paragraphs: list[str]


class PublicClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    status: str
    source_indices: list[int]


class PublicSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class PublicCoverOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str | None
    alt: str
    credit: str | None


class PublicArticleOut(BaseModel):
    """Reader-facing shape. An explicit allow-list, so a new editor-only field on the
    artifact never reaches a public response by default (2026-09-27 spec)."""

    model_config = ConfigDict(extra="forbid")

    title: str
    dek: str
    sections: list[PublicSectionOut]
    claims: list[PublicClaimOut]
    sources: list[PublicSourceOut]
    cover: PublicCoverOut

    @classmethod
    def from_body(cls, body: ArticleBody) -> "PublicArticleOut":
        return cls(
            title=body.title,
            dek=body.dek,
            sections=[
                PublicSectionOut(heading=s.heading, paragraphs=list(s.paragraphs))
                for s in body.sections
            ],
            claims=[
                PublicClaimOut(
                    text=c.text, status=c.status.value, source_indices=list(c.document_indices)
                )
                for c in body.claims
            ],
            sources=[PublicSourceOut(label=s.label, url=s.url) for s in body.sources],
            cover=PublicCoverOut(src=body.cover.src, alt=body.cover.alt, credit=body.cover.credit),
        )
