"""Article drafts. Editor-only read; there is no public route until approval exists."""

from collections import Counter
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.deps import get_article_repository
from apps.api.routes.cards import require_editor_key
from apps.api.schemas import ArticleDraftOut, ArticleDraftSummaryOut, ReviewIn, SentenceEditIn
from signalforge.core.artifacts.article import ArticleBody
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.stages.draft_review import apply_sentence_edit

router = APIRouter()

# Decisions the editor cannot take back through this API.
_FINAL = frozenset({"approved", "rejected"})


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
                flag_count=len(row.draft.get("flags", [])) if row.draft else 0,
                review_status=cast(Any, row.review_status),
                created_at=row.created_at,
            )
        )
    return summaries


def _out(row: Any) -> ArticleDraftOut:
    return ArticleDraftOut(
        card_id=row.card_id,
        status=cast(Any, row.status),
        template=cast(Any, row.template),
        # A failed card stores {} rather than a body.
        draft=ArticleBody.model_validate(row.draft) if row.draft else None,
        review_summary=row.review_summary,
        failure_reason=row.failure_reason,
        review_status=cast(Any, row.review_status),
        review_note=row.review_note,
        reviewed_at=row.reviewed_at,
        cost_usd=row.cost_usd,
        calls=row.calls,
        tokens=row.tokens,
        created_at=row.created_at,
    )


def _row(repo: ArticleDraftRepository, card_id: UUID) -> Any:
    row = repo.get(card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return row


@router.get(
    "/editor/drafts/{card_id}",
    response_model=ArticleDraftOut,
    dependencies=[Depends(require_editor_key)],
)
def editor_draft(
    card_id: UUID, repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)]
) -> ArticleDraftOut:
    return _out(_row(repo, card_id))


@router.post(
    "/editor/drafts/{card_id}/sentence",
    response_model=ArticleDraftOut,
    dependencies=[Depends(require_editor_key)],
)
def edit_sentence(
    card_id: UUID,
    payload: SentenceEditIn,
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
) -> ArticleDraftOut:
    row = _row(repo, card_id)
    if not row.draft:
        raise HTTPException(status_code=409, detail="This draft has no body to edit")
    if row.review_status in _FINAL:
        raise HTTPException(status_code=409, detail=f"Draft is already {row.review_status}")
    try:
        edited = apply_sentence_edit(
            ArticleBody.model_validate(row.draft),
            section=payload.section,
            paragraph=payload.paragraph,
            text=payload.text,
            replacement=payload.replacement,
        )
    except ArtifactValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    repo.save_edit(
        row,
        edited,
        {
            "type": "edit",
            "section": payload.section,
            "paragraph": payload.paragraph,
            "before": payload.text,
            "after": payload.replacement,
        },
    )
    return _out(row)


@router.post(
    "/editor/drafts/{card_id}/review",
    response_model=ArticleDraftOut,
    dependencies=[Depends(require_editor_key)],
)
def review_draft(
    card_id: UUID,
    payload: ReviewIn,
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
) -> ArticleDraftOut:
    row = _row(repo, card_id)
    if row.review_status in _FINAL:
        raise HTTPException(status_code=409, detail=f"Draft is already {row.review_status}")
    if payload.decision == "approved":
        if row.status != "drafted" or not row.draft:
            raise HTTPException(status_code=409, detail="Only a drafted article can be approved")
        if row.draft.get("flags"):
            raise HTTPException(status_code=409, detail="Resolve every flagged sentence first")
    repo.save_review(
        row, payload.decision, payload.note, {"type": "review", "decision": payload.decision}
    )
    return _out(row)
