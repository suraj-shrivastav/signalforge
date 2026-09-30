"""Clean-text extraction and the mechanical evidence checks for research (FR-06).

The mechanical span check catches a hallucinated quote before it ever reaches
FR-08's LLM judge: cheap, exact, and it never needs a model call.
"""

from collections import defaultdict

import trafilatura

from signalforge.core.artifacts.research import ResearchClaim

# Evidence spans must come from the article body. The default recall-leaning fallback
# keeps nav chrome on short pages, so a span could "match" boilerplate.
_FAVOR_PRECISION = True
# Reader comments are third-party text, not the source's claims.
_INCLUDE_COMMENTS = False


def extract_clean_text(html: str) -> str | None:
    """Return the main article text of ``html``, or ``None`` if nothing usable is found."""
    text = trafilatura.extract(
        html, favor_precision=_FAVOR_PRECISION, include_comments=_INCLUDE_COMMENTS
    )
    return text if text else None


def span_exists(span: str, document_text: str) -> bool:
    """Return True if ``span``, stripped and non-blank, appears verbatim in ``document_text``."""
    needle = span.strip()
    return bool(needle) and needle in document_text


def merge_claims(candidates: list[tuple[int, ResearchClaim]]) -> tuple[ResearchClaim, ...]:
    """Merge claims whose stripped ``text`` matches exactly, in first-seen order.

    Each candidate's int is its source document index and is the only input to the
    merged ``document_indices`` (sorted, unique). Other fields come from the first claim.
    """
    by_text: dict[str, list[tuple[int, ResearchClaim]]] = defaultdict(list)
    for doc_index, claim in candidates:
        by_text[claim.text.strip()].append((doc_index, claim))

    merged: list[ResearchClaim] = []
    for group in by_text.values():
        indices = tuple(sorted({doc_index for doc_index, _ in group}))
        first_claim = group[0][1]
        # model_copy(update=...) skips validation; rebuilding keeps the ge=0 index rule.
        merged.append(
            ResearchClaim.model_validate({**first_claim.model_dump(), "document_indices": indices})
        )
    return tuple(merged)
