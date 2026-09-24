# ADR-0004: Separate dev and prod Supabase projects; migrations reach shared databases only from main

**Status:** Accepted
**Date:** 2026-09-24
**Deciders:** suraj
**PRD impact:** refines §39 (PostgreSQL) and §42 (deployment)

## Context

Supabase is the only database; there is no local Postgres. One hosted project
served every branch. Migration `0002` was applied to it from the unmerged branch
`feat/ops-tables`, so the database was stamped `0002` while `main` only had
`0001`, and `alembic current` failed on every other branch.

The cause is structural: a shared database takes the schema of whichever branch
ran `alembic upgrade` last, and nothing ties it back to `main`.

## Decision

- The existing project is `signalforge-dev`. A separate `signalforge-prod`
  project is created at first deploy (PRD §42), not before. Production
  credentials never sit in a developer `.env`.
- On dev, a branch may apply its own migration to test it, and must
  `alembic downgrade` it before switching branches or merging.
- Prod is changed only by `alembic upgrade head` run from `main`, as the release
  step of the deploy.
- If dev drifts, reset it (drop the objects in `public`, then
  `alembic upgrade head` from `main`). Dev holds no data worth keeping. Never
  `alembic stamp` to hide a mismatch.
- When two open branches add a migration, the second rebases and renumbers
  before merge, so the chain stays linear.

## Alternatives considered

| Option | Why not |
|---|---|
| Local Docker Postgres | Not available on this machine, and would differ from the Supabase pooler behaviour that ADR-0003 depends on. |
| Supabase Branching | Paid feature; one developer, so the cost is not justified yet. |
| One shared project, discipline only | This is what failed. |

## Consequences

A drifted dev database is cheap to rebuild. Prod cannot drift from `main`
because only the release step touches it. The cost is one extra Supabase project
at deploy time, and a downgrade step that depends on every migration having a
working `downgrade` (checked in CI).

Reversing this means pointing all environments at one project again, which
reintroduces the failure above.

## Follow-ups

- [x] Update `README.md` and `.kiro/steering/dev_standards.md`
- [ ] CI checks upgrade, downgrade and a single head (`chore/ci-migration-check`)
- [ ] Create `signalforge-prod` at first deploy
