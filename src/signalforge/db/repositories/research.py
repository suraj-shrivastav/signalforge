from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import ResearchPackage
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_accepted_unresearched(self, limit: int) -> list[tuple[TopicCardRow, Signal]]:
        """Cards whose LATEST decision is 'accepted' and that have no research_packages row.

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
        self, package: ResearchPackage, *, cost_usd: Decimal, calls: int, tokens: int
    ) -> bool:
        """Insert a research_packages row derived from ``package``.

        ON CONFLICT (card_id) DO NOTHING.
        """
        dumped = package.model_dump(mode="json")
        statement = (
            insert(ResearchPackageRow)
            .values(
                id=package.id,
                schema_version=package.schema_version,
                card_id=package.card_id,
                status=package.status.value,
                documents=dumped["documents"],
                claims=dumped["claims"],
                gaps_and_disagreements=package.gaps_and_disagreements,
                cost_usd=cost_usd,
                calls=calls,
                tokens=tokens,
            )
            .on_conflict_do_nothing(index_elements=["card_id"])
            .returning(ResearchPackageRow.id)
        )
        return self._session.execute(statement).first() is not None
