from datetime import UTC, datetime

import pytest

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleSection,
    ArticleTemplate,
)
from signalforge.core.artifacts.research import (
    ClaimStatus,
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
)
from signalforge.stages.draft_extraction import (
    assign_status,
    flagged_spans,
    is_conflicting,
    publish_gate,
    select_template,
    span_documents,
    title_overreach,
)


def doc(url: str, *, primary: bool = False, text: str = "alpha beta gamma") -> ResearchDocument:
    return ResearchDocument(
        url=url,
        title="t",
        source_label="s",
        is_primary=primary,
        raw_text_ref="r",
        text=text,
        fetched_at=datetime.now(UTC),
    )


def body(paragraph: str, title: str = "Title") -> ArticleBody:
    return ArticleBody(
        title=title,
        dek="Dek",
        sections=(ArticleSection(heading="H", paragraphs=(paragraph,)),),
        cover=ArticleCover(alt="Alt"),
    )


@pytest.mark.parametrize(
    ("source_type", "card_format", "topics", "title", "expected"),
    [
        ("paper", "comparison", ["release"], "Released", ArticleTemplate.PAPER_BREAKDOWN),
        ("blog", "comparison", [], "Released", ArticleTemplate.COMPARISON),
        ("blog", "explainer", ["Comparison"], "", ArticleTemplate.COMPARISON),
        ("community", "explainer", ["launch"], "", ArticleTemplate.NEWS_BRIEF),
        ("community", "explainer", [], "Acme launches v2", ArticleTemplate.NEWS_BRIEF),
        ("blog", "deep_dive", [], "EmbeddingGemma 2: an open model", ArticleTemplate.EXPLAINER),
        ("blog", "deep_dive", [], "Acme launches v2", ArticleTemplate.NEWS_BRIEF),
        ("community", "deep_dive", ["agents"], "How agents plan", ArticleTemplate.EXPLAINER),
    ],
)
def test_select_template_first_match_wins(
    source_type: str, card_format: str, topics: list[str], title: str, expected: ArticleTemplate
) -> None:
    assert (
        select_template(
            source_type=source_type, card_format=card_format, topics=topics, title=title
        )
        is expected
    )


def test_span_documents_skips_missing_and_out_of_range_indices() -> None:
    documents = [doc("https://a.com", text="has the quote"), doc("https://b.com")]
    claim = ArticleClaim(text="c", evidence_span="the quote", document_indices=(0, 1, 7))
    assert span_documents(claim, documents) == frozenset({0})


@pytest.mark.parametrize(
    ("span_docs", "judge", "conflicting", "expected"),
    [
        (frozenset(), True, False, ClaimStatus.UNVERIFIED),
        (frozenset({1}), True, True, ClaimStatus.CONFLICTING),
        (frozenset({1}), False, False, ClaimStatus.UNCERTAIN),
        (frozenset({0}), True, False, ClaimStatus.VERIFIED),
        (frozenset({1, 2}), True, False, ClaimStatus.VERIFIED),
        (frozenset({1}), True, False, ClaimStatus.SUPPORTED),
        (frozenset({1, 3}), True, False, ClaimStatus.SUPPORTED),
    ],
)
def test_assign_status_table(
    span_docs: frozenset[int], judge: bool, conflicting: bool, expected: ClaimStatus
) -> None:
    documents = [
        doc("https://primary.com", primary=True),
        doc("https://one.com/a"),
        doc("https://two.com"),
        doc("https://one.com/b"),
    ]
    status = assign_status(
        span_docs=span_docs, judge_supported=judge, conflicting=conflicting, documents=documents
    )
    assert status is expected


def test_conflicting_uses_research_disagreement_note() -> None:
    package = ResearchPackage(
        card_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
        claims=(
            ResearchClaim(text="X is fast", evidence_span="X runs fast", document_indices=(0,)),
            ResearchClaim(text="Y ships", evidence_span="Y shipped", document_indices=(1,)),
        ),
        gaps_and_disagreements="Document 0 and Document 1 report conflicting claims near: "
        "'X is fast'.",
    )
    flagged = flagged_spans(package)
    hit = ArticleClaim(text="c", evidence_span="X runs fast", document_indices=(0,))
    miss = ArticleClaim(text="c", evidence_span="Y shipped", document_indices=(1,))
    assert (is_conflicting(hit, flagged), is_conflicting(miss, flagged)) == (True, False)


def test_gate_passes_clean_draft_in_band() -> None:
    assert publish_gate(body(" ".join(["w"] * 299)), ArticleTemplate.NEWS_BRIEF) == []


@pytest.mark.parametrize(
    ("paragraph", "reason"),
    [
        ("one \u2014 two", "em dash"),
        ("one \u2013 two", "em dash or an en dash"),
        ("We tested it twice", "banned authorship"),
        ("As an AI I think", "banned authorship"),
    ],
)
def test_gate_rejects_style_violations(paragraph: str, reason: str) -> None:
    padded = paragraph + " " + " ".join(["w"] * 300)
    failures = publish_gate(body(padded), ArticleTemplate.NEWS_BRIEF)
    assert any(reason in failure for failure in failures)


def test_gate_allows_en_dash_in_a_range() -> None:
    padded = "From 2020\u20132024. " + " ".join(["w"] * 300)
    assert publish_gate(body(padded), ArticleTemplate.NEWS_BRIEF) == []


def test_gate_checks_title_and_length_band() -> None:
    failures = publish_gate(body("too short", title="A \u2014 B"), ArticleTemplate.EXPLAINER)
    assert len(failures) == 2
    assert "outside the explainer band 700-1000" in failures[1]


def test_title_overreach_lists_strong_words_the_claims_never_use() -> None:
    assert title_overreach("LFM3 Beats Larger Models", "LFM3 outperforms larger models") == [
        "beats"
    ]
    assert title_overreach("Only Frontier Models Can Reliably Investigate", "") == [
        "only",
        "reliably",
    ]
    assert title_overreach("Method outperforms baselines", "It outperforms the baselines") == []
    assert title_overreach("A plain title", "") == []
