# Phase 3: Topic Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn relevant, assessed signals into ranked topic cards that an editor can accept, reject or snooze with reason tags, and record those decisions so the two-week usefulness test can run.

**Architecture:** A `cards` stage (LLM role `topic_card`, same gateway and stage-run pattern as `assess`) writes one `TopicCard` per relevant assessed signal. A rules-based ranker scores cards and a queue builder picks the top K plus a small wildcard slot. Editor decisions are stored in `editor_decisions` and exposed through FastAPI (`GET /cards/queue`, `POST /cards/{id}/decision`). The web triage screen is a **placeholder structure only**: data wiring and component skeletons with no visual design, because the design references and `global.css` (Tailwind) arrive later.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, the existing LLM gateway, Next.js (no styling yet), vitest.

**Spec:** `docs/signalforge_prd.md` FR-03 to FR-05, the data model (lines 748 and 749), stage table, dashboard section (line 845) and build-order row "3 Topic Intelligence" (line 888). Exit criterion: run about 2 weeks nightly; the editor answers "are the cards useful?" using decision time per card, accept rate and their own verdict. Do not build Phase 4 until that passes.

## Global Constraints

- Python 3.13, ruff, mypy strict, pre-commit must pass. Conventional Commits, no AI or Co-Authored-By trailers.
- PRs at most 400 changed lines, squash-merged.
- No new runtime dependency. No hard vendor dependency: models are reached by role through the gateway.
- Migrations are applied to the dev DB only from main (ADR-0004).
- Fetched and generated text is untrusted data: prompts delimit it, output is validated with Pydantic, and the page renders it as text, never as HTML.
- Failures raise `SignalForgeError` subtypes and are recorded in `stage_runs`; nothing is silently skipped.
- Web: no CSS, no Tailwind, no design tokens in this phase. Markup is semantic and unstyled. Styling follows the provided `global.css` and Tailwind design system in a later change.
- Never print `.env` values.

## UI scope, stated plainly

Phase 3 is about 70% backend. The UI here is limited to a placeholder triage route so decisions can be recorded. The full UI is spread over several phases in the PRD: Phase 3 the triage dashboard (this plan, placeholder), Phase 5 draft review with claim highlighting, Phase 6 the public site (articles, tags, RSS, JSON-LD), Phase 7 analytics dashboards. Real visual design for Phase 3 happens when the design references and `global.css` are supplied.

## Rulings made while planning

- **One card per signal, not per cluster.** PRD says Signal → Cluster → TopicCard, but clustering is deferred (plan `2026-09-27-phase-2b-dedupe-clustering.md`). `topic_cards.signal_id` is used now; a nullable `cluster_id` is added by the clustering work. Costs duplicate cards for repeated stories until then.
- **Cards only for signals whose latest assessment has `is_relevant` true.** Cheaper and keeps the queue on-niche. Costs missing cards if the assessment prompt is too conservative (known, calibrated at about 96% agreement).
- **Rules-based ranker first** (PRD §Ranker plugins: "rules, embedding, learned later"). Weighted sum of relevance, novelty, signal strength and confidence. Weights live in one constant, tuned from decision data.
- **Wildcards:** the queue reserves `WILDCARD_SLOTS = 2` positions for relevant cards ranked below the cutoff, chosen by highest novelty, flagged `wildcard=true`. This is the exploration slot that stops the queue from only confirming past taste.
- **Write endpoints use a shared secret** (`EDITOR_API_KEY` in the `X-Editor-Key` header) until dashboard auth is decided (PRD open question 3). Reads stay open like today. Costs weak protection; fine for a single-editor dev setup and easy to replace.
- **Latest decision wins.** `editor_decisions` is append-only; a card's status is its newest decision. This keeps the history the exit test needs.
- **Card `format` and `evergreen_score` are generated but not used for ranking yet.** They cost tokens now and are needed by Phase 4; if the output quality is poor they are dropped without a migration issue because they are nullable in the queue query.

---

## File Structure

