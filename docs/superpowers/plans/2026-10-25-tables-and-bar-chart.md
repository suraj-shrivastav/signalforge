# Tables in articles and a bar-chart template: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show benchmark numbers in articles: a `bar-chart` image template, and a table block copied from the source.

**Architecture:** Research keeps real `<table>` data from fetched HTML. The writer only picks a table id and a section index. Code copies the cells into the article body. The public API, the page, and the markdown and JSON twins render it.

**Tech Stack:** Python 3.13, pydantic, lxml (already installed through trafilatura), FastAPI, Next.js 16, vitest. The image script is standard library only and must run on Python 3.9.

**Spec:** `docs/superpowers/specs/2026-10-25-tables-and-bar-chart-design.md`

## Global Constraints

- Image script: Python 3.9 compatible, standard library only, no `zip(strict=...)`.
- Image limits stay: label 28, figure 8, caption 34, alt 140, item 30, name 14, text 8.
- Every number in an image must come from the article's title, dek or verified claims.
- Tables: at most 8 columns and 30 rows, cell at most 120 characters, no `colspan` or `rowspan` above 1, at most 3 per document. Oversized or odd tables are dropped, never trimmed.
- The writer never types a table cell or table text; it replies with `{"id": n, "after_section": i}` only.
- No database migration (JSONB). `check-tokens` forbids hex, arbitrary Tailwind values and inline styles in web code.
- Commits and PRs as `suraj-shrivastav` with no Claude attribution. Use `PATH="$PWD/.venv/bin:$PATH"` for pre-commit. Each part is its own branch from `origin/main` in its own worktree.

---

## PR A: `bar-chart` template

### Task 1: validation, drawing, examples, docs

**Files:**
- Modify: `skills/article-images/scripts/articleimg.py` (TEMPLATES, `validate`, new `draw_barchart`, `DRAW`)
- Create: `skills/article-images/examples/example-bar-chart-figure.json`, `example-bar-chart-cover.json`
- Modify: `skills/article-images/SKILL.md`, `skills/article-images/references/templates.md`
- Test: `tests/unit/test_article_images.py`

**Interfaces:**
- Produces: template name `"bar-chart"`; spec `values.bars: [{"name": str<=14, "value": positive number, "text": str<=8}]` (3 to 6 items), optional `caption`, no `figure`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_article_images.py`)

```python
def bars(*items: tuple[str, float, str]) -> dict[str, Any]:
    spec = example("example-bar-chart-figure.json")
    spec["values"] = {"bars": [{"name": n, "value": v, "text": t} for n, v, t in items]}
    return spec


GOOD_BARS = (("Granite", 5.06, "5.06%"), ("Whisper", 7.4, "7.4%"), ("Canary", 6.1, "6.1%"))


def test_bar_chart_validates_count_value_text_and_fields() -> None:
    assert img.validate(bars(*GOOD_BARS), None) == []
    assert any("3 to 6" in e for e in img.validate(bars(*GOOD_BARS[:2]), None))
    assert any("3 to 6" in e for e in img.validate(bars(*(GOOD_BARS * 3)), None))
    bad = bars(("A", 5.0, "9%"), GOOD_BARS[1], GOOD_BARS[2])
    assert any("must show the value" in e for e in img.validate(bad, None))
    assert any("positive" in e for e in img.validate(bars(("A", 0, "0"), *GOOD_BARS[1:]), None))
    assert any("limit 14" in e for e in img.validate(bars(("x" * 15, 5, "5"), *GOOD_BARS[1:]), None))
    assert any("limit 8" in e for e in img.validate(bars(("A", 5, "5" * 9), *GOOD_BARS[1:]), None))
    assert any("no figure" in e for e in img.validate({**bars(*GOOD_BARS), "figure": "5"}, None))
    unknown = bars(("A", 9.99, "9.99%"), *GOOD_BARS[1:])
    assert any("'9.99'" in e for e in img.validate(unknown, ARTICLE))


@pytest.mark.parametrize("count", [3, 4, 5, 6])
def test_bar_chart_draws_proportional_bars_inside_the_canvas(count: int) -> None:
    items = tuple((f"Model {i}", float(10 * (i + 1)), f"{10 * (i + 1)}") for i in range(count))
    svg = img.render(bars(*items), "some-slug")
    widths = [int(w) for w in re.findall(r'<rect class="bar" [^>]*width="(\d+)"', svg)]
    assert len(widths) == count
    for i, width in enumerate(widths):
        assert abs(width / widths[-1] - (i + 1) / count) < 0.02  # linear scale from zero
    for x, w in re.findall(r'<rect class="bar" x="(\d+)"[^>]*width="(\d+)"', svg):
        assert int(x) + int(w) <= 1120
    assert svg == img.render(bars(*items), "some-slug")
    assert "NaN" not in svg


