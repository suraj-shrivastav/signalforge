import pytest

from signalforge.core.errors import ProviderRejectedError
from signalforge.stages.research import _collect_primary, _Collector, _fetch_reference
from signalforge.stages.research_arxiv import (
    arxiv_id,
    candidate_urls,
    select_sections,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://arxiv.org/abs/2610.40325", "2610.40325"),
        ("https://arxiv.org/abs/2610.40325v2", "2610.40325"),
        ("https://arxiv.org/pdf/2610.40325v3.pdf", "2610.40325"),
        ("https://arxiv.org/pdf/2610.40325", "2610.40325"),
        ("https://arxiv.org/html/2610.40325v1", "2610.40325"),
        ("https://ar5iv.labs.arxiv.org/html/2610.40325", "2610.40325"),
        ("https://example.com/abs/2610.40325", None),
        ("https://arxiv.org/list/cs.AI/recent", None),
    ],
)
def test_arxiv_id_forms(url: str, expected: str | None) -> None:
    assert arxiv_id(url) == expected


def test_candidate_urls_order() -> None:
    assert candidate_urls("2610.40325") == (
        "https://arxiv.org/html/2610.40325",
        "https://ar5iv.labs.arxiv.org/html/2610.40325",
    )


def _section(title: str, body: str) -> str:
    return f'<section class="ltx_section"><h2 class="ltx_title">{title}</h2><p>{body}</p></section>'


def _paper(*sections: tuple[str, str], abstract: str = "Abstract text. " * 20) -> str:
    body = "".join(_section(t, b) for t, b in sections)
    return (
        f'<html><body><article><div class="ltx_abstract"><p>{abstract}</p></div>{body}'
        "</article></body></html>"
    )


RESULTS_PAPER = _paper(
    ("1 Introduction", "Intro words. " * 40),
    ("2 Related Work", "UNRELATED prior work. " * 40),
    ("4 Results", "Accuracy rose to 91.2 percent. " * 20),
    ("5 Limitations", "It fails on long inputs. " * 20),
)


def test_select_sections_keeps_abstract_intro_results_limitations() -> None:
    paper = select_sections(RESULTS_PAPER)
    assert paper is not None
    assert paper.has_results is True
    assert "Abstract text." in paper.text
    assert "Intro words." in paper.text
    assert "91.2 percent" in paper.text
    assert "long inputs" in paper.text
    assert "UNRELATED" not in paper.text


def test_first_section_is_capped() -> None:
    paper = select_sections(_paper(("1 Introduction", "q" * 9000), ("2 Results", "z" * 2000)))
    assert paper is not None
    assert paper.text.count("q") <= 3000


def test_select_sections_respects_limit() -> None:
    paper = select_sections(RESULTS_PAPER, limit=2000)
    assert paper is not None
    assert len(paper.text) <= 2000


def test_no_results_like_heading_means_no_results() -> None:
    paper = select_sections(
        _paper(("1 Introduction", "words " * 300), ("2 Method", "more words " * 300))
    )
    assert paper is not None
    assert paper.has_results is False


def test_tiny_page_gives_none() -> None:
    assert select_sections(_paper(("1 Introduction", "short"), abstract="tiny")) is None


class FakeFetcher:
    def __init__(self, pages: dict[str, str | Exception]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, int | None]] = []

    def fetch_html(self, url: str, *, max_attempts: int | None = None) -> str:
        self.calls.append((url, max_attempts))
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page


class _Signal:
    def __init__(self, url: str) -> None:
        self.canonical_url = url
        self.title = "A paper"
        self.source = "arxiv"


ABS = "https://arxiv.org/abs/2610.40325"
HTML_URL = "https://arxiv.org/html/2610.40325"
AR5IV = "https://ar5iv.labs.arxiv.org/html/2610.40325"
ABS_PAGE = (
    "<html><body><article><p>" + "Abstract only page words. " * 80 + "</p></article></body></html>"
)


def test_second_candidate_used_one_call_per_url_and_failure_noted() -> None:
    fetcher = FakeFetcher({HTML_URL: ProviderRejectedError("406"), AR5IV: RESULTS_PAPER})
    collector = _Collector()
    html = _collect_primary(fetcher, _Signal(ABS), collector)  # type: ignore[arg-type]
    assert html == RESULTS_PAPER
    assert fetcher.calls == [(HTML_URL, 1), (AR5IV, 1)]
    assert collector.primary_full_text is True
    assert "91.2 percent" in collector.documents[0].text
    assert any(HTML_URL in n for n in collector.notes)


def test_all_candidates_failing_falls_back_to_abs_page_single_attempt() -> None:
    fetcher = FakeFetcher(
        {HTML_URL: ProviderRejectedError("406"), AR5IV: ProviderRejectedError("404"), ABS: ABS_PAGE}
    )
    collector = _Collector()
    html = _collect_primary(fetcher, _Signal(ABS), collector)  # type: ignore[arg-type]
    assert html == ABS_PAGE
    assert fetcher.calls == [(HTML_URL, 1), (AR5IV, 1), (ABS, 1)]
    assert collector.primary_full_text is False


def test_non_arxiv_primary_is_unchanged() -> None:
    url = "https://example.com/post"
    fetcher = FakeFetcher({url: ABS_PAGE})
    collector = _Collector()
    _collect_primary(fetcher, _Signal(url), collector)  # type: ignore[arg-type]
    assert fetcher.calls == [(url, None)]


def test_arxiv_reference_reads_sections() -> None:
    fetcher = FakeFetcher({HTML_URL: RESULTS_PAPER})
    fetched = _fetch_reference(fetcher, (HTML_URL, ABS))
    assert fetched is not None
    assert "91.2 percent" in fetched[1]
    assert "UNRELATED" not in fetched[1]
    assert fetcher.calls == [(HTML_URL, 1)]
