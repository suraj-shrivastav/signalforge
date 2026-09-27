# SignalForge Tech Stack

Modular monolith in a monorepo. **Boring infrastructure around sophisticated product intelligence.**

Runtime: one FastAPI process, one Python worker, one Next.js app, one PostgreSQL database, a Postgres-backed job queue.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13 (pinned via `.python-version`), FastAPI |
| Packaging | uv (resolution, lockfile, task running); `src/` layout, hatchling build |
| Contracts | Pydantic (artifacts, validation) + `typing.Protocol` (plugin seams) |
| Database | PostgreSQL (Supabase for V1) with JSONB + pgvector |
| ORM / migrations | SQLAlchemy + Alembic |
| Queue + scheduler | Postgres-backed (Procrastinate or Arq — **open question**), `FOR UPDATE SKIP LOCKED` |
| LLM access | One OpenAI-compatible gateway; OpenRouter first |
| Search | `SearchProvider` abstraction; direct fetch + local extraction (trafilatura) first |
| Frontend | Next.js (public site + editor dashboard), TypeScript strict |
| Observability | Structured logs + LLM tracing (e.g. Langfuse) from day one |
| Lint / format | ruff (Python), eslint + prettier (TS) |
| Types | mypy strict over `src` and `tests`; TS strict |
| Tests | pytest, vitest, Playwright (triage + review flows only) |
| Deploy | Railway (`api`, `worker`, `web`, `scheduler`), Dockerized, migrations as a release step |

## Hard constraints

Deliberate exclusions. Do not introduce these without an ADR.

- **No LangChain / LangGraph.** Orchestration is plain Python.
- **No Redis, no Celery, no Kafka.** The queue is PostgreSQL.
- **No microservices.** Extract a module only for a concrete reason.
- **No Supabase SDK** beyond (optionally) auth. Use plain PostgreSQL semantics so a move to RDS is a connection-string change. Mind pooler modes with prepared statements.
- **No Railway-specific runtime dependencies.**
- **No direct DB access from Next.js.** Always `Next.js → HTTPS → FastAPI → repositories → PostgreSQL`.
- **No provider SDK imports outside their own plugin.**
- **No model IDs in stage code.** Stages reference a *role* (`article_draft`, `claim_verify`); the gateway resolves the model.
- **No browser-automation-heavy scraping.**

## LLM gateway rules

Stages say `role="article_draft"`, never `model="..."`. The gateway owns routing, capability checks (JSON mode, tools, context window), retries with exponential backoff, fallback chains, token and cost budgets, Pydantic output validation with retry, model-family constraints, and per-call cost/latency logging.

Budgets: ~$0.50 per topic (research), ~$1.50 per article (all stages).

## Untrusted input

Fetched web content is untrusted and may contain prompt injection. It is passed to models as delimited data, cannot define or modify tools, and cannot trigger side effects. Sanitize HTML before rendering. Respect robots.txt and source terms. Never reproduce large source passages.

## Commands

Prerequisite: uv. It provisions the pinned Python itself.

```bash
uv sync --all-groups          # install (creates .venv)
uv run pre-commit install     # commit + push hooks
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy                   # typecheck
uv run pytest                 # test
uv run alembic upgrade head                                    # apply migrations (dev only from a branch, see ADR-0004)
uv run python -m apps.worker.ingest hackernews --hours 48      # fetch and store
uv run python -m apps.worker.assess --limit 25               # summarize and score unassessed signals (needs LLM_PROVIDER + key)
uv run python -m apps.worker.cards --limit 25                # build topic cards for relevant signals (needs LLM_MODEL_TOPIC_CARD)
uv run python -m apps.worker.triage_metrics --days 14          # editor triage numbers (read only)
uv run python -m apps.worker.tick --hours 24 --assess-limit 25 --cards-limit 25  # ingest every source, then assess, then cards
uv run uvicorn --factory apps.api.main:create_app --port 8000  # API
cd apps/web && cp .env.example .env.local && npm run dev       # UI on :3000
TEST_DATABASE_URL=<migrated db url> uv run pytest -m integration   # integration tests
```

Scheduling: `tick` ingests all sources, then assesses, then builds topic cards (assess and cards need `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL_RELEVANCE` and `LLM_MODEL_TOPIC_CARD` in `.env`; both are skipped when the provider is `fake`; the editor API needs `EDITOR_API_KEY` in `.env`, set it to your own secret and never commit it). One failing stage never stops the later ones. Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | at least one source ingested and assess and cards ok or skipped |
| 1 | every source failed |
| 2 | ingest ok but assess or cards failed |

Cron, every 30 minutes (cron has a minimal PATH, so use the absolute path from `which uv`, or set `PATH=` in the crontab; the log is not rotated):

```
*/30 * * * * cd /Users/suraj/personal/signalforge && /opt/homebrew/bin/uv run python -m apps.worker.tick >> $HOME/signalforge-tick.log 2>&1
```

Nightly at 02:15 (offset so it never starts with the 02:00 tick), with the same notes (absolute `uv` path, log under `$HOME`, not rotated), to run a larger cards batch:

```
15 2 * * * cd /Users/suraj/personal/signalforge && /opt/homebrew/bin/uv run python -m apps.worker.tick --cards-limit 100 >> $HOME/signalforge-tick-nightly.log 2>&1
```

Overlapping runs are safe (`ON CONFLICT DO NOTHING`) but waste LLM spend, so keep the two schedules apart and wrap each command in `flock -n /tmp/signalforge-tick.lock` on Linux. macOS has no `flock` by default: use a lockfile check in a wrapper script, or launchd (which does not start a job that is still running).

Cost note: the budget is per stage per run (TOPIC scope, $0.50), not per day; real spend is bounded by the number of new signals.

Pre-commit runs lint, format and types on commit, and pytest on push, using the
versions in `uv.lock` so it cannot drift from CI.

## Editor console auth

The editor console (`apps/web/src/app/editor`) sits behind a single shared
password, not per-user accounts. Two environment variables control it, both
set via environment, never committed:

- `EDITOR_UI_PASSWORD`: the shared password checked on login.
- `EDITOR_COOKIE_SECRET`: the HMAC secret used to sign the session cookie.
  Falls back to `EDITOR_UI_PASSWORD` if unset, so the feature works with only
  one variable configured, but a real deployment should set both to
  independent secrets.

See `docs/ui/editor-console.md` for how the auth flow and the mock article
fixture work.
