"""Pure arXiv helpers: paper ids, fetch candidates and results-first section selection.

No network code here; callers fetch (one request per URL) and pass the HTML in.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from lxml import html as lxml_html  # type: ignore[import-untyped]

MAX_DOCUMENT_CHARS = 30_000
FIRST_SECTION_CHARS = 3_000
MIN_PAPER_CHARS = 1_500

ARXIV_HOSTS = frozenset({"arxiv.org", "www.arxiv.org", "ar5iv.labs.arxiv.org", "ar5iv.org"})

_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Za-z]{2})?/\d{7})"
_PATH = re.compile(rf"^/(?:abs|pdf|html)/{_ID}(?:v\d+)?(?:\.pdf)?/?$")
_WANTED_HEADING = re.compile(
    r"result|experiment|evaluation|ablation|limitation|discussion|conclusion|analysis"
)
_ABSTRACT = '//*[contains(concat(" ", normalize-space(@class), " "), " ltx_abstract ")]'
_HEADINGS = "./h1|./h2|./h3|./h4|./h5|./h6"


@dataclass(frozen=True)
class PaperText:
    text: str
    has_results: bool


def is_arxiv_host(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() in ARXIV_HOSTS


def arxiv_id(url: str) -> str | None:
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in ARXIV_HOSTS:
        return None
    match = _PATH.match(parts.path)
    return match.group(1) if match else None


def candidate_urls(paper_id: str) -> tuple[str, ...]:
    return (
        f"https://arxiv.org/html/{paper_id}",
        f"https://ar5iv.labs.arxiv.org/html/{paper_id}",
    )


def _squash(text: str) -> str:
    return " ".join(text.split())


def select_sections(html: str, limit: int = MAX_DOCUMENT_CHARS) -> PaperText | None:
    """Abstract, a capped first section, then results/limitations-like sections in order."""
    try:
        root = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return None
    for junk in root.xpath("//script|//style"):
        junk.drop_tree()

    pieces: list[str] = []
    taken: list[object] = []

    for abstract in root.xpath(_ABSTRACT)[:1]:
        pieces.append(_squash(abstract.text_content()))
        taken.append(abstract)

    sections = root.xpath("//section")
    if sections:
        first = sections[0]
        pieces.append(_squash(first.text_content())[:FIRST_SECTION_CHARS])
        taken.append(first)

    has_results = False
    for section in sections[1:]:
        if any(ancestor in taken for ancestor in section.iterancestors()):
            continue
        heading = section.xpath(_HEADINGS)
        if not heading or not _WANTED_HEADING.search(_squash(heading[0].text_content()).lower()):
            continue
        has_results = True
        taken.append(section)
        pieces.append(_squash(section.text_content()))

    kept: list[str] = []
    remaining = limit
    for piece in pieces:
        if remaining <= 0:
            break
        if not piece:
            continue
        piece = piece[:remaining]
        kept.append(piece)
        remaining -= len(piece) + 2
    text = "\n\n".join(kept)
    if len(text) < MIN_PAPER_CHARS:
        return None
    return PaperText(text=text, has_results=has_results)
