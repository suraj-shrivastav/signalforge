# ADR-0006: Assess each signal (relevance and summary) before clustering and topic cards

**Status:** Accepted
**Date:** 2026-09-26
**Deciders:** suraj
**PRD impact:** adds Phase 1.6 to §43; pulls a thin part of the §25 LLM gateway and the Phase 3 relevance filter forward

## Context

Phase 1.5 shows raw Hacker News hits matched by keyword queries. A keyword match
is not the niche, and a title plus a link tells an editor nothing about why it
matters. The niche is: **new advancements and innovations in AI** (models,
research results, tools, techniques, releases), not general AI news, opinion,
funding or hype.

The PRD puts the relevance filter and topic cards in Phase 3, after Phase 2
sources and clustering. Building clustering first would cluster noise. Judging
each signal first shows how good the LLM step is on real data, cheaply, before
embeddings and cards are designed.

## Decision

Insert **Phase 1.6**: assess every stored signal with an LLM and show the result.

1. A thin **LLM gateway** (PRD §25 subset): one OpenAI-compatible client, roles
   instead of model names, JSON output validated with Pydantic and one repair
   retry, every call recorded in `llm_calls` and logged, spend checked against
   the existing `Budget` before each call. A `fake` provider keeps tests and CI
   free and offline.
2. A **`SignalAssessment`** artifact and `signal_assessments` table: `is_relevant`,
   `relevance_score` (0 to 1), `category`, a one-line `summary`, a one-line
   `why_it_matters`, plus the prompt version, model and `llm_call_id`. One row per
   signal and prompt version, so a prompt change re-assesses without losing history.
3. An **`assess` stage** (function plus CLI, same shape as ingest) that scores
   unassessed signals in small batches, records a `stage_runs` row, and stops
   when the budget is exhausted.
4. `GET /signals` returns the assessment and accepts `relevant_only`. The page
   shows summary, category and score, and defaults to relevant items.

Fetched titles and text are untrusted. The prompt delimits them as data, the
model cannot call tools, and the output is validated, so an injected instruction
can at worst produce a wrong score for that one item.

## Consequences

- The page shows what matters and why, using real data, before clustering exists.
- Summaries come from the title and metadata only. Reading the linked page is
  Phase 4 (research). Summaries state this limit and must not claim facts the
  title does not support.
- Needs an `OPENROUTER_API_KEY` for real runs. Costs are small (cheap model, short
  input) and capped by the budget.
- The gateway is deliberately partial: no fallback chains, family constraints or
  routing yet. They arrive with the first stage that needs them (writer/judge).

## Alternatives considered

- **Keyword or embedding score only:** cheap, but cannot say why something matters
  or produce a summary. Embeddings arrive with clustering.
- **Build Phase 2 and 3 in full first:** the PRD's order. Rejected for the same
  reason as ADR-0005: it designs cards and clustering before seeing scored data.
- **Fetch and summarize the linked pages now:** better summaries, but adds
  extraction, robots.txt handling and prompt-injection surface. Deferred to Phase 4.

## Follow-ups

- Calibrate the prompt on ~50 hand-labelled signals before trusting scores (owner: suraj).
- Decide clustering and topic cards from what the scores show (Phase 2/3).
- Langfuse tracing ADR once the gateway is in regular use.
