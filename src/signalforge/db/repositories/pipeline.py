from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from signalforge.db.models.article import ArticleDraftRow
from signalforge.db.models.cards import EditorDecisionRow, TopicCardRow
from signalforge.db.models.published import PublishedArticleRow
from signalforge.db.models.research import ResearchPackageRow
from signalforge.db.models.signals import Signal
from signalforge.pipeline_state import classify, redrafts_used


@dataclass(frozen=True)
class PipelineCard:
    card_id: UUID
    title: str
    stage: str
    next_action: str
    slug: str | None
    created_at: datetime


class PipelineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def accepted_cards(self, limit: int, *, max_redrafts: int) -> list[PipelineCard]:
        """Newest accepted cards (latest decision 'accepted') with their derived stage.

        ``max_redrafts`` is AUTO_REVIEW_MAX_REDRAFTS: a revise past it is closed.
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
        query = (
            select(
                TopicCardRow.id,
                Signal.title,
                TopicCardRow.created_at,
                ResearchPackageRow.status,
                ResearchPackageRow.attempts,
                ArticleDraftRow.status,
                ArticleDraftRow.attempts,
                ArticleDraftRow.review_status,
                PublishedArticleRow.status,
                PublishedArticleRow.slug,
                PublishedArticleRow.body,
                ArticleDraftRow.review_log,
            )
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .join(latest, latest.c.topic_card_id == TopicCardRow.id)
            .outerjoin(ResearchPackageRow, ResearchPackageRow.card_id == TopicCardRow.id)
            .outerjoin(ArticleDraftRow, ArticleDraftRow.card_id == TopicCardRow.id)
            .outerjoin(PublishedArticleRow, PublishedArticleRow.card_id == TopicCardRow.id)
            .where(latest.c.decision == "accepted")
            .order_by(TopicCardRow.created_at.desc(), TopicCardRow.id.desc())
            .limit(limit)
        )
        cards = []
        for (
            card_id,
            title,
            created,
            research,
            attempts,
            draft,
            draft_attempts,
            review,
            pub,
            slug,
            body,
            review_log,
        ) in self._session.execute(query).all():
            body = body or {}
            state = classify(
                research=research,
                research_attempts=attempts or 0,
                draft=draft,
                draft_attempts=draft_attempts or 0,
                review=review,
                redrafts=redrafts_used(review_log or []),
                max_redrafts=max_redrafts,
                published=pub,
                has_cover=bool((body.get("cover") or {}).get("src")),
                has_figure=bool(body.get("figure")),
            )
            cards.append(
                PipelineCard(
                    card_id, title, state.stage, state.next_action,
                    slug if pub == "published" else None, created,
                )
            )  # fmt: skip
        return cards