def test_bar_chart_pairs_with_another_template() -> None:
    cover = example("example-bar-chart-cover.json")
    assert img.check_pair(cover, example("example-bar-chart-figure.json")) == []
```

- [ ] **Step 2: Run to see them fail**

Run: `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/unit/test_article_images.py -q`
Expected: FAIL (`template: must be one of`, missing example files).

- [ ] **Step 3: Implement.** In `articleimg.py`: add `"bar-chart"` to `TEMPLATES`; in `validate` add this branch before `layers`:

```python
    elif template == "bar-chart":
        texts.append(_text(spec, "caption", errors, required=False))
        found = values.get("bars")
        if not isinstance(found, list) or not 3 <= len(found) <= 6:
            errors.append("values.bars: 3 to 6 objects with name, value, text")
        else:
            for i, bar in enumerate(found):
                if not isinstance(bar, dict):
                    errors.append(f"values.bars[{i}]: object with name, value, text")
                    continue
                texts += [_text(bar, "name", errors), _text(bar, "text", errors)]
                value = bar.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    errors.append(f"values.bars[{i}].value: positive number")
                    continue
                tokens = NUMBER.findall(str(bar.get("text", "")))
                first = tokens[0].rstrip(".,").replace(",", "") if tokens else ""
                try:
                    shown = float(first)
                except ValueError:
                    shown = -1.0
                if abs(shown - value) > 1e-9 * max(1.0, abs(value)):
                    errors.append(
                        f"values.bars[{i}]: text {bar.get('text')!r} must show the value {value}"
                    )
        if "figure" in spec:
            errors.append("bar-chart takes no figure; use values.bars")
```

and the drawer, registered as `"bar-chart": draw_barchart` in `DRAW`:

```python
def draw_barchart(spec: dict[str, Any], seed: Seed) -> str:
    """Horizontal bars on one linear scale from zero; the longest bar is dark."""
    found = spec["values"]["bars"]
    n = len(found)
    top = max(b["value"] for b in found)
    left, room = 400, 520  # bars start here and may use this much width; values sit after them
    gap = 26
    height = int(min(96, (610 - (n - 1) * gap) / n))
    start = 190 + (610 - (n * height + (n - 1) * gap)) // 2
    parts = [label(spec["label"])]
    for i, bar in enumerate(found):
        y = start + i * (height + gap)
        width = max(24, int(room * bar["value"] / top))
        dark = bar["value"] == top
        fill, ink = (INK, WHITE) if dark else (WHITE, INK)
        parts.append(
            txt(
                80, y + height / 2 + 12, bar["name"], fit(bar["name"], 290, 36, 0.56),
                weight=700, spacing=0,
            )
        )
        parts.append(
            f'<rect class="bar" x="{left}" y="{y}" width="{width}" height="{height}" '
            f'rx="{height // 2}" fill="{fill}"/>'
        )
        parts.append(
            txt(left + width + 18, y + height / 2 + 14, bar["text"], 40, weight=800, spacing=0)
        )
        del ink  # the value sits outside the bar, always in ink
    return "".join(parts) + caption(spec, 80, 860, 40)
