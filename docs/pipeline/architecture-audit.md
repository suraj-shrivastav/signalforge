# Pipeline architecture audit: card selection to research to draft

Date: 2026-10-21. Code state: `main` at `798e901` plus the uncommitted observability, retry and writer-endpoint changes from this session. Read-only audit: no live rows were written.

This document builds on `docs/pipeline/selection-to-draft.md` (the F1 to F26 findings). It does not repeat them. It answers three questions: is the wiring right, are the prompts good, and what must change for drafting to be structurally sound. Finding IDs of the form `A-nn` are new here. `F-nn` refers to the earlier report.

## 1. Verdict

The wiring is mechanically correct but thin. Data flows card, then package, then draft, and every hand-off is typed. The design principle behind the stages is sound: the writer only sees the research package, the judge checks stored text, and untrusted text is escaped.

Drafting is not yet structurally good, for five reasons:

1. **Prose and evidence are disconnected.** The writer produces paragraphs and, separately, a list of claims. Nothing says which sentence rests on which claim. The "verified" label therefore describes the claim list, not the article (A-01, F7).
2. **One LLM call does too many jobs.** A single call has to plan, write, hit a word band, copy verbatim quotes and emit JSON. When it fails, the whole draft fails with nothing salvageable (A-02).
3. **The editor's intent never reaches the writer.** The accepted card's angle, format and coverage gap are dropped (A-03).
4. **Quality gates fail closed with no repair path.** A stray em dash or a short draft ends in `needs_more_info` and a dead end, because the only repair loop is for invalid JSON (A-04).
5. **No way to measure prompt quality.** `tests/golden/` and `tests/e2e/` are empty. Every prompt change is judged by eye (A-05).

Operational state is separate from design: the pipeline is untriggered (no job on accept), has no per-card state machine, and until this session hid every failure.

## 2. Wiring audit

| Hand-off | Mechanism | Verdict |
| --- | --- | --- |
| Editor accept to research | Derived: latest `editor_decisions` row is `accepted` and no `research_packages` row. Picked up by the next `research` or `tick` run | Works, but nothing triggers it (F24). State is derived from three tables, not stored |
| Research to draft | `research_packages.status = researched` and no `article_drafts` row | Works. Ignores later rejection (F13) |
| Draft failure to retry | New: `--retry-failed` replaces a `failed` row | Works for drafts only. Research `failed` and `needs_more_info` rows are still dead ends |
| Card fields to writer | None | **Gap** (A-03) |
| Config to behaviour | Roles map to `ModelSpec`. Writer now has its own endpoint, cap and timeout | Works. Config hash still ignores model and prompt text (A-08) |
| Cost control | `Budget` per card, checked before each call | **Weak.** See A-06 |
| Provenance | `produced_by` stage run, `parent_ids` | Partly lost on reload (F11). No model or prompt version stored on the row (A-08) |

Things that are wired correctly and should be kept:

- Roles, not model ids, in stage code. No provider SDK outside plugins.
- Per-card budget and gateway, so one card cannot drain another.
- `ON CONFLICT (card_id)` idempotent inserts, now with replace-on-failed.
- Writer and judge family check before any card is touched.
- Untrusted text wrapped in tags and escaped, with the system prompt stating it is data.
- Mechanical checks before LLM checks (span match before judge).

## 3. Prompt review

### 3.1 Card prompt (`stages/cards.py`)

Good: untrusted-data framing, strict JSON shape with length limits, enums taken from the artifact (no drift), `risk_flags` as a closed set.

Issues:

- The card is a pitch written by a cheap model from a title and summary. Its `what_happened` is later used as both the research topic and the Tavily search query (`search.search(card.what_happened)`). A 400 char prose sentence is a weak search query. Use a short query field or derive keywords.
- `suggested_angle` and `coverage_gap` are the editor-approved intent and are not used downstream (A-03).

### 3.2 Research extraction prompt (`stages/research.py`)

Good: verbatim span rule, mechanical span check afterwards, document capped, topic and document delimited.

Issues:

