"""Endpoints for the automation agent: what needs doing, run a stage, review by policy.

All of them take the editor key or the agent key (X-Editor-Key). Everything the agent does
here is also written to the draft's review log with ``actor`` so a person can audit it.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api import agent_runs
from apps.api.deps import get_article_repository, get_published_repository, get_session
from apps.api.routes.articles import get_draft_row, publish_approved
from apps.api.routes.cards import require_editor_key
from apps.api.schemas import PublishedOut, PublishIn
from signalforge.auto_review import ReviewPolicy, decide
from signalforge.core.artifacts.article import ArticleBody, ArticleTemplate
from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.db.repositories.pipeline import PipelineRepository
from signalforge.db.repositories.published import PublishedArticleRepository
from signalforge.publish_pacing import next_publish_time

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_editor_key)])

Stage = Literal["tick", "assess", "cards", "research", "draft", "revise"]


class PipelineCardOut(BaseModel):
    card_id: UUID
    title: str
    stage: str
    next_action: str
    slug: str | None


class PipelineOut(BaseModel):
    counts: dict[str, int]
    cards: list[PipelineCardOut]


class RunOut(BaseModel):
    started: bool
    stage: str


class AutoReviewOut(BaseModel):
    action: Literal["approve", "revise", "reject"]
    reasons: list[str]
    deleted_sentences: int
    published: PublishedOut | None = None
    # With publish=true: approved but held for the publish pace; next_publish_at is the
    # earliest time POST /agent/publish-next will publish it.
    queued: bool = False
    next_publish_at: datetime | None = None


class PublishNextOut(BaseModel):
    published: PublishedOut | None
    waiting: int
    next_publish_at: datetime | None


def _cards(session: Session, limit: int) -> list[PipelineCardOut]:
    return [
        PipelineCardOut(
            card_id=c.card_id, title=c.title, stage=c.stage, next_action=c.next_action, slug=c.slug
        )
        for c in PipelineRepository(session).accepted_cards(limit)
    ]


@router.get("/pipeline", response_model=PipelineOut)
def pipeline(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PipelineOut:
    """Every recently accepted card with its stage and the next action."""
    cards = _cards(session, limit)
    return PipelineOut(counts=dict(Counter(c.stage for c in cards)), cards=cards)


@router.get("/work", response_model=PipelineOut)
def work(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PipelineOut:
    """Only the cards that need a call from the agent; counts are by next_action.

    Pick new topics with GET /cards/queue and POST /cards/{id}/decision.
    """
    cards = [c for c in _cards(session, limit) if c.next_action not in ("none", "wait")]
    return PipelineOut(counts=dict(Counter(c.next_action for c in cards)), cards=cards)


# Research is the costly stage: one card per run unless the caller asks for more. The best
# accepted card (highest score) goes first.
_DEFAULT_LIMIT = {"research": 1}


@router.post("/run/{stage}", response_model=RunOut, status_code=202)
def run_stage(
    stage: Stage,
    request: Request,
    limit: Annotated[int | None, Query(ge=1, le=50)] = None,
    retry_failed: bool = False,
) -> RunOut:
    """Start a stage in the background. One run at a time: 409 while another is going.

    ``limit`` is how many cards to take; research defaults to 1 (the best waiting card),
    every other stage to 10.
    """
    count = limit if limit is not None else _DEFAULT_LIMIT.get(stage, 10)
    if not agent_runs.start(stage, request.app.state.settings, count, retry_failed):
        raise HTTPException(status_code=409, detail="Another run is still going")
    return RunOut(started=True, stage=stage)


@router.get("/runs")
def runs() -> dict[str, Any]:
    """The run in progress (if any) and how the last run of each stage ended."""
    return agent_runs.status()


@router.post("/drafts/{card_id}/auto-review", response_model=AutoReviewOut)
def auto_review(
    card_id: UUID,
    request: Request,
    background: BackgroundTasks,
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
    publish: bool = False,
    force: bool = False,
) -> AutoReviewOut:
    """Review a pending draft by the configured rules.

    Approve: flagged sentences are deleted, the draft is approved and (with publish=true)
    published, on the publish pace unless ``force=true`` (a hot topic the owner asked for).
    Revise: it goes back for a redraft with the reasons as the note (run stage
    'revise'). Reject: it already had the maximum redrafts. Every step is logged.
    """
    settings = request.app.state.settings
    row = get_draft_row(repo, card_id)
    if row.status != "drafted" or not row.draft:
        raise HTTPException(status_code=409, detail="Only a drafted article can be reviewed")
    if row.review_status != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {row.review_status}")
    policy = ReviewPolicy(
        min_words=settings.auto_review_min_words,
        min_claims=settings.auto_review_min_claims,
        max_flagged_share=settings.auto_review_max_flagged_share,
        max_redrafts=settings.auto_review_max_redrafts,
    )
    redrafts = sum(1 for e in row.review_log if e.get("type") == "redraft")
    decision = decide(
        ArticleBody.model_validate(row.draft), ArticleTemplate(row.template), redrafts, policy
    )
    actor = getattr(request.state, "actor", "agent")
    note = "; ".join(decision.reasons)
    result = AutoReviewOut(
        action=decision.action,
        reasons=list(decision.reasons),
        deleted_sentences=len(decision.deleted),
    )
    if decision.action == "approve":
        if decision.deleted:
            repo.save_edit(
                row,
                decision.body,
                {
                    "type": "auto_edit",
                    "actor": actor,
                    "deleted": [f.text for f in decision.deleted],
                    "new_dek": decision.new_dek,
                },
            )
        repo.save_review(
            row,
            "approved",
            "approved by policy",
            {"type": "review", "decision": "approved", "actor": actor},
        )
        if publish:
            slot = _next_slot(settings, published)
            if force or slot <= datetime.now(UTC):
                result.published = publish_approved(
                    card_id, PublishIn(), settings, background, repo, published
                )
            else:
                result.queued, result.next_publish_at = True, slot
        return result
    final = "revise" if decision.action == "revise" else "rejected"
    repo.save_review(
        row,
        final,
        note,
        {"type": "review", "decision": final, "actor": actor, "reasons": list(decision.reasons)},
    )
    return result


def _next_slot(settings: Any, published: PublishedArticleRepository) -> datetime:
    now = datetime.now(UTC)
    return next_publish_time(
        published.published_times_since(now - timedelta(days=1)),
        now,
        min_gap=timedelta(minutes=settings.publish_min_gap_minutes),
        daily_cap=settings.publish_daily_cap,
    )


@router.post("/publish-next", response_model=PublishNextOut)
def publish_next(
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
    force: bool = False,
    card_id: UUID | None = None,
) -> PublishNextOut:
    """Publish the longest-waiting approved draft if the publish pace allows it.

    Call this on a schedule (every 15 to 30 minutes). Approved drafts wait until a slot opens
    (PUBLISH_MIN_GAP_MINUTES since the last publish, PUBLISH_DAILY_CAP per 24 hours), so
    articles go out spread over the day. ``next_publish_at`` says when to expect the next.

    The pace is a target, not a limit: ``force=true`` publishes now whatever the pace says, for
    a hot topic the owner asked for. ``card_id`` picks that waiting draft instead of the oldest.
    """
    settings = request.app.state.settings
    waiting = [c for c in _cards(session, 200) if c.next_action == "publish"]
    if card_id is not None:
        chosen = next((c for c in waiting if c.card_id == card_id), None)
        if chosen is None:
            raise HTTPException(status_code=404, detail="That draft is not waiting to publish")
    else:
        chosen = waiting[-1] if waiting else None  # the list is newest first
    slot = _next_slot(settings, published)
    if chosen is None or (not force and slot > datetime.now(UTC)):
        return PublishNextOut(
            published=None, waiting=len(waiting), next_publish_at=slot if waiting else None
        )
    result = publish_approved(chosen.card_id, PublishIn(), settings, background, repo, published)
    return PublishNextOut(published=result, waiting=len(waiting) - 1, next_publish_at=None)
