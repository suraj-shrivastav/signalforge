from datetime import UTC, datetime

import pytest

from signalforge.core.artifacts.research import ResearchDocument, ResearchTable
from signalforge.stages.research import _build_document
from signalforge.stages.research_extraction import extract_tables


def page(table: str, before: str = "") -> str:
    return f"<html><body><article>{before}{table}</article></body></html>"


BENCH = """
<table>
  <caption>Word error rate by model</caption>
  <thead><tr><th>Model</th><th>WER</th><th>RTFx</th></tr></thead>
  <tbody>
    <tr><td>Granite  Speech</td><td>5.06</td><td>280</td></tr>
    <tr><td>Whisper
        large</td><td>7.40</td><td>145</td></tr>
  </tbody>
</table>
"""


def test_a_data_table_keeps_header_rows_caption_and_collapses_whitespace() -> None:
    (table,) = extract_tables(page(BENCH))
    assert table.caption == "Word error rate by model"
    assert table.header == ("Model", "WER", "RTFx")
    assert table.rows == (("Granite Speech", "5.06", "280"), ("Whisper large", "7.40", "145"))


def test_a_table_without_its_own_caption_has_none_even_under_a_heading() -> None:
    bare = BENCH.replace("<caption>Word error rate by model</caption>", "")
    assert extract_tables(page(bare, "<h3>Usage with vLLM</h3>"))[0].caption == ""


def test_a_header_is_found_without_th_when_the_first_row_has_no_numbers() -> None:
    plain = (
        "<table><tr><td>Model</td><td>Score</td></tr>"
        "<tr><td>A</td><td>91</td></tr><tr><td>B</td><td>88</td></tr></table>"
    )
    assert extract_tables(page(plain))[0].header == ("Model", "Score")


@pytest.mark.parametrize(
    "table",
    [
        # one text column: a layout table
        "<table><tr><td>" + "A long paragraph of text. " * 10 + "</td></tr></table>",
        # a merged cell
        "<table><tr><th colspan='2'>Group</th></tr><tr><td>A</td><td>1</td></tr>"
        "<tr><td>B</td><td>2</td></tr></table>",
        # words only, no numbers
        "<table><tr><th>Tool</th><th>Use</th></tr><tr><td>A</td><td>search</td></tr>"
        "<tr><td>B</td><td>chat</td></tr></table>",
        # a cell over 120 characters
        "<table><tr><th>A</th><th>B</th></tr><tr><td>" + "x" * 121 + "</td><td>1</td></tr>"
        "<tr><td>y</td><td>2</td></tr></table>",
        # no header: the first row has numbers
        "<table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr>"
        "<tr><td>5</td><td>6</td></tr></table>",
        # rows of different lengths
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr>"
        "<tr><td>3</td></tr></table>",
    ],
)
def test_tables_that_are_not_clean_data_are_dropped(table: str) -> None:
    assert extract_tables(page(table)) == ()


def test_an_outer_layout_table_is_skipped_but_a_data_table_inside_it_is_kept() -> None:
    inner = (
        "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr>"
        "<tr><td>3</td><td>4</td></tr></table>"
    )
    found = extract_tables(page(f"<table><tr><td>{inner}</td><td>menu</td></tr></table>"))
    assert [t.header for t in found] == [("a", "b")]


def test_too_wide_or_too_long_tables_are_dropped_not_trimmed() -> None:
    wide = "<tr>" + "".join(f"<th>H{i}</th>" for i in range(9)) + "</tr>"
    row = "<tr>" + "".join(f"<td>{i}</td>" for i in range(9)) + "</tr>"
    assert extract_tables(page(f"<table>{wide}{row}{row}</table>")) == ()
    long = "<tr><th>A</th><th>B</th></tr>" + "<tr><td>1</td><td>2</td></tr>" * 31
    assert extract_tables(page(f"<table>{long}</table>")) == ()
    ok = "<tr><th>A</th><th>B</th></tr>" + "<tr><td>1</td><td>2</td></tr>" * 30
    assert len(extract_tables(page(f"<table>{ok}</table>"))[0].rows) == 30


def test_at_most_three_tables_the_most_numeric_ones_in_page_order() -> None:
    def table(n: int) -> str:
        rows = "".join(f"<tr><td>r{i}</td><td>{i}</td></tr>" for i in range(n))
        return f"<table><tr><th>K</th><th>V</th></tr>{rows}</table>"

    html = page(table(2) + table(5) + table(3) + table(4))
    sizes = [len(t.rows) for t in extract_tables(html)]
    assert sizes == [5, 3, 4]  # the 2-row table loses; the rest keep page order


def test_bad_html_gives_no_tables() -> None:
    assert extract_tables("") == ()
    assert extract_tables("not html at all") == ()


def test_a_research_document_without_tables_still_validates() -> None:
    doc = ResearchDocument(
        url="https://e.com",
        title="t",
        source_label="e",
        is_primary=True,
        raw_text_ref="sha256:x",
        text="body",
        fetched_at=datetime.now(UTC),
    )
    assert doc.tables == ()


def test_a_built_document_carries_the_tables_found_in_its_html() -> None:
    with_table = _build_document(
        url="https://e.com/a",
        title="t",
        source_label="e",
        is_primary=True,
        clean_text="Some article text.",
        html=page(BENCH),
    )
    assert isinstance(with_table.tables[0], ResearchTable)
    assert with_table.tables[0].header == ("Model", "WER", "RTFx")
    without = _build_document(
        url="https://e.com/b",
        title="t",
        source_label="e",
        is_primary=False,
        clean_text="Some text.",
        html=page("<p>no table</p>"),
    )
    assert without.tables == ()
