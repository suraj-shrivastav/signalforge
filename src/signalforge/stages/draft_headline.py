"""Cover facts for a draft: kind, source label and a headline number checked by code.

Pure functions, no I/O and no model calls. The writer only proposes a headline; it is kept
only when the number and its unit are found in a claim that ended ``verified`` or ``supported``.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from urllib.parse import urlsplit

from signalforge.core.artifacts.article import ArticleClaim, ArticleHeadline
from signalforge.core.artifacts.research import ClaimStatus

MAX_VALUE = 8
MAX_UNIT = 34
MAX_TAKEAWAY = 80
MAX_LABEL = 24

_GOOD = frozenset({ClaimStatus.VERIFIED, ClaimStatus.SUPPORTED})
_BENCH = re.compile(r"\b(benchmark|bench|eval)\b", re.IGNORECASE)
_HOSTS = {
    "arxiv.org": "arXiv",
    "huggingface.co": "Hugging Face",
    "github.com": "GitHub",
    "news.ycombinator.com": "Hacker News",
}
_NUMBER = re.compile(r"\d(?:[\d.,]*\d)?")
_WORD_JUNK = re.compile(r"[^\w]+")


def derive_kind(source_type: str, title: str, canonical_url: str) -> str:
    """What sort of item this is, from the signal's source type (first match wins)."""
    if source_type == "paper":
        return "benchmark" if _BENCH.search(title) else "paper"
    if source_type == "model":
        return "model"
    if source_type == "repo":
        return "tool"
    if source_type == "community":
        return "discussion"
    if source_type == "blog" and "/releases" in canonical_url:
        return "release"
    return "news"


def derive_source_label(source_url: str | None) -> str:
    """Short reader-facing name of the first source's host; empty without a source."""
    if not source_url:
        return ""
    host = (urlsplit(source_url).hostname or "").lower().removeprefix("www.")
    return _HOSTS.get(host, host)[:MAX_LABEL]


def _cut(text: str, limit: int) -> str:
    """Cut at a word boundary to at most ``limit`` characters."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] != " " and " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:.-")


def _unit_ok(unit: str, claim_text: str) -> bool:
    low = claim_text.lower()
    for word in unit.lower().split():
        word = _WORD_JUNK.sub("", word)
        if len(word) >= 3 and word not in low:
            return False
    return True


def validate_headline(
    pick: object,
    *,
    claims: Sequence[ArticleClaim],
    index_of: Mapping[int, int],
    title: str,
    dek: str,
) -> ArticleHeadline | None:
    """The writer's pick as a headline, or None if any check fails.

    ``pick`` is a dict with ``claim_id``, ``value``, ``unit``, ``direction`` and ``takeaway``.
    ``claims`` carry their final statuses; ``index_of`` maps a research claim id to its index.
    """
    if not isinstance(pick, dict):
        return None
    claim_id = pick.get("claim_id")
    if isinstance(claim_id, bool) or not isinstance(claim_id, int) or claim_id not in index_of:
        return None
    index = index_of[claim_id]
    if not 0 <= index < len(claims):
        return None
    claim = claims[index]
    if claim.status not in _GOOD:
        return None
    value, unit = pick.get("value"), pick.get("unit", "")
    if not isinstance(value, str) or not value or len(value) > MAX_VALUE:
        return None
    if value not in claim.text:
        return None
    if not isinstance(unit, str) or len(unit) > MAX_UNIT or not _unit_ok(unit, claim.text):
        return None
    raw_direction = pick.get("direction")
    direction: Literal["up", "down", "none"] = "none"
    if raw_direction == "up":
        direction = "up"
    elif raw_direction == "down":
        direction = "down"
    return ArticleHeadline(
        value=value,
        unit=unit,
        direction=direction,
        takeaway=_takeaway(pick.get("takeaway"), title, dek, claims),
        claim_index=index,
    )


def _takeaway(raw: Any, title: str, dek: str, claims: Sequence[ArticleClaim]) -> str:
    if isinstance(raw, str) and raw.strip() and len(raw.strip()) <= MAX_TAKEAWAY:
        text = raw.strip()
        known = " ".join([title, dek, *(c.text for c in claims)])
        if all(token in known for token in _NUMBER.findall(text)):
            return text
    return _cut(dek, MAX_TAKEAWAY)
