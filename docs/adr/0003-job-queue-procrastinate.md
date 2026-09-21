# ADR-0003: Procrastinate for the job queue, on a session-mode Postgres connection

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** suraj
**PRD impact:** closes open question §18.4; refines §27 and §42

## Context

PRD §18.4 left the queue library open (Procrastinate vs Arq) and flagged
"behavior behind Supabase pooling" as part of the question. `tech.md` forbids
Redis, Celery and Kafka: the queue must be PostgreSQL.

That constraint already settles the comparison. Arq is a Redis-backed library,
so choosing it would mean adding the one dependency the stack explicitly
excludes. Procrastinate is Postgres-backed and uses `FOR UPDATE SKIP LOCKED`,
which PostgreSQL documents as suitable for queue tables with multiple consumers
(PRD §27).

The real decision is the connection, not the library. Procrastinate uses
`LISTEN/NOTIFY` so workers pick up jobs without polling latency, and that is a
session-scoped feature. Supabase documents that transaction mode "does not
support session-level features (SET, LISTEN/NOTIFY, temporary tables that span
transactions, or advisory locks)", and that Supavisor does not support prepared
statements in transaction mode. pgbouncer behaves the same way: `LISTEN` is
unsupported under transaction pooling even though `NOTIFY` works.

Measured on this project, the direct connection is also not reachable:

```
db.<ref>.supabase.co   A    -> (none)
db.<ref>.supabase.co   AAAA -> 2406:da1a:...
connect([2406:da1a:...]:5432) -> [Errno 65] No route to host
```

Supabase direct connections are IPv6-only without the IPv4 add-on, and this
network has no IPv6 route to that host.

## Decision

We use **Procrastinate**, and we run it over the **Supavisor pooler in session
mode** (port 5432 on `*.pooler.supabase.com`), which has IPv4 and preserves
`LISTEN/NOTIFY` and prepared statements. Configuration exposes two connection
strings:

- `DATABASE_URL` — session mode. Used by the worker and by Alembic migrations.
- `DATABASE_POOLER_URL` — optional, transaction mode (port 6543). Available for
  the API, which only runs short transactions. Prepared statements must be
  disabled on this connection (`prepare_threshold=None` for psycopg).

The application keeps plain PostgreSQL semantics, so moving to RDS stays a
connection-string change. The variable is named `DATABASE_URL`, not
`SUPABASE_DB_STRING`, to keep the vendor out of the application's vocabulary;
the Supabase name is accepted as an alias so existing `.env` files keep working.

## Alternatives considered

| Option | Why not |
|---|---|
| Arq | Redis-backed. `tech.md` excludes Redis, so it contradicts the stack |
| Celery | Explicitly excluded, and needs a broker |
| Hand-rolled `SKIP LOCKED` queue | We would rewrite retries, locking, scheduling and admin tooling that Procrastinate already provides and tests |
| Direct connection (port 5432, `db.<ref>`) | IPv6-only; measured "no route to host". Would need the paid IPv4 add-on |
| Transaction mode (port 6543) for the worker | Breaks `LISTEN`, degrading the worker to polling, and breaks prepared statements |

## Consequences

Job state lives in the same database as business state, so a job and the rows it
touches can be committed atomically — directly useful for the business/job state
separation in PRD §28.

The worker now has a hard requirement on a session-capable connection. If only a
transaction-mode URL is available, Procrastinate still functions but falls back
to polling, so job pickup latency rises; that is a degradation, not an outage.

Exit cost is moderate. Procrastinate owns its own tables and its API is reached
through our `JobQueue` abstraction (PRD §27), so replacing it means writing one
adapter plus a migration, not touching pipeline code.

## Follow-ups

- [ ] Obtain the session-mode pooler URL and confirm `LISTEN/NOTIFY` works against it
- [ ] Set `prepare_threshold=None` when wiring the transaction-mode connection
- [ ] Update PRD §18 to mark open question 4 as closed
