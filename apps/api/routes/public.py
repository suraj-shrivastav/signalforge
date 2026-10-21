"""Public, read-only article routes. No key: these serve what the editor chose to publish."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.deps import get_published_repository
from apps.api.schemas import PublicArticleOut, PublicArticleSummaryOut
from signalforge.db.repositories.published import PublishedArticleRepository

router = APIRouter()


@router.get("/articles", response_model=list[PublicArticleSummaryOut])
def public_articles(
    repo: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PublicArticleSummaryOut]:
    return [PublicArticleSummaryOut.from_row(row) for row in repo.list_public(limit)]


@router.get("/articles/{slug}", response_model=PublicArticleOut)
def public_article(
    slug: str, repo: Annotated[PublishedArticleRepository, Depends(get_published_repository)]
) -> PublicArticleOut:
    row = repo.get_public(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return PublicArticleOut.from_row(row)
