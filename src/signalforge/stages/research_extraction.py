"""Clean-text extraction and the mechanical evidence checks for research (FR-06).

The mechanical span check catches a hallucinated quote before it ever reaches
FR-08's LLM judge: cheap, exact, and it never needs a model call.
"""

import math
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlsplit

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


_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_ARXIV_ID = re.compile(r"^/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$")
_REPO_PATH = re.compile(r"^/[^/]+/[^/]+/?$")
# Repackaged weights (quantised builds) repeat the model card, so they add nothing.
_REPACKAGED = re.compile(r"gguf|awq|gptq|mlx|onnx", re.IGNORECASE)
# Site sections that look like "org/name" but are not model repos.
_HF_NON_MODEL_PATHS = frozenset(
    {
        "blog", "changelog", "datasets", "docs", "enterprise", "join", "learn", "login",
        "models", "new", "organizations", "papers", "posts", "pricing", "settings",
        "spaces", "tasks",
    }
)  # fmt: skip
# Lower rank is fetched first: papers, then model cards, then model repos, then code.
_PAPER, _MODEL_CARD, _MODEL_REPO, _CODE = range(4)


@dataclass(frozen=True)
class ReferenceLink:
    """A paper, model card or repo the primary source cites, to fetch as evidence."""

    url: str
    fetch_urls: tuple[str, ...]


def _rank(url: str) -> tuple[int, ReferenceLink] | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path
    if host == "arxiv.org" and (match := _ARXIV_ID.match(path)):
        paper = match.group(1)
        # The HTML render carries the full text; the abstract page is the fallback.
        abs_url = f"https://arxiv.org/abs/{paper}"
        return _PAPER, ReferenceLink(abs_url, (f"https://arxiv.org/html/{paper}", abs_url))
    if host == "openreview.net" and path.startswith("/forum"):
        return _PAPER, ReferenceLink(url, (url,))
    if host == "huggingface.co" and path.startswith("/papers/"):
        return _PAPER, ReferenceLink(url, (url,))
    if re.search(r"model[_-]card", path, re.IGNORECASE):
        return _MODEL_CARD, ReferenceLink(url, (url,))
    if (
        host == "huggingface.co"
        and _REPO_PATH.match(path)
        and not _REPACKAGED.search(path)
        and path.split("/")[1] not in _HF_NON_MODEL_PATHS
    ):
        return _MODEL_REPO, ReferenceLink(url, (url,))
    if host == "github.com" and _REPO_PATH.match(path):
        return _CODE, ReferenceLink(url, (url,))
    return None


def reference_links(html: str, base_url: str, *, limit: int) -> list[ReferenceLink]:
    """Up to ``limit`` papers, model cards and repos linked from ``html``, best first.

    Deterministic: the same page always yields the same links in the same order.
    """
    base = urlsplit(base_url)
    ranked: dict[str, tuple[int, int, ReferenceLink]] = {}
    for position, raw in enumerate(_HREF.findall(html)):
        absolute = urljoin(base_url, unescape(raw.strip()))
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"}:
            continue
        clean = parts._replace(query="", fragment="").geturl().rstrip("/")
        if parts.hostname == base.hostname and parts.path.rstrip("/") == base.path.rstrip("/"):
            continue
        hit = _rank(clean)
        if hit is not None and hit[1].url not in ranked:
            ranked[hit[1].url] = (hit[0], position, hit[1])
    ordered = sorted(ranked.values(), key=lambda item: (item[0], item[1]))
    return [link for _, _, link in ordered[:limit]]


def page_title(html: str) -> str | None:
    """The document's <title>, whitespace-collapsed, or None."""
    match = _TITLE.search(html)
    if not match:
        return None
    title = " ".join(unescape(match.group(1)).split())
    return title or None
