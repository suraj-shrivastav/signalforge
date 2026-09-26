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
