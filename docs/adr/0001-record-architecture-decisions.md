# ADR-0001: Record architecture decisions in this folder

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Owner
**PRD impact:** none (documents existing §6 practice)

## Context

`docs/signalforge_prd.md` v1.2 is the V1 development baseline. It already carries a decision log (§19) and a final architecture decision table (§44) covering every choice made up to the baseline: modular monolith, Postgres-backed queue, plain-Python orchestration, OpenAI-compatible gateway, stage-scoped idempotency, and the rest.

Development standards require a short ADR for architecture-changing decisions, but named no location and no format. Two failure modes follow from that: decisions get made in chat or commit messages and are lost, or they get duplicated into a second architecture document that drifts from the PRD.

## Decision

ADRs live in `docs/adr/`, numbered sequentially as `NNNN-kebab-case-title.md`, using `0000-template.md`.

The PRD stays the baseline and remains the single source of truth for the current architecture. **ADRs record changes to that baseline, not the baseline itself.** We do not backfill ADRs for decisions already in PRD §19 and §44. When an ADR is accepted, the PRD is updated in the same PR and the ADR is linked from the index below.

An ADR is required when a decision changes a module boundary, adds or removes an external dependency or service, changes a data contract or artifact schema in a breaking way, alters a state machine or idempotency key, or reverses anything in PRD §44. Everything else is a normal PR.

## Alternatives considered

| Option | Why not |
|---|---|
| Decision log inside the PRD only | Loses context and alternatives; a table row cannot explain why an option was rejected |
| Backfill an ADR per row of §44 | ~25 documents restating a table, creating a second source of truth that drifts |
| ADRs as GitHub issues | Not versioned with the code; invisible when reading the repo offline |

## Consequences

Architecture history becomes reviewable in the same PR flow as code, and rejected alternatives are preserved so we stop relitigating them.

The cost is that the PRD and the ADR set must be read together: the PRD tells you the current state, the ADRs tell you how it got there. The follow-up checklist in the template exists to keep the PRD authoritative, and a stale PRD is the main way this goes wrong.

Reversing this is cheap — stop writing new ADRs and fold any accepted ones into the PRD.

## Follow-ups

- [x] Add `docs/adr/` with template and index
- [x] Point `.kiro/steering/dev_standards.md` §6 at this folder
