# ADR-0007: Topic cards per signal with a rules-based ranker

**Status:** Accepted
**Date:** 2026-09-27
**Deciders:** suraj
**PRD impact:** FR-03 to FR-05, Phase 3 (Topic Intelligence); clustering deferred

## Context

Phase 3 needs ranked topic cards and recorded editor decisions for a two-week
usefulness test. Clustering is not built, the design system is not supplied, and
the API has no dashboard auth or CORS.

## Decision

- One card per signal, not per cluster; `cluster_id` is added later.
- Cards only for signals whose latest assessment is relevant.
- Rules-based ranker (weighted sum, weights in one constant); two wildcard
  slots for high-novelty cards below the cutoff.
- Writes use a shared secret in `X-Editor-Key` until dashboard auth is decided;
  reads stay open.
- Decisions are append-only; the latest decision wins.
- `format` and `evergreen_score` are generated but unused by ranking for now.
- Browser writes go through a same-origin Next.js Route Handler that forwards to
  the API; the API gets no CORS. The handler validates the UUID, uses a timeout,
  never logs or echoes the key, and maps upstream failure to a 502 error body.
- In the API, the decision commit happens before the response is sent (a failed
  commit is a 500, never a false 201), and auth runs before body parsing so
  unauthenticated callers never see validation errors.
- The triage UI is an unstyled placeholder until design references arrive.

## Alternatives considered

| Option | Why not |
|---|---|
| Card per cluster | Clustering not built |
| Enable CORS on the API | Widens the write surface; proxy keeps one origin |
| Learned ranker | No decision data yet |

## Consequences

Repeated stories yield duplicate cards until clustering lands. The shared secret
is weak protection. Weights are guesses until data exists. Exit cost: replace the
proxy with real auth and drop the header check.

## Follow-ups

- [ ] Real dashboard auth (PRD open question 3)
- [ ] Add `cluster_id` with clustering
- [ ] Apply the design system and global.css to `/triage`
