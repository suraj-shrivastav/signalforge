from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.db.models.published import PublishedArticleRow


class PublishedArticleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def slug_exists(self, slug: str) -> bool:
        return (
            self._session.scalars(
                select(PublishedArticleRow.id).where(PublishedArticleRow.slug == slug)
            ).first()
            is not None
        )

    def get_by_card(self, card_id: UUID) -> PublishedArticleRow | None:
        return self._session.scalars(
            select(PublishedArticleRow).where(PublishedArticleRow.card_id == card_id)
        ).one_or_none()

    def get_public(self, slug: str) -> PublishedArticleRow | None:
        """A published (not unpublished) article by slug."""
        return self._session.scalars(
            select(PublishedArticleRow).where(
                PublishedArticleRow.slug == slug, PublishedArticleRow.status == "published"
            )
        ).one_or_none()

    def get_by_slug(self, slug: str) -> PublishedArticleRow | None:
        return self._session.scalars(
            select(PublishedArticleRow).where(PublishedArticleRow.slug == slug)
        ).one_or_none()

    def list_public(self, limit: int) -> list[PublishedArticleRow]:
        """Newest published articles first."""
        query = (
            select(PublishedArticleRow)
            .where(PublishedArticleRow.status == "published")
            .order_by(PublishedArticleRow.published_at.desc(), PublishedArticleRow.id.desc())
            .limit(limit)
        )
        return list(self._session.scalars(query))

    def publish(self, card_id: UUID, fields: dict[str, Any]) -> PublishedArticleRow:
        """Create the row, or republish an unpublished one (keeps its first published_at)."""
        now = datetime.now(UTC)
        row = self.get_by_card(card_id)
        if row is None:
            row = PublishedArticleRow(
                card_id=card_id, published_at=now, modified_at=now, status="published", **fields
            )
            self._session.add(row)
        else:
            for name, value in fields.items():
                setattr(row, name, value)
            row.status = "published"
            row.modified_at = now
        self._session.flush()
        return row

    def unpublish(self, row: PublishedArticleRow) -> None:
        row.status = "unpublished"
        row.modified_at = datetime.now(UTC)
        self._session.flush()

    def set_images(
        self,
        row: PublishedArticleRow,
        *,
        cover: dict[str, str] | None,
        figure: dict[str, str] | None,
    ) -> None:
        """Attach the cover and inline image to the published body (a new dict, so the
        JSON column registers the change)."""
        body = dict(row.body)
        if cover is not None:
            body["cover"] = {**body.get("cover", {}), "src": cover["src"], "alt": cover["alt"]}
        if figure is not None:
            body["figure"] = figure
        row.body = body
        row.modified_at = datetime.now(UTC)
        self._session.flush()
