"""Kind, source label and headline validation are pure and never trust the writer."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from signalforge.core.artifacts.article import ArticleBody, ArticleClaim, ArticleTemplate
from signalforge.core.artifacts.research import (
    ClaimStatus,
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)
from signalforge.core.budget import Budget, BudgetLimits, BudgetScope
from signalforge.llm.gateway import LLMGateway
from signalforge.llm.providers import FakeProvider
from signalforge.llm.roles import ModelSpec
from signalforge.stages.draft import JUDGE_ROLE, WRITER_ROLE, _process_card
from signalforge.stages.draft_headline import (
    derive_kind,
    derive_source_label,
    validate_headline,
)


@pytest.mark.parametrize(
    ("source_type", "title", "url", "kind"),
    [
        ("paper", "A benchmark for agents", "https://arxiv.org/abs/1", "benchmark"),
        ("paper", "Agents in the wild", "https://arxiv.org/abs/1", "paper"),
        ("paper", "Benchmarking agents", "https://arxiv.org/abs/1", "paper"),
        ("paper", "An EVAL of agents", "https://arxiv.org/abs/1", "benchmark"),
        ("model", "Nemotron", "https://huggingface.co/x", "model"),
        ("repo", "Tool", "https://github.com/x/y", "tool"),
        ("community", "Ask HN", "https://news.ycombinator.com/item?id=1", "discussion"),
        ("blog", "v2", "https://github.com/x/y/releases/tag/v2", "release"),
        ("blog", "Post", "https://example.com/post", "news"),
        ("rss", "Thing", "https://example.com/", "news"),
    ],
)
def test_kind_mapping(source_type: str, title: str, url: str, kind: str) -> None:
    assert derive_kind(source_type, title, url) == kind


@pytest.mark.parametrize(
    ("url", "label"),
    [
        ("https://arxiv.org/abs/1", "arXiv"),
        ("https://www.huggingface.co/x", "Hugging Face"),
        ("https://github.com/x", "GitHub"),
        ("https://news.ycombinator.com/item?id=1", "Hacker News"),
        ("https://www.example.com/a", "example.com"),
        ("", ""),
        (None, ""),
    ],
)
def test_source_label(url: str | None, label: str) -> None:
    assert derive_source_label(url) == label


def claim(text: str, status: ClaimStatus = ClaimStatus.VERIFIED) -> ArticleClaim:
    return ArticleClaim(text=text, evidence_span="s", document_indices=(0,), status=status)


CLAIMS = (
    claim("The model scored 81.5% on the coding test."),
    claim("Latency fell 40% on long prompts.", ClaimStatus.UNCERTAIN),
    claim("It runs on 8 GPUs.", ClaimStatus.SUPPORTED),
)
INDEX = {10: 0, 11: 1, 12: 2}
DEK = "The model scored 81.5% on the coding test and costs less."


def pick(**over: Any) -> dict[str, Any]:
    base = {
        "claim_id": 10,
        "value": "81.5%",
        "unit": "on the coding test",
        "direction": "up",
        "takeaway": "A strong coding result at lower cost",
    }
    return {**base, **over}


def check(p: object) -> Any:
    return validate_headline(p, claims=CLAIMS, index_of=INDEX, title="Title", dek=DEK)


def test_valid_pick_is_kept() -> None:
    h = check(pick())
    assert (h.value, h.unit, h.direction, h.claim_index) == ("81.5%", "on the coding test", "up", 0)
    assert h.takeaway == "A strong coding result at lower cost"


def test_supported_claim_is_enough() -> None:
    assert check(pick(claim_id=12, value="8", unit="GPUs")).claim_index == 2


@pytest.mark.parametrize(
    "bad",
    [
        "81.5%",
        ["x"],
        None,
        pick(claim_id="10"),
        pick(claim_id=True),
        pick(claim_id=99),
        pick(claim_id=11, value="40%", unit="latency"),  # claim ended uncertain
        pick(value="82%"),
        pick(value=""),
        pick(value=5),
        pick(value="81.5% on the"),  # over 8 characters
        pick(unit="x" * 35),
        pick(unit="on the poetry test"),
        pick(unit=3),
    ],
)
def test_any_failed_check_drops_the_headline(bad: object) -> None:
    assert check(bad) is None


def test_unit_ignores_short_words_and_punctuation() -> None:
    assert check(pick(unit="on a (coding) test!")) is not None


@pytest.mark.parametrize("direction", ["sideways", None, 3])
def test_unknown_direction_becomes_none(direction: object) -> None:
    assert check(pick(direction=direction)).direction == "none"


@pytest.mark.parametrize("takeaway", ["", None, "x" * 81, "It got 99% better", 7])
def test_bad_takeaway_falls_back_to_the_dek(takeaway: object) -> None:
    got = check(pick(takeaway=takeaway)).takeaway
    assert got == "The model scored 81.5% on the coding test and costs less."
    assert len(got) <= 80


def test_takeaway_numbers_may_come_from_claims() -> None:
    assert check(pick(takeaway="Runs on 8 GPUs")).takeaway == "Runs on 8 GPUs"


def test_long_dek_is_cut_at_a_word_boundary() -> None:
    dek = "word " * 30
    h = validate_headline(
        pick(takeaway=""), claims=CLAIMS, index_of=INDEX, title="T", dek=dek.strip()
    )
    assert h is not None
    assert len(h.takeaway) <= 80
    assert not h.takeaway.endswith(" ")
    assert set(h.takeaway.split()) == {"word"}


def test_body_without_the_new_fields_still_loads() -> None:
    body = ArticleBody.model_validate(
        {
            "title": "T",
            "dek": "D",
            "sections": [{"heading": "H", "paragraphs": ["P."]}],
            "cover": {"alt": "a"},
        }
    )
    assert (body.kind, body.source_label, body.headline) == (None, "", None)


# --- wiring into the draft stage ---------------------------------------------------------

SPAN = "scored 535.4 out of 600 at the contest"
RESEARCH_CLAIM = "Nemotron scored 535.4 out of 600."
GOOD = "Nemotron scored 535.4 out of 600 at the contest."


class Recorder:
    def add(self, row: Any) -> None:
        pass


def pack() -> ResearchPackage:
    doc = ResearchDocument(
        url="https://arxiv.org/abs/1",
        title="t",
        source_label="arxiv.org",
        is_primary=True,
        raw_text_ref="r",
        text=f"Intro. The model {SPAN}, above the threshold.",
        fetched_at=datetime.now(UTC),
    )
    return ResearchPackage(
        card_id=uuid.uuid4(),
        status=ResearchStatus.RESEARCHED,
        documents=(doc,),
        claims=(ResearchClaim(text=RESEARCH_CLAIM, evidence_span=SPAN, document_indices=(0,)),),
    )


def draft(headline: Any = None, takeaway: Any = None, supported: bool = True) -> ArticleBody:
    sentence = {"text": GOOD, "claim_ids": [0]}
    reply: dict[str, Any] = {
        "title": "Nemotron scores",
        "dek": sentence,
        "sections": [
            {"heading": f"P{i}", "paragraphs": [{"sentences": [sentence] * 14}]} for i in range(2)
        ],
        "cover_alt": "Chart",
    }
    if headline is not None:
        reply["headline"] = headline
    if takeaway is not None:
        reply["takeaway"] = takeaway
    verdict = json.dumps({"sentences": [{"index": i, "supported": supported} for i in range(40)]})
    roles = {WRITER_ROLE: ModelSpec("a/w", "a"), JUDGE_ROLE: ModelSpec("b/j", "b")}
    budget = Budget(BudgetScope.ARTICLE, BudgetLimits(max_cost_usd=Decimal("1")))
    gateway = LLMGateway(FakeProvider([json.dumps(reply), verdict]), roles, budget, Recorder())  # type: ignore[arg-type]
    result = _process_card(
        gateway,
        pack(),
        ArticleTemplate.EXPLAINER,
        uuid.uuid4(),
        "",
        "paper",
        "https://arxiv.org/abs/1",
    )
    assert result.draft is not None
    return result.draft


PICK = {"claim_id": 0, "value": "535.4", "unit": "out of 600", "direction": "up"}


def test_draft_attaches_kind_label_and_a_valid_headline() -> None:
    body = draft(PICK, "Scores 535.4 at the contest")
    assert body.kind == "paper"
    assert body.source_label == "arXiv"
    assert body.headline is not None
    assert body.headline.value == "535.4"
    assert body.headline.takeaway == "Scores 535.4 at the contest"
    assert body.headline.claim_index == 0


def test_headline_is_dropped_when_the_claim_did_not_survive_the_judge() -> None:
    body = draft(PICK, "x", supported=False)
    assert body.headline is None
    assert body.kind == "paper"


def test_headline_is_dropped_when_the_value_is_not_in_the_claim() -> None:
    assert draft({**PICK, "value": "999"}).headline is None


def test_no_pick_still_gives_a_draft() -> None:
    body = draft()
    assert body.headline is None
    assert body.dek


@pytest.mark.parametrize("bad", ["535.4", ["535.4"], 7, {"claim_id": "0"}])
def test_malformed_pick_never_fails_the_draft(bad: Any) -> None:
    assert draft(bad, ["x"]).headline is None
