"""Article drafts. Editor-only read; there is no public route until approval exists."""

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import get_article_repository
from apps.api.routes.cards import require_editor_key
from apps.api.schemas import ArticleDraftOut
from signalforge.core.artifacts.article import ArticleBody
from signalforge.db.repositories.article import ArticleDraftRepository

router = APIRouter()


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
