"""Deterministic publishing helpers: slugs and meta descriptions. No DB, no LLM."""

import re
import unicodedata
from collections.abc import Callable

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_SLUG_MAX = 80
META_DESCRIPTION_MAX = 155


def slugify(title: str) -> str:
    """Lowercase ASCII words joined by hyphens, cut at a word boundary."""
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(slug) > _SLUG_MAX:
        cut = slug[:_SLUG_MAX]
        slug = cut.rsplit("-", 1)[0] if "-" in cut else cut
    return slug or "article"


def unique_slug(base: str, exists: Callable[[str], bool]) -> str:
    """``base``, or ``base-2``, ``base-3`` ... for the first one ``exists`` does not know."""
    if not exists(base):
        return base
    number = 2
    while exists(f"{base}-{number}"):
        number += 1
    return f"{base}-{number}"


def meta_description(dek: str, limit: int = META_DESCRIPTION_MAX) -> str:
    """The dek, whitespace-normalised and cut at a word boundary to fit a search snippet."""
    text = " ".join(dek.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    return cut.rsplit(" ", 1)[0].rstrip(",;:.") + "..."
