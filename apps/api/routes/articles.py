"""Article drafts. Editor-only read; there is no public route until approval exists."""

from collections import Counter
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.deps import get_article_repository
from apps.api.routes.cards import require_editor_key
from apps.api.schemas import ArticleDraftOut, ArticleDraftSummaryOut
from signalforge.core.artifacts.article import ArticleBody
from signalforge.db.repositories.article import ArticleDraftRepository

router = APIRouter()


@router.get(
    "/editor/drafts",
    response_model=list[ArticleDraftSummaryOut],
    dependencies=[Depends(require_editor_key)],
)
def editor_drafts(
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ArticleDraftSummaryOut]:
    summaries = []
    for row, signal_title in repo.list_recent(limit):
        # A failed card stores {} rather than a body.
        claims = row.draft.get("claims", []) if row.draft else []
        summaries.append(
            ArticleDraftSummaryOut(
                card_id=row.card_id,
                status=cast(Any, row.status),
                template=cast(Any, row.template),
                title=row.draft.get("title", "") if row.draft else "",
                signal_title=signal_title,
                claim_counts=dict(Counter(str(c.get("status", "unverified")) for c in claims)),
                created_at=row.created_at,
            )
        )
    return summaries


@router.get(
    "/editor/drafts/{card_id}",
    response_model=ArticleDraftOut,
    dependencies=[Depends(require_editor_key)],
)
def editor_draft(
    card_id: UUID, repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)]
) -> ArticleDraftOut:
    row = repo.get(card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return ArticleDraftOut(
        card_id=row.card_id,
        status=cast(Any, row.status),
        template=cast(Any, row.template),
        # A failed card stores {} rather than a body.
        draft=ArticleBody.model_validate(row.draft) if row.draft else None,
        review_summary=row.review_summary,
        cost_usd=row.cost_usd,
        calls=row.calls,
        tokens=row.tokens,
        created_at=row.created_at,
    )