- **No claim contract.** It says "claims directly relevant to the topic". It does not ask for atomic claims, or for numbers, dates, names and units to be kept in the claim text. Merged and cited claims drift in granularity: one claim is a headline, another a single score.
- **No cap or priority.** Both live packages hold 13 claims across 4 to 5 documents, with a mix of headline facts and trivia. Ask for at most N claims, ranked by relevance, with a `kind` (result, release, method, limitation, quote).
- **Limitations are never requested.** A balanced article needs limits, caveats and disagreements. The prompt asks only for relevant claims, so `Limits` sections in `paper_breakdown` have nothing to draw on.
- **Exact-substring matching is brittle.** Models normalise curly quotes, non-breaking spaces and whitespace when copying. `span_exists` is a raw `in` check, so near-misses are dropped silently or cost a repair round trip. Normalise both sides (NFKC, collapsed whitespace, unified quotes) and keep an offset map back to the original text (A-07).
- **One call per document, 30k chars each, with no relevance gate.** Off-topic documents (F18) still cost a call and add noise claims.
- No example in the prompt. One short worked example would tighten both JSON shape and span discipline.

### 3.3 Writer prompt (`stages/draft.py`, `_WRITER_SYSTEM`)

Good: sources only from the package, no web, JSON-only reply, explicit length band, em dash rule stated up front.

Issues, in order of impact:

1. **Claims and prose are separate outputs.** The writer must re-emit a verbatim `evidence_span` for each claim it wants credit for, even though research already extracted and span-checked those quotes. This duplicates work, invites copy errors, and still leaves paragraphs unchecked. The writer should cite research claim ids, never raw quotes.
2. **Length rule fights the grounding rule.** "Use every research claim and explain context from the documents to reach the minimum" plus "never add facts" is contradictory when a brief has few facts. Under pressure to reach 250 words, models pad with unsupported statements. A band should be a target for the planner, not a hard demand on the writer. A short, correct brief beats a padded one.
3. **"No mention of AI, models or generation"** forbids naming the subject of an AI publication (F17). Intended rule: never say or imply the article was written by AI.
4. **No audience, voice or editorial brief.** There is no reader description, no tone sample, no headline rules, no dek rule, and no use of the card angle. Output quality will vary by model, because nothing anchors it.
5. **Skeleton is one sentence of prose** per template. It does not say what each section must contain or which claim kinds feed it.
6. **No few-shot example** of a good brief, and no negative example of padding.
7. **Reasoning model plus `json_object` mode.** Reasoning models spend the output cap thinking (F2). The new writer cap and truncation detection handle this. A structured-output schema (`json_schema`) would also remove the repair round trip that Nemotron needed on one of two live cards.
8. **Repair prompt echoes the whole bad reply** back to the model and appends only the first three Pydantic errors. Fine for small JSON, costly for a 2k token article.

### 3.4 Judge prompt

Good: different family from the writer, boolean verdicts, untrusted framing.

Issues:

- It sees every document in full (20k to 35k tokens) to judge 8 to 13 one-line claims. Send only the cited documents' windows around each quote (F16).
- It never sees the article sentence, only the claim text. It cannot detect that a paragraph overstates a claim.
- It returns a bare boolean. A `verdict` of supported, partial or unsupported plus a short reason or quoted support gives the editor something to act on and gives you something to evaluate the judge with.
- A missing verdict counts as not supported. That is the right fail-closed default, but it should also be counted and surfaced as a judge failure, not silently folded into `uncertain`.

## 4. Architectural findings

