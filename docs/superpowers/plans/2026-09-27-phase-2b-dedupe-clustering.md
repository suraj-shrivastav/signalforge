# Phase 2b: Embeddings, Clustering and Duplicate Rate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group signals about the same event into clusters, measure the duplicate rate, and show one card per cluster on the signals page.

**Architecture:** A provider-neutral `Embedder` plug-in (same shape as the LLM providers: Protocol, registry, `fake` and `openai_compatible` built-ins) turns each signal's title and summary into a 1536-dimension vector stored in `signal_embeddings`. An `embed` stage fills missing vectors. A `cluster` stage assigns each unclustered signal to the nearest recent cluster by cosine similarity (pgvector) or opens a new one, and keeps a running-mean centroid. `GET /signals` gains `cluster_size` and `collapse`, and `tick` runs embed then cluster between ingest and assess. A report command prints the duplicate rate and exports a labeled-sample sheet for the exit check.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Alembic, pgvector (`pgvector.sqlalchemy.Vector`, already a dependency and enabled by migration 0001), httpx, Next.js.

**Spec:** `docs/signalforge_prd.md` FR-02 (line 142), stage table (line 823: "cluster: code + embeddings, cosine threshold plus entity overlap; no LLM"), data model lines 748 and 764, and build-order row "2 Discovery" (line 887). Exit criterion for 2b: duplicate rate measured; clustering spot-checked on a labeled sample of about 50 clusters.

## Global Constraints

- Python 3.13, ruff, mypy strict, pre-commit must pass. Conventional Commits, no AI or Co-Authored-By trailers.
- PRs at most 400 changed lines, squash-merged.
- No new runtime dependency (pgvector, httpx, sqlalchemy are already present). No numpy.
- Migrations are applied to the dev DB only from main (ADR-0004).
- No hard vendor dependency: the embedding provider is chosen by config, and the vendor name appears only in `.env.example` comments.
- Failures raise `SignalForgeError` subtypes and never return partial results silently. Fetched text is untrusted data; it only goes into the embedding request body.
- Never print `.env` values.

## Rulings made while planning

- **Embeddings live in their own table** (`signal_embeddings`), not a `signals.embedding` column as PRD line 776 says. Signals are immutable artifacts, and a separate table lets a model change re-embed without touching them. Costs one join.
- **Cosine similarity only in v1; no entity-overlap gate.** PRD FR-02 says similarity "with entity overlap", but `signals.entities` is empty for most sources because no stage extracts entities yet. Costs some false merges. Tune the threshold on the labeled sample (Task 6).
- **Dimension fixed at 1536** (matches `text-embedding-3-small`, available through OpenAI-compatible hosts). A model with another dimension needs a new migration. The model name is stored per row, so mixed models are detectable.
- **Embedding calls are not recorded in `llm_calls`** in this phase. Cost is a fraction of a cent per thousand signals. Deferred: add when embeddings get a budget line.
- **Cluster all signals, not only relevant ones**, as PRD line 109 orders it (cluster before relevance filter).

---

## File Structure

- Create `src/signalforge/embeddings/__init__.py`, `providers.py`, `registry.py`: the `Embedder` plug-in layer.
- Modify `src/signalforge/core/config.py`: `embedding_provider`, `embedding_model`.
- Create `src/signalforge/db/models/clusters.py`: `SignalEmbeddingRow`, `ClusterRow`, `ClusterSignalRow`.
- Create `src/signalforge/db/migrations/versions/0005_add_embeddings_and_clusters.py`.
- Create `src/signalforge/db/repositories/clusters.py`: `ClusterRepository`.
- Create `src/signalforge/stages/embed.py` and `src/signalforge/stages/cluster.py`.
- Create `apps/worker/embed.py`, `apps/worker/cluster.py`, `apps/worker/cluster_report.py`.
- Modify `apps/worker/tick.py`, `apps/api/schemas.py`, `apps/api/routes/signals.py`, `src/signalforge/db/repositories/signals.py`, `apps/web/src/lib/api.ts`, `apps/web/src/app/page.tsx`.
- Create `docs/adr/0007-cluster-with-embeddings-in-a-separate-table.md`.
- Tests under `tests/unit/` and `tests/integration/`, one file per unit below.

