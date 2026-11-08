"""Sufficiency gate: when a research package holds enough evidence to be 'researched'."""

from collections.abc import Sequence

from signalforge.core.artifacts.research import ResearchClaim

MIN_CLAIMS = 3
GAP_QUERY_SUFFIXES = ("benchmark results", "limitations criticism")
EXTRA_ROUND_RESULTS = 2  # results per gap query
MAX_DOCUMENTS = 8
MAX_EXTRA_DOCUMENTS = 4


def has_numeric_claim(claims: Sequence[ResearchClaim]) -> bool:
    return any(ch.isdigit() for claim in claims for ch in claim.text)


def is_sufficient(
    claims: Sequence[ResearchClaim], document_count: int, primary_full_text: bool
) -> bool:
    """At least MIN_CLAIMS claims, one with a digit, and independent or full-text evidence."""
    return (
        len(claims) >= MIN_CLAIMS
        and has_numeric_claim(claims)
        and (document_count >= 2 or primary_full_text)
    )


def gap_queries(title: str) -> tuple[str, ...]:
    return tuple(f"{title} {suffix}" for suffix in GAP_QUERY_SUFFIXES)
