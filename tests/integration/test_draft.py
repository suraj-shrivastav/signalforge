import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from signalforge.core.artifacts.research import (
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)
from signalforge.core.artifacts.signal import RawSignal
from signalforge.core.budget import Budget, BudgetLimits
from signalforge.core.errors import ConfigurationError
from signalforge.db.models import ArticleDraftRow, StageRun, StageRunStatus, TopicCardRow
from signalforge.db.repositories.research import ResearchRepository
from signalforge.db.repositories.signals import SignalRepository
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider
from signalforge.llm.roles import ModelSpec
from signalforge.stages.draft import JUDGE_ROLE, WRITER_ROLE, run_draft

pytestmark = pytest.mark.integration

SPAN = "beats the prior best by a wide margin"
DOC_TEXT = f"The model {SPAN} in every benchmark tested."
LIMITS = BudgetLimits(max_cost_usd=Decimal("1"))
# Explainer band is 700-1000 words; the gate checks it.
FILLER = " ".join(["word"] * 760)


def factory(
    replies: list[str], judge_family: str = "other", judge_model: str | None = None
) -> Callable[[Session, Budget], LLMGateway]:
    provider = FakeProvider(replies)

    def make(session: Session, budget: Budget) -> LLMGateway:
        roles = {
            WRITER_ROLE: ModelSpec("acme/w", "acme"),
            JUDGE_ROLE: ModelSpec(judge_model or f"{judge_family}/j", judge_family),
        }
        return LLMGateway(provider, roles, budget, session)

    return make


def writer(extra: list[dict[str, Any]] | None = None, paragraph: str = FILLER) -> str:
    """A reply whose every sentence cites research claim 0, plus optional extra sentences."""
    body = [{"text": paragraph, "claim_ids": [0]}, *(extra or [])]
    return json.dumps(
        {
            "title": "A model beats the prior best",
            "dek": {"text": "What the new results show.", "claim_ids": [0]},
            "sections": [{"heading": "The short version", "paragraphs": [{"sentences": body}]}],
            "cover_alt": "Benchmark chart",
        }
    )


def judge(*supported: bool) -> str:
    verdicts = [{"index": i, "supported": v} for i, v in enumerate(supported)]
    return json.dumps({"sentences": verdicts})


def seed(session: Session) -> TopicCardRow:
    signal = RawSignal(
        source="hackernews",
        source_type="community",
        canonical_url="https://example.com/draft",
        title="Benchmarks for a new model",
        published_at=datetime.now(UTC),
    )
    SignalRepository(session).insert_new([signal])
    run = StageRun(
        stage="card",
        entity_id=signal.id,
        input_hash="h",
        stage_config_hash="c",
        status=StageRunStatus.SUCCEEDED,
    )
    session.add(run)
    session.flush()
    card = TopicCardRow(
        signal_id=signal.id,
        stage_run_id=run.id,
        what_happened="w",
        why_it_matters="m",
        novelty=0.5,
        signal_strength=0.5,
        coverage_gap="",
        suggested_angle="a",
        format="explainer",
        evergreen_score=0.5,
        confidence=0.5,
        prompt_version="card-v1",
        model="m",
    )
    session.add(card)
    session.flush()
    package = ResearchPackage(
        card_id=card.id,
        status=ResearchStatus.RESEARCHED,
        documents=(
            ResearchDocument(
                url="https://example.com/draft",
                title="Doc",
                source_label="example",
                is_primary=True,
                raw_text_ref="ref",
                text=DOC_TEXT,
                fetched_at=datetime.now(UTC),
            ),
        ),
        claims=(ResearchClaim(text="beats", evidence_span=SPAN, document_indices=(0,)),),
    )
    ResearchRepository(session).insert(package, cost_usd=Decimal("0"), calls=0, tokens=0)
    return card


def row(session: Session, card: TopicCardRow) -> ArticleDraftRow:
    return session.query(ArticleDraftRow).filter_by(card_id=card.id).one()


