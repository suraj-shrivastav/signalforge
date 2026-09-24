# ADR-0005: Build a vertical slice (fetch, store, API, UI) before the pipeline infrastructure

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** suraj
**PRD impact:** adds Phase 1.5 to §43; the UI and ingest arrive earlier than Phase 3 and Phase 2 respectively

## Context

PRD §43 builds infrastructure first: Phase 1 finishes the stage runner, state
machine, queue and LLM gateway, and the first UI appears in Phase 3 after
discovery in Phase 2. Phase 1 is about half done and nothing yet fetches or
shows data.

Those components have not met a real stage. A state machine, queue and stage
runner designed without one are speculative, and the shape of real signals (what
sources return, how often they duplicate, what an editor wants to see) will
change them. Every later phase also depends on the source, storage and API
boundaries, so those are worth proving first.

## Decision

Insert **Phase 1.5, a vertical slice**, before the rest of Phase 1:

1. A `RawSignal` artifact, a `signals` table and a repository.
2. One source plugin (Hacker News) behind the `Source` Protocol.
3. An `ingest` function that fetches, stores and records a `stage_runs` row.
   It is callable from a CLI and from a temporary HTTP trigger.
4. A FastAPI service with `GET /signals` and one consistent error shape.
5. A minimal Next.js page that lists signals through the API only.

Deferred until a real stage needs them: the job queue, the generic stage runner
and state machine, the LLM gateway, auth, clustering and embeddings.

The slice keeps the boundary rules: Pydantic validation at every boundary,
sources behind a Protocol, timeouts and bounded retries on external calls, an
idempotent unique key on `canonical_url`, fetched content treated as untrusted,
and no database access from the frontend.

The ingest logic lives in a plain function, not in a request handler. The HTTP
trigger is a thin wrapper behind a config flag that defaults off and requires a
token, so it cannot become an open outbound-fetch endpoint. When the queue
lands, the function becomes a job with no rewrite.

## Alternatives considered

| Option | Why not |
|---|---|
| Follow PRD order (finish Phase 1, then Phase 2, then Phase 3 UI) | Real feedback arrives months later, after the infrastructure shapes have been guessed. |
| Fetch inline in an HTTP request handler | Slow, can time out, and exposes outbound fetching to any caller. The function-plus-thin-trigger form has none of these problems. |
| Skip the API and let Next.js read Postgres | Forbidden by `tech.md`; it would also have to be undone before any deploy. |

## Consequences

Real data is visible early, so the next steps (second source, dedupe, topic
cards, or reworking the artifact shape) are chosen from evidence. The cost is
that the stage runner and state machine are built after ingest exists, so ingest
is refactored onto them later; its logic stays in one function to keep that
cheap. The `ingest` stage's `stage_runs` key includes a start time, so each run
is recorded and the idempotency cache does not apply to it until the stage
runner arrives.

This does not cross the Phase 3 gate (about two weeks of nightly runs before
judging topic-card usefulness). The slice makes no topic cards.

Reversing it means deleting the slice code and returning to PRD order; nothing
in the queue or gateway work depends on it.

## Follow-ups

- [x] Add Phase 1.5 to `docs/signalforge_prd.md` §43
- [ ] Remove the `INGEST_ENDPOINT_ENABLED` flag when ingest runs through the queue (owner: suraj)
- [ ] Add auth before the API or the page is reachable beyond localhost
