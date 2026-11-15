from datetime import UTC, datetime

from apps.worker.quality_report import assess, below_floor, report

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleClaim,
    ArticleCover,
    ArticleSection,
    ArticleTemplate,
)

BODY = ArticleBody(
    title="Only this works",
    dek="A dek.",
    sections=(ArticleSection(heading="The problem", paragraphs=("This gap is large.",)),),
    claims=(ArticleClaim(text="It works.", evidence_span="s", document_indices=(0,)),),
    cover=ArticleCover(alt="a"),
)


def test_assess_finds_short_text_dangling_openers_and_strong_title_words() -> None:
    q = assess("slug", BODY, ArticleTemplate.PAPER_BREAKDOWN, 2)
    assert q.words == 6
    assert any("points back at nothing" in p for p in q.coherence)
    assert any("1 sentence" in p for p in q.coherence)
    assert q.overreach == ("only",)
    assert below_floor(q, 1.0)
    assert below_floor(q, 0.6)


def test_report_gives_shares_per_floor_ratio_and_a_row_per_article() -> None:
    q = assess("slug", BODY, ArticleTemplate.PAPER_BREAKDOWN, 2)
    text = report([q], datetime(2026, 11, 15, tzinfo=UTC))
    assert "Below 100% of the template minimum: 1 of 1" in text
    assert "Title uses a strong word no claim states: 1 of 1" in text
    assert "| slug | paper_breakdown | 6 |" in text
