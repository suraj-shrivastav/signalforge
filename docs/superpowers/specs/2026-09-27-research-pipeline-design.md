# Deep research pipeline (FR-06)

Status: draft for review. First sub-project of Phase 4 (research, drafting, verification, SEO, publishing). Nothing in Phase 4 is built yet.

## Context

Editorial dashboard (sub-project 3, merged #58) lets the editor accept a topic card. Today, accepting a card does nothing further: no research runs, no article is ever produced. This spec covers the next stage only: turning an accepted `topic_cards` row into a `ResearchPackage` — fetched sources, extracted claims, each claim mapped to a quoted evidence span.

Downstream stages (writer FR-07, verification FR-08, SEO FR-09, publishing FR-10/11) all consume `ResearchPackage` as their input and are specced separately, later. This stage does not assign claim status (`verified`/`supported`/etc, PRD §11) — that is FR-08's job, run by a different model family. This stage only extracts claims and their evidence spans.

## Decisions

- **Primary source + secondary search.** Fetch the card's own source URL (primary), then search for secondary corroborating sources via Tavily. Secondary discovery needs a real search API; direct-fetch alone only re-reads what the card already links.
- **Tavily** for secondary search. New env var `TAVILY_API_KEY`, added to `.env.local.example` and `.kiro/steering/tech.md`, value never printed.
- **`trafilatura`** for HTML-to-clean-text extraction. New dependency; nothing already installed does boilerplate removal.
- **One LLM call per document**, not per card. New role `research_extraction` in `roles.py`'s `build_roles()`, following the existing `relevance_filter`/`topic_card` pattern. Each call gets one document's clean text plus the card's topic summary, and returns candidate claims with verbatim quoted spans.
- **Mechanical span check in this stage.** A claim's quoted span must exist verbatim in the source document's extracted text. Claims that fail this are dropped as extraction failures, not surfaced. This is a cheap check that catches hallucinated quotes before FR-08's LLM judge ever sees them; it is not FR-08's judge check.
- **Claim status starts `unverified`.** FR-08 assigns real status later. This stage only records the claim text, its span, and which document(s) support it.
- **No separate `research_status` column on `topic_cards`.** Status lives on `research_packages.status`, joined by `card_id`. A duplicate column risks going out of sync.
- **`ResearchPackage` is an `Artifact` subclass** (`core/artifacts/base.py`), like every other stage output. Gets `id`, `schema_version`, `created_at`, `produced_by`, `parent_ids` for free; immutable; closed to unknown fields.
- **Budget: `BudgetScope.TOPIC`**, already defined in `core/budget.py`. Reuse it as-is; no new budget type.
- **Raw fetched document text stored out of band**, referenced by path/key from the artifact, not inline in JSONB — pages can be large.

## Data model

New table `research_packages` (UUID PK, timestamps, schema-version mixins — same base as `topic_cards`):

| Column | Type | Notes |
|---|---|---|
| `card_id` | UUID FK → `topic_cards.id` | one package per card (unique) |
| `status` | enum: `researching`, `researched`, `needs_more_info`, `failed` | |
| `documents` | JSONB list | `{url, title, source_label, fetched_at, is_primary, raw_text_ref}` |
| `claims` | JSONB list | `{text, evidence_span, document_indices: [int], status}` — `status` always `"unverified"` when written by this stage |
| `gaps_and_disagreements` | JSONB / text | sources that disagree, or coverage gaps noted during extraction |
| `cost_usd`, `calls`, `tokens` | numeric / int | from the `Budget` used for this card, recorded on completion |

`ResearchPackage(Artifact)` mirrors this shape as the in-process/typed form; the DB row is its persisted version, same pattern as `CardDraft` → `TopicCardRow`.

## Flow

For each `topic_cards` row with an editor decision of `accept` and no existing `research_packages` row:

1. Create a `Budget(scope=TOPIC, limits=...)` for this card (limits from settings, matching PRD's ~$0.50/topic starting budget).
2. Fetch the card's primary source URL via `httpx` (existing client pattern) → `trafilatura.extract()` → clean text. Fetch failure → package `status = needs_more_info`, stop here, editor sees it via the existing `need-more-info` reason tag (FR-05, already built).
3. Call Tavily with the card's title/summary as query → top 3 secondary results (fixed cap, cost control) → fetch + extract each the same way. A secondary fetch failure is skipped, not fatal (primary source alone is enough to proceed).
4. For each successfully extracted document, call the `research_extraction` role once: input is that document's clean text plus the card's topic summary; output is a list of candidate claims, each with a verbatim quoted span.
5. For each candidate claim, check the span exists verbatim in that document's clean text. Fails → drop, do not surface.
6. Merge surviving claims across documents: identical or near-identical claims from 2+ documents get both document indices recorded (feeds the "primary, or 2 independent sources" language in PRD §11, though FR-08 assigns the actual status later).
7. Write the `research_packages` row, `status = researched`. Record `Budget.record(...)` totals onto the row.
8. If step 2 succeeds but zero claims survive from any document → `status = needs_more_info` instead of `researched`.

Budget exhaustion (`BudgetExceededError`) at any point → package `status = failed`, logged, no partial write.

## Testing

- `trafilatura` extraction wrapper: fixture HTML in, expected clean text out (strip nav/ads/boilerplate).
- Mechanical span-exists check: exact match passes, near-miss/paraphrase fails, case-sensitivity handled deliberately (decide and test one way).
- Claim merge: same claim text from 2 documents → single merged claim with both document indices; distinct claims stay separate.
- Full stage run with a fake Tavily client and fake `httpx` responses (existing pattern from `plugins/sources` tests, no live network calls): asserts `ResearchPackage` shape, `needs_more_info` on primary-fetch failure, `needs_more_info` on zero surviving claims, `failed` on budget exhaustion.
- No live Tavily or live HTTP calls in the test suite.

## Out of scope

Claim status assignment (`verified`/`supported`/`uncertain`/`conflicting`/`unverified` beyond the mechanical span check) — FR-08. Writer/drafting — FR-07, consumes this stage's output unchanged. SEO, publishing — untouched. Additional search providers, PDF extraction, non-English sources, retry/backoff tuning beyond try-once — deferred; try-once failures route to `needs_more_info` or `failed` rather than retrying.
