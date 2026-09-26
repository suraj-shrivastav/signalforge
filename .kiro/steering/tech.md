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
uv run uvicorn --factory apps.api.main:create_app --port 8000  # API
cd apps/web && cp .env.example .env.local && npm run dev       # UI on :3000
TEST_DATABASE_URL=<migrated db url> uv run pytest -m integration   # integration tests
```

Pre-commit runs lint, format and types on commit, and pytest on push, using the
versions in `uv.lock` so it cannot drift from CI.