def test_clean_draft_is_drafted_with_verified_claim(db_session: Session) -> None:
    card = seed(db_session)
    result = run_draft(db_session, factory([writer(), judge(True, True)]), budget_limits=LIMITS)
    assert (result.considered, result.drafted) == (1, 1)
    draft = row(db_session, card)
    assert (draft.status, draft.template) == ("drafted", "explainer")
    assert draft.draft["claims"][0]["status"] == "verified"
    assert draft.draft["sources"] == [{"label": "example", "url": "https://example.com/draft"}]
    assert draft.calls == 2


def test_uncited_sentence_needs_more_info(db_session: Session) -> None:
    card = seed(db_session)
    extra = [{"text": "It is free for everyone.", "claim_ids": []}]
    replies = [writer(extra), judge(True, True)]
    result = run_draft(db_session, factory(replies), budget_limits=LIMITS)
    assert result.needs_more_info == 1
    draft = row(db_session, card)
    assert draft.status == "needs_more_info"
    assert "uncited sentence: 'It is free for everyone.'" in draft.review_summary


def test_judge_disagreement_marks_claim_uncertain(db_session: Session) -> None:
    card = seed(db_session)
    run_draft(db_session, factory([writer(), judge(True, False)]), budget_limits=LIMITS)
    draft = row(db_session, card)
    assert draft.status == "needs_more_info"
    assert [c["status"] for c in draft.draft["claims"]] == ["uncertain"]
    assert "judge does not confirm sentence" in draft.review_summary


def test_publish_gate_failure_needs_more_info(db_session: Session) -> None:
    card = seed(db_session)
    replies = [writer(paragraph=FILLER + " \u2014 aside"), judge(True, True)]
    result = run_draft(db_session, factory(replies), budget_limits=LIMITS)
    assert result.needs_more_info == 1
    draft = row(db_session, card)
    assert draft.status == "needs_more_info"
    assert draft.draft["title"]
    assert "Publish gate: contains an em dash" in draft.review_summary


def test_budget_exhausted_mid_card_fails_with_empty_draft(db_session: Session) -> None:
    card = seed(db_session)
    limits = BudgetLimits(max_cost_usd=Decimal("1"), max_calls=1)
    result = run_draft(db_session, factory([writer(), judge(True, True)]), budget_limits=limits)
    assert result.failed == 1
    draft = row(db_session, card)
    assert (draft.status, draft.draft, draft.calls) == ("failed", {}, 1)


def test_same_model_roles_fail_fast_before_any_card(db_session: Session) -> None:
    card = seed(db_session)
    with pytest.raises(ConfigurationError):
        run_draft(
            db_session, factory([], judge_family="acme", judge_model="acme/w"), budget_limits=LIMITS
        )
    assert db_session.query(ArticleDraftRow).filter_by(card_id=card.id).count() == 0
    # Latest run, not .one(): a shared dev database already holds real draft runs.
    latest = (
        db_session.query(StageRun)
        .filter_by(stage="draft")
        .order_by(StageRun.created_at.desc())
        .first()
    )
    assert latest is not None
    assert latest.status == StageRunStatus.FAILED


def test_failed_draft_records_reason_and_is_retried_only_on_request(db_session: Session) -> None:
    card = seed(db_session)
    run_draft(db_session, factory([]), budget_limits=LIMITS)  # no queued reply: provider error
    failed = row(db_session, card)
    assert failed.status == "failed"
    assert failed.failure_reason is not None
    assert failed.failure_reason.startswith("ProviderRejectedError:")

    plain = run_draft(db_session, factory([writer(), judge(True, True)]), budget_limits=LIMITS)
    assert plain.considered == 0

    retried = run_draft(
        db_session,
        factory([writer(), judge(True, True)]),
        budget_limits=LIMITS,
        retry_failed=True,
    )
    assert retried.considered == 1
    db_session.expire_all()
    redone = row(db_session, card)
    assert redone.status != "failed"
    assert redone.failure_reason is None
    assert db_session.query(ArticleDraftRow).filter_by(card_id=card.id).count() == 1
