"""Read-only diagnostics for the owner's Telegram control: why is a card where it is, and
what is waiting to publish. Nothing here writes, runs a stage or calls an LLM.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from apps.api.deps import get_controls_repository, get_pipeline_repository, get_published_repository
from apps.api.routes.cards import require_editor_key
from signalforge.control_policy import is_paused
from signalforge.db.repositories.controls import ControlsRepository
from signalforge.db.repositories.pipeline import PipelineRepository
from signalforge.db.repositories.published import PublishedArticleRepository
from signalforge.explain import CardFacts, review_reasons, summarize
from signalforge.pipeline_state import MAX_DRAFT_ATTEMPTS, MAX_RESEARCH_ATTEMPTS, redrafts_used
from signalforge.publish_pacing import schedule

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_editor_key)])

Controls = Annotated[ControlsRepository, Depends(get_controls_repository)]
Pipeline = Annotated[PipelineRepository, Depends(get_pipeline_repository)]
Published = Annotated[PublishedArticleRepository, Depends(get_published_repository)]

_RECENT = 200
_MAX_MATCHES = 5


class PartOut(BaseModel):
    status: str | None
    attempts: int
    max_attempts: int
    failure_reason: str | None


class ReviewOut(BaseModel):
    review_status: str | None
    last_reasons: list[str]
    redrafts_used: int
    max_redrafts: int


class PublishedOut(BaseModel):
    status: str | None
    slug: str | None
    url: str | None


class ExplanationOut(BaseModel):
    card_id: UUID
    title: str
    stage: str
    next_action: str
    research: PartOut
    draft: PartOut
    review: ReviewOut
    published: PublishedOut
    paused: bool
    paused_reason: str | None
    queue_position: int | None
    next_publish_at: datetime | None
    summary: str


class ExplainSearchOut(BaseModel):
    query: str
    matches: list[ExplanationOut]


class QueueItemOut(BaseModel):
    position: int
    card_id: UUID
    title: str
    estimated_publish_at: datetime


class PublishQueueOut(BaseModel):
    paused: bool
    paused_reason: str | None
    min_gap_minutes: int
    daily_cap: int
    waiting: int
    items: list[QueueItemOut]


class _Context:
    """What every explanation shares: settings, the pause state and the publish queue."""

    def __init__(
        self,
        request: Request,
        pipeline: PipelineRepository,
        controls: Controls,
        published: Published,
    ) -> None:
        self.settings = request.app.state.settings
        self.pipeline = pipeline
        self.now = datetime.now(UTC)
        row = controls.get()
        self.paused = is_paused(row, self.now)
        self.paused_reason: str | None = (
            (row.paused_reason or "no reason given") if self.paused else None
        )
        self.queue = self._queue(published)

    def _queue(self, published: Published) -> list[tuple[CardFacts, datetime]]:
        waiting = [
            f
            for f in self.pipeline.facts(_RECENT)
            if self.pipeline.state_of(f, self.settings.auto_review_max_redrafts).next_action
            == "publish"
        ]
        waiting.sort(key=lambda f: f.created_at)  # oldest first: the order publish-next uses
        times = schedule(
            published.published_times_since(self.now - timedelta(days=1)),
            len(waiting),
            self.now,
            min_gap=timedelta(minutes=self.settings.publish_min_gap_minutes),
            daily_cap=self.settings.publish_daily_cap,
        )
        return list(zip(waiting, times, strict=True))

    def explain(self, f: CardFacts) -> ExplanationOut:
        max_redrafts = self.settings.auto_review_max_redrafts
        state = self.pipeline.state_of(f, max_redrafts)
        used = redrafts_used(f.review_log)
        position: int | None = None
        at: datetime | None = None
        for i, (item, when) in enumerate(self.queue, start=1):
            if item.card_id == f.card_id:
                position, at = i, when
        base = self.settings.site_url.rstrip("/")
        url = (
            f"{base}/articles/{f.slug}"
            if base and f.slug and f.published_status == "published"
            else None
        )
        return ExplanationOut(
            card_id=f.card_id,
            title=f.title,
            stage=state.stage,
            next_action=state.next_action,
            research=PartOut(
                status=f.research_status, attempts=f.research_attempts,
                max_attempts=MAX_RESEARCH_ATTEMPTS, failure_reason=f.research_failure,
            ),
            draft=PartOut(
                status=f.draft_status, attempts=f.draft_attempts,
                max_attempts=MAX_DRAFT_ATTEMPTS, failure_reason=f.draft_failure,
            ),
            review=ReviewOut(
                review_status=f.review_status, last_reasons=review_reasons(f.review_log),
                redrafts_used=used, max_redrafts=max_redrafts,
            ),
            published=PublishedOut(status=f.published_status, slug=f.slug, url=url),
            paused=self.paused,
            paused_reason=self.paused_reason,
            queue_position=position,
            next_publish_at=at,
            summary=summarize(
                f, state, paused_reason=self.paused_reason, max_redrafts=max_redrafts,
                redrafts=used, queue_position=position, next_publish_at=at,
            ),
        )  # fmt: skip


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1}


@router.get("/cards/explain", response_model=ExplainSearchOut)
def explain_search(
    request: Request,
    pipeline: Pipeline,
    controls: Controls,
    published: Published,
    q: Annotated[str, Query(min_length=2, max_length=200)],
) -> ExplainSearchOut:
    """The best matches (at most 5) among recent accepted cards and published slugs for title
    words or a slug, each with its explanation."""
    want = _tokens(q)
    scored: list[tuple[float, CardFacts]] = []
    for f in pipeline.facts(_RECENT):
        have = _tokens(f"{f.title} {f.slug or ''}")
        hit = len(want & have) / len(want) if want else 0.0
        if f.slug and f.slug == q.strip():
            hit = 2.0
        if hit >= 0.5:
            scored.append((hit, f))
    scored.sort(key=lambda s: (-s[0], -s[1].created_at.timestamp()))
    matched = [f for _, f in scored[:_MAX_MATCHES]]
    if not matched:  # a published slug older than the recent window
        row = published.get_by_slug(q.strip())
        if row is not None:
            matched = pipeline.facts(1, accepted_only=False, card_id=row.card_id)
    ctx = _Context(request, pipeline, controls, published)
    return ExplainSearchOut(query=q, matches=[ctx.explain(f) for f in matched])


@router.get("/cards/{card_id}/explain", response_model=ExplanationOut)
def explain_card(
    card_id: UUID, request: Request, pipeline: Pipeline, controls: Controls, published: Published
) -> ExplanationOut:
    """Where one card is, why, and what happens next, in structured facts plus a sentence."""
    found = pipeline.facts(1, accepted_only=False, card_id=card_id)
    if not found:
        raise HTTPException(status_code=404, detail="Card not found")
    return _Context(request, pipeline, controls, published).explain(found[0])


@router.get("/publish-queue", response_model=PublishQueueOut)
def publish_queue(
    request: Request, pipeline: Pipeline, controls: Controls, published: Published
) -> PublishQueueOut:
    """Approved drafts waiting to publish, oldest first, with the estimated publish time of
    each under the pace (gap and daily cap). Estimates only; while paused nothing publishes."""
    ctx = _Context(request, pipeline, controls, published)
    s: Any = ctx.settings
    return PublishQueueOut(
        paused=ctx.paused,
        paused_reason=ctx.paused_reason,
        min_gap_minutes=s.publish_min_gap_minutes,
        daily_cap=s.publish_daily_cap,
        waiting=len(ctx.queue),
        items=[
            QueueItemOut(position=i, card_id=f.card_id, title=f.title, estimated_publish_at=at)
            for i, (f, at) in enumerate(ctx.queue, start=1)
        ],
    )
