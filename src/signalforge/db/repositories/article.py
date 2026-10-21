from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.article import ArticleBody, ArticleDraft, DraftStatus
from signalforge.core.artifacts.research import ResearchStatus
from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
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

        The card's latest editor decision must still be 'accepted': a card rejected or
        snoozed after research is not drafted.
        The signal is returned for template selection only; the writer never sees it.
        Ordered oldest card first, id as a deterministic tie-break.
        """
        drafted = select(ArticleDraftRow.card_id)
        if retry_failed:
            drafted = drafted.where(ArticleDraftRow.status != DraftStatus.FAILED.value)
        latest = (
            select(EditorDecisionRow.topic_card_id, EditorDecisionRow.decision)
            .distinct(EditorDecisionRow.topic_card_id)
            .order_by(
                EditorDecisionRow.topic_card_id,
                EditorDecisionRow.decided_at.desc(),
                EditorDecisionRow.created_at.desc(),
            )
            .subquery()
        )
        query = (
            select(TopicCardRow, Signal, ResearchPackageRow)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(latest, latest.c.topic_card_id == TopicCardRow.id)
            .join(ResearchPackageRow, ResearchPackageRow.card_id == TopicCardRow.id)
            .where(
                latest.c.decision == "accepted",
                ResearchPackageRow.status == ResearchStatus.RESEARCHED.value,
                TopicCardRow.id.not_in(drafted),
            )
            .order_by(TopicCardRow.created_at.asc(), TopicCardRow.id.asc())
            .limit(limit)
        )
        return [(card, signal, pkg) for card, signal, pkg in self._session.execute(query).all()]

    def list_revisions(
        self, limit: int
    ) -> list[tuple[TopicCardRow, Signal, ResearchPackageRow, ArticleDraftRow]]:
        """Drafts the editor sent back (review_status 'revise'), oldest review first."""
        query = (
            select(TopicCardRow, Signal, ResearchPackageRow, ArticleDraftRow)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(ResearchPackageRow, ResearchPackageRow.card_id == TopicCardRow.id)
            .join(ArticleDraftRow, ArticleDraftRow.card_id == TopicCardRow.id)
            .where(
                ArticleDraftRow.review_status == "revise",
                ResearchPackageRow.status == ResearchStatus.RESEARCHED.value,
            )
            .order_by(ArticleDraftRow.reviewed_at.asc(), ArticleDraftRow.id.asc())
            .limit(limit)
        )
        return [tuple(r) for r in self._session.execute(query).all()]

    def replace_revision(
        self,
        row: ArticleDraftRow,
        draft: ArticleDraft,
        *,
        cost_usd: Decimal,
        calls: int,
        tokens: int,
    ) -> None:
        """Swap in a redrafted body, return the draft to the editor and log the redraft.

        The previous summary and the editor's note go to the review log; cost accumulates.
        """
        assert draft.draft is not None
        event = {
            "type": "redraft",
            "note": row.review_note,
            "previous_summary": row.review_summary,
            "at": datetime.now(UTC).isoformat(),
        }
        row.draft = draft.model_dump(mode="json")["draft"]
        row.status = draft.status.value
        row.template = draft.template.value
        row.review_summary = draft.review_summary
        row.failure_reason = None
        row.review_status = "pending"
        row.review_log = [*row.review_log, event]
        row.cost_usd = row.cost_usd + cost_usd
        row.calls = row.calls + calls
        row.tokens = row.tokens + tokens
        self._session.flush()

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

    def save_edit(self, row: ArticleDraftRow, body: ArticleBody, event: dict[str, Any]) -> None:
        """Store an edited body and append the edit to the review log."""
        row.draft = body.model_dump(mode="json")
        row.review_log = [*row.review_log, {**event, "at": datetime.now(UTC).isoformat()}]
        self._session.flush()

    def save_review(
        self, row: ArticleDraftRow, decision: str, note: str, event: dict[str, Any]
    ) -> None:
        """Record the editor's decision on the draft and log it."""
        now = datetime.now(UTC)
        row.review_status = decision
        row.review_note = note
        row.reviewed_at = now
        row.review_log = [*row.review_log, {**event, "at": now.isoformat()}]
        self._session.flush()
