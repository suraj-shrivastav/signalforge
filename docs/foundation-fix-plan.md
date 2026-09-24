# Foundation fix plan

Status: proposed. Scope: the gaps found while verifying the initial setup. Each item states the symptom, the root cause and a fix at the cause, not a workaround.

## Findings and root causes

### F1. Database is stamped `0002`, repo has only `0001`

**Symptom.** `alembic current` fails with `Can't locate revision identified by '0002'`. The database already holds `stage_runs` and `llm_calls`.

**Evidence.**
- `0002_add_stage_runs_and_llm_calls.py` exists only on the unmerged branch `feat/ops-tables` (commit `11736a0`).
- `feat/core-budget` branches from `main` at `b336806` and does not contain it.
- The single hosted Supabase database is shared by every branch, and `alembic upgrade head` was run from `feat/ops-tables`.

**Root causes.**
1. There is one shared, long-lived database and no per-developer or per-branch isolation. Any branch can advance its schema, so the schema follows whichever branch ran last, not `main`.
2. Nothing verifies that the migration history in the repo matches what a database is stamped with. Drift is found by accident.
3. Feature branches are cut in parallel from `main` and touch the same linear migration chain. Two branches adding `0002` would collide.

### F2. No structured logging or correlation IDs

**Symptom.** No logging setup in `src`. Only `LOG_LEVEL` is read in config.

**Root cause.** Standards section 6 requires structured logs with correlation IDs and one LLM-call log line with model, tokens, cost and latency. The logging foundation was never scheduled, so each later module would invent its own logging.

### F3. CI cannot catch migration problems

**Symptom.** CI runs lint, format, types and tests only. It never applies migrations.

**Root cause.** Tests are network-free by rule, and no throwaway Postgres is provided to CI. A broken or forked migration chain merges green.

### F5. GitHub CLI is signed in as the work account

**Symptom.** `gh auth status` shows `suraj-neuralarc`, and `gh pr list` cannot resolve `suraj-shrivastav/signalforge`.

**Root cause.** The git identity is routed per directory (conditional include), but `gh` keeps one global login. Git operations use the personal SSH alias, PR operations do not. A PR opened with `gh` would be attributed to the wrong account.

### F4. Uncommitted working-tree changes and a stale local task list

**Symptom.** `.kiro/steering/structure.md` modified, `docs/architecture-diagrams.md` untracked, on a branch that is unrelated to them.

**Root cause.** Docs edits were made on a feature branch instead of their own `docs/` branch, against the branch-per-change rule.

## Fix plan

Order matters. Each step is its own branch and PR, squash-merged, per the git workflow.

### Step 0. Fix the GitHub identity (F5)

Run `gh auth login` as `suraj-shrivastav` (or add the account and `gh auth switch`). Confirm with `gh auth status` and `gh pr list`. Prerequisite for every PR below.

### Step 1. Reconcile the shared database (F1, immediate)

Branch: none. This is an operations step, not a code change.

1. The branches are stacked: `feat/ops-tables` contains `feat/core-artifacts`. Merge in this order, one squash PR each: `feat/core-artifacts`, `feat/ops-tables`, `chore/scaffold-package-structure`, `feat/core-budget`. After each merge, rebase the next branch on `main`.
2. `gh` must first be signed in as `suraj-shrivastav` (F5), or the PRs opened in the GitHub UI. Merging directly to `main` is not allowed by the standards.
3. Confirm `alembic current` reports `0002 (head)` from `main`. No `stamp` and no manual edits to `alembic_version`. Stamping would hide the drift, not remove it.
4. Record the outcome in the PR description.

Exit check: `alembic current` and `alembic heads` agree, and `alembic check` reports no drift between models and database.

### Step 2. Stop the drift from recurring (F1)

Branch: `chore/db-environments`. Needs an ADR, because it changes how the team works with the database. No local Docker: Supabase is the only database.

1. Use the existing project as `signalforge-dev`. Create `signalforge-prod` only at first deploy (PRD section 42, Railway, migrations as a release step), not before. Production credentials never sit in a developer `.env`.
2. Dev database rule: a branch may apply its own migration to dev to test it, but must `alembic downgrade` it before switching branches or merging. The schema on dev then matches `main` plus at most the one branch in flight.
3. Prod rule: schema changes only by `alembic upgrade head` run from `main`, in one documented place, after merge.
4. Recovery rule: if dev drifts anyway, reset it (drop the `public` schema objects and re-run `alembic upgrade head` from `main`). Dev holds no data worth keeping. Never `alembic stamp` to hide a mismatch.
5. Migration chain: when two open branches add a migration, the second rebases and renumbers before merge. State this in the ADR.
6. Document the rules in `README.md` and `.kiro/steering/standards.md`, and list the dev and prod variable names in `.env.example`.

Not done here: Supabase Branching (paid) or a migration-locking tool. Add one only if two projects prove insufficient.

### Step 3. Guard migrations in CI (F3)

Branch: `chore/ci-migration-check`.

1. Add a throwaway Postgres service container with pgvector to the CI job. It lives only in the GitHub runner, so nothing is needed locally and CI never touches Supabase.
2. Add steps: `alembic upgrade head`, `alembic check` (models match migrations), and `alembic downgrade base` then `upgrade head` (reversibility).
3. Add a single-head assertion (`alembic heads` returns exactly one revision) so a forked chain fails the build.

This is CI-only. Unit tests stay network-free as the standards require.

### Step 4. Logging foundation (F2)

Branch: `feat/core-logging`. Plan first (issue or draft PR), because it sets a project-wide convention.

1. Add `core/logging.py`: JSON output, configured once from `Settings.log_level`, with a `correlation_id` carried in a `contextvar` and attached to every record. It maps to the PRD section 40 identifiers: `request_id` for an LLM call and `stage_run_id` for a stage run, so a log line joins to `llm_calls` and `stage_runs` rows.
2. Redact secrets: a filter that masks `SecretStr` values and known key names.
3. Provide one helper for the LLM-call log line (model, tokens, cost, latency) so the standard is met in one place.
4. Wire it at the process entry points only (worker and API). Library code just calls `logging.getLogger`.
5. Tests: correlation ID appears on records, secrets are masked, level comes from settings.

LLM tracing (Langfuse, PRD section 40 "from day one") is a separate decision and gets its own ADR when the first LLM call exists. It is not built here.

Dependency choice: standard library `logging` with a small JSON formatter. Add `structlog` only if the formatter grows past a small file.

### Step 5. Tidy the working tree (F4)

Branch: `docs/architecture-diagrams`. Done: committed as `6881e66`, diagrams only, no PRD change needed.

1. Move `docs/architecture-diagrams.md` and the `structure.md` edit onto this branch, off `main`.
2. Update the PRD in the same PR if the diagrams change current architecture, per the ADR rule.

## Verification for the whole plan

- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest` all green.
- `alembic upgrade head`, `alembic check` and `alembic heads` clean on the reconciled dev project and on the CI database.
- CI fails when a migration is missing, forked or not reversible (prove it once with a deliberately broken branch).

## Out of scope

Domain models, queue wiring, plugins, pipeline stages, API and frontend. Those follow the gated build order in PRD section 43.
