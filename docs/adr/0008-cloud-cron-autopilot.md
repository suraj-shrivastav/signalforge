# ADR-0008: A cloud cron autopilot drives the pipeline through the agent API

**Status:** Accepted
**Date:** 2026-11-15
**Deciders:** suraj
**PRD impact:** none (refines how ADR-0003's queue need is met for now; the pipeline stages are unchanged)

## Context

The pipeline ran from the owner's laptop: launchd scripts called the API every 15 minutes and once per 6-hour slot. When the laptop slept, slots ran late or not at all, and a Hermes or Telegram failure could stall the driver.

Inside the API, stage runs are daemon threads in one process, guarded by one in-memory lock. That works, but a restart kills a running stage, and nothing outside the process could tell whether a slot was running or stop it.

ADR-0003 chose Procrastinate on a session-mode connection for a real queue. That needs `LISTEN/NOTIFY` and a long-lived worker with a direct line to Postgres. The Supabase direct host is IPv6-only and the network measured in ADR-0003 has no IPv6 route, so a queue worker on that network has to go through the session pooler and run as a second long-lived service with database credentials. We have not built it.

What breaks if we do nothing: no unattended operation, no kill switch an owner can reach from a phone, and no way for two runners not to double a slot.

## Decision

A host cron runs `apps/worker/autopilot.py` every 15 minutes. It drives the pipeline only through the idempotent agent API (`/agent/*`, `/cards/*`) with the revocable agent key. Slot state (a 6-hour lease with a failure count) and the kill switch live in Postgres, in the `pipeline_controls` singleton row, so any host can run it and two overlapping runs cannot both take a slot. This replaces the laptop launchd scripts, which stay in the repo as a fallback only.

## Alternatives considered

| Option | Why not |
|---|---|
| Procrastinate (ADR-0003) | Needs a long-lived worker with database credentials and `LISTEN/NOTIFY` through the session pooler, plus queue tables and a deploy. More machinery than a 15-minute cron needs while the stage threads work. Deferred, not rejected |
| GitHub Actions `schedule` | Scheduled runs start late or are skipped under load, so slot timing is unreliable; it also puts the agent key in a third system |
| Keep the laptop launchd scripts | The laptop must be on and awake. The scripts keep slot state in a local file, so nothing else can see it or stop it |

## Consequences

- The cron holds only the agent key and the API URL. It has no database credentials, no storage keys and no LLM keys, and it strips them from the images script's environment.
- Any cron host works (Render, Railway), and the owner can pause from `curl` or Telegram without the laptop.
- A mid-stage API restart loses the in-flight stage, because runs are in-process threads. The startup stale-run sweep fails the orphaned rows, and the research and draft attempt caps (two each) and the three-failures-per-slot rule bound the retries.
- Procrastinate stays deferred until mid-stage restarts lose work more than once a week. That is the re-entry trigger in the roadmap.
- Exit cost: run the launchd scripts again, or move the same API calls into a queue worker. The API and the control row do not change.

## Follow-ups

- [ ] Owner: run the 7-day soak (`docs/deploy-cron.md`).
- [ ] Move the Hermes gateway off the laptop so Telegram control does not depend on it.