- Create `src/signalforge/core/artifacts/topic_card.py`: `TopicCard`, enums.
- Create `src/signalforge/db/models/cards.py`: `TopicCardRow`, `EditorDecisionRow`.
- Create `src/signalforge/db/migrations/versions/0005_add_topic_cards_and_decisions.py`.
- Create `src/signalforge/db/repositories/cards.py`: `CardRepository`.
- Create `src/signalforge/stages/cards.py`: prompt, `run_cards`.
- Create `src/signalforge/plugins/rankers/rules.py`: `RulesRanker`, `build_queue`.
- Modify `src/signalforge/llm/roles.py`, `src/signalforge/core/config.py`: role `topic_card`, `llm_model_topic_card`, `editor_api_key`.
- Create `apps/worker/cards.py`, `apps/worker/triage_metrics.py`; modify `apps/worker/tick.py`.
- Create `apps/api/routes/cards.py`; modify `apps/api/schemas.py`, `apps/api/main.py`, `apps/api/deps.py`.
- Create `apps/web/src/app/triage/page.tsx`, `apps/web/src/components/triage/{CardView,DecisionBar,ReasonTags}.tsx`; modify `apps/web/src/lib/api.ts`.
- Create `docs/adr/0007-topic-cards-per-signal-with-rules-ranker.md`, `docs/ui/triage-placeholder.md`.
- Tests: one file per unit under `tests/unit/`, DB behavior under `tests/integration/`.

---

### Task 1: TopicCard artifact, tables, repository

**Files:**
- Create: `src/signalforge/core/artifacts/topic_card.py`, `src/signalforge/db/models/cards.py`, migration `0005`, `src/signalforge/db/repositories/cards.py`
- Modify: `src/signalforge/db/models/__init__.py`
- Test: `tests/unit/test_topic_card_artifact.py`, `tests/integration/test_cards_repository.py`

**Interfaces:**
- Produces (artifact, follows `SignalAssessment` style):
  - `ArticleFormat(StrEnum)`: `explainer`, `deep_dive`, `comparison`.
  - `RiskFlag(StrEnum)`: `unverified_claim`, `single_source`, `hype`, `paywalled`, `stale`.
  - `TopicCard(Artifact)`, `SCHEMA_VERSION = 1`: `signal_id: UUID`, `what_happened: str (1..400)`, `why_it_matters: str (1..300)`, `novelty: float (0..1)`, `signal_strength: float (0..1)`, `coverage_gap: str (max 300, may be empty)`, `suggested_angle: str (1..200)`, `format: ArticleFormat`, `evergreen_score: float (0..1)`, `confidence: float (0..1)`, `risk_flags: tuple[RiskFlag, ...]`, `prompt_version: str`, `model: str`.
- Produces (tables):
  - `topic_cards(id, signal_id FK signals ON DELETE CASCADE, stage_run_id FK stage_runs, llm_call_id FK llm_calls NULL, what_happened, why_it_matters, novelty, signal_strength, coverage_gap, suggested_angle, format varchar(16), evergreen_score, confidence, risk_flags JSONB, score float NOT NULL DEFAULT 0, wildcard bool NOT NULL DEFAULT false, prompt_version, model, created_at, updated_at, schema_version)`. Unique `(signal_id, prompt_version)`. Index on `(score DESC)`.
  - `editor_decisions(id, topic_card_id FK topic_cards ON DELETE CASCADE, decision varchar(16) CHECK in ('accepted','rejected','snoozed'), reason_tags JSONB NOT NULL DEFAULT '[]', note text NOT NULL DEFAULT '', decision_ms int NULL, decided_at timestamptz DEFAULT now(), created_at, updated_at, schema_version)`. Index on `(topic_card_id, decided_at DESC)`.
- Produces (repository, takes `Session`):
  - `CardRepository.insert(card: TopicCard, *, stage_run_id: UUID, llm_call_id: UUID | None, score: float) -> bool` (False when the unique pair exists).
  - `list_uncarded(limit: int) -> list[tuple[Signal, SignalAssessment row]]` — signals whose latest assessment is relevant and that have no card for the current card prompt version, newest first. Reuse the latest-assessment `DISTINCT ON` logic from `db/repositories/signals.py` (extract a shared helper if it reads cleaner; do not duplicate the SQL).
  - `add_decision(card_id, decision, reason_tags, note, decision_ms) -> EditorDecisionRow`.
  - `latest_decision(card_id) -> EditorDecisionRow | None`.

