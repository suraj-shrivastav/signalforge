"""Clean-text extraction and the mechanical evidence checks for research (FR-06).

The mechanical span check catches a hallucinated quote before it ever reaches
FR-08's LLM judge: cheap, exact, and it never needs a model call.
"""

import math

import trafilatura

from signalforge.core.artifacts.research import ResearchClaim

# Evidence spans must come from the article body. The default recall-leaning fallback
# keeps nav chrome on short pages, so a span could "match" boilerplate.
_FAVOR_PRECISION = True
# Reader comments are third-party text, not the source's claims.
_INCLUDE_COMMENTS = False

# Fixed thresholds, tuned by eye; revisit once the trust ramp has real runs to look at.
MERGE_SIMILARITY = 0.85
DISAGREEMENT_SIMILARITY = 0.60


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


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def merge_claims(
    candidates: list[tuple[int, ResearchClaim]], embeddings: list[tuple[float, ...]]
) -> tuple[tuple[ResearchClaim, ...], str]:
    """Merge near-duplicate claims by embedding similarity; flag likely disagreements.

    ``embeddings[i]`` is the embedding of ``candidates[i].text``, same order, same length.
    Claims with similarity >= MERGE_SIMILARITY are merged (union ``document_indices``).
    Claims with similarity in [DISAGREEMENT_SIMILARITY, MERGE_SIMILARITY) are left distinct
    but noted as a likely disagreement in the returned free-text summary.
    """
    n = len(candidates)
    assigned = [-1] * n
    groups: list[list[int]] = []
    disagreements: list[str] = []
    for i in range(n):
        if assigned[i] != -1:
            continue
        group_index = len(groups)
        groups.append([i])
        assigned[i] = group_index
        for j in range(i + 1, n):
            if assigned[j] != -1:
                continue
            sim = _cosine(embeddings[i], embeddings[j])
            if sim >= MERGE_SIMILARITY:
                groups[group_index].append(j)
                assigned[j] = group_index
            elif sim >= DISAGREEMENT_SIMILARITY:
                doc_i, doc_j = candidates[i][0], candidates[j][0]
                if doc_i != doc_j:
                    disagreements.append(
                        f"Document {doc_i} and Document {doc_j} report conflicting claims "
                        f"near: '{candidates[i][1].text}'."
                    )

    merged: list[ResearchClaim] = []
    for group in groups:
        indices = tuple(sorted({candidates[i][0] for i in group}))
        first_claim = candidates[group[0]][1]
        # model_copy(update=...) skips validation; rebuilding keeps the ge=0 index rule.
        merged.append(
            ResearchClaim.model_validate({**first_claim.model_dump(), "document_indices": indices})
        )
    return tuple(merged), " ".join(disagreements)
