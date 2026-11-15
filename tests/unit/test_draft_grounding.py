# ruff: noqa: ARG002
"""Draft grounding: every sentence cites research claims, and code checks the citations."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

import pytest

from signalforge.core.artifacts.article import ArticleTemplate, DraftStatus, FlagKind
from signalforge.core.artifacts.research import (
    ClaimStatus,
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.core.errors import ConfigurationError
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider, ProviderReply
from signalforge.llm.roles import ModelSpec
from signalforge.stages.draft import JUDGE_ROLE, WRITER_ROLE, _check_families, _process_card
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


def make_gateway(replies: list[str], provider: Any = None) -> LLMGateway:
    roles = {WRITER_ROLE: ModelSpec("a/w", "a"), JUDGE_ROLE: ModelSpec("b/j", "b")}
    budget = Budget(BudgetScope.ARTICLE, BudgetLimits(max_cost_usd=Decimal("1")))
    return LLMGateway(provider or FakeProvider(replies), roles, budget, Recorder())  # type: ignore[arg-type]


def run(replies: list[str], brief: str = "", provider: Any = None, repair: bool = False) -> Any:
    gateway = make_gateway(replies, provider)
    return _process_card(gateway, package(), ArticleTemplate.NEWS_BRIEF, RUN, brief, repair=repair)


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


def test_uncited_sentence_is_flagged_but_the_draft_still_reaches_the_editor() -> None:
    body = [*BODY, sentence("It is open source and free for everyone.", [])]
    draft = run([writer(body), all_true()])
    assert draft.status is DraftStatus.DRAFTED
    assert draft.draft is not None
    (flag,) = draft.draft.flags
    assert (flag.kind, flag.section, flag.paragraph) == (FlagKind.UNCITED, 0, 0)
    assert flag.text == "It is open source and free for everyone."
    assert "1 of 30 sentences flagged" in draft.review_summary
    assert "Flagged (uncited)" in draft.review_summary


def test_unknown_claim_id_counts_as_uncited() -> None:
    body = [*BODY, sentence("Nemotron scored 535.4 out of 600.", [7])]
    draft = run([writer(body), all_true()])
    assert draft.draft is not None
    assert [f.kind for f in draft.draft.flags] == [FlagKind.UNCITED]


def test_invented_number_is_flagged() -> None:
    body = [*BODY, sentence("Nemotron scored 612 out of 600 at the contest.", [0])]
    draft = run([writer(body), all_true()])
    assert draft.draft is not None
    (flag,) = draft.draft.flags
    assert flag.kind is FlagKind.NUMBER
    assert "612" in flag.detail


def test_invented_number_in_title_is_noted_for_the_editor() -> None:
    draft = run([writer(title="Nemotron beats 99 rivals"), all_true()])
    assert draft.status is DraftStatus.DRAFTED
    assert "title: number(s) 99" in draft.review_summary


def test_judge_rejection_flags_the_sentence_and_marks_the_claim_uncertain() -> None:
    verdicts = [True] * 29
    verdicts[3] = False
    draft = run([writer(), judge(*verdicts)])
    assert draft.draft is not None
    assert [f.kind for f in draft.draft.flags] == [FlagKind.UNSUPPORTED]
    assert draft.draft.claims[0].status is ClaimStatus.UNCERTAIN
    # The only claim is uncertain, so nothing in the draft is usable.
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "no claim reached verified or supported" in draft.review_summary


def test_mostly_flagged_draft_is_blocked() -> None:
    body = [sentence(f"Invented fact number {i} about nothing.", []) for i in range(30)]
    draft = run([writer(body), all_true()])
    assert draft.status is DraftStatus.NEEDS_MORE_INFO
    assert "sentences are flagged" in draft.review_summary


def test_dashes_are_fixed_instead_of_failing_the_gate() -> None:
    body = [*BODY, sentence("Nemotron scored 535.4 \u2014 above the threshold.", [0])]
    draft = run([writer(body), all_true(30)])
    assert draft.status is DraftStatus.DRAFTED
    assert draft.draft is not None
    text = " ".join(p for sec in draft.draft.sections for p in sec.paragraphs)
    assert "\u2014" not in text
    assert "535.4, above the threshold." in text


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


def _gateway(writer_model: str, judge_model: str) -> LLMGateway:
    def family(model: str) -> str:
        return model.split("/")[0]

    roles = {
        WRITER_ROLE: ModelSpec(writer_model, family(writer_model)),
        JUDGE_ROLE: ModelSpec(judge_model, family(judge_model)),
    }
    budget = Budget(BudgetScope.ARTICLE, BudgetLimits(max_cost_usd=Decimal("1")))
    return LLMGateway(FakeProvider([]), roles, budget, Recorder())  # type: ignore[arg-type]


def test_writer_and_judge_must_be_different_models() -> None:
    with pytest.raises(ConfigurationError):
        _check_families(_gateway("nvidia/a", "nvidia/a"))


def test_same_family_different_model_is_allowed(caplog: pytest.LogCaptureFixture) -> None:
    _check_families(_gateway("nvidia/big", "nvidia/small"))
    assert "share a model family" in caplog.text
    _check_families(_gateway("nvidia/big", "google/small"))


UNCITED = "It is open source and free for everyone."


def repaired(*fixes: tuple[int, str, list[int]], title: str | None = None) -> str:
    sentences = [{"index": i, "text": t, "claim_ids": ids} for i, t, ids in fixes]
    return json.dumps({"title": title, "sentences": sentences})


def test_repair_rewrites_a_flagged_sentence_and_the_recheck_clears_its_flag() -> None:
    body = [*BODY, sentence(UNCITED, [])]
    draft = run([writer(body), all_true(30), repaired((29, GOOD, [0])), all_true(30)], repair=True)
    assert draft.draft is not None
    assert draft.draft.flags == ()
    assert UNCITED not in draft.draft.sections[0].paragraphs[0]


def test_repair_can_drop_a_body_sentence_no_claim_supports() -> None:
    body = [*BODY, sentence(UNCITED, [])]
    draft = run([writer(body), all_true(30), repaired((29, "", [])), all_true(29)], repair=True)
    assert draft.draft is not None
    assert draft.draft.flags == ()
    assert draft.draft.sections[0].paragraphs[0].count(GOOD) == 28


def test_repair_never_drops_the_dek() -> None:
    rejects_dek = judge(False, *([True] * 28))
    draft = run([writer(), rejects_dek, repaired((0, "", [])), rejects_dek], repair=True)
    assert draft.draft is not None
    assert draft.draft.dek == GOOD
    assert [f.section for f in draft.draft.flags] == [-1]


def test_repair_only_changes_flagged_sentences() -> None:
    body = [*BODY, sentence(UNCITED, [])]
    sneaky = repaired((29, GOOD, [0]), (1, "Nemotron won.", [0]))
    draft = run([writer(body), all_true(30), sneaky, all_true(30)], repair=True)
    assert draft.draft is not None
    assert "Nemotron won." not in draft.draft.sections[0].paragraphs[0]


def test_a_failed_repair_keeps_the_writer_sentences_and_their_flags() -> None:
    body = [*BODY, sentence(UNCITED, [])]
    draft = run([writer(body), all_true(30)], repair=True)  # no reply queued for the repair
    assert draft.status is DraftStatus.DRAFTED
    assert draft.draft is not None
    assert [f.text for f in draft.draft.flags] == [UNCITED]


def test_repair_rewrites_an_overreaching_title() -> None:
    fix = repaired(title="Nemotron scores 535.4 out of 600")
    draft = run(
        [writer(title="Nemotron beats the contest"), all_true(), fix, all_true()], repair=True
    )
    assert draft.draft is not None
    assert draft.draft.title == "Nemotron scores 535.4 out of 600"


def test_a_paper_title_that_still_overreaches_falls_back_to_the_paper_title() -> None:
    gateway = make_gateway([writer(title="Nemotron beats the contest"), all_true()])
    draft = _process_card(
        gateway, package(), ArticleTemplate.NEWS_BRIEF, RUN, "", "paper", "", repair=False
    )
    assert draft.draft is not None
    assert draft.draft.title == "Post"


def test_an_overreaching_title_without_a_fallback_is_kept_with_a_note() -> None:
    draft = run([writer(title="Nemotron beats the contest"), all_true()])
    assert draft.draft is not None
    assert draft.draft.title == "Nemotron beats the contest"
    assert "title: uses 'beats'" in draft.review_summary
