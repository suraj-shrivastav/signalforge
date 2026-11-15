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
from signalforge.explain import CardFacts
from signalforge.pipeline_state import CardState, classify, redrafts_used


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
        cards = []
        for f in self.facts(limit, accepted_only=True):
            state = self.state_of(f, max_redrafts)
            cards.append(
                PipelineCard(
                    f.card_id, f.title, state.stage, state.next_action,
                    f.slug if f.published_status == "published" else None, f.created_at,
                )
            )  # fmt: skip
        return cards

    @staticmethod
    def state_of(f: CardFacts, max_redrafts: int) -> CardState:
        """The one classification of a card's facts (shared by the list and the explainer)."""
        return classify(
            research=f.research_status,
            research_attempts=f.research_attempts,
            draft=f.draft_status,
            draft_attempts=f.draft_attempts,
            review=f.review_status,
            redrafts=redrafts_used(f.review_log),
            max_redrafts=max_redrafts,
            published=f.published_status,
            has_cover=f.has_cover,
            has_figure=f.has_figure,
        )

    def facts(
        self, limit: int, *, accepted_only: bool = True, card_id: UUID | None = None
    ) -> list[CardFacts]:
        """Newest cards first with the stored facts of each. Read-only.

        ``accepted_only`` keeps cards whose latest decision is 'accepted'; without it any card
        comes back with its latest decision (None if it has none).
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
                latest.c.decision,
                ResearchPackageRow.status,
                ResearchPackageRow.attempts,
                ResearchPackageRow.failure_reason,
                ArticleDraftRow.status,
                ArticleDraftRow.attempts,
                ArticleDraftRow.failure_reason,
                ArticleDraftRow.review_status,
                ArticleDraftRow.review_log,
                PublishedArticleRow.status,
                PublishedArticleRow.slug,
                PublishedArticleRow.body,
            )
            .join(Signal, Signal.id == TopicCardRow.signal_id)
            .outerjoin(latest, latest.c.topic_card_id == TopicCardRow.id)
            .outerjoin(ResearchPackageRow, ResearchPackageRow.card_id == TopicCardRow.id)
            .outerjoin(ArticleDraftRow, ArticleDraftRow.card_id == TopicCardRow.id)
            .outerjoin(PublishedArticleRow, PublishedArticleRow.card_id == TopicCardRow.id)
            .order_by(TopicCardRow.created_at.desc(), TopicCardRow.id.desc())
            .limit(limit)
        )
        if accepted_only:
            query = query.where(latest.c.decision == "accepted")
        if card_id is not None:
            query = query.where(TopicCardRow.id == card_id)
        out = []
        for (
            cid, title, created, decision, r_status, r_attempts, r_failure,
            d_status, d_attempts, d_failure, review, review_log, pub, slug, body,
        ) in self._session.execute(query).all():  # fmt: skip
            body = body or {}
            out.append(
                CardFacts(
                    card_id=cid, title=title, created_at=created, decision=decision,
                    research_status=r_status, research_attempts=r_attempts or 0,
                    research_failure=r_failure, draft_status=d_status,
                    draft_attempts=d_attempts or 0, draft_failure=d_failure,
                    review_status=review, review_log=tuple(review_log or ()),
                    published_status=pub, slug=slug,
                    has_cover=bool((body.get("cover") or {}).get("src")),
                    has_figure=bool(body.get("figure")),
                )
            )  # fmt: skip
        return out
