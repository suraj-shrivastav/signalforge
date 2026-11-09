from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from signalforge.core.artifacts.article import ArticleBody
from signalforge.core.reason_tags import REASON_TAGS
from signalforge.db.models.assessments import SignalAssessmentRow
from signalforge.db.models.signals import Signal
from signalforge.publishing import SLUG_PATTERN


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
    review_status: Literal["pending", "approved", "revise", "rejected"] = "pending"
    review_note: str = ""
    reviewed_at: datetime | None = None
    published_slug: str | None = None
    cost_usd: Decimal
    calls: int
    tokens: int
    created_at: datetime


class SentenceEditIn(BaseModel):
    """Replace (or delete, when ``replacement`` is null) one sentence of a draft."""

    model_config = ConfigDict(extra="forbid")

    section: int = Field(ge=-1)  # -1 is the dek
    paragraph: int = Field(ge=-1)
    text: str = Field(min_length=1, max_length=2000)
    replacement: str | None = Field(default=None, max_length=2000)


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "revise", "rejected"]
    note: str = Field(default="", max_length=2000)


class ArticleDraftSummaryOut(BaseModel):
    """Editor-only list row: enough to pick a draft to open."""

    card_id: UUID
    status: Literal["drafting", "drafted", "needs_more_info", "failed"]
    template: Literal["news_brief", "explainer", "paper_breakdown", "comparison"]
    title: str
    signal_title: str
    claim_counts: dict[str, int]
    flag_count: int = 0
    review_status: Literal["pending", "approved", "revise", "rejected"] = "pending"
    created_at: datetime


class PublicSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class PublicTableOut(BaseModel):
    """A source table, copied from the source page. ``source`` names where it came from."""

    model_config = ConfigDict(extra="forbid")

    caption: str
    header: list[str]
    rows: list[list[str]]
    source: PublicSourceOut | None = None


class PublicSectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    paragraphs: list[str]
    table: PublicTableOut | None = None


class PublicClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    status: str
    source_indices: list[int]


class PublicCoverOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str | None
    alt: str
    credit: str | None


class PublicFigureOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str
    alt: str
    caption: str


class ImageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    src: str = Field(min_length=1, max_length=500)
    alt: str = Field(min_length=1, max_length=300)
    caption: str = Field(default="", max_length=300)


class ImageUploadIn(BaseModel):
    """A rendered SVG for the API to store; the caption is shown under the inline figure."""

    model_config = ConfigDict(extra="forbid")

    svg: str = Field(min_length=1, max_length=400_000)
    alt: str = Field(min_length=1, max_length=300)
    caption: str = Field(default="", max_length=300)


class ImagesUploadIn(BaseModel):
    """Cover and figure SVGs together, so an article never ends up with only one of them."""

    model_config = ConfigDict(extra="forbid")

    cover: ImageUploadIn
    figure: ImageUploadIn


class ImagesIn(BaseModel):
    """Both images for one article. Either may be sent alone."""

    model_config = ConfigDict(extra="forbid")

    cover: ImageIn | None = None
    figure: ImageIn | None = None


def _public_section(section: Any, body: ArticleBody) -> PublicSectionOut:
    table = section.table
    source = None
    if table is not None and table.source_index < len(body.sources):
        found = body.sources[table.source_index]
        source = PublicSourceOut(label=found.label, url=found.url)
    return PublicSectionOut(
        heading=section.heading,
        paragraphs=list(section.paragraphs),
        table=PublicTableOut(
            caption=table.caption,
            header=list(table.header),
            rows=[list(row) for row in table.rows],
            source=source,
        )
        if table is not None
        else None,
    )


class PublicHeadlineOut(BaseModel):
    """The cover's verified number. ``claim_index`` stays server-side."""

    model_config = ConfigDict(extra="forbid")

    value: str
    unit: str
    direction: Literal["up", "down", "none"]
    takeaway: str


def _public_headline(body: ArticleBody) -> PublicHeadlineOut | None:
    h = body.headline
    if h is None:
        return None
    return PublicHeadlineOut(value=h.value, unit=h.unit, direction=h.direction, takeaway=h.takeaway)


class PublicArticleOut(BaseModel):
    """Reader-facing shape. An explicit allow-list, so a new editor-only field on the
    artifact never reaches a public response by default (2026-09-27 spec)."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    seo_title: str
    meta_description: str
    dek: str
    byline: str
    process_note: str
    editor_analysis: str
    published_at: datetime
    modified_at: datetime
    sections: list[PublicSectionOut]
    claims: list[PublicClaimOut]
    sources: list[PublicSourceOut]
    cover: PublicCoverOut
    figure: PublicFigureOut | None = None
    kind: str | None = None
    source_label: str = ""
    headline: PublicHeadlineOut | None = None

    @classmethod
    def from_row(cls, row: Any) -> "PublicArticleOut":
        body = ArticleBody.model_validate(row.body)
        return cls(
            slug=row.slug,
            title=body.title,
            seo_title=row.seo_title,
            meta_description=row.meta_description,
            dek=body.dek,
            byline=row.byline,
            process_note=row.process_note,
            editor_analysis=row.editor_analysis,
            published_at=row.published_at,
            modified_at=row.modified_at,
            sections=[_public_section(s, body) for s in body.sections],
            claims=[
                PublicClaimOut(
                    text=c.text, status=c.status.value, source_indices=list(c.document_indices)
                )
                for c in body.claims
            ],
            sources=[PublicSourceOut(label=s.label, url=s.url) for s in body.sources],
            cover=PublicCoverOut(src=body.cover.src, alt=body.cover.alt, credit=body.cover.credit),
            figure=PublicFigureOut(
                src=body.figure.src, alt=body.figure.alt, caption=body.figure.caption
            )
            if body.figure
            else None,
            kind=body.kind,
            source_label=body.source_label,
            headline=_public_headline(body),
        )


class PublicArticleSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    dek: str
    meta_description: str
    published_at: datetime
    modified_at: datetime
    cover: PublicCoverOut
    kind: str | None = None
    source_label: str = ""
    headline: PublicHeadlineOut | None = None

    @classmethod
    def from_row(cls, row: Any) -> "PublicArticleSummaryOut":
        body = ArticleBody.model_validate(row.body)
        return cls(
            slug=row.slug,
            title=body.title,
            dek=body.dek,
            meta_description=row.meta_description,
            published_at=row.published_at,
            modified_at=row.modified_at,
            cover=PublicCoverOut(src=body.cover.src, alt=body.cover.alt, credit=body.cover.credit),
            kind=body.kind,
            source_label=body.source_label,
            headline=_public_headline(body),
        )


class PublishIn(BaseModel):
    """Editor's publish request. Every field is optional: defaults come from the article."""

    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, max_length=120, pattern=SLUG_PATTERN)
    seo_title: str | None = Field(default=None, min_length=1, max_length=160)
    meta_description: str | None = Field(default=None, min_length=1, max_length=320)
    editor_analysis: str = Field(default="", max_length=4000)


class PublishedOut(BaseModel):
    slug: str
    status: Literal["published", "unpublished"]
    published_at: datetime
    modified_at: datetime
