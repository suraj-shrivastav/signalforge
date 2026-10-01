# Article Drafting and Verification (FR-07 + FR-08)

Status: draft for review. Builds on FR-06 (merged) and
`2026-09-27-article-drafting-design.md` (templates/voice/images, treated as
binding here, not re-decided).

## Goal

Turn a `RESEARCHED` topic card's `ResearchPackage` into a draft article with
per-claim verification status, so the editorial dashboard (FR-05) can show a
"draft review view with claim-status highlighting and risk summary" that
today has nothing real behind it.

## Scope

In scope: FR-07 (article generation) and FR-08 (verification and review
summary), bundled into one pipeline stage and one data model, because a
draft with no claim status is not reviewable.

Out of scope: FR-09 (SEO/structuring), FR-11 (publishing), any public-facing
UI beyond what's needed to render a draft with claim highlighting in
`/editor`. Template/voice/image decisions are not reopened — see the
2026-09-27 spec.

## Pipeline

One new stage function, `run_draft`, same shape as `run_research`
(`src/signalforge/stages/research.py`): a `StageRun` row, a fresh `Budget`
and `LLMGateway` built per card, a repository method that selects
`RESEARCHED` cards with no `article_drafts` row yet.

Before the per-card loop: resolve both new roles (`article_writer`,
`claim_judge`) via `model_for`, same fail-fast pattern `run_research` already
uses for `research_extraction`/`claim_embedding`. If the two roles resolve to
the same model `family` (`ModelSpec.family`), raise `ConfigurationError` —
FR-08 requires the judge to be a different model family from the writer, and
this is the one place that requirement can be enforced mechanically instead
of by convention.

Per card, in order:

1. **Template selection.** Pure function of the card's signal type and the
   `ResearchPackage`, per the 2026-09-27 spec's selection rule (paper source
   gives Paper breakdown; comparison-tagged gives Comparison; release/launch
   gives News brief; otherwise Explainer). No LLM call.
2. **Writer call.** One `complete_json` against the `article_writer` role.
   Input is the `ResearchPackage` only (per PRD FR-07 — the writer never sees
   the raw topic card or any other context). Output: the template's
   structured shape (`title`, `dek`, `sections[]`, `claims[]`, `sources[]`,
   `cover`). Untrusted-text handling matches `research.py`: anything from
   `ResearchPackage.documents[].text` that gets echoed into the prompt is
   `html.escape(..., quote=False)`-wrapped before the call and
   `html.unescape`d on any field that must round-trip.
3. **Mechanical span check.** Reuse `span_exists` from
   `research_extraction.py` unchanged. Each draft claim must cite a span
   that exists verbatim in the `ResearchPackage` document(s) it points to.
   A claim whose span does not check out is a mechanical failure for that
   claim, not a budget or provider error — record it, do not raise.
4. **Judge call.** One batched `complete_json` against the `claim_judge`
   role, covering every claim the draft makes in that card (not one call
   per claim — cost control, same reasoning as FR-06's batched embedding
   call). Schema: `{"claims": [{"index": int, "supported": bool}]}`.
5. **Status assignment.** Pure logic, no LLM call, applying PRD Sec. 11's
   table exactly: `verified` (span exists + judge confirms + primary source
   or 2+ independent sources), `supported` (span exists + judge confirms,
   single non-primary source or partial), `uncertain` (weak/indirect
   evidence), `conflicting` (credible sources disagree — reuse FR-06's
   `gaps_and_disagreements` similarity-band signal as an input here),
   `unverified` (no evidence). This is where FR-06's revisit work
   (stored document text, embedding-based near-dup/disagreement detection)
   becomes load-bearing for FR-08 — it was built for this.
6. **Publish gate.** Deterministic checks from the 2026-09-27 spec: no
   em/en dash used as a dash, no banned AI-authorship phrasing, length
   within the template's target band. Runs after status assignment, before
   the row is written. A failure routes the card to `needs_more_info` with
   the reason recorded in the review summary — same per-card routing style
   `research.py` uses for its own `NEEDS_MORE_INFO`/`FAILED` branches, no
   new error type.
7. **Review summary.** Mechanically assembled plain text (not LLM-written):
   every `uncertain`/`conflicting`/`unverified` claim, every single-source
   claim, every judge-vs-mechanical disagreement (judge says supported but
   span check failed, or vice versa), and the publish-gate failure reason
   if any.

Error routing mirrors `research.py`: a `BudgetExceededError` from either
the writer or judge call ends that card as `failed` with an empty draft; any
other per-card `SignalForgeError` logs and marks `failed`; nothing escapes
to fail the whole `StageRun` except a misconfigured role (the fail-fast
check) or a genuine bug.

## Data model

One table, `article_drafts`, one artifact, `ArticleDraft`
(`SCHEMA_VERSION = 1`), built first and dumped to the row second — same
"artifact first, row second" rule as `ResearchPackage`.

Row: `card_id` (UUID FK, unique), `status` (`String(32)`, CHECK constraint:
`drafting`/`drafted`/`needs_more_info`/`failed`), `template` (`String(32)`,
CHECK constraint against the four template names), `draft` (JSONB — the
structured shape: title/dek/sections/claims/sources/cover, claims carrying
their status per Sec. 11's enum), `review_summary` (Text, default `""`),
`cost_usd` (`Numeric(12,6)`), `calls`/`tokens` (int).

`ArticleDraftRepository`, mirroring `ResearchRepository`:
`list_researched_undrafted(limit)` (same DISTINCT-ON-latest-decision join
shape, excluding cards with an existing `article_drafts` row) and
`insert(draft, *, cost_usd, calls, tokens)` (ON CONFLICT DO NOTHING).

## Settings and roles

Two new `Settings` fields: `llm_model_article_writer`,
`llm_model_claim_judge` — same pattern as `llm_model_research_extraction`.
Two new roles in `build_roles()`: `article_writer`, `claim_judge`.

## Editor/public data boundary

Per the 2026-09-27 spec: model trail, prompt version, template-choice
reasoning, and the full review summary are `/editor`-only fields. Any public
API shape omits them — same pattern as FR-06's existing editor-vs-public
split, extended to cover the new fields. A web test scans public response
shapes for these field names, same as the existing editor-console tests do
for other editor-only data.

## Frontend

`apps/web/src/lib/mock/article.ts` is deleted once a real draft exists to
render; its drift from the 2026-09-27 spec (`template: string` instead of
the 4-value union, per-claim `sourceLabel`/`sourceUrl` instead of a
top-level `sources[]` array) is corrected in the same change, not carried
forward. `ArticlePreview.tsx` and its test are updated to the real shape.

## Testing

Same conventions as FR-06: unit tests for pure logic (template selection,
status assignment, publish-gate checks) with no network and no DB; a
`FakeProvider`-backed integration suite for `run_draft` gated on
`TEST_DATABASE_URL`, covering: a clean draft reaching `drafted`, a
span-check failure, a judge disagreement, a publish-gate failure, a budget
exhaustion mid-card, and the role-family fail-fast check.

## Out of scope (explicit)

FR-09 (SEO/structuring), FR-11 (publishing), image generation, per-topic
custom templates, A/B testing of structure, translations (the last four
already out of scope per the 2026-09-27 spec).
