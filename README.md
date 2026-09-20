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
```

## Status

Phase 1 (foundation) in progress. Nothing is wired end to end yet — see PRD §43
for the gated build order.
