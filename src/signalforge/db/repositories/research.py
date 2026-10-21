from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import ResearchPackage, ResearchStatus
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal

_RETRYABLE = (ResearchStatus.FAILED.value, ResearchStatus.NEEDS_MORE_INFO.value)


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_accepted_unresearched(
        self, limit: int, *, retry_failed: bool = False
    ) -> list[tuple[TopicCardRow, Signal]]:
        """Cards whose LATEST decision is 'accepted' and that have no research_packages row.

        With ``retry_failed``, a 'failed' or 'needs_more_info' package does not count as
        researched, and ``insert`` replaces it.

        Ordered oldest card first, id as a deterministic tie-break.
        """
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
        researched = select(ResearchPackageRow.card_id)
        if retry_failed:
            researched = researched.where(ResearchPackageRow.status.not_in(_RETRYABLE))
        query = (
            select(TopicCardRow, Signal)
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(latest, latest.c.topic_card_id == TopicCardRow.id)
            .where(
                latest.c.decision == "accepted",
                TopicCardRow.id.not_in(researched),
            )
            .order_by(TopicCardRow.created_at.asc(), TopicCardRow.id.asc())
            .limit(limit)
        )
        return [(card, signal) for card, signal in self._session.execute(query).all()]

    def insert(
        self,
        package: ResearchPackage,
        *,
        cost_usd: Decimal,
        calls: int,
        tokens: int,
        failure_reason: str | None = None,
    ) -> bool:
        """Insert a research_packages row derived from ``package``.

        ON CONFLICT (card_id) a 'failed' or 'needs_more_info' row is replaced by the retry;
        any other row is left alone.
        """
        dumped = package.model_dump(mode="json")
        values = {
            "schema_version": package.schema_version,
            "status": package.status.value,
            "documents": dumped["documents"],
            "claims": dumped["claims"],
            "gaps_and_disagreements": package.gaps_and_disagreements,
            "failure_reason": failure_reason,
            "cost_usd": cost_usd,
            "calls": calls,
            "tokens": tokens,
        }
        statement = (
            insert(ResearchPackageRow)
            .values(id=package.id, card_id=package.card_id, **values)
            .on_conflict_do_update(
                index_elements=["card_id"],
                set_={**values, "updated_at": func.now()},
                where=ResearchPackageRow.status.in_(_RETRYABLE),
            )
            .returning(ResearchPackageRow.id)
        )
        return self._session.execute(statement).first() is not None