---

### Task 1: Embedder plug-in layer

**Files:**
- Create: `src/signalforge/embeddings/__init__.py`, `providers.py`, `registry.py`
- Modify: `src/signalforge/core/config.py`, `.env.example`
- Test: `tests/unit/test_embeddings.py`

**Interfaces:**
- Produces:
  - `EMBEDDING_DIMENSIONS = 1536` (in `providers.py`).
  - `class Embedder(Protocol): name: str; def embed(self, texts: Sequence[str]) -> list[list[float]]` — returns one vector of exactly `EMBEDDING_DIMENSIONS` floats per input, in order. Raises `SignalForgeError` subtypes; never returns fewer vectors than inputs.
  - `class FakeEmbedder` (`name="fake"`): deterministic, offline. Vector for a text is built from a SHA-256 of each lowercase word bucketed into 1536 slots, then L2-normalised, so texts sharing words have positive cosine similarity and identical texts have similarity 1.0. Empty text returns a fixed unit vector.
  - `class OpenAICompatibleEmbedder(client: httpx.Client, *, base_url: str, api_key: str | None, model: str, sleep=time.sleep)`: `POST {base_url}/embeddings` with `{"model": model, "input": [...]}`, reads `data[i].embedding` ordered by `index`. Validates count and dimension, else raises `ArtifactValidationError`. Uses the same HTTP error mapping and retry as `fetch_bytes` (reuse it via a small local copy only if `fetch_bytes` cannot POST; prefer extending `_http.py` with `post_json_bytes` that shares the status mapping).
  - `PROVIDERS: dict[str, Callable[..., Embedder]]`, `register_embedder(name, factory)`, `build_embedder(settings, client) -> Embedder` in `registry.py`.
  - Settings: `embedding_provider: str = "fake"`, `embedding_model: str = "openai/text-embedding-3-small"`. Reuse `llm_base_url` and `llm_api_key`; the existing settings validator that requires a key for a non-local `openai_compatible` LLM also applies to a non-fake `embedding_provider`.

- [ ] **Step 1: Write failing tests** covering: fake determinism and dimension; identical texts have cosine 1.0; unrelated texts have cosine below 0.5; empty text works; the openai_compatible embedder (using `httpx.MockTransport`) returns vectors ordered by `index` even when the server returns them shuffled; wrong count raises `ArtifactValidationError`; wrong dimension raises `ArtifactValidationError`; 503 raises `ProviderUnavailableError` after 3 calls; 401 raises `ProviderRejectedError`; unknown provider name raises `ConfigurationError`; a custom embedder registered with `register_embedder` is built by name (proves plug-in without editing core).
- [ ] **Step 2: Run to verify failure:** `uv run pytest tests/unit/test_embeddings.py -v` → FAIL (module not found).
- [ ] **Step 3: Implement** the three files and the settings. Add a `cosine(a, b)` helper in `providers.py` for tests and the cluster stage's in-memory checks.
- [ ] **Step 4: Run tests, lint, types:** `uv run pytest tests/unit -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`. Expected: PASS.
- [ ] **Step 5: Commit:** `git commit -m "feat: add pluggable embedder layer"`

---

### Task 2: Tables, models and repository

**Files:**
- Create: `src/signalforge/db/models/clusters.py`, `src/signalforge/db/migrations/versions/0005_add_embeddings_and_clusters.py`, `src/signalforge/db/repositories/clusters.py`
- Modify: `src/signalforge/db/models/__init__.py`
- Test: `tests/integration/test_clusters_repository.py`