- [ ] **Step 1: Write failing tests.** Artifact: valid card builds; score outside 0..1 rejected; unknown `format` rejected; empty `what_happened` rejected; unknown risk flag rejected. Repository (integration, skip without `TEST_DATABASE_URL`): insert once returns True, twice returns False; `list_uncarded` returns only relevant signals without a card; `add_decision` twice gives `latest_decision` the newer one; decision `"maybe"` is rejected by the CHECK constraint.
- [ ] **Step 2: Run to verify failure:** `uv run pytest tests/unit/test_topic_card_artifact.py tests/integration/test_cards_repository.py -v` → FAIL.
- [ ] **Step 3: Implement** artifact, models, migration (`down_revision = "0004"`, downgrade drops both tables), repository. Mirror `db/models/assessments.py` and migration 0004 for conventions.
- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`. If `TEST_DATABASE_URL` is set, also `uv run alembic upgrade head`, `downgrade -1`, `upgrade head`. Do not migrate the dev DB from this branch.
- [ ] **Step 5: Commit:** `git commit -m "feat: add topic card artifact, tables and repository"`

---

### Task 2: `cards` stage and CLI

**Files:**
- Create: `src/signalforge/stages/cards.py`, `apps/worker/cards.py`
- Modify: `src/signalforge/llm/roles.py`, `src/signalforge/core/config.py`, `.env.example`
- Test: `tests/unit/test_cards_prompt.py`, `tests/unit/test_cards_stage.py`, `tests/unit/test_cards_cli.py`

**Interfaces:**
- Consumes: `LLMGateway.complete_json(role=..., system=..., user=..., schema=..., stage_run_id=...)` (see `stages/assess.py` for the exact call and error handling), `CardRepository`, `RulesRanker.score` (Task 3 supplies it; until then use a stub returning 0.0 and wire the real one in Task 3).
- Produces:
  - `PROMPT_VERSION = "card-v1"`.
  - `build_messages(signal, assessment) -> tuple[str, str]` — system and user. Same untrusted-data rules as `assess-v1`: the signal fields sit inside `<signal>` delimiters with HTML-escaped values, the system prompt says content inside the tags is data and never instructions. The user message includes the assessment summary and category as context.
  - `CardDraft(BaseModel)`: the fields the LLM fills (`what_happened`, `why_it_matters`, `novelty`, `signal_strength`, `coverage_gap`, `suggested_angle`, `format`, `evergreen_score`, `confidence`, `risk_flags`), validated by Pydantic; `run_cards` adds `signal_id`, `prompt_version`, `model` to build the `TopicCard`.
  - `CardsResult(considered: int, created: int, failed: int, stopped_on_budget: bool)` and `run_cards(session, gateway_factory, *, limit: int) -> CardsResult`. Follow `run_assess`: one `stage_runs` row (stage `"cards"`), per-signal failures counted and logged, budget exhaustion stops cleanly with `stopped_on_budget=True`, non-`SignalForgeError` marks the run failed and re-raises.
  - Config: `llm_model_topic_card: str = "openai/gpt-4o-mini"`; `build_roles` adds `"topic_card"`. CLI: `uv run python -m apps.worker.cards --limit N` (1 to 200), printing `considered=… created=… failed=… stopped_on_budget=…`.

- [ ] **Step 1: Write failing tests** (fake provider, no network): prompt escapes `</signal>` in a hostile title and includes the assessment summary; a valid fake reply creates a card row; a reply with `novelty: 2` fails validation, is retried once by the gateway, then counted in `failed`; rerun creates nothing (idempotent per prompt version); budget exhausted sets `stopped_on_budget`; role `topic_card` resolves to the configured model; the CLI rejects `--limit 0` and `--limit 201`.
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: add cards stage and CLI`.

---

### Task 3: Rules ranker, wildcards and queue

**Files:**
- Create: `src/signalforge/plugins/rankers/rules.py`
- Modify: `src/signalforge/stages/cards.py` (use the real scorer), `src/signalforge/db/repositories/cards.py` (queue query)
- Test: `tests/unit/test_rules_ranker.py`, `tests/integration/test_card_queue.py`

