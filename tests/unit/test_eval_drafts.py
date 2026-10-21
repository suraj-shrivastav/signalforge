"""The golden fixtures load, stay small, and the scorer reads a draft correctly."""

import uuid
from datetime import UTC, datetime

from apps.worker import eval_drafts
from apps.worker.eval_drafts import load_fixtures, score, trim_package

from signalforge.core.artifacts.article import (
    ArticleBody,
    ArticleCover,
    ArticleDraft,
    ArticleFlag,
    ArticleSection,
    ArticleTemplate,
    DraftStatus,
    FlagKind,
)
from signalforge.core.artifacts.research import (
    ResearchClaim,
    ResearchDocument,
    ResearchPackage,
    ResearchStatus,
)
from signalforge.stages.draft_extraction import span_documents


def test_golden_fixtures_load_and_every_quote_is_in_its_trimmed_documents() -> None:
    fixtures = load_fixtures()
    assert fixtures, "tests/golden must hold exported research packages"
    for fx in fixtures:
        package = fx["package"]
        assert package.claims
        for claim in package.claims:
            quote_found = [
                doc.text for i, doc in enumerate(package.documents) if i in claim.document_indices
            ]
            assert any(claim.evidence_span.strip() in text for text in quote_found), fx["name"]


def test_trim_keeps_quotes_and_drops_distant_text() -> None:
    far = "filler sentence. " * 400
    text = f"{far}KEY FACT here.{far}"
    package = ResearchPackage(
        card_id=uuid.uuid4(),
        status=ResearchStatus.RESEARCHED,
        documents=(
            ResearchDocument(
                url="https://example.com/a",
                title="A",
                source_label="a",
                is_primary=True,
                raw_text_ref="r",
                text=text,
                fetched_at=datetime.now(UTC),
            ),
        ),
        claims=(ResearchClaim(text="c", evidence_span="KEY FACT here.", document_indices=(0,)),),
    )
    trimmed = trim_package(package)
    assert len(trimmed.documents[0].text) < len(text) / 5
    assert "KEY FACT here." in trimmed.documents[0].text
    claim = trimmed.claims[0]
    from signalforge.core.artifacts.article import ArticleClaim

    cited = ArticleClaim(text="c", evidence_span=claim.evidence_span, document_indices=(0,))
    assert span_documents(cited, trimmed.documents) == frozenset({0})


def test_score_counts_flags_by_kind() -> None:
    flags = tuple(
        ArticleFlag(section=0, paragraph=0, text=f"s{i}", kind=kind)
        for i, kind in enumerate([FlagKind.UNCITED, FlagKind.NUMBER, FlagKind.UNSUPPORTED])
    )
    body = ArticleBody(
        title="T",
        dek="One two three.",
        sections=(ArticleSection(heading="H", paragraphs=("Alpha beta. Gamma delta.",)),),
        cover=ArticleCover(alt="a"),
        flags=flags,
    )
    result = ArticleDraft(
        card_id=uuid.uuid4(),
        status=DraftStatus.DRAFTED,
        template=ArticleTemplate.NEWS_BRIEF,
        draft=body,
    )
    metrics = score(result)
    assert (metrics["uncited"], metrics["number_mismatch"], metrics["judge_rejected"]) == (1, 1, 1)
    assert metrics["in_band"] is False
    assert metrics["sentences"] == 2


def test_number_mutation_changes_the_first_number_only() -> None:
    assert eval_drafts._mutate_number("scored 535.4 of 600") == "scored 542.4 of 600"
    assert eval_drafts._mutate_number("no digits") is None