**Interfaces:**
- Consumes: `EMBEDDING_DIMENSIONS` from Task 1.
- Produces (tables):
  - `signal_embeddings(id, signal_id UNIQUE FK signals ON DELETE CASCADE, embedding vector(1536) NOT NULL, model varchar(128) NOT NULL, created_at, updated_at, schema_version)`.
  - `clusters(id, centroid vector(1536) NOT NULL, first_seen timestamptz, last_seen timestamptz, primary_signal_id FK signals NULL, signal_count int, created_at, updated_at, schema_version)`. HNSW index on `centroid` with `vector_cosine_ops`; btree on `last_seen`.
  - `cluster_signals(id, cluster_id FK clusters ON DELETE CASCADE, signal_id UNIQUE FK signals ON DELETE CASCADE, similarity float, created_at, updated_at, schema_version)`. A signal is in at most one cluster.
- Produces (repository), all taking a `Session`:
  - `ClusterRepository.add_embeddings(rows: list[tuple[uuid.UUID, list[float], str]]) -> int` — insert `(signal_id, embedding, model)`, ignore existing `signal_id` (ON CONFLICT DO NOTHING), return count inserted.
  - `list_unembedded(limit: int) -> list[Signal]` — signals without an embedding row, oldest first.
  - `list_unclustered(limit: int) -> list[tuple[Signal, list[float]]]` — embedded signals with no `cluster_signals` row, ordered by `published_at`, `id`.
  - `nearest_cluster(embedding, *, since: datetime) -> tuple[ClusterRow, float] | None` — the cluster with `last_seen >= since` and the smallest cosine distance; returns similarity `1 - distance`.
  - `create_cluster(signal: Signal, embedding, similarity: float = 1.0) -> ClusterRow` and `join_cluster(cluster: ClusterRow, signal: Signal, embedding, similarity: float) -> None` — join updates `centroid` as the running mean `(old * n + new) / (n + 1)`, `signal_count`, `last_seen = max(last_seen, published_at)`, `first_seen = min(...)`, and `primary_signal_id` = the member with the earliest `published_at`.

- [ ] **Step 1: Write failing integration tests** (they skip without `TEST_DATABASE_URL`, like the existing integration tests; follow `tests/integration/test_ingest.py` for the fixture): insert two signals, add embeddings, assert `list_unembedded` shrinks; create a cluster, `nearest_cluster` finds it for a near vector and returns `None` for an orthogonal vector and for a `since` after `last_seen`; `join_cluster` moves the centroid to the mean and sets `primary_signal_id` to the earliest signal; a signal cannot join two clusters (unique violation).
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** models, migration (`down_revision = "0004"`; create the HNSW index with `op.execute("CREATE INDEX ... USING hnsw (centroid vector_cosine_ops)")`; the downgrade drops the tables), and repository. Use `pgvector.sqlalchemy.Vector(1536)` and `Vector.cosine_distance`.
- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check . && uv run mypy src`, and `uv run alembic upgrade head` then `downgrade -1` then `upgrade head` against the test database if `TEST_DATABASE_URL` is set. Do not migrate the dev DB from this branch (ADR-0004).
- [ ] **Step 5: Commit:** `git commit -m "feat: add embeddings and clusters tables and repository"`

---

### Task 3: `embed` stage and CLI

**Files:**
- Create: `src/signalforge/stages/embed.py`, `apps/worker/embed.py`
- Test: `tests/unit/test_embed_stage.py`, `tests/unit/test_embed_cli.py`

**Interfaces:**
- Consumes: `Embedder`, `ClusterRepository.list_unembedded`, `add_embeddings`; `StageRun` model and the stage-run pattern in `stages/assess.py`.
- Produces:
  - `EmbedResult(considered: int, embedded: int, failed_batches: int)`.
  - `run_embed(session: Session, embedder: Embedder, *, limit: int, batch_size: int = 64) -> EmbedResult`. Text for a signal is `f"{title}\n\n{summary}"[:2000]`. Embeds in batches; a batch that raises `SignalForgeError` is logged with the stage-run id, counted in `failed_batches`, and skipped, and the run continues; other exceptions propagate after the stage run is marked failed. Records one `stage_runs` row (stage `"embed"`) like assess does.
  - CLI: `uv run python -m apps.worker.embed --limit N` (1 to 2000, validators from `apps/worker/_args.py`), printing `considered=… embedded=… failed_batches=…`.

- [ ] **Step 1: Write failing tests** with `FakeEmbedder` and a fake repository or an in-memory SQLite-free stub, following `tests/unit/test_assess_stage.py`: all signals embedded once; a second run embeds nothing; a failing batch is counted and later batches still run; text is truncated to 2000 characters; a `SignalForgeError` from the embedder never marks the whole stage failed; a non-`SignalForgeError` marks the stage run `failed` and re-raises.
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: add embed stage and CLI`.