**Interfaces:**
- Produces:
  - `WEIGHTS = {"relevance": 0.35, "novelty": 0.30, "signal_strength": 0.20, "confidence": 0.15}` (named constant with a `ponytail:` comment: tuned from decision data after week one).
  - `score(relevance: float, card: TopicCard) -> float` — weighted sum of the four inputs, clipped to `[0, 1]`, minus `0.1` per risk flag in `{"unverified_claim", "hype"}` (floor 0).
  - `RulesRanker` with `name = "rules"` and `score` implementing the ranker Protocol shape used elsewhere (a card-level adaptation is fine; document the deviation from PRD's cluster argument in a docstring).
  - `CardRepository.queue(*, limit: int = 15, wildcard_slots: int = 2, since: datetime) -> list[QueueItem]`. `QueueItem` carries the card, signal title, source, canonical URL, `wildcard: bool`, and `status`. Cards are eligible when their latest decision is missing or `snoozed`, and `created_at >= since`. The first `limit - wildcard_slots` items are the highest `score`. The wildcard items are the `wildcard_slots` eligible cards not already chosen with the highest `novelty`, marked `wildcard=True`. Fewer eligible cards than slots is fine; never duplicate a card.

- [ ] **Step 1: Write failing tests:** score of an all-ones card is 1.0 and all-zeros is 0.0; each risk flag lowers the score by 0.1 and the floor is 0; weights sum to 1.0 (assert on the constant); queue with 20 cards returns 15, of which 13 are top-scored and 2 are the highest-novelty leftovers flagged wildcard; an accepted or rejected card never appears; a snoozed card does appear; fewer than 15 eligible cards returns them all without duplicates.
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: add rules ranker and card queue`.

---

### Task 4: Editor decision API

**Files:**
- Create: `apps/api/routes/cards.py`
- Modify: `apps/api/schemas.py`, `apps/api/main.py`, `apps/api/deps.py`, `src/signalforge/core/config.py`, `.env.example`
- Test: `tests/unit/test_api_cards.py`

**Interfaces:**
- Consumes: `CardRepository.queue`, `add_decision`, `latest_decision`.
- Produces:
  - `GET /cards/queue?limit=15&days=7` → `list[CardOut]`. `CardOut` has the card fields, `signal: {id, title, source, canonical_url}`, `score`, `wildcard`, `status` (`proposed` | `snoozed`), `created_at`. Open read, like `GET /signals`. `limit` 1 to 50, `days` 1 to 30, validated.
  - `POST /cards/{card_id}/decision` with body `{decision: "accepted"|"rejected"|"snoozed", reason_tags: list[str] (max 8, each 1..32 chars from a fixed set), note: str (max 500), decision_ms: int | None (0..3_600_000)}` → 201 with the stored decision. Requires header `X-Editor-Key` equal to `settings.editor_api_key` (compare with `secrets.compare_digest`); missing or wrong key → 401 with the standard error body; unset key in settings → 503 `editor_key_not_configured` so an unconfigured server never accepts writes. Unknown card → 404. Unknown reason tag → 422.
  - `REASON_TAGS = ("off_niche", "too_incremental", "duplicate", "already_covered", "low_quality_source", "great_angle", "timely", "evergreen", "needs_more_evidence")` in one module, imported by the schema and by the placeholder page (mirrored in `api.ts`).
  - Config: `editor_api_key: SecretStr | None = None`.

- [ ] **Step 1: Write failing tests** with `TestClient` and a stubbed repository: queue returns items and respects `limit`; write without header → 401; wrong key → 401; unset server key → 503; valid write → 201 and stored; bad decision value → 422; unknown tag → 422; unknown card → 404; `limit=0` → 422; the key never appears in any response body or log line (assert on captured logs).
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: add card queue and editor decision endpoints`.

---

### Task 5: `tick` integration and triage metrics

**Files:**
- Modify: `apps/worker/tick.py`, `README.md`, `.kiro/steering/tech.md`
- Create: `apps/worker/triage_metrics.py`
- Test: `tests/unit/test_tick_cli.py` (extend), `tests/unit/test_triage_metrics.py`

**Interfaces:**
- Produces:
  - `tick` runs cards after assess (only when the LLM provider is not `fake`, same rule as assess), with `--cards-limit` (default 25, 1 to 200). A cards failure is logged and counted, never stops other work. Exit codes stay 0 ok, 1 every source failed, 2 any of assess or cards failed while ingest succeeded.
  - `uv run python -m apps.worker.triage_metrics [--days 14]` prints the exit-test numbers: cards created, decided, accept rate (`accepted / decided`), snooze rate, median and 90th-percentile `decision_ms`, decisions by reason tag, and cards still waiting. It reads only. Guard divide-by-zero (no decisions prints `accept_rate=n/a`).
  - Docs: the nightly cron line (`0 2 * * *`, absolute `uv` path, log under `$HOME`, same notes as the tick cron line), the three new commands, `EDITOR_API_KEY` and `LLM_MODEL_TOPIC_CARD` in `.env`.

- [ ] **Step 1: Write failing tests:** tick calls cards after assess; cards failure gives exit 2 and does not lose assess results; fake provider skips cards with a message; metrics on a seeded fixture (4 decided: 2 accepted, 1 rejected, 1 snoozed) give accept rate 0.5 and the right median; no decisions gives `n/a` without an exception.
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: run cards in tick and add triage metrics`.

---

### Task 6: Placeholder triage screen, ADR and UI notes

**Files:**
- Create: `apps/web/src/app/triage/page.tsx`, `apps/web/src/components/triage/CardView.tsx`, `DecisionBar.tsx`, `ReasonTags.tsx`, `docs/ui/triage-placeholder.md`, `docs/adr/0007-topic-cards-per-signal-with-rules-ranker.md`
- Modify: `apps/web/src/lib/api.ts`
- Test: `apps/web/src/lib/api.test.ts` (extend), a vitest render test for `CardView` if the repo already renders components in tests; otherwise type and build checks.

**Interfaces:**
- Consumes: `GET /cards/queue`, `POST /cards/{id}/decision`.
- Produces:
  - `api.ts`: types `Card`, `Decision`, `ReasonTag` (union of the nine tags from Task 4), `fetchQueue(limit?: number): Promise<Card[]>`, `postDecision(cardId, body, editorKey): Promise<void>`. Errors throw a typed `ApiError` carrying the status; never swallow a non-2xx.
  - `/triage` page (server component) fetches the queue and renders `<CardView>` for each card. `CardView` renders the card fields as plain text in semantic elements (`article`, `h2`, `dl`, `p`), a `wildcard` marker, the source link, and `<DecisionBar>`. `DecisionBar` is a small client component with accept, reject and snooze buttons and `<ReasonTags>` checkboxes, records `decision_ms` from when the card rendered, and calls `postDecision`. The editor key is read from an input on the page and kept in memory only (never `localStorage`, never in the URL). Keyboard shortcuts (`a`, `r`, `s`, `j`, `k`) are **listed in the UI notes doc, not implemented**.
  - **No styling.** No classes, no CSS files, no Tailwind, no colors. A `TODO(design)` comment at the top of each component says the design references and `global.css` are pending. Text is rendered as React text nodes, never with `dangerouslySetInnerHTML`.
  - `docs/ui/triage-placeholder.md` records the planned structure: screen layout blocks (queue list, card detail, decision bar, reason tags), states (loading, empty queue, error, wrong key, saving, saved), the keyboard map, and what the supplied references and `global.css` must decide (spacing, type scale, color tokens, focus rings, wildcard treatment, dark mode).
  - ADR-0007 records the rulings listed at the top of this plan.

- [ ] **Step 1: Write failing tests:** `fetchQueue` returns typed cards from a mocked `fetch`; a 500 throws `ApiError` with status 500; `postDecision` sends `X-Editor-Key` and the JSON body and throws on 401; a card containing `<script>` in `what_happened` renders as text (render test, or an assertion that no component uses `dangerouslySetInnerHTML`, via a grep-based vitest check).
- [ ] **Step 2 to 5:** run to fail, implement, then `cd apps/web && npm run typecheck && npm run lint && npm run test && npm run build && npm run format:check`, commit `feat: add placeholder triage screen`.

---

## Acceptance (after merge, on the dev DB)

- [ ] Apply migration 0005 to the dev DB from main only: `uv run alembic upgrade head`.
- [ ] Set `EDITOR_API_KEY` in `.env` (do not print it), then run `LLM_PROVIDER=openai_compatible LLM_BASE_URL=https://openrouter.ai/api/v1 uv run python -m apps.worker.cards --limit 25`; expect `failed=0` and a cost under about $0.01.
- [ ] `curl 'http://localhost:8000/cards/queue?limit=15'` returns ranked cards with two wildcards; a `POST` without the key returns 401.
- [ ] Open `/triage`, record a few decisions, then run `triage_metrics`; the numbers match what was clicked.
- [ ] Install the nightly cron line. Start the two-week exit test; record the editor's verdict on card usefulness in the Phase 3 exit note.

## Self-Review

- **Spec coverage:** relevance filter (exists from 1.6, used as the card gate); topic cards (Tasks 1, 2); ranker plus wildcards (Task 3); editor decisions and reason tags (Tasks 1, 4, 6); dashboard (placeholder in Task 6, full design deferred by the user); nightly run and exit metrics (Task 5). Snoozed backlog is covered by the queue including snoozed cards. Cost view and pipeline-status views from PRD line 845 are not in Phase 3's exit test and are deferred.
- **Placeholders:** Tasks 2 to 6 describe steps 2 to 5 in one line because they repeat Task 1's pattern; the executor must still write every test listed in Step 1. The weights, tag set, endpoint shapes and status codes are given exactly. The UI has no design by request, and the doc lists what is pending.
- **Type consistency:** `TopicCard` fields, `CardRepository` method names, `REASON_TAGS`, `run_cards` and `score` signatures match across tasks. Task 2's temporary scorer stub is replaced in Task 3.
- **Known ceilings:** the shared-secret write check is not real auth; the ranker weights are guesses until decision data exists; per-signal cards duplicate repeated stories until clustering lands; card quality depends on the `card-v1` prompt, so calibrate it on about 20 cards before trusting the queue.
