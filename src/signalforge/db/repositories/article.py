from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.article import ArticleDraft
from signalforge.core.artifacts.research import ResearchStatus
from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal


class ArticleDraftRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_researched_undrafted(
        self, limit: int
    ) -> list[tuple[TopicCardRow, Signal, ResearchPackageRow]]:
        """Cards with a 'researched' package and no article_drafts row.

        Keyed on the package status, not the latest editor decision: research only ran
        because the card was accepted, and a finished package is what drafting needs.
        The signal is returned for template selection only; the writer never sees it.
        Ordered oldest card first, id as a deterministic tie-break.
        """
        drafted = select(ArticleDraftRow.card_id)
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

    def insert(self, draft: ArticleDraft, *, cost_usd: Decimal, calls: int, tokens: int) -> bool:
        """Insert an article_drafts row derived from ``draft``.

        ON CONFLICT (card_id) DO NOTHING. A missing body is stored as ``{}``.
        """
        dumped = draft.model_dump(mode="json")
        statement = (
            insert(ArticleDraftRow)
            .values(
                id=draft.id,
                schema_version=draft.schema_version,
                card_id=draft.card_id,
                status=draft.status.value,
                template=draft.template.value,
                draft=dumped["draft"] or {},
                review_summary=draft.review_summary,
                cost_usd=cost_usd,
                calls=calls,
                tokens=tokens,
            )
            .on_conflict_do_nothing(index_elements=["card_id"])
            .returning(ArticleDraftRow.id)
        )
        return self._session.execute(statement).first() is not None
