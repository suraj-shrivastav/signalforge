# SignalForge

AI-engineering intelligence platform. It discovers emerging signals, surfaces them
to an editor, researches selected topics from stored evidence, and publishes
verified, traceable articles.

**The article is the output. The intelligence system behind it is the product.**

- Product and architecture baseline: [`docs/signalforge_prd.md`](docs/signalforge_prd.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Working agreements: [`.kiro/steering/`](.kiro/steering/)

## Prerequisites

[uv](https://docs.astral.sh/uv/getting-started/installation/). It provisions the
pinned Python itself, so nothing else is required.

## Setup

```bash
uv sync --all-groups        # create .venv and install dependencies
uv run pre-commit install   # install commit and push hooks
cp .env.example .env        # then fill in the values
```

## Commands

```bash
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy                   # type-check
uv run pytest                 # tests
uv run pre-commit run --all-files
uv run alembic upgrade head                                    # apply migrations (dev only from a branch, see ADR-0004)
uv run python -m apps.worker.ingest hackernews --hours 48      # fetch and store
uv run python -m apps.worker.assess --limit 25               # summarize and score unassessed signals (needs LLM_PROVIDER + key)
uv run python -m apps.worker.tick --hours 24 --assess-limit 25  # ingest every source, then assess
uv run uvicorn --factory apps.api.main:create_app --port 8000  # API
cd apps/web && cp .env.example .env.local && npm run dev       # UI on :3000
TEST_DATABASE_URL=<migrated db url> uv run pytest -m integration   # integration tests
```

Scheduling: `tick` ingests all sources then assesses (assess needs `LLM_PROVIDER`, `LLM_BASE_URL` and `LLM_MODEL_RELEVANCE` in `.env`; it is skipped when the provider is `fake`). Cron, every 30 minutes:

```
*/30 * * * * cd /Users/suraj/personal/signalforge && uv run python -m apps.worker.tick >> /tmp/signalforge-tick.log 2>&1
```

## Trying it locally

Run the commands above in order: migrate, ingest, start the API, start the UI at
`localhost:3000`. `INGEST_ENDPOINT_ENABLED` stays `false` unless you want
`POST /ingest/hackernews` (send the `X-Ingest-Token` header).

## Database

Supabase Postgres is the only database (no local Docker). Use the session pooler
string in `DATABASE_URL`, pointed at the dev project. Migrations follow
[ADR-0004](docs/adr/0004-database-environments.md): run
`uv run alembic upgrade head` to test a branch's migration, and
`uv run alembic downgrade -1` before switching branches or merging.

## Status

Phase 1 (foundation) in progress. Nothing is wired end to end yet — see PRD §43
for the gated build order.

## Assessing signals (Phase 1.6)

`assess` sends each unassessed signal to an LLM and stores a relevance score, category, summary and why-it-matters. The provider is plug-in: set `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL` (for example `https://openrouter.ai/api/v1`), `LLM_API_KEY` (or `OPENROUTER_API_KEY`) and `LLM_MODEL_RELEVANCE`. With `LLM_PROVIDER=fake` no network call is made. Cost is recorded per call in `llm_calls`; a 25-signal run on `openai/gpt-4o-mini` cost about $0.002.
