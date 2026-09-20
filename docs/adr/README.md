# Architecture Decision Records

Short documents recording architecture-changing decisions and the alternatives rejected along the way.

[`signalforge_prd.md`](../signalforge_prd.md) is the baseline and stays the source of truth for the **current** architecture. ADRs record **changes** to that baseline. See [ADR-0001](0001-record-architecture-decisions.md) for the rationale and the bar for writing one.

## How to add one

1. Copy `0000-template.md` to `NNNN-kebab-case-title.md`, next free number.
2. Open it as `Proposed`. Fill in Context, Decision, Alternatives, Consequences. Keep it to a page.
3. Update the PRD in the same PR if the decision changes it.
4. Add a row to the index below.
5. Flip to `Accepted` on merge. Never edit an accepted ADR's decision — supersede it with a new one and mark the old `Superseded by ADR-NNNN`.

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions in this folder | Accepted | 2026-09-20 |

## Expected

The PRD's open questions (§18) each need an ADR when decided. Listed here so they don't get settled silently in a commit message. Not files yet — create them when the decision is actually made.

| Open question | Blocks |
|---|---|
| Queue library: Procrastinate vs Arq, incl. behavior behind Supabase pooling | Phase 1 |
| Model IDs per role + monthly budget cap | Phase 1 (LLM gateway config) |
| Dashboard auth: Supabase Auth vs simple JWT | Phase 3 (dashboard) |
| Embedding model and host: local CPU vs API | Phase 2 (clustering) |
| Storage for large research documents: Postgres vs object storage | Phase 4 (evidence store) |
| Final V1 source list for AI engineering | Phase 2 |
| Publish windows and audience time zone | Phase 6 |
| Sandbox design for executed experiments | Roadmap |

Two open questions are not architecture and need no ADR: the parallel distribution channel, and AI-disclosure policy at scale plus the trademark and domain check for the name.
