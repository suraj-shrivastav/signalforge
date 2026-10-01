import pytest
from pydantic import ValidationError

from signalforge.core.artifacts.research import ClaimStatus, ResearchClaim
from signalforge.stages.research_extraction import extract_clean_text, merge_claims, span_exists

_HTML = """
<html><body>
<nav>Home | About | Contact</nav>
<article><h1>Model X released</h1><p>Model X reaches 90% accuracy on benchmark Y.</p></article>
<footer>Copyright 2026</footer>
</body></html>
"""

_SAME: tuple[float, ...] = (1.0, 0.0)
_DISAGREE: tuple[float, ...] = (0.7, 0.7)  # cosine with _SAME is ~0.7, between the two thresholds
_UNRELATED: tuple[float, ...] = (0.0, 1.0)


def _claim(text: str, span: str | None = None, indices: tuple[int, ...] = (0,)) -> ResearchClaim:
    return ResearchClaim(text=text, evidence_span=span or text, document_indices=indices)


def test_extract_clean_text_drops_nav_and_footer() -> None:
    text = extract_clean_text(_HTML)
    assert text is not None
    assert "90% accuracy" in text
    assert "Home | About | Contact" not in text
    assert "Copyright 2026" not in text


def test_extract_clean_text_drops_reader_comments() -> None:
    body = "".join(
        f"<p>Paragraph {i}: Model X was evaluated on benchmark Y with a new protocol.</p>"
        for i in range(8)
    )
    html = (
        f"<html><body><article><h1>Model X</h1>{body}</article>"
        "<div class='comments'><p>Great post! Visit my site.</p></div></body></html>"
    )
    text = extract_clean_text(html)
    assert text is not None
    assert "Paragraph 7:" in text
    assert "Great post" not in text


def test_extract_clean_text_returns_none_for_empty_input() -> None:
    assert extract_clean_text("<html><body></body></html>") is None


def test_span_exists_exact_match() -> None:
    assert span_exists("Model X reaches 90% accuracy", "Model X reaches 90% accuracy on Y.")


def test_span_exists_false_for_paraphrase() -> None:
    assert not span_exists("Model X hits ninety percent", "Model X reaches 90% accuracy on Y.")


def test_span_exists_false_for_blank_span() -> None:
    assert not span_exists("   ", "Model X reaches 90% accuracy on Y.")
    assert not span_exists("", "Model X reaches 90% accuracy on Y.")


def test_merge_claims_combines_similar_embeddings() -> None:
    a = _claim("X does Y", "X does Y")
    b = _claim("X does Y, roughly", "X does Y exactly", indices=(1,))
    merged, gaps = merge_claims([(0, a), (1, b)], [_SAME, _SAME])
    assert len(merged) == 1
    assert merged[0].document_indices == (0, 1)
    assert gaps == ""


def test_merge_claims_keeps_dissimilar_claims_separate() -> None:
    merged, gaps = merge_claims(
        [(0, _claim("X does Y")), (0, _claim("X does Z"))], [_SAME, _UNRELATED]
    )
    assert len(merged) == 2
    assert gaps == ""


def test_merge_claims_flags_disagreement_band() -> None:
    merged, gaps = merge_claims(
        [(0, _claim("X does Y")), (1, _claim("X does not do Y"))], [_SAME, _DISAGREE]
    )
    assert len(merged) == 2
    assert "Document 0 and Document 1" in gaps


def test_merge_claims_uses_candidate_index_sorted_and_unique() -> None:
    claim = _claim("X does Y", indices=(9,))
    merged, _ = merge_claims([(3, claim), (1, claim), (3, claim)], [_SAME, _SAME, _SAME])
    assert merged[0].document_indices == (1, 3)


def test_merge_claims_preserves_first_seen_order_and_first_claim_fields() -> None:
    first = ResearchClaim(
        text="B claim",
        evidence_span="B span",
        document_indices=(0,),
        status=ClaimStatus.SUPPORTED,
    )
    candidates = [
        (0, first),
        (1, _claim("A claim")),
        (2, _claim("B claim", "other span")),
        (0, _claim("C")),
    ]
    embeddings: list[tuple[float, ...]] = [_SAME, _UNRELATED, _SAME, (0.0, -1.0)]
    merged, _ = merge_claims(candidates, embeddings)
    assert [c.text for c in merged] == ["B claim", "A claim", "C"]
    assert merged[0].evidence_span == "B span"
    assert merged[0].status is ClaimStatus.SUPPORTED
    assert merged[0].document_indices == (0, 2)


def test_merge_claims_empty_returns_empty_tuple() -> None:
    assert merge_claims([], []) == ((), "")


def test_merge_claims_rejects_negative_document_index() -> None:
    with pytest.raises(ValidationError):
        merge_claims([(-1, _claim("X does Y"))], [_SAME])