```

Remove the unused `ink`/`del ink` lines if lint prefers: keep `fill` only.

- [ ] **Step 4: Examples.** `example-bar-chart-figure.json`:

```json
{
  "role": "figure",
  "template": "bar-chart",
  "label": "Word error rate",
  "caption": "lower is better",
  "values": {
    "bars": [
      {"name": "Granite", "value": 5.06, "text": "5.06%"},
      {"name": "Canary", "value": 6.1, "text": "6.1%"},
      {"name": "Whisper", "value": 7.4, "text": "7.4%"}
    ]
  },
  "alt": "Bar chart of word error rate: Granite 5.06 percent, Canary 6.1, Whisper 7.4"
}
```

`example-bar-chart-cover.json` is a `figure-ripples` cover (`"figure": "5.06%"`, `"caption": "word error rate"`).

- [ ] **Step 5: Docs.** `SKILL.md`: add the table row `| Three to six named things with a number of the same kind (scores, latency, price) | bar-chart | values.bars, optional caption |` directly **above** the `compare-blocks` row (exactly two things still use `compare-blocks`); add the `bar-chart values` paragraph and the limit "bar name 14, bar text 8". `templates.md`: one row in the table and a line in Examples.

- [ ] **Step 6: Verify on Python 3.9 and the whole suite**

Run: `for s in a b c d e f; do for f in skills/article-images/examples/*.json; do /usr/bin/python3 skills/article-images/scripts/articleimg.py render $f --slug $s --out /tmp/x.svg | grep -v '^OK'; done; done`
Expected: no output. Run `ruff check src apps tests skills`, `ruff format --check`, `mypy src apps tests`, `python -m pytest tests/unit -q`: all pass. Render a 3-bar and a 6-bar chart with `qlmanage -t -s 900` and look at them.

- [ ] **Step 7: Commit and PR** `feat: bar-chart template for article images`.

---

## PR B: research keeps source tables

### Task 2: `ResearchTable` and `extract_tables`

**Files:**
- Modify: `src/signalforge/core/artifacts/research.py` (add `ResearchTable`, `ResearchDocument.tables`)
- Modify: `src/signalforge/stages/research_extraction.py` (add `extract_tables`)
- Test: `tests/unit/test_research_tables.py`

**Interfaces:**
- Produces: `class ResearchTable(BaseModel)` with `caption: str = ""`, `header: tuple[str, ...]`, `rows: tuple[tuple[str, ...], ...]` (frozen, `extra="forbid"`); `ResearchDocument.tables: tuple[ResearchTable, ...] = ()`; `def extract_tables(html: str) -> tuple[ResearchTable, ...]`.

- [ ] **Step 1: Failing tests.** Inline HTML samples: (a) a clean benchmark table with `<thead>` and a `<caption>` returns 1 table with the right header, rows and caption; (b) a layout table (one text column, cells over 120 chars) returns `()`; (c) a table with `colspan="2"` returns `()`; (d) 9 columns returns `()`; 31 rows returns `()`; (e) a table whose cells are all words (no digits) returns `()`; (f) nested table returns `()`; (g) four valid tables return the 3 with the most numeric cells; (h) whitespace in cells is collapsed; (i) `ResearchDocument` without `tables` still validates and `tables` defaults to `()`.

- [ ] **Step 2: Run, expect FAIL** (`ImportError: extract_tables`).

- [ ] **Step 3: Implement.** Parse with `lxml.html.fromstring`; for each `table` element not containing another `table`: reject if any `td`/`th` has `colspan` or `rowspan` greater than 1; header = cells of the first `tr` when they are `th` or contain no digit; rows = the rest, each cell `" ".join(text_content().split())`; reject if rows have unequal lengths, fewer than 2 columns or 2 rows, more than 8 columns or 30 rows, any cell over 120 characters, or fewer than a third of data cells containing a digit. Caption: `<caption>` text, else the text of the nearest preceding `h1` to `h4`, else `""`. Return the 3 tables with the most numeric cells, in page order.

- [ ] **Step 4: Run, expect PASS.** `ruff`, `mypy`.
- [ ] **Step 5: Commit** `feat: research keeps data tables from source pages`.

### Task 3: wire into the research stage

**Files:**
- Modify: `src/signalforge/stages/research.py` (`_build_document` takes `html`; three call sites; `PROMPT_VERSION = "research-v4"`)
- Test: `tests/unit/test_research_tables.py` (extend)

**Interfaces:**
- Consumes: `extract_tables(html)` from Task 2.
- Produces: stored `ResearchDocument.tables` for the primary page, reference pages and secondary pages.

- [ ] **Step 1: Failing test:** build a document from HTML that has a clean table and assert `document.tables` has it; a document from HTML with no table has `()`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Add `html: str` to `_build_document` and pass `tables=extract_tables(html)`; update the three callers (primary, reference links, secondary results) to pass the HTML they already hold.
- [ ] **Step 4: Run all unit tests, `ruff`, `mypy`.** Run the golden eval once to confirm no regressions in word counts.
- [ ] **Step 5: Commit** `feat: store source tables in the research package (research-v4)`. PR B.

---

## PR C: the draft chooses a table

### Task 4: `ArticleTable`, writer prompt and reply

**Files:**
- Modify: `src/signalforge/core/artifacts/article.py` (`ArticleTable`, `ArticleSection.table`)
- Modify: `src/signalforge/stages/draft.py` (`_writer_user`, `_WriterReply`, assembly; `PROMPT_VERSION = "draft-v7"`)
- Modify: `apps/worker/eval_drafts.py` (metric `table_chosen`; fixtures keep `tables`)
- Test: `tests/unit/test_draft_tables.py`

**Interfaces:**
- Consumes: `ResearchDocument.tables`.
- Produces: `class ArticleTable(BaseModel)`: `caption: str`, `header: tuple[str, ...]`, `rows: tuple[tuple[str, ...], ...]`, `source_index: int = Field(ge=0)`; `ArticleSection.table: ArticleTable | None = None`; writer reply field `"table": {"id": int, "after_section": int}` or absent.

- [ ] **Step 1: Failing tests:** (a) a reply naming a valid id and section puts an `ArticleTable` equal to the stored table (cell for cell) on that section; (b) unknown id, negative or out-of-range `after_section` give no table and no flag; (c) a second `table` pick is ignored; (d) the user prompt lists each table's id, caption, header and only the first three rows; (e) with no tables the prompt has no table block and the reply works as before; (f) `ArticleBody` still validates old stored bodies without `table`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** In `_writer_user`, append `<tables>` with one `<table id="n" source="label">` per table across documents (global ids by document order). Add to the system prompt: "Tables: you may show at most one source table when a reader benefits from its exact numbers. Reply with `"table": {"id": n, "after_section": i}`. Never write or retype table text." Assembly looks the id up in the package, builds `ArticleTable(... source_index=<document index>)`, and sets it on the chosen section. Word count and the publish gate ignore tables.
- [ ] **Step 4: Run all unit tests, `ruff`, `mypy`; run the golden eval and report `table_chosen`.**
- [ ] **Step 5: Commit** `feat: the draft can show one source table (draft-v7)`. PR C.

---

## PR D: readers see it

### Task 5: public API, markdown and JSON

**Files:**
- Modify: `apps/api/schemas.py` (`PublicTableOut`, `PublicSectionOut.table`)
- Modify: `apps/api/routes/public.py` (map body section tables, resolve `source`)
- Modify: `apps/web/src/lib/public.ts`, `apps/web/src/lib/seo.ts` (`articleMarkdown` renders a GitHub table, `|` escaped)
- Test: `tests/unit/test_api_articles.py`, `apps/web/src/lib/seo.test.ts`

**Interfaces:**
- Produces: `PublicSectionOut.table: PublicTableOut | None` with `caption: str`, `header: list[str]`, `rows: list[list[str]]`, `source: PublicSource | None`; TypeScript `PublicTable` with the same fields.

- [ ] **Step 1: Failing tests:** the public article endpoint returns the table with its source label and URL; a body with no table returns `table: null`; the markdown contains a header row, a separator row and data rows, and a cell containing `|` is escaped.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the schema, mapping and markdown function.
- [ ] **Step 4: Run Python and web tests.**
- [ ] **Step 5: Commit.**

### Task 6: the article page

**Files:**
- Create: `apps/web/src/components/public/ArticleTable.tsx`
- Modify: `apps/web/src/app/(public)/articles/[slug]/page.tsx` (render after the section's paragraphs, before the figure check)
- Test: `apps/web/src/components/public/ArticleTable.test.tsx`

**Interfaces:**
- Consumes: `PublicTable` from Task 5.

- [ ] **Step 1: Failing tests:** renders a `<table>` with `<caption>`, a `<thead>` of `<th scope="col">`, one body row per row, the source as a link under it; a cell with `<b>` text renders escaped, not as markup; `null` renders nothing.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `<figure>` wrapper with `overflow-x-auto`, rounded tile surface (`rounded-tile`, `bg-surface`), header row on `bg-sunken`, `tabular-nums` cells, `text-small`; `figcaption` with the source link using `safeHref`. Tokens only.
- [ ] **Step 4: Run web tests, `npm run lint`, `check-tokens`, typecheck, build.** Open the page in the local dev server with a seeded article and look at it at desktop and phone width.
- [ ] **Step 5: Commit.** PR D.

---

## Self-review

- **Spec coverage:** bar chart (Task 1), research tables and caps (Tasks 2 and 3), writer choice with no free text (Task 4), public shape, markdown, JSON (Task 5), page with scroll wrapper and source line (Task 6), versions research-v4 and draft-v7, eval metric (Task 4). No JSON-LD change, per the spec. Out-of-scope items stay out.
- **Placeholders:** none; Task 2 and 3 name the exact rules rather than code because the rules are the content.
- **Types:** `ResearchTable` and `ArticleTable` share `caption`, `header`, `rows`; `source_index` is on `ArticleTable` only and resolved to `source` in the public shape.