---

### Task 4: `cluster` stage and CLI

**Files:**
- Create: `src/signalforge/stages/cluster.py`, `apps/worker/cluster.py`
- Test: `tests/unit/test_cluster_stage.py`

**Interfaces:**
- Consumes: `ClusterRepository.list_unclustered`, `nearest_cluster`, `create_cluster`, `join_cluster`.
- Produces:
  - `DEFAULT_THRESHOLD = 0.80`, `DEFAULT_WINDOW_DAYS = 14` (named constants with a `ponytail:` comment: threshold is tuned on the labeled sample in Task 6).
  - `ClusterResult(considered: int, joined: int, created: int)`.
  - `run_cluster(session, *, limit: int, threshold: float = DEFAULT_THRESHOLD, window_days: int = DEFAULT_WINDOW_DAYS, now: datetime | None = None) -> ClusterResult`. For each unclustered embedded signal, oldest first: find `nearest_cluster(embedding, since=signal.published_at - window)`; if similarity `>= threshold`, join; else create. Processing oldest-first and committing per batch of 100 means a crash leaves already-assigned signals assigned and the rest for the next run. Records a `stage_runs` row (stage `"cluster"`).
  - CLI: `uv run python -m apps.worker.cluster --limit N [--threshold X]` (limit 1 to 5000, threshold 0.5 to 0.99), printing `considered=… joined=… created=…`.

