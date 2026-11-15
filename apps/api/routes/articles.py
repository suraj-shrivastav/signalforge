"""Article drafts. Editor-only read; there is no public route until approval exists."""

from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from apps.api.deps import (
    get_article_repository,
    get_controls_repository,
    get_published_repository,
)
from apps.api.routes.cards import require_editor_key
from apps.api.schemas import (
    ArticleDraftOut,
    ArticleDraftSummaryOut,
    ImagesIn,
    ImagesUploadIn,
    PublishedOut,
    PublishIn,
    ReviewIn,
    SentenceEditIn,
)
from signalforge.control_policy import is_paused
from signalforge.core.artifacts.article import ArticleBody
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.repositories.article import ArticleDraftRepository
from signalforge.db.repositories.controls import ControlsRepository
from signalforge.db.repositories.published import PublishedArticleRepository
from signalforge.image_storage import ImageStorageError, check_svg, upload_svg
from signalforge.indexnow import ping_indexnow
from signalforge.publishing import meta_description, slugify, unique_slug
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


def _out(row: Any, published_slug: str | None = None) -> ArticleDraftOut:
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
        published_slug=published_slug,
        cost_usd=row.cost_usd,
        calls=row.calls,
        tokens=row.tokens,
        created_at=row.created_at,
    )


def ensure_running(controls: ControlsRepository) -> None:
    """423 while the pipeline is paused (the kill switch the agent must obey)."""
    if is_paused(controls.get(), datetime.now(UTC)):
        raise HTTPException(status_code=423, detail="Pipeline is paused")


def get_draft_row(repo: ArticleDraftRepository, card_id: UUID) -> Any:
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
    card_id: UUID,
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
) -> ArticleDraftOut:
    row = get_draft_row(repo, card_id)
    live = published.get_by_card(card_id)
    return _out(row, live.slug if live is not None and live.status == "published" else None)


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
    row = get_draft_row(repo, card_id)
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
    row = get_draft_row(repo, card_id)
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


def publish_approved(
    card_id: UUID,
    payload: PublishIn,
    settings: Any,
    background: BackgroundTasks,
    repo: ArticleDraftRepository,
    published: PublishedArticleRepository,
) -> PublishedOut:
    """Publish an approved draft as an immutable snapshot with its SEO fields."""
    row = get_draft_row(repo, card_id)
    if row.review_status != "approved" or row.status != "drafted" or not row.draft:
        raise HTTPException(status_code=409, detail="Only an approved, drafted article can publish")
    if row.draft.get("flags"):
        raise HTTPException(status_code=409, detail="Resolve every flagged sentence first")
    existing = published.get_by_card(card_id)
    if existing is not None and existing.status == "published":
        raise HTTPException(status_code=409, detail="Already published")
    body = ArticleBody.model_validate(row.draft)
    if payload.slug is not None:
        slug = payload.slug
        taken = published.get_by_slug(slug)
        if taken is not None and (existing is None or taken.id != existing.id):
            raise HTTPException(status_code=409, detail="That slug is already in use")
    elif existing is not None:
        slug = existing.slug
    else:
        slug = unique_slug(slugify(body.title), published.slug_exists)
    saved = published.publish(
        card_id,
        {
            "slug": slug,
            "template": row.template,
            "seo_title": payload.seo_title or body.title,
            "meta_description": payload.meta_description or meta_description(body.dek),
            "byline": settings.publish_byline,
            "process_note": settings.publish_process_note,
            "editor_analysis": payload.editor_analysis.strip(),
            "body": body.model_dump(mode="json"),
        },
    )
    if settings.site_url and settings.indexnow_key:
        background.add_task(ping_indexnow, settings.site_url, settings.indexnow_key, saved.slug)
    return PublishedOut(
        slug=saved.slug,
        status=cast(Any, saved.status),
        published_at=saved.published_at,
        modified_at=saved.modified_at,
    )


