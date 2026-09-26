# ADR-0007: Topic cards per signal with a rules-based ranker

**Status:** Proposed
**Date:** 2026-09-27
**Deciders:** suraj
**PRD impact:** FR-03 to FR-05, Phase 3 (Topic Intelligence); clustering deferred

## Context

Phase 3 needs ranked topic cards and recorded editor decisions for a two-week
usefulness test. Clustering is not built, the design system is not supplied, and
the API has no dashboard auth or CORS.

## Decision

We write one card per signal (not per cluster; a nullable `cluster_id` comes with clustering) and only for signals whose latest assessment is relevant; a rules-based ranker scores cards as a weighted sum of relevance, novelty, signal strength and confidence (weights in one constant), and the queue reserves WILDCARD_SLOTS=2 positions for high-novelty cards below the cutoff; editor writes use a shared secret in `X-Editor-Key` until dashboard auth is decided, reads stay open, and decisions are append-only with the latest winning; `format` and `evergreen_score` are generated but unused by ranking; browser writes go through a same-origin Next.js Route Handler that forwards to the API (which gets no CORS), validates the UUID, caps the body at 16 KB, uses timeouts, never logs or echoes the key and maps upstream failure to a 502 error body; in the API the decision commit happens before the response is sent (a failed commit is a 500, never a false 201) and auth runs before body parsing so unauthenticated callers never see validation errors; the triage UI stays an unstyled placeholder until design references arrive.

## Alternatives considered

| Option | Why not |
|---|---|
| Card per cluster | Clustering not built |
| Enable CORS on the API | Widens the write surface; proxy keeps one origin |
| Learned ranker | No decision data yet |

## Consequences

Repeated stories yield duplicate cards until clustering lands. The shared secret
is weak protection. Weights are guesses until data exists. The relevance gate misses cards if the assessment is conservative. There is no Origin check on the proxy (residual CSRF assumption): this is safe only because the key is never stored in a cookie or any other ambient browser credential. Exit cost: replace the
proxy with real auth and drop the header check.

## Differences from the PRD

FR-05 mentions a `need_more` decision and a different tag set (too obvious, shallow, saturated, off-vertical, other); the code has 3 decisions and 9 tags with no "other". Snoozed cards stay in the main ranked list (no separate backlog) and drop out of the queue after the 7-day window. `topic_cards.wildcard` exists but is never written (wildcard is computed per request). `ix_topic_cards_score` is unused because sorting happens in Python. The per-run cost bound is the TOPIC budget scope ($0.50) per stage per run, not per day.

## Follow-ups

- [ ] Real dashboard auth (PRD open question 3)
- [ ] Add `cluster_id` with clustering
- [ ] Apply the design system and global.css to `/triage`
