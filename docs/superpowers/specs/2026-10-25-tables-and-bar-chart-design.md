# Tables in articles and a bar-chart image template

Date: 2026-10-25. Status: design, awaiting review.

## Problem

Benchmark numbers are the most useful thing a technical article can show, and the site shows
them only as sentences. Two gaps:

1. The article has no table. A section holds paragraphs, and one inline image appears after the
   second section.
2. The image tool has no chart for "N models scored X on one metric". `compare-blocks` takes
   exactly two values.

Research already fetches the source HTML, but it keeps only the main text. A real data table
survives as flat pipe text with no header structure (checked on the Granite model card). Blog
posts such as Falcon3 and SmolVLM2 hold their benchmarks in images, not tables. Reading tables
out of images (a vision path) is out of scope here.

## Decision

Numbers in a table come from the source, copied cell by cell by code. The writer model chooses
which table to show and where. It never types a table number and never writes table text. A
table built by the writer from claims is out of scope: the sentence judge cannot check a table
cell, so it would put invented numbers on the page.

The work is two independent builds, ordered so each ships safely on its own.

## Part 1: `bar-chart` image template

An eighth template in `skills/article-images/scripts/articleimg.py`.

- Spec: `values.bars`, 3 to 6 items of `{name, value, text}`; optional `caption` (34 characters);
  no `figure`. `name` is at most 14 characters, `text` at most 8, as for `compare-blocks`.
- Drawing: horizontal bars on one linear scale from zero (no truncated axis), longest bar at
  full width, the leading bar in ink and the others in white or the accent colour. The value
  text sits at the end of each bar. Colour and small variations come from the slug, as in the
  other templates. Same canvas (1200 by 900), no emoji, logos or faces.
- Validation, beyond the existing checks:
  - `value` is a positive number.
  - The first number in `text` equals `value`. The bars measure one metric, so the unit is
    the same and no scaling is needed. This stops a bar that says 91 but is drawn as 19.
  - Every number in `text`, `name` and `caption` is in the article's title, dek or verified
    claims (the existing number check).
- Template choice in `SKILL.md`: three to six named things with a number of the same kind
  (scores, latency, price) pick `bar-chart`; exactly two keep `compare-blocks`. It is the new
  row after the compare-blocks row.
- Tests: validation rules, one `<rect>` per bar, bar length proportional to value, bars inside
  the canvas, text fits, and every example renders on Python 3.9.

Independent of Part 2. One pull request.

## Part 2: tables in the article

### Data model

No database migration: research documents, drafts and published bodies are JSONB.

- `ResearchTable` (new, in `core/artifacts/research.py`): `caption` (string, may be empty),
  `header` (tuple of strings), `rows` (tuple of tuples of strings). `ResearchDocument` gains
  `tables: tuple[ResearchTable, ...] = ()`. Old packages read as having no tables.
- `ArticleTable` (new, in `core/artifacts/article.py`): the same three fields plus
  `source_index`, the index of the document it came from (the reader-facing source is looked up
  in `ArticleBody.sources`, as for claims). `ArticleSection` gains `table: ArticleTable | None
  = None`, rendered after the section's paragraphs. The model allows one table per section;
  this version picks one per article (see Choosing and placing).
- Public shape: `PublicSectionOut` gains an optional `table` with `caption`, `header`, `rows`
  and `source` (label and URL). The explicit allow-list rule stays.

### Extraction (research stage)

A new `extract_tables(html)` in `research_extraction.py` parses `<table>` elements with lxml
(already installed through trafilatura). It runs wherever the stage already holds a page's
HTML (`_build_document`), so no extra fetch.

A table is kept only when it looks like data:

- at least 2 columns and 2 data rows, at most 8 columns and 30 rows;
- a header row (`<th>` or a first row with no numeric cells);
- at least a third of data cells contain a digit;
- no nested tables, no `colspan` or `rowspan` above 1, no cell over 120 characters.

Anything else is dropped, never trimmed, so a half table never appears. Caption is the
table's own `<caption>` and nothing else: a nearby heading was tried on the Granite model card and
both tables took an unrelated section title. At most 3 tables per document,
the ones with the most numeric cells. Cell text is whitespace-normalised plain text.

Known limits, accepted for the first version: merged-cell headers, tables built from images
or rendered by script, and pages the fetcher cannot read (arXiv currently).

### Choosing and placing (draft stage)

- The writer prompt (`draft-v7`) lists the available tables as `<table id=n>` blocks: caption,
  header, and the first three rows only. It may pick at most one table whose numbers matter to
  the story.
- The reply gains an optional `"table": {"id": n, "after_section": i}`. There is no free text.
- Code builds the `ArticleTable` from the stored table, so the cells are the source's own. An
  unknown id or a section index out of range is ignored without flagging. A second pick is
  ignored.
- The sentence judge and the number check do not apply to the table, since no model wrote it.
  Auto-review and publish gates ignore it. Word count excludes table cells.
- Prose may mention a table number only through a cited claim; the existing rules apply.

### Rendering

- Article page: `<figure>` with a real `<table>`: `<caption>`, `<thead>`, `scope` on header
  cells, rounded tile surface from the design tokens (pastel header, no hex or arbitrary values,
  per `check-tokens`). It sits in a horizontal scroll wrapper so a wide table never breaks the
  mobile layout. A line under it names the source, linked.
- Markdown twin (`/articles/<slug>/md`): a GitHub-style table, `|` escaped.
- JSON twin: the table in the section.
- Answer engines read HTML tables and markdown tables directly, so no extra JSON-LD is added in
  this version.
- Editor draft preview shows the table plainly; the editor UI is not a priority.

### Pipeline and rollout

- `research-v4` (tables extracted), `draft-v7` (table choice). Existing packages keep no
  tables until they are researched again; nothing is back-filled automatically.
- The golden fixtures gain `tables`, and `eval_drafts` reports whether a table was chosen.
- Hermes needs no change: tables arrive through the same research and draft calls.

### Build order, three pull requests

1. Schema and extraction: `ResearchTable`, `extract_tables`, wired into research, tests on real
   HTML samples (a data table, a layout table, a merged-cell table, an oversized table).
   Invisible to readers.
2. Draft integration: `ArticleTable`, the prompt, the reply parsing, placement validation, eval
   metric. Still invisible until a published body carries a table and the page renders it.
3. Public API and web: `PublicSectionOut.table`, the page, the markdown and JSON twins, and web
   tests. This is where readers see it.

## Risks

- Layout tables read as data. Mitigation: the numeric-density and shape rules, plus tests on
  both kinds. Worst case a harmless table of text appears; no number is invented.
- A table from a secondary page can be wrong. Mitigation: the source line under every table;
  tables from the primary page and its cited model cards are the common case.
- A very wide table on a phone. Mitigation: scroll wrapper and the 8-column cap.
- More prompt text raises writer cost slightly: three small tables at most per package.

## Out of scope

Reading tables from images (vision), editing a table by hand, tables the model writes,
charts rendered on the page from table data, back-filling published articles.
