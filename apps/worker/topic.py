"""A topic the owner asks for, as a URL or plain text: make it a card, and for a hot one go on.

Not a CLI: the API runs it as a background job (``POST /agent/topics``). Always returns a
dict (``ok`` false with an ``error`` the owner can read) so the agent sees the outcome in
``GET /agent/runs``.
"""

import logging
from typing import Any

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from apps.worker import draft, research
from apps.worker.research import build_search
from signalforge.core.budget import Budget, BudgetScope
from signalforge.core.canonical import canonical_url
from signalforge.core.config import Settings
from signalforge.core.errors import ArtifactValidationError
from signalforge.db.models.cards import TopicCardRow
from signalforge.db.models.signals import Signal
from signalforge.db.repositories.cards import CardRepository
from signalforge.db.repositories.signals import SignalRepository
from signalforge.db.session import create_session_factory
from signalforge.llm.gateway import LLMGateway, build_gateway
from signalforge.plugins.search.direct_fetch import DirectFetcher
from signalforge.stages.assess import run_assess
from signalforge.stages.cards import run_cards
from signalforge.stages.manual_topic import (
    HOT_SCORE,
    TopicError,
    TopicPage,
    find_page,
    read_page,
    to_signal,
)

log = logging.getLogger(__name__)


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _card_summary(card: TopicCardRow) -> dict[str, Any]:
    return {
        "card_id": str(card.id),
        "what_happened": card.what_happened,
        "why_it_matters": card.why_it_matters,
        "suggested_angle": card.suggested_angle,
        "format": card.format,
        "novelty": card.novelty,
        "signal_strength": card.signal_strength,
        "confidence": card.confidence,
        "risk_flags": list(card.risk_flags),
        "score": card.score,
    }


def run(
    engine: Engine, settings: Settings, *, url: str | None, query: str | None, note: str, hot: bool
) -> dict[str, Any]:
    """Turn the topic into a card (and for ``hot`` accept it, research it and draft it)."""

    def gateway_factory(session: Session) -> LLMGateway:
        budget = Budget(BudgetScope.TOPIC, settings.budget_limits(BudgetScope.TOPIC))
        return build_gateway(settings, session, budget)

    with httpx.Client() as client, create_session_factory(engine)() as session:

        def known(candidate: str) -> bool:
            try:
                wanted = canonical_url(candidate)
            except ArtifactValidationError:
                return True
            found = session.scalar(select(Signal.id).where(Signal.canonical_url == wanted))
            return found is not None

        fetcher = DirectFetcher(client)
        others: list[Any] = []
        page: TopicPage
        try:
            if query:
                page, others = find_page(build_search(settings, client), fetcher, query, known)
            else:
                assert url is not None  # the route guarantees one of the two
                page = read_page(fetcher, url)
            raw = to_signal(page, note=note, hot=hot)
        except (TopicError, ArtifactValidationError) as exc:
            return _fail(getattr(exc, "message", "That is not a usable URL"))
        SignalRepository(session).insert_new([raw])
        session.commit()
        signal_id = session.scalar(
            select(Signal.id).where(Signal.canonical_url == raw.canonical_url)
        )
        if signal_id is None:
            return _fail("The topic could not be saved")
        run_assess(session, gateway_factory, limit=1, only=[signal_id])
        run_cards(session, gateway_factory, limit=1, only=[signal_id])
        card = session.scalars(
            select(TopicCardRow)
            .where(TopicCardRow.signal_id == signal_id)
            .order_by(TopicCardRow.created_at.desc())
        ).first()
        if card is None:
            return _fail("No card was made for that page (the model call failed or hit its budget)")
        outcome: dict[str, Any] = {
            "ok": True,
            "source": {"url": page.url, "title": page.title},
            "alternatives": [{"url": o.url, "title": o.title} for o in others],
            "card": _card_summary(card),
            "accepted": False,
        }
        if not hot:
            return outcome
        CardRepository(session).add_decision(
            card.id, "accepted", [], note or "Hot topic requested by the owner", None
        )
        card.score = max(card.score, HOT_SCORE)
        session.commit()
    outcome["accepted"] = True
    try:
        researched = research.run(engine, 1)
        outcome["research"] = {
            "researched": researched.researched,
            "needs_more_info": researched.needs_more_info,
            "failed": researched.failed,
        }
        if researched.researched:
            drafted = draft.run(engine, 1)
            outcome["draft"] = {"drafted": drafted.drafted, "failed": drafted.failed}
    except Exception as exc:
        log.exception("hot topic follow-up failed")
        outcome["error"] = f"Accepted, but research or drafting failed: {type(exc).__name__}"
    return outcome
