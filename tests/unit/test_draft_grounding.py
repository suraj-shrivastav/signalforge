# ruff: noqa: ARG002
"""Draft grounding: every sentence cites research claims, and code checks the citations."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import pytest

from signalforge.core.artifacts.article import ArticleTemplate, DraftStatus
from signalforge.core.artifacts.research import (
    ClaimStatus,
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider, ProviderReply
from signalforge.llm.roles import ModelSpec
from signalforge.stages.draft import JUDGE_ROLE, WRITER_ROLE, _process_card
from signalforge.stages.draft_extraction import (
    evidence_window,
    sentence_problems,
    unfamiliar_names,
)

SPAN = "scored 535.4 out of 600 at the contest"
CLAIM = "Nemotron scored 535.4 out of 600."
FAR = "Unrelated trailing text about licensing. " * 40
DOC = f"Intro text. The model {SPAN}, above the threshold. {FAR}"
RUN = uuid.uuid4()


class Recorder:
    def add(self, row: Any) -> None:
        pass


def package() -> ResearchPackage:
    return ResearchPackage(
        card_id=uuid.uuid4(),
        status=ResearchStatus.RESEARCHED,
        documents=(
            ResearchDocument(
                url="https://example.com/post",
                title="Post",
                source_label="example.com",
                is_primary=True,
                raw_text_ref="ref",
                text=DOC,
                fetched_at=datetime.now(UTC),
            ),
        ),
        claims=(ResearchClaim(text=CLAIM, evidence_span=SPAN, document_indices=(0,)),),
    )


def sentence(text: str, ids: list[int]) -> dict[str, Any]:
    return {"text": text, "claim_ids": ids}


GOOD = "Nemotron scored 535.4 out of 600 at the contest."
# Fills the news_brief band (250 to 400 words) with grounded repeats of the claim.
BODY = [sentence(GOOD, [0])] * 28


def writer(sentences: list[dict[str, Any]] | None = None, title: str = "Nemotron scores") -> str:
    return json.dumps(
        {
            "title": title,
            "dek": sentence(GOOD, [0]),
            "sections": [
                {"heading": "What changed", "paragraphs": [{"sentences": sentences or BODY}]}
            ],
            "cover_alt": "Score chart",
        }
    )


def judge(*supported: bool) -> str:
    verdicts = [{"index": i, "supported": s} for i, s in enumerate(supported)]
    return json.dumps({"sentences": verdicts})


def run(replies: list[str], brief: str = "", provider: Any = None) -> Any:
    roles = {WRITER_ROLE: ModelSpec("a/w", "a"), JUDGE_ROLE: ModelSpec("b/j", "b")}
    budget = Budget(BudgetScope.ARTICLE, BudgetLimits(max_cost_usd=Decimal("1")))
    gateway = LLMGateway(provider or FakeProvider(replies), roles, budget, Recorder())  # type: ignore[arg-type]
    return _process_card(gateway, package(), ArticleTemplate.NEWS_BRIEF, RUN, brief)


def all_true(n: int = 29) -> str:
    return judge(*([True] * n))


def test_grounded_article_is_drafted_with_cited_claim_copied_from_research() -> None:
    draft = run([writer(), all_true()])
    assert draft.status is DraftStatus.DRAFTED
    assert draft.draft is not None
    (claim,) = draft.draft.claims
    assert (claim.text, claim.evidence_span) == (CLAIM, SPAN)
    assert claim.status is ClaimStatus.VERIFIED
    assert draft.draft.sections[0].citations == ((0,),)


def test_uncited_sentence_blocks_the_draft() -> None:
    body = [*BODY, sentence("It is open source and free for everyone.", [])]
    draft = run([writer(body), all_true()])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "uncited sentence: 'It is open source" in draft.review_summary


def test_unknown_claim_id_counts_as_uncited() -> None:
    body = [*BODY, sentence("Nemotron scored 535.4 out of 600.", [7])]
    draft = run([writer(body), all_true()])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "uncited sentence" in draft.review_summary


def test_invented_number_blocks_the_draft() -> None:
    body = [*BODY, sentence("Nemotron scored 612 out of 600 at the contest.", [0])]
    draft = run([writer(body), all_true()])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "number(s) 612 not in the cited claims" in draft.review_summary


def test_invented_number_in_title_blocks_the_draft() -> None:
    draft = run([writer(title="Nemotron beats 99 rivals"), all_true()])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "title: number(s) 99" in draft.review_summary


def test_judge_rejection_blocks_the_draft_and_marks_the_claim_uncertain() -> None:
    verdicts = [True] * 29
    verdicts[3] = False
    draft = run([writer(), judge(*verdicts)])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "judge does not confirm sentence" in draft.review_summary
    assert draft.draft is not None
    assert draft.draft.claims[0].status is ClaimStatus.UNCERTAIN


def test_missing_judge_verdict_fails_closed() -> None:
    draft = run([writer(), judge(*([True] * 5))])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO


def test_unfamiliar_name_is_flagged_for_the_editor_without_blocking() -> None:
    body = [*BODY, sentence("Nemotron scored 535.4 out of 600, said Jensen.", [0])]
    draft = run([writer(body), all_true(30)])
    assert "names not in the cited claims (Jensen)" in draft.review_summary


def test_writer_sees_claim_windows_not_whole_documents() -> None:
    seen: list[str] = []

    class Spy:
        name = "spy"
        replies: ClassVar[list[str]] = [writer(), all_true()]

        def chat(self, model: str, messages: list[dict[str, str]], **k: Any) -> ProviderReply:
            seen.append(messages[-1]["content"])
            return ProviderReply(self.replies.pop(0), 1, 1, 1)

    run([], brief="Focus on the contest result", provider=Spy())
    writer_prompt, judge_prompt = seen
    assert SPAN in writer_prompt
    assert FAR not in writer_prompt
    assert "Focus on the contest result" in writer_prompt
    assert FAR not in judge_prompt
    assert len(judge_prompt) < 40_000


def test_sentence_problems() -> None:
    support = f"{CLAIM} {SPAN}"
    assert sentence_problems("Scored 535.4 here.", [0], support) == []
    assert sentence_problems("Scored 535,4 here.", [0], support) != []
    assert sentence_problems("No ids.", [], support)[0].startswith("uncited sentence")
    assert "612" in sentence_problems("Scored 612.", [0], support)[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Nemotron won.", []),
        ("It beat Gemini.", ["Gemini"]),
        ("Nemotron and IMO are linked.", ["IMO"]),
    ],
)
def test_unfamiliar_names(text: str, expected: list[str]) -> None:
    assert unfamiliar_names(text, CLAIM) == expected


def test_evidence_window_is_bounded_and_falls_back_to_the_quote() -> None:
    pkg = package()
    window = evidence_window(pkg.claims[0], pkg.documents, radius=20)
    assert SPAN in window
    assert len(window) <= len(SPAN) + 40
    orphan = ResearchClaim(text="x", evidence_span="not in doc", document_indices=(0,))
    assert evidence_window(orphan, pkg.documents) == "not in doc"