| ID | Sev | Finding | Why it matters | Recommended change |
| --- | --- | --- | --- | --- |
| A-01 | high | The body schema (`sections[].paragraphs[]` of plain strings) cannot express which claim supports which sentence | The editor cannot audit the article, and the publish gate cannot enforce "every factual sentence is cited" (PRD FR-08) | Body schema v2: paragraphs are lists of sentences, each with `claim_ids`. Sentences with no claim must be marked `connective` (no facts) or the draft fails the gate |
| A-02 | high | One call does plan, write, quote, and format. A failure at any step discards everything | Expensive retries, no partial progress, hard to improve one step | Split into: (1) outline from claims, small and cheap, deterministic validation; (2) write each section from its assigned claims; (3) deterministic assembly and checks; (4) judge on sentences. Each step is a role with its own cap, model and test |
| A-03 | high | Card `suggested_angle`, `format` and `coverage_gap` are not passed to the planner | The system writes something other than what the editor accepted (F15 is one symptom: `deep_dive` becomes a news brief) | Pass an `EditorBrief` (angle, format, gap, title) into the outline step. Keep the "writer sees only the package" rule by making the brief part of the stored input artifact, not a live card read |
| A-04 | high | Gate failures end in `needs_more_info` with no repair step | Em dash, banned phrase and word-count failures are mechanical and fixable. They currently cost a full paid draft | Deterministic fixes first (dash replacement). Then one targeted revise call that receives the exact failures and the offending section only |
| A-05 | high | No evaluation set. `tests/golden/` and `tests/e2e/` are empty | Prompt and model changes (like today's Nemotron switch) cannot be compared. Regressions are invisible | Build a 10 to 15 card golden set from stored packages. Score with deterministic metrics (span pass rate, uncited sentence count, band hit, banned-phrase hits) plus the judge. Run on every prompt or model change |
| A-06 | high | Cost control is a soft cap and is blind for non-OpenRouter models | `ModelSpec` has no prices, and `_cost` uses the provider-reported `usage.cost`. NVIDIA replies carry none, so the writer is recorded at $0 and the per-article budget never trips (the new writer endpoint made this real) | Put per-role prices in config. Estimate worst-case cost (input estimate plus cap) and pass it to `Budget.check` before each call (F8). Log a warning only once per model, not per call |
| A-07 | medium | Evidence matching is exact-substring on raw text, and stored text is capped at 30k chars while the span check runs on the full text | Valid quotes are rejected on punctuation or whitespace. Quotes found in research are missing in the capped stored text, so the draft stage drops them (F12) | Normalised matching with offsets recorded at research time. Store the exact span and offsets, then verify in draft by offset, not by re-searching |
| A-08 | medium | No model, prompt version or config on the stored rows. `stage_config_hash` is the prompt version only | You cannot tell which model and prompt produced a draft, or whether two drafts are comparable. A model swap does not mark old drafts stale | Add `prompt_version`, `writer_model`, `judge_model` and a config hash covering role models, caps and band table. Store them on `article_drafts` and `research_packages` |
| A-09 | medium | No per-card stage state. `drafting` and `researching` exist as enums but are never written | A crash mid-card leaves no trace and two runs can process the same card (F22) | Per-card `stage_runs` (F10) and a claim step: insert an in-flight row, select with `FOR UPDATE SKIP LOCKED`. This is the foundation for a job queue |
| A-10 | medium | Research failures remain invisible and unretryable | Only drafts got `failure_reason` and `--retry-failed`. A card whose research failed is stuck forever | Same migration pattern for `research_packages`, same flag on the research CLI |
| A-11 | medium | `stages/draft.py` mixes prompts, orchestration, parsing and persistence in one 400 line module | Hard to test a prompt alone, and every prompt tweak touches orchestration | Move prompt text to versioned modules (`prompts/draft_writer_v3.py`) with a builder per prompt, and keep `draft.py` as orchestration |
| A-12 | medium | Trigger and scheduling: `tick` runs stages in sequence on a cron that is not installed here | Accepting a card does nothing visible for hours. Editors cannot see progress | Job per decision (ADR-0003, Procrastinate): accept enqueues research, research success enqueues draft. Until then, add a pipeline status per card to the editor console (F14) |
| A-13 | low | `GET /editor/drafts` shows no failure reason or attempt count in the UI | The reason is now stored and returned by the API, but the console still renders "Drafting failed." | Show `failure_reason` in `ArticlePreview` and the list row |
| A-14 | low | Writer endpoint is configured through an alias to a vendor-named env var (`NVIDIA_API`) | Works, but ties generic config to one vendor's variable name | Document `LLM_WRITER_API_KEY` as the canonical name and treat `NVIDIA_API` as a legacy alias |
| A-15 | low | Secrets hygiene: provider errors can carry `detail` text from the upstream body (first 200 chars) into `llm_calls.error` and logs | Low risk today (402 text contained no secret), but upstream error bodies are untrusted | Keep the 200 char cap, strip anything that looks like a key or bearer token before storing |

## 5. What "structurally good" drafting looks like

Target flow. Each box is a role, a versioned prompt, a typed artifact, and a test.

```
EditorBrief (card angle, format, gap) + ResearchPackage (docs, claims with ids and offsets)
   |
   v
1. plan      cheap model     -> Outline: sections, each with claim_ids and a purpose
   |   deterministic check: every claim id exists; the outline covers the lead claims
   v
2. write     writer model    -> per section: sentences, each tagged with claim_ids or connective
   |   deterministic checks per section: ids valid, no new numbers or names absent from cited claims,
   |   banned phrases, dash rule (auto-fixed), no uncited factual sentence
   v
3. assemble  code            -> ArticleBody v2 with sources derived from cited documents only
   |   gate: band, structure, title and dek rules
   v
4. judge     different family -> per sentence: supported / partial / unsupported + short reason
   |   input: only the cited claim windows, not whole documents
   v
5. revise    writer model, once -> only if a gate or judge failure is local to a section
   v
ArticleDraft: status, body, claim_status per claim, sentence_status per sentence,
              model + prompt versions, failure_reason, cost, calls
```

Properties this gives you:

- **Verifiable by construction.** Every factual sentence points at a claim, every claim at a span with offsets, every span at a document. "Verified" means something.
- **Cheap failure.** A failed section is regenerated, not the article.
- **Small prompts.** The writer sees the claims for one section plus short windows, not 100k characters.
- **Comparable.** Pinned prompt and model versions let the golden set show whether a change helped.

## 6. Recommended order of work

Each item is sized for one PR of at most 400 changed lines. Items 1 to 3 finish the debugging work already in flight. The rest matches the earlier report's order where it overlaps.

| # | Change | Findings | Size |
| --- | --- | --- | --- |
| 1 | Commit the current work (observability, retry, writer endpoint). Apply migration 0008 and retry one draft | F1, F5, F9 | done locally |
| 2 | Research: `failure_reason` and `--retry-failed` | A-10, F1 | about 250 lines |
| 3 | Prices in config, worst-case estimate before each call, show failure reason in the console | A-06, A-13, F8 | about 300 lines |
| 4 | Golden set and a scoring script (no prompt changes yet). Run it on current prompts to get a baseline | A-05 | about 350 lines |
| 5 | Stop mapping similarity to conflict. Store related pairs as data | F6 | about 150 lines |
| 6 | Normalised span matching with offsets, plus stored-text hash | A-07, F12 | about 300 lines |
| 7 | Provenance columns: prompt version, models, config hash | A-08 | about 200 lines |
| 8 | Body schema v2 (sentences with claim ids) and the sentence-level gate | A-01, F7 | about 400 lines |
| 9 | Planner step and `EditorBrief`, writer by section, bounded revise | A-02, A-03, A-04 | two PRs |
| 10 | Judge on windows, with reasons | F16, section 3.4 | about 250 lines |
| 11 | Per-card stage runs, claim-before-work locking, then job-per-decision trigger | A-09, A-12, F10, F22, F24 | two or three PRs |
| 12 | Prompt modules and few-shot examples, tuned against the golden set | A-11, section 3 | about 300 lines |

Order rationale: the baseline (4) must come before any prompt rewrite (8 to 12), otherwise you cannot tell whether the rewrite helped. Cost control (3) must come before more LLM calls are added by the planner and reviser.

## 7. Decisions that need the project owner

1. **Do paragraphs need sentence-level citations?** The audit recommends yes (A-01). It changes the article schema and the editor preview, and it is the largest piece of work.
2. **Does card format override the source type for templates?** Today a `deep_dive` card becomes a 250 to 400 word brief (F15).
3. **Should a later rejection stop drafting?** Today it does not (F13).
4. **Which writer model is the long-term default?** Fable 5.1 is blocked by account credit. Nemotron 3 Ultra via NVIDIA works, is unpriced in this system, and needed one repair retry in two live runs. The golden set (item 4) is the way to decide this on evidence rather than on availability.

## 8. What was checked

- Read: `stages/research.py`, `stages/research_extraction.py`, `stages/draft.py`, `stages/draft_extraction.py`, `stages/cards.py` (prompt section), `llm/gateway.py`, `llm/providers.py`, `llm/roles.py`, `core/budget.py`, `core/config.py`, `apps/worker/tick.py`, `apps/worker/draft.py`, the repositories and migrations, and the earlier debug report.
- Ran earlier this session: one rolled-back writer and judge pass on each live package with three writer models. Results: Fable 5.1 fails with HTTP 402 (credit), GPT-4o-mini and Nemotron 3 Ultra both complete a draft that ends `needs_more_info`.
- Not checked: the web console code beyond what the earlier report covered, integration tests (no `TEST_DATABASE_URL`), and prompt quality on a real reader-facing sample. Section 3 is a prompt design review, not an evaluation.

## 9. Verification and grounding fixes (2026-10-21)

Findings re-checked against the code and against a real run (writer `nvidia/nemotron-3-ultra-550b-a55b`, judge `google/gemini-2.5-flash-lite`, live package b84beb7f, session rolled back, about $0.0005).

| Finding | Re-check | Status |
| --- | --- | --- |
| A-01 / F7 prose not tied to claims | Confirmed in code and in a live run: the old reply let any paragraph text through | **Fixed**: every sentence cites research claim ids. Code rejects uncited sentences and numbers absent from the cited claims and their context. Paragraph citations are stored (`ArticleSection.citations`, `ArticleDraft` schema v2) |
| Writer invents quotes (new) | Writer re-emitted `evidence_span` itself | **Fixed**: article claims are copied from the research package, never written by the model |
| F16 oversized writer and judge input | 100k chars to the writer, 35k tokens to the judge | **Fixed**: both see only each claim's quote plus a 300 char window. Judge prompt is a few KB |
| Judge never saw the article sentence | Confirmed | **Fixed**: judge now rules per sentence against its cited evidence. Any unconfirmed sentence blocks the draft (`needs_more_info`) |
| F6 similar claims marked `conflicting` | Confirmed (R2) | **Mitigated**: drafting no longer derives `conflicting` from the similarity heuristic. A real contradiction check is still open |
| A-03 editor intent dropped | Confirmed | **Partly fixed**: the card's `suggested_angle` is passed as an untrusted `<editor_brief>`. Format and gap are not used yet |
| F17 "no mention of AI" | Confirmed | **Fixed**: rule now forbids implying the article was written by AI only |
| Length rule forced padding | Confirmed by prompt reading | **Fixed in the prompt** ("write fewer words rather than pad"). The band gate still applies, so a short grounded draft lands in `needs_more_info` with the reason |
| Research claims included vague filler (new) | Live package held "this advancement is significant" and "has certain limitations" as claims | **Fixed**: `research-v2` prompt asks for concrete facts only, at most 15, standalone, numbers kept. Existing packages keep the old claims until researched again |
| A-02, A-04, A-05, A-06, A-07 to A-12 | Unchanged | Open, see section 6 |

Live result for b84beb7f after the fixes: the draft is `needs_more_info`. Two sentences were blocked, one for a number (740) missing from its cited claim context and one that the judge did not confirm (an Apache 2.0 licence claim). That is the intended outcome: the system now says exactly what it could not ground instead of publishing it.

Residual gaps in grounding: a sentence can still misstate a fact that has no number (only the judge catches that), name checks are advisory notes rather than blocks, and `conflicting` needs a real contradiction check.
