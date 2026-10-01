# Article Drafting and Verification (FR-07 + FR-08) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Note on this plan's format:** unlike a standard writing-plans output, tasks below describe
> *what to build and why*, not full code. Each implementer is expected to read the referenced
> house patterns in the existing codebase and follow them — not invent new shapes. Where a task
> says "mirror X", X is the actual file to open and copy the structure of, not a suggestion.

**Goal:** Turn a `RESEARCHED` topic card into a draft article with per-claim verification status
and a review summary, so FR-05's dashboard has something real to show in its draft review view.

**Architecture:** One new stage (`run_draft`), same shape as `run_research`
(`src/signalforge/stages/research.py`): per-card writer call, mechanical span check, judge call,
status assignment, publish gate, one row written per card. One new table/artifact
(`article_drafts` / `ArticleDraft`), same "artifact first, row second" pattern as
`ResearchPackageRow`.

**Tech Stack:** Same as the rest of the backend — Python 3.13, SQLAlchemy/Alembic, pydantic,
the existing `LLMGateway`/`Budget`/`StageRun` machinery. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-01-article-drafting-verification-design.md` (this plan's
authority — read it before Task 1). Templates, voice rules, image handling, and the publish-gate
rules it enforces come from `docs/superpowers/specs/2026-09-27-article-drafting-design.md`, which
is binding and NOT reopened by this plan.

## Global Constraints

- No AI/Claude attribution anywhere — commits, PR bodies, code, comments.
- mypy strict, ruff line-length 100, `--strict-markers`, ban-relative-imports (match the existing
  `pyproject.toml` config; don't add new lint exceptions).
- No live network calls in tests. Integration tests gate on `TEST_DATABASE_URL` being set, same
  as every existing integration test file — skip cleanly when it's unset, don't invent a new
  skip convention.
- Never print or log a `.env` value or any API key.
- The writer's only input is the `ResearchPackage` (PRD FR-07) — never the raw `TopicCardRow`,
  never anything outside the package. If a task seems to need more context than the package
  carries, that's a sign the package is missing a field FR-06 should have populated — flag it,
  don't route around it by reaching into other tables.
- The judge role (`claim_judge`) must resolve to a different model `family` than the writer role
  (`article_writer`). This is enforced by a fail-fast check (Task 2), not by convention — don't
  skip the check to save time.
- Untrusted text (anything from `ResearchPackage.documents[].text` or claim text) that gets
  embedded into an LLM prompt must be `html.escape(..., quote=False)`-wrapped, and
  `html.unescape`d on the way back out for any field that must round-trip exactly (claim text,
  evidence spans). Mirror `research.py`'s existing escaping, don't reinvent it.
- Git worktree required for all implementation — `main` has a pre-commit hook blocking direct
  commits. One PR per task. Squash-merge on approval. Conventional Commits.
- Model-trail/prompt-version/template-choice-reasoning/full-review-summary fields are
  `/editor`-only. Any public-facing shape must omit them — this is a security/trust-boundary
  requirement, not a nice-to-have, and needs its own test (a web test scanning the public shape
  for these field names), same as the existing editor-console tests do for other editor-only data.

---

## Task 1: `ArticleDraft` artifact and `article_drafts` table

**Files:**
- Create: `src/signalforge/core/artifacts/article.py`
- Create: `src/signalforge/db/models/article.py`
- Create: Alembic migration (run `alembic revision` under `migrations/`, following the most
  recent migration's naming/structure — check `migrations/versions/` for the latest one before
  writing this)
- Test: `tests/unit/test_article_artifact.py`

**What to build:**

The `ArticleDraft` pydantic artifact, same conventions as `ResearchPackage`
(`src/signalforge/core/artifacts/research.py`): frozen, `extra="forbid"` nested models,
`SCHEMA_VERSION: ClassVar[int] = 1`.

Fields the artifact needs (derive the exact pydantic field definitions from the spec's "Data
model" section — this plan does not repeat them, the spec is the source of truth for field names
and constraints):
- `card_id`
- `status` — a `StrEnum` mirroring the new table's CHECK constraint: `drafting` / `drafted` /
  `needs_more_info` / `failed`.
- `template` — a `StrEnum`: the four template names from the 2026-09-27 spec (news brief,
  explainer, paper breakdown, comparison) — use the spec's exact names, don't invent your own.
- A nested structure for the draft itself: title, dek, sections (heading + paragraphs, same
  shape `MockArticleSection` already uses in `apps/web/src/lib/mock/article.ts` — keep the
  backend and frontend shapes compatible so Task 6's wiring is a straight pass-through), claims
  (text, evidence span, document reference(s), a `ClaimStatus` from
  `signalforge.core.artifacts.research` — reuse that enum, don't create a second one), sources
  (label + url, top-level array, NOT nested per-claim — this is the correction to the mock's
  drift the spec calls out), and a cover slot (`src?`, `alt` required, `credit?`, per the
  2026-09-27 spec).
- `review_summary: str = ""`.

The `ArticleDraftRow` SQLAlchemy model, mirroring `ResearchPackageRow`
(`src/signalforge/db/models/research.py`): `card_id` (UUID FK to `topic_cards`, unique),
`status`/`template` (`String(32)` with CHECK constraints matching the enums above), `draft`
(JSONB, default `{}`), `review_summary` (Text, default `""`), `cost_usd` (`Numeric(12,6)`),
`calls`/`tokens` (int). Register it in `src/signalforge/db/models/__init__.py` next to
`ResearchPackageRow`.

**Why this task is scoped alone:** every later task either builds the artifact or writes rows of
it. Getting the shape right once, reviewed once, before any stage logic depends on it, avoids a
schema change rippling through three other tasks.

**Testing:** unit tests for the artifact only (validation rules, frozen-ness, `extra="forbid"`
rejecting unknown fields) — same style as `tests/unit/test_research_artifact.py`. No DB, no
migration test; migration correctness is verified by Task 2's integration tests actually writing
rows against it.

**Watch for:** don't let `draft`'s nested shape drift from what the frontend mock
(`apps/web/src/lib/mock/article.ts`) currently uses — Task 6 needs them close enough that
updating the frontend is a rename, not a redesign.

---

## Task 2: `ArticleDraftRepository`

**Files:**
- Create: `src/signalforge/db/repositories/article.py`
- Test: `tests/integration/test_article_repository.py` (gated on `TEST_DATABASE_URL`)

**Interfaces:**
- Consumes: `ArticleDraft` from Task 1, `TopicCardRow`/`EditorDecisionRow`/`Signal` (existing).
- Produces: `list_researched_undrafted(limit) -> list[tuple[TopicCardRow, ResearchPackageRow]]`
  and `insert(draft, *, cost_usd, calls, tokens) -> bool`, which Task 4's stage consumes.

**What to build:**

Mirror `ResearchRepository` (`src/signalforge/db/repositories/research.py`) exactly in shape:

`list_researched_undrafted(limit)` — same DISTINCT-ON-latest-decision join pattern
`list_accepted_unresearched` uses, but filtering on `ResearchPackageRow.status == "researched"`
(not the editor decision — a card only needs drafting once FR-06 has actually produced a
`researched` package, regardless of what today's accept/reject decision says) and excluding
cards that already have an `article_drafts` row. Returns the card alongside its
`ResearchPackageRow` (the stage needs the package's documents/claims, not just the card) —
decide the exact join based on what Task 4 actually needs to read, and say so in your report if
the return shape changes from what's written here.

`insert(draft, *, cost_usd, calls, tokens)` — same `ON CONFLICT (card_id) DO NOTHING` pattern as
`ResearchRepository.insert`, deriving the row from `draft.model_dump(mode="json")`.

**Testing:** integration tests against a real test DB (gated, same skip convention as
`tests/integration/test_research_repository.py`): a researched-but-undrafted card is returned; a
card with an existing draft is excluded; a card whose research package is `needs_more_info` or
`failed` (not `researched`) is excluded; `insert` is idempotent on conflict.

---

## Task 3: Writer and judge roles

**Files:**
- Modify: `src/signalforge/core/config.py`
- Modify: `src/signalforge/llm/roles.py`
- Test: extend `tests/unit/test_config.py`, `tests/unit/test_roles.py` (if it exists; check) with
  the two new roles, same style as the existing `research_extraction`/`claim_embedding` role
  tests.

**What to build:**

Two new `Settings` fields (`llm_model_article_writer`, `llm_model_claim_judge`), two new entries
in `build_roles()` (`article_writer`, `claim_judge`) — exactly the pattern
`llm_model_research_extraction` / `research_extraction` already establishes. Pick sensible
defaults (a cheap writer-capable model for the writer role, a different-family cheap model for
the judge — e.g. if the writer defaults to an `openai/...` model, the judge should default to a
model from a different vendor namespace, since `ModelSpec.family` is derived from the
`vendor/model` string's prefix). State your chosen defaults in your report so the task reviewer
can sanity-check the family split.

**Why separate from Task 4:** this is pure configuration, independently testable, and Task 4's
fail-fast role-family check needs these roles to already exist.

---

## Task 4: `run_draft` stage — writer, span check, judge, status, gate

**Files:**
- Create: `src/signalforge/stages/draft.py`
- Test: `tests/integration/test_draft.py` (gated on `TEST_DATABASE_URL`, `FakeProvider`-backed,
  same style as `tests/integration/test_research.py`)

**Interfaces:**
- Consumes: `ArticleDraftRepository` (Task 2), roles from Task 3, `span_exists` from
  `signalforge.stages.research_extraction` (unchanged, reused as-is), `ClaimStatus` from
  `signalforge.core.artifacts.research`.
- Produces: `run_draft(session, gateway_factory, *, budget_limits, limit) -> DraftResult`
  (mirror `ResearchResult`'s shape: considered/drafted/needs_more_info/failed/stage_run_id).

**What to build, in order, per the spec's "Pipeline" section:**

1. Stage scaffolding: `StageRun` row, fail-fast `model_for` check for BOTH roles before the loop
   (mirror `run_research`'s existing fail-fast check, which currently checks `ROLE` and
   `EMBEDDING_ROLE` — add a third check here: compare the two roles' resolved `family` and raise
   `ConfigurationError` if they match). Per-card loop: fresh `Budget` + `LLMGateway` per card,
   same as `run_research`.
2. Template selection: a pure function, no LLM call, implementing the 2026-09-27 spec's
   first-match-wins rule. Put it in a place a unit test can hit directly without spinning up the
   stage (either its own small module or a clearly separated function in `draft.py` — your call,
   note it in your report).
3. Writer call: one `complete_json` per card against `article_writer`, input built from the
   `ResearchPackage`'s documents/claims only, output validated against a pydantic schema shaped
   like the template's expected output (title/dek/sections/claims/sources/cover). Escape
   untrusted text per the Global Constraints section above.
4. Mechanical span check: for every claim the writer produced, call `span_exists` against the
   `ResearchPackage` document(s) it cites. Record pass/fail per claim; a failing claim does not
   abort the card, it's an input to status assignment and the review summary.
5. Judge call: one batched `complete_json` against `claim_judge`, all claims from one card in one
   call, schema `{"claims": [{"index": int, "supported": bool}]}`.
6. Status assignment: pure function implementing PRD Sec. 11's table exactly (see the spec's
   "Status assignment" step for the five-case breakdown, including how to fold in FR-06's
   `gaps_and_disagreements` signal for the `conflicting` case). No LLM call. Unit-testable in
   isolation — write it as its own function, not inlined into the per-card loop, so Task 4's
   reviewer and future readers can verify the table mapping without tracing the whole stage.
7. Publish gate: deterministic checks from the 2026-09-27 spec (em/en dash used as a dash,
   banned authorship phrases, length within the template's target band). Also its own function,
   unit-testable with plain strings, no stage machinery. A failure routes the card to
   `needs_more_info`, reason appended to the review summary — do not raise an exception for a
   gate failure, it's an expected outcome, not an error.
8. Review summary: mechanically assembled text (see spec), built from the outputs of steps 4-7.
9. Error routing at the per-card level: match `run_research`'s existing routing exactly —
   `BudgetExceededError` → `failed`, empty draft; other `SignalForgeError` → log, `failed`, empty
   draft, loop continues; normal completion → status from step 6/7.

**Testing:** integration tests covering (at minimum) the six cases the spec's "Testing" section
lists: a clean draft reaching `drafted`; a span-check failure; a judge disagreement; a
publish-gate failure; a budget exhaustion mid-card; the role-family fail-fast check raising
`ConfigurationError` before any card is touched. Unit tests for template selection, status
assignment, and the publish gate in isolation (no DB, no network, no stage).

**Watch for:** this is the biggest task in the plan. If the implementer finds it sprawling past
roughly 400-500 lines of stage code, that's a signal the per-card logic (steps 2-8) should split
into a `draft_extraction.py` sibling module, same relationship `research.py` has to
`research_extraction.py`. Don't force it into one file if the existing codebase's own precedent
says otherwise.

---

## Task 5: Editor-vs-public data boundary

**Files:**
- Wherever the existing `/editor` API routes live (check how FR-06/FR-05's editor routes are
  structured before writing new ones — follow the same router/handler pattern, don't invent a
  new one)
- A public read path for a drafted article, if one doesn't already exist for topic cards (check
  first)
- Test: a web test scanning the public response shape for editor-only field names (model trail,
  prompt version, template-choice reasoning, full review summary), same pattern the existing
  editor-console tests use for other editor-only data — find that existing test and mirror its
  scanning approach exactly.

**What to build:**

Expose `ArticleDraft` through two shapes: a full one for `/editor` (every field, including
`review_summary`) and a trimmed one for anything public-facing (title/dek/sections/claims with
their status/sources/cover — no model trail, no prompt version, no template-choice reasoning, no
`review_summary`). Read the spec's "Editor/public data boundary" section for the exact field
list.

**Why this is its own task:** it's the one place a mistake (leaking an editor-only field into a
public response) is a real trust/security issue, not just a bug — it deserves its own reviewer
pass, isolated from the stage logic in Task 4.

---

## Task 6: Frontend: real draft shape, delete the mock

**Files:**
- Modify: `apps/web/src/lib/mock/article.ts` — delete once Task 5's real endpoint exists and this
  task wires `ArticlePreview` to it
- Modify: `apps/web/src/components/triage/ArticlePreview.tsx` and
  `apps/web/src/components/triage/ArticlePreview.test.tsx`
- Any API client/fetch code needed to call Task 5's public or editor read path from the triage
  view (check how other dashboard data already gets fetched client-side, follow that pattern)

**What to build:**

Wire `ArticlePreview` to the real draft shape instead of `mockArticle`. In the same change,
correct the drift the research doc identified: `template` becomes the real 4-value union (not a
bare `string`), and claims' per-claim `sourceLabel`/`sourceUrl` becomes a top-level `sources[]`
array matching the backend shape from Task 1/5. Delete `apps/web/src/lib/mock/article.ts` once
nothing imports it — its own header comment says exactly this ("this fixture should be deleted
rather than reused as a fallback").

**Testing:** update `ArticlePreview.test.tsx` to the real shape; no new test framework, follow
whatever this repo's existing web tests already use (check `apps/web/AGENTS.md` for anything
version-specific before touching Next.js APIs).

---

## Execution Notes

- Tasks 1 → 2 → 3 → 4 are a strict dependency chain (artifact before repository, roles before the
  stage that fail-fasts on them). Task 5 depends on Task 4's artifact existing with real data to
  shape a response around; it does not strictly need Task 4 to be *merged* first if the
  implementer works from Task 1's artifact directly, but dispatching it after Task 4 avoids
  rework if Task 4's review changes the artifact's shape.
- Task 6 depends on Task 5 being merged — it needs a real endpoint to call.
- Per the subagent-driven-development process: fresh subagent per task, task review after each,
  one PR per task, final whole-branch review at the end covering all six tasks together (that
  review is the right place to catch any drift between Task 1's artifact shape and Task 6's
  frontend shape that crept in across tasks).
- If a task's reviewer finds the writer or judge prompt producing inconsistent JSON shapes
  (common with structured multi-field outputs), that's exactly what `complete_json`'s one
  repair-retry is for — don't add a second retry layer in `draft.py`, trust the gateway's
  existing mechanism the way `research.py` does.
