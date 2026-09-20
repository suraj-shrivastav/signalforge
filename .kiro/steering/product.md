# SignalForge Product Context

Autonomous AI-technology intelligence platform. It discovers emerging signals in **AI engineering**, surfaces them to an editor, researches selected topics from stored evidence, and publishes verified, traceable articles for humans and AI systems.

**The article is the output. The intelligence system behind it is the product.** Not an AI writer.

Full detail: `docs/signalforge_prd.md` (v1.2, ~940 lines). Read it on demand; do not assume its contents.

## Core loop

```text
Observe → Detect → Understand → Select → Research → Verify → Explain → Structure → Publish → Learn
```

Wide ingest (~500-2000 signals/day) narrows to **1 published article/day**. Two human gates:

1. **Editor review 1** — topic triage, picks from ~40-50 topic cards/night (accept / reject+reason / snooze / need-more-info)
2. **Editor review 2** — draft review via risk summary (approve / revise / reject)

SEO and structuring run **before** review 2, so the editor approves exactly what ships.

## Non-negotiables

These are product invariants, not preferences. Do not design around them.

- **Quality over quota.** If nothing meets the bar, the slot is skipped. Never publish to fill a slot.
- **Research before writing.** The writer's only input is the `ResearchPackage`, never the open web.
- **Evidence before claims.** Claims link to a stored, hashed document version and a character span, not a URL.
- **Deterministic before LLM.** Use code, parsers and rules wherever reliable.
- **Verify against stored source text,** never against another model's summary (avoids circular verification).
- **Writer model family ≠ judge model family.** Enforced at startup.
- **Plug-in everything.** Sources, search, models, publisher, rankers, verticals and stages are replaceable via config.
- **Provenance is required.** Every article must answer "why was this published?" and "what evidence produced this sentence?"
- **Authorship:** published under the brand. AI authorship is not advertised, and no fabricated human persona. The writer must not make first-person or experiential claims ("I tested this") without an executed experiment in the research package.

## Claim status enum

One enum everywhere (artifacts, verification, dashboard, DB constraint):

`verified` · `supported` · `uncertain` · `conflicting` · `unverified`

Core claims must be `verified` or `supported`. `uncertain`/`unverified` are removed, hedged or explicitly editor-approved. `conflicting` is presented as disputed with both sources, or removed. Every editor override is logged with a reason.

## Autonomy

V1 is **L2**: automated research + drafting, human topic selection, human draft approval. Autonomy increases only on measured quality.

## Out of scope for V1

Designed for, not built: claim/evidence graph, entity ontology, public/MCP APIs, automatic article updates, analytics-driven selection, executed-experiment pipeline, additional verticals. Don't build these unless asked.