- [ ] **Step 1: Write failing tests** (integration, needs `TEST_DATABASE_URL`) using hand-made vectors so results do not depend on an embedding model: two near-identical vectors join one cluster; an orthogonal vector opens a second cluster; a signal older than the window relative to the cluster's `last_seen` does not join; re-running clusters nothing new (idempotent); threshold 0.99 splits two merely similar vectors that threshold 0.80 merges; centroid after three joins equals the mean of the three vectors (assert with a tolerance).
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: add cluster stage and CLI`.

---

### Task 5: API and page show clusters

**Files:**
- Modify: `apps/api/schemas.py`, `apps/api/routes/signals.py`, `src/signalforge/db/repositories/signals.py`, `apps/web/src/lib/api.ts`, `apps/web/src/app/page.tsx`
- Test: `tests/unit/test_api_signals.py` (extend), a web component test if the repo already has web tests; otherwise a `npm run build` check.

**Interfaces:**
- Produces: `SignalOut.cluster_id: uuid.UUID | None` and `SignalOut.cluster_size: int` (1 when unclustered). `GET /signals?collapse=true` returns only each cluster's primary signal (plus every unclustered signal), keeping the existing keyset cursor and the `relevant_only` filter (applied to the primary signal's latest assessment). Default `collapse=false` keeps today's behavior.
- The page requests `collapse=true` by default and shows a `+N more sources` line when `cluster_size > 1`. "Show all" (`?all=1`) also turns collapse off.

- [ ] **Step 1: Write failing tests:** unclustered signals have `cluster_size == 1` and `cluster_id is None`; with two signals in one cluster, `collapse=true` returns one item with `cluster_size == 2` and `collapse=false` returns both; pagination across a collapsed page neither repeats nor skips items (three clusters, `limit=2`).
- [ ] **Step 2 to 5:** run to fail, implement, `uv run pytest -q`, lint, types, `cd apps/web && npm run build`, commit `feat: collapse clustered signals on the page`.

---

### Task 6: `tick` integration, report, ADR and docs

**Files:**
- Modify: `apps/worker/tick.py`, `README.md`, `.kiro/steering/tech.md`, `.env.example`
- Create: `apps/worker/cluster_report.py`, `docs/adr/0007-cluster-with-embeddings-in-a-separate-table.md`
- Test: `tests/unit/test_tick_cli.py` (extend), `tests/unit/test_cluster_report.py`

**Interfaces:**
- Consumes: `run_embed`, `run_cluster`, `build_embedder`.
- Produces:
  - `tick` order: ingest all sources, then embed, then cluster, then assess. An embed or cluster failure is logged, counted and does not stop assess. Exit codes: 0 ok, 1 every source failed, 2 any of embed, cluster or assess failed while ingest succeeded. Embed and cluster run only when `embedding_provider != "fake"`, and the summary line says so when skipped (same rule as assess).
  - `uv run python -m apps.worker.cluster_report [--sample 50] [--out clusters.csv]` prints `signals=N clusters=M duplicate_rate=X` where `duplicate_rate = 1 - clusters / signals` over clustered signals, and writes a CSV of up to `--sample` random multi-signal clusters with columns `cluster_id, signal_count, member_titles (joined by " | "), member_sources, min_similarity, label` (the `label` column left blank for the editor to fill with `same` or `different`). It reads only.
  - ADR-0007 records the separate-table and cosine-only rulings from the top of this plan.
- Docs: README and `tech.md` gain the `embed`, `cluster` and `cluster_report` commands and the three new `.env` values (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, and the reused `LLM_BASE_URL` and key).

- [ ] **Step 1: Write failing tests:** tick calls embed and cluster after ingest and before assess; embed failure yields exit 2 and assess still runs; fake embedding provider skips embed and cluster with a message; report computes the duplicate rate from a seeded fixture (3 signals in 1 cluster plus 1 alone gives `1 - 2/4 = 0.5`); the CSV has the expected columns and at most `--sample` rows.
- [ ] **Step 2 to 5:** run to fail, implement, run tests/lint/types, commit `feat: run embed and cluster in tick and add cluster report`.

---

## Acceptance (after merge, on the dev DB)

- [ ] Apply migration 0005 to the dev DB from main only (ADR-0004): `uv run alembic upgrade head`.
- [ ] With `EMBEDDING_PROVIDER=openai_compatible` and the LLM base URL and key set, run `tick --hours 72`; expect embed and cluster lines and exit 0.
- [ ] `uv run python -m apps.worker.cluster_report --sample 50 --out clusters.csv`, then label the sheet. Record the duplicate rate and the same/different agreement in the Phase 2 exit note. If agreement is below 85%, adjust `DEFAULT_THRESHOLD` and re-run cluster from scratch (a `--rebuild` flag is out of scope; truncate `cluster_signals` and `clusters` by hand).
- [ ] Open the page: clustered stories show `+N more sources`, and "Show all" lists every signal.

## Self-Review

- **Spec coverage:** FR-02 dedupe by canonical URL (exists since 1.5) and content hash (column exists, not used for merging; near-duplicates are handled by embeddings); embedding similarity (Tasks 1 to 4); entity overlap deferred by ruling; duplicate rate measured and spot-check sample (Task 6); page shows one card per event (Task 5). Stage table row "cluster: no LLM" holds: nothing in Tasks 3 and 4 calls the LLM gateway.
- **Placeholders:** Tasks 3 to 6 describe steps 2 to 5 in one line because they repeat the Task 1 pattern (run to fail, implement, run tests, commit); the executor must still write the tests listed in each task's Step 1. The centroid formula, thresholds and CSV columns are given exactly.
- **Type consistency:** `EMBEDDING_DIMENSIONS`, `Embedder.embed`, `ClusterRepository` method names and `run_embed`/`run_cluster` signatures match between tasks.
- **Known ceilings:** greedy single-pass clustering depends on processing order and can chain-merge related stories through a drifting centroid; the 14-day window and threshold bound this. The HNSW index is approximate, so a near-threshold match can be missed. Revisit both if the labeled sample shows more than 15% wrong merges.
- **Also open:** an `Accept`/rate concern for the embeddings host is not expected, since it is a paid API called in batches of 64.
