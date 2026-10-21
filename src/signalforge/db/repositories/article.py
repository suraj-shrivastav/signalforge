from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.article import ArticleDraft, DraftStatus
from signalforge.core.artifacts.research import ResearchStatus
from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal


class ArticleDraftRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_researched_undrafted(
        self, limit: int, *, retry_failed: bool = False
    ) -> list[tuple[TopicCardRow, Signal, ResearchPackageRow]]:
        """Cards with a 'researched' package and no article_drafts row.

        With ``retry_failed``, a 'failed' row does not count as drafted, and ``insert``
        replaces it. Other statuses are never reselected.

        Keyed on the package status, not the latest editor decision: research only ran
        because the card was accepted, and a finished package is what drafting needs.
        The signal is returned for template selection only; the writer never sees it.
        Ordered oldest card first, id as a deterministic tie-break.
        """
        drafted = select(ArticleDraftRow.card_id)
        if retry_failed:
            drafted = drafted.where(ArticleDraftRow.status != DraftStatus.FAILED.value)
        query = (
            select(TopicCardRow, Signal, ResearchPackageRow)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(ResearchPackageRow, ResearchPackageRow.card_id == TopicCardRow.id)
            .where(
                ResearchPackageRow.status == ResearchStatus.RESEARCHED.value,
                TopicCardRow.id.not_in(drafted),
            )
            .order_by(TopicCardRow.created_at.asc(), TopicCardRow.id.asc())
            .limit(limit)
        )
        return [(card, signal, pkg) for card, signal, pkg in self._session.execute(query).all()]

    def insert(
        self,
        draft: ArticleDraft,
        *,
        cost_usd: Decimal,
        calls: int,
        tokens: int,
        failure_reason: str | None = None,
    ) -> bool:
        """Insert an article_drafts row derived from ``draft``.

        ON CONFLICT (card_id) a 'failed' row is replaced by the retry; any other row is
        left alone. A missing body is stored as ``{}``.
        """
        dumped = draft.model_dump(mode="json")
        values = {
            "schema_version": draft.schema_version,
            "status": draft.status.value,
            "template": draft.template.value,
            "draft": dumped["draft"] or {},
            "review_summary": draft.review_summary,
            "failure_reason": failure_reason,
            "cost_usd": cost_usd,
            "calls": calls,
            "tokens": tokens,
        }
        statement = (
            insert(ArticleDraftRow)
            .values(id=draft.id, card_id=draft.card_id, **values)
            .on_conflict_do_update(
                index_elements=["card_id"],
                set_={**values, "updated_at": func.now()},
                where=ArticleDraftRow.status == DraftStatus.FAILED.value,
            )
            .returning(ArticleDraftRow.id)
        )
        return self._session.execute(statement).first() is not None

    def list_recent(self, limit: int) -> list[tuple[ArticleDraftRow, str]]:
        """Newest drafts first, each with its source signal's title."""
        query = (
            select(ArticleDraftRow, Signal.title)
            .join(TopicCardRow, TopicCardRow.id == ArticleDraftRow.card_id)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .order_by(ArticleDraftRow.created_at.desc(), ArticleDraftRow.id.desc())
            .limit(limit)
        )
        return [(row, title) for row, title in self._session.execute(query).all()]

    def get(self, card_id: UUID) -> ArticleDraftRow | None:
        return self._session.scalars(
            select(ArticleDraftRow).where(ArticleDraftRow.card_id == card_id)
        ).one_or_none()
