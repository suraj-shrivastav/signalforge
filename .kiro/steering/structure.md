# SignalForge Repository Structure

Target layout (PRD §23). Most of this is **not scaffolded yet** — the repo currently holds the PRD and steering files. Create new code at these paths rather than inventing new ones.

```text
signalforge/
├── apps/
│   ├── api/                 # FastAPI entrypoint, routers, auth, DTOs
│   ├── worker/              # worker + scheduler entrypoint
│   └── web/                 # Next.js public site + dashboard
├── src/signalforge/
│   ├── core/                # protocols, no provider imports
│   │   ├── artifacts/       # Pydantic typed + versioned artifacts
│   │   ├── stage.py         # Stage interface + runner
│   │   ├── pipeline.py      # orchestration + state transitions
│   │   ├── registry.py      # plugin registry
│   │   ├── config.py        # settings + vertical configuration
│   │   ├── budget.py        # cost/token/search budgets
│   │   ├── provenance.py    # production lineage
│   │   └── errors.py        # typed hierarchy: retryable vs permanent
│   ├── plugins/
│   │   ├── sources/         # github, hn, rss, arxiv, hf
│   │   ├── search/          # direct_fetch, tavily, firecrawl, searxng
│   │   ├── llm/             # gateway, routing, fallbacks, capability flags
│   │   ├── rankers/         # rules, embeddings, learned later
│   │   └── publishers/      # owned-site publisher
│   ├── stages/              # ingest, cluster, filter, topic_intel, research,
│   │                        # write, verify, seo, publish, analytics
│   ├── db/                  # models, repositories, migrations
│   └── verticals/
│       └── ai_engineering.yaml
├── tests/                   # unit, contract, golden, e2e
├── infra/                   # Dockerfiles, railway config
└── docs/
    ├── signalforge_prd.md   # V1 baseline, source of truth for current architecture
    └── adr/                 # architecture decision records, NNNN-title.md
```

## Layering

```text
apps/  →  stages/  →  core/ (protocols)  ←  plugins/ (implementations)
```

- `core/` defines protocols and owns no provider knowledge. It imports nothing from `plugins/` or `stages/`.
- `stages/` depends on protocols only. A stage never imports a concrete provider, never calls an LLM provider directly, and never reaches outside the search abstraction.
- `plugins/` implement protocols. A provider SDK is imported **only** inside its own plugin directory.
- Modules never import another module's internals. Cross-module access goes through the public interface.
- Provider selection is config-driven. Adding a source or provider = one implementation + one config entry, never a pipeline change.

## Stage contract

Every stage reads and writes a **typed, versioned artifact**. Artifacts carry `id`, `schema_version`, `created_at`, `produced_by` (stage run id), `parent_ids`.

Pipeline order: `ingest → cluster → filter → topic_intel → [editor review 1] → research → write → verify → seo → [editor review 2] → publish → analytics`.

## State

**Business state and job state are separate.** Only the pipeline engine transitions business state; a failed job must never implicitly push business state somewhere invalid.

- Business: `proposed, accepted, researching, researched, drafting, drafted, verifying, verified, structuring, structured, approved, scheduled, published, live_verified, monitoring` + side states `rejected, snoozed, need_more, failed`
- Job: `queued, leased, running, succeeded, retrying, failed, dead_lettered`

Every transition writes a `stage_run`. Failures land in `failed` with a dashboard-visible reason.

## Idempotency

- Stage key: `(stage, entity_id, input_hash, stage_config_hash)`, unique in `stage_runs`.
- `stage_config_hash` covers **only** what that stage depends on (its prompt version, its role's model routing, relevant weights, artifact schema version). Never a global config version — an unrelated tweak must not rerun everything.
- Publish key: `article_id + article_version`.
- Rerunning with an identical key returns the cached result, since LLM output is not deterministic.

## Database conventions

UUID primary keys, `created_at`/`updated_at`, soft delete only where needed. JSONB for artifact payloads; promote a field to a real column once it's queried or filtered. Every artifact row stores `schema_version`. pgvector indexes on `signals.embedding` and `clusters.centroid`. `claims.status` is a constrained enum matching the claim status list in `product.md`. Migrations via Alembic only.

Table groups: discovery (`sources, signals, clusters, cluster_signals`), editorial (`topic_cards, editor_decisions, editor_reviews`), research (`source_documents, research_packages, claims, evidence`), content (`articles, article_versions, verification_results, structured_drafts, publish_records`), ops (`jobs, stage_runs, llm_calls, model_scorecard, config_snapshots`), metrics (`referral_events, crawler_hits, citation_probes, page_metrics`).

## Build order

Phases are gated (PRD §43). Phase 3 (topic intelligence) requires ~2 weeks of nightly runs proving the cards are useful **before** later phases are built. Don't skip ahead to research or content work while an earlier phase is unproven.