@router.post(
    "/editor/drafts/{card_id}/publish",
    response_model=PublishedOut,
    dependencies=[Depends(require_editor_key)],
)
def publish_draft(
    card_id: UUID,
    payload: PublishIn,
    request: Request,
    background: BackgroundTasks,
    repo: Annotated[ArticleDraftRepository, Depends(get_article_repository)],
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
    controls: Annotated[ControlsRepository, Depends(get_controls_repository)],
) -> PublishedOut:
    """Publish an approved draft. With the agent key, 423 while the pipeline is paused.

    The editor key always publishes: it is the owner's manual override, and the only way to
    bring back an article the owner unpublished.
    """
    if request.state.actor == "agent":
        ensure_running(controls)
        existing = published.get_by_card(card_id)
        if existing is not None and existing.status == "unpublished":
            raise HTTPException(
                status_code=409,
                detail="Unpublished by the owner; only the editor key can republish",
            )
    return publish_approved(
        card_id, payload, request.app.state.settings, background, repo, published
    )


@router.post(
    "/editor/articles/{slug}/unpublish",
    response_model=PublishedOut,
    dependencies=[Depends(require_editor_key)],
)
def unpublish_article(
    slug: str,
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
) -> PublishedOut:
    row = published.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    if row.status == "published":
        published.unpublish(row)
    return PublishedOut(
        slug=row.slug,
        status=cast(Any, row.status),
        published_at=row.published_at,
        modified_at=row.modified_at,
    )


_IMAGE_PATH = "/storage/v1/object/public/article-images/"


def _image_url_ok(src: str, supabase_url: str) -> bool:
    """Only images in the project's public article-images bucket are accepted."""
    if not supabase_url:
        return False
    allowed = urlparse(supabase_url)
    url = urlparse(src)
    return (
        url.scheme == "https"
        and url.netloc == allowed.netloc
        and url.path.startswith(_IMAGE_PATH)
        and not url.query
        and not url.fragment
    )


@router.post(
    "/editor/articles/{slug}/images",
    response_model=PublishedOut,
    dependencies=[Depends(require_editor_key)],
)
def attach_images(
    slug: str,
    payload: ImagesIn,
    request: Request,
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
) -> PublishedOut:
    """Attach the cover and the inline image (stored in the Supabase bucket) to an article."""
    row = published.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    supabase_url = request.app.state.settings.supabase_url
    for image in (payload.cover, payload.figure):
        if image is not None and not _image_url_ok(image.src, supabase_url):
            raise HTTPException(
                status_code=422, detail="Image must be in the article-images bucket"
            )
    published.set_images(
        row,
        cover=payload.cover.model_dump() if payload.cover else None,
        figure=payload.figure.model_dump() if payload.figure else None,
    )
    return PublishedOut(
        slug=row.slug,
        status=cast(Any, row.status),
        published_at=row.published_at,
        modified_at=row.modified_at,
    )


@router.post(
    "/editor/articles/{slug}/images/upload",
    response_model=PublishedOut,
    dependencies=[Depends(require_editor_key)],
)
def upload_images(
    slug: str,
    payload: ImagesUploadIn,
    request: Request,
    published: Annotated[PublishedArticleRepository, Depends(get_published_repository)],
) -> PublishedOut:
    """Store the agent's rendered SVGs in the article-images bucket and attach them.

    The Supabase secret stays on the API, so an agent needs only its API key.
    """
    settings = request.app.state.settings
    if not settings.supabase_url or settings.supabase_secret_key is None:
        raise HTTPException(status_code=503, detail="Image upload is not configured")
    row = published.get_by_slug(slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    try:
        for image in (payload.cover, payload.figure):
            check_svg(image.svg)
    except ImageStorageError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    key = settings.supabase_secret_key.get_secret_value()
    try:
        urls = {
            role: upload_svg(
                image.svg, slug=slug, role=role, supabase_url=settings.supabase_url, key=key
            )
            for role, image in (("cover", payload.cover), ("figure", payload.figure))
        }
    except ImageStorageError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc
    published.set_images(
        row,
        cover={"src": urls["cover"], "alt": payload.cover.alt, "caption": ""},
        figure={
            "src": urls["figure"],
            "alt": payload.figure.alt,
            "caption": payload.figure.caption,
        },
    )
    return PublishedOut(
        slug=row.slug,
        status=cast(Any, row.status),
        published_at=row.published_at,
        modified_at=row.modified_at,
    )
